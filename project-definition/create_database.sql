-- =============================================================================================
-- MailySoft System API: creación de la base de datos completa (equivale a las migraciones 0001-0002)
--
-- Contenido: catálogo de estatus de las suscripciones (con sus 4 estatus iniciales), tabla de
-- suscripciones, el índice único del nombre y el disparador que mantiene subscriptions.updated_at.
-- No carga suscripciones: el catálogo empieza vacío y se llena con la API.
--
-- Las claves primarias, únicas y foráneas y las restricciones NOT NULL y CHECK no se nombran aquí:
-- PostgreSQL las crea solas (subscriptions_pkey, subscriptions_status_id_fkey,
-- subscriptions_name_check...). Solo llevan nombre el índice subscriptions_name_not_deleted_key (la
-- aplicación lo usa para traducir un nombre repetido a un 409), la función set_updated_at y su
-- disparador.
--
-- IMPORTANTE: úsalo en una base de datos PROPIA de este servicio, no en la de mailySoft-usuarios.
-- Ambos proyectos crean la tabla `alembic_version` y la función `set_updated_at()`, y no pueden
-- compartirlas. Si ya existen, el script se detiene sin cambiar nada y lo explica.
--
-- Cómo usarlo (PostgreSQL 17 o superior; se ejecuta entero en una transacción, así que si algo falla
-- no queda nada a medias; no se puede ejecutar dos veces sobre la misma base):
--   1. Crear una base vacía, una sola vez:   CREATE DATABASE maily_system;
--   2. Conectarse a ella y ejecutar este archivo, por ejemplo:
--        psql -U postgres -d maily_system -v ON_ERROR_STOP=1 -f project-definition/create_database.sql
--      o, contra un servidor remoto (Azure, por ejemplo):
--        psql "host=<servidor> port=5432 dbname=maily_system user=<usuario> sslmode=require" ^
--             -v ON_ERROR_STOP=1 -f project-definition/create_database.sql
--
-- La estructura de referencia, comentada, está en DATA_SCHEMA.md; este archivo la repite y añade los
-- datos iniciales y el registro de la versión de Alembic.
-- =============================================================================================

BEGIN;

SET search_path TO public;

-- Protección: si la base ya tiene algo de esto (p. ej. es la de mailySoft-usuarios), se detiene
-- aquí con un mensaje claro en lugar de fallar a medias.
DO $$
BEGIN
	IF to_regclass('public.alembic_version') IS NOT NULL
	   OR to_regclass('public.subscriptions') IS NOT NULL
	   OR to_regclass('public.subscription_statuses') IS NOT NULL
	   OR to_regprocedure('public.set_updated_at()') IS NOT NULL THEN
		RAISE EXCEPTION 'Esta base de datos ya tiene tablas o funciones de este servicio (alembic_version, subscriptions, subscription_statuses o set_updated_at). Use una base de datos vacía y exclusiva de MailySoft System API.';
	END IF;
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Catálogo de estatus  -- [spec 001-subscriptions-api FR-022]
-- Se administra a mano (sin API). Los estatus del sistema (1 a 4) se reconocen por su
-- identificador, no por su nombre: no deben eliminarse ni renumerarse. Otros estatus pueden
-- añadirse a mano con identificador >= 5.
-- ---------------------------------------------------------------------------------------------

CREATE TABLE subscription_statuses (
	id serial4 PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	description text
);

-- ---------------------------------------------------------------------------------------------
-- Suscripciones  -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- ---------------------------------------------------------------------------------------------

CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
	monthly_price numeric(10,2) NOT NULL CHECK (monthly_price >= 0), -- [spec FR-013] pesos mexicanos, nunca float
	features text[] NOT NULL DEFAULT '{}' CHECK (cardinality(features) <= 20), -- [spec FR-012] lista ordenada de textos libres
	status_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_statuses (id), -- [spec FR-011] 1 = Activa
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- [spec FR-014] el nombre es único, sin distinguir mayúsculas, entre las suscripciones no
-- eliminadas (estatus distinto de 4 = Eliminada): el nombre de una Eliminada queda libre y el de
-- una Inactiva o Bloqueada sigue reservado.
CREATE UNIQUE INDEX subscriptions_name_not_deleted_key ON subscriptions (lower(name)) WHERE status_id <> 4;

-- [spec FR-015] la fecha de última modificación cambia con cualquier UPDATE (también con el cambio
-- de estatus).
CREATE FUNCTION set_updated_at() RETURNS trigger
	LANGUAGE plpgsql
	AS $$
BEGIN
	NEW.updated_at = CURRENT_TIMESTAMP;
	RETURN NEW;
END;
$$;

CREATE TRIGGER subscriptions_set_updated_at
	BEFORE UPDATE ON subscriptions
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------------------
-- Datos iniciales: los 4 estatus del sistema  -- [spec 001-subscriptions-api FR-022]
-- ---------------------------------------------------------------------------------------------

INSERT INTO subscription_statuses (id, name, description) VALUES
	(1, 'Activa',    'Disponible y ofrecida a clínicas nuevas.'),
	(2, 'Inactiva',  'Retirada de la oferta; las clínicas que ya la tienen la conservan.'),
	(3, 'Bloqueada', 'Suspendida por la administración.'),
	(4, 'Eliminada', 'Baja lógica: fuera de toda consulta y operación.');

-- Los estatus que se añadan a mano empezarán en 5.
SELECT setval(pg_get_serial_sequence('subscription_statuses', 'id'), 4);

-- ---------------------------------------------------------------------------------------------
-- Versión de Alembic  -- [Principio VI de la constitución]
-- Marca la base como creada hasta la migración 0002, para que `alembic upgrade head` no intente
-- volver a crear las tablas y las migraciones futuras se apliquen sobre esta base.
-- ---------------------------------------------------------------------------------------------

CREATE TABLE alembic_version (
	version_num varchar(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('0002');

COMMIT;

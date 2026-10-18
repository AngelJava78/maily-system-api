-- Esquema de la feature 001-subscriptions-api (PostgreSQL 17).
-- Es el contenido que entregan las migraciones 0001 y 0002 y el que se refleja en
-- project-definition/DATA_SCHEMA.md (esquema objetivo del proyecto).
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK NO se declaran con nombre:
-- PostgreSQL las crea solas con su nombre automático (<tabla>_pkey, <tabla>_<columna>_key,
-- <tabla>_<columna>_fkey, <tabla>_<columna>_check). Llevan nombre explícito solo el índice
-- parcial del nombre (la aplicación lo usa para traducir un nombre repetido a un 409), la función
-- y el disparador de updated_at.

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
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
	NEW.updated_at = CURRENT_TIMESTAMP;
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER subscriptions_set_updated_at
	BEFORE UPDATE ON subscriptions
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------------------
-- Datos iniciales (migración 0002)  -- [spec 001-subscriptions-api FR-022]
-- ---------------------------------------------------------------------------------------------
INSERT INTO subscription_statuses (id, name, description) VALUES
	(1, 'Activa',    'Disponible y ofrecida a clínicas nuevas.'),
	(2, 'Inactiva',  'Retirada de la oferta; las clínicas que ya la tienen la conservan.'),
	(3, 'Bloqueada', 'Suspendida por la administración.'),
	(4, 'Eliminada', 'Baja lógica: fuera de toda consulta y operación.');

-- Los estatus añadidos a mano empiezan en 5.
SELECT setval(pg_get_serial_sequence('subscription_statuses', 'id'), 4);

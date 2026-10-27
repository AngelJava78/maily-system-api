-- =============================================================================================
-- MailySoft System API: creación de la base de datos completa (equivale a las migraciones
-- 0001 a 0006: esquema de suscripciones, catálogo de estatus con sus 4 estatus iniciales,
-- corrección del modelo de suscripciones -- spec 004--, registro de componentes monitoreados
-- -- spec 005--, el tipo de suscripción -- spec 006-- y el límite de clínicas -- spec 007--).
--
-- Contenido: catálogo de estatus de las suscripciones, tabla de suscripciones ya con precio
-- anual, días de prueba, autoconsumo, módulos, los cinco límites de la clínica y el tipo de
-- suscripción; el registro de componentes monitoreados; el índice único del nombre de cada tabla
-- y la función/disparador que mantiene `updated_at`. No carga suscripciones ni componentes: ambos
-- catálogos empiezan vacíos y se llenan con la API.
--
-- Las claves primarias, únicas y foráneas y las restricciones NOT NULL y CHECK de una sola columna
-- no se nombran aquí: PostgreSQL las crea solas (subscriptions_pkey, subscriptions_status_id_fkey,
-- subscriptions_name_check...). Sí llevan nombre explícito el CHECK de dos columnas
-- `subscriptions_clinics_limit_check` -- [spec 007-add-clinics-limit] (PostgreSQL no le da uno
-- estable), los índices parciales del nombre (la aplicación los usa para traducir un nombre
-- repetido a un 409), la función set_updated_at y sus disparadores.
--
-- IMPORTANTE: úsalo en una base de datos PROPIA de este servicio, no en la de mailySoft-usuarios
-- (ni en ninguna otra base que ya tenga tablas o datos ajenos a este servicio). Ambos proyectos
-- crean la tabla `alembic_version` y la función `set_updated_at()`, y no pueden compartirlas: si
-- se ejecuta sobre una base que ya tiene objetos de otro servicio, Alembic de ambos proyectos
-- termina leyendo y escribiendo la misma `alembic_version`, y las migraciones de uno pueden
-- fallar o corromper el historial del otro. Si ya existen, el script se detiene sin cambiar nada
-- y lo explica.
--
-- Cómo usarlo (PostgreSQL 17 o superior; se ejecuta entero en una transacción, así que si algo falla
-- no queda nada a medias; no se puede ejecutar dos veces sobre la misma base):
--   1. Crear una base vacía, una sola vez:   CREATE DATABASE maily_system;
--   2. Conectarse a ella y ejecutar este archivo, por ejemplo:
--        psql -U postgres -d maily_system -v ON_ERROR_STOP=1 -f project-definition/create_database.sql
--      o, contra un servidor remoto (Azure, por ejemplo, en una base dedicada y vacía):
--        psql "host=<servidor> port=5432 dbname=<base-propia-y-vacia> user=<usuario> sslmode=require" ^
--             -v ON_ERROR_STOP=1 -f project-definition/create_database.sql
--
-- La estructura de referencia, comentada, está en DATA_SCHEMA.md; este archivo la repite y añade los
-- datos iniciales y el registro de la versión de Alembic.
-- =============================================================================================

BEGIN;

SET search_path TO public;

-- Protección: si la base ya tiene algo de esto (p. ej. es la de mailySoft-usuarios, o ya tiene
-- este mismo esquema de una ejecución anterior), se detiene aquí con un mensaje claro en lugar de
-- fallar a medias.
DO $$
BEGIN
	IF to_regclass('public.alembic_version') IS NOT NULL
	   OR to_regclass('public.subscriptions') IS NOT NULL
	   OR to_regclass('public.subscription_statuses') IS NOT NULL
	   OR to_regclass('public.subscription_types') IS NOT NULL
	   OR to_regclass('public.monitored_components') IS NOT NULL
	   OR to_regprocedure('public.set_updated_at()') IS NOT NULL THEN
		RAISE EXCEPTION 'Esta base de datos ya tiene tablas o funciones de este servicio (alembic_version, subscriptions, subscription_statuses, subscription_types, monitored_components o set_updated_at). Use una base de datos vacía y exclusiva de MailySoft System API.';
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
-- Tipos de suscripción  -- [spec 006-add-subscription-type FR-001]
-- Catálogo administrado a mano, misma forma que subscription_statuses: id estable, name editable.
-- Sin operación de la API para administrarlo; se amplía insertando una fila.
-- ---------------------------------------------------------------------------------------------

CREATE TABLE subscription_types (
	id serial4 PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	description text
);

-- ---------------------------------------------------------------------------------------------
-- Suscripciones  -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo, módulos (claves de un catálogo EXTERNO, propiedad de la API de usuarios: no hay
-- tabla de módulos en este esquema) y los cuatro límites de la clínica. La antigua `features` se
-- renombra a `other_features` (mismo contenido, acotado a lo que no es un módulo).
-- [spec 006-add-subscription-type FR-001 a FR-010]: `subscription_type_id` (a quién va dirigida la
-- suscripción), obligatorio, inmutable por la aplicación, referencia al catálogo subscription_types.
-- [spec 007-add-clinics-limit FR-001 a FR-007]: `clinics_limit`, el quinto límite de la clínica,
-- con su rango acotado por `subscription_type_id` (exactamente 1 si es Individual; 1 a 100 si no).
-- ---------------------------------------------------------------------------------------------

CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
	subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types (id), -- [spec 006 FR-001, FR-002, FR-008] 1 = Individual; fija desde la creación (FR-004)
	monthly_price numeric(10,2) NOT NULL CHECK (monthly_price >= 0), -- [spec 001 FR-013] pesos mexicanos, sin IVA, nunca float
	annual_price numeric(10,2) NOT NULL CHECK (annual_price >= 0), -- [spec 004 FR-012] independiente de monthly_price
	trial_days int4 NOT NULL DEFAULT 0 CHECK (trial_days BETWEEN 0 AND 3650), -- [spec 004 FR-013] 0 = sin periodo de prueba
	self_service bool NOT NULL DEFAULT false, -- [spec 004 FR-014] autoconsumo en el portal de MailySoft
	module_keys text[] NOT NULL DEFAULT ARRAY['patients']::text[] CHECK ('patients' = ANY(module_keys)), -- [spec 004 FR-015 a FR-019] claves de módulos de tipo Clínica de la API de usuarios
	other_features text[] NOT NULL DEFAULT '{}' CHECK (cardinality(other_features) <= 20), -- [spec 004 FR-024] lista ordenada de textos libres que no son módulos
	consulting_rooms_limit int4 NOT NULL CHECK (consulting_rooms_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021] techo informativo
	doctors_limit int4 NOT NULL CHECK (doctors_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	assistants_limit int4 NOT NULL CHECK (assistants_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	new_patients_per_year_limit int4 NOT NULL CHECK (new_patients_per_year_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	clinics_limit int4 NOT NULL DEFAULT 1, -- [spec 007 FR-001] quinto límite; ver el CHECK de dos columnas, abajo
	status_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_statuses (id), -- [spec 001 FR-011] 1 = Activa
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT subscriptions_clinics_limit_check CHECK ( -- [spec 007 FR-002, FR-003] respaldo defensivo: la API ya impide llegar a violarlo
		(subscription_type_id = 1 AND clinics_limit = 1)
		OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)
	)
);

-- [spec 001 FR-014] el nombre es único, sin distinguir mayúsculas, entre las suscripciones no
-- eliminadas (estatus distinto de 4 = Eliminada): el nombre de una Eliminada queda libre y el de
-- una Inactiva o Bloqueada sigue reservado.
CREATE UNIQUE INDEX subscriptions_name_not_deleted_key ON subscriptions (lower(name)) WHERE status_id <> 4;

-- [spec 001 FR-015] la fecha de última modificación cambia con cualquier UPDATE (también con el
-- cambio de estatus). Compartida con `monitored_components` (spec 005).
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
-- Registro de componentes monitoreados  -- [spec 005-health-monitoring FR-023 a FR-032]
-- Servicios y frontends cuya salud agrega GET /api/v1/health. Los dos componentes integrados
-- (maily-system-api y database) NO se guardan aquí: sus códigos están reservados. La baja es
-- lógica (deleted_at con fecha); la fila se conserva y su code queda libre. Empieza vacío: no hay
-- datos iniciales.
-- ---------------------------------------------------------------------------------------------

CREATE TABLE monitored_components (
	id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	code varchar(50) NOT NULL CHECK (
		char_length(code) BETWEEN 2 AND 50
		AND code ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'
		AND code NOT IN ('maily-system-api', 'database')
	), -- [spec 005 FR-024]
	name varchar(100) NOT NULL CHECK (btrim(name) <> '' AND name = btrim(name)), -- [spec 005 FR-024]
	kind varchar(20) NOT NULL CHECK (kind IN ('service', 'frontend')), -- [spec 005 FR-024]
	base_url varchar(255) NOT NULL, -- [spec 005 FR-025] sin credenciales, query ni fragmento (lo valida el servicio)
	live_path varchar(200) NOT NULL, -- [spec 005 FR-026]
	ready_path varchar(200), -- [spec 005 FR-026] NULL en un frontend
	info_path varchar(200), -- [spec 005 FR-026] opcional en un frontend
	enabled bool NOT NULL DEFAULT true, -- [spec 005 FR-024]
	sort_order int4 NOT NULL DEFAULT 0 CHECK (sort_order BETWEEN 0 AND 9999), -- [spec 005 FR-024]
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	deleted_at timestamptz, -- [spec 005 FR-029] baja lógica; no se publica
	CONSTRAINT monitored_components_service_paths_check
		CHECK (kind <> 'service' OR (ready_path IS NOT NULL AND info_path IS NOT NULL)),
	CONSTRAINT monitored_components_frontend_ready_path_check
		CHECK (kind <> 'frontend' OR ready_path IS NULL)
);

-- [spec 005 FR-024, FR-028, FR-029] código único entre los componentes no eliminados.
CREATE UNIQUE INDEX monitored_components_code_not_deleted_key
	ON monitored_components (code) WHERE deleted_at IS NULL;

-- [spec 005 FR-028] updated_at cambia con cualquier UPDATE (reutiliza set_updated_at de arriba).
CREATE TRIGGER monitored_components_set_updated_at
	BEFORE UPDATE ON monitored_components
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
-- Datos iniciales: los dos tipos de hoy  -- [spec 006-add-subscription-type FR-001]
-- ---------------------------------------------------------------------------------------------

INSERT INTO subscription_types (id, name, description) VALUES
	(1, 'Individual',  'Para médicos independientes; su consultorio se asocia a una sola clínica.'),
	(2, 'Empresarial', 'Para empresas con varias clínicas y varios consultorios por clínica.');

-- Los tipos que se añadan a mano empezarán en 3.
SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2);

-- ---------------------------------------------------------------------------------------------
-- Versión de Alembic  -- [Principio VI de la constitución]
-- Marca la base como creada hasta la migración 0006, para que `alembic upgrade head` no intente
-- volver a crear las tablas y las migraciones futuras se apliquen sobre esta base.
-- ---------------------------------------------------------------------------------------------

CREATE TABLE alembic_version (
	version_num varchar(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('0006');

COMMIT;

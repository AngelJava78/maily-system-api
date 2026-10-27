-- Esquema de la feature 007-add-clinics-limit (PostgreSQL 17), sobre lo que ya entregan las
-- migraciones 0001 a 0005 (001-subscriptions-api, 004-correct-subscriptions-api,
-- 005-health-monitoring y 006-add-subscription-type).
--
-- Esta es la tabla `subscriptions` COMPLETA, más la tabla `subscription_types` (sin cambios de
-- 006), tal como deben quedar tras aplicar 0001 a 0006 (0006 introduce esta feature).
-- `subscription_statuses` y `monitored_components` no cambian: ver
-- specs/001-subscriptions-api/contracts/database-schema.sql y
-- specs/005-health-monitoring/contracts/database-schema.sql.
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK de una sola columna NO se
-- declaran con nombre: PostgreSQL las crea solas con su nombre automático (<tabla>_pkey,
-- <tabla>_<columna>_key, <tabla>_<columna>_fkey, <tabla>_<columna>_check). El CHECK nuevo de dos
-- columnas (clinics_limit) SÍ lleva nombre explícito, igual que el índice parcial del nombre, la
-- función y el disparador de updated_at (sin cambios respecto a 001/006).

-- ---------------------------------------------------------------------------------------------
-- Tipos de suscripción -- [spec 006-add-subscription-type FR-001] -- SIN CAMBIOS en esta feature
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscription_types (
	id serial4 PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	description text
);

-- ---------------------------------------------------------------------------------------------
-- Suscripciones -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo, módulos (claves externas, no una tabla propia) y los cuatro límites de la clínica.
-- [spec 006-add-subscription-type FR-001 a FR-010]: `subscription_type_id`, obligatorio,
-- inmutable por la aplicación, referencia a subscription_types.
-- [spec 007-add-clinics-limit FR-001 a FR-010]: `clinics_limit`, el quinto límite, con su rango
-- acotado por el tipo de la suscripción (exactamente 1 si es Individual; 1 a 100 si no lo es).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
	subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types (id), -- [spec 006 FR-001, FR-002, FR-008] 1 = Individual; fija desde la creación (FR-004)
	monthly_price numeric(10,2) NOT NULL CHECK (monthly_price >= 0), -- pesos mexicanos, sin IVA, nunca float
	annual_price numeric(10,2) NOT NULL CHECK (annual_price >= 0), -- [spec 004 FR-012] independiente de monthly_price, sin proporción obligatoria
	trial_days int4 NOT NULL DEFAULT 0 CHECK (trial_days BETWEEN 0 AND 3650), -- [spec 004 FR-013] 0 = sin periodo de prueba
	self_service bool NOT NULL DEFAULT false, -- [spec 004 FR-014] autoconsumo en el portal de MailySoft; nace en falso
	module_keys text[] NOT NULL DEFAULT ARRAY['patients']::text[] CHECK ('patients' = ANY(module_keys)), -- [spec 004 FR-015 a FR-019] claves de módulos de tipo Clínica de la API de usuarios; Pacientes siempre incluido
	other_features text[] NOT NULL DEFAULT '{}' CHECK (cardinality(other_features) <= 20), -- [spec 004 FR-024] lista ordenada de textos libres que no son módulos (antes `features`)
	consulting_rooms_limit int4 NOT NULL CHECK (consulting_rooms_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021] techo informativo, no un contador de uso
	doctors_limit int4 NOT NULL CHECK (doctors_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	assistants_limit int4 NOT NULL CHECK (assistants_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	new_patients_per_year_limit int4 NOT NULL CHECK (new_patients_per_year_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	clinics_limit int4 NOT NULL DEFAULT 1, -- [spec 007 FR-001 a FR-003, FR-007] quinto límite; ver el CHECK con nombre explícito, abajo
	status_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_statuses (id), -- [spec 001 FR-011] 1 = Activa
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT subscriptions_clinics_limit_check CHECK ( -- [spec 007 FR-002, FR-003, research R6] respaldo defensivo; Pydantic y el Service ya impiden que la API llegue a violarlo
		(subscription_type_id = 1 AND clinics_limit = 1)
		OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)
	)
);

-- [spec 001 FR-014] el nombre es único, sin distinguir mayúsculas, entre las suscripciones no
-- eliminadas (estatus distinto de 4 = Eliminada). Sin cambios en esta feature.
CREATE UNIQUE INDEX subscriptions_name_not_deleted_key ON subscriptions (lower(name)) WHERE status_id <> 4;

-- [spec 001 FR-015] la fecha de última modificación cambia con cualquier UPDATE. Sin cambios.
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
-- Migración 0005 (delta sobre una tabla `subscriptions` ya desplegada) -- [spec 006], SIN CAMBIOS
-- ---------------------------------------------------------------------------------------------
-- CREATE TABLE subscription_types (id serial4 PRIMARY KEY, name varchar(50) NOT NULL UNIQUE, description text);
-- INSERT INTO subscription_types (id, name, description) VALUES
--     (1, 'Individual', 'Para médicos independientes; su consultorio se asocia a una sola clínica.'),
--     (2, 'Empresarial', 'Para empresas con varias clínicas y varios consultorios por clínica.');
-- SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2);
-- ALTER TABLE subscriptions ADD COLUMN subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types (id);

-- ---------------------------------------------------------------------------------------------
-- Migración 0006 (delta sobre una tabla `subscriptions` ya desplegada) -- [spec 007-add-clinics-limit]
-- Una sola sentencia agrega la columna con DEFAULT 1: PostgreSQL la asigna a cada fila existente
-- en la misma sentencia, válida tanto para una Individual (único valor permitido) como para una no
-- Individual (el más bajo de 1 a 100) -- research R5. No hace falta ningún paso fuera de Alembic
-- (a diferencia de 0005/FR-009, FR-010 de 006).
-- ---------------------------------------------------------------------------------------------
-- ALTER TABLE subscriptions ADD COLUMN clinics_limit int4 NOT NULL DEFAULT 1;
-- ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_clinics_limit_check CHECK (
--     (subscription_type_id = 1 AND clinics_limit = 1)
--     OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)
-- );

-- ---------------------------------------------------------------------------------------------
-- Reconciliación de tipos (FR-009, FR-010 de 006) -- SIN CAMBIOS; no es una migración de Alembic.
-- ---------------------------------------------------------------------------------------------
-- UPDATE subscriptions SET subscription_type_id = 2 WHERE id = ANY(:ids_con_mas_de_una_clinica);

-- Esquema de la feature 006-add-subscription-type (PostgreSQL 17), sobre lo que ya entregaron
-- las migraciones 0001 a 0004 (001-subscriptions-api, 004-correct-subscriptions-api y
-- 005-health-monitoring).
--
-- Revisión tras Clarifications (2026-10-26): el tipo es un catálogo propio (tabla
-- `subscription_types`), no una columna con CHECK fijo a dos valores. Reemplaza a la versión
-- anterior de este archivo.
--
-- Esta es la tabla `subscriptions` COMPLETA, más la tabla nueva `subscription_types`, tal como
-- deben quedar tras aplicar 0001 a 0005 (0005 introduce esta feature). `subscription_statuses` y
-- `monitored_components` no cambian: ver specs/001-subscriptions-api/contracts/database-schema.sql
-- y specs/005-health-monitoring/contracts/database-schema.sql.
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK NO se declaran con nombre:
-- PostgreSQL las crea solas con su nombre automático (<tabla>_pkey, <tabla>_<columna>_key,
-- <tabla>_<columna>_fkey, <tabla>_<columna>_check). Llevan nombre explícito solo el índice parcial
-- del nombre, la función y el disparador de updated_at (sin cambios respecto a 001).

-- ---------------------------------------------------------------------------------------------
-- Tipos de suscripción  -- [spec 006-add-subscription-type FR-001]
-- Catálogo administrado a mano, EXACTAMENTE la misma forma que subscription_statuses: id estable
-- (quien consume la API MUST basarse en él, no en name), name editable. Sin operación propia de
-- la API para administrarlo (ni alta, ni baja, ni edición): se amplía insertando una fila, no con
-- una migración que reescriba una restricción.
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
-- `features` se renombra a `other_features` (mismo contenido y regla, acotado a lo que no es módulo).
-- [spec 006-add-subscription-type FR-001 a FR-010]: `subscription_type_id` (a quién va dirigida la
-- suscripción), obligatorio, inmutable por la aplicación, referencia a subscription_types.
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
	status_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_statuses (id), -- [spec 001 FR-011] 1 = Activa
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
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
-- Migración 0005 (delta sobre una tabla `subscriptions` ya desplegada por 0001 y corregida por 0003)
-- [spec 006-add-subscription-type]
-- Orden obligatorio: crear el catálogo, sembrarlo, y SOLO ENTONCES agregar la columna que lo
-- referencia (si no, el DEFAULT 1 no tendría una fila 1 que referenciar). A diferencia de 0003,
-- esta ADD COLUMN sí asume que `subscriptions` puede tener filas: el DEFAULT hace que PostgreSQL
-- asigne 1 ('Individual') a cada fila existente en la misma sentencia (FR-001, FR-008).
-- ---------------------------------------------------------------------------------------------
-- CREATE TABLE subscription_types (id serial4 PRIMARY KEY, name varchar(50) NOT NULL UNIQUE, description text);
-- INSERT INTO subscription_types (id, name, description) VALUES
--     (1, 'Individual', 'Para médicos independientes; su consultorio se asocia a una sola clínica.'),
--     (2, 'Empresarial', 'Para empresas con varias clínicas y varios consultorios por clínica.');
-- SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2);
-- ALTER TABLE subscriptions ADD COLUMN subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types (id);

-- ---------------------------------------------------------------------------------------------
-- Reconciliación de tipos (FR-009, FR-010) -- [spec 006-add-subscription-type]
-- NO es una migración de Alembic (ver data-model.md "Reconciliación de tipos" y quickstart.md).
-- En términos de SQL, su efecto es equivalente a:
-- ---------------------------------------------------------------------------------------------
-- UPDATE subscriptions SET subscription_type_id = 2 WHERE id = ANY(:ids_con_mas_de_una_clinica);

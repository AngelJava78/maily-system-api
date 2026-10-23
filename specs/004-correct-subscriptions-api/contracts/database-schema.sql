-- Esquema de la feature 004-correct-subscriptions-api (PostgreSQL 17), sobre lo que ya entregaron
-- las migraciones 0001 y 0002 de 001-subscriptions-api.
--
-- Esta es la tabla `subscriptions` COMPLETA tal como debe quedar tras aplicar 0001, 0002 y 0003 (la
-- que introduce esta feature). `subscription_statuses` no cambia: ver
-- specs/001-subscriptions-api/contracts/database-schema.sql.
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK NO se declaran con nombre:
-- PostgreSQL las crea solas con su nombre automático (<tabla>_pkey, <tabla>_<columna>_key,
-- <tabla>_<columna>_fkey, <tabla>_<columna>_check). Llevan nombre explícito solo el índice parcial
-- del nombre, la función y el disparador de updated_at (sin cambios respecto a 001).

-- ---------------------------------------------------------------------------------------------
-- Suscripciones -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo, módulos (claves externas, no una tabla propia) y los cuatro límites de la clínica.
-- `features` se renombra a `other_features` (mismo contenido y regla, acotado a lo que no es módulo).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
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
-- Migración 0003 (delta sobre una tabla `subscriptions` ya desplegada por 0001)
-- [spec 004-correct-subscriptions-api]
-- Asume que la tabla no tiene filas (supuesto del spec: sin datos reales que migrar). Las columnas
-- sin DEFAULT fallarían con ALTER TABLE si existieran filas.
-- ---------------------------------------------------------------------------------------------
-- ALTER TABLE subscriptions RENAME COLUMN features TO other_features;
-- ALTER TABLE subscriptions RENAME CONSTRAINT subscriptions_features_check TO subscriptions_other_features_check;
-- ALTER TABLE subscriptions ADD COLUMN annual_price numeric(10,2) NOT NULL CHECK (annual_price >= 0);
-- ALTER TABLE subscriptions ADD COLUMN trial_days int4 NOT NULL DEFAULT 0 CHECK (trial_days BETWEEN 0 AND 3650);
-- ALTER TABLE subscriptions ADD COLUMN self_service bool NOT NULL DEFAULT false;
-- ALTER TABLE subscriptions ADD COLUMN module_keys text[] NOT NULL DEFAULT ARRAY['patients']::text[] CHECK ('patients' = ANY(module_keys));
-- ALTER TABLE subscriptions ADD COLUMN consulting_rooms_limit int4 NOT NULL CHECK (consulting_rooms_limit BETWEEN 0 AND 1000000);
-- ALTER TABLE subscriptions ADD COLUMN doctors_limit int4 NOT NULL CHECK (doctors_limit BETWEEN 0 AND 1000000);
-- ALTER TABLE subscriptions ADD COLUMN assistants_limit int4 NOT NULL CHECK (assistants_limit BETWEEN 0 AND 1000000);
-- ALTER TABLE subscriptions ADD COLUMN new_patients_per_year_limit int4 NOT NULL CHECK (new_patients_per_year_limit BETWEEN 0 AND 1000000);

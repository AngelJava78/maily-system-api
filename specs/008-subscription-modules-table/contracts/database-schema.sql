-- Esquema de la feature 008-subscription-modules-table (PostgreSQL 17), sobre lo que ya entregan
-- las migraciones 0001 a 0006 (001-subscriptions-api, 004-correct-subscriptions-api,
-- 005-health-monitoring, 006-add-subscription-type y 007-add-clinics-limit).
--
-- Esta es la tabla `subscriptions` COMPLETA (sin su columna `module_keys`, que esta feature quita)
-- más la tabla nueva `subscription_modules`, tal como deben quedar tras aplicar 0001 a 0007 (0007
-- introduce esta feature). `subscription_types`, `subscription_statuses` y `monitored_components`
-- no cambian: ver specs/001-subscriptions-api/contracts/database-schema.sql,
-- specs/006-add-subscription-type/contracts/database-schema.sql y
-- specs/005-health-monitoring/contracts/database-schema.sql.
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK de una sola columna NO se
-- declaran con nombre: PostgreSQL las crea solas con su nombre automático (<tabla>_pkey,
-- <tabla>_<columna>_key, <tabla>_<columna>_fkey, <tabla>_<columna>_check). La clave primaria
-- compuesta de `subscription_modules` también recibe el nombre automático y estable
-- (`subscription_modules_pkey`): no hace falta nombrarla a mano.

-- ---------------------------------------------------------------------------------------------
-- Suscripciones -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo y los cuatro límites de la clínica. [spec 006-add-subscription-type FR-001 a
-- FR-010]: `subscription_type_id`. [spec 007-add-clinics-limit FR-001 a FR-010]: `clinics_limit`.
-- [spec 008-subscription-modules-table FR-001]: ya NO lleva `module_keys` como columna propia; sus
-- módulos viven en `subscription_modules`, abajo.
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

-- [spec 001 FR-015] la fecha de última modificación cambia con cualquier UPDATE. Sin cambios: una
-- actualización que solo toca los módulos de la suscripción (subscription_modules, abajo) también
-- la dispara, porque el Repository siempre ejecuta un UPDATE sobre `subscriptions` en ese caso
-- (research R8 de esta feature).
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
-- Módulo incluido en una suscripción -- [spec 008-subscription-modules-table FR-001, FR-002]
-- Tabla nueva: una fila por cada módulo de clínica que incluye una suscripción. La clave del
-- módulo es propiedad de users-api (Principio IX); esta tabla no la copia, solo registra qué
-- claves eligió cada suscripción -- research R1.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscription_modules (
	subscription_id int4 NOT NULL REFERENCES subscriptions (id),
	module_key text NOT NULL,
	PRIMARY KEY (subscription_id, module_key) -- sin columna `id` propia (research R1); esta misma
	                                           -- clave impide un módulo repetido y, junto con la
	                                           -- FOREIGN KEY, una fila sin su suscripción (FR-002)
);

-- No hay ningún CHECK en subscription_modules que exija "patients siempre incluido": un CHECK de
-- PostgreSQL no puede ver otras filas de la misma tabla (research R2). Esa regla, igual que la
-- validación contra users-api y los prerrequisitos entre módulos, la sigue garantizando
-- exclusivamente SubscriptionService._resolve_modules, sin cambios de esta feature.

-- No hay ningún índice adicional sobre `module_key` por sí solo: ninguna consulta de esta
-- especificación lo necesita (research R9); la clave primaria ya basta para las consultas por
-- subscription_id que usan create/update/list/get.

-- ---------------------------------------------------------------------------------------------
-- Migración 0007 (delta sobre una tabla `subscriptions` ya desplegada) -- [spec 008], research R5
-- Los módulos ya guardados se migran con una sola sentencia SQL, sin ningún paso fuera de Alembic
-- (a diferencia de 006, que sí necesitó un script aparte porque dependía de la API de clínicas).
-- ---------------------------------------------------------------------------------------------
-- CREATE TABLE subscription_modules (
--     subscription_id int4 NOT NULL REFERENCES subscriptions (id),
--     module_key text NOT NULL,
--     PRIMARY KEY (subscription_id, module_key)
-- );
-- INSERT INTO subscription_modules (subscription_id, module_key)
--     SELECT id, unnest(module_keys) FROM subscriptions;
-- ALTER TABLE subscriptions DROP CONSTRAINT subscriptions_module_keys_check;
-- ALTER TABLE subscriptions DROP COLUMN module_keys;

-- ---------------------------------------------------------------------------------------------
-- downgrade() de 0007 (orden inverso) -- research R6
-- ---------------------------------------------------------------------------------------------
-- ALTER TABLE subscriptions ADD COLUMN module_keys text[] NOT NULL DEFAULT ARRAY['patients']::text[];
-- UPDATE subscriptions SET module_keys = (
--     SELECT COALESCE(array_agg(module_key ORDER BY module_key), ARRAY['patients']::text[])
--     FROM subscription_modules WHERE subscription_id = subscriptions.id
-- );
-- ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_module_keys_check CHECK ('patients' = ANY(module_keys));
-- DROP TABLE subscription_modules;

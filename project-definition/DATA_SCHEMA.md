# Esquema de datos objetivo (MailySoft System API)

Este es el **esquema objetivo** del proyecto (Principio VI de la constitución): reúne las estructuras
—tablas, restricciones, índices, funciones, disparadores y datos iniciales— que exigen las
especificaciones. Cada regla lleva el comentario `-- [spec NNN-nombre]` de la especificación que la
introduce. Hoy coincide con lo que entregan las migraciones `0001` y `0002` (esquema y datos
iniciales de `001-subscriptions-api`), `0003` (`004-correct-subscriptions-api`) y `0004`
(`005-health-monitoring`), y con `specs/004-correct-subscriptions-api/contracts/database-schema.sql` (el
esquema completo vigente de `subscriptions`; el de `001-subscriptions-api` quedó superado por esa
corrección) y `specs/005-health-monitoring/contracts/database-schema.sql` (`monitored_components`).

Debe mantenerse al día: toda especificación o plan que cambie una regla de datos debe reflejarla aquí.

## Nombres de restricciones de los que depende el código

Las claves primarias, únicas y foráneas y las restricciones `CHECK` **no** se declaran con nombre en el SQL:
PostgreSQL les pone el automático (`<tabla>_pkey`, `<tabla>_<columna>_key`, `<tabla>_<columna>_fkey`,
`<tabla>_<columna>_check`). El código y las pruebas dependen de estos:

| Nombre | Regla |
|---|---|
| `subscription_statuses_name_key` | Los nombres del catálogo de estatus son únicos |
| `subscriptions_name_check` | El nombre no puede estar en blanco |
| `subscriptions_monthly_price_check` | El precio mensual no puede ser negativo |
| `subscriptions_annual_price_check` | El precio anual no puede ser negativo -- [spec 004-correct-subscriptions-api] |
| `subscriptions_trial_days_check` | Los días de prueba van de 0 a 3650 -- [spec 004-correct-subscriptions-api] |
| `subscriptions_module_keys_check` | `module_keys` siempre contiene `patients` -- [spec 004-correct-subscriptions-api] |
| `subscriptions_other_features_check` | Lo que incluye una suscripción (otras funcionalidades) tiene como máximo 20 elementos -- [spec 004-correct-subscriptions-api] (reemplaza a `subscriptions_features_check` de 001: columna renombrada) |
| `subscriptions_consulting_rooms_limit_check`, `subscriptions_doctors_limit_check`, `subscriptions_assistants_limit_check`, `subscriptions_new_patients_per_year_limit_check` | Cada límite de la clínica va de 0 a 1 000 000 -- [spec 004-correct-subscriptions-api] |
| `subscriptions_status_id_fkey` | El estatus debe existir en el catálogo |
| `monitored_components_code_check` | El código tiene de 2 a 50 caracteres (minúsculas, dígitos y guiones; empieza con letra; sin guion final ni doble) y no es `maily-system-api` ni `database` -- [spec 005-health-monitoring] |
| `monitored_components_name_check` | El nombre no está en blanco ni tiene espacios en los extremos -- [spec 005-health-monitoring] |
| `monitored_components_kind_check` | El tipo es `service` o `frontend` -- [spec 005-health-monitoring] |
| `monitored_components_sort_order_check` | El orden va de 0 a 9999 -- [spec 005-health-monitoring] |
| `monitored_components_service_paths_check` | Un servicio tiene `ready_path` e `info_path` -- [spec 005-health-monitoring] |
| `monitored_components_frontend_ready_path_check` | Un frontend no tiene `ready_path` -- [spec 005-health-monitoring] |

Los índices con nombre explícito son `subscriptions_name_not_deleted_key` (el servicio lo usa para
traducir un nombre repetido a un 409) y `monitored_components_code_not_deleted_key` (traduce un código de
componente repetido a un 409) -- [spec 005-health-monitoring]; también llevan nombre explícito la función
`set_updated_at` y los disparadores `subscriptions_set_updated_at` y `monitored_components_set_updated_at`
(este último de `005-health-monitoring`, que reutiliza la función). Las restricciones de tabla de
`monitored_components` (`…_service_paths_check` y `…_frontend_ready_path_check`) se nombran a propósito,
porque PostgreSQL no da un nombre estable a una restricción de varias columnas.

## Esquema

```sql
-- Esquema vigente tras 001-subscriptions-api (migraciones 0001, 0002), su corrección
-- 004-correct-subscriptions-api (migración 0003) y 005-health-monitoring (migración 0004), PostgreSQL 17.
-- Es el contenido que entregan esas migraciones y el que se refleja en
-- project-definition/DATA_SCHEMA.md (esquema objetivo del proyecto). `subscriptions` se muestra ya
-- corregida (no el estado intermedio de solo 0001); el delta que aplica 0003 está documentado en
-- specs/004-correct-subscriptions-api/contracts/database-schema.sql.
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
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo, módulos (claves de un catálogo EXTERNO, propiedad de la API de usuarios: no hay
-- tabla de módulos en este esquema, Principio IX) y los cuatro límites de la clínica. `features`
-- se renombró a `other_features` (mismo contenido, acotado a lo que no es un módulo).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
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
	status_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_statuses (id), -- [spec 001 FR-011] 1 = Activa
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- [spec 001 FR-014] el nombre es único, sin distinguir mayúsculas, entre las suscripciones no
-- eliminadas (estatus distinto de 4 = Eliminada): el nombre de una Eliminada queda libre y el de
-- una Inactiva o Bloqueada sigue reservado. Sin cambios en 004.
CREATE UNIQUE INDEX subscriptions_name_not_deleted_key ON subscriptions (lower(name)) WHERE status_id <> 4;

-- [spec 001 FR-015] la fecha de última modificación cambia con cualquier UPDATE (también con el
-- cambio de estatus). Sin cambios en 004.
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

-- ---------------------------------------------------------------------------------------------
-- Registro de componentes monitoreados  -- [spec 005-health-monitoring FR-023 a FR-032]
-- Servicios y frontends cuya salud agrega GET /api/v1/health (migración 0004). Los dos componentes
-- integrados (maily-system-api y database) NO se guardan aquí: sus códigos están reservados. La baja
-- es lógica (deleted_at con fecha); la fila se conserva y su code queda libre. Empieza vacío: no hay
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

-- [spec 005 FR-028] updated_at cambia con cualquier UPDATE (reutiliza set_updated_at de 001).
CREATE TRIGGER monitored_components_set_updated_at
	BEFORE UPDATE ON monitored_components
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

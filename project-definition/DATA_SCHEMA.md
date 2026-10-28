# Esquema de datos objetivo (MailySoft System API)

Este es el **esquema objetivo** del proyecto (Principio VI de la constitución): reúne las estructuras
—tablas, restricciones, índices, funciones, disparadores y datos iniciales— que exigen las
especificaciones. Cada regla lleva el comentario `-- [spec NNN-nombre]` de la especificación que la
introduce. Hoy coincide con lo que entregan las migraciones `0001` y `0002` (esquema y datos
iniciales de `001-subscriptions-api`), `0003` (`004-correct-subscriptions-api`), `0004`
(`005-health-monitoring`), `0005` (`006-add-subscription-type`), `0006`
(`007-add-clinics-limit`) y `0007` (`008-subscription-modules-table`), y con
`specs/008-subscription-modules-table/contracts/database-schema.sql` (el esquema completo vigente
de `subscriptions`, ya sin `module_keys`, y de la tabla nueva `subscription_modules`; el de
`007-add-clinics-limit` quedó superado por esta feature solo en esos dos puntos) y
`specs/005-health-monitoring/contracts/database-schema.sql` (`monitored_components`).

La asignación del tipo a las suscripciones que ya existían (FR-009/FR-010 de `006-add-subscription-type`)
no es parte de este esquema: la ejecuta, una sola vez, `src/scripts/backfill_subscription_types.py`
(ver `specs/006-add-subscription-type/data-model.md`), porque depende de una llamada a la API de
clínicas que ninguna migración de este proyecto hace.

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
| `subscription_types_name_key` | Los nombres del catálogo de tipos son únicos -- [spec 006-add-subscription-type] |
| `subscriptions_subscription_type_id_fkey` | El tipo debe existir en el catálogo `subscription_types` -- [spec 006-add-subscription-type] |
| `subscriptions_annual_price_check` | El precio anual no puede ser negativo -- [spec 004-correct-subscriptions-api] |
| `subscriptions_trial_days_check` | Los días de prueba van de 0 a 3650 -- [spec 004-correct-subscriptions-api] |
| `subscriptions_other_features_check` | Lo que incluye una suscripción (otras funcionalidades) tiene como máximo 20 elementos -- [spec 004-correct-subscriptions-api] (reemplaza a `subscriptions_features_check` de 001: columna renombrada) |
| `subscriptions_consulting_rooms_limit_check`, `subscriptions_doctors_limit_check`, `subscriptions_assistants_limit_check`, `subscriptions_new_patients_per_year_limit_check` | Cada límite de la clínica va de 0 a 1 000 000 -- [spec 004-correct-subscriptions-api] |
| `subscriptions_clinics_limit_check` | El límite de clínicas es exactamente 1 si el tipo es Individual, o de 1 a 100 si no lo es (restricción de dos columnas, con nombre explícito porque PostgreSQL no le da uno estable) -- [spec 007-add-clinics-limit] |
| ~~`subscriptions_module_keys_check`~~ | Quitada por `008-subscription-modules-table`: los módulos ya no viven en una columna de `subscriptions`, sino en la tabla `subscription_modules` (abajo); esa regla («patients» siempre incluido) ya no es una restricción de base de datos, porque un `CHECK` no puede ver otras filas de la misma tabla -- [spec 008-subscription-modules-table, research R2] |
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
`monitored_components` (`…_service_paths_check` y `…_frontend_ready_path_check`) y de `subscriptions`
(`subscriptions_clinics_limit_check`, spec 007) se nombran a propósito, porque PostgreSQL no da un
nombre estable a una restricción de varias columnas.

## Esquema

```sql
-- Esquema vigente tras 001-subscriptions-api (migraciones 0001, 0002), su corrección
-- 004-correct-subscriptions-api (migración 0003), 005-health-monitoring (migración 0004),
-- 006-add-subscription-type (migración 0005), 007-add-clinics-limit (migración 0006) y
-- 008-subscription-modules-table (migración 0007), PostgreSQL 17. Es el contenido que entregan
-- esas migraciones y el que se refleja en project-definition/DATA_SCHEMA.md (esquema objetivo del
-- proyecto). `subscriptions` se muestra ya sin `module_keys` (movida a `subscription_modules`,
-- abajo) y con el tipo y el límite de clínicas; el delta que aplica 0007 está documentado en
-- specs/008-subscription-modules-table/contracts/database-schema.sql.
--
-- Las claves primarias, únicas y foráneas y las restricciones CHECK de una sola columna NO se
-- declaran con nombre: PostgreSQL las crea solas con su nombre automático (<tabla>_pkey,
-- <tabla>_<columna>_key, <tabla>_<columna>_fkey, <tabla>_<columna>_check) — incluida la clave
-- primaria compuesta de `subscription_modules` (`subscription_modules_pkey`), que no necesita
-- nombre explícito por ser estable. Llevan nombre explícito el CHECK de dos columnas de
-- `subscriptions` (`subscriptions_clinics_limit_check`), el índice parcial del nombre (la
-- aplicación lo usa para traducir un nombre repetido a un 409), la función y el disparador de
-- updated_at.

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
-- Catálogo administrado a mano, misma forma que subscription_statuses: id estable (quien consume
-- la API MUST basarse en él, no en name), name editable. Sin operación de la API para
-- administrarlo; se amplía insertando una fila, no con una migración que reescriba una restricción.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscription_types (
	id serial4 PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	description text
);

-- ---------------------------------------------------------------------------------------------
-- Suscripciones  -- [spec 001-subscriptions-api FR-008, FR-011 a FR-015]
-- [spec 004-correct-subscriptions-api FR-008, FR-011 a FR-024]: precio anual, días de prueba,
-- autoconsumo y los cuatro límites de la clínica. `features` se renombró a `other_features`
-- (mismo contenido, acotado a lo que no es un módulo).
-- [spec 006-add-subscription-type FR-001 a FR-010]: `subscription_type_id` (a quién va dirigida
-- la suscripción), obligatorio, inmutable por la aplicación, referencia al catálogo
-- subscription_types (igual patrón que status_id).
-- [spec 007-add-clinics-limit FR-001 a FR-007]: `clinics_limit`, el quinto límite de la clínica,
-- con su rango acotado por `subscription_type_id` (exactamente 1 si es Individual; 1 a 100 si no).
-- [spec 008-subscription-modules-table FR-001]: ya NO lleva `module_keys` (claves de un catálogo
-- EXTERNO, propiedad de la API de usuarios: no hay tabla de módulos en este esquema, Principio
-- IX); sus módulos viven ahora en `subscription_modules`, una fila por módulo (abajo).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscriptions (
	id serial4 PRIMARY KEY,
	name varchar(100) NOT NULL CHECK (btrim(name) <> ''),
	description varchar(500),
	subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types (id), -- [spec 006 FR-001, FR-002, FR-008] 1 = Individual; fija desde la creación (FR-004); el DEFAULT asigna 1 a toda fila existente al aplicar 0005
	monthly_price numeric(10,2) NOT NULL CHECK (monthly_price >= 0), -- [spec 001 FR-013] pesos mexicanos, sin IVA, nunca float
	annual_price numeric(10,2) NOT NULL CHECK (annual_price >= 0), -- [spec 004 FR-012] independiente de monthly_price
	trial_days int4 NOT NULL DEFAULT 0 CHECK (trial_days BETWEEN 0 AND 3650), -- [spec 004 FR-013] 0 = sin periodo de prueba
	self_service bool NOT NULL DEFAULT false, -- [spec 004 FR-014] autoconsumo en el portal de MailySoft
	other_features text[] NOT NULL DEFAULT '{}' CHECK (cardinality(other_features) <= 20), -- [spec 004 FR-024] lista ordenada de textos libres que no son módulos
	consulting_rooms_limit int4 NOT NULL CHECK (consulting_rooms_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021] techo informativo
	doctors_limit int4 NOT NULL CHECK (doctors_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	assistants_limit int4 NOT NULL CHECK (assistants_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	new_patients_per_year_limit int4 NOT NULL CHECK (new_patients_per_year_limit BETWEEN 0 AND 1000000), -- [spec 004 FR-021]
	clinics_limit int4 NOT NULL DEFAULT 1, -- [spec 007 FR-001, FR-007] quinto límite; el DEFAULT asigna 1 a toda fila existente al aplicar 0006 (válido para cualquier tipo); ver el CHECK de dos columnas, abajo
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
-- Módulo incluido en una suscripción  -- [spec 008-subscription-modules-table FR-001, FR-002]
-- Una fila por cada módulo de clínica que incluye una suscripción. `module_key` es la clave de un
-- catálogo EXTERNO, propiedad de la API de usuarios (Principio IX): esta tabla no lo copia, solo
-- registra qué claves eligió cada suscripción (antes, en la columna `module_keys` que esta
-- migración quita de `subscriptions`). Sin columna `id` propia: la clave primaria compuesta ya
-- impide un módulo repetido para la misma suscripción, y la FOREIGN KEY impide una fila sin su
-- suscripción. Sin CHECK de "patients siempre incluido": un CHECK no ve otras filas de la misma
-- tabla; esa regla sigue siendo responsabilidad exclusiva del servicio, no de la base de datos.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE subscription_modules (
	subscription_id int4 NOT NULL REFERENCES subscriptions (id),
	module_key text NOT NULL,
	PRIMARY KEY (subscription_id, module_key)
);

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
-- Datos iniciales: los dos tipos de hoy (migración 0005)  -- [spec 006-add-subscription-type FR-001]
-- Constantes SubscriptionType.INDIVIDUAL=1 / .ENTERPRISE=2 (research R8, data-model.md). Un
-- tercer tipo se agregaría aquí, a mano, sin tocar esta tabla ni ningún CHECK.
-- ---------------------------------------------------------------------------------------------
INSERT INTO subscription_types (id, name, description) VALUES
	(1, 'Individual',  'Para médicos independientes; su consultorio se asocia a una sola clínica.'),
	(2, 'Empresarial', 'Para empresas con varias clínicas y varios consultorios por clínica.');

-- Los tipos añadidos a mano empiezan en 3.
SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2);

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

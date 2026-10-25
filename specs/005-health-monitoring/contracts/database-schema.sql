-- Esquema de la feature 005-health-monitoring (PostgreSQL 17), sobre lo que ya entregaron las
-- migraciones 0001 a 0003 (subscription_statuses y subscriptions, que NO cambian).
--
-- Es lo que crea la migración 0004 (`alembic/versions/0004_monitored_components.py`, revisa 0003) y lo
-- que se añade a project-definition/DATA_SCHEMA.md con el comentario -- [spec 005-health-monitoring].
-- El registro empieza VACÍO: no hay datos iniciales (FR-031).
--
-- Las restricciones de una sola columna NO se declaran con nombre: PostgreSQL les pone el automático
-- (<tabla>_pkey, <tabla>_<columna>_check). Llevan nombre explícito las dos restricciones de tabla, el
-- índice único parcial del código (la aplicación lo usa para traducir un código repetido a un 409) y el
-- disparador de updated_at. La función set_updated_at() es la de la migración 0001: se reutiliza y el
-- downgrade de 0004 NO la borra.

-- ---------------------------------------------------------------------------------------------
-- Registro de componentes monitoreados  -- [spec 005-health-monitoring FR-023 a FR-032]
-- Servicios y frontends cuya salud agrega GET /api/v1/health. Los dos componentes integrados
-- (maily-system-api y database) NO se guardan aquí: sus códigos están reservados.
-- La baja es lógica: deleted_at con fecha; la fila se conserva y su code queda libre.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE monitored_components (
	id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	code varchar(50) NOT NULL CHECK (
		char_length(code) BETWEEN 2 AND 50
		AND code ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'
		AND code NOT IN ('maily-system-api', 'database')
	), -- [spec 005 FR-024] minúsculas, dígitos y guiones; empieza con letra; sin guion final ni doble
	name varchar(100) NOT NULL CHECK (btrim(name) <> '' AND name = btrim(name)), -- [spec 005 FR-024] sin espacios en los extremos
	kind varchar(20) NOT NULL CHECK (kind IN ('service', 'frontend')), -- [spec 005 FR-024] la base de datos solo es integrada
	base_url varchar(255) NOT NULL, -- [spec 005 FR-025] http(s), sin credenciales, query ni fragmento; esquema y host en minúsculas, sin barra final (lo valida el servicio)
	live_path varchar(200) NOT NULL, -- [spec 005 FR-026] servicio: /health/live por defecto; frontend: su ruta de salud
	ready_path varchar(200), -- [spec 005 FR-026] servicio: /health/ready por defecto; frontend: siempre NULL
	info_path varchar(200), -- [spec 005 FR-026] servicio: /info por defecto; frontend: opcional
	enabled bool NOT NULL DEFAULT true, -- [spec 005 FR-024] deshabilitado = no se consulta ni sale en la salud
	sort_order int4 NOT NULL DEFAULT 0 CHECK (sort_order BETWEEN 0 AND 9999), -- [spec 005 FR-024]
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	deleted_at timestamptz, -- [spec 005 FR-029] marca de baja lógica con su fecha; NULL = vigente; no se publica
	CONSTRAINT monitored_components_service_paths_check
		CHECK (kind <> 'service' OR (ready_path IS NOT NULL AND info_path IS NOT NULL)),
	CONSTRAINT monitored_components_frontend_ready_path_check
		CHECK (kind <> 'frontend' OR ready_path IS NULL)
);

-- [spec 005 FR-024, FR-028, FR-029] el código es único entre los componentes no eliminados: el de uno
-- eliminado queda libre (registrarlo de nuevo crea otra fila, con otro id). Decide también las altas
-- y modificaciones simultáneas: solo una tiene éxito y la otra recibe 409.
CREATE UNIQUE INDEX monitored_components_code_not_deleted_key
	ON monitored_components (code) WHERE deleted_at IS NULL;

-- [spec 005 FR-028] updated_at cambia con cualquier UPDATE (también con la baja lógica).
CREATE TRIGGER monitored_components_set_updated_at
	BEFORE UPDATE ON monitored_components
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Consultas que hace el servicio (referencia; no son parte del esquema):
--   listado (FR-023):     ... WHERE deleted_at IS NULL ORDER BY sort_order, code COLLATE "C"
--   agregación (FR-011):  ... WHERE deleted_at IS NULL AND enabled ORDER BY sort_order, code COLLATE "C"
--   baja (FR-029):        UPDATE ... SET deleted_at = CURRENT_TIMESTAMP
--                         WHERE id = $1 AND deleted_at IS NULL RETURNING id
--   modificación (FR-028): SELECT ... WHERE id = $1 AND deleted_at IS NULL FOR UPDATE; luego UPDATE ... RETURNING
-- COLLATE "C" hace que el orden sea el de los puntos de código, el mismo que usa la agregación en Python
-- (con en_US.UTF-8 el guion se ignora en la primera pasada y 'a-c' y 'ab' podrían ordenarse distinto).

-- Downgrade de 0004 (reversible, Principio VI):
--   DROP TRIGGER monitored_components_set_updated_at ON monitored_components;
--   DROP INDEX monitored_components_code_not_deleted_key;
--   DROP TABLE monitored_components;

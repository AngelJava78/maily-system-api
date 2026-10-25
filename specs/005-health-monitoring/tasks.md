---

description: "Task list for feature 005-health-monitoring (Monitoreo de salud de los servicios de Maily)"
---

# Tasks: Monitoreo de salud de los servicios de Maily

**Input**: Design documents from `/specs/005-health-monitoring/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.0.0** sin enmiendas (los puntos C1, C2 y C3 del Complexity Tracking del plan y la validación
de `DATABASE_URL` al arrancar quedaron aprobados el 2026-10-24), las features 001 a 004 implementadas (con
sus pruebas y simulaciones), Docker Desktop con Compose 2.24 o superior, `uv` con Python 3.14 o superior y,
solo para la colección de punta a punta, Node.js con npm.

**Tests**: Incluidas. La spec las exige (FR-039, FR-041, FR-042, FR-049) y el Principio V también. TDD dentro de
cada historia: las tareas de pruebas se escriben primero y **deben fallar** antes de implementar (fallar al
importar código que aún no existe cuenta). **Ninguna prueba llama a un servicio real**: el API de usuarios es
`tests/stubs/users_api`; los componentes, `tests/stubs/components` montado en memoria con
`httpx.ASGITransport` y un transporte de pruebas que produce fallas de DNS y de conexión.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md), en orden de prioridad: US1 y
US2 (P1), US3, US4 y US6 (P2) y US5 (P3). El **MVP** es Setup + Foundational + US1 + US2: la consulta de salud
protegida con los dos componentes integrados y los registrados (insertados en la base) y el contrato de salud
v1 propio.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US6); sin etiqueta en Setup, Foundational y Polish
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones y evidencia: [research.md](research.md) (R1 a R24)
- Tabla, DTOs, registros internos, estado en memoria y configuración: [data-model.md](data-model.md)
- Contrato HTTP de las diez operaciones (OpenAPI 3.1): [contracts/openapi-health.yaml](contracts/openapi-health.yaml)
- Contrato de salud v1 (implementado y consumido): [contracts/health-contract-v1.md](contracts/health-contract-v1.md)
- Operación → permiso y rutas públicas: [contracts/permission-matrix.md](contracts/permission-matrix.md)
- Códigos y mensajes exactos, precedencia y códigos de componente: [contracts/error-catalog.md](contracts/error-catalog.md)
- DDL de la migración 0004: [contracts/database-schema.sql](contracts/database-schema.sql)
- Colección de Postman, simulación de componentes y pruebas guardianas: [contracts/e2e-collection.md](contracts/e2e-collection.md)
- Ajustes a pruebas existentes (A1 a A10): sección «Ajustes a las pruebas existentes» de [plan.md](plan.md)
- Guía de validación: [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json` (debe seguir en
  `specs\005-health-monitoring`) y `.specify/memory/constitution.md`; escribir tokens, contraseñas o secretos
  reales en cualquier archivo; añadir dependencias distintas de `tzdata` (T002); trabajos en segundo plano,
  APScheduler o reintentos automáticos (FR-019, FR-043).
- **No se toca** (FR-040): el comportamiento, los DTOs y los contratos de suscripciones y del dashboard, las
  tres colecciones de Postman existentes, `tests/stubs/users_api` ni `tests/stubs/clinics_api`. **Las únicas
  pruebas existentes que se editan son las de los ajustes del plan**: A1 (T034, T047, T063, T088), A2 y A3
  (T048, T059), A4 y A5 (T059), A6 (T104) y A7 (T027), y solo de la forma que describe cada tarea. Si otra
  prueba existente falla, **no se arregla editándola**: se corrige el código nuevo y, si el choque es real, se
  avisa a la persona.
- **G9 en rojo de forma temporal y esperada**: desde T042 (US1 publica `get_health`) hasta T102 y T104, las
  pruebas `test_g9_the_three_collections_together_cover_exactly_the_operations_of_the_api` y
  `test_g9_detects_an_operation_that_no_collection_covers` de
  `tests/contract/test_dashboard_postman_collection.py` fallan porque las operaciones nuevas aún no tienen
  colección. Los checkpoints de las historias no ejecutan ese archivo; no se edita antes de T104.
- **Idioma** (Principio VII): identificadores, campos de la API y códigos en inglés; mensajes, descripciones de
  OpenAPI y documentos en español; comentarios y docstrings en inglés; los registros (logs) del servicio en
  inglés y **nunca** con direcciones, tokens, cabeceras, cuerpos ni el texto de una excepción.
- **Mensajes exactos**: los textos salen de [contracts/error-catalog.md](contracts/error-catalog.md); no se
  parafrasean (en Python, la `\` del mensaje de rutas se escribe `\\`).
- **Pruebas con base de datos**: `docker compose up -d db` y `uv run pytest [ruta]` (la base es
  `TEST_DATABASE_URL` y su nombre termina en `_test`). Las pruebas unitarias marcadas así no la necesitan.
- **Todo lo que hace I/O es `async`** (Principio III), incluidos los proveedores de `src/dependencies.py`. La
  única E/S síncrona permitida es la lectura de la zona horaria al validar la configuración al arrancar (R12).
- **Capas** (Principio I): los Routers no importan integraciones, repositorios, base de datos ni modelos; los
  Services no importan `fastapi` ni `sqlalchemy`; las integraciones no importan `fastapi`, `sqlalchemy`,
  `src.dtos` ni `src.models`. `tests/unit/test_layering.py` debe seguir en verde en cada fase sin editarse.
- **Constantes** (se definen una sola vez, con nombre, en el módulo que se indica):

  | Constante | Valor | Módulo |
  |---|---|---|
  | `VERSION` | `"2.0.0"` (fuente única de la versión) | `src/__init__.py` |
  | `HEALTH_READ`, `HEALTH_WRITE`, `HEALTH_UPDATE`, `HEALTH_DELETE` | `"health:read"`, `"health:write"`, `"health:update"`, `"health:delete"` | `src/security.py` |
  | `HEALTH_PATH` | `"/api/v1/health"` | `src/routers/health.py` |
  | `MONITORED_COMPONENTS_PATH` | `"/api/v1/monitored-components"` | `src/routers/monitored_components.py` |
  | `HEALTH_TAG` | `"Salud"` (etiqueta OpenAPI de las diez operaciones) | `src/routers/health.py` (lo importa el otro Router) |
  | `SERVICE_NAME` | `"maily-system-api"` (campo `service` de `/info`) | `src/config.py` |
  | `SELF_CODE`, `SELF_NAME` | `"maily-system-api"`, `"MailySoft System API"` | `src/services/health_service.py` |
  | `DATABASE_CODE`, `DATABASE_NAME` | `"database"`, `"Base de datos"` | `src/services/health_service.py` |
  | `RESERVED_CODES` | `frozenset({SELF_CODE, DATABASE_CODE})` | `src/services/health_service.py` |
  | `PUBLIC_MIN_CACHE_SECONDS` | `15` | `src/services/health_service.py` |
  | `UNKNOWN` | `"unknown"` | `src/integrations/health_contract.py` |
  | `MAX_TEXT_LENGTH`, `MAX_CHECKS` | `64`, `20` | `src/integrations/health_contract.py` |
  | `CHECK_ERROR_CODES` | `frozenset({"timeout", "connection_error", "not_configured", "unexpected_error"})` | `src/integrations/health_contract.py` |
  | `MAX_RESPONSE_BYTES` | `65_536` | `src/integrations/health_probe.py` |
  | `PROBE_MAX_CONNECTIONS` | `200` (con `max_keepalive_connections=0`) | `src/integrations/health_probe.py` |
  | `MONITORED_COMPONENT_CODE_INDEX` | `"monitored_components_code_not_deleted_key"` | `src/models/monitored_component.py` |
  | `SERVICE_DEFAULT_PATHS` | `{"live_path": "/health/live", "ready_path": "/health/ready", "info_path": "/info"}` | `src/services/monitored_component_service.py` |
  | Valores por defecto de la configuración | `HEALTH_CHECK_TIMEOUT_SECONDS` 3 (1–10), `HEALTH_CACHE_SECONDS` 15 (0–300), `HEALTH_READY_TIMEOUT_SECONDS` 2 (1–10) | `src/config.py` |
  | *User-Agent* de los chequeos | `f"maily-system-api-health/{VERSION}"` | `src/main.py` (lo pasa a la fábrica del cliente) |
  | Registro de cambio de estado | `"Health of component %s changed to %s (%s)"` con `code`, estado y código de error (o `"none"`); `WARNING` | `src/services/health_service.py` |
  | Registro de cambio de disponibilidad | `"Database readiness changed to %s (%s)"` con `ok`/`error` y código (o `"none"`); `WARNING` | `src/services/health_service.py` |
  | Registro de falla del agregador | `"Health check of component %s failed unexpectedly (%s)"` con `code` y `type(error).__name__`; `ERROR`, sin `exc_info` | `src/services/health_service.py` |
  | Registro de registro no legible | `"Registry of monitored components unavailable (%s)"` con el tipo de falla; `WARNING` | `src/services/health_service.py` |

- **Interfaces compartidas entre tareas** (usar exactamente estos nombres):
  - `src/config.py`: `valid_host(text: str) -> str | None` (host normalizado en minúsculas, o `None`);
    `AllowedHosts` (dataclass congelada: `exact: frozenset[str]`, `suffixes: tuple[str, ...]`; `parse(text)`
    clase-método que lanza `ValueError`; `allows(host) -> bool`; `is_empty`); `DatabaseSchedule` (dataclass
    congelada: `zone: ZoneInfo`, `days: frozenset[int]` con 0 = lunes, `start: time`, `end: time`);
    `HealthConfig` (dataclass congelada: `check_timeout_seconds: float`, `ready_timeout_seconds: float`,
    `cache_seconds: float`, `allowed_hosts: AllowedHosts`, `schedule: DatabaseSchedule | None = None`);
    `HealthSettings`, `BuildSettings`, `BuildInfo` (dataclass congelada: `service`, `version`, `commit`,
    `build_date`, `environment`, todos `str`); `health_config_from(settings) -> HealthConfig`;
    `build_info_from(settings) -> BuildInfo`; `get_health_settings()` y `get_build_settings()` con
    `lru_cache`; en US4, `InvalidSettingsError(variables: tuple[str, ...])` y
    `database_schedule_from(settings) -> DatabaseSchedule | None`.
  - `src/services/clock.py`: `Clock` (Protocol: `now() -> datetime` aware en UTC, `monotonic() -> float`) y
    `SystemClock`.
  - `src/services/health_state.py`: `HealthState` (`generation`, `last`, `in_flight`, `registry_snapshot`,
    `readiness_task`, `last_statuses`, `invalidate()`), `CachedResult(result, completed_at, generation)`,
    `InFlight(generation, task)`.
  - `src/repositories/errors.py`: `DatabaseUnavailableError(kind: str)` con `kind` `"connection_error"` o
    `"unexpected_error"`.
  - `src/repositories/database_health_repository.py`: `DatabaseHealthRepository(session)` con `async ping()`.
  - `src/repositories/monitored_component_repository.py`: `MonitoredComponentRepository(session)` con
    `list_enabled()` (Foundational) y `list_current()`, `get_current(id)`, `create(values)`,
    `lock_current(id)`, `update(id, changes)`, `soft_delete(id)`, `rollback()` (US3).
  - `src/models/monitored_component.py`: `MonitoredComponent` y `MONITORED_COMPONENT_CODE_INDEX`.
  - `src/integrations/health_probe.py`: `create_health_http_client(*, timeout_seconds, user_agent,
    transport=None) -> httpx.AsyncClient` (Foundational); `ProbeResponse(status_code, body, failure,
    latency_ms)` y `HealthProbeClient(http_client, timeout_seconds)` con `async get_json(url)` y
    `async get_status(url)` (US1).
  - `src/integrations/health_contract.py`: `CheckResult(name, status, latency_ms, error)`,
    `BuildData(version, commit, build_date, environment)`, `CallOutcome(ok, error, checks, latency_ms)`,
    `parse_live`, `parse_ready`, `parse_frontend`, `parse_info`, `clean_text`, `clean_build_date`,
    `clean_checks`.
  - `src/services/health_service.py`: `ComponentTarget`, `ComponentHealth`, `HealthResult`,
    `ReadinessResult(ok: bool, check: CheckResult)`, `global_status(components) -> str` y
    `HealthService(*, state, config, build, clock, probe, read_registry, ping_database)` con
    `async health()`, `async readiness()`, `info()` y `async public_status()`.
  - `src/services/health_schedule.py`: `in_window(schedule, instant) -> bool` y
    `next_start(schedule, instant) -> datetime`.
  - `src/services/monitored_component_service.py`: `MonitoredComponentService(repository, state, config)` con
    `list()`, `get(id)`, `create(data)`, `update(id, data)`, `delete(id)`; `apply_kind_rules(values, sent)`.
  - `src/dependencies.py`: `get_health_config`, `get_build_info`, `get_clock`, `get_health_state`,
    `get_health_http_client`, `read_enabled_components`, `ping_database`, `get_registry_reader`,
    `get_database_pinger` (Foundational); `get_health_probe`, `get_health_service` (US1);
    `get_monitored_component_repository`, `get_monitored_component_service` (US3).
  - `tests/health_support.py`: `FakeClock`, `FaultTransport`, `HealthConfigHolder`, `TEST_NOW`,
    `TEST_ALLOWED_HOSTS`, `TEST_HEALTH_CONFIG`, `stub_url(prefix)`, `insert_component(engine, **values)`,
    `install_health_overrides(...)`, `HealthApi` (Foundational); `FakeProbe`, `make_component(...)` (US1).
  - `tests/conftest.py`: las fixtures `components_stub_app`, `components_stub` y `health_api` (nuevas) y la
    fixture `api` ampliada (A7).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Comprobar el punto de partida y preparar la única dependencia nueva y la versión del proyecto.

- [X] T001 Verificar prerrequisitos y fijar la línea base (no modifica archivos): confirmar que
  `.specify/memory/constitution.md` termina en `**Version**: 1.0.0`; que `.specify/feature.json` apunta a
  `specs\005-health-monitoring`; que `uv --version` y `docker --version` responden; levantar la base con
  `docker compose up -d db` y ejecutar `uv run pytest`. **Debe terminar en verde**: anotar cuántas pruebas
  pasan (al final deben pasar todas esas más las nuevas). Si hay fallos previos, **detenerse** y avisar.
  `git status --short` solo debe mostrar `specs/005-health-monitoring/`.
- [X] T002 Añadir `tzdata` como dependencia del servicio (decisión C2 aprobada, [R13](research.md#r13-zoneinfo-y-tzdata-en-la-tabla-de-stack)):
  `uv add tzdata` (actualiza `dependencies` de `pyproject.toml` y `uv.lock`; sin marcador de plataforma).
  Comprobar con `uv run python -c "import zoneinfo; print(zoneinfo.ZoneInfo('America/Mexico_City'), zoneinfo.ZoneInfo('America/Tijuana'))"`
  (sin `tzdata` lanzaría `ZoneInfoNotFoundError` en Windows). Ningún módulo de `src/` importa `tzdata`.
- [X] T003 Alinear la versión del proyecto ([R1](research.md#r1-versión-de-una-sola-fuente-fr-007-sc-008)): en
  `pyproject.toml` cambiar `version = "0.1.0"` por `version = "2.0.0"` y ejecutar `uv lock` para que el paquete
  raíz `mailysoft-system-api` de `uv.lock` quede en `2.0.0`. No cambiar nada más (`[tool.uv] package = false`
  se queda).
- [X] T004 [P] Confirmar que la simulación del API de usuarios (`tests/stubs/users_api/app.py`) ya acepta los
  permisos nuevos (no modifica archivos): `uv run python -c "from tests.stubs.users_api.app import PERMISSION_PATTERN as p; assert all(p.match(x) for x in ('health:read','health:write','health:update','health:delete'))"`
  debe terminar sin error. Así `tests/stubs/users_api` no necesita cambios.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuración, versión, permisos, estado del proceso, cliente HTTP de chequeos, tabla del
registro, consulta trivial a la base e infraestructura de pruebas que usan **todas** las historias.

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase.

### Tests for Foundational (escribirlas primero; deben fallar) ⚠️

- [X] T005 [P] `tests/unit/test_allowed_hosts.py` (sin base de datos): (a) `valid_host`: acepta y normaliza a
  minúsculas `mailysoft-usuarios`, `Maily360-Production.up.railway.app`, `a.b.c`, `10.0.0.5`, `127.0.0.1`,
  `::1`; rechaza (`None`) `""`, `-a`, `a-`, `a..b`, `a.`, etiqueta de 64 caracteres, nombre de 254, `a_b`,
  `ñandu.mx` (no ASCII), `2130706433` y `0x7f.1` (última etiqueta solo dígitos que no es IP), `1.2.3`; (b)
  `AllowedHosts.parse`: `"mailysoft-usuarios, .Maily.Internal"` → `exact={"mailysoft-usuarios"}`,
  `suffixes=(".maily.internal",)`; `""` y `"   "` → vacía (`is_empty`); duplicados se aceptan; **lanzan
  `ValueError`** `"a,,b"`, `"a,"`, `"."`, `"*.maily.internal"`, `"*"`, `"http://a"`, `"a/b"`, `"a:8000"`,
  `"[::1]"`, `".-x"` y `"a b"`; el texto del error no contiene la entrada recibida; (c) `allows`: con
  `".maily.internal"` admite `a.maily.internal` y `x.y.maily.internal`, **no** `maily.internal` ni
  `otromaily.internal`; con la exacta `mailysoft-usuarios` admite `MAILYSOFT-USUARIOS` (sin distinguir
  mayúsculas) y no `mailysoft-usuarios.x`; una IP exacta solo se admite a sí misma; vacía no admite ninguno.
- [X] T006 [P] `tests/unit/test_health_settings.py` (sin base de datos), con una fixture `autouse` que borre del
  entorno `HEALTH_CHECK_TIMEOUT_SECONDS`, `HEALTH_CACHE_SECONDS`, `HEALTH_READY_TIMEOUT_SECONDS`,
  `HEALTH_ALLOWED_HOSTS`, `APP_COMMIT_SHA`, `APP_BUILD_DATE` y `APP_ENVIRONMENT` y construya con
  `_env_file=None`: (a) sin variables: 3, 15, 2 y lista vacía; (b) vacías (`""`) equivalen a no configuradas;
  (c) válidos `"1"` y `"10"` (timeouts), `"0"` y `"300"` (caché), `" 5 "`; **inválidos** (parametrizados)
  `"0"`, `"11"`, `"3.5"`, `"+3"`, `"03"`, `"-1"`, `"abc"`, `"1e1"`, `" "` en los timeouts y `"301"`, `"-1"` en
  la caché: `ValidationError` cuyo único error tiene `loc` del campo; (d) `HEALTH_ALLOWED_HOSTS` inválida →
  `ValidationError` en `health_allowed_hosts`; (e) `BuildSettings`: `APP_COMMIT_SHA` de 7 y de 64
  hexadecimales (mayúsculas → se guarda en minúsculas), inválidos `"abc12"` (5), 65 caracteres, `"xyz1234"`;
  `APP_BUILD_DATE` `"2026-10-24T16:05:00Z"` y `"2026-10-24T10:05:00-06:00"` → `"2026-10-24T16:05:00Z"`,
  inválidos `"ayer"`, `"2026-10-24T16:05:00"` (sin zona), `"1700000000"`; `APP_ENVIRONMENT` `"staging"`,
  `"prod-1.mx_a"`, inválidos `"con espacio"`, 51 caracteres, `"ñ"`; (f) `build_info_from` sin variables →
  `BuildInfo("maily-system-api", "2.0.0", "unknown", "unknown", "unknown")` y la versión es `src.VERSION`;
  (g) `health_config_from` convierte los enteros a `float` y entrega `AllowedHosts`; `schedule` es `None`;
  (h) `configuration_error_message(error)` de un valor inválido con un texto reconocible
  (`"valor-secreto-9"`) nombra la variable (`HEALTH_CACHE_SECONDS`) y **no** contiene el texto.
- [X] T007 [P] `tests/unit/test_health_startup.py` (sin base de datos; mismo patrón de aislamiento que
  `tests/unit/test_dashboard_startup.py`: limpiar las cachés de `get_settings`, `get_integration_settings`,
  `get_cors_settings`, `get_dashboard_settings`, `get_health_settings` y `get_build_settings`, `env_file=None`
  en sus clases, definir `USERS_API_BASE_URL` y `CLINICS_API_BASE_URL`): (a) `create_app()` sin ninguna
  variable funciona y `app.state.health` es un `HealthState`; (b) con la configuración por defecto el
  `lifespan` arranca, deja `app.state.health_http_client` abierto y lo cierra al salir (y sigue cerrando
  `app.state.http_client`); (c) parametrizada con cada valor inválido de T006 (al menos uno por variable) el
  arranque lanza `RuntimeError` cuyo mensaje nombra la variable y **no** contiene el valor (y lo registra con
  `logger.error`); (d) dos variables inválidas a la vez → un solo mensaje que nombra ambas; (e) sin
  `DATABASE_URL` (quitarla con `monkeypatch.delenv` y `get_settings.cache_clear()`, restaurar al final) el
  arranque falla con `"Falta la variable de entorno DATABASE_URL."` (decisión aprobada, R16).
- [X] T008 [P] `tests/unit/test_health_http_client.py` (sin base de datos; usar `httpx.MockTransport` como
  `transport=`): el cliente que devuelve `create_health_http_client(timeout_seconds=0.5, user_agent="agente-prueba", transport=...)`
  (a) no sigue redirecciones (un 307 se devuelve tal cual y el destino no se pide); (b) tiene
  `trust_env=False`; (c) rechaza cookies: una respuesta con `Set-Cookie` no hace que la siguiente petición
  lleve `Cookie`; (d) envía `User-Agent: agente-prueba` y `Accept-Encoding: identity`; (e) no envía
  `Authorization` ni cabeceras extra; (f) su `timeout` es `httpx.Timeout(0.5)`; (g) sus límites tienen
  `max_connections == 200` y `max_keepalive_connections == 0`.
- [X] T009 [P] `tests/integration/test_monitored_components_migration.py` (contra PostgreSQL 17, fixtures
  `migrator`, `engine` y una `restore_head` como la de `test_migrations.py`): (a) `upgrade head` crea la tabla
  `monitored_components`, el índice `monitored_components_code_not_deleted_key` (único y parcial) y el
  disparador `monitored_components_set_updated_at`; existen las restricciones
  `monitored_components_code_check`, `_name_check`, `_kind_check`, `_sort_order_check`,
  `_service_paths_check` y `_frontend_ready_path_check` (consultar `pg_constraint`); (b) `downgrade 0003`
  borra la tabla, el índice y el disparador pero **conserva** la función `set_updated_at()` y las tablas de
  suscripciones; (c) subir y bajar es repetible; (d) `id` toma `gen_random_uuid()` por defecto.

### Implementation for Foundational

- [X] T010 `src/config.py` (aditivo; cumple T005 y T006, [data-model.md](data-model.md) sección 7):
  `SERVICE_NAME = "maily-system-api"`; `valid_host(text)` con las reglas de [R14](research.md#r14-ssrf-y-lista-permitida-fr-025-fr-026-fr-027-sc-004)
  (IP literal con `ipaddress.ip_address`, sin corchetes; si no, etiquetas `[a-z0-9-]` de 1 a 63 caracteres
  que no empiezan ni terminan con guion, hasta 253 en total, sin punto final, y si la última etiqueta es solo
  dígitos tiene que ser una IP válida); `AllowedHosts` (entradas separadas por comas, `strip`, minúsculas; con
  punto inicial es sufijo y el resto debe ser un host válido; sin él, `valid_host`; una entrada vacía, `.`,
  `*`, `://`, `/` o un `:` que no forme una IPv6 válida → `ValueError("Invalid allowed host entry")` sin la
  entrada; todo el texto vacío o solo espacios → lista vacía); `DatabaseSchedule` (solo el objeto de valor;
  su lectura llega en US4); `HealthConfig`; `class HealthSettings(BaseSettings)` con
  `health_check_timeout_seconds: int = 3`, `health_cache_seconds: int = 15`,
  `health_ready_timeout_seconds: int = 2` (validadores `mode="before"` que, tras `str(value).strip()`, exigen
  solo dígitos ASCII y el rango —1 a 10, 0 a 300, 1 a 10— y lanzan `ValueError` sin el valor) y
  `health_allowed_hosts: str = ""` (validador que llama a `AllowedHosts.parse` para fallar al arrancar y
  propiedad `allowed_hosts`); `class BuildSettings(BaseSettings)` con `app_commit_sha`, `app_build_date` y
  `app_environment` (`str | None = None`; validadores: `^[0-9A-Fa-f]{7,64}$` → minúsculas;
  `datetime.fromisoformat` con `tzinfo` obligatorio → `astimezone(UTC)` publicado como
  `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`; `^[A-Za-z0-9._-]{1,50}$`); las dos clases con
  `SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)`; `BuildInfo`;
  `health_config_from(settings)` y `build_info_from(settings)` (lee `src.VERSION`; lo ausente es `"unknown"`);
  `@lru_cache get_health_settings()` y `get_build_settings()`. Actualizar el docstring del módulo.
- [X] T011 [P] `src/__init__.py`: `VERSION = "2.0.0"` con el comentario `# The only source of the version: the OpenAPI document, /info and pyproject.toml must match it (FR-007).`;
  en `src/main.py`, quitar la constante `VERSION` y usar `from src import VERSION` en `create_app()`.
- [X] T012 [P] `src/security.py`: añadir `HEALTH_READ`, `HEALTH_WRITE`, `HEALTH_UPDATE` y `HEALTH_DELETE`
  debajo de `DASHBOARD_READ`, con el comentario
  `# Permissions of the health operations (specs/005-health-monitoring/contracts/permission-matrix.md).` No tocar nada más.
- [X] T013 [P] `src/services/clock.py`: `class Clock(Protocol)` con `now() -> datetime` (aware, UTC) y
  `monotonic() -> float`, y `class SystemClock` (`datetime.now(UTC)` y `time.monotonic()`). Docstring: los
  Services reciben el reloj para que las pruebas lo controlen.
- [X] T014 [P] `src/services/health_state.py`: `@dataclass(frozen=True, slots=True) class CachedResult(result,
  completed_at: float, generation: int)`, `InFlight(generation: int, task: asyncio.Task)` y
  `class HealthState` (sin E/S ni configuración) con `generation = 0`, `last: CachedResult | None = None`,
  `in_flight: InFlight | None = None`, `registry_snapshot: tuple | None = None` (`None` = nunca leído),
  `readiness_task: asyncio.Task | None = None`, `last_statuses: dict[str, str]` y `invalidate()` (incrementa
  `generation` y borra `last`). El tipo del resultado se anota con `HealthResult` bajo `TYPE_CHECKING`.
- [X] T015 [P] `src/integrations/health_probe.py` (cumple T008; solo la fábrica en esta fase):
  `MAX_RESPONSE_BYTES = 65_536`, `PROBE_MAX_CONNECTIONS = 200` y
  `create_health_http_client(*, timeout_seconds: float, user_agent: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient`
  con `follow_redirects=False`, `trust_env=False`, `timeout=httpx.Timeout(timeout_seconds)`,
  `limits=httpx.Limits(max_connections=200, max_keepalive_connections=0)`, cabeceras
  `{"User-Agent": user_agent, "Accept-Encoding": "identity"}` y un tarro de cookies
  (`httpx.Cookies(http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[])))`)
  que no acepta ninguna. Docstring: por qué cada ajuste ([R6](research.md#r6-llamadas-a-los-componentes-fr-019-fr-021-sc-004-sc-005)).
  Sin `fastapi`, `sqlalchemy`, DTOs ni modelos.
- [X] T016 `src/main.py` (cumple T007; depende de T010, T011, T014 y T015): (1) `lifespan` carga juntas, antes
  de rendirse, `get_settings` (valida `DATABASE_URL`, decisión aprobada), `get_integration_settings`,
  `get_dashboard_settings`, `get_health_settings` y `get_build_settings`, y nombra todas las inválidas en un
  solo mensaje (como hoy); (2) crea `app.state.health_http_client = create_health_http_client(timeout_seconds=health_config_from(get_health_settings()).check_timeout_seconds, user_agent=f"maily-system-api-health/{VERSION}")`
  y lo cierra en el `finally` junto con el actual; (3) `create_app()` crea `app.state.health = HealthState()`
  (sin E/S); (4) añade a `OPENAPI_TAGS` `{"name": "Salud", "description": "Salud de los servicios de Maily: contrato de salud v1 (público), estado público de la plataforma, consulta agregada de salud y registro de componentes monitoreados."}`;
  (5) en `DESCRIPTION`, cambia «**Todas las operaciones exigen un token de acceso y un permiso**» por «**Todas
  las operaciones exigen un token de acceso y un permiso**, salvo las cuatro rutas públicas de salud
  (`/health/live`, `/health/ready`, `/info` y `/health/status`)» y añade un párrafo sobre la salud de servicios
  (consulta agregada siempre 200, registro sin redespliegue, estado público sin token y sin datos sensibles).
- [X] T017 [P] `src/models/monitored_component.py` y `src/models/__init__.py` (data-model sección 2):
  `MONITORED_COMPONENT_CODE_INDEX = "monitored_components_code_not_deleted_key"` y
  `class MonitoredComponent(Base)` (`__tablename__ = "monitored_components"`) con `id: Mapped[UUID]`
  (`Uuid`, `primary_key`, `server_default=text("gen_random_uuid()")`); `code` `String(50)`; `name`
  `String(100)`; `kind` `String(20)`; `base_url` `String(255)`; `live_path` `String(200)` no nula;
  `ready_path` e `info_path` `String(200)` nulas; `enabled` `Boolean` `server_default=text("true")`;
  `sort_order` `Integer` `server_default=text("0")`; `created_at` y `updated_at` `DateTime(timezone=True)`
  `server_default=text("CURRENT_TIMESTAMP")`; `deleted_at` `DateTime(timezone=True)` nula; `__table_args__`
  con `CheckConstraint`: `code_check` (`char_length(code) BETWEEN 2 AND 50 AND code ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$' AND code NOT IN ('maily-system-api', 'database')`),
  `name_check` (`btrim(name) <> '' AND name = btrim(name)`), `kind_check` (`kind IN ('service', 'frontend')`),
  `sort_order_check` (`sort_order BETWEEN 0 AND 9999`), `service_paths_check`
  (`kind <> 'service' OR (ready_path IS NOT NULL AND info_path IS NOT NULL)`) y `frontend_ready_path_check`
  (`kind <> 'frontend' OR ready_path IS NULL`) (la convención de `Base` antepone `monitored_components_`), y el
  `Index(MONITORED_COMPONENT_CODE_INDEX, MonitoredComponent.code, unique=True, postgresql_where=text("deleted_at IS NULL"))`.
  Docstring: los integrados no se guardan aquí y sus códigos están reservados. Exportarlo en `__all__`.
- [X] T018 `alembic/versions/0004_monitored_components.py` (revisa `0003`; cumple T009): reproduce
  [contracts/database-schema.sql](contracts/database-schema.sql) con `op.create_table` (CHECK con los nombres
  cortos de T017, como hace 0001), `op.create_index("monitored_components_code_not_deleted_key", …, unique=True, postgresql_where=sa.text("deleted_at IS NULL"))`
  y `op.execute("CREATE TRIGGER monitored_components_set_updated_at BEFORE UPDATE ON monitored_components FOR EACH ROW EXECUTE FUNCTION set_updated_at()")`.
  `downgrade`: borra el disparador, el índice y la tabla, **no** la función. Docstring en español como las
  migraciones anteriores (qué reproduce y por qué la función no se borra).
- [X] T019 [P] `project-definition/DATA_SCHEMA.md`: actualizar el párrafo inicial (coincide con las
  migraciones 0001 a 0004); añadir a la tabla de nombres `monitored_components_code_check`,
  `monitored_components_name_check`, `monitored_components_kind_check`, `monitored_components_sort_order_check`,
  `monitored_components_service_paths_check` y `monitored_components_frontend_ready_path_check`, todas con
  `-- [spec 005-health-monitoring]`; mencionar el índice `monitored_components_code_not_deleted_key` y el
  disparador `monitored_components_set_updated_at`; y añadir al bloque SQL la tabla, el índice y el
  disparador de [contracts/database-schema.sql](contracts/database-schema.sql) con sus comentarios `-- [spec 005 …]`.
- [X] T020 [P] `tests/integration/test_monitored_component_repository.py` (escribirla **antes** de T021; contra
  PostgreSQL 17, sesión con `commit` real y `TRUNCATE monitored_components` al terminar): `list_enabled()`
  devuelve solo los vigentes y habilitados, en orden `sort_order` y `code` con orden de puntos de código
  (con `a-c` y `ab` en el mismo `sort_order`, `a-c` va antes: `COLLATE "C"`), sin los eliminados
  (`deleted_at` con fecha) ni los deshabilitados; con la tabla vacía, `[]`.
- [X] T021 `src/repositories/monitored_component_repository.py` (cumple T020; depende de T017 y T018):
  `class MonitoredComponentRepository` con `__init__(session)` y `async list_enabled() -> list[MonitoredComponent]`
  (`WHERE deleted_at IS NULL AND enabled ORDER BY sort_order, code COLLATE "C"`, con
  `MonitoredComponent.code.collate("C")`). Docstring: única capa que consulta el registro.
- [X] T022 [P] `tests/integration/test_database_health_repository.py` (escribirla **antes** de T023): (a)
  contra la base de pruebas, `DatabaseHealthRepository(session).ping()` termina sin error; (b) con una sesión de
  un engine a `postgresql+asyncpg://nobody:nobody@127.0.0.1:1/not_configured_test` lanza
  `DatabaseUnavailableError` con `kind == "connection_error"` (falla al obtener la conexión); (c) si la
  ejecución falla con un error que no es de desconexión (sustituir `session.execute` por uno que lance
  `sqlalchemy.exc.ProgrammingError`) → `kind == "unexpected_error"`; (d) una cancelación
  (`asyncio.CancelledError`) **no** se atrapa; (e) el mensaje de la excepción no contiene la dirección.
- [X] T023 `src/repositories/errors.py` y `src/repositories/database_health_repository.py` (cumple T022):
  `class DatabaseUnavailableError(Exception)` con `__init__(self, kind: str)`, `self.kind` y el mensaje
  genérico `"The database did not answer as expected"`; `class DatabaseHealthRepository` con
  `async ping()`: `await session.connection()` en un `try` (cualquier `Exception` → `connection_error`) y luego
  `await session.execute(text("SELECT 1"))` (`DBAPIError` con `connection_invalidated` → `connection_error`;
  cualquier otra `Exception` → `unexpected_error`), siempre `raise … from None`. Sin `fastapi` ni DTOs.
- [X] T024 `src/dependencies.py` (aditivo; depende de T010, T013, T014, T021 y T023): `async get_health_config() -> HealthConfig`
  (`health_config_from(get_health_settings())`), `async get_build_info() -> BuildInfo`, `_SYSTEM_CLOCK =
  SystemClock()` y `async get_clock() -> Clock`, `async get_health_state(request) -> HealthState`
  (`request.app.state.health`), `async get_health_http_client(request)` (`request.app.state.health_http_client`),
  `async read_enabled_components()` y `async ping_database()` (cada una abre **su propia** sesión con
  `get_session_factory()()` y usa su Repository: la agregación es compartida y no puede depender de la sesión
  de una petición), `async get_registry_reader()` y `async get_database_pinger()` (devuelven esas dos
  funciones, para que las pruebas las sustituyan). Actualizar el docstring del módulo.
- [X] T025 [P] `tests/stubs/components/__init__.py` (vacío) y `tests/stubs/components/app.py` (simulación de
  componentes, autocontenida: no importa `src/` ni usa imports relativos; [contracts/e2e-collection.md](contracts/e2e-collection.md)):
  `create_stub_app()` y `app = create_stub_app()`; `GET /{prefix}/{rest:path}` con el comportamiento del modo
  del prefijo (`state["modes"].get(prefix, prefix)`): `healthy` (`health/live` 200 `{"status":"ok"}`;
  `health/ready` 200 `ok` con un chequeo `database` `ok`; `info` 200 con `service`, `version` `"1.4.2"`,
  `commit` de 40 hexadecimales, `build_date` `"2026-10-20T15:30:00-06:00"`, `environment` `"e2e"`;
  `healthz/` 200 HTML; otra ruta 404; las respuestas `ok` llevan `Set-Cookie: session=SECRETO-INTERNO; Path=/`),
  `not-ready` (`ready` 503 `unavailable` con un chequeo `database` en `timeout` y otro `cache` con
  `error: "disk_full"`), `html` (200 `text/html` con el marcador `SECRETO-INTERNO`), `not-json` (200
  `text/plain`), `redirect` (307 a `/healthy/{rest}`), `slow` (espera `state["slow_seconds"]`, 30 por defecto,
  y responde como `healthy`), `too-large` (200 JSON de 70 KiB con `Content-Length`), `too-large-chunked`
  (lo mismo con `StreamingResponse`, sin `Content-Length`), `gzip` (200 con `Content-Encoding: gzip` y el
  cuerpo comprimido), `info-incomplete` (`info` `{"version": 123, "commit": "a"*100 + "\u0007", "build_date": "ayer", "environment": null, "extra": "SECRETO-INTERNO"}`),
  `many-checks` (`ready` 200 `ok` con 25 chequeos, algunos sin `name`, con `status` `warn`, `latency_ms`
  `"12"` o `true` y `error` `"weird"`), `error` (500 con el marcador) y `spa` (200 HTML en **cualquier**
  ruta). Un middleware ASGI registra cada llamada (salvo `/__test__/`): `path`, `method`, `header_names`
  (minúsculas), `has_authorization` y `has_cookie`. Superficie de pruebas: `GET /__test__/calls`,
  `POST /__test__/reset` (borra llamadas y modos; `slow_seconds` vuelve a 30) y `POST /__test__/modes`
  (`{"prefix": …, "mode": …}`, 422 si el modo no existe).
- [X] T026 [P] `tests/health_support.py` (sin fixtures, como `tests/helpers.py`; imports de la aplicación dentro
  de funciones): `TEST_NOW = datetime(2026, 10, 27, 16, 0, tzinfo=UTC)` (martes 10:00 en la Ciudad de México);
  `COMPONENTS_HOST = "components.test"`; `TEST_ALLOWED_HOSTS = "components.test,dns-error.test,refused.test,reset.test,tls-error.test"`;
  `stub_url(prefix) -> f"http://components.test/{prefix}"`; `TEST_HEALTH_CONFIG` (timeouts 0,5 y 0,3,
  caché 0, la lista de arriba, sin horario); `class FakeClock(now=TEST_NOW, monotonic=1000.0)` con `now()`,
  `monotonic()`, `advance(seconds)` (mueve los dos) y `set(now)`; `class FaultTransport(inner)` que, según el
  host, lanza `httpx.ConnectError` con causa `socket.gaierror` (`dns-error.test`), con causa
  `ConnectionRefusedError` (`refused.test`), con causa `ssl.SSLCertVerificationError` (`tls-error.test`) o
  `httpx.RemoteProtocolError` (`reset.test`), y si no delega en `inner`; `class HealthConfigHolder(config)`
  con `config` y `replace(**changes)` (`dataclasses.replace`); `async insert_component(engine, **values) -> UUID`
  (inserta directo con valores por defecto: `code` único, `name`, `kind="service"`, `base_url=stub_url("healthy")`,
  las tres rutas del contrato si es `service`, `enabled=True`, `sort_order=0`; acepta `deleted_at`);
  `install_health_overrides(app, components_app, holder, clock=None) -> httpx.AsyncClient` (sustituye
  `get_health_http_client` por `create_health_http_client(timeout_seconds=…, user_agent="maily-system-api-health/test", transport=FaultTransport(httpx.ASGITransport(app=components_app)))`,
  `get_health_config` por `lambda: holder.config` y, si se pasa, `get_clock`; devuelve el cliente para
  cerrarlo); y `class HealthApi` con `app`, `client`, `anonymous`, `users_stub`, `components_stub`, `engine`,
  `clock`, `holder` y los métodos `insert_component(**values)`, `component_calls()`, `reset_components()`,
  `set_component_mode(prefix, mode)`, `grant(permissions, token=TEST_TOKEN)`, `users_fault(mode, count=1, delay=30)`,
  `users_calls()`, `use(dependency, provider)`, `set_config(**changes)`, `health()` (`GET /api/v1/health`),
  `status()` (`GET /health/status`, sin token) y `get(path, **kwargs)`.
- [X] T027 `tests/conftest.py` (ajuste **A7** y fixtures nuevas; depende de T024 a T026): (1) fixtures
  `components_stub_app` (nueva app por prueba) y `components_stub` (cliente `httpx` con `ASGITransport` a
  `http://components.test` para `/__test__/`); (2) la fixture `api` llama a
  `install_health_overrides(app, components_stub_app, HealthConfigHolder(TEST_HEALTH_CONFIG))`, cierra el
  cliente al terminar y su `TRUNCATE` pasa a `TRUNCATE subscriptions, monitored_components RESTART IDENTITY CASCADE`
  (nada más cambia en `api` ni en `Api`); (3) fixture nueva `health_api(engine, migrated_db, users_stub,
  components_stub_app, components_stub)`: `create_app()`, sustituye `get_users_api_client` (cliente real sobre
  la simulación), `get_session` (sesión del `engine` de pruebas) y aplica `install_health_overrides` con un
  `FakeClock()` y un `HealthConfigHolder(TEST_HEALTH_CONFIG)`; registra `TEST_TOKEN` con los cuatro `health:*`;
  crea los clientes con y sin token; cede un `HealthApi`; al terminar vacía `monitored_components` y cierra
  los clientes.
- [X] T028 Checkpoint de la fase: `uv run pytest tests/unit/test_allowed_hosts.py tests/unit/test_health_settings.py tests/unit/test_health_startup.py tests/unit/test_health_http_client.py tests/unit/test_layering.py tests/unit/test_main.py tests/unit/test_config.py tests/unit/test_dashboard_startup.py tests/integration/test_monitored_components_migration.py tests/integration/test_models_match_migrations.py tests/integration/test_migrations.py tests/integration/test_monitored_component_repository.py tests/integration/test_database_health_repository.py`
  en verde; `uv run python -c "import tests.health_support, tests.stubs.components.app"` sin errores; y
  `uv run pytest` **completo** sigue en verde (aún no hay rutas nuevas).

**Checkpoint**: Fundamentos listos: configuración, versión, permisos, estado del proceso, cliente HTTP de
chequeos, tabla del registro, consulta a la base e infraestructura de pruebas.

---

## Phase 3: User Story 1 - Ver en una sola consulta la salud de todos los componentes (Priority: P1) 🎯 MVP

**Goal**: `GET /api/v1/health` (permiso `health:read`) responde siempre 200 con el estado global, los dos
integrados y los registrados habilitados, cada uno con sus trece campos, depurado, sin direcciones ni cuerpos
crudos, con la agregación en paralelo, compartida y en caché por proceso
([R6](research.md#r6-llamadas-a-los-componentes-fr-019-fr-021-sc-004-sc-005) a
[R10](research.md#r10-caché-agregación-compartida-y-periodo-mínimo-del-estado-público-fr-020-fr-048-sc-006-sc-016)).

**Independent Test**: con `health:read` concedido por la simulación y dos servicios registrados (insertados en
la base: uno sano y otro lento), la consulta responde 200, global `down`, los integrados primero y después los
registrados en su orden, los trece campos y ninguna dirección ni cuerpo crudo; sin token, sin el permiso y con
el API de usuarios caído responde 401, 403 y 503 sin datos y sin consultar ningún componente.

### Tests for User Story 1 (escribirlas primero; deben fallar) ⚠️

- [X] T029 [P] [US1] `tests/unit/test_health_contract.py` (sin base de datos; construir `ProbeResponse` a mano):
  `parse_live`: 200 con `{"status":"ok"}` (y con campos extra) → bien; 500 o 307 → `unexpected_status`; 200
  con HTML, texto, lista JSON o `{"status":"fine"}` → `invalid_response`; una falla de red se conserva
  (`timeout`, `dns_error`…). `parse_ready`: 200 `ok` con `checks` → bien con sus chequeos; 503 `unavailable`
  con `checks` → `not_ready` con sus chequeos; 200 con `status` `unavailable`, 503 con HTML, 200 sin
  `checks` → `invalid_response`; 404 → `unexpected_status`. `parse_frontend`: 200, 204 y 299 → bien sin leer el
  cuerpo; 301, 404 y 500 → `unexpected_status`. `parse_info`: campos válidos → `BuildData` con `build_date`
  `"2026-10-20T15:30:00-06:00"` normalizada a `"2026-10-20T21:30:00Z"`; cualquier falla, otro código o un
  cuerpo que no es objeto → los cuatro `unknown`; un campo ausente, no texto (`123`, `null`, `true`) o vacío
  tras limpiar → solo ese `unknown`. `clean_text`: quita caracteres de control (categoría `C*`, incluido
  `\u0007` y `\n`), recorta espacios y corta a 64. `clean_build_date`: sin zona, inválida o no texto →
  `unknown`. `clean_checks`: toma los **primeros 20** elementos y descarta los mal formados (sin `name` de
  texto, `status` distinto de `ok`/`error`, no objeto); `latency_ms` entero ≥ 0 o `None` (`True`, `"12"`,
  `12.5` y `-1` → `None`); `error` `None` si `ok`; si `error`, uno de `CHECK_ERROR_CODES` y cualquier otro
  (`"disk_full"`, ausente) → `unexpected_error`; el nombre se limpia como un texto. Ningún resultado conserva
  el marcador `SECRETO-INTERNO`.
- [X] T030 [P] [US1] `tests/unit/test_health_probe.py` (sin base de datos): `HealthProbeClient(create_health_http_client(timeout_seconds=0.3, user_agent="ua", transport=FaultTransport(httpx.ASGITransport(app=create_stub_app()))), timeout_seconds=0.3)`:
  (a) `get_json(stub_url("healthy") + "/health/live")` → 200, cuerpo y `latency_ms` entero ≥ 0; (b)
  `too-large` → `response_too_large` (por `Content-Length`) y `too-large-chunked` → `response_too_large`
  (leyendo a lo más 65 536 bytes); un cuerpo de exactamente 65 536 bytes se acepta; (c) `gzip` →
  `invalid_response`; (d) `redirect` → 307 sin seguirla (la simulación no recibe la ruta de destino); (e)
  `slow` → `timeout` con `latency_ms` entre 250 y 1 500; (f) `dns-error.test` → `dns_error`; `refused.test`,
  `tls-error.test` y `reset.test` → `connection_error`; (g) ninguna llamada llega con `Authorization` ni
  `Cookie` (dos llamadas seguidas a `healthy`, que pone una cookie); todas son `GET` y llevan el
  `User-Agent`; (h) `get_status` devuelve el código de `spa` y de `html` sin `body`; (i) una excepción
  inesperada del transporte → `unexpected_error`; (j) los registros no contienen la dirección.
- [X] T031 [P] [US1] `tests/unit/test_health_service.py` (sin base de datos) y, en `tests/health_support.py`,
  `FakeProbe` (respuestas programadas por URL —`ProbeResponse` o función—, registro de llamadas con su tipo
  `json`/`status`, barrera y retraso opcionales) y `make_component(code, **values) -> MonitoredComponent`
  (objeto transitorio con `id`): construir `HealthService(state=HealthState(), config=TEST_HEALTH_CONFIG,
  build=BuildInfo(...), clock=FakeClock(), probe=FakeProbe(...), read_registry=…, ping_database=…)` y
  comprobar: (a) reglas de servicio de [R8](research.md#r8-reglas-de-estado-fr-014-a-fr-018) (`up`; `degraded`
  con `not_ready` y los chequeos; `degraded` con el código de `ready`; `down` con el de `live`; `info` que
  falla → `unknown` sin cambiar el estado; `checks` y `latency_ms` de `live`); (b) reglas de frontend (2xx →
  `up`; 404 o 3xx → `down` `unexpected_status`; con `info_path` se lee, sin ella `unknown`); (c) integrados:
  `database` `up` o `down` (con `timeout`, `connection_error` o `unexpected_error`), `checks` vacía y datos
  de build `unknown`; `maily-system-api` `up` o `degraded` con `not_ready`, con `checks` `[database]`, la
  latencia de la consulta y los datos de `BuildInfo`; **una sola** consulta a la base por agregación y
  ninguna llamada del `FakeProbe` para `maily-system-api`; (d) un registrado cuyo host no está en la lista →
  `unknown`, `host_not_allowed`, `latency_ms` `None` y sin llamadas; (e) una excepción inesperada al evaluar un
  componente → solo ese `unknown` con `unexpected_error` y un registro `ERROR` sin la dirección; (f) estado
  global de FR-017 (`down` > `degraded`/`stopped`/`unknown` > `ok`; `registry_available` no lo cambia); (g)
  orden: integrados y luego `(sort_order, code)` por puntos de código; (h) lectura del registro que falla →
  solo los integrados y `registry_available` `False` (la copia en memoria llega en US5); vacía → solo los
  integrados y `True`; (i) paralelismo: la base y el registro empiezan a la vez; los chequeos empiezan al
  terminar la lectura del registro, sin esperar a la base; las tres llamadas de un servicio van en paralelo;
  (j) caché: con `cache_seconds=15` una segunda llamada reutiliza el resultado con los mismos `checked_at`;
  con 0 lanza otra agregación; 50 llamadas simultáneas → **una** agregación (cada URL una vez); cancelar la
  tarea de quien esperaba no cancela la agregación (`asyncio.shield`); (k) generación: `state.invalidate()` →
  la siguiente llamada no reutiliza; con una agregación en curso de la generación anterior, la siguiente
  espera a que termine y lanza otra, y nunca hay dos a la vez (contar concurrencia máxima 1); (l) con un
  registrado lento la agregación dura menos de `check_timeout_seconds` + 0,5 s; (m) registros: un componente
  que pasa a `down` registra un `WARNING` con su `code` y su código de error (sin la dirección); otra
  agregación con el mismo estado no vuelve a registrar.
- [X] T032 [P] [US1] `tests/contract/test_health_api.py` (con `health_api`): (a) componentes `healthy` (orden 10)
  y `slow` (orden 20) insertados → 200, `Cache-Control: no-store`, `status` `down`, `registry_available`
  `true`, `checked_at` `…Z`, componentes en orden `maily-system-api`, `database`, `healthy`, `slow`, cada uno
  con **exactamente** los trece campos de FR-012; `slow` `down` con `timeout`; (b) el cuerpo no contiene
  `components.test`, `http://`, `SECRETO-INTERNO` ni el token; (c) la simulación no recibió ninguna llamada
  con `Authorization`; (d) un componente deshabilitado y otro eliminado (`deleted_at`) no aparecen ni reciben
  llamadas; (e) sin registrados → solo los integrados y `registry_available` `true`; (f) parámetros de
  consulta desconocidos se ignoran; (g) con 20 registrados (varios `slow`) la respuesta llega en menos de
  `check_timeout_seconds` + 1 s (SC-001); (h) un frontend `spa` con `live_path` `/healthz/` sale `up` y uno
  `html` registrado como servicio sale `down` con `invalid_response`; (i) con `TEST_ALLOWED_HOSTS` sin
  `components.test` (`set_config`), los registrados salen `unknown` con `host_not_allowed` y no se les llama.
- [X] T033 [P] [US1] `tests/contract/test_health_access_control.py` (con `health_api`): sin token → 401
  `unauthenticated` con `WWW-Authenticate`; token inválido → 401 `invalid_token`; vencido → 401
  `token_expired`; sin `health:read` (solo `dashboard:read`, o los otros tres `health:*`) → 403
  `permission_denied` que nombra `health:read`; API de usuarios caído (`users_fault("unavailable")`) → 503
  `authorization_unavailable`; en todos, el cuerpo no trae `components` y la simulación de componentes **no**
  recibió llamadas; la pregunta al API de usuarios es exactamente por `health:read` con el token tal cual;
  con `cache_seconds=15`, 50 consultas simultáneas → 50 consultas de permiso y **una** ronda de chequeos
  (SC-006); con un resultado en caché, retirar el permiso hace que la siguiente consulta reciba 403 (la caché
  nunca guarda decisiones).
- [X] T034 [US1] Ajuste **A1** (parte de US1) en `tests/contract/test_permission_coverage.py`: añadir
  `"get_health": "health:read"` a `EXPECTED_PERMISSIONS` y `"get_health": ("GET", "/api/v1/health", None)` a
  `REQUESTS`, y actualizar el comentario de la matriz (incluye la spec 005). Ninguna aserción cambia.
- [X] T035 [P] [US1] `tests/contract/test_health_openapi.py` (sin base de datos; `create_app().openapi()`):
  `get_health` en `GET /api/v1/health` con `tags == ["Salud"]`, `security == [{"BearerAuth": []}]`,
  `x-required-permission == "health:read"`, `"Permiso requerido: `health:read`"` en la descripción, respuestas
  200/401/403/503 (las de error con `ErrorResponse`), 200 con la cabecera `Cache-Control` y el esquema
  `HealthRead`; `HealthRead` y `ComponentHealthRead` con exactamente los campos de
  [data-model.md](data-model.md) sección 5 (todos obligatorios), `status` con los enumerados de la spec y
  `error` con los nueve códigos de FR-018 o `null`; la etiqueta «Salud» está en `openapi_tags`.

### Implementation for User Story 1

- [X] T036 [P] [US1] `src/integrations/health_contract.py` (cumple T029; funciones puras, solo biblioteca
  estándar): constantes `UNKNOWN`, `MAX_TEXT_LENGTH`, `MAX_CHECKS`, `CHECK_ERROR_CODES`; registros
  `CheckResult`, `BuildData`, `CallOutcome` (`@dataclass(frozen=True, slots=True)`, [data-model.md](data-model.md)
  sección 4); `parse_live`, `parse_ready`, `parse_frontend`, `parse_info`, `clean_text`, `clean_build_date` y
  `clean_checks` con las reglas de [R7](research.md#r7-depuración-del-contrato-v1-fr-013-fr-014-fr-015) y de
  [contracts/health-contract-v1.md](contracts/health-contract-v1.md) sección 2. El JSON se decodifica de los
  bytes con `json.loads`; nunca se devuelve texto crudo.
- [X] T037 [US1] `src/integrations/health_probe.py` (cumple T030; después de T015): `ProbeResponse`
  (`status_code: int | None`, `body: bytes | None`, `failure: str | None`, `latency_ms: int`) y
  `HealthProbeClient(http_client, timeout_seconds)` con `get_json(url)` (`Accept: application/json`) y
  `get_status(url)` (`Accept: */*`; no lee el cuerpo): `GET` con `client.stream(..., follow_redirects=False)`
  dentro de `asyncio.timeout(timeout_seconds)` alrededor de **todo**; `Content-Length` > 65 536 →
  `response_too_large` sin leer; `Content-Encoding` distinto de `identity` → `invalid_response`; lectura con
  `aiter_raw()` hasta 65 536 bytes (uno más → `response_too_large`); traducción de fallas de
  [R6](research.md#r6-llamadas-a-los-componentes-fr-019-fr-021-sc-004-sc-005) (la `socket.gaierror` se busca en la
  cadena `__cause__`/`__context__`); latencia con `time.perf_counter()`; el log nombra solo el tipo de falla;
  sin reintentos.
- [X] T038 [P] [US1] `src/dtos/health.py`: `CheckRead`, `ComponentHealthRead` y `HealthRead` (data-model sección
  5): `status` con `Literal` de la spec, `latency_ms: int | None` con `ge=0`, fechas `AwareDatetime`
  normalizadas a UTC (como `RecentClinicRead`), `next_start_at: AwareDatetime | None`, `components` nunca
  nula, descripciones y ejemplos en español; sin ningún campo de dirección. Conversión desde los registros
  del Service con `model_validate(..., from_attributes=True)`.
- [X] T039 [US1] `src/services/health_service.py` (cumple T031; depende de T013, T014, T036 y T037):
  constantes `SELF_CODE`, `SELF_NAME`, `DATABASE_CODE`, `DATABASE_NAME`, `RESERVED_CODES`; registros
  `ComponentTarget` (con `from_model(model)`), `ComponentHealth`, `HealthResult`; `global_status(components)`;
  `class HealthService` con `async health()` (= `current_result(max_age=config.cache_seconds)`) y la
  maquinaria de [R9](research.md#r9-agregación-en-paralelo-y-su-duración-fr-019-sc-001) y
  [R10](research.md#r10-caché-agregación-compartida-y-periodo-mínimo-del-estado-público-fr-020-fr-048-sc-006-sc-016):
  `current_result` (caché por generación y edad monótona, una agregación en curso con `asyncio.create_task`,
  esperas con `asyncio.shield`, una agregación de una generación vieja se espera y se relanza, solo se guarda
  si su generación sigue vigente y `in_flight` se libera en `finally`), `_aggregate` (base de datos y
  registro a la vez con `asyncio.timeout(config.check_timeout_seconds)` cada uno; los chequeos al conocerse
  la lista; `asyncio.gather`; integrados y orden; `checked_at` al terminar), `_check_target` (lista
  permitida vigente con `urlsplit(base_url).hostname` y `config.allowed_hosts.allows`; guardia de que la
  `httpx.URL` armada con `base_url + ruta` conserva esquema, host y puerto; `live`, `ready` e `info` en
  paralelo o la ruta de salud del frontend; reglas de R8; guarda que convierte una excepción inesperada en
  `unknown`/`unexpected_error`), `_database_component` y `_self_component`; y los registros de cambio de
  estado con `state.last_statuses`. Sin `fastapi` ni `sqlalchemy`.
- [X] T040 [US1] `src/dependencies.py` (después de T024): `async get_health_probe(client=Depends(get_health_http_client), config=Depends(get_health_config)) -> HealthProbeClient`
  y `async get_health_service(...) -> HealthService` con `state`, `config`, `build`, `clock`, `probe`,
  `read_registry` y `ping_database` de sus proveedores.
- [X] T041 [US1] `src/routers/health.py` (nuevo; depende de T038 y T040): `HEALTH_TAG = "Salud"`,
  `HEALTH_PATH = "/api/v1/health"`, `router = APIRouter(tags=[HEALTH_TAG])` y `GET /api/v1/health`
  (`operation_id="get_health"`, `response_model=HealthRead`, resumen y descripción en español con
  «Permiso requerido: `health:read`.», `**protected(HEALTH_READ, responses={200: …})` con el ejemplo y la
  cabecera `Cache-Control` documentados): llama a `service.health()`, pone `Cache-Control: no-store` y
  convierte el resultado a `HealthRead`. El Router no importa integraciones, repositorios ni modelos.
- [X] T042 [US1] `src/main.py`: `app.include_router(health.router)` en `create_app()` (después del dashboard).
  Desde aquí G9 queda en rojo hasta T104 (ver Convenciones).
- [X] T043 [US1] Checkpoint: `uv run pytest tests/unit/test_health_contract.py tests/unit/test_health_probe.py tests/unit/test_health_service.py tests/contract/test_health_api.py tests/contract/test_health_access_control.py tests/contract/test_health_openapi.py tests/contract/test_permission_coverage.py tests/unit/test_layering.py`
  en verde.

**Checkpoint**: US1 funciona y se prueba por sí sola: la consulta de salud protegida muestra integrados y
registrados.

---

## Phase 4: User Story 2 - Este servicio cumple el contrato de salud v1 y aparece como componente integrado (Priority: P1)

**Goal**: `/health/live`, `/health/ready` e `/info` públicos, en la raíz, con `Cache-Control: no-store`, con la
versión de una sola fuente y los datos de build de `APP_*`, y la imagen Docker preparada para recibirlos
([R1](research.md#r1-versión-de-una-sola-fuente-fr-007-sc-008), [R5](research.md#r5-chequeo-de-la-base-de-datos-fr-005-fr-016-sc-007), [R17](research.md#r17-datos-de-build-dockerfile-y-compose-fr-006-fr-009)).

**Independent Test**: sin token, las tres rutas con la base disponible y sin ella dan los códigos, cuerpos y
`no-store` del contrato; `/health/live` responde en menos de 100 ms aunque la base no responda; la versión de
`/info` es la del OpenAPI; sin las variables de build vale `unknown` y arranca igual; la consulta agregada
muestra `maily-system-api` sin que el servicio se llame a sí mismo.

### Tests for User Story 2 (escribirlas primero; deben fallar) ⚠️

- [X] T044 [P] [US2] `tests/contract/test_health_public_api.py` (con `health_api`): (a) `GET /health/live` sin
  token → 200 `{"status":"ok"}` exacto, `no-store`, en menos de 100 ms aun con `get_database_pinger`
  sustituido por uno que no termina; no consulta al API de usuarios; (b) `GET /health/ready` → 200 `ok` con un
  único chequeo `database` `ok` y `latency_ms` entero; (c) con un *pinger* que no termina → 503 `unavailable`,
  `error` `timeout` y respuesta en menos de `ready_timeout_seconds` + 1 s (SC-007); con uno que lanza
  `DatabaseUnavailableError("connection_error")` → `connection_error`; con uno que lanza `RuntimeError("SECRETO-INTERNO host=db")`
  → `unexpected_error` y el cuerpo no contiene el texto; nunca 500; (d) el resultado no cambia con el API de
  usuarios caído; (e) 20 peticiones simultáneas a `/health/ready` → **una** consulta a la base (contar
  llamadas del *pinger*); al terminar, la siguiente vuelve a consultar; (f) `GET /info` sin variables →
  `service` `maily-system-api`, `version` `2.0.0` y tres `unknown`; con `get_build_info` sustituido → esos
  valores; (g) una cabecera `Authorization` (válida o no) no cambia nada; (h) CORS (FR-050): con
  `CORS_ALLOWED_ORIGINS=http://localhost:5173` (variable, `get_cors_settings.cache_clear()` y una app nueva
  con `install_health_overrides`), `/health/live` y `/health/ready` (200 **y** 503) con
  `Origin: http://localhost:5173` llevan `access-control-allow-origin` y **no** `access-control-allow-credentials`;
  con `Origin: http://otro.example`, ninguna cabecera CORS; (i) la consulta agregada muestra
  `maily-system-api` con los mismos datos de build que `/info` y la simulación de componentes no recibió
  ninguna llamada a rutas del propio servicio.
- [X] T045 [P] [US2] `tests/unit/test_version.py` (sin base de datos): `tomllib` lee `pyproject.toml`
  (`project.version`) y `uv.lock` (el paquete `mailysoft-system-api`); ambos valen `src.VERSION`, igual que
  `create_app().version`, `create_app().openapi()["info"]["version"]` y la `version` de `/info` (pedida por
  `httpx.ASGITransport` con los proveedores sustituidos).
- [X] T046 [US2] `tests/unit/test_health_service.py` (después de T031): `readiness()` → `ReadinessResult(ok=True)`
  con el chequeo `database` `ok`; `timeout` con un *pinger* que no termina (`ready_timeout_seconds=0.2`),
  `connection_error` y `unexpected_error` según la excepción, con `latency_ms` medido también al fallar;
  peticiones simultáneas comparten la comprobación (`state.readiness_task`) y al terminar no se guarda nada;
  registros: un `WARNING` solo cuando el resultado cambia; `info()` devuelve el `BuildInfo` recibido.
- [X] T047 [US2] Ajuste **A1** (parte de US2) en `tests/contract/test_permission_coverage.py`: `PUBLIC_ROUTES`
  suma `/health/live`, `/health/ready` e `/info`; en
  `test_every_route_declares_its_permission_or_is_public_documentation`, una `APIRoute` anidada cuya ruta esté
  en `PUBLIC_ROUTES` se anota en `public_seen` y **no** se cuenta en `checked`; `declared_permissions()` omite
  las operaciones de las rutas de `PUBLIC_ROUTES` (hoy accedería a `x-required-permission`, que no tienen).
  `checked == len(EXPECTED_PERMISSIONS)` y `public_seen == PUBLIC_ROUTES` se mantienen.
- [X] T048 [US2] Ajustes **A2** y **A3** (parte de seguridad): en `tests/contract/test_openapi_contract.py`
  (`test_the_documentation_routes_declare_no_security`) y en `tests/contract/test_dashboard_openapi.py`
  (`test_every_operation_of_the_api_declares_security_and_permission`), excluir **solo** las operaciones de
  `PUBLIC_HEALTH_PATHS = {"/health/live", "/health/ready", "/info", "/health/status"}` (constante en cada
  archivo, con un comentario que remite a la spec 005); el resto de las aserciones no cambia.
- [X] T049 [US2] `tests/contract/test_health_openapi.py` (después de T035): `get_health_live`,
  `get_health_ready` y `get_info` en sus rutas, con `tags == ["Salud"]`, **sin** `security` ni
  `x-required-permission`; `get_health_ready` documenta 200 y 503 con el esquema `ReadyRead`; las tres
  documentan `Cache-Control`; `InfoRead` con exactamente `service`, `version`, `commit`, `build_date` y
  `environment`.

### Implementation for User Story 2

- [X] T050 [US2] `src/dtos/health.py` (después de T038): `LiveRead` (`status: Literal["ok"]`), `ReadyRead`
  (`status: Literal["ok", "unavailable"]`, `checks: list[CheckRead]`) e `InfoRead` (`service`, `version`,
  `commit`, `build_date`, `environment`: `str`), con descripciones en español.
- [X] T051 [US2] `src/services/health_service.py` (después de T039): `ReadinessResult` y `async readiness()`
  (`ping_database` con `asyncio.timeout(config.ready_timeout_seconds)`, latencia con `perf_counter`,
  `TimeoutError` → `timeout`, `DatabaseUnavailableError` → su `kind`, otra `Exception` → `unexpected_error`;
  comprobación compartida en `state.readiness_task` con `asyncio.shield`, que se libera al terminar; aviso
  solo si cambia) e `info()`. No tiene en cuenta el horario (FR-005).
- [X] T052 [US2] `src/routers/health.py` (después de T041): `public_router = APIRouter(tags=[HEALTH_TAG])` con
  `GET /health/live` (`get_health_live`; **sin dependencias**: devuelve `LiveRead(status="ok")`),
  `GET /health/ready` (`get_health_ready`; 200 con `ReadyRead` o
  `JSONResponse(status_code=503, content=…, headers={"Cache-Control": "no-store"})`; documenta las dos
  respuestas) y `GET /info` (`get_info`); las tres con `Cache-Control: no-store`, descripciones en español que
  dicen «Ruta pública: no exige token» y sin `protected`, `get_bearer_token` ni nada que lea `Authorization`.
- [X] T053 [US2] `src/main.py`: `app.include_router(health.public_router)` en `create_app()`.
- [X] T054 [P] [US2] `Dockerfile` (FR-009, R17): después de `COPY src ./src` y antes de `CMD`, añadir
  `ARG APP_COMMIT_SHA=""`, `ARG APP_BUILD_DATE=""` y
  `ENV APP_COMMIT_SHA=$APP_COMMIT_SHA APP_BUILD_DATE=$APP_BUILD_DATE`, con un comentario que explica que van al
  final para no invalidar la capa de dependencias. `APP_ENVIRONMENT` **no** va en la imagen.
- [X] T055 [US2] Comprobar la imagen del `Dockerfile` (no modifica archivos): `docker build -t maily-system-api:health .` sin
  argumentos y con `--build-arg APP_COMMIT_SHA=$(git rev-parse HEAD) --build-arg APP_BUILD_DATE=<UTC>`;
  `docker run --rm --entrypoint python maily-system-api:health -c "import os; print(os.environ.get('APP_COMMIT_SHA'))"`
  muestra vacío y el SHA, respectivamente.
- [X] T056 [US2] Checkpoint: `uv run pytest tests/contract/test_health_public_api.py tests/unit/test_version.py tests/unit/test_health_service.py tests/contract/test_health_openapi.py tests/contract/test_permission_coverage.py tests/contract/test_openapi_contract.py tests/contract/test_dashboard_openapi.py`
  en verde.

**Checkpoint**: MVP completo (US1 + US2): consulta de salud protegida y contrato v1 propio.

---

## Phase 5: User Story 3 - Registrar componentes sin redesplegar (Priority: P2)

**Goal**: las cinco operaciones de `/api/v1/monitored-components` con permisos `health:*`, protección contra
SSRF (formato estricto y `HEALTH_ALLOWED_HOSTS`), baja lógica con reutilización del código, los dos códigos de
error nuevos y la invalidación de la caché ([R14](research.md#r14-ssrf-y-lista-permitida-fr-025-fr-026-fr-027-sc-004),
[R15](research.md#r15-registro-de-componentes-fr-023-a-fr-032-fr-037)).

**Independent Test**: con la lista permitida configurada, registrar un servicio simulado y verlo en la salud;
modificarlo, deshabilitarlo y eliminarlo comprobando cada efecto en la siguiente consulta; volver a registrar
el código; y obtener 409, 422, 404, 401, 403 y 503 en sus casos.

### Tests for User Story 3 (escribirlas primero; deben fallar) ⚠️

- [X] T057 [P] [US3] `tests/unit/test_monitored_component_dtos.py` (sin base de datos): `MonitoredComponentCreate`
  y `MonitoredComponentUpdate` con las reglas **por campo** de [data-model.md](data-model.md) sección 2
  («`code`: 2 a 50 caracteres; `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`»; «`name`: 1 a 100 caracteres, sin espacios en
  los extremos»; «`kind`: `service` o `frontend`»; «`sort_order`: 0 a 9999»; rutas «hasta 200 caracteres»):
  `code` válidos `ab`, `mailysoft-usuarios`, `a1-b2`, inválidos `a`, `1a`, `a-`, `a--b`, `Ab`, `a_b`, `ñu`,
  51 caracteres; `name` se recorta, vacío o 101 caracteres inválidos; `kind` `database` inválido;
  `base_url` válidas `http://mailysoft-usuarios:8000`, `https://Maily360-production.up.railway.app/` (se
  guarda `https://maily360-production.up.railway.app`), `http://10.0.0.5:8080/api`, `http://[::1]:8000`;
  inválidas `ftp://a`, `http://`, `http://usuario:clave@h`, `http://h/?`, `http://h?x=1`, `http://h/#`,
  `http://h#f`, 256 caracteres, `http://h /x`, `http://h\x`, `http://ñandu.mx`, `http://2130706433`,
  `http://0x7f.1`, `http://h./`, `http://-h`, `http://h:0`, `http://h:65536`, `http://h:abc`; rutas válidas
  `/health/live`, `/healthz/`, `/a:b@c`; inválidas `health`, `//otro-host/x`, `/\otro-host`, `/../admin`,
  `/a/./b`, `/a/..`, `/a?b`, `/a#b`, `/a%2e%2e`, `/a b`, `/a\u0000`, 201 caracteres, `""`; `enabled` y
  `sort_order` inválidos con sus mensajes; un campo desconocido → `extra_forbidden`; en `Update`, `{}` →
  «Hay que enviar al menos un dato para modificar.», `id`, `created_at`, `updated_at` y `deleted_at` →
  `extra_forbidden`, y `code`, `name`, `kind`, `base_url`, `enabled` o `sort_order` en `null` → su mensaje (las
  rutas sí admiten `null`); todos los mensajes son los exactos del catálogo y **ninguno** repite el valor
  recibido (con `http://usuario:clave@h`, el mensaje no contiene `clave`).
- [X] T058 [P] [US3] `tests/unit/test_health_messages.py` (sin base de datos): los dos mensajes nuevos con sus
  textos exactos (`MONITORED_COMPONENT_NOT_FOUND_MESSAGE`, `MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE`);
  `ErrorCode` tiene 17 valores, incluidos `monitored_component_not_found` y
  `monitored_component_code_already_exists`; las excepciones nuevas dan 404, 409 y 422 con su código; cada
  mensaje de validación de la tabla del catálogo sale de `translate_validation_errors(errores, "monitored-components")`
  en su campo (incluido `uuid_parsing` en `component_id` → «El identificador del componente debe ser un
  UUID.»); el recurso `subscriptions` no cambia sus mensajes.
- [X] T059 [US3] Ajustes **A2**, **A3**, **A4** y **A5** (conteo de códigos): en
  `tests/contract/test_openapi_contract.py`, renombrar `test_the_error_codes_are_the_fifteen_of_the_catalog` a
  `test_the_error_codes_are_the_seventeen_of_the_catalog` y comprobar `len(ErrorCode) == 17`; en
  `tests/contract/test_dashboard_openapi.py` y `tests/unit/test_dashboard_messages.py`, `test_no_error_code_was_added`
  → `len(ErrorCode) == 17` con el comentario `# spec 005 added 2 registry codes; reviewed, no dashboard impact`;
  en `tests/unit/test_error_messages.py`, renombrar `test_the_error_codes_are_exactly_the_fifteen_of_the_catalog`
  a `…_seventeen_…` y añadir los dos códigos al conjunto. Nada más cambia.
- [X] T060 [P] [US3] `tests/unit/test_monitored_component_service.py` (sin base de datos; repositorio doble,
  `HealthState` real y `HealthConfig` de prueba): `apply_kind_rules` (servicio sin rutas → valores por defecto;
  servicio con una ruta en `null` → error en ese campo; frontend sin `live_path` o con `null` → error en
  `live_path`; frontend con `ready_path` → error en `ready_path`; `info_path` opcional); `create`: host fuera de
  la lista (o lista vacía) → `MonitoredComponentDataError` en `base_url` **antes** de tocar el repositorio;
  `maily-system-api` o `database` → 409 sin tocar el repositorio; `UniqueViolationError` del índice → 409; solo
  un alta exitosa invalida (`generation` + 1); `update`: `base_url` enviada se comprueba antes de bloquear;
  `lock_current` vacío → 404; frontend con `ready_path` guardada sin enviar `null` → 422 en `ready_path` y
  `rollback`; frontend → servicio sin rutas enviadas → valores por defecto; código reservado → 409 después del
  404; repetido → 409; solo una modificación exitosa invalida; `delete`: `soft_delete` falso → 404,
  verdadero → invalida; `get` inexistente → 404 con el identificador en el mensaje.
- [X] T061 [US3] `tests/integration/test_monitored_component_repository.py` (después de T020): `create` devuelve
  la fila con `id` UUID, `enabled` `true`, `sort_order` 0 y fechas; un `code` repetido entre vigentes →
  `UniqueViolationError` con `constraint_name == MONITORED_COMPONENT_CODE_INDEX`; tras `soft_delete`, el mismo
  `code` se registra con otro `id`; dos altas simultáneas con el mismo `code` (dos sesiones y
  `asyncio.gather`) → una sola fila; `list_current` incluye deshabilitados, excluye eliminados y ordena con
  `COLLATE "C"`; `get_current` y `lock_current` no ven eliminados; `lock_current` bloquea la fila (otra sesión
  con `SET lock_timeout = '200ms'` no puede bloquearla hasta el `commit`); `update` mueve `updated_at` (dos
  transacciones) y devuelve `None` sobre un eliminado; `soft_delete` devuelve `False` la segunda vez; las
  restricciones rechazan un servicio sin `ready_path` (`monitored_components_service_paths_check`), un frontend
  con `ready_path`, el código `database`, un nombre con espacios en los extremos y `sort_order` 10 000 (SQLSTATE
  23514, con `assert_pg_error`).
- [X] T062 [P] [US3] `tests/contract/test_monitored_components_api.py` (con `health_api`): escenarios 1 a 12 de
  la historia 3: alta 201 con `Location`, rutas por defecto, `enabled` `true`, `sort_order` 0 y fechas `…Z`,
  y aparece en la siguiente consulta de salud **aunque** `cache_seconds=15` (invalidación); 409 con código
  repetido y con `database`; 422 en `base_url` (host no permitido —el mensaje no contiene la dirección ni la
  lista—, credenciales, query, fragmento, `ftp`), en rutas tramposas, en un frontend con `ready_path`, con un
  campo desconocido y en una modificación vacía; un frontend sin `ready_path` se acepta; deshabilitar lo saca
  de la salud y de las llamadas pero sigue en el listado; habilitar lo devuelve; baja 204, después 404 al
  consultarlo, modificarlo o eliminarlo, y desaparece de la salud; el `code` se reutiliza con otro `id`; 404
  con un UUID inexistente; 422 en `component_id` con un identificador que no es UUID; con solo `health:read`,
  registrar con datos inválidos → **403**; el listado llega sin envoltorio, con habilitados y deshabilitados,
  en orden; ninguna llamada a componentes lleva el token; dos altas simultáneas → una 201 y una 409; un cambio
  de `base_url` vuelve a comprobar la lista; pasar `kind` a `frontend` sin enviar `ready_path: null` → 422.
- [X] T063 [US3] Ajuste **A1** (parte de US3) en `tests/contract/test_permission_coverage.py`: añadir a
  `EXPECTED_PERMISSIONS` y `REQUESTS` `list_monitored_components` (`GET /api/v1/monitored-components`),
  `get_monitored_component` (`GET …/{COMPONENT_ID}`), `create_monitored_component` (`POST` con
  `{"code": "nuevo", "name": "Nuevo", "kind": "service", "base_url": "http://components.test/healthy"}`),
  `update_monitored_component` (`PATCH …/{COMPONENT_ID}` con `{"name": "Cambio"}`) y
  `delete_monitored_component` (`DELETE …/{COMPONENT_ID}`), con
  `COMPONENT_ID = "00000000-0000-4000-8000-000000000001"`; la fixture `seeded` inserta también ese componente
  (`insert_component` de `tests/health_support.py`); `snapshot` añade las filas de `monitored_components`
  (`id, code, name, enabled, deleted_at, updated_at`). Quedan **13** operaciones.
- [X] T064 [US3] `tests/contract/test_health_openapi.py` (después de T049): las cinco operaciones del registro
  con su ruta y método de FR-001, `tags == ["Salud"]`, `BearerAuth`, su `x-required-permission` y su texto de
  permiso, las respuestas de FR-001 (500 y 503 incluidos), `Location` en el 201, cuerpos `ErrorResponse` en los
  errores, `MonitoredComponentCreate` y `MonitoredComponentUpdate` con `additionalProperties: false`,
  `MonitoredComponentRead` sin `deleted_at` y `component_id` con `format: uuid`; `ErrorCode` con 17 valores.

### Implementation for User Story 3

- [X] T065 [P] [US3] `src/messages.py` (cumple parte de T058): `ErrorCode.MONITORED_COMPONENT_NOT_FOUND` y
  `ErrorCode.MONITORED_COMPONENT_CODE_ALREADY_EXISTS`; `MONITORED_COMPONENT_NOT_FOUND_MESSAGE` y
  `MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE`; las constantes públicas de los mensajes de validación que
  lanzan los validadores (código, nombre, tipo, dirección, host no permitido, ruta, rutas por `kind`, `enabled`,
  orden, modificación vacía e identificador) con los textos exactos del catálogo; y
  `VALIDATION_MESSAGES["monitored-components"]` para los tipos nativos de Pydantic (`name` `required`,
  `too_long`, `not_text`; `enabled` y `sort_order` `invalid`; `component_id` `invalid`). Actualizar el docstring
  (los textos salen de `specs/005-health-monitoring/contracts/error-catalog.md`).
- [X] T066 [US3] `src/exceptions.py` (después de T065): `MonitoredComponentNotFoundError(component_id)` (404),
  `MonitoredComponentCodeAlreadyExistsError(code)` (409) y `MonitoredComponentDataError(errors)` (422,
  `ErrorCode.VALIDATION_ERROR`, guarda los errores en el formato de Pydantic: `type`, `loc`, `ctx` con el
  `ValueError` del mensaje).
- [X] T067 [US3] `src/error_handlers.py` (después de T066): añadir `"uuid_parsing": "invalid"` y
  `"uuid_type": "invalid"` a `_KINDS` y un manejador para `MonitoredComponentDataError` que responde 422 con
  `ErrorResponse(code=VALIDATION_ERROR, message=VALIDATION_ERROR_MESSAGE, errors=translate_validation_errors(error.errors, "monitored-components"))`;
  registrarlo en `register_error_handlers` (más específico que `AppError`). Nada más cambia.
- [X] T068 [P] [US3] `src/dtos/monitored_component.py` (cumple T057): `MonitoredComponentCreate` (`extra="forbid"`,
  `str_strip_whitespace=True`; `code`, `name` con `min_length=1, max_length=100`, `kind: Literal["service", "frontend"]`
  con validador `mode="before"`, `base_url`, `live_path`, `ready_path`, `info_path: str | None = None`,
  `enabled: bool = True`, `sort_order: int = Field(0, ge=0, le=9999)`), `MonitoredComponentUpdate` (todos
  opcionales, `model_validator` «al menos uno», validadores que rechazan `null` salvo en las rutas) y
  `MonitoredComponentRead` (`from_attributes=True`; `id: UUID`, fechas `AwareDatetime` en UTC; sin
  `deleted_at`). Funciones puras `validate_base_url(value) -> str` (reglas de R14 con `valid_host` de
  `src/config.py`; normaliza esquema y host a minúsculas y quita la barra final) y `validate_path(value) -> str`
  (`^/[A-Za-z0-9\-._~!$&'()*+,;=:@/]*$`, sin `//`, sin segmentos `.` ni `..`, hasta 200), que lanzan
  `ValueError` con el mensaje exacto. Las reglas que dependen de `kind` **no** van aquí (las aplica el Service).
  Descripciones y ejemplos en español.
- [X] T069 [US3] `src/repositories/monitored_component_repository.py` (cumple T061; después de T021):
  `list_current()`, `get_current(component_id)`, `create(values)` (`insert … returning id` con
  `execute_and_commit` y recarga; el código repetido sale como `UniqueViolationError`), `lock_current(component_id)`
  (`SELECT … FOR UPDATE` sin `commit`), `update(component_id, changes)` (`UPDATE … WHERE id AND deleted_at IS NULL RETURNING id`
  con `execute_and_commit` y recarga con `populate_existing`), `soft_delete(component_id)`
  (`deleted_at = CURRENT_TIMESTAMP`, atómico) y `rollback()`. Sin reglas de negocio.
- [X] T070 [US3] `src/services/monitored_component_service.py` (cumple T060; depende de T066, T068 y T069):
  `SERVICE_DEFAULT_PATHS`; `apply_kind_rules(values, sent) -> dict` (tabla de [data-model.md](data-model.md)
  sección 3; lanza `MonitoredComponentDataError` en el campo afectado); `MonitoredComponentService(repository,
  state, config)`: `list()`, `get(id)` (404), `create(data)` (lista permitida con `config.allowed_hosts` →
  422 en `base_url`; reglas por `kind` con `data.model_fields_set`; `RESERVED_CODES` → 409; repositorio; índice
  → 409; `state.invalidate()`), `update(id, data)` (lista permitida si llega `base_url`; `lock_current` → 404;
  fusión con la fila; reglas por `kind` sobre el resultado con lo enviado; `rollback` si falla; reservado →
  409; `update`; índice → 409; invalida) y `delete(id)` (404 o invalida). Nunca invalida si algo falla.
- [X] T071 [US3] `src/dependencies.py` (después de T040): `async get_monitored_component_repository(session=Depends(get_session))`
  y `async get_monitored_component_service(repository, state=Depends(get_health_state), config=Depends(get_health_config))`.
- [X] T072 [US3] `src/routers/monitored_components.py` (nuevo; depende de T068 y T071):
  `MONITORED_COMPONENTS_PATH`, `router = APIRouter(prefix=MONITORED_COMPONENTS_PATH, tags=[HEALTH_TAG])` y las
  cinco operaciones con `operation_id`, `response_model`, resúmenes, descripciones (con «Permiso requerido:
  `health:…`.»), ejemplos en español y `**protected(...)` con las respuestas de FR-001
  ([contracts/openapi-health.yaml](contracts/openapi-health.yaml)): listado; consulta; alta 201 con
  `Location: {MONITORED_COMPONENTS_PATH}/{id}`; modificación 200; baja 204 (`Response(status_code=204)`).
  `component_id: UUID` como parámetro de ruta.
- [X] T073 [US3] `src/main.py`: `app.include_router(monitored_components.router)` en `create_app()`.
- [X] T074 [US3] Checkpoint: `uv run pytest tests/unit/test_monitored_component_dtos.py tests/unit/test_health_messages.py tests/unit/test_monitored_component_service.py tests/unit/test_error_messages.py tests/unit/test_dashboard_messages.py tests/integration/test_monitored_component_repository.py tests/contract/test_monitored_components_api.py tests/contract/test_health_openapi.py tests/contract/test_openapi_contract.py tests/contract/test_dashboard_openapi.py tests/contract/test_permission_coverage.py tests/unit/test_layering.py`
  en verde.

**Checkpoint**: US1, US2 y US3 funcionan: el registro se administra sin redesplegar y la salud lo refleja.

---

## Phase 6: User Story 4 - La base de datos detenida por horario no se reporta como caída (Priority: P2)

**Goal**: las variables `DATABASE_SCHEDULE_*` (las cuatro o ninguna) se validan al arrancar, y una falla de la
base fuera de la ventana `[inicio, fin)` local es `stopped` con su `next_start_at`, con el cambio de horario de
verano resuelto ([R12](research.md#r12-horario-de-la-base-de-datos-y-next_start_at-fr-033-fr-034-fr-035-fr-044-sc-003-sc-013)).

**Independent Test**: con lunes a viernes de 08:00 a 20:00 en America/Mexico_City y un reloj controlable, la base
sin responder un martes a las 21:00, un sábado a las 10:00 y un martes a las 10:00 da `stopped` (miércoles
08:00), `stopped` (lunes 08:00) y `down` sin próximo encendido; respondiendo un domingo, `up`; sin horario,
`down`; con un horario incompleto o inválido, el servicio no arranca.

### Tests for User Story 4 (escribirlas primero; deben fallar) ⚠️

- [X] T075 [P] [US4] `tests/unit/test_health_schedule.py` (sin base de datos; horario de lunes a viernes,
  08:00–20:00, America/Mexico_City): parametrizada con los casos verificados en R12: martes
  `2026-10-28T03:00:00Z` (21:00) fuera → `2026-10-28T14:00:00Z`; martes `2026-10-27T16:00:00Z` (10:00) dentro;
  viernes 19:30 local (`2026-10-24T01:30:00Z`, ya sábado en UTC) dentro; 20:00 en punto fuera y 08:00 en
  punto dentro; viernes 21:00 (`2026-10-24T03:00:00Z`) → `2026-10-26T14:00:00Z`; viernes 23 de octubre de
  2026 a las 21:15 (`2026-10-24T03:15:00Z`) → `2026-10-26T14:00:00Z`; sábado 10:00 → lunes 14:00 Z; antes de
  las 08:00 de un martes → ese martes 14:00 Z; con America/Tijuana, viernes 30 de octubre de 2026 a las 21:00
  (UTC−7) → `2026-11-02T16:00:00Z`; con solo domingo de 02:30 a 05:00 en Tijuana, una falla del sábado 13 de
  marzo de 2027 → `2027-03-14T10:00:00Z` (instante del salto) y con 01:30 a 05:00, del sábado 6 de noviembre
  de 2027 → `2027-11-07T08:30:00Z` (la primera); el resultado es siempre posterior al instante y en UTC.
- [X] T076 [US4] `tests/unit/test_health_settings.py` (después de T006): `database_schedule_from` con las cuatro
  variables válidas → `DatabaseSchedule` (días sin distinguir mayúsculas y con espacios alrededor de las comas);
  con ninguna → `None`; con cualquier subconjunto de una a tres → `InvalidSettingsError` cuyas `variables` son
  las que faltan; zona `Mars/Olympus` o `../x`, día `Lunes`, día repetido, entrada vacía (`Monday,,Friday`),
  hora `8:00`, `24:00`, `20:5`, `2000` o `20:60`, e inicio igual o posterior al fin → `InvalidSettingsError`
  que nombra la variable; `configuration_error_message(error_de_pydantic, invalid_variables=("DATABASE_SCHEDULE_DAYS",))`
  nombra las dos en un solo mensaje y nunca los valores; `health_config_from` entrega el horario.
- [X] T077 [US4] `tests/unit/test_health_startup.py` (después de T007): con solo `DATABASE_SCHEDULE_TIMEZONE`
  el servicio no arranca y el mensaje nombra las tres que faltan sin mostrar `America/Mexico_City`; con el
  horario completo y válido arranca; con `HEALTH_CACHE_SECONDS=301` y un horario incompleto, un solo mensaje
  nombra las dos causas.
- [X] T078 [US4] `tests/unit/test_health_service.py` (después de T046): con el horario por defecto, un
  `FakeClock` y un *pinger* que falla con `connection_error`: martes 21:00 → `database` `stopped`, `error`
  `connection_error`, `next_start_at` `2026-10-28T14:00:00Z`, `maily-system-api` `degraded` y estado global no
  peor que `degraded` (sin otros caídos); martes 10:00 → `down`, `next_start_at` `None` y global `down`;
  domingo con la base respondiendo → `up`; sin horario → `down` a cualquier hora; `next_start_at` es `None` en
  todos los demás componentes; un resultado en caché conserva su `next_start_at`.
- [X] T079 [US4] `tests/contract/test_health_api.py` (después de T032): por HTTP, con el horario en la
  configuración (`set_config(schedule=…)`), el reloj en viernes 21:00 de la Ciudad de México y un *pinger* que
  falla: `database` `stopped` con `next_start_at` `2026-10-26T14:00:00Z`; con el reloj en martes 10:00, `down`
  y `null`.

### Implementation for User Story 4

- [X] T080 [US4] `src/config.py` (cumple T076; después de T010): campos `database_schedule_timezone`,
  `database_schedule_days`, `database_schedule_start` y `database_schedule_end` (`str | None = None`) en
  `HealthSettings`; `class InvalidSettingsError(Exception)` con `variables: tuple[str, ...]`;
  `database_schedule_from(settings)` (las cuatro o ninguna; zona con `ZoneInfo` —`ZoneInfoNotFoundError` o
  `ValueError` → inválida—; días en inglés completos sin repetir; `^([01]\d|2[0-3]):[0-5]\d$`; inicio < fin;
  nombra las variables, nunca los valores); `health_config_from` añade `schedule`; y
  `configuration_error_message(*errors, invalid_variables=())` añade «La variable de entorno X no es válida.»
  o «Falta la variable de entorno X.» por cada nombre, con el encabezado una sola vez. Las llamadas actuales no
  cambian.
- [X] T081 [US4] `src/main.py` (cumple T077; después de T016): el `lifespan` llama también a
  `database_schedule_from(get_health_settings())`, recoge `InvalidSettingsError` junto con los
  `ValidationError` y pasa sus variables a `configuration_error_message`; el cliente de chequeos usa
  `health_config_from` ya con el horario.
- [X] T082 [P] [US4] `src/services/health_schedule.py` (cumple T075; funciones puras): `in_window(schedule, instant)`
  y `next_start(schedule, instant)` con el algoritmo de R12 (fechas locales hasta 8 días; `fold=0`; hueco
  detectado porque el instante no vuelve a la misma hora local y resuelto por bisección al segundo hasta el
  primer instante con el desfase nuevo). Docstring con el porqué (runbook `Deploy-PgAutoShutdown.ps1`).
- [X] T083 [US4] `src/services/health_service.py` (cumple T078; después de T051): `_database_component` aplica
  el horario con `in_window`/`next_start` y el `now()` del reloj al terminar la consulta: sin horario o dentro
  de la ventana → `down` y `next_start_at` `None`; fuera → `stopped`, `error` = causa observada y
  `next_start_at` = `next_start(...)`. `/health/ready` no cambia (FR-005).
- [X] T084 [US4] Checkpoint: `uv run pytest tests/unit/test_health_schedule.py tests/unit/test_health_settings.py tests/unit/test_health_startup.py tests/unit/test_health_service.py tests/contract/test_health_api.py`
  en verde.

**Checkpoint**: US1 a US4 funcionan: de noche la base aparece «detenida por horario» con su próximo encendido.

---

## Phase 7: User Story 6 - Ver el estado de la plataforma sin iniciar sesión (Priority: P2)

**Goal**: `GET /health/status`, público, siempre 200, con la lista cerrada de campos de FR-047, desde el mismo
resultado y caché que la consulta de salud y con un periodo mínimo de `max(HEALTH_CACHE_SECONDS, 15)` segundos
(FR-045 a FR-048). Depende de US1; con US4, su `next_start_at` tiene valor de noche.

**Independent Test**: sin token, con el API de usuarios caído, el horario por defecto y el reloj en el viernes 23
de octubre de 2026 a las 21:15 de la Ciudad de México y la base sin responder, responde 200 con `database`
`stopped` y su próximo encendido, solo con los campos permitidos; sin deshabilitados; con el registro ilegible,
con la copia; 100 peticiones dentro del periodo → una ronda; sin horario, `next_start_at` `null`.

### Tests for User Story 6 (escribirlas primero; deben fallar) ⚠️

- [X] T085 [P] [US6] `tests/contract/test_health_public_api.py` (después de T044): (a) `GET /health/status` sin
  token, con `users_fault("unavailable")`, responde 200 con `no-store` y la falla del API de usuarios **no** se
  consume (ninguna consulta de permisos); (b) con `Authorization` válida o no, la misma respuesta y ninguna
  consulta; (c) escenario 6-1: horario por defecto, reloj en `2026-10-24T03:15:00Z`, *pinger* que falla →
  `database` `stopped` con `next_start_at` `2026-10-26T14:00:00Z`, `maily-system-api` `degraded` y global
  `degraded`; (d) un deshabilitado y un eliminado no aparecen y el resto sale en el mismo orden y estado que en
  `GET /api/v1/health`; (e) sin horario, `database` `down` y `next_start_at` `null`; (f) CORS como en T044 (h)
  para `/health/status`.
- [X] T086 [P] [US6] `tests/contract/test_health_public_fields.py` (con `health_api`; SC-014): con componentes en
  todos los estados (`up`, `degraded`, `down`, `stopped`, `unknown`) y con versiones, chequeos y errores en el
  resultado de salud, la respuesta pública tiene **exactamente** las claves `status`, `checked_at` y
  `components`, y cada componente exactamente `code`, `name`, `kind`, `status` y `next_start_at`; el cuerpo no
  contiene `components.test`, `latency`, `version`, `checks`, `registry_available`, `1.4.2` ni ningún código de
  error.
- [X] T087 [US6] `tests/unit/test_health_service.py` (después de T078): `public_status()` con `cache_seconds=0`:
  100 llamadas dentro de 15 s (reloj monótono controlado) → **una** agregación y el mismo `checked_at`; a los
  15 s exactos, otra; reutiliza un resultado que produjo `health()`; una consulta autenticada puede adelantar la
  siguiente ronda y las públicas no; tras `invalidate()`, la pública lanza una; una pública se une a una
  agregación en curso aunque sea de la generación anterior y ese resultado no se guarda; 1 000 llamadas
  repartidas en 60 s simulados → a lo más 4 agregaciones (SC-016); con la base y el registro sin responder, la
  respuesta llega en menos de 2 × `check_timeout_seconds` + 0,5 s (SC-015).
- [X] T088 [US6] Ajuste **A1** (parte de US6) en `tests/contract/test_permission_coverage.py`: `PUBLIC_ROUTES`
  suma `/health/status` (**8** rutas públicas).
- [X] T089 [US6] `tests/contract/test_health_openapi.py` (después de T064): `get_health_status` en
  `GET /health/status`, `tags == ["Salud"]`, sin `security` ni `x-required-permission`, solo 200 con
  `Cache-Control` y el esquema `PublicStatusRead`; `PublicStatusRead` y `PublicComponentRead` con exactamente
  sus campos; la descripción dice que no es una *probe*.

### Implementation for User Story 6

- [X] T090 [US6] `src/dtos/health.py` (después de T050): `PublicComponentRead` (`code`, `name`, `kind`,
  `status`, `next_start_at`) y `PublicStatusRead` (`status`, `checked_at`, `components`), con
  `model_config = ConfigDict(extra="forbid")` y descripciones que dicen que la lista de campos es cerrada.
- [X] T091 [US6] `src/services/health_service.py` (después de T083): `PUBLIC_MIN_CACHE_SECONDS = 15` y
  `async public_status()` = `current_result(max_age=max(config.cache_seconds, 15), accept_stale_in_flight=True)`
  (une a cualquier agregación en curso y no guarda la de una generación vieja). `current_result` recibe ese
  parámetro por palabra clave; `health()` no cambia.
- [X] T092 [US6] `src/routers/health.py` (después de T052): `GET /health/status` en `public_router`
  (`get_health_status`, `response_model=PublicStatusRead`, `Cache-Control: no-store`, sin dependencias de
  seguridad; descripción en español de [contracts/openapi-health.yaml](contracts/openapi-health.yaml), con «No
  es una *probe*»); arma el DTO **campo por campo** desde el `HealthResult`.
- [X] T093 [US6] Checkpoint: `uv run pytest tests/contract/test_health_public_api.py tests/contract/test_health_public_fields.py tests/unit/test_health_service.py tests/contract/test_health_openapi.py tests/contract/test_permission_coverage.py tests/contract/test_openapi_contract.py tests/contract/test_dashboard_openapi.py`
  en verde.

**Checkpoint**: US1, US2, US3, US4 y US6 funcionan: el estado público se ve sin sesión.

---

## Phase 8: User Story 5 - Seguir informando cuando la base de datos o el registro no responden (Priority: P3)

**Goal**: la copia del registro en memoria (por proceso, sin caducidad) se usa cuando la lectura falla, con
`registry_available: false`, y las operaciones del registro fallan sin cambiar nada con la base caída
([R11](research.md#r11-copia-del-registro-en-memoria-fr-036-sc-009), FR-037). Depende de US1 (agregación) y, para
FR-037, de US3.

**Independent Test**: consultar una vez con la base disponible; hacer que la lectura del registro falle y volver
a consultar: los mismos registrados, consultados de verdad, con `registry_available: false`; con la lectura
fallando desde el arranque, solo los integrados; al restablecerla, `true` y la copia al día.

### Tests for User Story 5 (escribirlas primero; deben fallar) ⚠️

- [X] T094 [US5] `tests/unit/test_health_service.py` (después de T087): lectura buena y luego fallida → los
  componentes de la copia, chequeados de verdad, y `registry_available` `False`; nunca leída → solo integrados y
  `False`; lectura vacía → `True` y la copia queda vacía; la lectura vuelve → `True` y la copia nueva refleja
  los cambios; lectura que no termina → la copia, y la agregación dura menos de 2 × `check_timeout_seconds` +
  0,5 s; la copia guarda `ComponentTarget` (no objetos ORM) y una falla de lectura registra un `WARNING` sin
  detalles.
- [X] T095 [P] [US5] `tests/contract/test_health_api.py` (después de T079): por HTTP, tras una consulta buena,
  `use(get_registry_reader, …)` con un lector que lanza → 200, `registry_available` `false` y los mismos
  registrados (la simulación recibió sus llamadas); una app nueva con el lector fallando desde el inicio →
  solo integrados; lector fallando con la base respondiendo → `database` `up` y `false`; con US6,
  `/health/status` también usa la copia y nunca trae `registry_available`.
- [X] T096 [P] [US5] `tests/contract/test_monitored_components_api.py` (después de T062): con
  `get_monitored_component_repository` sustituido por uno cuya sesión lanza `sqlalchemy.exc.OperationalError`,
  alta, modificación y baja responden 500 `internal_error` con el mensaje genérico y sin detalles; la
  generación de la caché no cambia; `GET /api/v1/health` sigue en 200.

### Implementation for User Story 5

- [X] T097 [US5] `src/services/health_service.py` (cumple T094; después de T091): en la lectura del registro,
  una lectura buena reemplaza `state.registry_snapshot` por la tupla de `ComponentTarget` (también vacía) y da
  `registry_available` `True`; una falla o un tiempo agotado usa la copia (o solo los integrados si es `None`)
  y da `False`, con el aviso de la tabla de constantes. Para FR-037 no hace falta código nuevo: comprobar que
  `MonitoredComponentService` no invalida si el repositorio falla (lo cubre T096).
- [X] T098 [US5] Checkpoint: `uv run pytest tests/unit/test_health_service.py tests/contract/test_health_api.py tests/contract/test_monitored_components_api.py tests/contract/test_health_public_api.py`
  en verde.

**Checkpoint**: Las seis historias funcionan de forma independiente.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Colección de Postman y su pila, la cobertura conjunta de colecciones (A6), Compose, documentación y
la validación final.

- [X] T099 [P] Ajuste **A8** en `tests/postman/docker-compose.e2e.yml`: servicio `components-stub` (imagen del
  proyecto, `uvicorn app:app --app-dir /stub --host 0.0.0.0 --port 8080`, volumen `./tests/stubs/components:/stub:ro`,
  puerto `127.0.0.1:${E2E_COMPONENTS_STUB_PORT:-8014}:8080` y el mismo `healthcheck` de las otras simulaciones
  con `/__test__/calls`); la `api` depende de él (`service_healthy`) y recibe
  `HEALTH_ALLOWED_HOSTS: components-stub,missing-service.invalid`, `HEALTH_CHECK_TIMEOUT_SECONDS: "2"` y
  `HEALTH_CACHE_SECONDS: "0"`; actualizar el comentario de la cabecera (tres simulaciones).
- [X] T100 [P] Ajuste **A9** en `tests/postman/environments/e2e.postman_environment.json`: añadir
  `{"key": "componentsStubUrl", "value": "http://127.0.0.1:8014", "type": "default", "enabled": true}`.
- [X] T101 [P] `tests/contract/postman_support.py` (aditivo): `HEALTH_COLLECTION = POSTMAN / "collections" / "MailySoft-System-Salud.postman_collection.json"`,
  `HEALTH_HELPER_PREFIXES = {"setup", "docs"}`, `HEALTH_PATH_PREFIXES = ("/health/", "/info", "/api/v1/health", "/api/v1/monitored-components")`
  y `health_operation_ids() -> set[str]` (operaciones del OpenAPI cuya ruta empieza con alguno de esos
  prefijos). Nada existente cambia.
- [X] T102 `tests/postman/collections/MailySoft-System-Salud.postman_collection.json` (**colección nueva**,
  v2.1): exactamente las carpetas, peticiones, script previo, tokens y comprobaciones de
  [contracts/e2e-collection.md](contracts/e2e-collection.md) (0. Preparación, 1. Contrato de salud (público),
  2. Registro, 3. Componentes caídos, 4. Errores del registro y 5. Control de acceso); autenticación Bearer
  `{{accessToken}}`; ningún token escrito; los nombres `<operationId>: <descripción>`; las comprobaciones con
  `pm.response.to.have.status(…)` y los mensajes exactos del catálogo.
- [X] T103 `tests/contract/test_health_postman_collection.py` (depende de T101 y T102): reglas **G1 a G8** de
  [contracts/e2e-collection.md](contracts/e2e-collection.md), cada una como `check_*(...) -> list[str]` (mismo
  estilo que `test_dashboard_postman_collection.py`), con `ALLOWED_TOKENS = {"{{readerToken}}", "{{plainToken}}", "{{subscriptionsToken}}", "{{badToken}}"}`
  y los estatus `200, 201, 204, 401, 403, 404, 409, 422, 503`; la colección real pasa todas y cada regla detecta
  su falla en una copia alterada en memoria; además, la colección tiene las seis carpetas de la tabla.
- [X] T104 Ajuste **A6** en `tests/contract/test_dashboard_postman_collection.py` (depende de T101 y T102):
  `prefixes_of_the_three` pasa a `prefixes_of_the_collections` y añade `"health": operation_prefixes(load_json(HEALTH_COLLECTION), HEALTH_HELPER_PREFIXES)`;
  `test_g9_the_three_collections_together_cover_exactly_the_operations_of_the_api` se renombra a
  `test_g9_the_four_collections_together_cover_exactly_the_operations_of_the_api`;
  `test_g9_detects_an_operation_that_no_collection_covers` usa la función renombrada. Las reglas G1–G8 del
  dashboard no cambian. Con esto G9 vuelve a verde.
- [X] T105 [P] Ajuste **A10** en `tests/postman/package.json`: script
  `"e2e:health": "newman run collections/MailySoft-System-Salud.postman_collection.json -e environments/e2e.postman_environment.json -r cli,junit --reporter-junit-export reports/junit-health.xml --timeout-request 15000"`
  y `"e2e:all": "npm run e2e && npm run e2e:dashboard && npm run e2e:health"`; `e2e` y `e2e:dashboard` no cambian.
- [X] T106 [P] `docker-compose.yml` (FR-038, R17): el servicio `api` pasa a `build: {context: ., args: {APP_COMMIT_SHA: "${APP_COMMIT_SHA:-}", APP_BUILD_DATE: "${APP_BUILD_DATE:-}"}}`
  y en `environment` añade, con comentarios en español, `HEALTH_CHECK_TIMEOUT_SECONDS`, `HEALTH_CACHE_SECONDS`,
  `HEALTH_READY_TIMEOUT_SECONDS`, `HEALTH_ALLOWED_HOSTS`, las cuatro `DATABASE_SCHEDULE_*` y `APP_ENVIRONMENT`
  como `${VARIABLE:-}` (vacías = por defecto). **No** pone `APP_COMMIT_SHA` ni `APP_BUILD_DATE` en
  `environment` (taparían el valor de la imagen).
- [X] T107 [P] `.env.example`: bloque «Salud de servicios» con las once variables comentadas, sus valores
  admitidos y su valor por defecto ([data-model.md](data-model.md) sección 7), los valores del runbook para el
  horario y la nota de que conviene listar hosts exactos (un sufijo de una plataforma compartida, como
  `.up.railway.app`, admitiría aplicaciones de terceros).
- [X] T108 [P] `README.md`: en «Qué incluye hoy», la sección «Salud de servicios» con las diez operaciones
  (tabla con permiso o «pública»), qué es cada ruta, que `/health/status` **no** es una *probe*, el registro
  sin redespliegue, la lista permitida, el horario alineado con `Deploy-PgAutoShutdown.ps1` y la relación de
  tiempos (`ready` 2 s < agregador 3 s); filas nuevas en la tabla de «Configuración»; cómo construir la imagen
  con `--build-arg APP_COMMIT_SHA=… --build-arg APP_BUILD_DATE=…`; el ejemplo de *probes* de Kubernetes de la
  sección «Documentación y despliegue» de [plan.md](plan.md) (liveness y startup a `/health/live`, readiness a
  `/health/ready`, con la explicación de qué pasa con la base detenida); «Pruebas de punta a punta» con la
  colección de salud y «las cuatro colecciones juntas cubren toda la API»; y la estructura.
- [X] T109 Puertas de calidad (no modifica archivos): `docker compose up -d db`; `uv run pytest` **completo** en
  verde (las de T001 más las nuevas); `uv run alembic upgrade head` y `uv run alembic check` sin diferencias;
  `uv run python -c "import json; from src.main import create_app; print(len(json.dumps(create_app().openapi())))"`
  sin errores; las 10 operaciones del OpenAPI generado coinciden con [contracts/openapi-health.yaml](contracts/openapi-health.yaml)
  (ruta, método, `operationId` y permiso); `git status --short` muestra solo los archivos de la estructura de
  [plan.md](plan.md); `.specify/memory/constitution.md` sigue en 1.0.0.
- [X] T110 Pruebas de punta a punta (no modifica archivos): `npm ci --prefix tests/postman`; levantar la pila
  aislada (`docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api`);
  `npm run e2e:all --prefix tests/postman` termina con código 0; desmontar con `down -v`.
- [X] T111 Validar `specs/005-health-monitoring/quickstart.md` (no modifica archivos): niveles 3 y 4 a mano (comprobaciones
  1 a 5 y la imagen con argumentos de build); anotar cualquier diferencia con lo documentado y corregir el
  código o la guía, avisando a la persona si cambia un contrato.
- [X] T112 Revisión final de seguridad y privacidad (no modifica archivos salvo para corregir): buscar en `src/`
  que ningún `logger` reciba URLs, tokens, cuerpos o `str(error)` de una falla de componente; que ninguna
  respuesta de salud tenga un campo de dirección; que el cliente de chequeos sea el único que llama a
  componentes y nunca reciba cabeceras de la petición; y que `tests/postman/` no tenga secretos (lo vigila
  G6).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias; T002 y T003 tocan los mismos archivos (`pyproject.toml`, `uv.lock`) y
  van en orden.
- **Foundational (Phase 2)**: depende de Setup y **bloquea** todas las historias.
- **US1 (Phase 3)** y **US2 (Phase 4)**: dependen de Foundational. US2 usa el `CheckRead` y el `HealthService` de
  US1, así que va después de US1 (las dos son P1 y forman el MVP).
- **US3 (Phase 5)**: depende de US1 (la salud refleja los cambios del registro e invalida su caché).
- **US4 (Phase 6)**: depende de US1 (el componente `database` de la agregación).
- **US6 (Phase 7)**: depende de US1; con US4 muestra `next_start_at` de noche.
- **US5 (Phase 8)**: depende de US1 y, para FR-037, de US3.
- **Polish (Phase 9)**: depende de todas las historias (la colección cubre las diez operaciones).

### User Story Dependencies

```text
Setup → Foundational → US1 ─┬─→ US2
                             ├─→ US3 ─┐
                             ├─→ US4   ├─→ US5
                             └─→ US6 ──┘ (US6 y US5 solo necesitan US1; US5 usa US3 para FR-037)
                                          → Polish
```

### Archivos compartidos (límite real del paralelismo)

Estos archivos los tocan varias tareas, que deben ir **en orden** aunque sean de historias distintas:
`src/main.py` (T011, T016, T042, T053, T073, T081), `src/config.py` (T010, T080), `src/dependencies.py` (T024,
T040, T071), `src/services/health_service.py` (T039, T051, T083, T091, T097), `src/routers/health.py` (T041,
T052, T092), `src/dtos/health.py` (T038, T050, T090), `src/integrations/health_probe.py` (T015, T037),
`src/repositories/monitored_component_repository.py` (T021, T069), `tests/unit/test_health_service.py` (T031,
T046, T078, T087, T094), `tests/contract/test_health_api.py` (T032, T079, T095),
`tests/contract/test_health_public_api.py` (T044, T085), `tests/contract/test_health_openapi.py` (T035, T049,
T064, T089), `tests/contract/test_monitored_components_api.py` (T062, T096), `tests/unit/test_health_settings.py`
(T006, T076), `tests/unit/test_health_startup.py` (T007, T077), `tests/health_support.py` (T026, T031),
`tests/integration/test_monitored_component_repository.py` (T020, T061) y
`tests/contract/test_permission_coverage.py` (T034, T047, T063, T088).

### Within Each User Story

- Las pruebas se escriben primero y deben fallar; después, la implementación que las cumple.
- Mensajes y excepciones antes que DTOs y Services; Repositories antes que Services; Services antes que
  dependencias y Routers; el `include_router` al final; el checkpoint cierra la historia.
- Los ajustes a pruebas existentes de cada historia van en la misma historia que añade lo que reconocen.

### Parallel Opportunities

- Setup: T004 en paralelo con T002 y T003.
- Foundational: las pruebas T005 a T009 en paralelo; después T011 a T015, T017, T019, T020, T022, T025 y T026
  en paralelo (archivos distintos); T010 antes de T016 y T024; T017 y T018 antes de T021.
- US1: T029 a T033 y T035 en paralelo; T036 y T038 en paralelo; T037 después de T015.
- US2: T044 y T045 en paralelo; T054 en paralelo con todo lo de US2.
- US3: T057, T058, T060 y T062 en paralelo; T065 y T068 en paralelo.
- US4: T075 y T082 en paralelo con lo demás de US4.
- US6: T085 y T086 en paralelo.
- US5: T095 y T096 en paralelo.
- Polish: T099, T100, T101, T105, T106, T107 y T108 en paralelo.

---

## Parallel Example: User Story 1

```text
# Las pruebas de US1, todas a la vez (archivos distintos):
Task: "T029 tests/unit/test_health_contract.py"
Task: "T030 tests/unit/test_health_probe.py"
Task: "T031 tests/unit/test_health_service.py (+ FakeProbe en tests/health_support.py)"
Task: "T032 tests/contract/test_health_api.py"
Task: "T033 tests/contract/test_health_access_control.py"
Task: "T035 tests/contract/test_health_openapi.py"

# Después, en paralelo:
Task: "T036 src/integrations/health_contract.py"
Task: "T038 src/dtos/health.py"
```

## Parallel Example: User Story 3

```text
Task: "T057 tests/unit/test_monitored_component_dtos.py"
Task: "T058 tests/unit/test_health_messages.py"
Task: "T060 tests/unit/test_monitored_component_service.py"
Task: "T062 tests/contract/test_monitored_components_api.py"
# Después:
Task: "T065 src/messages.py"
Task: "T068 src/dtos/monitored_component.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1: Setup (T001 a T004).
2. Phase 2: Foundational (T005 a T028): **crítica**, bloquea todo.
3. Phase 3: US1 (T029 a T043): la consulta de salud protegida.
4. Phase 4: US2 (T044 a T056): el contrato v1 propio y la imagen con su build.
5. **Parar y validar**: los checkpoints T043 y T056, y el nivel 3 del quickstart (comprobaciones 1 y 2).

### Incremental Delivery

1. Setup + Foundational → base lista (la suite completa sigue en verde).
2. US1 → consulta de salud (G9 queda en rojo hasta Polish, por diseño).
3. US2 → *probes* y `/info` (MVP).
4. US3 → registro desde el Backoffice sin redesplegar.
5. US4 → «detenida por horario» con su próximo encendido.
6. US6 → estado público para la pantalla de acceso fallido del Backoffice.
7. US5 → resiliencia con la copia en memoria.
8. Polish → Postman, Compose, README y puertas finales (G9 vuelve a verde).

### Parallel Team Strategy

Con varias personas, después de Foundational y US1: una sigue con US2, otra con US3 y otra con US4; US6 puede
empezar en cuanto termine US1. Hay que coordinar los archivos compartidos de arriba (sobre todo
`src/services/health_service.py` y `src/main.py`).

---

## Trazabilidad requisitos → tareas

| Requisitos | Pruebas | Implementación |
|---|---|---|
| FR-001 a FR-003 (operaciones, públicas, control de acceso) | T033, T034, T047, T062, T063, T085, T088 | T012, T041, T052, T072, T092 |
| FR-004 a FR-008 (contrato v1 propio, versión, reglas comunes) | T044, T045, T046, T049 | T003, T011, T050, T051, T052 |
| FR-009 (Docker y *probes*) | T055 | T054, T108 |
| FR-010 a FR-018 (consulta agregada, campos, depuración, estados, códigos) | T029, T031, T032, T035 | T036, T038, T039, T041 |
| FR-019 a FR-021 (paralelo, caché compartida, llamadas a componentes) | T008, T030, T031, T033, T062 | T015, T037, T039, T070 |
| FR-022 (desviación del Principio IX) | — | Complexity Tracking C1 del plan (aprobada) |
| FR-023 a FR-032 (registro, SSRF, lista permitida, baja lógica, migración) | T005, T009, T020, T057, T060, T061, T062 | T010, T017, T018, T019, T021, T068, T069, T070, T072 |
| FR-033 a FR-035, FR-044 (horario, `stopped`, `next_start_at`) | T075, T076, T077, T078, T079 | T080, T081, T082, T083 |
| FR-036, FR-037 (copia en memoria, base caída) | T094, T095, T096 | T097 |
| FR-038 (configuración) | T006, T007, T076, T077 | T010, T016, T080, T106, T107, T108 |
| FR-039, FR-040 (ajustes, sin regresiones) | T034, T047, T048, T059, T063, T088, T104, T109 | T027 |
| FR-041, FR-042, FR-049 (pruebas y Postman) | T025, T026, T103, T110 | T099 a T102, T105 |
| FR-043 (stack) | T109 | T002 |
| FR-045 a FR-048 (estado público, lista cerrada, periodo mínimo) | T085, T086, T087, T089 | T090, T091, T092 |
| FR-050 (CORS) | T044 (h), T085 (f) | — (middleware vigente, R18) |
| SC-001, SC-005, SC-006 | T032 (b, c, g), T030 (g), T033 | T037, T039 |
| SC-002, SC-004 | T062, T057, T031 (d) | T070 |
| SC-003, SC-013 | T075, T078, T085 (c) | T082, T083 |
| SC-007, SC-008, SC-010 | T044 (a, c), T045, T055, T007, T077 | T051, T016, T081 |
| SC-009, SC-011, SC-012 | T094, T095, T109, T110 | T097 |
| SC-014, SC-015, SC-016 | T086, T087 | T091 |

---

## Notes

- Una tarea con [P] toca archivos distintos y no tiene dependencias abiertas; [USn] da la trazabilidad con la
  historia de la spec.
- Cada historia se puede completar y probar por sí sola en el orden indicado; los checkpoints lo comprueban.
- Verificar que las pruebas fallan antes de implementar.
- No hacer commits salvo que la persona lo pida (convención de esta feature).
- Evitar tareas vagas, conflictos en los archivos compartidos y dependencias entre historias que rompan su
  independencia.

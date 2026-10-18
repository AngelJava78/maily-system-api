---

description: "Task list for feature 001-subscriptions-api (API REST de Suscripciones)"
---

# Tasks: API REST de Suscripciones

**Input**: Design documents from `/specs/001-subscriptions-api/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.0.0** vigente, Docker Desktop con Compose 2.24 o superior, `uv` con Python 3.14 o
superior y, para la pila de punta a punta, Node.js con npm. El repositorio parte **vacío** (solo
`README.md`, `.gitignore` y la configuración de Spec Kit): todo el código es nuevo.

**Tests**: Incluidas. El Principio V las exige. Se sigue TDD dentro de cada historia: las tareas de
pruebas se escriben primero y **deben fallar** antes de implementar (cuando la prueba necesita código que
aún no existe, falla al importarlo; eso cuenta). Cada fase termina con `uv run pytest` en verde.
**Ninguna prueba llama al API de usuarios ni al de clínicas reales**: usan las simulaciones
`tests/stubs/` o dobles en memoria.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). Las dos historias P1 se
construyen en este orden: **US2** (control de acceso, que es la puerta de todas las operaciones) y luego
**US1** (catálogo); después las P2 (US3 crear, US4 consultar, US5 actualizar, US6 cambiar el estatus) y la
P3 (US7 eliminar). El **MVP** es Setup + Foundational + US2 + US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US7); sin etiqueta en Setup, Foundational y
  Polish
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones y evidencia: [research.md](research.md) (R1 a R21)
- Tablas, columnas, restricciones, ciclo de vida del estatus y DTOs: [data-model.md](data-model.md)
- Esquema SQL validado en PostgreSQL 17: [contracts/database-schema.sql](contracts/database-schema.sql)
- Contrato HTTP (OpenAPI 3.1, validado): [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
- Operación → permiso: [contracts/permission-matrix.md](contracts/permission-matrix.md)
- Códigos de error, mensajes exactos y precedencia: [contracts/error-catalog.md](contracts/error-catalog.md)
- Contrato consumido del API de usuarios: [contracts/users-api-integration.md](contracts/users-api-integration.md)
- Contrato consumido (propuesto) del API de clínicas: [contracts/clinics-api-integration.md](contracts/clinics-api-integration.md)
- Simulaciones, pila e2e y colección de Postman: [contracts/e2e-stubs.md](contracts/e2e-stubs.md)
- Guía de validación: [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json` (debe seguir
  en `specs/001-subscriptions-api`); escribir tokens, contraseñas o secretos reales en cualquier
  archivo; añadir dependencias fuera de la tabla del stack de la constitución (p. ej. PyYAML, PyJWT,
  respx).
- **Idioma** (Principio VII): identificadores, campos de la API y códigos de error en inglés; mensajes,
  descripciones de OpenAPI y documentos en español; comentarios y docstrings en inglés.
- **Mensajes exactos**: los textos en español de cada error salen de
  [contracts/error-catalog.md](contracts/error-catalog.md); no se parafrasean.
- **Pruebas**: `docker compose up -d db` y `uv run pytest [ruta]`. La base de pruebas es
  `TEST_DATABASE_URL` y su nombre debe terminar en `_test`. Ninguna prueba necesita las variables
  `USERS_API_*` ni `CLINICS_API_*`.
- **Todo lo que hace I/O es `async`** (Principio III), incluidos los proveedores de `src/dependencies.py`.
- **Constantes** (se definen una sola vez, con nombre, en el módulo que se indica):

  | Constante | Valor | Módulo |
  |---|---|---|
  | `INT4_MAX` | `2_147_483_647` (un identificador mayor «no existe» sin consultar) | `src/repositories/__init__.py` |
  | Estatus | `SubscriptionStatus.ACTIVE = 1`, `INACTIVE = 2`, `BLOCKED = 3`, `DELETED = 4` (`ClassVar[int]`) | `src/models/subscription_status.py` |
  | Índice del nombre | `SUBSCRIPTION_NAME_INDEX = "subscriptions_name_not_deleted_key"` | `src/models/subscription.py` |
  | Tamaño máximo del token | `MAX_TOKEN_BYTES = 8192` (mayor → `invalid_token`, sin llamar al API de usuarios) | `src/services/authorization_service.py` |
  | Permisos | `SUBSCRIPTIONS_READ = "subscriptions:read"`, `SUBSCRIPTIONS_WRITE = "subscriptions:write"`, `SUBSCRIPTIONS_UPDATE = "subscriptions:update"`, `SUBSCRIPTIONS_DELETE = "subscriptions:delete"` | `src/security.py` |
  | Tiempo máximo **total** por llamada a otro API | `USERS_API_TIMEOUT_SECONDS` y `CLINICS_API_TIMEOUT_SECONDS`; por defecto `5.0`; mayor que 0 y no más de 30 | `src/config.py` |
  | Prefijo de rutas | `SUBSCRIPTIONS_PATH = "/api/v1/subscriptions"` | `src/routers/subscriptions.py` |

- **Interfaces compartidas entre tareas** (usar exactamente estos nombres):
  - `src/integrations/errors.py`: `IntegrationError(Exception)` → `UsersApiRejectedToken(code: str)`
    (el código del API de usuarios: `unauthenticated`, `token_expired` o `invalid_token`),
    `UsersApiUnavailable`, `ClinicsApiUnavailable`. Sus mensajes **nunca** incluyen tokens ni cuerpos.
  - `src/integrations/users_api.py`: `UsersApiClient(http_client: httpx.AsyncClient, base_url: str,
    timeout_seconds: float)` con `async check_permission(token: str, permission: str) -> bool`.
  - `src/integrations/clinics_api.py`: `ClinicsApiClient(http_client, base_url, timeout_seconds)` con
    `async get_counts(token: str, subscription_ids: Sequence[int] | None = None) -> dict[int, int]`
    (solo suscripciones con ≥ 1 clínica; quien llama trata una ausente como 0).
  - `src/services/authorization_service.py`: `AuthorizationService(users_api: UsersApiClient)` con
    `async require(token: str, permission: str) -> None`.
  - `src/security.py`: `bearer_scheme`, `async get_bearer_token(...) -> str` y
    `require_permission(permission: str)` (devuelve una dependencia `async` que no devuelve nada).
  - `src/routers/openapi_docs.py`: `error_response(description, **examples)`,
    `example_response(description, example_name, value)` y
    `protected(permission, *, responses=None) -> dict` (se expande en el decorador de la ruta:
    `@router.get("", **protected(SUBSCRIPTIONS_READ, responses={...}))`).
  - `src/repositories/subscription_repository.py`: `SubscriptionRepository(session)` con
    `list_current() -> list[Subscription]`, `get_current_by_id(id) -> Subscription | None`,
    `create(name, description, monthly_price, features) -> Subscription`,
    `update(id, changes) -> Subscription | None`, `change_status(id, to_status_id) -> Subscription | None`,
    `get_status_id(id) -> int | None` y `soft_delete(id) -> bool`.
  - `src/services/subscription_service.py`: `SubscriptionView(subscription, clinics_count)` (dataclass
    inmutable) y `SubscriptionService(repository, clinics_api)` con `list(token)`, `get(id, token)`,
    `create(data)`, `update(id, data, token)`, `change_status(id, data, token)` y `delete(id, token)`.
  - `src/dependencies.py`: `get_http_client`, `get_users_api_client`, `get_clinics_api_client`,
    `get_authorization_service`, `get_subscription_repository`, `get_subscription_service`.
  - `src/config.py`: `Settings`, `IntegrationSettings`, `CorsSettings`, `get_settings`,
    `get_integration_settings`, `get_cors_settings` y `configuration_error_message(error)`.
  - `tests/stubs/users_api/app.py` y `tests/stubs/clinics_api/app.py`: cada uno con
    `create_stub_app() -> FastAPI` (estado nuevo en cada llamada) y `app = create_stub_app()`.
  - `tests/unit/fakes.py`: `FakeSubscriptionRepository`, `FakeClinicsApi`, `FakeUsersApi`.
  - `tests/helpers.py`: `ROOT`, `Migrator`, `TEST_TOKEN`, `insert_subscription(session, **valores)`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Herramientas, entorno y esqueleto del repositorio.

- [X] T001 Verificar prerrequisitos (no modifica archivos): confirmar que `.specify/memory/constitution.md`
  termina en `**Version**: 1.0.0`; que `.specify/feature.json` contiene
  `"feature_directory": "specs/001-subscriptions-api"`; que `docker --version` y `uv --version` responden
  y que `docker images` incluye `postgres:17` y `python:3.14-slim` (si no, se descargan en T006/T005); y
  que `git status --short` solo muestra `.claude/`, `.specify/` y `specs/` sin seguimiento.
- [X] T002 `pyproject.toml`: `[project]` con `name = "mailysoft-system-api"`, `version = "0.1.0"`,
  `description = "Servicio REST de MailySoft (suscripciones)"`, `requires-python = ">=3.14"` y
  `dependencies = ["alembic>=1.14", "asyncpg>=0.30", "fastapi>=0.143", "httpx>=0.28",
  "pydantic-settings>=2.6", "sqlalchemy[asyncio]>=2.0,<2.1", "uvicorn>=0.30"]` (**sin** `pyjwt`);
  `[dependency-groups] dev = ["pytest>=8.3", "pytest-asyncio>=1.0", "python-dotenv>=1.0"]`;
  `[tool.uv] package = false`; `[tool.pytest.ini_options]` con `testpaths = ["tests"]`,
  `pythonpath = ["."]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`,
  `asyncio_default_test_loop_scope = "session"`, `markers = ["slow: pruebas lentas"]` y
  `addopts = "-m 'not slow'"`. Ejecutar `uv lock` y `uv sync`; comprobar
  `uv run python -c "import fastapi, httpx, sqlalchemy, asyncpg, alembic, pydantic_settings"`. Si alguna
  versión mínima no resuelve, usar la más cercana que resuelva y anotarlo en el mensaje de cierre.
- [X] T003 [P] `.gitignore` y `.dockerignore`. Leer primero el `.gitignore` existente (plantilla de Python) y
  **añadir solo lo que falte**: `.env`, `.env.*`, `!.env.example`, `.venv/`, `.pytest_cache/`,
  `tests/postman/node_modules/` y `tests/postman/reports/`. Crear `.dockerignore` con: `.git`, `.claude`,
  `.specify`, `.vscode`, `.idea`, `project-definition`, `specs`, `tests`, `docker`, `.venv`, `venv`,
  `__pycache__`, `*.py[cod]`, `.pytest_cache`, `.env`, `.env.*`, `*.md`.
- [X] T004 [P] `.env.example` (se copia a `.env`, que no se versiona), con comentarios en español:
  `POSTGRES_PORT=5433`; `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/maily_system`;
  `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/maily_system_test` (avisar de que
  las pruebas **eliminan y recrean el esquema** y por eso el nombre debe terminar en `_test`);
  `API_PORT=8010`; y el bloque «APIs de los que depende este servicio»: `USERS_API_BASE_URL=` y
  `CLINICS_API_BASE_URL=` (obligatorias, vacías: el arranque se niega sin ellas; usar `https://` salvo en
  local o en la red de Docker, porque a esas direcciones se reenvía el token de la persona), `#
  USERS_API_TIMEOUT_SECONDS=5`, `# CLINICS_API_TIMEOUT_SECONDS=5` (opcionales, con su valor por defecto) y
  `# CORS_ALLOWED_ORIGINS=` (orígenes del Front separados por comas). Aclarar que las pruebas automatizadas
  **no** necesitan estas variables (usan simulaciones).
- [X] T005 [P] `Dockerfile` (mismo patrón que `C:\maily\code\mailySoft-usuarios\Dockerfile`):
  `FROM python:3.14-slim`; `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
  UV_PYTHON_DOWNLOADS=never`; `WORKDIR /app`; `RUN pip install --no-cache-dir "uv==<la versión fijada en el
  Dockerfile de mailySoft-usuarios>"`; `COPY pyproject.toml uv.lock ./`; `RUN uv sync --frozen --no-dev`;
  `COPY alembic.ini ./`, `COPY alembic ./alembic`, `COPY src ./src`;
  `ENV PATH="/app/.venv/bin:$PATH"`; `EXPOSE 8000`; `CMD ["alembic", "upgrade", "head"]`.
- [X] T006 [P] `docker-compose.yml` y `docker/postgres/init/01-create-test-db.sql`. Servicios: `db`
  (`postgres:17`; `POSTGRES_USER`/`POSTGRES_PASSWORD` = `postgres`; `POSTGRES_DB: maily_system`; puerto
  `"${POSTGRES_PORT:-5433}:5432"`; volumen `pgdata`; montar `./docker/postgres/init` en
  `/docker-entrypoint-initdb.d:ro`; `healthcheck` con `pg_isready -U postgres -d maily_system`),
  `migrate` (`build: .`; depende de `db` sano; `DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/maily_system`;
  `command: ["alembic", "upgrade", "head"]`; `restart: "no"`) y `api` (`build: .`; depende de `migrate`
  completado con éxito; `DATABASE_URL` igual; `USERS_API_BASE_URL: ${USERS_API_BASE_URL:-}`,
  `USERS_API_TIMEOUT_SECONDS: ${USERS_API_TIMEOUT_SECONDS:-}`, `CLINICS_API_BASE_URL: ${CLINICS_API_BASE_URL:-}`,
  `CLINICS_API_TIMEOUT_SECONDS: ${CLINICS_API_TIMEOUT_SECONDS:-}`, `CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-}`
  (vacías por defecto para que `db` y `migrate` funcionen sin ellas; las vacías se ignoran, ver T021);
  `command: ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`; puerto
  `"${API_PORT:-8010}:8000"`). El SQL de inicio contiene solo `CREATE DATABASE maily_system_test;`
  (con un comentario de que corre solo la primera vez que se crea el volumen).
- [X] T007 [P] `alembic.ini` (con `script_location = %(here)s/alembic`, `prepend_sys_path = .`, sin
  `sqlalchemy.url`: lo toma `alembic/env.py` de `DATABASE_URL`, y la configuración de registros del
  patrón de `C:\maily\code\mailySoft-usuarios\alembic.ini`) y `alembic/script.py.mako` (copia de la
  plantilla estándar de Alembic con `down_revision`).
- [X] T008 [P] Esqueleto de paquetes: crear archivos `__init__.py` **vacíos** en `src/`, `src/routers/`,
  `src/services/`, `src/repositories/`, `src/integrations/`, `src/database/`, `src/models/`, `src/dtos/`,
  `tests/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/stubs/`,
  `tests/stubs/users_api/` y `tests/stubs/clinics_api/`. (Los de `src/repositories/`, `src/database/`,
  `src/models/` y `src/dtos/` se reescriben después con contenido; basta con que existan.)

**Checkpoint**: `uv sync` limpio y `uv run python -c "import src"` sin errores.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: vocabulario de errores, configuración, esquema de datos, migraciones y base de las pruebas.
Nada de esta fase es específico de una historia, y **ninguna historia puede empezar** sin ella.

**⚠️ CRITICAL**: no empieces ninguna historia hasta terminar esta fase.

### Tests de la base (escribirlos primero; deben fallar)

- [X] T009 `tests/helpers.py` y `tests/conftest.py` (patrón de `C:\maily\code\mailySoft-usuarios\tests\conftest.py`).
  `helpers.py`: `ROOT = Path(__file__).resolve().parents[1]`; `TEST_TOKEN = "test-token"`; clase
  `Migrator(test_db_url, engine)` con `async upgrade(revision)` y `async downgrade(revision)` que llaman a
  `alembic.command` dentro de `asyncio.to_thread` (porque `env.py` usa `asyncio.run`), con
  `Config(ROOT / "alembic.ini")`, `config.attributes["configure_logger"] = False` y
  `sqlalchemy.url` = la URL de pruebas; y `async insert_subscription(session, *, name="Plan", monthly_price="100.00",
  description=None, features=(), status_id=1) -> int` que inserta con SQLAlchemy Core y confirma. `conftest.py`:
  fixture de sesión `autouse` `_never_reach_the_real_database` (apunta `DATABASE_URL` a la base de pruebas
  durante toda la sesión y limpia las cachés de `get_settings`, `get_engine` y `get_session_factory`; sin base
  de pruebas configurada usa `postgresql+asyncpg://nobody:nobody@127.0.0.1:1/not_configured_test`);
  `test_db_url` (lee `TEST_DATABASE_URL` del entorno o de `.env`; **falla** si falta o si el nombre de la base
  no termina en `_test`, con el mensaje «Las pruebas eliminan y recrean el esquema, así que la base de datos
  de pruebas debe llamarse '*_test'…»); `engine` y `migrator` (sesión); `migrated_db` (sesión: `downgrade base`
  → `upgrade head` → yield → `downgrade base`); `db_session` (transacción externa con
  `join_transaction_mode="create_savepoint"` que se revierte) y `committing_session` (sin transacción externa;
  al terminar ejecuta `TRUNCATE subscriptions RESTART IDENTITY CASCADE`, **sin** tocar `subscription_statuses`).
  Los imports de `src` y de `httpx` van dentro de las fixtures para que la suite de datos corra sin la aplicación.
- [X] T010 [P] `tests/unit/test_error_messages.py`: (a) `ErrorCode` tiene exactamente los 12 valores de
  [contracts/error-catalog.md](contracts/error-catalog.md); (b) cada código con mensaje tiene el texto exacto
  de la tabla «Mensajes» (comparar la cadena completa, incluidos los marcadores `{permission}`,
  `{subscription_id}`, `{name}` y `{status}`); (c) cada error de `src/exceptions.py` tiene el `code`, el
  `status_code` y las cabeceras de la tabla «Códigos» (`unauthenticated` → 401 con
  `WWW-Authenticate: Bearer`; `token_expired` e `invalid_token` → 401 con
  `WWW-Authenticate: Bearer error="invalid_token"`; `permission_denied` → 403; `authorization_unavailable`
  y `clinics_check_unavailable` → 503; `subscription_not_found` → 404; `subscription_name_already_exists`,
  `subscription_status_unchanged` y `subscription_has_clinics` → 409); (d) `translate_validation_errors`
  (de `src/error_handlers.py`) convierte los errores de Pydantic en los mensajes de la tabla «Mensajes de
  validación» (un caso por fila: nombre faltante/`null`/vacío/largo/no texto, descripción larga, precio
  faltante/`null`/inválido, `features` no lista/más de 20/elemento vacío o largo, `status_id`
  faltante/inválido/fuera del catálogo, campo desconocido con `field` = el campo, cuerpo `{}` al actualizar,
  JSON inválido, `subscription_id` no entero positivo) y nunca repite el valor recibido; (e) ningún mensaje
  contiene la palabra «Bearer» ni «token» seguida de un valor. Falla hasta T017–T020.
- [X] T011 [P] `tests/unit/test_config.py`: `IntegrationSettings` exige `USERS_API_BASE_URL` y
  `CLINICS_API_BASE_URL`; los tiempos valen `5.0` por defecto, deben ser > 0 y ≤ 30 (0, −1 y 31 fallan); una
  variable **vacía** se ignora (cuenta como no definida); las URL deben empezar por `http://` o `https://` y
  se normalizan sin `/` final (`http://x:8000/` → `http://x:8000`); `CorsSettings` sin variable → `origins
  == []`, con `"http://a.com, http://b.com,"` → `["http://a.com", "http://b.com"]`;
  `configuration_error_message(error)` devuelve un texto en español que **nombra** las variables que faltan
  o son inválidas (p. ej. `USERS_API_BASE_URL`) y **nunca** contiene el valor recibido (probar con una URL
  inválida `"ftp://secreto"` y comprobar que «secreto» no aparece). Además, `insecure_url_warnings(settings)
  -> list[str]` (FR-024): devuelve una advertencia **por cada** dirección con `http://` cuyo host no es
  `localhost`, `127.0.0.1`, `::1` ni un nombre sin punto (los de Docker Compose); ninguna para `https://` ni
  para esas excepciones (`http://localhost:8000`, `http://127.0.0.1`, `http://users-api-stub:8080`); con
  `http://users.empresa.com` y `http://clinicas.internal:8000` devuelve 2; cada advertencia **nombra la
  variable** (`USERS_API_BASE_URL` o `CLINICS_API_BASE_URL`) y **no** contiene la dirección ni credenciales
  (probar con `http://usuario:clave@host.com`: «clave» no aparece). Falla hasta T021.
- [X] T012 [P] `tests/integration/test_migrations.py` (usa `migrator` y `engine`): `upgrade head` crea
  `subscription_statuses` y `subscriptions`, el índice `subscriptions_name_not_deleted_key`, la función
  `set_updated_at` y el disparador `subscriptions_set_updated_at`; `downgrade base` los elimina (también la
  función); `upgrade head` otra vez funciona (reversibles); `downgrade 0001` (deshace solo la `0002`) deja la
  tabla `subscription_statuses` **vacía** y conserva las dos tablas. Falla hasta T024 y T025.
- [X] T013 [P] `tests/integration/test_seed_data.py` (usa `db_session` y `migrated_db`): el catálogo tiene
  exactamente 4 estatus: `(1, 'Activa')`, `(2, 'Inactiva')`, `(3, 'Bloqueada')`, `(4, 'Eliminada')`; la tabla
  `subscriptions` está vacía (no hay suscripciones iniciales); un estatus insertado a mano recibe `id = 5`.
  Falla hasta T025.
- [X] T014 [P] `tests/integration/test_subscriptions_constraints.py` (usa `db_session`/`committing_session` y SQL
  directo): cada restricción de [data-model.md](data-model.md) se rechaza con el nombre automático esperado
  (`subscriptions_name_check` con nombre `'   '`; `subscriptions_monthly_price_check` con precio −1;
  `subscriptions_features_check` con 21 elementos; `subscriptions_status_id_fkey` con estatus 99; desbordamiento
  de `numeric(10,2)` con `100000000`); **unicidad** (FR-014): `Pro` y `pro` chocan en
  `subscriptions_name_not_deleted_key`, `Básico` y `BÁSICO` también (acentos), el nombre de una suscripción con
  estatus 4 queda libre, el de una con estatus 2 o 3 sigue reservado, y renombrar una suscripción a su propio
  nombre con otra capitalización no choca; **`updated_at`**: tras un `UPDATE` (también solo del `status_id`) es
  mayor que `created_at` (usa `committing_session` porque `CURRENT_TIMESTAMP` es la hora de inicio de la
  transacción); un precio `4500` se lee como `Decimal('4500.00')`. Falla hasta T024.
- [X] T015 [P] `tests/integration/test_models_match_migrations.py`: tras `upgrade head`, la comparación de
  Alembic entre `Base.metadata` y la base de datos (`alembic.autogenerate.compare_metadata` con
  `compare_type=True` y `compare_server_default=True`, sobre una conexión síncrona de `run_sync`) no devuelve
  diferencias. Falla hasta T022 y T024.
- [X] T016 [P] `tests/unit/test_layering.py` (patrón de `tests/unit/test_layering.py` de la referencia, con `ast`
  sobre todos los módulos de `src/`; sin importaciones relativas): tabla `FORBIDDEN_IMPORTS` por capa:
  `routers` no importa `src.repositories`, `src.integrations`, `src.database`, `src.models` ni `sqlalchemy`;
  `services` no importa `src.routers`, `src.security`, `fastapi` ni `sqlalchemy`; `repositories` no importa
  `src.services`, `src.routers`, `src.integrations`, `src.security`, `src.dtos` ni `fastapi`; `integrations`
  no importa `src.routers`, `src.services`, `src.repositories`, `src.database`, `src.models`, `src.dtos`,
  `src.security`, `fastapi` ni `sqlalchemy`; `database` no importa `src.models`, `src.repositories`,
  `src.services`, `src.routers`, `src.integrations`, `src.security` ni `src.dtos`; `models` no importa
  `src.routers`, `src.services`, `src.repositories`, `src.database`, `src.integrations`, `src.security` ni
  `src.dtos`; `dtos` no importa `src.routers`, `src.services`, `src.repositories`, `src.database`,
  `src.integrations`, `src.security`, `src.models` ni `sqlalchemy`. Quedan fuera (raíz de composición y
  vocabulario compartido): `main`, `dependencies`, `security`, `exceptions`, `error_handlers`, `messages` y
  `config`. Además comprueba que todo archivo de `src/` está en `src/` y en una de las carpetas de capa o es
  uno de esos módulos de la raíz. Pasa en vacío ahora y **no debe romperse** en ninguna fase posterior.

### Implementación de la base

- [X] T017 `src/messages.py` (no importa ninguna capa): `ErrorCode(StrEnum)` con los 12 valores en inglés de
  [contracts/error-catalog.md](contracts/error-catalog.md) (`UNAUTHENTICATED = "unauthenticated"`,
  `TOKEN_EXPIRED`, `INVALID_TOKEN`, `PERMISSION_DENIED`, `AUTHORIZATION_UNAVAILABLE`,
  `SUBSCRIPTION_NOT_FOUND`, `SUBSCRIPTION_NAME_ALREADY_EXISTS`, `SUBSCRIPTION_STATUS_UNCHANGED`,
  `SUBSCRIPTION_HAS_CLINICS`, `CLINICS_CHECK_UNAVAILABLE`, `VALIDATION_ERROR`, `INTERNAL_ERROR`); una
  constante `*_MESSAGE` por código con el **texto exacto** de la tabla «Mensajes» del catálogo (nombres:
  `UNAUTHENTICATED_MESSAGE`, `TOKEN_EXPIRED_MESSAGE`, `INVALID_TOKEN_MESSAGE`, `PERMISSION_DENIED_MESSAGE`,
  `AUTHORIZATION_UNAVAILABLE_MESSAGE`, `SUBSCRIPTION_NOT_FOUND_MESSAGE`,
  `SUBSCRIPTION_NAME_ALREADY_EXISTS_MESSAGE`, `SUBSCRIPTION_STATUS_UNCHANGED_MESSAGE`,
  `SUBSCRIPTION_HAS_CLINICS_MESSAGE`, `CLINICS_CHECK_UNAVAILABLE_MESSAGE`, `VALIDATION_ERROR_MESSAGE`,
  `INTERNAL_ERROR_MESSAGE`); y los textos de validación: `FORBIDDEN_FIELD_MESSAGE = "El campo «{field}» no
  está permitido."`, `INVALID_BODY_MESSAGE = "El cuerpo de la solicitud no es válido."`,
  `INVALID_VALUE_MESSAGE = "El valor del campo «{field}» no es válido."`, `SUBSCRIPTION_EMPTY_UPDATE_MESSAGE
  = "Hay que enviar al menos un dato para modificar."`, `SUBSCRIPTION_NAME_REQUIRED_MESSAGE` y
  `SUBSCRIPTION_PRICE_REQUIRED_MESSAGE` («El precio mensual es obligatorio.»),
  `SUBSCRIPTION_FEATURES_NOT_LIST_MESSAGE` («Lo que incluye la suscripción debe ser una lista de textos.») y
  `SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE` («El estatus debe ser uno de los que admite esta operación (1, 2
  o 3).»), que los validadores de los DTOs lanzan como `ValueError` (un `null` explícito al actualizar o un
  estatus fuera de 1 a 3), y los diccionarios `FIELD_MESSAGES: dict[tuple[str, str], str]` (genéricos) y
  `VALIDATION_MESSAGES: dict[str, dict[tuple[str, str], str]]` con el bloque `"subscriptions"`. Claves
  `(campo, tipo)` con los tipos `required`, `too_long`, `too_many`, `not_text`, `not_list`, `invalid`:
  `("name","required")` «El nombre de la suscripción es obligatorio.»; `("name","too_long")` «…no puede
  tener más de 100 caracteres.»; `("name","not_text")` «…debe ser un texto.»; `("description","too_long")`
  «La descripción no puede tener más de 500 caracteres.»; `("monthly_price","required")` «El precio mensual
  es obligatorio.»; `("monthly_price","invalid")` «El precio mensual debe ser un importe de 0 a 99 999
  999,99 con hasta dos decimales.»; `("features","not_list")` y `("features","not_text")` «Lo que incluye la
  suscripción debe ser una lista de textos.»; `("features","too_many")` «…no puede tener más de 20
  elementos.»; `("features","required")` y `("features","too_long")` «Cada elemento de lo que incluye la
  suscripción debe tener de 1 a 150 caracteres.»; `("status_id","required")` y `("status_id","invalid")` «El
  estatus es obligatorio y debe ser un número entero.»;  `("subscription_id","invalid")` «El identificador
  de la suscripción debe ser un número entero positivo.». Todo el texto es el de la tabla «Mensajes de
  validación» del catálogo, sin parafrasear.
- [X] T018 `src/exceptions.py`: `AppError(Exception)` con `code: ClassVar[ErrorCode]`,
  `status_code: ClassVar[int]` y `__init__(message, headers=None)`; y los 10 errores del catálogo, cada uno
  con su `code`, `status_code` y mensaje formateado con las constantes de T017: `UnauthenticatedError()` (401,
  cabecera `{"WWW-Authenticate": "Bearer"}`), `TokenExpiredError()` y `InvalidTokenError()` (401, cabecera
  `{"WWW-Authenticate": 'Bearer error="invalid_token"'}`), `PermissionDeniedError(permission)` (403),
  `AuthorizationUnavailableError()` (503), `SubscriptionNotFoundError(subscription_id)` (404),
  `SubscriptionNameAlreadyExistsError(name)` (409), `SubscriptionStatusUnchangedError(subscription_id,
  status_name)` (409), `SubscriptionHasClinicsError(subscription_id)` (409) y
  `ClinicsCheckUnavailableError(subscription_id)` (503). Cada cabecera se entrega como **copia** del diccionario.
- [X] T019 [P] `src/dtos/errors.py` (`FieldError{field, message}` y `ErrorResponse{code: ErrorCode, message,
  errors: list[FieldError] | None}`, con `description` en español en cada `Field` y en
  `json_schema_extra`) y `src/dtos/status.py` (`StatusRead{id: int (ge=1), name: str}` con
  `from_attributes=True` y la descripción de [data-model.md](data-model.md): «Es el valor estable en el que debe
  basarse quien consume la API»); `src/dtos/__init__.py` queda vacío.
- [X] T020 `src/error_handlers.py` (patrón de la referencia): `register_error_handlers(app)` registra
  `AppError` → `JSONResponse(status_code, ErrorResponse(code, message), headers)`; `RequestValidationError`
  → 422 con `ErrorResponse(code=VALIDATION_ERROR, message=VALIDATION_ERROR_MESSAGE,
  errors=translate_validation_errors(...))`; y `Exception` → 500 `internal_error` (la traza va al registro
  en inglés con método y ruta, **nunca** el cuerpo ni las cabeceras). `translate_validation_errors(errors,
  resource)` usa `API_PREFIX = "/api/v1/"` para sacar el recurso (`subscriptions`) del primer segmento de la
  ruta y `_field_of(loc)` (el primer elemento tras `body`/`query`/`path`, o `body`). Tabla `_KINDS` de tipo
  de error de Pydantic → tipo de mensaje: `missing`, `string_too_short` → `required`; `string_too_long` →
  `too_long`; `too_long` (listas) → `too_many`; `string_type` → `not_text`; `list_type` → `not_list`;
  `extra_forbidden` → `forbidden`;  `int_parsing`, `int_type`, `int_from_float`, `greater_than`,
  `greater_than_equal`, `less_than`, `less_than_equal`, `decimal_parsing`, `decimal_type`,
  `decimal_max_places`, `decimal_max_digits`, `decimal_whole_digits`, `finite_number` → `invalid`. **Regla
  extra**: un error cuyo tipo termina en `_type` y cuyo `input` es `None` cuenta como `required`, **salvo
  `list_type`** (así `name: null`, `monthly_price: null` y `status_id: null` dicen «es obligatorio»,
  mientras `features: null` dice «debe ser una lista de textos»). `value_error` usa el mensaje ya en español
  de `ctx["error"]`; `json_invalid` o campo `body` → `INVALID_BODY_MESSAGE`; sin texto para el par →
  `FORBIDDEN_FIELD_MESSAGE` si es `forbidden`, si no `INVALID_VALUE_MESSAGE`. Busca primero en
  `VALIDATION_MESSAGES[recurso]` y luego en `FIELD_MESSAGES`.
- [X] T021 [P] `src/config.py`: `Settings(BaseSettings)` con `database_url: str` y `test_database_url: str |
  None = None` (`env_file=".env"`, `extra="ignore"`); `IntegrationSettings(BaseSettings)` con
  `users_api_base_url: str`, `users_api_timeout_seconds: float = 5.0`, `clinics_api_base_url: str`,
  `clinics_api_timeout_seconds: float = 5.0` (`env_file=".env"`, `extra="ignore"`, `env_ignore_empty=True`;
  los tiempos con `gt=0, le=30`; las URL deben empezar por `http://` o `https://` y se guardan sin `/`
  final); `CorsSettings(BaseSettings)` con `cors_allowed_origins: str = ""` y una propiedad `origins ->
  list[str]` (separa por comas, recorta y descarta vacíos); `@lru_cache` `get_settings`,
  `get_integration_settings` y `get_cors_settings`; y `configuration_error_message(error: ValidationError)
  -> str` en español que recorre `error.errors()` y arma, por cada error, «Falta la variable de entorno
  USERS_API_BASE_URL.» (`type == "missing"`) o «La variable de entorno USERS_API_TIMEOUT_SECONDS no es
  válida.» usando **solo** `loc` (nombre del campo en mayúsculas), **nunca** `input` ni `msg`. Añade
  `insecure_url_warnings(settings: IntegrationSettings) -> list[str]` (FR-024): por cada una de las dos
  direcciones cuyo esquema es `http` y cuyo host no es `localhost`, `127.0.0.1`, `::1` ni un nombre sin
  punto, devuelve un texto en inglés del estilo «USERS_API_BASE_URL uses plain http outside a local or
  Docker network: the access token will travel unencrypted» que **nombra la variable** y **nunca** la
  dirección ni credenciales. Hace pasar T011.
- [X] T022 [P] `src/models/base.py` (`NAMING_CONVENTION = {"pk": "%(table_name)s_pkey", "uq":
  "%(table_name)s_%(column_0_name)s_key", "fk": "%(table_name)s_%(column_0_name)s_fkey", "ix":
  "idx_%(table_name)s_%(column_0_name)s", "ck": "%(table_name)s_%(constraint_name)s"}` y
  `Base(DeclarativeBase)` con `MetaData(naming_convention=...)`), `src/models/subscription_status.py`
  (`SubscriptionStatus`: `id` `Integer` PK, `name` `String(50)` **único**, `description` `Text` opcional;
  `ClassVar[int]` `ACTIVE = 1`, `INACTIVE = 2`, `BLOCKED = 3`, `DELETED = 4`; docstring: el código reconoce los
  estatus por su identificador, nunca por su nombre, y un estatus añadido a mano tiene `id >= 5`),
  `src/models/subscription.py` y `src/models/__init__.py` (exporta `Base`, `Subscription`,
  `SubscriptionStatus`). `Subscription` (`__tablename__ = "subscriptions"`) con **exactamente** las columnas y
  restricciones de [data-model.md](data-model.md): `id` `Integer` PK; `name` `String(100)` `NOT NULL` con
  `CheckConstraint("btrim(name) <> ''", name="name_check")`; `description` `String(500)` opcional;
  `monthly_price` `Numeric(10, 2)` `NOT NULL` con `CheckConstraint("monthly_price >= 0",
  name="monthly_price_check")`; `features` `ARRAY(Text)` `NOT NULL`, `server_default=text("'{}'::text[]")` y
  `CheckConstraint("cardinality(features) <= 20", name="features_check")`; `status_id` `Integer`
  `ForeignKey("subscription_statuses.id")` `NOT NULL` con `server_default=text("1")`; `created_at` y
  `updated_at` `DateTime(timezone=True)` `NOT NULL` con `server_default=text("CURRENT_TIMESTAMP")`;
  `status: Mapped["SubscriptionStatus"] = relationship(lazy="raise")`; y fuera de la clase
  `SUBSCRIPTION_NAME_INDEX = "subscriptions_name_not_deleted_key"` y
  `Index(SUBSCRIPTION_NAME_INDEX, func.lower(Subscription.name), unique=True, postgresql_where=text("status_id <> 4"))`.
- [X] T023 `alembic/env.py` en modo async (patrón de `C:\maily\code\mailySoft-usuarios\alembic\env.py`):
  `target_metadata = Base.metadata`; `get_url()` toma `sqlalchemy.url` si existe o `get_settings().database_url`;
  `compare_type=True` y `compare_server_default=True`; `run_migrations_online` usa `asyncio.run` con
  `async_engine_from_config(..., poolclass=pool.NullPool)`; respeta `config.attributes.get("configure_logger", True)`.
- [X] T024 `alembic/versions/0001_subscriptions_schema.py` (`revision = "0001"`, `down_revision = None`):
  `upgrade` crea, en este orden, `subscription_statuses` y `subscriptions` **tal como** están en
  [contracts/database-schema.sql](contracts/database-schema.sql) (mismas columnas, tipos, `NOT NULL`,
  `DEFAULT`, `CHECK` y clave foránea; las restricciones **sin nombre explícito**, para que PostgreSQL les
  ponga el automático), el índice único parcial `subscriptions_name_not_deleted_key` sobre `lower(name)` donde
  `status_id <> 4`, y, con `op.execute`, la función `set_updated_at()` y el disparador
  `subscriptions_set_updated_at` (`BEFORE UPDATE … FOR EACH ROW`). `downgrade` elimina el disparador, la
  función, el índice y las dos tablas (en orden inverso). Hace pasar T012 (parte de estructura), T014 y T015.
- [X] T025 `alembic/versions/0002_seed_subscription_statuses.py` (`revision = "0002"`,
  `down_revision = "0001"`): `upgrade` inserta `(1, 'Activa', 'Disponible y ofrecida a clínicas nuevas.')`,
  `(2, 'Inactiva', 'Retirada de la oferta; las clínicas que ya la tienen la conservan.')`,
  `(3, 'Bloqueada', 'Suspendida por la administración.')` y `(4, 'Eliminada', 'Baja lógica: fuera de toda
  consulta y operación.')` y ejecuta `SELECT setval(pg_get_serial_sequence('subscription_statuses', 'id'), 4)`;
  `downgrade` borra esos cuatro registros (falla por la clave foránea si hay suscripciones que los usan; es
  aceptable y se documenta en un comentario). Hace pasar T012 y T013.
- [X] T026 [P] `src/database/session.py` y `src/database/__init__.py` (patrón de la referencia):
  `get_engine()` con `@lru_cache` crea `create_async_engine(get_settings().database_url, pool_pre_ping=True)`
  en el primer uso (importar la aplicación no exige `DATABASE_URL`), `get_session_factory()` con
  `async_sessionmaker(get_engine(), expire_on_commit=False)` y `async get_session()` (dependencia de FastAPI
  que cede una sesión y la cierra). `__init__.py` exporta los tres.
- [X] T027 [P] `src/repositories/__init__.py` (solo `INT4_MAX = 2_147_483_647` con su comentario),
  `src/repositories/errors.py` (`UniqueViolationError(constraint_name)`, `ForeignKeyViolationError`,
  `as_unique_violation(error)` y `as_foreign_key_violation(error)`, que leen `sqlstate` `23505`/`23503` y
  `constraint_name` de `error.orig.__cause__`) y `src/repositories/transactions.py`
  (`async execute_and_commit(session, statement) -> int | None`: ejecuta una sentencia con `RETURNING id`,
  confirma, y si no hay fila hace `rollback` y devuelve `None`; ante `IntegrityError` hace `rollback` y lanza
  `UniqueViolationError`/`ForeignKeyViolationError`; ante cualquier otro error hace `rollback` y lo relanza).
- [X] T028 [P] `project-definition/DATA_SCHEMA.md` (Principio VI: esquema objetivo): el contenido de
  [contracts/database-schema.sql](contracts/database-schema.sql) en un bloque `sql`, precedido de una
  introducción en español (qué es, que coincide con las migraciones `0001` y `0002`, y la lista de nombres
  automáticos de restricciones de los que depende el código: `subscriptions_name_check`,
  `subscriptions_monthly_price_check`, `subscriptions_features_check`, `subscriptions_status_id_fkey`,
  `subscription_statuses_name_key`; el único índice con nombre explícito es
  `subscriptions_name_not_deleted_key`). Cada regla lleva el comentario `-- [spec 001-subscriptions-api …]`
  que ya trae el contrato.

**Checkpoint**: `docker compose up -d db`, `uv run alembic upgrade head`, `uv run alembic check` («No new
upgrade operations detected») y `uv run pytest tests/unit tests/integration` en verde (T010–T016 pasan);
`uv run alembic downgrade base` funciona.

---

## Phase 3: User Story 2 - Solo quien tiene el permiso puede operar (Priority: P1) 🎯 MVP

**Goal**: toda operación exige un token y el permiso que decide el API de usuarios, en cada petición, sin
caché y fallando cerrado.

**Independent Test**: con una ruta de sondeo protegida (definida solo en la prueba), probar (a) sin token,
(b) token inválido o vencido, (c) persona sin el permiso, (d) persona con el permiso y (e) el API de usuarios
caído: solo (d) ejecuta la ruta y las demás no cambian nada; además, el permiso se comprueba antes que la
validación del cuerpo y la documentación sigue pública.

### Tests for User Story 2 (escribirlos primero; deben fallar)

- [X] T029 [P] [US2] `tests/stubs/users_api/app.py`: simulación del API de usuarios según
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md) §1. **No importa nada de `src/`** (FastAPI y la
  biblioteca estándar) y no usa importaciones relativas (la pila e2e la ejecuta con `uvicorn app:app
  --app-dir /stub`). `create_stub_app() -> FastAPI` guarda el estado en memoria. `GET
  /api/v1/authorization/check?permission=`: sin cabecera `Authorization: Bearer …` → 401 `{"code":
  "unauthenticated", "message": "…"}`; token no registrado → 401 `invalid_token`; token registrado como
  vencido → 401 `token_expired`; `permission` que no cumple `^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$` (o de más de
  100 caracteres) → 422; si no, `200 {"permission": …, "allowed": bool}` según los permisos del token.
  Superficie de pruebas: `POST /__test__/tokens {"token", "permissions": [], "expired": false}`; `POST
  /__test__/faults {"mode", "count", "delay_seconds"}` con los modos `unavailable` (503), `rate_limited`
  (429), `forbidden` (403), `not_found` (404), `malformed` (200 sin `allowed`), `wrong_permission` (200 con
  otro `permission`), `not_json` (200 con cuerpo de texto), `redirect` (307 con `Location:
  http://evil.test/steal`) y `slow` (duerme `delay_seconds`, 30 por defecto), cada uno aplicado a las
  próximas `count` consultas; `GET /__test__/calls` (lista de `{"path", "permission", "has_authorization",
  "authorization"}` en orden, de **toda** petición que no sea de `/__test__/…`, incluso a rutas
  inexistentes, para detectar redirecciones seguidas); `POST /__test__/reset`. Termina con `app =
  create_stub_app()`.
- [X] T030 [P] [US2] `tests/contract/test_users_api_client.py`: `UsersApiClient` real contra el stub montado
  con `httpx.AsyncClient(transport=httpx.ASGITransport(app=create_stub_app()),
  base_url="http://users-api.test")`. Un caso por fila de la tabla «Traducción de las respuestas» de
  [contracts/users-api-integration.md](contracts/users-api-integration.md): `allowed: true` → `True`;
  `allowed: false` → `False`; 401 con cada código → `UsersApiRejectedToken(code)` con ese código; 401 de
  cuerpo ilegible o código desconocido → `UsersApiRejectedToken("invalid_token")`; `malformed`,
  `wrong_permission`, `not_json` y `redirect` → `UsersApiUnavailable` (la redirección **no se sigue**:
  `/__test__/calls` registra una sola petición y ninguna a `/steal`); 503, 429, 403, 404 y 422 →
  `UsersApiUnavailable`; conexión rechazada (cliente apuntando a un transporte que lanza
  `httpx.ConnectError`) → `UsersApiUnavailable`; modo `slow` con `timeout_seconds=0.2` y `delay_seconds=1` →
  `UsersApiUnavailable` en menos de 1 s (tiempo máximo **total**). Además: la cabecera `Authorization` llega
  **idéntica** al stub (`Bearer <token>`), la petición lleva el `permission` pedido, **no** se envía ninguna
  otra cabecera de la solicitud original, y `check_permission` produce **una** llamada. Ni el mensaje de
  ninguna excepción ni los registros (`caplog`) contienen el token.
- [X] T031 [P] [US2] `tests/unit/test_authorization_service.py` (con `FakeUsersApi`): `allowed=True` → no lanza;
  `allowed=False` → `PermissionDeniedError` con el permiso en el mensaje; `UsersApiRejectedToken("token_expired")`
  → `TokenExpiredError`; `("unauthenticated")` → `UnauthenticatedError`; `("invalid_token")` y cualquier otro
  código → `InvalidTokenError`; `UsersApiUnavailable` → `AuthorizationUnavailableError`; un token de 8 193
  bytes → `InvalidTokenError` **sin** llamar a `FakeUsersApi` (y uno de exactamente 8 192 bytes sí llama);
  `require` pasa el permiso y el token tal cual al cliente.
- [X] T032 [P] [US2] `tests/unit/test_security.py`: `get_bearer_token` con `HTTPAuthorizationCredentials(scheme="Bearer",
  credentials="abc")` devuelve `"abc"`; `None` (sin cabecera o con otro esquema, como `Basic`) →
  `UnauthenticatedError`; credenciales vacías → `UnauthenticatedError`; `require_permission("subscriptions:read")`
  devuelve una dependencia `async` que llama a `AuthorizationService.require(token, "subscriptions:read")`
  exactamente una vez y propaga sus errores; las cuatro constantes `SUBSCRIPTIONS_*` valen lo de la tabla de
  convenciones.
- [X] T033 [US2] `tests/conftest.py` (ampliar): fixture `users_stub_app` (`create_stub_app()` nuevo por prueba),
  `users_stub` (`httpx.AsyncClient` con `ASGITransport(app=users_stub_app)` y `base_url="http://users-api.test"`) y
  `users_api_client` (`UsersApiClient(users_stub, "http://users-api.test", 5.0)`); y una función
  `async grant(users_stub, token=TEST_TOKEN, permissions=(...los cuatro...))` que registra un token en la
  simulación vía `POST /__test__/tokens`. (Depende de T029 y de T036.)
- [X] T034 [US2] `tests/contract/test_access_control.py`: crea una aplicación con `create_app()` y añade
  **en la prueba** un router de sondeo con `GET /probe` (`**protected(SUBSCRIPTIONS_READ)`) y `POST /probe`
  con un cuerpo Pydantic `{"value": int}` (`**protected(SUBSCRIPTIONS_WRITE)`), sustituyendo
  `get_users_api_client` por el cliente de la simulación (`app.dependency_overrides`) y usando
  `httpx.AsyncClient(ASGITransport(app))`. Casos: (a) sin cabecera, con esquema `Basic` y con `Bearer` vacío
  → 401 `unauthenticated` con `WWW-Authenticate: Bearer` y **cero** llamadas a la simulación; (b) token
  desconocido → 401 `invalid_token`, vencido → 401 `token_expired`, ambos con `WWW-Authenticate: Bearer
  error="invalid_token"`; (c) persona autenticada sin el permiso → 403 `permission_denied` con «Permiso
  requerido: subscriptions:read.» en el mensaje; con `subscriptions:read` pero sin `subscriptions:write`,
  `GET` pasa y `POST` da 403; (d) con permiso → 200; (e) simulación caída, con 429, con respuesta mal
  formada, con otro `permission` y con tiempo agotado (cliente con `timeout_seconds=0.2`) → 503
  `authorization_unavailable` y la ruta **no** se ejecuta (un contador en la ruta de sondeo queda en 0).
  Además: **una** llamada por petición con el permiso exacto y el token reenviado idéntico
  (`/__test__/calls`); **sin caché**: dos peticiones seguidas = dos llamadas, y quitar el permiso en la
  simulación entre ellas hace que la segunda dé 403 (SC-003); **precedencia** (R4): `POST /probe` sin token
  con cuerpo inválido → 401, con token **sin** permiso y cuerpo inválido → 403, con permiso y cuerpo
  inválido → 422, y con un cuerpo que no es JSON y sin token → 422 (limitación conocida, documentada en el
  catálogo de errores); el token **no** aparece en ninguna respuesta ni en `caplog`; ningún 503 revela
  detalles del otro servicio: su cuerpo es **exactamente** el texto del catálogo y no contiene la dirección
  base, el host ni el texto de la respuesta de la simulación (modo `not_json` con un cuerpo distintivo como
  «SECRETO-INTERNO»); `/openapi.json`, `/docs` y `/redoc` responden 200 **sin** token; el OpenAPI de la ruta
  de sondeo trae `security: [{"BearerAuth": []}]`, `x-required-permission` y las respuestas 401, 403 y 503.
  Falla hasta T041.

### Implementation for User Story 2

- [X] T035 [P] [US2] `src/integrations/__init__.py` (vacío) y `src/integrations/errors.py`: `IntegrationError(Exception)`;
  `UsersApiRejectedToken(IntegrationError)` con `__init__(self, code: str)` y atributo `code`;
  `UsersApiUnavailable(IntegrationError)` y `ClinicsApiUnavailable(IntegrationError)`. Los mensajes son
  genéricos en inglés («The users API did not answer as expected») y **nunca** incluyen tokens ni cuerpos.
- [X] T036 [US2] `src/integrations/users_api.py`: `UsersApiClient(http_client, base_url, timeout_seconds)` con
  `async check_permission(token, permission) -> bool` según
  [contracts/users-api-integration.md](contracts/users-api-integration.md): `GET {base_url}/api/v1/authorization/check`
  con `params={"permission": permission}` y **solo** las cabeceras `Authorization: Bearer {token}` y
  `Accept: application/json`; todo dentro de `async with asyncio.timeout(timeout_seconds)`; traduce **exactamente**
  la tabla del contrato: 200 con JSON objeto que tiene `allowed` booleano y `permission == permission` pedido →
  `allowed`; 401 → `UsersApiRejectedToken(code)` con el `code` del cuerpo si es `unauthenticated`,
  `token_expired` o `invalid_token`, y `invalid_token` en cualquier otro caso; todo lo demás (otros 4xx, 5xx,
  429, JSON inválido, forma inesperada, `httpx.HTTPError`, `TimeoutError`) → `UsersApiUnavailable`; un 4xx
  inesperado (distinto de 401) se registra con `logger.error("Users API answered an unexpected status %s",
  status)` **sin** token ni cuerpo. Hace pasar T030.
- [X] T037 [US2] `src/services/authorization_service.py`: `MAX_TOKEN_BYTES = 8192` y
  `AuthorizationService(users_api)` con `async require(token, permission)`: si `len(token.encode()) >
  MAX_TOKEN_BYTES` → `InvalidTokenError` sin llamar; llama a `users_api.check_permission`; traduce
  `UsersApiRejectedToken` (`token_expired` → `TokenExpiredError`, `unauthenticated` → `UnauthenticatedError`, otro
  → `InvalidTokenError`) y `UsersApiUnavailable` → `AuthorizationUnavailableError`; `False` →
  `PermissionDeniedError(permission)`. No importa `fastapi` ni `src.security`. Hace pasar T031.
- [X] T038 [US2] `src/dependencies.py` (raíz de composición; todos los proveedores `async def`): `get_http_client(request:
  Request) -> httpx.AsyncClient` (lee `request.app.state.http_client`), `get_users_api_client` (construye
  `UsersApiClient(client, settings.users_api_base_url, settings.users_api_timeout_seconds)` con
  `get_integration_settings()`) y `get_authorization_service`. Docstring del módulo: el Router solo recibe el
  Service; el Service recibe sus Repositories y clientes; el Repository recibe la sesión.
- [X] T039 [US2] `src/security.py`: las cuatro constantes de permisos; `bearer_scheme =
  HTTPBearer(scheme_name="BearerAuth", bearerFormat="JWT", auto_error=False,
  description="Token de acceso emitido por Auth0. Este servicio no lo verifica: lo reenvía al API de usuarios.")`;
  `async get_bearer_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)])
  -> str` (lanza `UnauthenticatedError` si es `None` o si las credenciales están vacías); y
  `require_permission(permission) -> Callable` que devuelve `async def dependency(token: Annotated[str,
  Depends(get_bearer_token)], service: Annotated[AuthorizationService, Depends(get_authorization_service)]) ->
  None: await service.require(token, permission)`. Hace pasar T032.
- [X] T040 [US2] `src/routers/openapi_docs.py`: `error_response(description, **examples)` y
  `example_response(description, example_name, value)` (patrón de la referencia); las respuestas compartidas
  `UNAUTHORIZED` (con la cabecera `WWW-Authenticate` y los ejemplos `sin_token`, `vencido` y `no_valido` de
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)), `FORBIDDEN` y
  `AUTHORIZATION_UNAVAILABLE`; y `protected(permission, *, responses=None) -> dict` que devuelve
  `{"dependencies": [Depends(require_permission(permission))], "openapi_extra": {"x-required-permission":
  permission}, "responses": {401: UNAUTHORIZED, 403: FORBIDDEN, 503: AUTHORIZATION_UNAVAILABLE, **(responses or {})}}`
  (las `responses` recibidas pisan a las compartidas con la misma clave, para documentar los dos 503 de eliminar).
- [X] T041 [US2] `src/main.py`: `TITLE = "MailySoft System API"`, `VERSION = "1.0.0"`, `DESCRIPTION` en
  español (suscripciones; estatus como objeto con `id` y `name`; todos los errores con el mismo formato;
  **todas las operaciones exigen token y permiso, decididos por el API de usuarios**) y `OPENAPI_TAGS` con
  `{"name": "subscriptions", "description": …}`; un `lifespan` que (1) llama a `get_integration_settings()`
  y, si lanza `ValidationError`, escribe `configuration_error_message(error)` con `logger.error` y relanza
  `RuntimeError(mensaje)` (el servicio **no arranca**), (1b) registra con `logger.warning` cada texto de
  `insecure_url_warnings(settings)` (FR-024; no impide arrancar), (2) crea `app.state.http_client =
  httpx.AsyncClient(limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
  follow_redirects=False)` y (3) lo cierra con `aclose()` al terminar; `create_app()` **sin efectos
  secundarios** (no abre conexiones ni exige variables): `FastAPI(title, version, description, openapi_tags,
  lifespan)`, `register_error_handlers(app)`, `logging.getLogger("httpx").setLevel(logging.WARNING)` y,
  (FR-025) **solo si** `get_cors_settings().origins` no está vacío, `CORSMiddleware(allow_origins=origins,
  allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
  allow_credentials=False)`; `app = create_app()`. **Antes** de implementarlo, crear
  `tests/unit/test_main.py` con la prueba del `lifespan` (se prueba la función directamente: `ASGITransport`
  no ejecuta el ciclo de vida): con `USERS_API_BASE_URL` sin definir, `async with lifespan(app)` lanza
  `RuntimeError` cuyo mensaje nombra la variable y no contiene valores; con las dos URL definidas (vía
  `monkeypatch.setenv` y limpiando la caché de `get_integration_settings`), entra y sale sin error, deja
  `app.state.http_client` abierto dentro del bloque y **cerrado** (`is_closed`) al salir; y que
  `create_app()` se puede llamar sin ninguna variable definida y sin abrir conexiones. Esa prueba cubre
  además: (c) con `http://users.empresa.com` en `USERS_API_BASE_URL`, el `lifespan` registra una advertencia
  (en `caplog`) que nombra la variable y no contiene la dirección, y arranca igual; con
  `http://users-api-stub:8080` no registra ninguna; (d) CORS (FR-025), con `monkeypatch.setenv`, limpiando
  la caché de `get_cors_settings` y usando `httpx.ASGITransport` sobre `create_app()`: sin
  `CORS_ALLOWED_ORIGINS`, una petición a `/openapi.json` con `Origin: http://front.test` **no** trae
  `access-control-allow-origin`; con `CORS_ALLOWED_ORIGINS="http://front.test"` sí
  (`access-control-allow-origin: http://front.test`) y **no** trae `access-control-allow-credentials`; un
  origen no listado no recibe la cabecera; el preflight (`OPTIONS` con `Access-Control-Request-Method: POST`
  y `Access-Control-Request-Headers: authorization,content-type`) desde el origen listado responde 200
  permitiendo esas cabeceras, y pidiendo una cabecera no permitida (`x-otra`) no la autoriza. Hace pasar
  T034 y esa prueba.

**Checkpoint**: `uv run pytest tests/unit tests/contract/test_users_api_client.py tests/contract/test_access_control.py`
en verde. El control de acceso funciona y es reutilizable por todas las demás historias. La verificación por cada una de las 6 operaciones reales (SC-002) se completa en T094, cuando todas existen.

---

## Phase 4: User Story 1 - Consultar el catálogo de suscripciones con su estatus (Priority: P1)

**Goal**: devolver en una sola respuesta, sin paginar y en orden estable, todas las suscripciones vigentes
con su estatus, su precio, lo que incluyen y el número de clínicas (o «no disponible»).

**Independent Test**: con cuatro suscripciones (Activa, Inactiva, Bloqueada y Eliminada) insertadas
directamente en la base, `GET /api/v1/subscriptions` devuelve las tres primeras con su estatus, en el mismo
orden en dos consultas, sin señal de paginación; con el catálogo vacío devuelve `[]`; con el API de clínicas
caído devuelve las mismas con `clinics_count: null`.

### Tests for User Story 1 (escribirlos primero; deben fallar)

- [X] T042 [P] [US1] `tests/stubs/clinics_api/app.py`: simulación del API de clínicas según
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md) §1 (sin importar nada de `src/`; `create_stub_app()` y
  `app`). `GET /api/v1/clinics/subscription-counts[?subscription_id=…&subscription_id=…]`: sin
  `Authorization: Bearer …` → 401; si no, `200 {"items": [{"subscription_id", "clinics_count"}, …]}` con los
  conteos configurados **solo con `clinics_count >= 1`**, filtrados por los `subscription_id` pedidos si los
  hay. Pruebas: `POST /__test__/counts {"1": 2, "6": 14}` (sustituye los anteriores); `POST /__test__/faults
  {"mode", "count", "delay_seconds"}` con `unavailable` (503), `unauthorized` (401), `forbidden` (403),
  `malformed` (200 sin `items`), `negative_count`, `unrequested_id` (añade un `subscription_id` que no se
  pidió), `duplicate_id`, `not_json`, `redirect` (307 con `Location: http://evil.test/steal`) y `slow`; `GET
  /__test__/calls` (lista de `{"path", "subscription_ids", "authorization"}` de **toda** petición que no sea
  de `/__test__/…`, incluso a rutas inexistentes); `POST /__test__/reset`.
- [X] T043 [P] [US1] `tests/contract/test_clinics_api_client.py`: `ClinicsApiClient` real contra el stub
  montado con `ASGITransport`. Sin filtro devuelve `{1: 2, 6: 14}`; con `subscription_ids=[1]` solo `{1:
  2}`; una suscripción sin clínicas no aparece (`{}`); repetir `subscription_id` en la consulta
  (`?subscription_id=1&subscription_id=6`); la cabecera `Authorization` recibida por el stub es la de la
  persona, idéntica; y cada modo de falla (`unavailable`, `unauthorized`, `forbidden`, `malformed`,
  `negative_count`, `unrequested_id`, `duplicate_id`, `not_json`, `redirect` (no se sigue: una sola petición
  registrada y ninguna a `/steal`), `slow` con `timeout_seconds=0.2`) → `ClinicsApiUnavailable` (nunca un
  cero ni un diccionario parcial). Ningún mensaje ni registro contiene el token.
- [X] T044 [P] [US1] `tests/unit/fakes.py`: `FakeSubscriptionRepository` (en memoria; mismos métodos y firmas que
  `SubscriptionRepository`; `list_current` ordena por `created_at` y luego `id` y excluye el estatus 4;
  guarda un contador `calls` por método), `FakeClinicsApi` (`counts: dict[int, int]`, `fail: bool`;
  `get_counts(token, ids=None)` registra `(token, ids)` y lanza `ClinicsApiUnavailable` si `fail`) y
  `FakeUsersApi` (`allowed`, `rejected_code`, `unavailable`; `check_permission` registra las llamadas). Se
  amplía en cada historia.
- [X] T045 [P] [US1] `tests/unit/test_subscription_service.py` (ampliable; con `FakeSubscriptionRepository` y
  `FakeClinicsApi`): `list(token)` devuelve una `SubscriptionView` por suscripción vigente con
  `clinics_count` = el conteo del API (0 para las ausentes); con `FakeClinicsApi(fail=True)` devuelve **todas**
  con `clinics_count is None` (nunca 0); consulta al API de clínicas **sin filtro** (`ids is None`) **una** vez y
  con el token recibido; con el repositorio vacío devuelve `[]`; el repositorio y el API de clínicas se llaman
  **en paralelo** (ambos se invocan aunque el otro lance).
- [X] T046 [P] [US1] `tests/integration/test_subscription_repository.py` (ampliable; usa `db_session`):
  `list_current` devuelve las de estatus 1, 2 y 3 y también las de un estatus añadido a mano (id 5, insertado en
  la prueba), **excluye** las de estatus 4, ordena por `created_at` ascendente y, a igualdad, por `id`
  ascendente (insertar tres con el mismo `created_at`), carga el estatus junto con la suscripción (acceder a
  `subscription.status.name` no lanza), devuelve `[]` si no hay y no devuelve las Eliminadas aunque sean las
  únicas.
- [X] T047 [US1] `tests/conftest.py` y `tests/helpers.py` (ampliar): fixtures `clinics_stub_app`,
  `clinics_stub` y `clinics_api_client` (como las de usuarios, con `base_url="http://clinics-api.test"`); y la
  fixture `api` que crea `create_app()`, sustituye con `app.dependency_overrides` `get_users_api_client` →
  `users_api_client`, `get_clinics_api_client` → `clinics_api_client` y `get_session` → una sesión sobre el
  `engine` de pruebas (`AsyncSession(engine, expire_on_commit=False)`, con `committing_session` para limpiar al
  terminar), registra `TEST_TOKEN` con los cuatro permisos (`grant`) y entrega un
  `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test", headers={"Authorization":
  f"Bearer {TEST_TOKEN}"})` junto con acceso a las dos simulaciones. (Depende de T033, T036, T042 y T043.)
- [X] T048 [US1] `tests/contract/test_subscriptions_api.py` (ampliable; usa `api`): `GET /api/v1/subscriptions`:
  200 con un **arreglo JSON**; cada elemento tiene exactamente `id`, `name`, `description`, `monthly_price`,
  `features`, `status` (`{"id", "name"}`), `clinics_count`, `created_at` y `updated_at`; `monthly_price` es una
  **cadena con dos decimales** (`"1500.00"`); devuelve Activa, Inactiva y Bloqueada con su estatus y no devuelve
  la Eliminada; mismo orden en dos consultas seguidas (por `created_at` e `id`); `[]` con el catálogo vacío;
  sin paginación (sin `total`, `pages` ni cabeceras de página); `clinics_count` = el de la simulación (0 para las
  suscripciones que no aparecen en ella) y se hizo **una** llamada a la simulación de clínicas sin
  `subscription_id`; sin `subscriptions:read` → 403 y sin token → 401 (reutilizando T034).
- [X] T049 [P] [US1] `tests/contract/test_clinics_degradation.py` (ampliable; usa `api`): con cada modo de
  falla de la simulación de clínicas (`unavailable`, `unauthorized`, `forbidden`, `malformed`, `slow` con el
  cliente de 0,2 s, `negative_count`, `duplicate_id`, `unrequested_id`, `not_json`) el listado sigue
  respondiendo **200** con todas las suscripciones y `clinics_count: null` en **todas** (SC-005); con el API
  de clínicas sano, un conteo real; el token de la persona llega a la simulación de clínicas idéntico
  (`/__test__/calls`); y ningún cuerpo, mensaje ni registro contiene la dirección ni el texto distintivo de
  las respuestas de la simulación (modo `not_json` con «SECRETO-INTERNO»).
- [X] T050 [P] [US1] `tests/integration/test_catalog_scale.py` (SC-001): inserta 500 suscripciones (nombres
  únicos, estatus mezclados 1/2/3/4) con una sola sentencia; `GET /api/v1/subscriptions` devuelve 500 menos
  las Eliminadas, en orden correcto (creación e `id`), y la petición completa con las simulaciones tarda
  menos de 2 s; además repite la consulta 30 veces seguidas y comprueba que el percentil 95 de los tiempos
  es menor de 2 s (SC-001).

### Implementation for User Story 1

- [X] T051 [US1] `src/integrations/clinics_api.py`: `ClinicsApiClient(http_client, base_url, timeout_seconds)` con
  `async get_counts(token, subscription_ids=None) -> dict[int, int]` según
  [contracts/clinics-api-integration.md](contracts/clinics-api-integration.md): `GET
  {base_url}/api/v1/clinics/subscription-counts` con `params=[("subscription_id", i) for i in ids]` si se
  recibieron identificadores, solo las cabeceras `Authorization: Bearer {token}` y `Accept: application/json`,
  dentro de `asyncio.timeout(timeout_seconds)`. Cualquier respuesta que no sea `200` con un objeto JSON cuyo
  `items` es una lista de objetos con `subscription_id` **entero** (no booleano) y `clinics_count` **entero ≥ 1**,
  sin `subscription_id` repetidos y, si se filtró, solo con los pedidos → `ClinicsApiUnavailable` (también
  `httpx.HTTPError`, `TimeoutError` y JSON inválido); registra la falla con `logger.warning("Clinics API
  unavailable (status %s)", status)` sin token ni cuerpo. Hace pasar T043.
- [X] T052 [P] [US1] `src/dtos/subscription.py` (se amplía en las historias siguientes): `SubscriptionRead`
  (`from_attributes=True`) con `id: int (ge=1)`, `name: str`, `description: str | None`, `monthly_price: Decimal`
  (serializada como **cadena con dos decimales** mediante un `@field_serializer` que hace
  `format(value.quantize(Decimal("0.01")), "f")`; `description` en español: «Precio mensual en pesos mexicanos,
  con dos decimales (cadena para no perder precisión)»), `features: list[str]`, `status: StatusRead`,
  `clinics_count: int | None = None` (≥ 0; «`null` = no disponible») y `created_at`/`updated_at: datetime`;
  todas las descripciones de `Field` en español y los ejemplos de
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml).
- [X] T053 [US1] `src/repositories/subscription_repository.py`: `SubscriptionRepository(session)` con un helper
  `_select_with_status()` (`select(Subscription).options(joinedload(Subscription.status))`) y
  `async list_current() -> list[Subscription]`: `where(Subscription.status_id != SubscriptionStatus.DELETED)`
  ordenado por `Subscription.created_at, Subscription.id`. Docstring: solo esta capa construye consultas.
  Hace pasar T046.
- [X] T054 [US1] `src/services/subscription_service.py`: `@dataclass(frozen=True, slots=True) class
  SubscriptionView(subscription: Subscription, clinics_count: int | None)` y
  `SubscriptionService(repository, clinics_api)` con un helper privado `async _fetch_counts(token, ids) ->
  dict[int, int] | None` (llama a `clinics_api.get_counts`; ante `ClinicsApiUnavailable` registra
  `logger.warning("Clinics count unavailable")` y devuelve `None`) y `async list(token) -> list[SubscriptionView]`:
  `subscriptions, counts = await asyncio.gather(repository.list_current(), self._fetch_counts(token, None))` y
  una vista por suscripción con `clinics_count = None if counts is None else counts.get(s.id, 0)`. Hace
  pasar T045.
- [X] T055 [US1] `src/dependencies.py` (ampliar): `get_clinics_api_client`, `get_subscription_repository(session:
  Depends(get_session))` y `get_subscription_service(repository, clinics_api)`.
- [X] T056 [US1] `src/routers/subscriptions.py`: `SUBSCRIPTIONS_PATH = "/api/v1/subscriptions"`,
  `router = APIRouter(prefix=SUBSCRIPTIONS_PATH, tags=["subscriptions"])`, `SubscriptionServiceDep`,
  `BearerTokenDep = Annotated[str, Depends(get_bearer_token)]`, `SubscriptionIdPath = Annotated[int, Path(gt=0,
  description="Identificador de la suscripción (entero positivo).", examples=[1])]` y un helper
  `_to_read(view: SubscriptionView) -> SubscriptionRead` (`SubscriptionRead.model_validate(view.subscription)`
  y luego `clinics_count = view.clinics_count`). Operación `list_subscriptions`: `@router.get("",
  response_model=list[SubscriptionRead], operation_id="list_subscriptions", summary="Listar las suscripciones
  vigentes (sin paginar)", **protected(SUBSCRIPTIONS_READ, responses={200: LIST_EXAMPLE}))` con la
  `description` de [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) terminada en
  «**Permiso requerido: `subscriptions:read`.**»; el router solo llama a `service.list(token)` y serializa
  (**no** importa repositorios, sesiones ni modelos). Definir en el módulo las constantes de documentación `LIST_EXAMPLE` (el ejemplo `catalogo` del OpenAPI) e
  `INTERNAL_ERROR` (`error_response(...)` con el ejemplo `internal_error`) y documentar `500` con esta última.
- [X] T057 [US1] `src/main.py` (ampliar): `app.include_router(subscriptions.router)` dentro de `create_app()`.
  Hace pasar T048 a T050.

**Checkpoint**: el catálogo funciona de punta a punta y con control de acceso: **MVP** (US2 + US1).
`uv run pytest` en verde.

---

## Phase 5: User Story 3 - Crear una suscripción (Priority: P2)

**Goal**: registrar un plan nuevo, que nace Activa, con nombre único y `clinics_count: 0`.

**Independent Test**: crear «Pro» con precio mensual 4500: respuesta 201 con identificador, estatus Activa,
`monthly_price: "4500.00"`, `clinics_count: 0` y cabecera `Location`; aparece en el catálogo; «pro» se
rechaza (409); sin nombre o con precio negativo se rechaza (422).

### Tests for User Story 3 (escribirlos primero; deben fallar)

- [X] T058 [P] [US3] `tests/unit/test_subscription_dtos.py` (parte de `SubscriptionCreate`; ampliable):
  `name` obligatorio, recortado, de **1 a 100** caracteres tras recortar (101 falla; `"  Pro  "` → `"Pro"`;
  `"   "` falla; `null` falla; un número falla como «no es texto»); `description` opcional de hasta **500**
  caracteres, la cadena vacía (o de solo espacios) equivale a `None`; `monthly_price` obligatorio, `Decimal`
  con `max_digits=10, decimal_places=2, ge=0` (acepta `4500`, `4500.5`, `"4500.50"`, `0`; rechaza `-1`,
  `4500.555`, `100000000`, `"abc"`, `null` y ausente); `features` opcional (por defecto `[]`), **máximo 20**
  elementos, cada uno recortado de **1 a 150** caracteres (21 elementos, `""`, `"  "` y 151 caracteres
  fallan; un elemento que no es texto falla; `features: null` y `features: "abc"` fallan con «Lo que incluye
  la suscripción debe ser una lista de textos.», no con el mensaje de los elementos); `extra="forbid"`:
  `id`, `status`, `status_id`, `clinics_count`, `created_at` y `updated_at` fallan como campos no
  permitidos. Los errores pasan por `translate_validation_errors` y dan los mensajes del catálogo.
- [X] T059 [P] [US3] `tests/unit/test_subscription_service.py` (ampliar): `create(data)` llama a
  `repository.create(name, description, monthly_price, features)` con los valores validados y devuelve
  `SubscriptionView(…, clinics_count=0)` **sin** llamar al API de clínicas (`FakeClinicsApi.calls == 0`); un
  `UniqueViolationError` con `constraint_name == SUBSCRIPTION_NAME_INDEX` → `SubscriptionNameAlreadyExistsError`
  con el nombre; con otro `constraint_name` se relanza tal cual; **no** se consulta el nombre antes de insertar.
- [X] T060 [P] [US3] `tests/integration/test_subscription_repository.py` (ampliar): `create` inserta con estatus 1
  y devuelve la fila recargada con `status.name == 'Activa'`, `monthly_price == Decimal("4500.00")` (aunque se
  pase `Decimal("4500")`), `features` en el mismo orden, `created_at == updated_at`; nombre repetido (otra
  capitalización) → `UniqueViolationError` con `constraint_name == "subscriptions_name_not_deleted_key"`; el
  nombre de una Eliminada se puede reutilizar; **50 creaciones simultáneas** con el mismo nombre
  (`asyncio.gather`, una sesión propia por tarea sobre el `engine`) → exactamente **una** prospera y 49 lanzan
  `UniqueViolationError` (SC-006); limpiar con `TRUNCATE` al terminar.
- [X] T061 [US3] `tests/contract/test_subscriptions_api.py` (ampliar): `POST /api/v1/subscriptions` con
  `{"name": "Pro", "monthly_price": 4500, "features": ["Hasta 5 consultorios", "Usuarios ilimitados"]}` → 201,
  cuerpo con estatus `{"id": 1, "name": "Activa"}`, `monthly_price == "4500.00"`, `clinics_count == 0`,
  `description is None`, `features` en orden y cabecera `Location: /api/v1/subscriptions/{id}`; **no** llama al
  API de clínicas; aparece en el listado; solo lo obligatorio (`{"name": "Legacy full", "monthly_price": 0}`)
  funciona y `features == []`; espacios sobrantes recortados; «pro» tras «Pro» → 409
  `subscription_name_already_exists` con «Ya existe una suscripción con el nombre «pro».»; el nombre de una
  Eliminada queda libre; el de una Inactiva sigue reservado; `status`, `id`, `clinics_count` en el cuerpo →
  422 con `errors[0].field` = el campo y «El campo «status» no está permitido.»; nombre vacío, precio negativo y
  con tres decimales → 422 con un elemento por campo inválido y sin repetir el valor recibido; sin
  `subscriptions:write` → 403 y **no** se crea nada; con `subscriptions:read` solamente → 403.

### Implementation for User Story 3

- [X] T062 [US3] `src/dtos/subscription.py` (ampliar): `SubscriptionCreate` con `ConfigDict(extra="forbid",
  str_strip_whitespace=True)` y los campos **con estas restricciones verbatim**: `name: str = Field(min_length=1,
  max_length=100)`; `description: str | None = Field(default=None, max_length=500)` (con
  `@field_validator("description")` que convierte la cadena vacía en `None`); `monthly_price: Decimal =
  Field(ge=0, max_digits=10, decimal_places=2)`; `features: list[Annotated[str, StringConstraints(strip_whitespace=True,
  min_length=1, max_length=150)]] = Field(default_factory=list, max_length=20)`. Descripciones y ejemplos en
  español como en el OpenAPI. Hace pasar T058.
- [X] T063 [US3] `src/repositories/subscription_repository.py` (ampliar): `async create(name, description,
  monthly_price, features) -> Subscription`: `insert(Subscription).values(...).returning(Subscription.id)` con
  `execute_and_commit` (el índice único decide los nombres repetidos), seguido de `_reload(id)` (`select` con
  `joinedload(status)` y `execution_options(populate_existing=True)`). Si `execute_and_commit` devuelve `None`
  lanza `RuntimeError("The INSERT of the subscription returned no row")`. Hace pasar T060.
- [X] T064 [US3] `src/services/subscription_service.py` (ampliar): `async create(data: SubscriptionCreate) ->
  SubscriptionView`: llama a `repository.create(data.name, data.description, data.monthly_price, data.features)`;
  captura `UniqueViolationError` y, si `error.constraint_name == SUBSCRIPTION_NAME_INDEX`, lanza
  `SubscriptionNameAlreadyExistsError(data.name)` (con `from error`), si no relanza; devuelve
  `SubscriptionView(subscription, clinics_count=0)`. Docstring: no se comprueba el nombre antes (carrera, R11) y
  el cero es verdadero porque una suscripción nueva no puede tener clínicas (R6). Hace pasar T059.
- [X] T065 [US3] `src/routers/subscriptions.py` (ampliar): operación `create_subscription`: `@router.post("",
  status_code=201, response_model=SubscriptionRead, operation_id="create_subscription", summary="Crear una
  suscripción", **protected(SUBSCRIPTIONS_WRITE, responses={201: CREATED, 409: NAME_CONFLICT, 422:
  VALIDATION_ERROR}))` con cuerpo `Annotated[SubscriptionCreate, Body(openapi_examples=CREATE_EXAMPLES)]`
  (ejemplos `completo` y `minimo` del OpenAPI), un parámetro `response: Response` y
  `response.headers["Location"] = f"{SUBSCRIPTIONS_PATH}/{view.subscription.id}"`; descripción terminada en
  «**Permiso requerido: `subscriptions:write`.**». Definir `CREATED` (respuesta 201 con la cabecera `Location` y
  un ejemplo), `CREATE_EXAMPLES`, `NAME_CONFLICT` (409) y `VALIDATION_ERROR` (422) con `error_response(...)` y los
  ejemplos del OpenAPI. Hace pasar T061.

**Checkpoint**: se pueden crear suscripciones y verlas en el catálogo. `uv run pytest` en verde.

---

## Phase 6: User Story 4 - Consultar una suscripción (Priority: P2)

**Goal**: leer una suscripción vigente por su identificador, con estatus y número de clínicas.

**Independent Test**: consultar una Activa, una Inactiva y una Bloqueada (se devuelven con su estatus);
consultar una Eliminada, una inexistente y una con identificador mayor que `INT4_MAX` (todas «no se encuentra»).

### Tests for User Story 4 (escribirlos primero; deben fallar)

- [X] T066 [P] [US4] `tests/unit/test_subscription_service.py` (ampliar): `get(id, token)` devuelve la vista con
  el conteo de `FakeClinicsApi` (consultado con `ids=[id]` y el token); suscripción ausente o Eliminada →
  `SubscriptionNotFoundError` **sin** llamar al API de clínicas; con `FakeClinicsApi(fail=True)` devuelve la
  vista con `clinics_count is None` y no lanza.
- [X] T067 [P] [US4] `tests/integration/test_subscription_repository.py` (ampliar): `get_current_by_id` devuelve la
  suscripción de estatus 1, 2, 3 y de un estatus añadido a mano, con su estatus cargado; devuelve `None` para
  una Eliminada, una inexistente y un identificador `INT4_MAX + 1` (sin consultar la base de datos: la
  prueba usa un `session` que falla si se ejecuta algo).
- [X] T068 [US4] `tests/contract/test_subscriptions_api.py` (ampliar): `GET /api/v1/subscriptions/{id}` → 200 con
  el mismo detalle que el listado (incluye `status`, `clinics_count` y `monthly_price` con dos decimales) para
  Activa, Inactiva y Bloqueada; una **sola** llamada a clínicas con `subscription_id={id}`; Eliminada o
  inexistente → 404 `subscription_not_found` con «No se encontró la suscripción con el identificador 42.» (y
  **sin** llamar a clínicas); `INT4_MAX + 1` → 404; `0`, `-1` y `abc` → 422 con `field = "subscription_id"` y
  el mensaje del catálogo; con el API de clínicas caído → 200 con `clinics_count: null`; sin
  `subscriptions:read` → 403 (aunque el identificador no exista: no se revela si existe).

### Implementation for User Story 4

- [X] T069 [US4] `src/repositories/subscription_repository.py` (ampliar): `async get_current_by_id(id) ->
  Subscription | None`: si `id > INT4_MAX` devuelve `None` **sin consultar**; si no, `select` con
  `joinedload(status)` y `where(Subscription.id == id, Subscription.status_id != SubscriptionStatus.DELETED)`,
  `one_or_none()`. Hace pasar T067.
- [X] T070 [US4] `src/services/subscription_service.py` (ampliar): `async get(id, token) -> SubscriptionView`:
  lee con `get_current_by_id` (si `None` → `SubscriptionNotFoundError(id)`), luego
  `counts = await self._fetch_counts(token, [id])` y devuelve la vista con
  `None if counts is None else counts.get(id, 0)`. Hace pasar T066.
- [X] T071 [US4] `src/routers/subscriptions.py` (ampliar): operación `get_subscription`: `@router.get("/{subscription_id}",
  response_model=SubscriptionRead, operation_id="get_subscription", summary="Consultar una suscripción por su
  identificador", **protected(SUBSCRIPTIONS_READ, responses={404: NOT_FOUND, 422: VALIDATION_ERROR}))` con
  `SubscriptionIdPath` y `BearerTokenDep`; descripción terminada en «**Permiso requerido: `subscriptions:read`.**».
  Definir `NOT_FOUND` (404, ejemplo «No se encontró la suscripción con el identificador 42.»). Hace pasar T068.

**Checkpoint**: crear, listar y consultar funcionan. `uv run pytest` en verde.

---

## Phase 7: User Story 5 - Actualizar una suscripción (Priority: P2)

**Goal**: modificar nombre, descripción, precio y lo que incluye de una suscripción vigente, enviando solo lo
que cambia.

**Independent Test**: cambiar solo el precio y comprobar que lo demás queda igual y `updated_at` cambia;
ponerle el nombre de otra suscripción vigente (409); intentar actualizar una Eliminada (404); enviar
`{}` o un campo no permitido (422).

### Tests for User Story 5 (escribirlos primero; deben fallar)

- [X] T072 [P] [US5] `tests/unit/test_subscription_dtos.py` (ampliar, `SubscriptionUpdate`): mismas
  restricciones que `SubscriptionCreate` pero todos los campos opcionales (`name` **1 a 100**, `description`
  hasta **500**, `monthly_price` con `max_digits=10, decimal_places=2, ge=0`, `features` máximo **20** de
  **1 a 150**); `{}` falla con «Hay que enviar al menos un dato para modificar.» (campo `body`); `name:
  null` y `monthly_price: null` fallan (no admiten `null`); `description: null` y `""` son válidos y borran
  la descripción (`model_dump(exclude_unset=True)` conserva el `None`); `features: []` es válido y vacía la
  lista; `features: null` falla con «Lo que incluye la suscripción debe ser una lista de textos.» (la
  columna es `NOT NULL`: un `null` jamás debe llegar a la base de datos); `extra="forbid"` rechaza `id`,
  `status`, `status_id`, `clinics_count` y fechas.
- [X] T073 [P] [US5] `tests/unit/test_subscription_service.py` (ampliar): `update(id, data, token)` pasa a
  `repository.update` **solo** los campos enviados (`model_dump(exclude_unset=True)`); repositorio devuelve
  `None` → `SubscriptionNotFoundError`; `UniqueViolationError` del índice del nombre →
  `SubscriptionNameAlreadyExistsError(changes["name"])`; devuelve la vista con el conteo (consultado después de
  escribir, con `ids=[id]`); con clínicas caído la actualización es exitosa con `clinics_count is None`.
- [X] T074 [P] [US5] `tests/integration/test_subscription_repository.py` (ampliar): `update` cambia solo las
  columnas indicadas, devuelve la fila recargada y `updated_at` mayor que `created_at` (usa
  `committing_session`); renombrar a otra capitalización del **propio** nombre no choca; renombrar al nombre de
  otra vigente → `UniqueViolationError`; sobre una Eliminada o inexistente devuelve `None` sin cambios; un
  `id > INT4_MAX` devuelve `None` sin consultar; `description=None` borra la descripción; `features=[]` vacía la
  lista.
- [X] T075 [US5] `tests/contract/test_subscriptions_api.py` (ampliar): `PATCH /api/v1/subscriptions/{id}`
  con `{"monthly_price": "4700.00"}` → 200 con el precio nuevo y lo demás intacto (nombre, descripción,
  funciones, estatus) y `updated_at` mayor que antes; renombrar a «pro» (distinta capitalización de la
  propia, «Pro») → 200; renombrar al nombre de otra vigente → 409 `subscription_name_already_exists`; `{}` →
  422 con `field: "body"`; `{"status_id": 2}`, `{"status": …}`, `{"id": 9}` y `{"clinics_count": 3}` → 422
  con «El campo «…» no está permitido.»; `name: null` → 422 «El nombre de la suscripción es obligatorio.»;
  Eliminada e inexistente → 404; `description: ""` y `null` la borran; `features: []` vacía la lista;
  `features: null` → 422 con «Lo que incluye la suscripción debe ser una lista de textos.» y no cambia nada
  (nunca un 500); un conteo de clínicas caído → 200 con `clinics_count: null`; sin `subscriptions:update` →
  403 y no cambia nada.

### Implementation for User Story 5

- [X] T076 [US5] `src/dtos/subscription.py` (ampliar): `SubscriptionUpdate` con `ConfigDict(extra="forbid",
  str_strip_whitespace=True)`; `name: str | None = Field(default=None, min_length=1, max_length=100)` y
  `monthly_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)` con
  `@field_validator("name", "monthly_price")` que, si el valor es `None` (solo se ejecuta cuando el campo
  viene en el cuerpo), lanza `ValueError` con el mensaje «obligatorio» del campo
  (`SUBSCRIPTION_NAME_REQUIRED_MESSAGE` y `SUBSCRIPTION_PRICE_REQUIRED_MESSAGE`, uno por campo);
  `description: str | None = Field(default=None, max_length=500)` con el validador «vacía = `None`»;
  `features: list[…] | None = Field(default=None, max_length=20)` con los mismos elementos que en
  `SubscriptionCreate` y un `@field_validator("features")` que, si el valor es `None` (solo se ejecuta
  cuando el campo viene en el cuerpo), lanza `ValueError(SUBSCRIPTION_FEATURES_NOT_LIST_MESSAGE)`; y
  `@model_validator(mode="after")` que lanza `ValueError(SUBSCRIPTION_EMPTY_UPDATE_MESSAGE)` si `not
  self.model_fields_set`. Hace pasar T072.
- [X] T077 [US5] `src/repositories/subscription_repository.py` (ampliar): `async update(id, changes:
  Mapping[str, Any]) -> Subscription | None`: `id > INT4_MAX` → `None`; `update(Subscription).where(id,
  status_id != DELETED).values(**changes).returning(Subscription.id)` con `execute_and_commit` (`None` → `None`)
  y `_reload`. Hace pasar T074 (el disparador actualiza `updated_at`).
- [X] T078 [US5] `src/services/subscription_service.py` (ampliar): `async update(id, data, token) ->
  SubscriptionView` con `changes = data.model_dump(exclude_unset=True)`; captura `UniqueViolationError` del
  índice → `SubscriptionNameAlreadyExistsError(changes["name"])`; `None` → `SubscriptionNotFoundError(id)`;
  luego `_fetch_counts(token, [id])` y la vista. Hace pasar T073.
- [X] T079 [US5] `src/routers/subscriptions.py` (ampliar): operación `update_subscription`:
  `@router.patch("/{subscription_id}", response_model=SubscriptionRead, operation_id="update_subscription",
  summary="Actualizar una suscripción", **protected(SUBSCRIPTIONS_UPDATE, responses={404: NOT_FOUND, 409:
  NAME_CONFLICT, 422: VALIDATION_ERROR}))` con `SubscriptionIdPath`, `Annotated[SubscriptionUpdate,
  Body(openapi_examples=UPDATE_EXAMPLES)]` y `BearerTokenDep`; descripción terminada en
  «**Permiso requerido: `subscriptions:update`.**». Definir `UPDATE_EXAMPLES` (el ejemplo `precio` del OpenAPI).
  Hace pasar T075.

**Checkpoint**: crear, listar, consultar y actualizar funcionan. `uv run pytest` en verde.

---

## Phase 8: User Story 6 - Cambiar el estatus de una suscripción (Priority: P2)

**Goal**: pasar una suscripción vigente entre Activa, Inactiva y Bloqueada, en cualquier dirección y tenga o
no clínicas.

**Independent Test**: Activa → Inactiva → Bloqueada → Activa comprobando el estatus en el catálogo; pedir el
estatus que ya tiene (409); pedir `4`, un número desconocido o un tipo equivocado (422); cambiar el estatus de
una suscripción con clínicas (se permite y **no** se consulta a clínicas para decidirlo).

### Tests for User Story 6 (escribirlos primero; deben fallar)

- [X] T080 [P] [US6] `tests/unit/test_subscription_dtos.py` (ampliar, `SubscriptionStatusChange`):
  `status_id` obligatorio, entero **estricto** (`Field(strict=True)`) con `extra="forbid"`: `1`, `2` y `3`
  son válidos; `4`, `0` y `99` fallan con «El estatus debe ser uno de los que admite esta operación (1, 2 o
  3).»; `"2"`, `2.5`, `true`, `"x"`, `null` y ausente fallan con «El estatus es obligatorio y debe ser un
  número entero.» (**`true` no puede aceptarse como 1**: verificado que `Literal[1, 2, 3]` sí lo acepta); un
  campo extra falla como no permitido.
- [X] T081 [P] [US6] `tests/unit/test_subscription_service.py` (ampliar): `change_status(id, data, token)` llama a
  `repository.change_status(id, to_status_id)`; si devuelve la fila, responde con la vista y el conteo; si
  devuelve `None` lee `get_current_by_id`: ausente/Eliminada → `SubscriptionNotFoundError`; con el mismo
  estatus → `SubscriptionStatusUnchangedError(id, subscription.status.name)`; si otra petición cambió el
  estatus entre las dos lecturas, repite la secuencia **una** vez y, si aún no puede decidir, lanza el 409 con el
  estatus vigente; **no** llama al API de clínicas para decidir; sí la consulta después para devolver
  `clinics_count` (con degradación a `None`).
- [X] T082 [P] [US6] `tests/integration/test_subscription_repository.py` (ampliar): `change_status` pasa de cada
  estatus 1, 2 y 3 a cualquier otro de ellos y de uno añadido a mano (id 5) a 1, 2 o 3, con **una** sola
  sentencia y devolviendo la fila recargada; pedir el estatus actual → `None` sin cambios; sobre una Eliminada o
  inexistente → `None`; `id > INT4_MAX` → `None` sin consultar; `get_status_id` devuelve el estatus de
  cualquier suscripción (incluida la Eliminada) o `None` si no existe; **dos cambios simultáneos al mismo
  estatus** (`asyncio.gather`, sesiones propias) → exactamente uno devuelve la fila y el otro `None`;
  `updated_at` cambia.
- [X] T083 [US6] `tests/contract/test_subscriptions_api.py` (ampliar): `PATCH
  /api/v1/subscriptions/{id}/status` con `{"status_id": 2}` → 200 con `status == {"id": 2, "name":
  "Inactiva"}` y el catálogo la muestra así; Activa → Inactiva → Bloqueada → Activa; repetir el mismo
  estatus → 409 `subscription_status_unchanged` con «La suscripción con el identificador 1 ya tiene el
  estatus Inactiva.»; `{"status_id": 4}` y `{"status_id": 99}` y `{"status_id": true}` → 422 con `field:
  "status_id"` (`true` jamás se toma por 1); `{}`, `{"status_id": "x"}` y un campo extra → 422; Eliminada e
  inexistente → 404; con clínicas asignadas (conteo de la simulación) el cambio a Inactiva o Bloqueada se
  permite (200) y la simulación de clínicas se consulta **solo después**, para la respuesta; con el API de
  clínicas caído el cambio funciona con `clinics_count: null`; el cambio actualiza `updated_at`; sin
  `subscriptions:update` → 403 y no cambia nada.

### Implementation for User Story 6

- [X] T084 [US6] `src/dtos/subscription.py` (ampliar): `SubscriptionStatusChange` con
  `ConfigDict(extra="forbid")` y `status_id: Annotated[int, Field(strict=True)]` con un
  `@field_validator("status_id")` que lanza `ValueError(SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE)` si el
  valor no está en `(1, 2, 3)` (estricto: `true`, `"2"` y `2.5` fallan por tipo; verificado) (descripción:
  «1 Activa, 2 Inactiva o 3 Bloqueada. Eliminar tiene su propia operación.»). Hace pasar T080.
- [X] T085 [US6] `src/repositories/subscription_repository.py` (ampliar): `async change_status(id, to_status_id) ->
  Subscription | None` con **una** sentencia: `update(Subscription).where(Subscription.id == id,
  Subscription.status_id != SubscriptionStatus.DELETED, Subscription.status_id != to_status_id)
  .values(status_id=to_status_id).returning(Subscription.id)` vía `execute_and_commit` y `_reload`; y `async
  get_status_id(id) -> int | None` (`select(Subscription.status_id)`; `INT4_MAX` como en el resto). Hace pasar
  T082.
- [X] T086 [US6] `src/services/subscription_service.py` (ampliar): `async change_status(id, data, token) ->
  SubscriptionView` según T081 (nunca consulta a clínicas para decidir). Hace pasar T081.
- [X] T087 [US6] `src/routers/subscriptions.py` (ampliar): operación `change_subscription_status`:
  `@router.patch("/{subscription_id}/status", response_model=SubscriptionRead,
  operation_id="change_subscription_status", summary="Cambiar el estatus de una suscripción",
  **protected(SUBSCRIPTIONS_UPDATE, responses={404: NOT_FOUND, 409: STATUS_UNCHANGED, 422: VALIDATION_ERROR}))`
  con `Annotated[SubscriptionStatusChange, Body(openapi_examples={"inactivar": …})]`; descripción terminada en
  «**Permiso requerido: `subscriptions:update`.**». Definir `STATUS_UNCHANGED` (409, ejemplo `sin_cambio` del
  OpenAPI). Hace pasar T083.

**Checkpoint**: crear, listar, consultar, actualizar y cambiar el estatus funcionan. `uv run pytest` en verde.

---

## Phase 9: User Story 7 - Eliminar una suscripción (Priority: P3)

**Goal**: dar de baja de forma lógica una suscripción **sin clínicas**, rechazando la baja si tiene clínicas o
si no puede comprobarse.

**Independent Test**: eliminar una sin clínicas (204; ya no aparece, no se consulta, no se actualiza y su
nombre queda libre); intentar eliminar una con clínicas (409; sigue en el catálogo); repetirlo con el API de
clínicas inaccesible (503; sigue en el catálogo); eliminar una inexistente (404).

### Tests for User Story 7 (escribirlos primero; deben fallar)

- [X] T088 [P] [US7] `tests/unit/test_subscription_service.py` (ampliar): `delete(id, token)`: lee con
  `get_current_by_id` (ausente → `SubscriptionNotFoundError` **sin** llamar a clínicas); consulta `get_counts(token,
  [id])`; `ClinicsApiUnavailable` → `ClinicsCheckUnavailableError(id)` y **no** se llama a `soft_delete`; conteo
  ≥ 1 → `SubscriptionHasClinicsError(id)` y no se llama a `soft_delete`; conteo ausente (0 clínicas) → llama a
  `soft_delete`; `soft_delete` devuelve `False` (otra petición la eliminó antes) → `SubscriptionNotFoundError`.
- [X] T089 [P] [US7] `tests/integration/test_subscription_repository.py` (ampliar): `soft_delete` pone el estatus 4 y
  devuelve `True`, **conserva** la fila y sus datos, actualiza `updated_at`, y a partir de ahí `list_current` y
  `get_current_by_id` no la ven; sobre una Eliminada o inexistente devuelve `False`; `id > INT4_MAX` → `False`
  sin consultar; **dos bajas simultáneas** de la misma suscripción (`asyncio.gather`) → exactamente una
  devuelve `True`; el nombre de la eliminada se puede reutilizar en una nueva.
- [X] T090 [US7] `tests/contract/test_subscriptions_api.py` y `tests/contract/test_clinics_degradation.py`
  (ampliar): `DELETE /api/v1/subscriptions/{id}` sin clínicas (la simulación no la lista) → 204 **sin
  cuerpo**; después: no aparece en el listado, `GET` → 404, `PATCH` y `PATCH …/status` → 404, un `DELETE`
  repetido → 404, y se puede crear otra con el mismo nombre; con clínicas (`/__test__/counts {"1": 3}`) →
  409 `subscription_has_clinics` con «No se puede eliminar la suscripción con el identificador 1 porque
  tiene clínicas asignadas.» y la suscripción sigue en el catálogo con su estatus; con **cada** modo de
  falla de la simulación de clínicas (`unavailable`, `unauthorized`, `forbidden`, `malformed`,
  `negative_count`, `unrequested_id`, `duplicate_id`, `not_json`, `slow` con el cliente de 0,2 s) → 503
  `clinics_check_unavailable` con el mensaje del catálogo y la suscripción **no** se elimina (SC-009);
  inexistente → 404 (sin llamar a clínicas); sin `subscriptions:delete` → 403 y no se elimina; el token que
  llega a la simulación de clínicas es el de la persona; y el cuerpo del 503 `clinics_check_unavailable` es
  **exactamente** el mensaje del catálogo, sin dirección ni texto de la simulación.

### Implementation for User Story 7

- [X] T091 [US7] `src/repositories/subscription_repository.py` (ampliar): `async soft_delete(id) -> bool`:
  `id > INT4_MAX` → `False`; `update(Subscription).where(Subscription.id == id, Subscription.status_id !=
  SubscriptionStatus.DELETED).values(status_id=SubscriptionStatus.DELETED).returning(Subscription.id)` con
  `execute_and_commit`; `True` si devolvió fila. Docstring: la condición hace atómica la baja (con solicitudes
  simultáneas solo una la encuentra) y ninguna fila se borra. Hace pasar T089.
- [X] T092 [US7] `src/services/subscription_service.py` (ampliar): `async delete(id, token) -> None` según T088,
  en este orden: (1) `get_current_by_id` o `SubscriptionNotFoundError`; (2) `get_counts(token, [id])` capturando
  `ClinicsApiUnavailable` → `ClinicsCheckUnavailableError(id)` (a diferencia de las lecturas, **no** se degrada:
  escritura destructiva que falla cerrada, R7); (3) `counts.get(id, 0) >= 1` → `SubscriptionHasClinicsError(id)`;
  (4) `soft_delete` y, si devuelve `False`, `SubscriptionNotFoundError(id)`. Nunca mantiene una transacción
  abierta mientras espera al API de clínicas. Hace pasar T088.
- [X] T093 [US7] `src/routers/subscriptions.py` (ampliar): operación `delete_subscription`:
  `@router.delete("/{subscription_id}", status_code=204, response_class=Response,
  operation_id="delete_subscription", summary="Eliminar una suscripción (baja lógica)",
  **protected(SUBSCRIPTIONS_DELETE, responses={404: NOT_FOUND, 409: HAS_CLINICS, 422: VALIDATION_ERROR, 503:
  DELETE_UNAVAILABLE}))`, donde `DELETE_UNAVAILABLE` documenta **los dos** 503 (`authorization_unavailable` y
  `clinics_check_unavailable`) como en [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml);
  devuelve `Response(status_code=204)`; descripción terminada en «**Permiso requerido: `subscriptions:delete`.**».
  Definir `HAS_CLINICS` (409, ejemplo `con_clinicas` del OpenAPI). Hace pasar T090.

**Checkpoint**: las 6 operaciones funcionan. `uv run pytest` en verde.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: cobertura de permisos, contrato OpenAPI, pruebas de punta a punta con Newman, documentación y
validación final.

### Pruebas transversales (antes de cerrar)

- [X] T094 [P] `tests/contract/test_permission_coverage.py` (Principio V y VIII): recorre `app.routes` (solo
  `APIRoute`) y el OpenAPI generado; falla si una ruta **no** tiene `x-required-permission` y no está en la
  lista de excepciones públicas (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`); y compara las
  rutas con `EXPECTED_PERMISSIONS` (la matriz de
  [contracts/permission-matrix.md](contracts/permission-matrix.md): `list_subscriptions` y
  `get_subscription` → `subscriptions:read`; `create_subscription` → `subscriptions:write`;
  `update_subscription` y `change_subscription_status` → `subscriptions:update`; `delete_subscription` →
  `subscriptions:delete`) para que **ni sobre ni falte** ninguna operación. Además, para **cada una de las 6
  operaciones** comprueba con la simulación del API de usuarios: sin token → 401, con token inválido → 401,
  con token sin el permiso → 403, con el API de usuarios caído → 503, y que en los cuatro casos no se creó
  ni cambió nada (SC-002); y que cada operación pide a la simulación **exactamente** su permiso. Esta prueba
  cierra la historia US2 (SC-002) para las rutas reales; la fase 3 solo verificó la mecánica con una ruta de
  sondeo (T034).
- [X] T095 [P] `tests/contract/test_openapi_contract.py`: `create_app().openapi()` se genera sin errores; es
  OpenAPI 3.x con `info.version == "1.0.0"`; contiene exactamente las 6 `operationId` y rutas de
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) (lista fija en la prueba: no se
  añade PyYAML); cada operación tiene `security == [{"BearerAuth": []}]`, `x-required-permission` y `summary`,
  `description` con «Permiso requerido: `…`» y respuestas 401, 403 y 503 (más 404/409/422 según
  [contracts/error-catalog.md](contracts/error-catalog.md), «Qué operaciones pueden devolver cada código»);
  `components.securitySchemes.BearerAuth` es `{"type": "http", "scheme": "bearer"}`; los esquemas
  `SubscriptionRead`, `SubscriptionCreate`, `SubscriptionUpdate`, `SubscriptionStatusChange`, `StatusRead` y
  `ErrorResponse` existen; `ErrorResponse.code` enumera los 12 códigos; `monthly_price` de `SubscriptionRead`
  es de tipo `string`; las rutas de documentación **no** declaran seguridad.

### Pruebas de punta a punta (Postman con Newman; complementan a pytest, no lo sustituyen)

- [X] T096 [P] `tests/postman/package.json` (`"private": true`; `devDependencies: {"newman": "^6"}`; script
  `"e2e": "newman run collections/MailySoft-System-Suscripciones.postman_collection.json -e
  environments/e2e.postman_environment.json -r cli,junit --reporter-junit-export reports/junit.xml"`) y
  `tests/postman/environments/e2e.postman_environment.json` (`baseUrl` = `http://127.0.0.1:8011`,
  `usersStubUrl` = `http://127.0.0.1:8012`, `clinicsStubUrl` = `http://127.0.0.1:8013`; `accessToken`,
  `subscriptionId` y `otherSubscriptionId` **vacías**) y `dev.postman_environment.json` (`baseUrl` =
  `http://127.0.0.1:8010`, solo para explorar a mano). Ejecutar `npm install --prefix tests/postman` para generar
  `package-lock.json` (que sí se versiona; `node_modules/` y `reports/` no).
- [X] T097 [P] `tests/postman/docker-compose.e2e.yml` según [contracts/e2e-stubs.md](contracts/e2e-stubs.md) §2: sobre
  `docker-compose.yml`, `db` con `ports: !override []`; servicios nuevos `users-api-stub` y `clinics-api-stub`
  (`build: .`, `command: ["uvicorn", "app:app", "--app-dir", "/stub", "--host", "0.0.0.0", "--port", "8080"]`,
  volumen `./tests/stubs/users_api:/stub:ro` y `./tests/stubs/clinics_api:/stub:ro`, puertos
  `127.0.0.1:${E2E_USERS_STUB_PORT:-8012}:8080` y `127.0.0.1:${E2E_CLINICS_STUB_PORT:-8013}:8080`, `healthcheck` con
  `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/__test__/calls', timeout=3)"`);
  `api` con `depends_on` de ambas simulaciones, `USERS_API_BASE_URL: http://users-api-stub:8080`,
  `CLINICS_API_BASE_URL: http://clinics-api-stub:8080`, `ports: !override ["127.0.0.1:${E2E_API_PORT:-8011}:8000"]` y
  `healthcheck` sobre `http://127.0.0.1:8000/openapi.json`. Comentario de cabecera con los comandos de
  levantar y desmontar (proyecto `maily-system-e2e`) y el requisito de Docker Compose 2.24 o superior.
- [X] T098 `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json` (colección v2.1;
  esquema `https://schema.getpostman.com/json/collection/v2.1.0/collection.json`; autenticación Bearer **solo**
  con `{{accessToken}}`; **cada petición con `operationId` se llama `"<operationId>: <descripción>"`**, p. ej.
  `"create_subscription: crear Pro"`, y cada una lleva pruebas `pm.test` sobre estado y forma): carpetas **0.
  Preparación** (reinicia las dos simulaciones con `POST /__test__/reset`; registra el token `e2e-token` con los
  cuatro permisos en la de usuarios; fija `accessToken`; fija `{}` conteos en la de clínicas; estas peticiones se
  llaman `"setup: …"`) y **1. Catálogo** (listar → `[]`; crear «Pro» con `monthly_price` 4500 y dos funciones →
  201, estatus Activa, `clinics_count` 0 y guarda `subscriptionId`; listar → aparece).
- [X] T099 `tests/postman/collections/…postman_collection.json` (ampliar): carpetas **2. Consultar y actualizar**
  (`get_subscription`; `update_subscription` con el precio; crear otra con nombre «Otra» y guardar
  `otherSubscriptionId`; renombrar al nombre de otra → 409; `update_subscription` con campo no permitido → 422)
  y **3. Cambiar el estatus** (Activa → Inactiva → Bloqueada → Activa con comprobación del estatus del catálogo;
  repetir → 409 `subscription_status_unchanged`; `status_id` 4 → 422).
- [X] T100 `tests/postman/collections/…postman_collection.json` (ampliar): carpetas **4. Eliminar** (con
  `POST {{clinicsStubUrl}}/__test__/counts` de `subscriptionId` = 3 → `delete_subscription` 409
  `subscription_has_clinics`; con conteos `{}` → 204; luego `get_subscription` → 404; crear otra con el nombre
  liberado → 201), **5. Control de acceso** (sin token → 401; token inválido → 401; persona sin permiso →
  403; con `faults unavailable` en la simulación de usuarios → 503 `authorization_unavailable`; `GET {{baseUrl}}/docs`
  y `/openapi.json` → 200 sin token) y **6. Degradación de clínicas** (con `faults unavailable` en la de clínicas:
  `list_subscriptions` → 200 con `clinics_count: null`; `delete_subscription` → 503 `clinics_check_unavailable`;
  limpiar con `reset`). Al terminar, `collection` y `environments` no contienen identificadores ni valores
  actuales (solo variables vacías) ni ningún secreto.
- [X] T101 [P] `tests/contract/test_postman_collection.py` (parte de `uv run pytest`; no necesita Docker ni Node.js):
  carga la colección y compara el conjunto de `operationId` de sus peticiones (la parte del nombre antes de
  «: », ignorando la carpeta «0. Preparación» y las que empiezan por `setup`) con el de `create_app().openapi()`:
  falla **nombrando** las operaciones que faltan y las que sobran; comprueba que el bloque de autenticación
  solo referencia `{{accessToken}}` y que ningún archivo de `tests/postman/` (salvo `node_modules/`) contiene
  un JWT (patrón `eyJ[A-Za-z0-9_-]{10,}\.`) ni la cadena `secret`.

### Documentación y validación final

- [X] T102 `README.md` (reemplaza el título provisional): qué es el servicio y su primer dominio
  (suscripciones); qué incluye hoy (las 6 operaciones, los estatus, el control de acceso delegado al API de
  usuarios y el conteo de clínicas del API de clínicas, con su degradación); **requisitos** (Docker con
  Compose 2.24+, uv y Python 3.14+, Node.js solo para Newman); **puesta en marcha** (copiar `.env.example`,
  `docker compose up -d db`, `docker compose run --rm migrate`, `docker compose up -d api`; `uv sync` y `uv
  run uvicorn src.main:app --port 8010` sin Docker para la API) **con una advertencia**: sin
  `USERS_API_BASE_URL` y `CLINICS_API_BASE_URL` el servicio no arranca, y sin el API de usuarios todas las
  operaciones responden 503; **pruebas** (`uv run pytest`; la base de pruebas debe terminar en `_test`);
  **pruebas de punta a punta** con Newman (comandos de [quickstart.md](quickstart.md) nivel 3, con la
  advertencia de no apuntarla nunca a datos reales); **estructura** (árbol de `src/`, `tests/` y
  `alembic/`); y enlaces a `specs/001-subscriptions-api/` y a la constitución. Incluye una sección de
  **configuración** con `USERS_API_*`, `CLINICS_API_*` y `CORS_ALLOWED_ORIGINS`, y la advertencia de que una
  dirección `http://` no local envía el token sin cifrar (FR-024).
- [X] T103 Verificación de la suite y de la base de datos (archivos: `tests/`, `alembic/versions/`, `src/main.py`):
  `docker compose up -d db`; `uv run pytest` (toda la suite en verde; anotar cuántas pruebas pasan); `uv run alembic downgrade base && uv run alembic upgrade head`;
  `uv run alembic check` («No new upgrade operations detected»); `uv run python -c "from src.main import app;
  app.openapi()"`; `uv run pytest tests/unit/test_layering.py`. Corregir lo que falle en el archivo que corresponda.
- [X] T104 Verificación con Docker (archivos: `Dockerfile`, `docker-compose.yml`, `.env.example`): `docker compose build`; `docker compose up -d db`; `docker compose run --rm migrate`;
  comprobar que `docker compose up api` **no arranca** sin `USERS_API_BASE_URL`/`CLINICS_API_BASE_URL` y que el
  mensaje de los registros nombra las variables que faltan sin mostrar valores; y que `docker compose run --rm api
  python -c "import src.main"` funciona. Anotar el resultado.
- [X] T105 Ejecutar [quickstart.md](quickstart.md) **nivel 2** (levantar la pila `maily-system-e2e`,
  registrar un token, recorrer los comandos con `curl.exe` y comprobar los códigos de cada línea) y **nivel
  3** (`npm ci --prefix tests/postman` y `npm run e2e --prefix tests/postman`, salida `0`); desmontar con
  `down -v`. Corregir cualquier desajuste entre la guía, los contratos y el comportamiento real, en el
  documento o el código que corresponda. SC-007 (crear una suscripción y verla en el catálogo en menos de 1
  minuto, sin conocimientos técnicos) se verifica **a mano** con este recorrido: anotar el tiempo.
- [X] T106 Revisión final contra `.specify/memory/constitution.md` v1.0.0 (sin cambios de archivos salvo hallazgos): (a) Principio I:
  `test_layering.py` en verde y ningún Router importa Repositories ni sesiones; (b) Principio VIII: ningún
  registro ni respuesta contiene el token (buscar `Authorization` y `Bearer` en `src/` y en los registros de una
  ejecución de prueba) y toda ruta declara permiso; (c) Principio VI: `project-definition/DATA_SCHEMA.md`
  coincide con las migraciones; (d) Principio VII: no hay identificadores ni códigos en español ni mensajes en
  inglés en las respuestas; (e) `git status --short` solo muestra archivos de esta feature. Marcar los criterios de
  [checklists/requirements.md](checklists/requirements.md) que sigan válidos y resumir el resultado.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** todas las historias.
- **US2 (Phase 3)**: depende de Foundational. **Es la puerta de todas las operaciones** (`require_permission`,
  `protected`, `src/main.py` y `src/dependencies.py` nacen aquí), por eso va antes que US1 aunque ambas sean P1.
- **US1 (Phase 4)**: depende de US2 (usa `protected` y la aplicación) y de Foundational.
- **US3 (Phase 5), US4 (Phase 6), US5 (Phase 7), US6 (Phase 8) y US7 (Phase 9)**: dependen de US1 (el
  `SubscriptionView`, `_fetch_counts`, el Router y los fixtures de `api`) y entre sí **solo** por archivos
  compartidos.
- **Polish (Phase 10)**: depende de todas las historias deseadas (T094 y T101 necesitan las 6 operaciones).

### Archivos compartidos (límite real del paralelismo)

Las historias US1 a US7 **comparten** `src/routers/subscriptions.py`, `src/services/subscription_service.py`,
`src/repositories/subscription_repository.py`, `src/dtos/subscription.py` y los archivos de pruebas
`tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_service.py`,
`tests/integration/test_subscription_repository.py` y `tests/unit/test_subscription_dtos.py`. Por eso se
implementan **en el orden de las fases**; el paralelismo entre historias exigiría coordinar los cambios sobre
esos archivos. Cada historia, una vez integrada, se prueba y se demuestra de forma independiente con los
criterios de su fase.

### Within Each User Story

- Las pruebas se escriben primero y **deben fallar**; después DTO/modelos → Repository → Service → Router.
- Cada fase termina con `uv run pytest` en verde (además de la prueba de capas, que no puede romperse).

### Parallel Opportunities

- Setup: T003 a T008 son [P] (T002 los precede solo para `uv sync`).
- Foundational: los tests T010–T016 son [P] entre sí (tras T009); T019, T021, T022, T026, T027 y T028 son [P].
- US2: T029–T032 son [P]; T035 es [P].
- US1: T042–T046 son [P]; T049 y T050 son [P]; T052 es [P] con T051.
- US3–US7: dentro de cada fase, las pruebas de archivos distintos son [P] (DTOs, Service y Repository).
- Polish: T094–T097 y T101 son [P]; T098–T100 editan el **mismo** archivo y van en orden.

---

## Parallel Example: User Story 2

```bash
# Escribir a la vez las pruebas de la historia (archivos distintos):
Task: "Simulación del API de usuarios en tests/stubs/users_api/app.py"
Task: "Pruebas del cliente en tests/contract/test_users_api_client.py"
Task: "Pruebas del servicio en tests/unit/test_authorization_service.py"
Task: "Pruebas de la dependencia en tests/unit/test_security.py"

# Después, los módulos independientes:
Task: "Errores de integración en src/integrations/errors.py"
Task: "Documentación OpenAPI compartida y protected() en src/routers/openapi_docs.py"
```

---

## Implementation Strategy

### MVP First (US2 + US1)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational).
2. Completar Phase 3 (US2: control de acceso) y Phase 4 (US1: catálogo).
3. **DETENERSE y validar**: `uv run pytest`; levantar la pila del nivel 2 de [quickstart.md](quickstart.md) y
   comprobar el listado, el 401/403/503 y la degradación de clínicas. El catálogo se puede leer pero aún no
   escribir; sirve para que el Front y los demás sistemas consuman los planes.

### Incremental Delivery

1. MVP → demostrable (leer el catálogo con control de acceso).
2. + US3 (crear) → ya se puede formar el catálogo desde la API.
3. + US4 (consultar) y US5 (actualizar) → el formulario de edición de cada tarjeta funciona.
4. + US6 (cambiar el estatus) → se pueden retirar o suspender planes.
5. + US7 (eliminar) → baja lógica con la regla de clínicas.
6. Polish → cobertura de permisos, contrato OpenAPI, Newman y documentación.

---

## Notes

- [P] = archivos distintos y sin dependencias abiertas; [Story] = trazabilidad con la spec.
- Cada historia debe poder completarse y probarse; el límite real son los archivos compartidos (ver arriba).
- Verificar que las pruebas **fallan** antes de implementar y que pasan después.
- No hacer commits salvo que la persona los pida; si los pide, un commit por tarea o grupo lógico.
- Evitar: tareas vagas, conflictos de archivo dentro de una misma fase, y cualquier prueba que llame a un API real.

---

description: "Task list for feature 003-platform-dashboard (Dashboard de Plataforma, «Panel de Maily»)"
---

# Tasks: Dashboard de Plataforma («Panel de Maily»)

**Input**: Design documents from `/specs/003-platform-dashboard/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.0.0** vigente, la feature 001 ya implementada (el servicio de suscripciones, sus pruebas y
sus simulaciones), Docker Desktop con Compose 2.24 o superior, `uv` con Python 3.14 o superior y, solo para la
colección de punta a punta, Node.js con npm.

**Tests**: Incluidas. La spec las exige (FR-034 a FR-037) y el Principio V también. Se sigue TDD dentro de cada
historia: las tareas de pruebas se escriben primero y **deben fallar** antes de implementar (cuando la prueba
necesita código que aún no existe, falla al importarlo; eso cuenta). La excepción es la fase de la historia 2,
que **no añade código de producción** (ver su encabezado). **Ninguna prueba llama a un API real**: usan la
simulación `tests/stubs/users_api` y dobles en memoria de la fuente de datos.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md), en el orden de prioridad:
US1 y US2 (P1), US3, US4 y US5 (P2) y US6 (P3). El **MVP** es Setup + Foundational + US1 + US2: un dashboard
protegido que devuelve el resumen con la cantidad de clínicas por defecto.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US6); sin etiqueta en Setup, Foundational y
  Polish
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones y evidencia: [research.md](research.md) (R1 a R15)
- Registros, vista, DTOs, configuración y las 12 clínicas ficticias: [data-model.md](data-model.md)
- Contrato HTTP (OpenAPI 3.1, validado): [contracts/openapi-dashboard.yaml](contracts/openapi-dashboard.yaml)
- Operación → permiso: [contracts/permission-matrix.md](contracts/permission-matrix.md)
- Errores que aplican, mensaje de validación y precedencia: [contracts/error-catalog.md](contracts/error-catalog.md)
- Puerto de las fuentes de datos y degradación: [contracts/data-sources.md](contracts/data-sources.md)
- Colección de Postman y sus pruebas guardianas: [contracts/e2e-collection.md](contracts/e2e-collection.md)
- Ajustes a pruebas existentes (A1 a A3 y B1): sección «Ajustes a las pruebas existentes» de [plan.md](plan.md)
- Guía de validación: [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json` (debe seguir en
  `specs/003-platform-dashboard`); escribir tokens, contraseñas o secretos reales en cualquier archivo; añadir
  dependencias; crear migraciones, modelos ORM o repositorios (FR-020).
- **No se toca** (FR-032): `alembic/`, `src/models/`, `src/repositories/`, `src/database/`,
  `project-definition/`, `tests/stubs/`, `tests/postman/environments/`, `tests/postman/docker-compose.e2e.yml`,
  las dos colecciones de Postman existentes ni ninguna operación, DTO o prueba de suscripciones. **Las únicas
  pruebas existentes que se editan son las cuatro del plan**: A1 (T023), A2 (T015), A3 (T016 y T055) y B1 (T045),
  y solo de la forma que describe cada tarea. Si otra prueba existente falla, **no se arregla editándola**: se
  corrige el código nuevo y, si el choque es real, se avisa a la persona.
- **Idioma** (Principio VII): identificadores, campos de la API y códigos de error en inglés; mensajes,
  descripciones de OpenAPI y documentos en español; comentarios y docstrings en inglés; los registros del
  servicio en inglés.
- **Mensajes exactos**: el único mensaje de validación nuevo sale de
  [contracts/error-catalog.md](contracts/error-catalog.md); no se parafrasea.
- **Pruebas**: las del dashboard **no necesitan** PostgreSQL ni Docker (`uv run pytest -k dashboard`). Las que
  sí lo necesitan son las ya existentes: `docker compose up -d db` y `uv run pytest [ruta]` (la base de pruebas
  es `TEST_DATABASE_URL` y su nombre debe terminar en `_test`).
- **Todo lo que hace I/O es `async`** (Principio III), incluidos los proveedores de `src/dependencies.py`.
- **Capas** (Principio I): el Router no importa integraciones, repositorios, base de datos ni modelos; el
  Service no importa `fastapi` ni `sqlalchemy`; las integraciones solo usan `dataclass` y biblioteca estándar.
  `tests/unit/test_layering.py` debe seguir en verde en cada fase.
- **Constantes** (se definen una sola vez, con nombre, en el módulo que se indica):

  | Constante | Valor | Módulo |
  |---|---|---|
  | `DASHBOARD_READ` | `"dashboard:read"` | `src/security.py` |
  | `DASHBOARD_PATH` | `"/api/v1/dashboard"` | `src/routers/dashboard.py` |
  | `MAX_RECENT_CLINICS` | `10` (fijo, no configurable) | `src/services/dashboard_service.py` |
  | `ALLOWED_RECENT_CLINICS_LIMITS` | `(3, 5, 10)`; el valor por defecto de `dashboard_recent_clinics_limit` es `5` | `src/config.py` |
  | `HUGE_LIMIT` | `10**18` (lo que devuelve la lectura de `limit` para un entero de más de 18 cifras significativas) | `src/routers/dashboard.py` |
  | `DASHBOARD_LIMIT_INVALID_MESSAGE` | `"El parámetro «limit» debe ser un número entero mayor o igual que 1."` | `src/messages.py` |
  | `DUMMY_DASHBOARD_NOTICE` | `"The dashboard is returning DUMMY data (phase 1): the clinics, doctors, patients and users are fictitious and must be replaced by the real sources before production"` (no contiene `BASE_URL`) | `src/main.py` |
  | Registro de falla de una fuente | `"Dashboard source unavailable: %s"` con el nombre de la consulta (`clinic_counts`, `recent_clinics`, `doctors_total`, `patients_total`, `users_total`); nivel `WARNING`; nunca el token ni el texto de la excepción | `src/services/dashboard_service.py` |
  | Estatus de clínica ficticios | `1` «Activa», `2` «En prueba», `3` «Suspendida» | `src/integrations/dummy_dashboard_source.py` |

- **Interfaces compartidas entre tareas** (usar exactamente estos nombres):
  - `src/integrations/errors.py`: `DashboardSourceUnavailable(IntegrationError)`, sin argumentos; su mensaje
    es genérico (`"The dashboard data source did not answer as expected"`).
  - `src/integrations/dashboard_source.py`: `ClinicStatusRecord(id: int, name: str)`,
    `ClinicRecord(id: UUID, name: str, created_at: datetime, status: ClinicStatusRecord)`,
    `ClinicCounts(total: int, active: int, trial: int)` (las tres `@dataclass(frozen=True, slots=True)`) y
    `class DashboardSource(Protocol)` con `is_dummy: bool` y `async clinic_counts(token) -> ClinicCounts`,
    `async recent_clinics(token, limit) -> list[ClinicRecord]`, `async doctors_total(token) -> int`,
    `async patients_total(token) -> int`, `async users_total(token) -> int`.
  - `src/integrations/dummy_dashboard_source.py`: `DUMMY_CLINICS` (tupla de 12 `ClinicRecord`) y
    `DummyDashboardSource(clinics=DUMMY_CLINICS, doctors=37, patients=1284, users=52)` con `is_dummy = True`.
  - `src/services/dashboard_service.py`: `DashboardView` (dataclass congelada con `total_clinics`,
    `active_clinics`, `trial_clinics`, `total_doctors`, `total_patients`, `total_users`: `int | None`, y
    `recent_clinics: list[ClinicRecord] | None`) y `DashboardService(source: DashboardSource, default_limit: int)`
    con `async get(token: str, requested_limit: int | None = None) -> DashboardView`.
  - `src/dtos/dashboard.py`: `ClinicStatusRead`, `RecentClinicRead`, `DashboardRead`.
  - `src/routers/dashboard.py`: `router`, `DASHBOARD_PATH`, `requested_limit(request: Request) -> int | None`.
  - `src/dependencies.py`: `build_dashboard_source() -> DashboardSource`, `async get_dashboard_source()`,
    `async get_dashboard_service()`.
  - `src/config.py`: `DashboardSettings`, `get_dashboard_settings()` (con `lru_cache`) y
    `configuration_error_message(*errors: ValidationError)`.
  - `tests/dashboard_support.py`: `FakeDashboardSource`, `make_clinic(...)`, `DASHBOARD_URL`, `DashboardApi`.
  - `tests/contract/conftest.py`: la fixture `dashboard_api` (devuelve un `DashboardApi`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Comprobar el punto de partida. Esta feature no necesita herramientas ni dependencias nuevas.

- [X] T001 Verificar prerrequisitos y fijar la línea base (no modifica archivos): confirmar que
  `.specify/memory/constitution.md` termina en `**Version**: 1.0.0`; que `.specify/feature.json` contiene
  `"feature_directory": "specs/003-platform-dashboard"`; que `uv --version` y `docker --version` responden;
  levantar la base con `docker compose up -d db` y ejecutar `uv run pytest`. **Debe terminar en verde**: anotar
  cuántas pruebas pasan, porque al final de la feature deben pasar todas esas más las nuevas. Si hay fallos
  previos, **detenerse** y avisar. `git status --short` solo debe mostrar `specs/003-platform-dashboard/` y los
  dos `.ps1` sin seguimiento.
- [X] T002 [P] Confirmar que la simulación del API de usuarios ya acepta el permiso nuevo (no modifica
  archivos): `uv run python -c "from tests.stubs.users_api.app import PERMISSION_PATTERN as p; assert p.match('dashboard:read')"`
  debe terminar sin error. Así `tests/stubs/` no necesita cambios.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: El puerto de datos, la configuración del valor por defecto, el permiso y la infraestructura de
pruebas que usan **todas** las historias.

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase.

- [X] T003 [P] `src/integrations/errors.py`: añadir `class DashboardSourceUnavailable(IntegrationError)` con
  docstring (`A dashboard data source did not answer as expected: that indicator is not available`), sin
  argumentos en el constructor y `super().__init__("The dashboard data source did not answer as expected")`.
  Mismo estilo que `ClinicsApiUnavailable`. El mensaje **nunca** incluye direcciones, cuerpos de error, tokens
  ni credenciales.
- [X] T004 [P] `src/integrations/dashboard_source.py`: el puerto de las fuentes de datos
  ([contracts/data-sources.md](contracts/data-sources.md), [data-model.md](data-model.md) sección 1). Solo
  biblioteca estándar (`dataclasses`, `datetime`, `typing.Protocol`, `uuid`); **sin** `fastapi`, `pydantic`,
  `sqlalchemy` ni `src.dtos`/`src.models`. Tres `@dataclass(frozen=True, slots=True)`:
  `ClinicStatusRecord(id: int, name: str)`, `ClinicRecord(id: UUID, name: str, created_at: datetime,
  status: ClinicStatusRecord)` (`created_at` **con zona horaria**; se documenta en el docstring) y
  `ClinicCounts(total: int, active: int, trial: int)`. Y `class DashboardSource(Protocol)` con el atributo
  `is_dummy: bool` y cinco métodos `async` que reciben `token: str` primero: `clinic_counts`,
  `recent_clinics(token, limit: int) -> list[ClinicRecord]`, `doctors_total`, `patients_total`,
  `users_total`. El docstring del puerto resume el contrato: `recent_clinics` devuelve **como máximo** `limit`
  clínicas, de la más nueva a la más antigua y, a igualdad de fecha, por `id` ascendente; toda consulta puede
  lanzar `DashboardSourceUnavailable`; `users_total ≥ doctors_total`.
- [X] T005 [P] `src/security.py`: añadir `DASHBOARD_READ = "dashboard:read"` debajo de las constantes de
  suscripciones, con el comentario `# Permission of the dashboard operation (specs/003-platform-dashboard/contracts/permission-matrix.md).`
  No tocar nada más del archivo.
- [X] T006 [P] Pruebas en `tests/unit/test_dashboard_config.py` (escribirlas **antes** de T007; deben fallar al
  importar `DashboardSettings`). Con una fixture `autouse` que borre `DASHBOARD_RECENT_CLINICS_LIMIT` del
  entorno (`monkeypatch.delenv`) y construya siempre con `_env_file=None`: (a) sin variable el valor es `5`;
  (b) variable vacía (`""`) → `5` (igual que las demás opcionales); (c) `"3"`, `"5"` y `"10"` dan 3, 5 y 10, y
  `" 5 "` (espacios en los extremos) da 5; (d) parametrizada, son **inválidos** `"4"`, `"0"`, `"1"`, `"11"`,
  `"-5"`, `"abc"`, `"5.5"`, `"5.0"`, `"05"`, `"+5"`, `"1e1"` y `" "`: lanzan `ValidationError` cuyo único
  error tiene `loc == ("dashboard_recent_clinics_limit",)`; (e) por código (`DashboardSettings(_env_file=None,
  dashboard_recent_clinics_limit=3)`) 3 vale y `4`, `True` y `5.0` no; (f) `configuration_error_message(error)`
  de un valor inválido con un texto reconocible (`"valor-secreto-9"`) contiene `DASHBOARD_RECENT_CLINICS_LIMIT`
  y **no** contiene el texto; (g) con un solo error el mensaje es idéntico al de antes (por ejemplo, para
  `USERS_API_BASE_URL` ausente: `"Configuración incompleta o no válida. Falta la variable de entorno USERS_API_BASE_URL."`);
  (h) `configuration_error_message(a, b)` con el error de una dirección ausente **y** el de la variable
  inválida nombra ambas variables y lleva el encabezado `"Configuración incompleta o no válida."` una sola vez.
- [X] T007 `src/config.py` (aditivo; cumple T006): `ALLOWED_RECENT_CLINICS_LIMITS = (3, 5, 10)`;
  `class DashboardSettings(BaseSettings)` con `dashboard_recent_clinics_limit: int = 5` y
  `model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)`; un
  `@field_validator("dashboard_recent_clinics_limit", mode="before")` que acepte **solo** el texto exacto
  `"3"`, `"5"` o `"10"` tras `str(value).strip()` (así `05`, `5.0`, `+5`, `True` y `1e1` fallan) y devuelva el
  `int`; si no, `raise ValueError("Only 3, 5 or 10 are allowed")` **sin incluir el valor**; `@lru_cache def
  get_dashboard_settings() -> DashboardSettings`. Cambiar `configuration_error_message(error)` por
  `configuration_error_message(*errors: ValidationError)`: recorrer todos los errores, juntar los problemas
  (mismos textos de antes: `Falta la variable de entorno X.` / `La variable de entorno X no es válida.`) y
  anteponer una sola vez `"Configuración incompleta o no válida. "`. Actualizar el docstring del módulo para
  mencionar `DashboardSettings`. Las llamadas existentes con un solo argumento siguen funcionando igual.
- [X] T008 [P] `tests/dashboard_support.py` (sin fixtures, igual que `tests/helpers.py`): (1)
  `make_clinic(n: int, *, created_at: datetime | None = None, status_id: int = 1, name: str | None = None) ->
  ClinicRecord`: `id = uuid.UUID(f"00000000-0000-4000-8000-{n:012x}")`, nombre por defecto
  `f"Clínica {n}"`, `created_at` por defecto `datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=n)` y estatus
  `ClinicStatusRecord(status_id, {1: "Activa", 2: "En prueba", 3: "Suspendida"}.get(status_id, "Otro"))`.
  (2) `FakeDashboardSource(*, clinics=(), counts: ClinicCounts | None = None, doctors=0, patients=0, users=0,
  fail: Iterable[str] = (), crash: Iterable[str] = (), honor_order: bool = True, is_dummy: bool = False)`:
  implementa las cinco consultas; `counts` por omisión se deriva de `clinics` (total, y las de estatus 1 y 2);
  `recent_clinics` devuelve el corte ordenado según el contrato (fecha descendente, `id` ascendente) salvo con
  `honor_order=False`, que devuelve la lista **tal cual, sin ordenar ni cortar** (para probar que el Service
  lo hace); las consultas cuyo nombre esté en `fail` lanzan `DashboardSourceUnavailable` **encadenada** con
  `from RuntimeError("SECRETO-INTERNO http://interno:9000")` (para comprobar que ese detalle no se filtra);
  las de `crash` lanzan `RuntimeError("boom")`; registra cada llamada en `self.calls: list[tuple[str, tuple]]` (nombre y
  argumentos, **incluido el token**); admite una barrera opcional `barrier: asyncio.Barrier | None` que cada
  consulta espera antes de responder (para probar el paralelismo). (3) `DASHBOARD_URL = "/api/v1/dashboard"`.
  (4) `class DashboardApi`: `__init__(app, client, anonymous, users_stub)`; `use_source(source)` (fija
  `app.dependency_overrides[get_dashboard_source]`, importando dentro de la función); `async get(query: str =
  "", **kwargs) -> httpx.Response` (GET con el cliente autenticado a `DASHBOARD_URL + query`); `async
  set_permissions(permissions)` (con `grant(users_stub, TEST_TOKEN, permissions)` de `tests/helpers.py`);
  `async grant_token(token, permissions, *, expired=False)`; `async users_fault(mode, count=1, delay=30)` y
  `async users_calls()` (como en la clase `Api` de `tests/helpers.py`). Importar la aplicación solo dentro de
  funciones para no fallar mientras `src/` esté incompleto.
- [X] T009 `tests/contract/conftest.py` (**archivo nuevo**; no existe hoy): la fixture `dashboard_api(users_stub,
  monkeypatch)` (async): (a) aísla la configuración: `monkeypatch.delenv("DASHBOARD_RECENT_CLINICS_LIMIT",
  raising=False)`, `monkeypatch.setitem(DashboardSettings.model_config, "env_file", None)` y
  `get_dashboard_settings.cache_clear()` antes y después; (b) crea `create_app()` y sustituye
  `get_users_api_client` por un proveedor que devuelva `UsersApiClient(users_stub, USERS_BASE_URL, 5.0)` (el
  código real del cliente y de `AuthorizationService` se ejercita); (c) registra `TEST_TOKEN` con
  `["dashboard:read"]` (`grant`); (d) crea dos `httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
  base_url="http://api.test")`, uno con `Authorization: Bearer {TEST_TOKEN}` y otro sin cabecera; (e) cede un
  `DashboardApi`. La fixture **no** debe depender de `engine`, `migrated_db` ni de PostgreSQL. Los imports de
  la aplicación van dentro de la fixture (como en `tests/conftest.py`). No debe ser `autouse` (el archivo
  afecta a todo `tests/contract/`).
- [X] T010 Checkpoint de la fase: `uv run pytest tests/unit/test_dashboard_config.py tests/unit/test_config.py
  tests/unit/test_main.py tests/unit/test_layering.py` en verde (los tres últimos ya existían y deben seguir
  igual), y `uv run python -c "import tests.dashboard_support, src.integrations.dashboard_source"` sin errores.

**Checkpoint**: Fundamentos listos: el puerto, el permiso, la configuración y las ayudas de prueba existen.

---

## Phase 3: User Story 1 - Ver el resumen general de la plataforma (Priority: P1) 🎯 MVP

**Goal**: `GET /api/v1/dashboard` devuelve, en una sola consulta, los seis indicadores y las clínicas recientes
(cantidad por defecto), en el contrato de [openapi-dashboard.yaml](contracts/openapi-dashboard.yaml), con datos
ficticios deterministas, sin datos personales y con `Cache-Control: no-store`. La ruta nace **protegida** con
`protected(DASHBOARD_READ)` (la historia 2 la verifica a fondo).

**Independent Test**: con una persona con `dashboard:read`, consultar sin parámetros: llegan 7 claves; seis
enteros (`12, 8, 3, 37, 1284, 52`); 5 clínicas (Santa Aurora, Del Valle, Horizonte, Dental Sonríe y San
Rafael) con UUID, nombre, fecha `…Z` y estatus; dos consultas seguidas dan el mismo cuerpo.

### Tests for User Story 1 (escribirlas primero; deben fallar) ⚠️

- [X] T011 [P] [US1] `tests/unit/test_dashboard_dtos.py`: (a) `DashboardRead` con los siete campos en `None` es
  válido y `model_dump(mode="json")` los incluye **todos** con `None`; omitir cualquiera lanza `ValidationError`
  (obligatorios, sin valor por defecto); (b) `DashboardRead.model_json_schema()` lista los siete en `required`
  y cada indicador es `anyOf` de `integer` y `null`; un conteo negativo (`-1`) es inválido; `recent_clinics`
  con 11 elementos es inválido (máximo 10); (c) `RecentClinicRead.model_validate(ClinicRecord(...))` lee los
  atributos de la `dataclass` y de su estatus anidado; (d) un `created_at` con zona `-06:00` sale como
  `"…T16:20:00Z"` (UTC con `Z`) y uno **sin zona** (ingenuo) es inválido; (e) `id` sale como UUID canónico en
  minúsculas; (f) `set(RecentClinicRead.model_fields) == {"id", "name", "created_at", "status"}`,
  `set(ClinicStatusRead.model_fields) == {"id", "name"}` y los siete campos exactos de `DashboardRead`
  (garantía de que no hay datos personales, FR-008).
- [X] T012 [P] [US1] `tests/unit/test_dummy_dashboard_source.py` (importa `DummyDashboardSource` y
  `DUMMY_CLINICS`; deben fallar al importar): (a) la tupla tiene 12 clínicas y se **almacena en orden
  alfabético por nombre** (`[c.name for c in DUMMY_CLINICS] == sorted(...)`), que no es el orden por fecha ni
  por identificador; (b) `clinic_counts()` → `ClinicCounts(12, 8, 3)`; `doctors_total()` 37, `patients_total()`
  1284, `users_total()` 52; (c) `recent_clinics("t", limit)` para `limit` de 1 a 12 devuelve `min(limit, 12)`
  clínicas, de la más nueva a la más antigua; con `limit=10` los `id` y nombres de las filas 1 a 10 de la tabla
  de [data-model.md](data-model.md) sección 6, en ese orden, **con Dental Sonríe (`41902d77-…`) antes que
  Clínica San Rafael (`e042d32c-…`)** aunque San Rafael se almacena antes; con `limit=4` la cuarta es Dental
  Sonríe; (d) invariantes I1 a I8 de ese documento: `8 + 3 ≤ 12`; las recientes devueltas no superan el total;
  por estatus no superan los conteos; `users ≥ doctors`; los 12 `id` son UUID versión 4 válidos y distintos;
  las 10 más recientes contienen estatus 1 y 2 y exactamente dos con la misma `created_at`; toda `created_at`
  tiene zona y es UTC; (e) determinismo: dos instancias dan resultados iguales y dos llamadas seguidas también;
  (f) `is_dummy is True`; ignora el token (`""` y `"x"` dan lo mismo); nunca lanza `DashboardSourceUnavailable`;
  (g) `DummyDashboardSource(clinics=(), doctors=0, patients=0, users=0)` da `ClinicCounts(0, 0, 0)`, `[]` y
  tres ceros (FR-014); (h) un conjunto propio de 4 clínicas da `total=4` y las cuenta por estatus.
- [X] T013 [P] [US1] `tests/unit/test_dashboard_service.py` (sección «resumen»; con `FakeDashboardSource` de
  T008; el archivo lo seguirán ampliando T030 y T049): (a) `DashboardService(fake, 5).get("tok")` devuelve un
  `DashboardView` con los seis valores de la fuente y la lista; (b) pide `recent_clinics` con `limit == 5`
  (el valor por defecto) y cada consulta se llama **una vez** con el token recibido; (c) con
  `honor_order=False` y 8 clínicas desordenadas y empatadas, la vista trae 5, de la más nueva a la más
  antigua y desempatando por `id` ascendente (el Service ordena y corta aunque la fuente no lo haga); (d) el
  valor por defecto 3 y 10 se respetan; (e) las cinco consultas corren **a la vez**: con una barrera de 5 y
  `asyncio.timeout(1)` el `get` termina (en serie se bloquearía); (f) sin caché: dos `get` seguidos llaman dos
  veces a cada consulta.
- [X] T014 [P] [US1] `tests/contract/test_dashboard_api.py` (sección «resumen»; usa `dashboard_api`; el archivo
  lo seguirán ampliando T031, T037 y T044): (a) `GET` sin parámetros → 200, `Content-Type: application/json`,
  `Cache-Control: no-store`, exactamente las 7 claves; (b) los seis valores son `12, 8, 3, 37, 1284, 52` y
  `recent_clinics` trae 5 clínicas cuyos `id` y nombres son los de las filas 1, 2, 3, 4 y 5 (en ese orden) de
  [data-model.md](data-model.md); (c) cada clínica tiene exactamente `id`, `name`, `created_at` y `status`
  (`{id, name}`), `id` UUID válido y `created_at` que cumple `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$`; (d) dos
  consultas seguidas dan el **mismo cuerpo**; (e) invariantes de la respuesta: activas + prueba ≤ total,
  recientes ≤ total, usuarios ≥ doctores; (f) recorrer recursivamente el JSON y comprobar que las únicas claves
  son las del contrato (sin datos personales); (g) con `use_source(FakeDashboardSource(...))` la API devuelve
  lo que la fuente da (la fuente es sustituible sin tocar el resto).

### Ajustes a pruebas existentes que no cambian lo que verifican (plan: A2 y A3) ⚠️

- [X] T015 [P] [US1] **Ajuste A2** en `tests/contract/test_openapi_contract.py`: en
  `test_it_has_exactly_the_six_operations_of_the_contract`, acotar la comparación a las operaciones de
  suscripciones: construir `found` solo con las entradas de `operations_of(schema)` cuyo `path` empiece por
  `"/api/v1/subscriptions"`. Añadir un comentario en inglés (`# The dashboard operation is checked in
  test_dashboard_openapi.py`). No cambiar el nombre de la prueba, `OPERATIONS` ni ninguna otra aserción.
- [X] T016 [P] [US1] **Ajuste A3 (parte 1)** en `tests/contract/postman_support.py`: definir
  `SUBSCRIPTIONS_PREFIX = "/api/v1/subscriptions"` y cambiar `operation_ids_of_the_api()` por
  `operation_ids_of_the_api(path_prefix: str = SUBSCRIPTIONS_PREFIX) -> set[str]`, que devuelva solo los
  `operationId` de las rutas cuyo `path` empiece por `path_prefix` (docstring: por defecto, el recurso que
  cubren las colecciones de las specs 001 y 002; para todas las operaciones, `"/"`). Los archivos
  `test_postman_collection.py` y `test_manual_postman_collection.py` que la llaman **no se editan**.

### Implementation for User Story 1

- [X] T017 [P] [US1] `src/dtos/dashboard.py` ([data-model.md](data-model.md) sección 3; descripciones y ejemplos
  en español, como `src/dtos/status.py`): `ClinicStatusRead(id: int, name: str)`;
  `RecentClinicRead(id: UUID, name: str, created_at: AwareDatetime, status: ClinicStatusRead)` con
  `from_attributes=True` y un `@field_validator("created_at")` que devuelva `value.astimezone(timezone.utc)`;
  `DashboardRead` con `total_clinics`, `active_clinics`, `trial_clinics`, `total_doctors`, `total_patients`,
  `total_users` como `Annotated[int, Field(ge=0)] | None` y `recent_clinics: list[RecentClinicRead] | None` con
  `Field(max_length=10)`. **Todos obligatorios, sin valor por defecto** (la clave siempre aparece, con su
  valor o con `null`). Los DTOs de salida no tienen más campos. No importar `src.integrations` ni `src.models`.
- [X] T018 [P] [US1] `src/integrations/dummy_dashboard_source.py` ([data-model.md](data-model.md) sección 6):
  constantes de estatus (`ACTIVE_STATUS = ClinicStatusRecord(1, "Activa")`, `TRIAL_STATUS = (2, "En prueba")`,
  `SUSPENDED_STATUS = (3, "Suspendida")`); `DUMMY_CLINICS`: tupla de las **12 clínicas con los `id`, nombres,
  fechas (`datetime(…, tzinfo=UTC)`) y estatus literales de la tabla**, almacenadas en **orden alfabético por
  nombre**, es decir, las filas 3, 8, 7, 10, 5, 1, 12, 9, 2, 4, 6, 11; y `class DummyDashboardSource`
  (`is_dummy = True`) con `__init__(clinics=DUMMY_CLINICS, doctors=37, patients=1284, users=52)`.
  `clinic_counts` **calcula** total, activas (estatus 1) y en prueba (estatus 2) sobre `clinics`;
  `recent_clinics(token, limit)` devuelve las `limit` más recientes ordenadas por fecha descendente y, a
  igualdad, por `id` ascendente (`sorted(sorted(clinics, key=id), key=created_at, reverse=True)[:limit]`);
  las demás devuelven los enteros del constructor. Ignora el token. Solo biblioteca estándar y el puerto;
  nada de reloj, azar ni red. Cumple T012.
- [X] T019 [US1] `src/services/dashboard_service.py` (versión de esta historia; T033 y T052 la amplían):
  `MAX_RECENT_CLINICS = 10`; `DashboardView` (dataclass `frozen=True, slots=True`, campos de la sección de
  interfaces); `DashboardService.__init__(source, default_limit)` y `async get(self, token: str) ->
  DashboardView`: usa `limit = self._default_limit`, lanza las cinco consultas con `asyncio.gather` (las cinco
  a la vez), ordena la lista con el ordenamiento estable en dos pasadas (`sorted(sorted(clinics, key=lambda c:
  c.id), key=lambda c: c.created_at, reverse=True)`), la corta a `limit` y devuelve la vista. Docstrings en
  inglés con la regla de negocio. Importa el puerto de `src.integrations.dashboard_source` y **no** importa
  `fastapi`, `sqlalchemy` ni `src.security`. Cumple T013.
- [X] T020 [US1] `src/dependencies.py` (aditivo): importar `DummyDashboardSource`, `DashboardSource`,
  `DashboardService` y `get_dashboard_settings`; `build_dashboard_source() -> DashboardSource` devuelve una
  instancia única `DummyDashboardSource()` creada a nivel de módulo (es inmutable y sin estado);
  `async def get_dashboard_source()` devuelve `build_dashboard_source()`; `async def get_dashboard_service(source:
  Annotated[DashboardSource, Depends(get_dashboard_source)]) -> DashboardService` devuelve
  `DashboardService(source, get_dashboard_settings().dashboard_recent_clinics_limit)`. Actualizar el docstring
  del módulo para mencionar el puerto de datos del dashboard.
- [X] T021 [US1] `src/routers/dashboard.py` ([contracts/openapi-dashboard.yaml](contracts/openapi-dashboard.yaml),
  mismo estilo que `src/routers/subscriptions.py`): `DASHBOARD_PATH = "/api/v1/dashboard"`;
  `router = APIRouter(prefix=DASHBOARD_PATH, tags=["dashboard"])`; alias `DashboardServiceDep` y
  `BearerTokenDep` (este con `get_bearer_token` de `src.security`); `_to_read(view) -> DashboardRead` que
  construye el DTO con conversión explícita (`RecentClinicRead.model_validate(clinic)` por cada clínica, o
  `None` si la lista es `None`). La operación `@router.get("", response_model=DashboardRead,
  operation_id="get_dashboard", summary="Consultar el resumen general de la plataforma", description=…,
  **protected(DASHBOARD_READ, responses={200: …}))`: la descripción en español es la del contrato, termina con
  ``Permiso requerido: `dashboard:read`.`` y no menciona fuentes ni implementación; la respuesta 200 documenta
  la cabecera `Cache-Control: no-store` y los tres ejemplos del contrato (`por_defecto`, `sin_clinicas`,
  `fuente_de_doctores_caida`). El manejador recibe `response: Response`, el Service y el token, llama a
  `await service.get(token)`, fija `response.headers["Cache-Control"] = "no-store"` y devuelve `_to_read(view)`.
  Importar `DASHBOARD_READ` y `get_bearer_token` de `src.security`, `protected` y `example_response` de
  `src.routers.openapi_docs`. **No** importar integraciones, repositorios, base de datos ni modelos.
- [X] T022 [US1] `src/main.py` (aditivo): importar y registrar `app.include_router(dashboard.router)` después de
  el de suscripciones; añadir a `OPENAPI_TAGS` la etiqueta `{"name": "dashboard", "description": "Resumen
  general de la plataforma de Maily («Panel de Maily»). Solo lectura; los datos de la Fase 1 son ficticios."}`
  y un párrafo breve en `DESCRIPTION` sobre el dashboard (solo lectura, sin paginar, `null` si una fuente
  falla, datos ficticios en la Fase 1). **No** cambiar `VERSION` (sigue `"1.0.0"`, [research R9](research.md)).
- [X] T023 [US1] **Ajuste A1** en `tests/contract/test_permission_coverage.py`: añadir `"get_dashboard":
  "dashboard:read"` a `EXPECTED_PERMISSIONS` y `"get_dashboard": ("GET", "/api/v1/dashboard", None)` a
  `REQUESTS` (dos entradas; cambiar solo los comentarios que dicen «seis»/«six» por texto neutral). Ninguna
  aserción cambia: las pruebas parametrizadas ahora recorren también el dashboard. **Debe hacerse junto con
  T021/T022**: antes de que exista la ruta, este ajuste hace fallar la prueba de igualdad exacta.
- [X] T024 [US1] Checkpoint de la historia: `uv run pytest tests/unit/test_dashboard_dtos.py
  tests/unit/test_dummy_dashboard_source.py tests/unit/test_dashboard_service.py
  tests/contract/test_dashboard_api.py tests/unit/test_layering.py` y, con la base levantada,
  `uv run pytest tests/contract/test_permission_coverage.py tests/contract/test_openapi_contract.py
  tests/contract/test_postman_collection.py tests/contract/test_manual_postman_collection.py` y
  `uv run pytest` completo: todo en verde. Comprobar a mano que `GET /openapi.json` incluye `get_dashboard`.

**Checkpoint**: US1 funciona y se prueba por sí sola: el dashboard devuelve el resumen con la cantidad por
defecto, protegido por permiso.

---

## Phase 4: User Story 2 - Solo quien tiene el permiso puede consultar el dashboard (Priority: P1)

**Goal**: Verificar, operación por operación y por falla, que la consulta exige token y `dashboard:read`, que se
decide con datos vigentes en cada petición, que falla cerrada y que el acceso se comprueba **antes** que `limit`.

> **Esta historia no añade código de producción.** La puerta ya existe: `protected(DASHBOARD_READ)` en T021 y la
> constante en T005, y los 401/403/503 los produce el código de la feature 001 (`require_permission`,
> `AuthorizationService`, `UsersApiClient`). Por eso las pruebas de abajo **pasan desde que existe la ruta**;
> su valor es fijar el comportamiento y detectar si alguien lo quita (T027 lo demuestra). Si alguna falla, el
> defecto está en `src/routers/dashboard.py`.

**Independent Test**: con (a) sin token, (b) token inválido o vencido, (c) persona sin el permiso, (d) persona
con el permiso y (e) el API de usuarios caído, solo (d) devuelve el dashboard; (a) a (c) y (e) no devuelven dato
alguno ni siquiera con un `limit` inválido.

- [X] T025 [US2] `tests/contract/test_dashboard_access_control.py` (usa `dashboard_api` y
  `FakeDashboardSource` para comprobar que la fuente **no se consulta** cuando el acceso se niega): (a) sin
  cabecera → 401 `unauthenticated`, `WWW-Authenticate: Bearer`, cuerpo exacto
  (`{"code": "unauthenticated", "message": "Debe iniciar sesión para usar esta operación."}`), sin ninguna clave
  del dashboard; (b) esquema `Basic` → 401 `unauthenticated`; (c) token no registrado → 401 `invalid_token`;
  token vencido (`grant_token(..., expired=True)`) → 401 `token_expired`; (d) persona sin permisos
  (`set_permissions([])`) → 403 `permission_denied` y el mensaje es
  `"No tiene permiso para realizar esta operación. Permiso requerido: dashboard:read."`; (e) persona con los
  cuatro permisos de suscripciones pero sin `dashboard:read` → 403 (cada permiso autoriza solo su operación);
  (f) revocación: con permiso → 200, `set_permissions([])` → la **siguiente** petición 403 (SC-003);
  (g) el API de usuarios con cada falla de `["unavailable", "rate_limited", "malformed", "not_json",
  "redirect", "forbidden", "wrong_permission"]` → 503 `authorization_unavailable`, mensaje exacto
  `"No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde."` y el cuerpo **no** contiene
  `SECRETO-INTERNO`; (h) **el acceso gana a `limit`**: parametrizado sobre «sin token», «token inválido»,
  «token vencido», «sin permiso» y «API de usuarios caído», con `?limit=abc` y con `?limit=0` la respuesta es
  la del acceso (401, 403 o 503), **nunca 422**; (i) en todos los rechazos de (a) a (h) la fuente no recibió
  ninguna llamada (`source.calls == []`); (j) con permiso y `?limit=abc` el estatus **no** es 401/403/503
  (la validación viene después; el 422 exacto lo fija T031); (k) por petición protegida hay **una sola**
  llamada al API de usuarios, con `permission == "dashboard:read"` y `authorization == f"Bearer {TEST_TOKEN}"`
  (`users_calls()`), y dos peticiones seguidas hacen dos llamadas (sin caché de decisiones); (l) con
  `caplog.set_level(logging.DEBUG)` el token no aparece en la respuesta ni en los registros; (m) el
  contrato publicado: `GET /openapi.json` **sin token** → 200 y `get_dashboard` declara
  `x-required-permission == "dashboard:read"` y `security == [{"BearerAuth": []}]`; `/docs` también es público.
- [X] T026 [US2] Verificar el ajuste A1: ejecutar `uv run pytest tests/contract/test_permission_coverage.py -v`
  (con la base levantada) y confirmar que aparecen y pasan los casos de `get_dashboard` en las cinco pruebas
  parametrizadas (sin token, token inválido, sin permiso, API de usuarios caído y «solo con su permiso») y que
  `test_every_route_declares_its_permission_or_is_public_documentation` cuenta 7 operaciones. No modifica
  archivos. Revisar además que [contracts/permission-matrix.md](contracts/permission-matrix.md) coincide con el
  `EXPECTED_PERMISSIONS` resultante (7 filas).
- [X] T027 [US2] Comprobar que la prueba detecta lo que debe (no deja cambios): copiar `src/routers/dashboard.py`
  a la carpeta temporal de la sesión; editar el original quitando `**protected(DASHBOARD_READ, …)` del
  decorador (dejando las respuestas documentadas); ejecutar T025 y T026 y **confirmar que fallan** (al menos
  los casos de 401, 403 y 503 y la prueba de cobertura de permisos); **restaurar** el archivo desde la copia,
  confirmar con `diff` que quedó idéntico al original y que T025/T026 vuelven a pasar. El archivo aún no tiene
  seguimiento en git, así que la copia es la única forma de volver atrás: no seguir sin haberla hecho.
- [X] T028 [US2] Checkpoint: `uv run pytest tests/contract/test_dashboard_access_control.py
  tests/contract/test_permission_coverage.py` en verde y `uv run pytest -k dashboard` sin fallos.

**Checkpoint**: US1 y US2 completas: el MVP está listo (consulta protegida con el resumen por defecto).

---

## Phase 5: User Story 3 - Elegir cuántas clínicas recientes ver (Priority: P2)

**Goal**: el parámetro opcional `limit` (1 a 10; más de 10 devuelve 10; inválido, 422) con lectura estricta,
menos clínicas que lo pedido, ninguna clínica y el orden con desempate.

**Independent Test**: `limit` = 1, 3 y 10 devuelven 1, 3 y 10; 11, 1000 y 5 000 dígitos devuelven 10 sin error;
sin `limit`, la cantidad por defecto; 0, `abc`, vacío, `5.5`, `5.0`, `+3` y repetido dan 422 en español; con 4
clínicas y `limit=10` llegan 4; sin clínicas, `[]` y seis ceros.

### Tests for User Story 3 (escribirlas primero; deben fallar) ⚠️

- [X] T029 [P] [US3] `tests/unit/test_dashboard_messages.py`: (a) `messages.DASHBOARD_LIMIT_INVALID_MESSAGE ==
  "El parámetro «limit» debe ser un número entero mayor o igual que 1."`; (b) `translate_validation_errors([{
  "type": t, "loc": ("query", "limit"), "msg": "x", "input": None}], "dashboard")` para `t` en `int_parsing`,
  `greater_than_equal` y `int_type` devuelve un solo `FieldError(field="limit", message=<ese mensaje>)`;
  (c) con el recurso `"subscriptions"` el mismo error NO usa ese mensaje (cada recurso tiene su bloque);
  (d) `len(ErrorCode) == 12` (no se añadió ningún código) y ningún mensaje de `src.messages` repite un valor
  recibido.
- [X] T030 [P] [US3] `tests/unit/test_dashboard_service.py` (sección «cantidad efectiva»; archivo compartido con
  T013, escribir al final): `get(token, requested_limit)`: (a) `3` → pide `limit == 3` a la fuente y la vista
  trae 3; (b) `10` → 10; (c) `11`, `1000` y `10**18` → 10 (tope `MAX_RECENT_CLINICS`, sin error); (d) `None` →
  el valor por defecto (probar con 3, 5 y 10); (e) `1` → una sola, la más reciente; (f) con 4 clínicas y
  `requested_limit=10` → 4, sin rellenar; (g) con la fuente vacía (`clinics=()`, todo en 0) → `recent_clinics ==
  []` (no `None`) y los seis valores `0`; (h) `0` y `-1` lanzan `ValueError` (el Router nunca los envía; es una
  defensa); (i) cuando hay un empate de fecha en el corte (`limit` que deja fuera a uno de los dos), entra el de
  `id` ascendente.
- [X] T031 [P] [US3] `tests/contract/test_dashboard_api.py` (sección «limit»; archivo compartido con T014):
  (a) `limit` válido: 1, 2, 3, 7, 10 → esa cantidad de clínicas y son las más recientes en orden; `limit=007`
  → 7; (b) más de 10: `11`, `1000`, 30 nueves y **5 000 nueves** → 200 con 10 clínicas; (c) sin `limit` → 5;
  (d) parametrizada, **inválidos** → 422: `0`, `00`, `abc`, `` (vacío), `%20` (espacio), `5.5`, `5.0`, `1e1`,
  `+3`, `-1`, `%203`, `3%20`, `1_0`, `0x10`, `%EF%BC%91` (un dígito de ancho completo) y `?limit` sin `=`; cada
  uno con cuerpo **exacto** `{"code": "validation_error", "message": "Hay datos no válidos en la solicitud.",
  "errors": [{"field": "limit", "message": "El parámetro «limit» debe ser un número entero mayor o igual que 1."}]}`,
  sin ninguna clave del dashboard y sin repetir el valor enviado (probar con `limit=valor-secreto` que el texto
  no aparece); (e) `limit=3&limit=5` y `limit=3&limit=abc` → 422; (f) parámetros desconocidos se ignoran:
  `?page=2&offset=3&limit=2` → 2 clínicas; (g) con `FakeDashboardSource` de 4 clínicas y `limit=10` → 4
  (sin relleno); con la fuente vacía → `recent_clinics == []` y los seis conteos `0` (enteros, no `null`);
  (h) `limit=4` con la fuente ficticia → la cuarta es Dental Sonríe (`41902d77-45cb-451e-9e11-65c60e56ecf8`);
  (i) con permiso, un `limit` inválido da 422; sin permiso, 403 (el orden lo fija T025(h)); (j) `422` no lleva
  `Cache-Control: no-store`.

### Implementation for User Story 3

- [X] T032 [US3] `src/messages.py` (aditivo): constante `DASHBOARD_LIMIT_INVALID_MESSAGE` con el texto de la tabla
  de constantes, en una sección `# --- Validation messages of the dashboard ---`, y en `VALIDATION_MESSAGES` un
  bloque nuevo `"dashboard": {("limit", "invalid"): DASHBOARD_LIMIT_INVALID_MESSAGE}`. No tocar `ErrorCode` ni
  los otros bloques. Cumple T029.
- [X] T033 [US3] `src/services/dashboard_service.py`: cambiar la firma a `async get(self, token: str,
  requested_limit: int | None = None)`; añadir el método privado de cantidad efectiva: `None` → el valor por
  defecto; si no, `if requested_limit < 1: raise ValueError("requested_limit must be at least 1")` y
  `min(requested_limit, MAX_RECENT_CLINICS)`. Usar esa cantidad para `recent_clinics(token, limit)` y para el
  corte. El resto sigue igual. Cumple T030.
- [X] T034 [US3] `src/routers/dashboard.py`: (1) la lectura estricta de `limit` ([research R3](research.md)):
  `HUGE_LIMIT = 10**18` y `_DIGITS = re.compile(r"[0-9]+")` (solo dígitos ASCII); `def requested_limit(request:
  Request) -> int | None`: con `values = request.query_params.getlist("limit")`, sin valores → `None`; más de
  uno, o uno que no cumpla `_DIGITS.fullmatch` → `raise RequestValidationError([{"type": "int_parsing", "loc":
  ("query", "limit"), "msg": "invalid limit", "input": None}])`; quitar los ceros a la izquierda (`digits =
  value.lstrip("0")`); si queda vacío (era 0) → el mismo error; si tiene más de 18 cifras → `HUGE_LIMIT`; si no,
  `int(digits)`. (2) `LimitDep = Annotated[int | None, Depends(requested_limit)]` como **último** parámetro del
  manejador, que ahora llama a `service.get(token, limit)`. (3) Documentarlo en el contrato: construir
  `options = protected(DASHBOARD_READ, responses={200: …, 422: VALIDATION_ERROR})`, añadir
  `options["openapi_extra"]["parameters"] = [{"name": "limit", "in": "query", "required": False,
  "description": …, "schema": {"type": "integer", "minimum": 1, "examples": [5]}}]` (descripción en español del
  contrato) y decorar con `**options`; `VALIDATION_ERROR = error_response("…", limit_invalido={…})` con el
  ejemplo del contrato. **No** declarar `limit` como parámetro del endpoint (Pydantic aceptaría `5.0` y
  rechazaría los enteros enormes). Cumple T031.
- [X] T035 [US3] Checkpoint: `uv run pytest tests/unit/test_dashboard_messages.py
  tests/unit/test_dashboard_service.py tests/contract/test_dashboard_api.py
  tests/contract/test_dashboard_access_control.py tests/unit/test_error_messages.py tests/unit/test_layering.py`
  en verde. Comprobar que `GET /openapi.json` muestra `limit` como `integer` con `minimum: 1` en `get_dashboard`.

**Checkpoint**: US1, US2 y US3 funcionan de forma independiente.

---

## Phase 6: User Story 4 - Fijar la cantidad por defecto de clínicas recientes (Priority: P2)

**Goal**: la variable opcional `DASHBOARD_RECENT_CLINICS_LIMIT` (3, 5 o 10; 5 si falta) rige cuando no se envía
`limit`; un valor distinto impide arrancar nombrando la variable sin su valor; cambiarla exige reiniciar.

**Independent Test**: sin la variable el valor es 5; con 3, 5 y 10 rige cada uno; con 4, 0, 11 y `abc` el
servicio no arranca y el error nombra la variable sin el valor; `.env.example` la documenta.

### Tests for User Story 4 (escribirlas primero; deben fallar) ⚠️

- [X] T036 [P] [US4] `tests/unit/test_dashboard_startup.py` (**archivo nuevo**; T042 lo amplía), sección «configuración
  al arrancar». Fixture `autouse` igual a la de `tests/unit/test_main.py` pero también aislando
  `DashboardSettings`: `monkeypatch.delenv` de `USERS_API_BASE_URL`, `CLINICS_API_BASE_URL`,
  `USERS_API_TIMEOUT_SECONDS`, `CLINICS_API_TIMEOUT_SECONDS`, `CORS_ALLOWED_ORIGINS` y
  `DASHBOARD_RECENT_CLINICS_LIMIT`; `monkeypatch.setitem(<cada clase>.model_config, "env_file", None)` para
  `IntegrationSettings`, `CorsSettings` y `DashboardSettings`; y `cache_clear()` de las tres funciones
  `get_*_settings` antes y después. Casos con `async with lifespan(create_app())`: (a) variable ausente, vacía,
  `"3"`, `"5"` y `"10"` → arranca y cierra su cliente HTTP; (b) parametrizada, `"4"`, `"0"`, `"11"`, `"-5"`,
  `"abc"`, `"5.5"` y `"05"` (con las dos direcciones válidas) → `RuntimeError` cuyo texto contiene
  `DASHBOARD_RECENT_CLINICS_LIMIT` y **no** contiene el valor (usar también `"valor-secreto-9"` y comprobar que
  no aparece ni en la excepción ni en `caplog.text`); el mensaje empieza por `"Configuración incompleta o no
  válida."`; (c) variable inválida **y** falta `USERS_API_BASE_URL` → el mensaje nombra las dos y no nombra
  `CLINICS_API_BASE_URL`; (d) el error se registra con `logger.error` una vez; (e) cambiar la variable
  **después** de arrancar no cambia `get_dashboard_settings().dashboard_recent_clinics_limit` (el valor se
  lee una sola vez: hace falta reiniciar).
- [X] T037 [P] [US4] `tests/contract/test_dashboard_api.py` (sección «valor por defecto configurado»; archivo
  compartido): con `monkeypatch.setenv("DASHBOARD_RECENT_CLINICS_LIMIT", valor)` y
  `get_dashboard_settings.cache_clear()` **antes de la primera petición** (la fixture ya aísla la
  configuración): (a) sin variable → 5 clínicas; (b) `"3"`, `"5"` y `"10"` sin `limit` → 3, 5 y 10; (c) con la
  variable en `"3"` y `?limit=7` → 7 (el `limit` enviado prevalece) y `?limit=1000` → 10; (d) variable vacía →
  5; (e) el valor por defecto solo rige sin `limit`: con la variable en `"10"` y `?limit=2` → 2.

### Implementation for User Story 4

- [X] T038 [US4] `src/main.py` (`lifespan`): importar `get_dashboard_settings`; sustituir el bloque que valida solo
  `get_integration_settings()` por uno que cargue **ambas** configuraciones (`for load in
  (get_integration_settings, get_dashboard_settings)`), recoja los `ValidationError` en una lista y, si hay
  alguno, haga `message = configuration_error_message(*errors)`, `logger.error(message)` y `raise
  RuntimeError(message) from None` (el servicio no arranca; sin `from None` el texto de Pydantic repetiría el
  valor). Después de validar, `settings = get_integration_settings()` como hoy. No registrar nada nuevo en esta
  tarea (el aviso de datos ficticios es T046). Cumple T036 y T037; las pruebas de `tests/unit/test_main.py`
  existentes siguen pasando.
- [X] T039 [P] [US4] `.env.example`: en el bloque «Opcionales (se muestran con su valor por defecto)», añadir con
  comentarios en español, **comentada**: la explicación (`Cantidad de clínicas recientes que devuelve el
  dashboard cuando la persona no envía limit`), los valores admitidos (`3, 5 o 10; cualquier otro impide
  arrancar`), el valor por defecto (`5`), que un cambio requiere reiniciar el servicio y la línea
  `# DASHBOARD_RECENT_CLINICS_LIMIT=5`.
- [X] T040 [P] [US4] `docker-compose.yml`: en `services.api.environment`, junto a las demás opcionales, añadir
  `DASHBOARD_RECENT_CLINICS_LIMIT: ${DASHBOARD_RECENT_CLINICS_LIMIT:-}` (vacía = valor por defecto, que el
  servicio ignora). No tocar `db`, `migrate` ni `tests/postman/docker-compose.e2e.yml`.
- [X] T041 [US4] Checkpoint: `uv run pytest tests/unit/test_dashboard_startup.py tests/unit/test_dashboard_config.py
  tests/unit/test_main.py tests/unit/test_config.py tests/contract/test_dashboard_api.py` en verde;
  `docker compose config --quiet` sin errores.

**Checkpoint**: US1 a US4 funcionan de forma independiente.

---

## Phase 7: User Story 5 - Datos ficticios y avisados en la Fase 1 (Priority: P2)

**Goal**: al arrancar con datos ficticios el servicio registra un aviso; el dashboard no usa la base de datos
(sin tablas, modelos ni migraciones) y sus datos son idénticos tras un reinicio.

> La fuente ficticia, sus invariantes y su determinismo ya están implementados y probados en la historia 1
> (T012, T018). Aquí quedan el aviso de arranque, la garantía de que no toca la base de datos y la prueba de que
> un reinicio no cambia nada.

**Independent Test**: arrancar y encontrar el aviso; `git status` sin cambios en `alembic/`, `src/models/`,
`src/repositories/` ni `project-definition/`; dos aplicaciones distintas dan el mismo cuerpo; `limit=10` da 10
clínicas con UUID válidos.

### Tests for User Story 5 (escribirlas primero; deben fallar) ⚠️

- [X] T042 [P] [US5] `tests/unit/test_dashboard_startup.py` (sección «aviso de datos ficticios»; archivo compartido
  con T036, escribir al final): con las dos direcciones válidas y `caplog.at_level(logging.WARNING)`: (a) al
  arrancar queda **un** registro `WARNING` que contiene `DUMMY` y `phase 1`; (b) ese registro no contiene
  `BASE_URL`, ni `Bearer`, ni ninguna dirección; (c) el arranque no se impide (el `lifespan` entra y sale sin
  excepción y deja `app.state.http_client` creado); (d) si `build_dashboard_source` se sustituye (`monkeypatch.setattr(
  "src.main.build_dashboard_source", lambda: FakeDashboardSource(is_dummy=False))`) el aviso **no** aparece;
  (e) con una variable inválida no hay aviso (el servicio no arranca antes).
- [X] T043 [P] [US5] `tests/unit/test_dashboard_layering.py` (usa `imported_modules` y `violations_in` de
  `tests/unit/test_layering.py`): los cinco módulos nuevos (`src/routers/dashboard.py`,
  `src/services/dashboard_service.py`, `src/dtos/dashboard.py`, `src/integrations/dashboard_source.py` y
  `src/integrations/dummy_dashboard_source.py`) existen y no importan `sqlalchemy`, `asyncpg`, `alembic`,
  `src.database`, `src.models` ni `src.repositories` (FR-020); no existe ningún `src/models/dashboard*.py` ni
  `src/repositories/dashboard*.py`; el módulo de la fuente ficticia no importa `socket`, `httpx`, `random`,
  `secrets` ni `time`, y su texto no contiene `.now(`, `utcnow` ni `today(` (determinismo y sin red); el Router
  no importa `src.integrations`.
- [X] T044 [P] [US5] `tests/contract/test_dashboard_api.py` (sección «datos ficticios»; archivo compartido):
  (a) dos aplicaciones distintas (`create_app()` dos veces, simulando un reinicio y limpiando
  `get_dashboard_settings`) responden **exactamente** el mismo cuerpo con `limit=10`; (b) con `limit=10` llegan
  10 clínicas, todas con `id` UUID válido y distintos; (c) entre esas 10 hay estatus `{id: 1, name: "Activa"}`
  y `{id: 2, name: "En prueba"}` y exactamente dos con el mismo `created_at`, ordenadas por `id` ascendente;
  (d) la consulta funciona **sin base de datos** (la fixture `dashboard_api` no la usa; comprobar que
  `get_session` no se llama: sobrescribirlo con una función que haga `pytest.fail`).

### Implementation for User Story 5

- [X] T045 [US5] **Ajuste B1** en `tests/unit/test_main.py`: en `test_docker_and_https_addresses_do_not_warn`
  (línea `assert caplog.text == ""`), cambiar la aserción por `assert "BASE_URL" not in caplog.text` y añadir un
  comentario en inglés (`# Only the plain-http address warnings are meant to be absent; the start-up notice of
  the dummy dashboard data (spec 003 FR-024) is expected`). No cambiar nada más del archivo. **Debe hacerse
  antes o junto con T046**: sin este ajuste la prueba falla en cuanto exista el aviso.
- [X] T046 [US5] `src/main.py`: importar `build_dashboard_source` de `src.dependencies`; definir la constante
  `DUMMY_DASHBOARD_NOTICE` (texto de la tabla de constantes; **sin** `BASE_URL`, direcciones ni token); en
  `lifespan`, **después** de la validación y del bucle de `insecure_url_warnings`, `if
  build_dashboard_source().is_dummy: logger.warning(DUMMY_DASHBOARD_NOTICE)`. El aviso se emite una vez por
  arranque y desaparecerá solo cuando la fuente real tenga `is_dummy = False`. Cumple T042.
- [X] T047 [US5] Verificar que no hay cambios de esquema (SC-009; no modifica archivos): `git status --short
  alembic src/models src/repositories src/database project-definition tests/stubs` **sin salida**, y
  `uv run alembic heads` muestra una sola cabeza (la de la feature 001).
- [X] T048 [US5] Checkpoint: `uv run pytest tests/unit/test_dashboard_startup.py tests/unit/test_dashboard_layering.py
  tests/unit/test_main.py tests/contract/test_dashboard_api.py` en verde y `uv run pytest -k dashboard` sin
  fallos. Arrancar la API a mano (quickstart, nivel 3, comprobación 1) y ver el aviso en la consola.

**Checkpoint**: US1 a US5 funcionan de forma independiente.

---

## Phase 8: User Story 6 - Un contrato estable que sobrevive a las fuentes reales (Priority: P3)

**Goal**: si una fuente falla, solo lo suyo llega como `null` (nunca un cero ni `[]` inventado), el resto se
devuelve con 200, no se filtran detalles y el control de acceso no se relaja; el contrato publicado reserva
`null` en los siete campos desde hoy.

**Independent Test**: con fuentes simuladas que fallan una por una, solo los indicadores afectados llegan en
`null`; una fuente que dice «no hay nada» da `0` y `[]`; el esquema publicado declara cada campo como obligatorio
y anulable.

### Tests for User Story 6 (escribirlas primero; deben fallar) ⚠️

- [X] T049 [P] [US6] `tests/unit/test_dashboard_service.py` (sección «degradación»; archivo compartido):
  (a) `fail={"doctors_total"}` → `total_doctors is None` y los otros seis valores intactos; (b) `fail=
  {"clinic_counts"}` → `total_clinics`, `active_clinics` y `trial_clinics` en `None` y lo demás intacto;
  (c) `fail={"recent_clinics"}` → `recent_clinics is None` (**no** `[]`) y lo demás intacto; (d) lo mismo para
  `patients_total` y `users_total`; (e) fallan las cinco → los siete campos en `None`, sin excepción; (f) una
  fuente que responde «no hay nada» (`clinics=()`, ceros) → `0` y `[]`, **no** `None`; (g) `crash=
  {"users_total"}` (`RuntimeError`) **se propaga** (no se convierte en `None`); (h) por cada consulta caída
  hay un registro `WARNING` `"Dashboard source unavailable: <nombre>"` y los registros no contienen el token
  ni el texto de la excepción; (i) las demás consultas se ejecutan aunque una falle (la fuente registra las
  cinco llamadas).
- [X] T050 [P] [US6] `tests/contract/test_dashboard_degradation.py` (usa `dashboard_api`; todas con
  `FakeDashboardSource`): (a) `fail={"doctors_total"}` → 200, `total_doctors` es `null` (la clave **está**) y el
  resto tiene sus valores; `Cache-Control: no-store` también en este 200; (b) `fail={"recent_clinics"}` → 200 y
  `recent_clinics` es `null`, no `[]`; (c) `fail={"clinic_counts"}` → las tres claves de clínicas `null` y la
  lista intacta; (d) fallan las cinco → 200 con las siete claves en `null`; (e) fuente vacía → seis `0` y
  `[]`; (f) **sin fugas**: el cuerpo no contiene el texto interno que la excepción de la fuente pudiera llevar
  ni direcciones, y los registros (`caplog` en DEBUG) no contienen el token; (g) el acceso no se relaja
  (FR-028): con todas las fuentes caídas, sin token → 401, sin permiso → 403 y con el API de usuarios caído →
  503; (h) una excepción que **no** es `DashboardSourceUnavailable` (`crash={"users_total"}`) produce `500`
  con `{"code": "internal_error", "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde."}`
  (para esta prueba crear el cliente con `httpx.ASGITransport(app=app, raise_app_exceptions=False)`, porque el
  transporte por defecto relanza la excepción); (i) contrato estable: el conjunto de claves de la respuesta es
  el mismo con la fuente ficticia, con una fuente simulada y con fuentes caídas.
- [X] T051 [P] [US6] `tests/contract/test_dashboard_openapi.py` (paralela a `test_openapi_contract.py`; usa
  `create_app().openapi()`): (a) existe `get_dashboard` en `GET /api/v1/dashboard` y es la **única** operación
  bajo `/api/v1/dashboard`; (b) `tags == ["dashboard"]`, `security == [{"BearerAuth": []}]`,
  `x-required-permission == "dashboard:read"`, `summary` no vacío y la descripción contiene
  ``Permiso requerido: `dashboard:read` ``; (c) documenta las respuestas `200`, `401`, `403`, `422` y `503`;
  los errores usan `#/components/schemas/ErrorResponse`, `401` documenta `WWW-Authenticate` y `200` documenta
  la cabecera `Cache-Control`; (d) el parámetro `limit`: `in == "query"`, `required` falso, esquema
  `integer` con `minimum == 1` y descripción en español; (e) `DashboardRead` lista en `required` sus siete
  campos y cada uno acepta `null` (`anyOf` con `{"type": "null"}`); `RecentClinicRead` tiene exactamente `id`
  (`format: uuid`), `name`, `created_at` (`format: date-time`) y `status`; `ClinicStatusRead` exactamente `id` y
  `name`; (f) el esquema `ErrorCode` sigue teniendo los 12 códigos; (g) **toda** operación del documento
  (suscripciones y dashboard) declara `security` y `x-required-permission`; (h) `info.version == "1.0.0"`.

### Implementation for User Story 6

- [X] T052 [US6] `src/services/dashboard_service.py`: añadir `logger = logging.getLogger(__name__)` y el método
  privado `async _guarded(self, name: str, call: Awaitable[T]) -> T | None`: espera `call`; si lanza
  `DashboardSourceUnavailable`, registra `logger.warning("Dashboard source unavailable: %s", name)` (sin token
  ni texto de la excepción) y devuelve `None`; **cualquier otra excepción se propaga**. En `get`, envolver las
  cinco consultas (`"clinic_counts"`, `"recent_clinics"`, `"doctors_total"`, `"patients_total"`,
  `"users_total"`) con `_guarded` dentro del mismo `asyncio.gather`; si `counts is None`, los tres conteos de
  clínicas son `None`; si la lista es `None`, `recent_clinics` es `None` (no `[]`, y entonces no se ordena ni se
  corta). Actualizar los docstrings (degradación, Principio IX). Cumple T049 y T050.
- [X] T053 [US6] Checkpoint: `uv run pytest tests/unit/test_dashboard_service.py
  tests/contract/test_dashboard_degradation.py tests/contract/test_dashboard_openapi.py
  tests/contract/test_openapi_contract.py tests/unit/test_layering.py` en verde y `uv run pytest -k dashboard`
  sin fallos.

**Checkpoint**: Las seis historias funcionan de forma independiente.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: La colección de Postman (FR-036), su guardián, la documentación y la validación final.

- [X] T054 [P] `tests/postman/collections/MailySoft-System-Dashboard.postman_collection.json` (**colección nueva**,
  formato v2.1; [contracts/e2e-collection.md](contracts/e2e-collection.md)): 4 carpetas y 24 peticiones con
  los nombres, los métodos y las comprobaciones de las tablas de ese documento («0. Preparación»,
  «1. Resumen», «2. limit inválido (422)» y «3. Control de acceso»). Reglas: `info.name` «MailySoft System API —
  Dashboard» y descripción en español de la colección, de cada carpeta y de cada petición; autenticación de la
  colección Bearer `{{accessToken}}` (las peticiones heredan, son `noauth` o llevan exactamente
  `{{plainToken}}`, `{{subscriptionsToken}}` o `{{badToken}}`; en los textos no escribir la palabra `Bearer`
  seguida de 8 o más caracteres alfanuméricos, que el barrido de secretos confundiría con un token); nombres
  `get_dashboard: …`, `setup: …` y
  `docs: …`; todas las URL empiezan por `{{baseUrl}}` (o `{{usersStubUrl}}/__test__/…` las de `setup`); todas
  las peticiones a la API son `GET`; cada petición tiene un evento `test` con `pm.test("…")` en español; el
  script previo de la colección registra las tres personas (`accessToken` con `dashboard:read`, `plainToken`
  sin permisos y `subscriptionsToken` con los cuatro permisos de suscripciones) en
  `{{usersStubUrl}}/__test__/tokens` con tokens al azar solo en variables de colección, y `badToken` se genera
  en cada petición; el reinicio de la simulación descarta las tres variables; la comparación de determinismo
  guarda el cuerpo en la variable de colección `firstBody`. Aserciones del orden y del desempate con los `id` de
  [data-model.md](data-model.md) sección 6. **Sin secretos**: ningún JWT, ningún `Bearer` literal y **ni la
  palabra «secret»** en ningún lugar del archivo (el barrido de `test_postman_collection.py` recorre toda la
  carpeta). No tocar las colecciones existentes ni los entornos. Se puede generar con un script desechable
  fuera del repositorio (carpeta temporal de la sesión) que escriba el JSON con `ensure_ascii=False` y sangría
  de 2 espacios.
- [X] T055 **Ajuste A3 (parte 2)** en `tests/contract/postman_support.py`: añadir `DASHBOARD_COLLECTION = POSTMAN /
  "collections" / "MailySoft-System-Dashboard.postman_collection.json"`, `DASHBOARD_PREFIX = "/api/v1/dashboard"`
  y `DASHBOARD_HELPER_PREFIXES = {"setup", "docs"}` (con el mismo comentario que las otras constantes). Sin
  cambios en lo demás.
- [X] T056 `tests/contract/test_dashboard_postman_collection.py` (reglas **G1 a G9** de
  [contracts/e2e-collection.md](contracts/e2e-collection.md), solo leen archivos y el OpenAPI generado: sin
  Node.js, sin Postman, sin red). Escribir cada regla como función pura `check_*(collection[, environment]) ->
  list[str]` cuyo mensaje nombra lo que falta o sobra (patrón de `tests/contract/test_manual_postman_collection.py`),
  y una prueba por regla que la ejecute con la colección real y espere `[]`. **Pruebas del propio detector** sobre
  copias en memoria (sin tocar disco): quitar la única petición `get_dashboard` → G2 la nombra; añadir una
  petición con prefijo inexistente → G2; borrar el evento `test` de una petición → G3; quitar las peticiones que
  esperan 503 → G4; poner un `Bearer` literal o un valor distinto de las cuatro variables permitidas → G5;
  insertar un JWT de ejemplo o la palabra prohibida → G6; cambiar un `GET` por `POST` → G7; dar a una variable
  de colección el nombre de una clave del entorno → G8; y para G9, que la unión de las **tres** colecciones
  cubre exactamente `operation_ids_of_the_api("/")` (usar `E2E_HELPER_PREFIXES`, `MANUAL_HELPER_PREFIXES` y
  `DASHBOARD_HELPER_PREFIXES`) y que quitar una operación de la unión la delata.
- [X] T057 `tests/postman/package.json`: añadir a `scripts` `"e2e:dashboard": "newman run
  collections/MailySoft-System-Dashboard.postman_collection.json -e environments/e2e.postman_environment.json -r
  cli,junit --reporter-junit-export reports/junit-dashboard.xml --timeout-request 15000"` y `"e2e:all": "npm run
  e2e && npm run e2e:dashboard"`. **No** cambiar el script `e2e` ni las dependencias; no regenerar
  `package-lock.json`.
- [X] T058 Ejecutar la colección de punta a punta (verificación manual; no modifica archivos): `npm ci --prefix
  tests/postman`, levantar la pila aislada (`docker compose -p maily-system-e2e -f docker-compose.yml -f
  tests/postman/docker-compose.e2e.yml up -d --wait api`), `npm run e2e:dashboard --prefix tests/postman` (las 24
  peticiones pasan, código de salida 0), repetirlo una segunda vez (es de solo lectura: debe seguir en verde sin
  limpiar nada), `npm run e2e:all --prefix tests/postman` (las dos colecciones pasan) y desmontar la pila con
  `down -v`. Ver en `docker compose logs api` el aviso de datos ficticios del arranque.
- [X] T059 [P] `README.md`: (1) «Qué incluye hoy»: añadir el dashboard (tabla con `get_dashboard` →
  `GET /api/v1/dashboard` → `dashboard:read`, contrato en
  [`openapi-dashboard.yaml`](contracts/openapi-dashboard.yaml) con la ruta
  `specs/003-platform-dashboard/contracts/openapi-dashboard.yaml`, y 4 viñetas: solo lectura y sin caché; `limit`
  de 1 a 10 con tope y valor por defecto; datos ficticios deterministas con aviso al arrancar; un valor `null`
  significa «fuente no disponible», nunca un cero); (2) tabla de «Configuración»: la fila
  `DASHBOARD_RECENT_CLINICS_LIMIT` (no obligatoria, por defecto `5`, valores `3`, `5` o `10`); (3) «Pruebas»:
  mencionar que `uv run pytest -k dashboard` no necesita Docker y enlazar el
  [quickstart](quickstart.md) de esta feature; (4) «Pruebas de punta a punta (Postman)»: corregir el texto que
  dice que toda feature actualiza «las dos colecciones» —ahora hay tres: la de suscripciones (Newman), la
  manual (solo suscripciones) y la del dashboard (Newman, `npm run e2e:dashboard`)— y explicar que cada recurso
  nuevo tiene su colección y que `test_dashboard_postman_collection.py` comprueba que las tres juntas cubren
  la API; (5) «Estructura»: mencionar el puerto de datos en `integrations/`, `tests/dashboard_support.py` y
  `tests/contract/conftest.py`. No tocar las secciones de la colección manual salvo el enlace.
- [X] T060 Validar la guía de [quickstart.md](quickstart.md): recorrer los niveles 1 y 3 (las cinco comprobaciones
  manuales, incluida la de configuración inválida con `4`, `0`, `11`, `abc` y `5.5` y la de `3`/`10`/sin variable)
  y confirmar que cada resultado coincide con lo escrito. Si algún comando o resultado de la guía no es exacto,
  **corregir la guía** (no el código) y anotarlo en el mensaje de cierre.
- [X] T061 Puertas de calidad de la constitución: (a) `docker compose up -d db` y `uv run pytest` **completo** en
  verde: las pruebas de la línea base de T001 más las nuevas, sin ninguna omitida; (b) `uv run pytest
  tests/unit/test_layering.py tests/unit/test_dashboard_layering.py` (capas); (c) generar el OpenAPI sin
  errores (`uv run python -c "from src.main import create_app; create_app().openapi()"`); (d)
  `tests/contract/test_permission_coverage.py` en verde; (e) migraciones aplicables desde cero
  (`tests/integration/test_migrations.py`) y `git status --short alembic src/models src/repositories
  project-definition` sin salida; (f) Principio VII: ningún identificador ni código en español y ningún mensaje
  de la API en inglés en el código nuevo (revisar `git diff` y los archivos nuevos); (g) ningún archivo nuevo
  o modificado contiene tokens, contraseñas ni secretos.
- [X] T062 Cierre: (a) `git status --short` solo muestra los archivos de esta feature (los listados en
  [plan.md](plan.md) «Source Code») además de los dos `.ps1` ajenos, y **ningún** archivo prohibido por las
  convenciones; (b) las cuatro ediciones a pruebas existentes (A1, A2, A3, B1) son exactamente las descritas
  (`git diff` de esos cuatro archivos: solo las líneas de cada ajuste); (c) revisar
  [checklists/requirements.md](checklists/requirements.md) y marcar lo que siga válido; (d) resumir en el
  mensaje de cierre: pruebas totales y nuevas, los cuatro ajustes, la validación de Newman y cualquier
  desviación respecto al plan.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** todas las historias.
- **US1 (Phase 3)**: depende de Foundational. **Crea la ruta**, el Service, los DTOs, la fuente ficticia y el
  cableado de los que dependen todas las demás.
- **US2 (Phase 4)**: depende de US1 (necesita la ruta). No añade código de producción.
- **US3 (Phase 5)**: depende de US1 (amplía el Service y el Router).
- **US4 (Phase 6)**: depende de US1 (el valor por defecto) y de Foundational (T007). Independiente de US3 salvo
  por el archivo `tests/contract/test_dashboard_api.py`.
- **US5 (Phase 7)**: depende de US4 (ambas editan `lifespan` de `src/main.py` y
  `tests/unit/test_dashboard_startup.py`; US5 va después).
- **US6 (Phase 8)**: depende de US1 (amplía el Service). Sus pruebas OpenAPI (T051) esperan también a US3
  (el parámetro `limit` y la respuesta 422 en el contrato).
- **Polish (Phase 9)**: depende de las historias deseadas. T054 necesita US1 a US3 y US6 en marcha (la colección
  ejercita `limit` y el control de acceso); T056 necesita T054 y T055.

### Archivos compartidos (límite real del paralelismo)

Las historias comparten `src/routers/dashboard.py` (US1, US3), `src/services/dashboard_service.py` (US1, US3,
US6), `src/main.py` (US1, US4, US5), `src/messages.py` (US3), y los archivos de pruebas
`tests/unit/test_dashboard_service.py` (US1, US3, US6), `tests/contract/test_dashboard_api.py` (US1, US3, US4,
US5) y `tests/unit/test_dashboard_startup.py` (US4, US5). Por eso se implementan **en el orden de las fases**;
cada historia, una vez integrada, se prueba y se demuestra de forma independiente con los criterios de su fase.

### Within Each User Story

- Las pruebas se escriben primero y **deben fallar** (salvo US2); después DTO → fuente → Service → Router →
  composición.
- Los ajustes a pruebas existentes (A1 a A3, B1) se hacen **en el mismo paso** que el código que los exige: A2 y
  A3 antes de la ruta (T015, T016), A1 junto con ella (T023), B1 junto con el aviso (T045).
- Cada fase termina con su punto de control y con `uv run pytest -k dashboard` en verde; los puntos de control
  de US1, US5 y Polish ejecutan también la suite completa.

### Parallel Opportunities

- Setup: T002 es [P].
- Foundational: T003, T004, T005, T006 y T008 son [P]; T007 sigue a T006; T009 sigue a T008.
- US1: las pruebas T011–T014 son [P] entre sí; T015 y T016 son [P]; T017 y T018 son [P].
- US3: T029, T030 y T031 son [P] (archivos distintos).
- US4: T036 y T037 son [P]; T039 y T040 son [P].
- US5: T042, T043 y T044 son [P].
- US6: T049, T050 y T051 son [P].
- Polish: T054 y T059 son [P]; T055 y T056 van en orden (mismo archivo de apoyo, luego la prueba).

---

## Parallel Example: User Story 1

```bash
# Escribir a la vez las pruebas de la historia (archivos distintos):
Task: "Pruebas de los DTOs en tests/unit/test_dashboard_dtos.py"
Task: "Pruebas de la fuente ficticia en tests/unit/test_dummy_dashboard_source.py"
Task: "Pruebas del Service en tests/unit/test_dashboard_service.py"
Task: "Pruebas de la API en tests/contract/test_dashboard_api.py"

# Después, los módulos independientes:
Task: "DTOs en src/dtos/dashboard.py"
Task: "Fuente ficticia en src/integrations/dummy_dashboard_source.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational).
2. Completar Phase 3 (US1: el resumen) y Phase 4 (US2: el control de acceso verificado).
3. **DETENERSE y validar**: `uv run pytest`; arrancar con la simulación del API de usuarios (nivel 3 de
   [quickstart.md](quickstart.md)), consultar el resumen y comprobar el 401, el 403 y el 503. La pantalla del
   «Panel de Maily» ya puede consumir el contrato.

### Incremental Delivery

1. MVP → demostrable (resumen protegido con la cantidad por defecto).
2. + US3 (`limit`) → la pantalla puede pedir listas de distinto tamaño.
3. + US4 (valor por defecto configurable) → se ajusta por despliegue.
4. + US5 (aviso de datos ficticios) → nadie lo lleva a producción sin darse cuenta.
5. + US6 (degradación y contrato estable) → listo para conectar las fuentes reales.
6. Polish → colección de Postman, documentación y puertas de calidad.

---

## Notes

- [P] = archivos distintos y sin dependencias abiertas; [Story] = trazabilidad con la spec.
- Verificar que las pruebas **fallan** antes de implementar y que pasan después (salvo US2, que verifica código
  que ya existe).
- No hacer commits salvo que la persona los pida; si los pide, un commit por tarea o grupo lógico.
- Evitar: tareas vagas, conflictos de archivo dentro de una misma fase, editar pruebas existentes fuera de A1,
  A2, A3 y B1, y cualquier prueba que llame a un API real.

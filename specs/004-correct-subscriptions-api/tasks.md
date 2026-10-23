---

description: "Task list for feature 004-correct-subscriptions-api (corrección del modelo de datos de la API de Suscripciones)"
---

# Tasks: Corrección del modelo de datos de la API de Suscripciones

**Input**: Design documents from `/specs/004-correct-subscriptions-api/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.0.0** vigente (sin cambios) y `001-subscriptions-api` ya implementada y en verde en
`main` (`uv run pytest`, `uv run alembic upgrade head`). **No es un proyecto nuevo**: Setup y Docker ya
existen; estas tareas modifican y amplían código real ya desplegado.

**Tests**: Incluidas. El Principio V las exige, igual que en `001-subscriptions-api`. Se sigue TDD
dentro de cada fase: las tareas de pruebas se escriben primero y **deben fallar** antes de implementar.
**Ninguna prueba llama a la API de usuarios ni al API de clínicas reales**: usan `tests/stubs/` (HTTP vía
`httpx.ASGITransport`) o los dobles de `tests/unit/fakes.py`.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). Las historias **US1**
y **US2** (ambas P1) ya están satisfechas en su mayor parte por `001-subscriptions-api`: US2 no cambia
nada; US1 solo necesita pruebas nuevas, porque Foundational entrega el modelo completo. El trabajo
nuevo de verdad está en **US3** (crear) y **US5** (actualizar), que son las únicas historias con
módulos, límites y precio anual como entrada. **US4**, **US6** y **US7** solo necesitan pruebas de
regresión: su lógica no cambia. El **MVP de esta corrección** es Foundational + US1 + US3 (se puede
crear un plan completo y verlo en el catálogo).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US7); sin etiqueta en Setup, Foundational y
  Polish
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones nuevas y evidencia: [research.md](research.md) (R1 a R13)
- Columnas nuevas, DTOs y reglas de módulos: [data-model.md](data-model.md)
- Esquema SQL completo tras el cambio: [contracts/database-schema.sql](contracts/database-schema.sql)
- Contrato HTTP completo v2.0.0 (OpenAPI 3.1, validado): [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
- Códigos de error nuevos, mensajes exactos y precedencia: [contracts/error-catalog.md](contracts/error-catalog.md)
- Permiso externo adicional (`modules:read`): [contracts/permission-matrix.md](contracts/permission-matrix.md)
- Contrato consumido de módulos de la API de usuarios: [contracts/users-api-integration.md](contracts/users-api-integration.md)
- Simulación ampliada y colección de Postman: [contracts/e2e-stubs.md](contracts/e2e-stubs.md)
- Guía de validación (delta sobre 001): [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json` (debe
  seguir en `specs/004-correct-subscriptions-api`); escribir tokens, contraseñas o secretos reales en
  cualquier archivo; añadir dependencias fuera de la tabla del stack de la constitución; tocar
  `specs/001-subscriptions-api/` (sus artefactos quedan como registro histórico, no se editan).
- **Idioma** (Principio VII): identificadores, campos de la API y códigos de error en inglés; mensajes,
  descripciones de OpenAPI y documentos en español; comentarios y docstrings en inglés.
- **Mensajes exactos**: los textos en español de los 3 errores nuevos y de los mensajes de validación
  de los 7 campos nuevos salen de [contracts/error-catalog.md](contracts/error-catalog.md); no se
  parafrasean.
- **Pruebas**: `docker compose up -d db` y `uv run pytest [ruta]` (igual que en 001). Ninguna prueba
  necesita `USERS_API_*` ni `CLINICS_API_*` reales.
- **Constantes y nombres nuevos** (se definen una sola vez, con nombre exacto, en el módulo indicado):

  | Constante / nombre | Valor | Módulo |
  |---|---|---|
  | `PATIENTS_KEY` | `"patients"` | `src/clinic_modules.py` (**nuevo**) |
  | `MODULE_DEPENDENCIES` | `{"reminders": "scheduling", "clinical_record_templates": "clinical_records", "prescriptions": "clinical_records", "billing": "finance"}` | `src/clinic_modules.py` |
  | Las 9 claves de módulo de clínica | `patients, scheduling, reminders, clinical_records, clinical_record_templates, prescriptions, finance, reports, billing` | `src/clinic_modules.py` (research R2) |
  | Nombres de `CheckConstraint` nuevos | `annual_price_check`, `trial_days_check`, `module_keys_check`, `other_features_check` (reemplaza a `features_check`), `consulting_rooms_limit_check`, `doctors_limit_check`, `assistants_limit_check`, `new_patients_per_year_limit_check` | `src/models/subscription.py` |
  | Operación de módulos consumida | `GET {USERS_API_BASE_URL}/api/v1/modules?type_id=2&status_id=1` | `src/integrations/users_api.py` |
  | Códigos de error nuevos | `subscription_module_not_found` (422), `subscription_module_prerequisite_missing` (409), `module_check_unavailable` (503) | `src/messages.py` (`ErrorCode`) |

- **Interfaces compartidas nuevas o modificadas** (usar exactamente estos nombres):
  - `src/clinic_modules.py` (**nuevo**, sin E/S): `PATIENTS_KEY: str`, `MODULE_DEPENDENCIES: dict[str, str]`,
    `missing_prerequisite(keys: frozenset[str]) -> tuple[str, str] | None`.
  - `src/integrations/users_api.py`: `UsersApiClient` gana
    `async list_clinic_module_keys(self, token: str) -> frozenset[str]` (lanza `UsersApiRejectedToken`
    o `UsersApiUnavailable`, las mismas excepciones ya existentes).
  - `src/exceptions.py`: `SubscriptionModuleNotFoundError(module_key: str)` (422),
    `SubscriptionModulePrerequisiteMissingError(module_key: str, prerequisite_key: str)` (409),
    `ModuleCheckUnavailableError()` (503).
  - `src/services/subscription_service.py`: `SubscriptionService.__init__(repository, clinics_api,
    users_api)` (gana `users_api: UsersApiClient`); método privado
    `async _resolve_modules(self, requested: list[str] | None, token: str) -> list[str]` (devuelve el
    conjunto final ordenado, incluido `patients`).
  - `src/repositories/subscription_repository.py`: `create(...)` gana `annual_price: Decimal,
    trial_days: int, self_service: bool, module_keys: list[str], other_features: list[str],
    consulting_rooms_limit: int, doctors_limit: int, assistants_limit: int,
    new_patients_per_year_limit: int` (sustituye a `features`). `update(id, changes)` **no cambia de
    firma** (ya es genérico).
  - `tests/unit/fakes.py`: `FakeUsersApi` gana `clinic_module_keys: frozenset[str]`,
    `modules_unavailable: bool` y `list_clinic_module_keys(token)`. `FakeSubscriptionRepository.add()`
    y `.create()` ganan los mismos parámetros nuevos que el Repository real.
  - `tests/helpers.py`: `insert_subscription(session, **values)` gana los mismos parámetros, con
    valores por defecto para que las llamadas existentes sin ellos sigan funcionando.

---

## Phase 1: Setup

**Purpose**: Confirmar el punto de partida antes de modificar código ya desplegado.

- [X] T001 Verificar prerrequisitos (no modifica archivos): `git status --short` no muestra cambios sin
  seguimiento fuera de `specs/004-correct-subscriptions-api/` y `project-definition/DATA_SCHEMA.md`;
  `.specify/feature.json` contiene `"feature_directory": "specs/004-correct-subscriptions-api"`;
  `docker compose up -d db && uv run pytest` de `001-subscriptions-api` está en verde (línea base antes
  de corregir); `uv run alembic current` muestra `0002` como revisión vigente.

**Checkpoint**: línea base confirmada en verde antes de tocar nada.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Esquema de datos, modelo, catálogo de dependencias de módulos, cliente de la API de
usuarios y utilidades de prueba compartidas. **Ninguna historia puede empezar sin esta fase**: las 6
operaciones leen y escriben el mismo `Subscription` con las columnas nuevas.

### Tests (escribirlos primero; deben fallar)

- [X] T002 [P] `tests/integration/test_migrations.py` (ampliar): aplicar `0001` → `0003` sobre una base
  vacía no falla; `uv run alembic downgrade base` revierte las tres sin error; `uv run alembic check` no
  detecta diferencias entre modelos y migraciones tras `0003`.
- [X] T003 [P] `tests/integration/test_subscriptions_constraints.py` (ampliar, usa `assert_pg_error` de
  `tests/helpers.py`, SQLSTATE `23514` para `CHECK`): insertar con `annual_price = -1` →
  `subscriptions_annual_price_check`; `trial_days = -1` o `3651` → `subscriptions_trial_days_check`
  (rango **0 a 3650**); `module_keys = '{}'` (sin `'patients'`) → `subscriptions_module_keys_check`;
  cada límite en `-1` o `1000001` → su propio `CHECK` (rango **0 a 1 000 000**); `other_features` con 21
  elementos → `subscriptions_other_features_check` (el mismo límite de 20 que antes, con el nuevo
  nombre).
- [X] T004 [P] `tests/unit/test_clinic_modules.py` (nuevo): para cada uno de los 4 pares de
  `MODULE_DEPENDENCIES` (`reminders`→`scheduling`, `clinical_record_templates`→`clinical_records`,
  `prescriptions`→`clinical_records`, `billing`→`finance`),
  `missing_prerequisite(frozenset({dependiente}))` devuelve `(dependiente, prerrequisito)`; con el
  prerrequisito también en el conjunto, devuelve `None`; con `frozenset()` o con solo `PATIENTS_KEY`,
  devuelve `None`; `PATIENTS_KEY == "patients"`; `MODULE_DEPENDENCIES` tiene exactamente esos 4 pares.
- [X] T005 [P] `tests/contract/test_users_api_client.py` (ampliar, monta el stub con
  `httpx.ASGITransport`): con los 9 módulos de Clínica y los 4 de Sistema sembrados,
  `list_clinic_module_keys(token)` devuelve exactamente las 9 claves de tipo Clínica (nunca las de
  Sistema); sin token válido → `UsersApiRejectedToken`; con un fallo registrado con
  `{"operation": "modules", "mode": "unavailable"}` → `UsersApiUnavailable`; el mismo fallo con
  `{"operation": "check"}` **no** afecta a esta llamada (comprueba que el campo nuevo aísla los fallos
  por operación); `modos "not_json"`, `"malformed"` y `"redirect"` con `operation: "modules"` también →
  `UsersApiUnavailable`.
- [X] T006 [P] `tests/unit/test_error_messages.py` (ampliar): `SubscriptionModuleNotFoundError("billing").message`,
  `SubscriptionModulePrerequisiteMissingError("billing", "finance").message` y
  `ModuleCheckUnavailableError().message` son exactamente los textos de
  [contracts/error-catalog.md](contracts/error-catalog.md) («Mensajes nuevos»); sus `.code` son
  `subscription_module_not_found`, `subscription_module_prerequisite_missing`,
  `module_check_unavailable`; sus `.status_code` son `422`, `409`, `503`.

### Implementation

- [X] T007 [P] `alembic/versions/0003_subscription_pricing_modules_limits.py` (nuevo; `revision = "0003"`,
  `down_revision = "0002"`): reproducir exactamente la sección «Migración 0003» de
  [contracts/database-schema.sql](contracts/database-schema.sql) — `op.alter_column` con `new_column_name`
  para renombrar `features` → `other_features` y renombrar su `CHECK` con `op.execute` (`ALTER TABLE
  subscriptions RENAME CONSTRAINT ...`); `op.add_column` para las 7 columnas nuevas, cada una con su
  `CheckConstraint`/`sa.CheckConstraint` y, donde corresponda, `server_default` (`trial_days` → `"0"`,
  `self_service` → `"false"`, `module_keys` → `"ARRAY['patients']::text[]"`; `annual_price` y los 4
  límites **sin** `server_default`, `nullable=False`). `downgrade()` revierte en el orden inverso. Hace
  pasar T002 y T003.
- [X] T008 [P] `src/clinic_modules.py` (nuevo, sin importar nada de otras capas): `PATIENTS_KEY`,
  `MODULE_DEPENDENCIES`, `missing_prerequisite(keys)` tal como fija la tabla de constantes de arriba.
  Hace pasar T004.
- [X] T009 `src/models/subscription.py`: renombrar la columna `features` a `other_features` (mismo
  `ARRAY(Text)`, mismo `CheckConstraint("cardinality(other_features) <= 20", name="other_features_check")`);
  añadir `annual_price: Mapped[Decimal]` (`Numeric(10, 2)`), `trial_days: Mapped[int]` (`Integer,
  server_default=text("0")`), `self_service: Mapped[bool]` (`Boolean, server_default=text("false")`),
  `module_keys: Mapped[list[str]]` (`ARRAY(Text), server_default=text("ARRAY['patients']::text[]")`),
  `consulting_rooms_limit`, `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit`
  (`Mapped[int]`, `Integer`); añadir los 7 `CheckConstraint` con los nombres de la tabla de arriba y los
  mismos rangos que T007 (`annual_price >= 0`; `trial_days` y cada límite con `BETWEEN`;
  `'patients' = ANY(module_keys)`). Debe coincidir exactamente con T007: `uv run alembic check` sin
  diferencias.
- [X] T010 [P] `src/exceptions.py` + `src/messages.py`: `ErrorCode.SUBSCRIPTION_MODULE_NOT_FOUND =
  "subscription_module_not_found"`, `.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING =
  "subscription_module_prerequisite_missing"`, `.MODULE_CHECK_UNAVAILABLE = "module_check_unavailable"`
  y sus mensajes exactos de `contracts/error-catalog.md`; las 3 clases `AppError` de la tabla de
  constantes de arriba; añadir a `VALIDATION_MESSAGES["subscriptions"]` las 13 entradas `(campo, tipo) ->
  mensaje` de la tabla «Mensajes de validación nuevos» de `contracts/error-catalog.md` (`annual_price`,
  `trial_days`, `self_service`, `module_keys` ×2, `other_features` ×3, los 4 límites). Hace pasar T006.
- [X] T011 `src/integrations/users_api.py`: `async def list_clinic_module_keys(self, token: str) ->
  frozenset[str]`, mismo `asyncio.timeout(self._timeout)`, misma cabecera `Authorization`, mismo
  `_rejection_code` para un `401` que `check_permission`; `GET
  f"{self._base_url}/api/v1/modules"` con `params={"type_id": 2, "status_id": 1}`; si el estado no es
  `200`, o el cuerpo no es una lista de objetos cada uno con `key` de cadena no vacía, lanza
  `UsersApiUnavailable`; si no, devuelve `frozenset(item["key"] for item in data)`. Hace pasar T005.
- [X] T012 [P] `src/dependencies.py`: `get_subscription_service` añade
  `users_api: Annotated[UsersApiClient, Depends(get_users_api_client)]` y construye
  `SubscriptionService(repository, clinics_api, users_api)`.
- [X] T013 [P] `tests/stubs/users_api/app.py`: sembrar en memoria, al crear la app, los 9 módulos de
  tipo Clínica (`type_id: 2`) de `src/clinic_modules.py` más los 4 protegidos de tipo Sistema
  (`type_id: 1`: `users`, `roles`, `permissions`, `modules`), cada uno con `id` correlativo, `key`,
  `name`, `status: {id: 1, name: "Activo"}`, `type: {id, name}`; `GET /api/v1/modules` exige
  `Authorization: Bearer` (si no, `401 unauthenticated`) y filtra por `type_id`/`status_id` si se
  pasan; `FaultIn` gana `operation: str = "check"`, y `take_fault(operation)` solo consume fallos
  registrados con esa `operation`; `POST /__test__/modules/reset` repone el sembrado por defecto;
  `_RecordCalls` registra también las llamadas a `/api/v1/modules`. Detalle completo en
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md).
- [X] T014 [P] `tests/unit/fakes.py`: `FakeUsersApi.__init__` gana `clinic_module_keys: frozenset[str] =
  frozenset({"patients"})` y `modules_unavailable: bool = False`; nuevo método
  `async def list_clinic_module_keys(self, token: str) -> frozenset[str]` que registra la llamada en
  `self.module_calls: list[str]` (lista nueva, separada de `self.calls`) y lanza `UsersApiUnavailable()`
  si `modules_unavailable`, si no devuelve `self.clinic_module_keys`.
  `FakeSubscriptionRepository.add()` y `.create()` ganan `annual_price: str | Decimal = "100.00"`,
  `trial_days: int = 0`, `self_service: bool = False`, `module_keys: Iterable[str] = ("patients",)`,
  `other_features: Iterable[str] = ()` (sustituye a `features`), `consulting_rooms_limit: int = 1`,
  `doctors_limit: int = 1`, `assistants_limit: int = 1`, `new_patients_per_year_limit: int = 100`, todos
  asignados al `Subscription` construido.
- [X] T015 [P] `tests/helpers.py`: `insert_subscription` gana los mismos parámetros y valores por
  defecto que T014 (`features` se renombra a `other_features`), incluidos en el
  `insert(Subscription).values(...)`.

**Checkpoint**: `uv run alembic upgrade head`, `uv run alembic check`, y
`uv run pytest tests/unit/test_clinic_modules.py tests/contract/test_users_api_client.py tests/integration/test_migrations.py tests/integration/test_subscriptions_constraints.py`
en verde.

---

## Phase 3: User Story 2 - Solo quien tiene el permiso puede operar (Priority: P1)

**Goal**: ninguna de las 6 operaciones cambia su control de acceso (FR-001 a FR-005 no cambian).

**Independent Test**: igual que en `001-subscriptions-api` (sin token, token inválido, sin permiso, con
permiso, API de usuarios caída), para las 6 operaciones.

**Sin tareas nuevas de control de acceso**: `src/security.py`, `AuthorizationService` y
`require_permission` no cambian. Solo hace falta una revisión de mantenimiento:

- [X] T016 [US2] `tests/contract/test_access_control.py`: revisar los cuerpos de ejemplo que la prueba
  usa para `create_subscription`/`update_subscription` en sus casos de **403/401** (sin permiso no
  debe importar si el cuerpo es válido, FR-004); si algún caso prueba también el camino con permiso
  concedido, completar ese cuerpo con `annual_price` y los 4 límites para que siga probando acceso, no
  validación. No se cambia ninguna aserción de permisos ni de códigos.

**Checkpoint**: `uv run pytest tests/contract/test_access_control.py tests/contract/test_permission_coverage.py`
en verde, sin cambios de fondo.

---

## Phase 4: User Story 1 - Consultar el catálogo de planes con su información completa (Priority: P1)

**Goal**: listar y consultar devuelven los 13 campos (FR-008), sin depender de la API de usuarios por
módulos (research R5).

**Independent Test**: ver [spec.md](spec.md#user-story-1---consultar-el-catálogo-de-planes-con-su-información-completa-priority-p1)
(plan «Profesional» completo; suscripción «Avanzado» con 8 de 9 módulos).

### Tests for User Story 1

- [X] T017 [P] [US1] `tests/unit/test_subscription_dtos.py` (ampliar): `SubscriptionRead.model_validate`
  de un `Subscription` con los 7 campos nuevos serializa `annual_price` igual que `monthly_price` (dos
  decimales, cadena); `module_keys` y `other_features` se exponen tal cual la columna.
- [X] T018 [P] [US1] `tests/contract/test_subscriptions_api.py` (ampliar): crear (vía `Api.insert`) una
  suscripción con `module_keys={"patients","scheduling","finance","reports"}` (8 de 9: todos salvo
  `billing`) y comprobar que `GET /api/v1/subscriptions` la devuelve con esos módulos exactos, incluidos
  `finance` sin `billing` (confirma AT5: excluir un módulo no excluye a los que dependen de él); el
  resto de los 13 campos presentes; una Eliminada no aparece; catálogo vacío → `[]`.
- [X] T019 [US1] `tests/contract/test_subscriptions_api.py` o `test_clinics_degradation.py` (ampliar):
  con el API de clínicas caído, el listado sigue devolviendo los 13 campos con `clinics_count: null`.
- [X] T020 [US1] `tests/contract/test_subscriptions_api.py` (ampliar): `GET /api/v1/subscriptions` y
  `GET /api/v1/subscriptions/{id}` **no generan ninguna llamada** a `GET /api/v1/modules` del stub de
  usuarios (`[c for c in await api.users_calls() if c["path"] == "/api/v1/modules"] == []` antes y
  después de la petición).

**Checkpoint**: listar y consultar exponen el modelo completo; `uv run pytest tests/contract/test_subscriptions_api.py`
en verde.

---

## Phase 5: User Story 3 - Crear una suscripción con su información completa (Priority: P2)

**Goal**: crear exige y valida los 13 campos, incluidos módulos (contra la API de usuarios y las
dependencias locales) y los 4 límites.

**Independent Test**: ver [spec.md](spec.md#user-story-3---crear-una-suscripción-con-su-información-completa-priority-p2).

### Tests for User Story 3 (escribirlos primero; deben fallar)

- [X] T021 [P] [US3] `tests/unit/test_subscription_dtos.py` (ampliar) — `SubscriptionCreate` con estas
  restricciones **verbatim** (de [data-model.md](data-model.md#validación-de-cada-campo-nuevo-dto)):
  `annual_price`: `Decimal`, `ge=0`, `max_digits=10`, `decimal_places=2`, obligatorio (acepta `4500`,
  `"4500.50"`; rechaza `-1`, `4500.555`, `100000000`, `null`, ausente, con el mensaje «El precio anual es
  obligatorio.» o «El precio anual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales.»);
  `trial_days`: entero, `ge=0`, `le=3650`, por defecto `0` si se omite (rechaza `-1`, `3651`, `1.5`, con
  «Los días de prueba deben ser un número entero de 0 a 3650.»); `self_service`: booleano, por defecto
  `False` si se omite; `module_keys`: lista de hasta **50** elementos, cada uno con el patrón
  `^[a-z][a-z0-9_]*$` y máx. **50** caracteres, por defecto `[]` (rechaza `"Scheduling"`, `"123"`, un
  elemento no-texto, más de 50 elementos, con «Cada módulo debe identificarse con una clave válida.» o
  «No se pueden pedir más de 50 módulos.»); `other_features`: igual que la antigua `features` (hasta
  **20** elementos de **1 a 150** caracteres recortados, por defecto `[]`); `consulting_rooms_limit`,
  `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit`: enteros, `ge=0`, `le=1000000`,
  **obligatorios** (ausentes o `null` → 422 con «El límite de {consultorios|doctores|asistentes|
  pacientes nuevos al año} debe ser un número entero de 0 a 1 000 000.»); `extra="forbid"` sigue
  rechazando `id`, `status`, `clinics_count`, fechas.
- [X] T022 [P] [US3] `tests/unit/test_subscription_service.py` (ampliar): `create(data)` con
  `module_keys=[]` (o ausente) **no** llama a `users_api.list_clinic_module_keys`
  (`FakeUsersApi.module_calls == []`) y pasa `module_keys=["patients"]` a `repository.create(...)`; con
  `module_keys=["scheduling"]` (sin prerrequisitos pendientes) llama una vez a
  `list_clinic_module_keys` y pasa `["patients", "scheduling"]` (orden alfabético) a
  `repository.create`; con `module_keys=["reminders"]` (sin `scheduling`) → levanta
  `SubscriptionModulePrerequisiteMissingError` **sin** llamar a `users_api` (la dependencia se valida
  antes que el catálogo externo, research R6); con una clave que `FakeUsersApi(clinic_module_keys=...)`
  no reconoce → `SubscriptionModuleNotFoundError`; con `FakeUsersApi(modules_unavailable=True)` y algún
  módulo además de `patients` → `ModuleCheckUnavailableError`; se siguen pasando los 6 campos nuevos
  restantes (`annual_price`, `trial_days`, `self_service`, `other_features`, los 4 límites) a
  `repository.create`; `UniqueViolationError` se sigue traduciendo igual que antes.
- [X] T023 [P] [US3] `tests/integration/test_subscription_repository.py` (ampliar): `create(...)` con
  los 7 argumentos nuevos inserta y, al recargar, cada columna tiene exactamente ese valor
  (`annual_price` con 2 decimales aunque se pase sin ellos); `module_keys` se guarda tal como se
  recibió (el Service ya incluyó `patients`); las 50 creaciones simultáneas con el mismo nombre (SC-006)
  siguen funcionando con la nueva firma.
- [X] T024 [US3] `tests/contract/test_subscriptions_api.py` (ampliar): `POST /api/v1/subscriptions` con
  el ejemplo `completo` de [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
  (plan «Profesional») → 201 con los 13 campos, `module_keys` incluye `patients` aunque no se envió;
  solo los campos obligatorios (ejemplo `minimo`) → 201 con `module_keys: ["patients"]`, `trial_days: 0`,
  `self_service: false`, `other_features: []`; sin `annual_price` → 422; sin un límite → 422;
  `module_keys: ["billing"]` → 409 `subscription_module_prerequisite_missing` con el mensaje exacto
  «El módulo «billing» exige el módulo «finance», que no está incluido.»; `module_keys: ["no_existe"]` →
  422 `subscription_module_not_found`; con un fallo `{"operation": "modules", "mode": "unavailable"}`
  registrado y `module_keys: ["scheduling"]` → 503 `module_check_unavailable` (y **no** se crea nada:
  comprobar que no aparece después en el listado).

### Implementation for User Story 3

- [X] T025 [US3] `src/dtos/subscription.py`: `SubscriptionCreate` gana los 7 campos con las
  restricciones de T021 (`ConfigDict(extra="forbid", str_strip_whitespace=True)` ya existe). Patrón de
  `module_keys`: `Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=50)]`.
  Hace pasar T021.
- [X] T026 [US3] `src/services/subscription_service.py`: constructor gana `users_api: UsersApiClient`
  (actualizar también los sitios que lo instancian a mano, p. ej. pruebas que no usan
  `get_subscription_service`); nuevo método privado
  `async def _resolve_modules(self, requested: list[str] | None, token: str) -> list[str]` que: calcula
  `wanted = frozenset(requested or ()) | {PATIENTS_KEY}`; si `wanted == {PATIENTS_KEY}` devuelve
  `[PATIENTS_KEY]` sin llamar a nada; si no, primero `missing_prerequisite(wanted)` (local) y, si
  encuentra un par, `raise SubscriptionModulePrerequisiteMissingError(*par)`; luego
  `try: valid = await self._users_api.list_clinic_module_keys(token) except UsersApiUnavailable: raise
  ModuleCheckUnavailableError() from None`; `unknown = wanted - {PATIENTS_KEY} - valid`; si no está
  vacío, `raise SubscriptionModuleNotFoundError(sorted(unknown)[0])`; devuelve `sorted(wanted)`. `create`
  llama a `_resolve_modules(data.module_keys, token)` (necesita el `token`: añadir el parámetro a
  `create(data, token)` y actualizar el Router, ver T028) antes de `repository.create(...)`, pasando
  también `data.annual_price`, `data.trial_days`, `data.self_service`, `data.other_features` y los 4
  límites. Hace pasar T022.
- [X] T027 [US3] `src/repositories/subscription_repository.py`: `create(...)` gana los 7 parámetros
  nuevos (ver tabla de interfaces) e inclúyelos en `insert(Subscription).values(...)`. Hace pasar T023.
- [X] T028 [US3] `src/routers/subscriptions.py`: `create_subscription` pasa el `token` (ya disponible
  como `BearerTokenDep`) a `service.create(data, token)`; actualizar `protected(SUBSCRIPTIONS_WRITE,
  responses={...})` para documentar `409` (con los dos ejemplos: nombre repetido y prerrequisito
  faltante), `422` (con el ejemplo `modulo_no_reconocido` además de los ya existentes) y `503` (con los
  dos ejemplos: `authorization_unavailable` y `module_check_unavailable`), tal como
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) los documenta; actualizar
  `CREATE_EXAMPLES` con el ejemplo `completo` (plan «Profesional») del contrato. Hace pasar T024.

**Checkpoint**: se pueden crear suscripciones completas, con módulos validados y límites obligatorios.
`uv run pytest` en verde.

---

## Phase 6: User Story 4 - Consultar una suscripción por su identificador (Priority: P2)

**Goal**: el detalle individual trae el mismo modelo completo que el catálogo (ya lo entrega
Foundational + US1; sin lógica nueva).

**Independent Test**: ver [spec.md](spec.md#user-story-4---consultar-una-suscripción-por-su-identificador-priority-p2).

### Tests for User Story 4

- [X] T029 [P] [US4] `tests/contract/test_subscriptions_api.py` (ampliar): `GET
  /api/v1/subscriptions/{id}` de una suscripción Activa, Inactiva o Bloqueada creada con el modelo
  completo devuelve los 13 campos (incluidos `module_keys` y los 4 límites); Eliminada o inexistente →
  404 (sin cambios de fondo respecto a 001).

**Checkpoint**: `uv run pytest tests/contract/test_subscriptions_api.py` en verde.

---

## Phase 7: User Story 5 - Actualizar los datos de una suscripción (Priority: P2)

**Goal**: actualizar admite cualquier subconjunto de los 13 campos; si toca módulos, comprueba
existencia antes de llamar a la API de usuarios (research R6).

**Independent Test**: ver [spec.md](spec.md#user-story-5---actualizar-los-datos-de-una-suscripción-priority-p2).

### Tests for User Story 5

- [X] T030 [P] [US5] `tests/unit/test_subscription_dtos.py` (ampliar): `SubscriptionUpdate` acepta
  cualquier subconjunto no vacío de los 13 campos (mismas restricciones de T021 cuando se envían);
  `annual_price`, `trial_days`, `self_service`, `consulting_rooms_limit`, `doctors_limit`,
  `assistants_limit` y `new_patients_per_year_limit` **no admiten `null`** (mensaje «no puede ser
  nulo», mismo patrón que el validador existente de `name`/`monthly_price`); `module_keys` y
  `other_features` tampoco admiten `null` (deben ser lista; `[]` sí vacía `other_features` y deja
  `module_keys` en solo `patients`); cuerpo vacío `{}` se sigue rechazando.
- [X] T031 [P] [US5] `tests/unit/test_subscription_service.py` (ampliar): `update(id, data, token)` con
  `"module_keys"` en `data.model_fields_set` llama primero a `repository.get_current_by_id(id)`; si
  devuelve `None` → `SubscriptionNotFoundError` **sin** llamar a `users_api`
  (`FakeUsersApi.module_calls == []`); si existe, reutiliza `_resolve_modules` igual que `create`;
  **sin** `"module_keys"` en el payload, **no** se añade ninguna llamada extra a
  `repository.get_current_by_id` ni a `users_api` (el camino de `001-subscriptions-api` para los demás
  campos no cambia).
- [X] T032 [US5] `tests/contract/test_subscriptions_api.py` (ampliar): `PATCH` solo `{"annual_price":
  "13990.00"}` conserva el resto y actualiza `updated_at`; `{"module_keys": ["reminders"]}` sobre una
  suscripción sin `scheduling` → 409 `subscription_module_prerequisite_missing`; sobre una suscripción
  Eliminada con `{"module_keys": [...]}` → 404, y el stub de usuarios no recibe ninguna llamada a
  `/api/v1/modules`; bajar un límite (p. ej. `doctors_limit` de 3 a 1) se acepta siempre.

### Implementation for User Story 5

- [X] T033 [US5] `src/services/subscription_service.py`: `update(subscription_id, data, token)` — si
  `"module_keys" in changes`, llamar primero a `self._repository.get_current_by_id(subscription_id)` y
  lanzar `SubscriptionNotFoundError(subscription_id)` si es `None`; si no, reemplazar
  `changes["module_keys"]` por `await self._resolve_modules(changes["module_keys"], token)` antes de
  `repository.update(subscription_id, changes)`. El resto del método no cambia. Hace pasar T031.
- [X] T034 [US5] `src/routers/subscriptions.py`: `update_subscription` documenta `409` (+ ejemplo
  `prerrequisito_faltante`), `422` (+ ejemplo `modulo_no_reconocido`) y `503` (+ ejemplo `modulos`) en
  `protected(SUBSCRIPTIONS_UPDATE, responses={...})`, igual que el contrato; añadir el ejemplo `modulos`
  a `UPDATE_EXAMPLES`. Hace pasar T032.

**Checkpoint**: actualizar funciona con el modelo completo, incluidos módulos. `uv run pytest` en verde.

---

## Phase 8: User Story 6 - Cambiar el estatus de una suscripción (Priority: P2)

**Goal**: cambiar el estatus sigue sin tocar módulos, precios ni límites (regresión).

**Independent Test**: ver [spec.md](spec.md#user-story-6---cambiar-el-estatus-de-una-suscripción-priority-p2).

- [X] T035 [US6] `tests/contract/test_subscriptions_api.py` (ampliar): cambiar el estatus de una
  suscripción creada con módulos, precio anual y límites conserva esos datos exactos en la respuesta
  (`PATCH .../status` no los toca); el resto de los escenarios (cualquier dirección entre 1/2/3,
  estatus repetido → 409, «Eliminada» → 422) no cambia.

**Sin tareas de implementación**: `change_status` no lee ni escribe ningún campo nuevo.

**Checkpoint**: `uv run pytest tests/contract/test_subscriptions_api.py` en verde.

---

## Phase 9: User Story 7 - Eliminar una suscripción (Priority: P3)

**Goal**: la baja lógica sigue sin leer ni escribir módulos, precios ni límites (regresión).

**Independent Test**: ver [spec.md](spec.md#user-story-7---eliminar-una-suscripción-priority-p3).

- [X] T036 [US7] `tests/contract/test_subscriptions_api.py` (ampliar): eliminar una suscripción creada
  con el modelo completo (vía `Api.insert` con los valores por defecto de T015) sigue devolviendo 204 y
  deja de aparecer en el listado; con clínicas asignadas, sigue en 409; con el API de clínicas caído,
  sigue en 503 `clinics_check_unavailable`; nada de esto cambia por los campos nuevos.

**Sin tareas de implementación**: `soft_delete` solo cambia `status_id`.

**Checkpoint**: las 6 operaciones funcionan con el modelo completo. `uv run pytest` en verde.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: versión del contrato, colección de Postman, y validación de punta a punta.

- [X] T037 [P] `src/main.py`: `VERSION = "2.0.0"` (research R9); ampliar `DESCRIPTION` con el párrafo de
  módulos («`module_keys` son claves de un catálogo externo, propiedad de la API de usuarios…», como en
  `contracts/openapi-subscriptions.yaml`).
- [X] T038 [P] `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`:
  aplicar los cambios de [contracts/e2e-stubs.md](contracts/e2e-stubs.md) — cuerpos de «1. Catálogo» y
  «2. Consultar y actualizar» con los 7 campos nuevos; 2 peticiones nuevas en «2.» (módulo sin
  prerrequisito → 409; módulo no reconocido → 422); «0. Preparación» registra también `modules:read`.
- [X] T039 `uv run pytest tests/contract/test_openapi_contract.py`: confirmar que el `/openapi.json`
  generado por la aplicación coincide con
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) (si la prueba compara
  campo a campo contra un archivo fijo, actualizar esa referencia al nuevo contrato).
- [X] T040 `uv run pytest tests/contract/test_permission_coverage.py`: confirmar que las 6 rutas y sus 4
  permisos propios siguen coincidiendo exactamente con
  [contracts/permission-matrix.md](contracts/permission-matrix.md) (ninguna ruta nueva: la llamada de
  módulos no es una ruta de esta API).
- [X] T041 Ejecutar la guía de validación completa de [quickstart.md](quickstart.md) (niveles 1 a 3):
  `uv run pytest` completo; nivel 2 manual con la pila e2e (crear «Profesional», rechazo por
  prerrequisito, rechazo por módulo no reconocido, degradación de `module_check_unavailable`); nivel 3
  con Newman.
- [X] T042 [P] Revisión final: ningún identificador ni comentario nuevo en español (Principio VII); los
  3 mensajes de error y los 13 mensajes de validación nuevos coinciden **verbatim** con
  [contracts/error-catalog.md](contracts/error-catalog.md); `project-definition/DATA_SCHEMA.md` (ya
  actualizado en la fase de planificación) sigue coincidiendo con el esquema real tras aplicar `0003`.

**Checkpoint final**: `uv run pytest`, `uv run alembic check`, Newman y el quickstart completo, todo en
verde.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** las 7 historias (todas leen/escriben el
  mismo `Subscription` con las columnas nuevas).
- **US2 (Phase 3)** y **US1 (Phase 4)**: dependen solo de Foundational; no dependen entre sí.
- **US3 (Phase 5)**: depende de Foundational. Introduce `_resolve_modules`, que **US5 reutiliza**.
- **US4 (Phase 6)**: depende de Foundational (y, en la práctica, de que US1 ya haya probado el modelo de
  lectura, aunque no comparte tareas con ella).
- **US5 (Phase 7)**: depende de Foundational **y de US3** (reutiliza `_resolve_modules` de T026).
- **US6 (Phase 8)** y **US7 (Phase 9)**: dependen de Foundational; no tienen tareas de implementación,
  así que pueden probarse en cualquier momento después de Foundational.
- **Polish (Phase 10)**: depende de todas las historias deseadas (T039 y T040 necesitan las 6
  operaciones ya actualizadas).

### Archivos compartidos (límite real del paralelismo)

Las historias comparten `src/routers/subscriptions.py`, `src/services/subscription_service.py`,
`src/repositories/subscription_repository.py`, `src/dtos/subscription.py` y
`tests/contract/test_subscriptions_api.py`. Por eso US3 y US5 se implementan **en orden** (US5 depende
de código que nace en US3); US1, US4, US6 y US7 solo añaden pruebas y pueden intercalarse libremente
entre sí una vez Foundational está listo.

### Parallel Opportunities

- Foundational: T002–T006 (pruebas) son `[P]` entre sí; T007–T008 y T010–T015 son `[P]` entre sí (T009
  depende conceptualmente de T007 para que los nombres coincidan, pero son archivos distintos).
- US1: T017–T018 son `[P]`; T019–T020 tocan el mismo archivo que T018 y van después.
- US3: T021–T023 son `[P]` entre sí (archivos distintos); T025–T027 son secuenciales entre sí (DTO →
  Service → Repository) pero T025 puede escribirse en paralelo con T021 siendo la implementación que lo
  hace pasar.
- US4, US6, US7: cada una es una sola tarea.
- Polish: T037–T038 y T042 son `[P]`; T039–T041 se ejecutan, no se editan.

---

## Parallel Example: Foundational

```bash
# Escribir a la vez las pruebas de Foundational (archivos distintos):
Task: "Prueba de la migración en tests/integration/test_migrations.py"
Task: "Prueba de las restricciones nuevas en tests/integration/test_subscriptions_constraints.py"
Task: "Prueba de src/clinic_modules.py en tests/unit/test_clinic_modules.py"
Task: "Prueba de list_clinic_module_keys en tests/contract/test_users_api_client.py"
Task: "Prueba de los mensajes nuevos en tests/unit/test_error_messages.py"

# Después, las piezas independientes:
Task: "src/clinic_modules.py"
Task: "src/dependencies.py (inyectar UsersApiClient en SubscriptionService)"
Task: "tests/stubs/users_api/app.py (GET /api/v1/modules)"
Task: "tests/unit/fakes.py (FakeUsersApi, FakeSubscriptionRepository)"
Task: "tests/helpers.py (insert_subscription)"
```

---

## Implementation Strategy

### MVP de esta corrección (Foundational + US1 + US3)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational).
2. Completar Phase 4 (US1: el catálogo ya expone el modelo completo) y Phase 5 (US3: ya se pueden crear
   planes completos, con módulos validados).
3. **DETENERSE y validar**: `uv run pytest`; nivel 2 de [quickstart.md](quickstart.md) — crear el plan
   «Profesional» del mockup y verlo en el listado con sus 13 campos.

### Incremental Delivery

1. Foundational → el esquema y el modelo de datos ya están corregidos (nada se rompe: `001-subscriptions-api`
   seguía en verde antes de empezar, y Foundational es un superconjunto compatible).
2. + US1 → el catálogo ya muestra todo.
3. + US3 → ya se pueden crear planes completos (MVP de esta corrección).
4. + US4 → el detalle también.
5. + US5 → se pueden editar módulos, precios y límites de un plan existente.
6. + US6, US7 → confirmados sin regresión.
7. Polish → versión del contrato, Postman, OpenAPI y Newman.

---

## Notes

- `[P]` = archivos distintos y sin dependencias abiertas; `[Story]` = trazabilidad con la spec.
- US2, US6 y US7 no tienen tareas de implementación: son regresiones que confirman que esta corrección
  no rompió lo que ya funcionaba.
- Verificar que las pruebas **fallan** antes de implementar y que pasan después.
- No hacer commits salvo que la persona los pida; si los pide, un commit por tarea o grupo lógico.
- Recordar los **puntos a confirmar fuera de este repositorio** de [plan.md](plan.md) antes de dar la
  feature por lista para producción: la feature `013-modules-permissions-catalogs` de
  `mailySoft-usuarios` debe estar comprometida a git y desplegada, con los 9 módulos de clínica creados
  y el permiso `modules:read` asociado al rol correcto. Ninguna tarea de aquí puede resolver eso: son
  trabajo de otro repositorio.

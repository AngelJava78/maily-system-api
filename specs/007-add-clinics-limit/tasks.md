---

description: "Task list for feature 007-add-clinics-limit (límite de clínicas por suscripción)"
---

# Tasks: Límite de clínicas por suscripción

**Input**: Design documents from `/specs/007-add-clinics-limit/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md.
Requiere la **constitución v1.0.0** vigente (sin cambios). `006-add-subscription-type` ya está en
`main`.

**Tests**: Incluidas (Principio V). Se sigue TDD dentro de cada fase. Ninguna prueba llama a la API
de usuarios ni al API de clínicas reales; esta feature tampoco las llama en producción (FR-010).

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). US1 y US2 (P1) son
independientes entre sí; US3 (P2) depende solo de la Fase Foundational, no de US1/US2. A diferencia
de `006`, no hay ninguna fase de "datos existentes": el `DEFAULT 1` de la migración basta (research
R5), sin ningún script de reconciliación.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1, US2, US3); sin etiqueta en Setup,
  Foundational y Polish

## Referencias rápidas

- Decisiones: [research.md](research.md) (R1–R7)
- Columna, CHECK, DTOs y tabla de validación: [data-model.md](data-model.md)
- Esquema SQL completo: [contracts/database-schema.sql](contracts/database-schema.sql)
- Contrato HTTP v4.0.0 (OpenAPI 3.1): [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
- Catálogo de errores (CERO códigos nuevos): [contracts/error-catalog.md](contracts/error-catalog.md)
- Guía de validación: [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json`;
  escribir tokens, contraseñas o secretos reales en cualquier archivo; añadir dependencias fuera de
  la tabla del stack; tocar `specs/001-subscriptions-api/`, `specs/004-correct-subscriptions-api/`,
  `specs/005-health-monitoring/` ni `specs/006-add-subscription-type/` (quedan como registro
  histórico).
- **No se toca la migración `0005`**: es una migración nueva, `0006`, que solo agrega (nunca
  reescribe nada de `0001` a `0005`).
- **`project-definition/DATA_SCHEMA.md` y `project-definition/create_database.sql` YA están
  actualizados** (se hizo durante `/speckit-plan`, Principio VI): no hay que tocarlos salvo para
  verificarlos en el Polish (T026).
- **Idioma** (Principio VII): `clinics_limit` en inglés (identificador); sus mensajes, en español.
- **Mensajes exactos**: salen de [contracts/error-catalog.md](contracts/error-catalog.md); no se
  parafrasean.
- **Pruebas, en dos niveles (Principio V, enmienda 2026-10-27)**: `uv run pytest` (sin nada más)
  corre **solo lo rápido** (dobles de prueba, sin PostgreSQL) — es lo que se corre durante esta
  implementación. Las pruebas de `tests/integration/` y las de `tests/contract/` que usan `api`/
  `health_api` quedan marcadas `slow` automáticamente (hook en `tests/conftest.py`) y se excluyen
  por defecto; para correr una en particular mientras se escribe (TDD rojo→verde de esa prueba),
  hay que pedirlo explícito: `docker compose up -d db && uv run pytest <archivo> -m ""`. La corrida
  completa de la suite (`-m ""` sin ruta) y las colecciones de Postman (Newman) **no** son parte de
  esta implementación: son la puerta de calidad antes de integrar a `main` (ver Fase 6). Ninguna
  prueba necesita `USERS_API_*`/`CLINICS_API_*` reales.
- **Constantes y nombres nuevos**:

  | Constante / nombre | Valor | Módulo |
  |---|---|---|
  | `SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE` *(nuevo)* | «El límite de clínicas debe ser un número entero de 1 a 100.» | `src/messages.py` |
  | `SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE` *(nuevo)* | «Una suscripción Individual debe tener límite de clínicas igual a 1.» | `src/messages.py` |
  | `SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE` *(nuevo)* | «El límite de clínicas no puede modificarse en una suscripción Individual.» | `src/messages.py` |
  | `("clinics_limit", "required")`, `("clinics_limit", "invalid")` *(nuevas)* | ambas → `SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE` | `VALIDATION_MESSAGES["subscriptions"]` |
  | `subscriptions_clinics_limit_check` | restricción `CHECK` con nombre explícito (dos columnas) | `subscriptions` |

- **Interfaces compartidas nuevas o modificadas**:
  - `src/exceptions.py`: `AppError.field_error(field, message)` — el `@staticmethod` que hoy define
    `MonitoredComponentDataError` **se sube** a `AppError` (clase base), sin cambiar su
    comportamiento; `MonitoredComponentDataError` sigue usándolo igual (herencia). + nueva
    `class SubscriptionDataError(AppError)`: `code = ErrorCode.VALIDATION_ERROR`,
    `status_code = 422`, `__init__(self, errors: list[dict[str, Any]])` (mismo patrón que
    `MonitoredComponentDataError`).
  - `src/models/subscription.py`: + `clinics_limit: Mapped[int] = mapped_column(Integer,
    server_default=text("1"))` (mismo criterio que `subscription_type_id`: `server_default`
    declarado también en el modelo, no solo en la migración, para que `alembic check` no detecte
    diferencia); `__table_args__` gana
    `CheckConstraint("(subscription_type_id = 1 AND clinics_limit = 1) OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)", name="clinics_limit_check")`
    (nombre bare: la convención de `src/models/base.py` ya antepone `subscriptions_`, igual que
    `consulting_rooms_limit_check`; pasarle el nombre ya prefijado lo duplica).
  - `src/dtos/subscription.py`:
    - `SubscriptionRead.clinics_limit: int = Field(ge=1, le=100, description=..., examples=[5])`.
    - `SubscriptionCreate.clinics_limit: int = Field(ge=1, le=100, description=...)` (obligatorio,
      sin `default`) + `@field_validator("clinics_limit") def clinics_limit_matches_type(cls,
      value, info: ValidationInfo):` que, si `info.data.get("subscription_type_id") == 1 and value
      != 1`, levanta `ValueError(SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE)` (el `1` se
      escribe literal, igual criterio que `SubscriptionStatusChange.status_id`: los DTOs no
      importan constantes de `src/models/`). Un `field_validator` sobre el campo, no un
      `model_validator` de clase: así el error sale con `field: "clinics_limit"`, no con la raíz
      del modelo (`"body"`).
    - `SubscriptionUpdate.clinics_limit: int | None = Field(default=None, ge=1, le=100,
      description=...)` + `@field_validator("clinics_limit") def clinics_limit_cannot_be_null(...)`
      que levanta `ValueError(SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE)` si el valor es `None`
      (mismo patrón que `consulting_rooms_limit_cannot_be_null`).
  - `src/repositories/subscription_repository.py`: `create(...)` gana el parámetro con nombre
    `clinics_limit: int`, incluido en `insert(Subscription).values(...)`. `update(...)` **no**
    cambia: ya aplica `changes` de forma genérica (`.values(**changes)`), así que `clinics_limit`
    fluye solo cuando llega en el diccionario.
  - `src/services/subscription_service.py`:
    - `create(data, token)`: pasa `clinics_limit=data.clinics_limit` a `repository.create(...)`.
    - `update(subscription_id, data, token)`: la condición que hoy dispara una lectura previa
      (`if "module_keys" in changes`) se generaliza a `if "module_keys" in changes or
      "clinics_limit" in changes` (una sola lectura con `get_current_by_id`, reutilizada por
      ambos). Si `"clinics_limit" in changes` y la suscripción leída tiene
      `subscription_type_id == SubscriptionType.INDIVIDUAL`, levanta `SubscriptionDataError([
      AppError.field_error("clinics_limit", SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE)])`
      **antes** de intentar `module_keys` o el repositorio (importar `SubscriptionType` de
      `src.models.subscription_type`, igual que ya hace el Repository).
  - `tests/helpers.py`: `insert_subscription(...)` gana `clinics_limit: int = 1`.
  - `tests/unit/fakes.py`: `FakeSubscriptionRepository.add()`/`.create()` ganan
    `clinics_limit: int = 1`, pasado a `Subscription(...)`.

---

## Phase 1: Setup

**Purpose**: Confirmar el punto de partida.

- [X] T001 Verificar prerrequisitos: `git status --short` no muestra cambios sin seguimiento fuera
  de `specs/007-add-clinics-limit/` y `project-definition/`; `.specify/feature.json` contiene
  `"feature_directory": "specs/007-add-clinics-limit"`; `docker compose up -d db && uv run pytest`
  está en verde (línea base, con `006` ya integrada); `uv run alembic current` muestra `0005`.

**Checkpoint**: línea base confirmada, lista para agregar la migración `0006`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: La columna, el `CHECK`, los mensajes, la excepción compartida y los DTOs que las tres
historias necesitan. **Ninguna historia puede empezar sin esta fase.**

### Tests (escribirlos primero; deben fallar contra el código que todavía no tiene `clinics_limit`)

- [X] T002 [P] `tests/integration/test_migrations.py`: aplicar `0001` → `0006` sobre una base vacía
  agrega `subscriptions.clinics_limit` (`NOT NULL`, `DEFAULT 1`); `uv run alembic downgrade base`
  revierte las seis sin error (quita primero el `CHECK` y la columna de `0006`, luego sigue con
  `0005` a `0001`); `uv run alembic check` no detecta diferencias tras `0006`. Insertar, con la base
  en `0005`, una fila Individual (`subscription_type_id=1`) y otra Empresarial
  (`subscription_type_id=2`) directo por SQL, **antes** de aplicar `0006`, y luego subir deja ambas
  con `clinics_limit = 1` (verifica el `DEFAULT`, FR-007).
- [X] T003 [P] `tests/integration/test_subscriptions_constraints.py`: con la base en `0006`, insertar
  directo por SQL `subscription_type_id=1, clinics_limit=2` (o cualquier valor ≠ 1) →
  `DBAPIError` SQLSTATE `23514`, `constraint = "subscriptions_clinics_limit_check"`; con
  `subscription_type_id=1, clinics_limit=1` no falla; con `subscription_type_id=2, clinics_limit=0`
  o `clinics_limit=101` → mismo SQLSTATE/constraint; con `subscription_type_id=2, clinics_limit=1` y
  con `clinics_limit=100` (bordes) no falla; omitir la columna en un `INSERT` crudo usa el
  `DEFAULT 1`.
- [X] T004 [P] `tests/unit/test_subscription_dtos.py`: **Crear** —
  `SubscriptionCreate` sin `clinics_limit`, con `null`, con un valor no entero (`"1"`, `true`,
  `1.5`), o con `0`/`101`/negativo → 422 con el mensaje exacto «El límite de clínicas debe ser un
  número entero de 1 a 100.»; con `subscription_type_id=1` (Individual) y `clinics_limit` de `2`,
  `0` o `100` → 422 con el mensaje exacto «Una suscripción Individual debe tener límite de clínicas
  igual a 1.»; con `subscription_type_id=1, clinics_limit=1` se acepta; con
  `subscription_type_id=2, clinics_limit` en `1`, `50` o `100` (bordes incluidos) se acepta; con
  `subscription_type_id=99` (no existe; no es responsabilidad del DTO) y `clinics_limit=50` se
  acepta por el DTO (el catálogo lo resuelve el Service, research R2). **Actualizar** —
  `SubscriptionUpdate(clinics_limit=None)` → 422 con el mismo mensaje de rango (validador "no
  nulo"); `clinics_limit` fuera de 1–100 → mismo mensaje; `clinics_limit` en 1–100 (bordes
  incluidos) se acepta, con o sin otro campo válido junto.

### Implementation

- [X] T005 [P] `alembic/versions/0006_add_clinics_limit.py` (**nuevo**; `revision = "0006"`,
  `down_revision = "0005"`): `op.add_column("subscriptions", sa.Column("clinics_limit",
  sa.Integer(), nullable=False, server_default=sa.text("1")))`; luego
  `op.create_check_constraint("subscriptions_clinics_limit_check", "subscriptions",
  "(subscription_type_id = 1 AND clinics_limit = 1) OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)")`.
  `downgrade()`: `op.drop_constraint("subscriptions_clinics_limit_check", "subscriptions",
  type_="check")` y luego `op.drop_column("subscriptions", "clinics_limit")` (orden inverso). Hace
  pasar T002 y T003.
- [X] T006 [P] `src/models/subscription.py`: añadir `clinics_limit: Mapped[int] =
  mapped_column(Integer, server_default=text("1"))` (después de
  `new_patients_per_year_limit`, antes de `status_id`, mismo orden que la migración/el esquema);
  añadir a `__table_args__` el `CheckConstraint` de dos columnas con nombre
  `subscriptions_clinics_limit_check` (ver Convenciones). Debe coincidir exactamente con T005:
  `uv run alembic check` sin diferencias.
- [X] T007 [P] `src/messages.py`: añadir `SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE`,
  `SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE` y `SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE`
  (textos exactos en la tabla de Convenciones); en `VALIDATION_MESSAGES["subscriptions"]`, añadir
  `("clinics_limit", "required")` y `("clinics_limit", "invalid")`, ambas →
  `SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE` (mismo patrón que `consulting_rooms_limit`). Hace
  pasar T004.
- [X] T008 [P] `src/exceptions.py`: subir el `@staticmethod field_error(field, message)` de
  `MonitoredComponentDataError` a `AppError` (clase base; `MonitoredComponentDataError` ya no lo
  redefine, lo hereda); añadir `class SubscriptionDataError(AppError)` en la sección
  `--- Subscriptions ---`: `code = ErrorCode.VALIDATION_ERROR`, `status_code = 422`,
  `__init__(self, errors: list[dict[str, Any]])` que guarda `self.errors = errors` y llama a
  `super().__init__(VALIDATION_ERROR_MESSAGE)` (mismo patrón que `MonitoredComponentDataError`,
  sin `ErrorCode` nuevo). También en `src/error_handlers.py`: `subscription_data_error_handler`
  (análogo a `component_data_error_handler`, traduce `error.errors` con
  `translate_validation_errors(error.errors, "subscriptions")`) registrado en
  `register_error_handlers` antes del `AppError` genérico — sin este registro, `SubscriptionDataError`
  caería en el manejador genérico de `AppError` y respondería sin `errors[]`.
- [X] T009 [P] `src/dtos/subscription.py`: `SubscriptionRead` gana `clinics_limit: int` (`Field(ge=1,
  le=100, ...)`), colocado junto a los otros cuatro límites; `SubscriptionCreate` gana
  `clinics_limit: int` (`Field(ge=1, le=100, ...)`, sin `default`) + el `field_validator` nuevo
  sobre `clinics_limit` (ver Convenciones; importar `SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE`
  de `src.messages` y `ValidationInfo` de `pydantic`); `SubscriptionUpdate` gana
  `clinics_limit: int | None = Field(default=None, ge=1,
  le=100, ...)` + el `@field_validator("clinics_limit")` "no nulo" (importar
  `SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE`). Hace pasar T004.
- [X] T010 [P] `tests/helpers.py` y `tests/unit/fakes.py`: `insert_subscription(...)` gana
  `clinics_limit: int = 1` (incluido en el diccionario `values`); `FakeSubscriptionRepository.add()`
  gana `clinics_limit: int = 1`, pasado al `Subscription(...)` que construye; `.create()` gana el
  mismo parámetro con nombre y lo reenvía a `self.add(...)`.

**Checkpoint**: `uv run alembic upgrade head`, `uv run alembic check`, y (con `docker compose up -d
db`) `uv run pytest tests/integration/test_migrations.py
tests/integration/test_subscriptions_constraints.py -m ""` en verde (hay que forzar `-m ""`: son
`slow` por defecto); `uv run pytest tests/unit/test_subscription_dtos.py` en verde con la corrida
normal, sin nada especial. (`SubscriptionRepository.create` y `SubscriptionService.update` todavía
no conocen `clinics_limit`: esta fase no hace pasar la suite completa, ni tiene por qué —eso es la
Fase 6.)

---

## Phase 3: User Story 1 - Crear una suscripción con el límite de clínicas correcto para su tipo (Priority: P1) 🎯 MVP

**Goal**: crear exige `clinics_limit` (FR-001); para Individual solo se acepta `1` (FR-002); para
cualquier otro tipo, un entero de 1 a 100 (FR-003); fuera de esas reglas no se crea nada.

**Independent Test**: ver [spec.md](spec.md#user-story-1---crear-una-suscripción-con-el-límite-de-clínicas-correcto-para-su-tipo-priority-p1).

### Tests for User Story 1 (escribirlas primero; deben fallar)

- [X] T011 [P] [US1] `tests/unit/test_subscription_service.py`: `create(data, token)` con
  `data.clinics_limit = 1` (y `subscription_type_id = 1`) pasa `clinics_limit=1` a
  `repository.create(...)`; con `data.clinics_limit = 25` (y `subscription_type_id = 2`) pasa `25`.
- [X] T012 [US1] `tests/contract/test_subscriptions_api.py`: `POST /api/v1/subscriptions` con
  `subscription_type_id: 1, clinics_limit: 1` → 201 con `clinics_limit: 1`; con
  `subscription_type_id: 1` y `clinics_limit` distinto de `1` → 422 con el mensaje exacto «Una
  suscripción Individual debe tener límite de clínicas igual a 1.»; con `subscription_type_id: 2` y
  `clinics_limit` en `1`, `50` o `100` → 201 con ese valor; con `subscription_type_id: 2` y
  `clinics_limit` en `0` o `101` → 422 con el mensaje exacto «El límite de clínicas debe ser un
  número entero de 1 a 100.»; sin `clinics_limit` → 422 con el mismo mensaje de obligatoriedad; en
  todos los rechazos, la suscripción **no** aparece después en `GET /api/v1/subscriptions`.
- [X] T013 [P] [US1] `tests/integration/test_subscription_repository.py`: `create(...)` con
  `clinics_limit=1` (Individual) y con `clinics_limit=30` (Empresarial) persiste y devuelve ese
  valor exacto tras recargar de la base real.

### Implementation for User Story 1

- [X] T014 [US1] `src/repositories/subscription_repository.py`: `create(...)` gana el parámetro con
  nombre `clinics_limit: int`, incluido en `insert(Subscription).values(...)`. Hace pasar T013.
- [X] T015 [US1] `src/services/subscription_service.py`: `create(data, token)` pasa
  `clinics_limit=data.clinics_limit` a `repository.create(...)`. Hace pasar T011/T012.
- [X] T016 [US1] `src/routers/subscriptions.py`: `CREATED` gana `"clinics_limit": 25`;
  `CREATE_EXAMPLES["completo"]` gana `"clinics_limit": 25` (es Empresarial) y
  `CREATE_EXAMPLES["minimo"]` gana `"clinics_limit": 1` (es Individual); `WRITE_VALIDATION_ERROR`
  gana `limite_clinicas_obligatorio` (`code: "validation_error"`, `errors: [{"field":
  "clinics_limit", "message": "El límite de clínicas debe ser un número entero de 1 a 100."}]`) y
  `limite_clinicas_no_valido_para_individual` (mismo `code`, mensaje «Una suscripción Individual
  debe tener límite de clínicas igual a 1.»); la descripción de `create_subscription` gana un
  párrafo sobre la regla de `clinics_limit` según el tipo (ver
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)). Hace pasar T012.

**Checkpoint**: se pueden crear suscripciones con el límite de clínicas correcto para su tipo;
fuera de esa regla, nada se crea. `uv run pytest tests/unit/test_subscription_service.py` en verde
con la corrida normal (T011, sin DB); `uv run pytest tests/contract/test_subscriptions_api.py -m
""` en verde con `docker compose up -d db` (T012, T013 — es `slow`, hay que forzar `-m ""`).

---

## Phase 4: User Story 2 - Ver el límite de clínicas al consultar una suscripción (Priority: P1)

**Goal**: el listado completo y la consulta por identificador muestran `clinics_limit` (FR-004),
junto a los otros cuatro límites.

**Independent Test**: ver [spec.md](spec.md#user-story-2---ver-el-límite-de-clínicas-al-consultar-una-suscripción-priority-p1).

### Tests for User Story 2

- [X] T017 [P] [US2] `tests/contract/test_subscriptions_api.py`: crear una suscripción Individual
  (`clinics_limit: 1`) y una Empresarial (`clinics_limit: 40`); `GET /api/v1/subscriptions` devuelve
  cada una con su propio `clinics_limit`, junto a `consulting_rooms_limit`, `doctors_limit`,
  `assistants_limit` y `new_patients_per_year_limit`; `GET /api/v1/subscriptions/{id}` de cada una
  devuelve el mismo valor.

### Implementation for User Story 2

- [X] T018 [US2] `src/routers/subscriptions.py`: `LIST_EXAMPLE` gana `"clinics_limit": 5` en el
  primer elemento (Empresarial) y `"clinics_limit": 1` en el segundo (Individual). La Foundational
  (T006, T009) ya basta para que la respuesta real lo haga bien; esta tarea es solo la
  documentación. Hace pasar T017.

**Checkpoint**: catálogo y detalle exponen el límite de clínicas de cada suscripción. `uv run
pytest tests/contract/test_subscriptions_api.py -m ""` en verde (con `docker compose up -d db`;
es `slow`, hay que forzar `-m ""`).

---

## Phase 5: User Story 3 - El límite de clínicas se comporta según el tipo al actualizar (Priority: P2)

**Goal**: en una suscripción Individual, `clinics_limit` es fijo para siempre: cualquier intento de
enviarlo —mismo valor o distinto, solo o con otros campos válidos— rechaza toda la solicitud
(FR-005). En una no Individual, se puede modificar dentro de 1 a 100 (FR-006), igual que los otros
cuatro límites.

**Independent Test**: ver [spec.md](spec.md#user-story-3---el-límite-de-clínicas-se-comporta-según-el-tipo-al-actualizar-priority-p2).

### Tests for User Story 3 (escribirlas primero; deben fallar)

- [X] T019 [P] [US3] `tests/unit/test_subscription_service.py`: con un `FakeSubscriptionRepository`
  que ya tiene una suscripción Individual (`subscription_type_id=1, clinics_limit=1`),
  `update(id, SubscriptionUpdate(clinics_limit=1), token)` levanta `SubscriptionDataError` con
  `errors == [{"field": "clinics_limit", "message": "El límite de clínicas no puede modificarse en
  una suscripción Individual."}]`, **sin** llamar a `repository.update(...)`; lo mismo con
  `clinics_limit=50` y con `SubscriptionUpdate(clinics_limit=1, monthly_price=Decimal("950.00"))`
  (tampoco cambia `monthly_price`). Con una suscripción Empresarial
  (`subscription_type_id=2, clinics_limit=10`), `update(id, SubscriptionUpdate(clinics_limit=80),
  token)` sí llama a `repository.update(...)` con `{"clinics_limit": 80}` en `changes`. Una
  actualización que no incluye `clinics_limit` no dispara ninguna lectura adicional más allá de la
  que ya existía para `module_keys`.
- [X] T020 [US3] `tests/contract/test_subscriptions_api.py`: `PATCH
  /api/v1/subscriptions/{id}` sobre una Individual con `{"clinics_limit": 1}` → 422 con el mensaje
  exacto «El límite de clínicas no puede modificarse en una suscripción Individual.»; con
  `{"clinics_limit": 50, "monthly_price": "950.00"}` → también 422, mismo mensaje, y
  `monthly_price` **no** cambia; sobre una Empresarial con `{"clinics_limit": 80}` → 200 con
  `clinics_limit: 80`; sobre la misma Empresarial con `{"clinics_limit": 0}` o `{"clinics_limit":
  101}` → 422 con el mensaje exacto «El límite de clínicas debe ser un número entero de 1 a 100.»,
  sin cambiar el límite ya guardado; con `{"monthly_price": "950.00"}` (sin `clinics_limit`, sobre
  cualquier tipo) → 200, cambia con normalidad y el límite permanece igual.

### Implementation for User Story 3

- [X] T021 [US3] `src/services/subscription_service.py`: en `update(subscription_id, data, token)`,
  cambiar `if "module_keys" in changes:` por una condición que también dispare con
  `"clinics_limit" in changes`, leyendo la suscripción una sola vez con
  `self._repository.get_current_by_id(subscription_id)` y reutilizándola para ambas comprobaciones;
  si la suscripción no existe, `SubscriptionNotFoundError` (como ya ocurre hoy para `module_keys`);
  si `"clinics_limit" in changes` y `subscription.subscription_type_id ==
  SubscriptionType.INDIVIDUAL`, levantar `SubscriptionDataError([AppError.field_error(
  "clinics_limit", SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE)])` antes de resolver `module_keys`
  o llamar al repositorio (importar `SubscriptionType` de `src.models.subscription_type` y
  `AppError`/`SubscriptionDataError` de `src.exceptions`). Hace pasar T019/T020.
- [X] T022 [US3] `src/routers/subscriptions.py`: `UPDATE_EXAMPLES` gana `limite_clinicas`
  (`{"clinics_limit": 50}`, resumen "Subir el límite de clínicas (solo válido en una suscripción no
  Individual)"); `WRITE_VALIDATION_ERROR` gana `limite_clinicas_no_permitido_individual`
  (`errors: [{"field": "clinics_limit", "message": "El límite de clínicas no puede modificarse en
  una suscripción Individual."}]`) y `limite_clinicas_fuera_de_rango` (mismo mensaje que
  `limite_clinicas_obligatorio` de T016); la descripción de `update_subscription` gana un párrafo
  sobre `clinics_limit` (modificable salvo en Individual, ver
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)). Hace pasar T020.

**Checkpoint**: `uv run pytest tests/unit/test_subscription_service.py` en verde con la corrida
normal (T019, sin DB); `uv run pytest tests/contract/test_subscriptions_api.py -m ""` en verde con
`docker compose up -d db` (T020 — es `slow`, hay que forzar `-m ""`).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: versión del contrato y mantener al día la colección de Postman automatizada. Por la
enmienda del Principio V (2026-10-27), esta fase **no** ejecuta Newman ni la colección manual
(`002-manual-postman-collection`, que ya no se mantiene — ver Convenciones): eso le toca a la
puerta de calidad antes de integrar a `main` (pipeline de CI o, mientras no exista, a quien haga el
merge).

- [X] T023 [P] `src/__init__.py`: `VERSION = "4.0.0"`; `pyproject.toml`: `[project] version =
  "4.0.0"` (igual valor; `tests/unit/test_version.py` exige que las dos y `uv.lock` coincidan);
  correr `uv lock` para que `uv.lock` quede con `4.0.0`. Confirmar que `uv run pytest
  tests/unit/test_version.py tests/contract/test_openapi_contract.py` sigue en verde con la corrida
  normal (ninguna de las dos necesita PostgreSQL) y que `test_openapi_contract.py` sigue esperando
  **18** códigos de error (research R4 — esta feature no agrega ninguno).
- [X] T024 [P] `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`:
  los cuerpos de `create_subscription` existentes ganan `clinics_limit` (coherente con su
  `subscription_type_id`: `1` si Individual, un valor de 1 a 100 si no); + nueva petición
  `create_subscription: límite de clínicas inválido para Individual (422)` en «1. Catálogo»; + nueva
  petición `update_subscription: el límite de clínicas no se puede modificar en una Individual
  (422)` y `update_subscription: subir el límite de clínicas de una Empresarial` en «2. Consultar y
  actualizar». Solo se edita el archivo JSON; **no** se corre Newman aquí (Convenciones).
- [X] T025 Verificación final rápida (lo único que corre en esta implementación): `uv run pytest`
  (corrida normal, sin DB) en verde. Dejar anotado para quien integre a `main` que falta correr la
  puerta completa: `docker compose up -d db && uv run pytest -m ""` (incluye T002, T003, T012,
  T013, T017 y T020) y, aparte, Newman sobre
  `MailySoft-System-Suscripciones.postman_collection.json` (nivel 3 de
  [quickstart.md](quickstart.md)) — ninguna de las dos se ejecuta como parte de esta tarea.
- [X] T026 [P] Revisión final de documentación (sin ejecutar nada contra una base de datos): los
  mensajes nuevos coinciden **verbatim** con
  [contracts/error-catalog.md](contracts/error-catalog.md); `project-definition/DATA_SCHEMA.md` y
  `create_database.sql` (ya actualizados durante `/speckit-plan`) siguen coincidiendo, línea a
  línea, con la migración `0006` terminada (revisión visual; la comparación ejecutada contra una
  base real —`create_database.sql` vs. `alembic upgrade head` + `alembic check`— queda para la
  puerta de calidad de T025, no se repite aquí).

**Checkpoint final de esta implementación**: `uv run pytest` en verde (solo pruebas unitarias).
Pendiente, antes de integrar a `main` (fuera de `/speckit-implement`): `uv run pytest -m ""` +
Newman, según T025.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** US1, US2 y US3 (las tres leen o
  escriben `clinics_limit`).
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: dependen solo de Foundational; no
  dependen entre sí.
- **Polish (Phase 6)**: depende de todas las fases anteriores.

### Archivos compartidos (límite real del paralelismo)

Las historias comparten `src/routers/subscriptions.py` (T016, T018, T022: mismo diccionario
`WRITE_VALIDATION_ERROR` en T016/T022, así que van en orden aunque no lleven `[P]` entre sí),
`src/services/subscription_service.py` (T015, T021) y `tests/contract/test_subscriptions_api.py`
(T012, T017, T020). Dentro de cada fase, las tareas que tocan el mismo archivo se numeran en orden.

### Parallel Opportunities

- Foundational: T002–T004 (pruebas) son `[P]` entre sí; T005–T010 (implementación) son `[P]` entre
  sí (archivos distintos; la tabla de Convenciones ya fija los nombres compartidos, así que pueden
  escribirse a la vez).
- US1: T011 y T013 son `[P]` entre sí (no tocan el mismo archivo que T012).
- US3: T019 es `[P]` (no comparte archivo con T020).
- Polish: T023, T024 y T026 son `[P]` entre sí; T025 (la verificación final) se ejecuta aparte,
  después de que todo lo anterior ya esté implementado.

---

## Parallel Example: Foundational

```bash
# Escribir a la vez las pruebas de Foundational (archivos distintos):
Task: "Migración, columna y DEFAULT en tests/integration/test_migrations.py"
Task: "CHECK de dos columnas en tests/integration/test_subscriptions_constraints.py"
Task: "DTOs (crear y actualizar) en tests/unit/test_subscription_dtos.py"

# Después, las piezas independientes:
Task: "alembic/versions/0006_add_clinics_limit.py (nueva)"
Task: "src/models/subscription.py (columna + CHECK)"
Task: "src/messages.py (tres mensajes + dos entradas de VALIDATION_MESSAGES)"
Task: "src/exceptions.py (field_error a AppError + SubscriptionDataError) y src/error_handlers.py (su handler registrado)"
Task: "src/dtos/subscription.py (clinics_limit en los tres DTOs + field_validator cruzado)"
Task: "tests/helpers.py y tests/unit/fakes.py"
```

---

## Implementation Strategy

### MVP (Foundational + US1 + US2)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational: columna, CHECK, DTOs, mensajes, excepción).
2. Completar Phase 3 (US1: ya se puede crear con el límite correcto) y Phase 4 (US2: ya se ve en las
   lecturas).
3. **DETENERSE y validar**: `uv run pytest` (rápido, sin DB) en verde. El Nivel 2 de
   [quickstart.md](quickstart.md) (la pila e2e completa) y Newman quedan para la puerta de calidad
   antes de integrar, no para esta validación intermedia.

### Incremental Delivery

1. Foundational → la columna y el `CHECK` ya existen; las suscripciones que ya había quedan con
   `clinics_limit = 1` por el `DEFAULT` (válido para cualquier tipo).
2. + US1 → ya se puede crear con el límite correcto según el tipo.
3. + US2 → ya se ve en el listado y en el detalle (MVP completo).
4. + US3 → confirmado que es fijo en Individual y modificable en las demás.
5. Polish → versión del contrato y la colección automatizada de Postman actualizada (sin
   ejecutarla). La puerta completa (`uv run pytest -m ""` + Newman) se corre antes de integrar a
   `main`, fuera de esta implementación (Principio V, enmienda 2026-10-27).

---

## Notes

- `[P]` = archivos distintos y sin dependencias abiertas; `[Story]` = trazabilidad con la spec.
- A diferencia de `006`, no hay ninguna fase de "datos existentes" con script propio: el `DEFAULT 1`
  de la migración (T005) ya deja a cualquier suscripción existente con un valor válido para su tipo
  (research R5).
- Verificar que las pruebas **fallan** antes de implementar y que pasan después: para una prueba
  marcada `slow` (T002, T003, T012, T013, T017, T020), eso significa correrla una vez con `-m ""`
  mientras se escribe, no dejarla correr sola por defecto.
- No hacer commits salvo que la persona los pida.
- La colección manual (`002-manual-postman-collection`) no se toca en esta feature ni en las
  siguientes (decisión del responsable, 2026-10-27): aunque `clinics_limit` la vuelva inválida, se
  deja como registro histórico. La exploración manual se hace importando `/openapi.json` en
  Postman.

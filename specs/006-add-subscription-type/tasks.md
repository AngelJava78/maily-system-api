---

description: "Task list for feature 006-add-subscription-type (tipo de suscripción: Individual o Empresarial) — reescrita tras Clarifications (catálogo en tabla)"
---

# Tasks: Tipo de suscripción (Individual o Empresarial)

**Input**: Design documents from `/specs/006-add-subscription-type/`

**Revisión**: esta lista **reemplaza** a la anterior. El responsable del proyecto corrigió, vía
`/speckit-clarify`, el diseño central: el tipo no es una columna con `CHECK` fijo a dos valores —es
un catálogo propio (tabla `subscription_types`), igual que el estatus de la suscripción. Una primera
implementación (con el diseño anterior) ya existe en el repositorio; estas tareas la **corrigen**,
no la repiten desde cero. Donde una tarea dice "REESCRIBE", el archivo ya existe con el diseño
anterior y hay que cambiarlo de fondo, no solo ampliarlo.

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
(reescritos). Requiere la **constitución v1.0.0** vigente (sin cambios).

**Tests**: Incluidas (Principio V). Se sigue TDD dentro de cada fase. Ninguna prueba llama a la API
de usuarios ni al API de clínicas reales.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). US1 y US2 (P1) son
las que cambian de verdad con esta corrección (la forma de crear y de leer el tipo); US3 (P2) sigue
sin tareas de implementación. La Fase 6 (datos existentes) resulta mucho más pequeña que en la
versión anterior: el script y el método del Service que reintenta son **agnósticos** del valor exacto
que se escribe, así que no cambian; solo cambia qué escribe el Repository.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1, US2, US3); sin etiqueta en Setup,
  Foundational, «Datos existentes» y Polish

## Referencias rápidas

- Decisiones (corregidas tras Clarifications): [research.md](research.md) (R1, R2, R5, R8 nuevos o
  reescritos; R3, R4, R6, R7 sin cambios de fondo)
- Tabla nueva, columna FK, DTOs: [data-model.md](data-model.md)
- Esquema SQL completo (incluida `subscription_types`): [contracts/database-schema.sql](contracts/database-schema.sql)
- Contrato HTTP v3.0.0 (OpenAPI 3.1, validado): [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
- Código nuevo `subscription_type_not_found` (antes se pensó "ninguno"): [contracts/error-catalog.md](contracts/error-catalog.md)
- Guía de validación (incluye el Nivel 2b del script): [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json`;
  escribir tokens, contraseñas o secretos reales en cualquier archivo; añadir dependencias fuera de
  la tabla del stack; tocar `specs/001-subscriptions-api/`, `specs/004-correct-subscriptions-api/`
  ni `specs/005-health-monitoring/` (quedan como registro histórico).
- **No se apila una migración `0006`**: `0005` nunca se usó fuera de este repositorio (ni en una
  base compartida ni en producción), así que se **reescribe en el mismo archivo**. Antes de tocarla,
  hay que revertir las bases locales que ya la tengan aplicada con el diseño anterior (T001).
- **Idioma** (Principio VII): identificadores en inglés (`subscription_type_id`,
  `subscription_types`); los **datos** del catálogo (`name`: "Individual", "Empresarial") en
  español, igual que `subscription_statuses` ("Activa", "Inactiva") — a diferencia de la primera
  versión de esta feature, que (equivocadamente) guardaba los valores en inglés porque entonces no
  existía un `id` estable que cumpliera ese papel.
- **Mensajes exactos**: salen de [contracts/error-catalog.md](contracts/error-catalog.md); no se
  parafrasean.
- **Pruebas**: `docker compose up -d db && uv run pytest`. Ninguna prueba necesita
  `USERS_API_*`/`CLINICS_API_*` reales.
- **Constantes y nombres nuevos o corregidos**:

  | Constante / nombre | Valor | Módulo |
  |---|---|---|
  | `SubscriptionType.INDIVIDUAL` | `1` | `src/models/subscription_type.py` (**nuevo**) |
  | `SubscriptionType.ENTERPRISE` | `2` | `src/models/subscription_type.py` (**nuevo**) |
  | `SUBSCRIPTION_TYPE_FK_NAME` | `"subscriptions_subscription_type_id_fkey"` | `src/models/subscription.py` |
  | `SUBSCRIPTION_TYPE_REQUIRED_MESSAGE` *(texto nuevo)* | «El tipo de suscripción es obligatorio y debe ser un número entero positivo.» | `src/messages.py` |
  | `SUBSCRIPTION_TYPE_NOT_FOUND_MESSAGE` *(nuevo)* | «No se encontró el tipo de suscripción con el identificador {subscription_type_id}.» | `src/messages.py` |
  | `SUBSCRIPTION_TYPE_IMMUTABLE_MESSAGE` | sin cambios de texto: «El tipo de suscripción no puede modificarse una vez creada.» | `src/messages.py` |
  | `ErrorCode.SUBSCRIPTION_TYPE_NOT_FOUND` *(nuevo)* | `"subscription_type_not_found"` | `src/messages.py` |
  | `subscription_types_name_key` | restricción única automática | `subscription_types` |
  | `subscriptions_subscription_type_id_fkey` | clave foránea automática | `subscriptions` |

  **Ya no existen** (del diseño anterior, eliminar): `SUBSCRIPTION_TYPES`, `RegisteredSubscriptionType`,
  `_validate_subscription_type`, `SubscriptionType` (el alias `Annotated` de `src/dtos/subscription.py`
  — no confundir con el modelo ORM nuevo del mismo nombre en `src/models/`),
  `SUBSCRIPTION_TYPE_INVALID_MESSAGE`, la entrada `("subscription_type", ...)` de
  `VALIDATION_MESSAGES`, el `CheckConstraint` `subscription_type_check`.

- **Interfaces compartidas nuevas o modificadas**:
  - `src/models/subscription_type.py` (**nuevo**): `class SubscriptionType(Base)` — idéntica forma a
    `src/models/subscription_status.py` (`id`, `name`, `description`; `INDIVIDUAL`/`ENTERPRISE` como
    `ClassVar[int]`).
  - `src/dtos/subscription_type.py` (**nuevo**): `class SubscriptionTypeRead(BaseModel)` — idéntica
    forma a `src/dtos/status.py` (`id`, `name`).
  - `src/models/subscription.py`: `subscription_type_id: Mapped[int]` (FK, `server_default=text("1")`)
    reemplaza a `subscription_type: Mapped[str]`; nueva `subscription_type: Mapped["SubscriptionType"]
    = relationship(lazy="raise")` (como `status`).
  - `src/dtos/subscription.py`: `SubscriptionRead.subscription_type: SubscriptionTypeRead` (objeto,
    reemplaza a la cadena); `SubscriptionCreate.subscription_type_id: Annotated[int, Field(strict=True,
    gt=0)]` (reemplaza a `subscription_type: SubscriptionType`); `SubscriptionUpdate` sin cambios (sigue
    sin este campo).
  - `src/repositories/subscription_repository.py`: `_select_with_status()` → renombrado
    `_select_with_relations()`, con `joinedload(Subscription.status)` **y**
    `joinedload(Subscription.subscription_type)` (actualizar sus 3 usos: `list_current`,
    `get_current_by_id`, `_reload`); `create(...)` recibe `subscription_type_id: int` (reemplaza a
    `subscription_type: str`); `mark_enterprise(ids)` escribe
    `subscription_type_id=SubscriptionType.ENTERPRISE` (reemplaza a `subscription_type="enterprise"`).
  - `src/services/subscription_service.py`: `create(data, token)` pasa `data.subscription_type_id`;
    además de `UniqueViolationError`, atrapa `ForeignKeyViolationError` y, si
    `error.constraint_name == SUBSCRIPTION_TYPE_FK_NAME`, levanta
    `SubscriptionTypeNotFoundError(data.subscription_type_id)` (si no, re-lanza).
    `reconcile_types_from_clinic_counts` **no cambia**: ya era agnóstico del valor exacto que escribe
    `mark_enterprise`.
  - `src/exceptions.py`: `SubscriptionTypeNotFoundError(subscription_type_id: int)` (422, **nuevo**).
  - `src/scripts/backfill_subscription_types.py`: **sin cambios** (llama a
    `reconcile_types_from_clinic_counts`, agnóstico del valor).
  - `tests/unit/fakes.py`: `FakeSubscriptionRepository.add()`/`.create()` ganan
    `subscription_type_id: int = 1` (reemplaza a `subscription_type: str = "individual"`);
    `mark_enterprise` escribe `2`.
  - `tests/helpers.py`: `insert_subscription(...)` gana `subscription_type_id: int = 1` (reemplaza a
    `subscription_type: str = "individual"`).

---

## Phase 1: Setup

**Purpose**: Confirmar el punto de partida y dejar las bases locales listas para que la migración
`0005` se pueda reescribir sin arrastrar el esquema anterior.

- [X] T001 Verificar prerrequisitos y preparar el entorno: `git status --short` no muestra cambios
  sin seguimiento fuera de `specs/006-add-subscription-type/` y `project-definition/`;
  `.specify/feature.json` contiene `"feature_directory": "specs/006-add-subscription-type"`;
  `docker compose up -d db && uv run pytest` está en verde (línea base, con el diseño **anterior**
  aún vigente en el código); después, revertir la base local `maily_system` (la que usa
  `docker compose run --rm migrate`, NO la de pruebas) a la revisión `0004`, para que al reescribir
  `0005` (T005) se pueda volver a aplicar limpia:
  `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5434/maily_system" uv run alembic downgrade 0004`.
  La base de pruebas (`maily_system_test`) no necesita este paso: el fixture `migrated_db` la baja a
  `base` y la vuelve a subir en cada sesión de pytest, con el contenido de migración que esté vigente
  en ese momento.

**Checkpoint**: línea base confirmada; `maily_system` local en `0004`, lista para la migración
reescrita.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: El catálogo nuevo, la columna que lo referencia, los DTOs y los mensajes que las tres
historias comparten. **Ninguna historia puede empezar sin esta fase.**

### Tests (escribirlos primero; deben fallar contra el código que todavía tiene el diseño anterior)

- [X] T002 [P] `tests/integration/test_migrations.py` (reescribir los casos de `subscription_type`):
  aplicar `0001` → `0005` sobre una base vacía crea `subscription_types` con exactamente las filas
  `(1, 'Individual')` y `(2, 'Empresarial')`, y `subscriptions` gana `subscription_type_id`;
  `uv run alembic downgrade base` revierte las cinco sin error (primero quita la columna, luego la
  tabla); `uv run alembic check` no detecta diferencias tras `0005`; insertar una fila directo por
  SQL **antes** de aplicar `0005` (con la base en `0004`) y luego subir deja esa fila con
  `subscription_type_id = 1` (verifica el `DEFAULT`, FR-001/FR-008).
- [X] T003 [P] `tests/integration/test_subscriptions_constraints.py` (reescribir los casos de
  `subscription_type`): insertar con `subscription_type_id = 99` (no existe en `subscription_types`)
  → `DBAPIError` SQLSTATE `23503` (clave foránea, **ya no** `23514`), `constraint =
  "subscriptions_subscription_type_id_fkey"`; con `1` o `2` no falla; omitir la columna en un
  `INSERT` crudo usa el `DEFAULT 1`.
- [X] T004 [P] `tests/unit/test_subscription_dtos.py` (reescribir la sección de `subscription_type`):
  `SubscriptionCreate` sin `subscription_type_id`, con `null`, con un valor que no es un entero
  (`"1"`, `true`, `1.5`), o con `0`/negativo → 422 con el mensaje exacto «El tipo de suscripción es
  obligatorio y debe ser un número entero positivo.»; con `1` o `2` se acepta (la existencia real en
  el catálogo la comprueba el Service, no el DTO — research R5, no hace falta un doble de base de
  datos aquí). `SubscriptionUpdate(subscription_type_id=1)` y `(subscription_type_id=2)` (con o sin
  otro campo válido junto) → `ValidationError` (`extra_forbidden`) con el mensaje exacto «El tipo de
  suscripción no puede modificarse una vez creada.» en `errors[0]`. `SubscriptionRead.model_validate`
  de un objeto con `subscription_type=SimpleNamespace(id=2, name="Empresarial")` expone
  `read.subscription_type.id == 2` y `.name == "Empresarial"`.

### Implementation

- [X] T005 [P] `alembic/versions/0005_add_subscription_type.py` (**reescribir en el mismo archivo**;
  sigue siendo `revision = "0005"`, `down_revision = "0004"`): `op.create_table("subscription_types",
  ...)` (id, name, description, misma forma que `subscription_statuses` en `0001`);
  `op.bulk_insert(...)` con `(1, 'Individual', ...)` y `(2, 'Empresarial', ...)` (mismo patrón que
  `0002_seed_subscription_statuses.py`: `sa.table(...)` + `op.bulk_insert`) y
  `op.execute("SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2)")`;
  `op.add_column("subscriptions", sa.Column("subscription_type_id", sa.Integer(),
  sa.ForeignKey("subscription_types.id"), nullable=False, server_default=sa.text("1")))`.
  `downgrade()`: `op.drop_column("subscriptions", "subscription_type_id")` y luego
  `op.drop_table("subscription_types")` (orden inverso). Hace pasar T002 y T003.
- [X] T006 [P] `src/models/subscription_type.py` (**nuevo**): `class SubscriptionType(Base)` —
  `__tablename__ = "subscription_types"`; `INDIVIDUAL: ClassVar[int] = 1`,
  `ENTERPRISE: ClassVar[int] = 2`; `id: Mapped[int]` (PK), `name: Mapped[str]` (`String(50)`,
  `unique=True`), `description: Mapped[str | None]` (`Text`) — exactamente como
  `src/models/subscription_status.py`.
- [X] T007 [P] `src/models/subscription.py`: quitar `subscription_type: Mapped[str]` y su
  `CheckConstraint("subscription_type IN (...)", name="subscription_type_check")`; añadir
  `SUBSCRIPTION_TYPE_FK_NAME = "subscriptions_subscription_type_id_fkey"` (constante a nivel de
  módulo, como `SUBSCRIPTION_NAME_INDEX`); añadir `subscription_type_id: Mapped[int] =
  mapped_column(Integer, ForeignKey("subscription_types.id"), server_default=text("1"))` y
  `subscription_type: Mapped["SubscriptionType"] = relationship(lazy="raise")` (importar
  `SubscriptionType` bajo `TYPE_CHECKING`, como ya se hace con `SubscriptionStatus`). Debe coincidir
  exactamente con T005: `uv run alembic check` sin diferencias.
- [X] T008 [P] `src/dtos/subscription_type.py` (**nuevo**): `class SubscriptionTypeRead(BaseModel)`
  — `id: int = Field(ge=1, ...)`, `name: str = Field(...)` — exactamente como `src/dtos/status.py`
  (`model_config = ConfigDict(from_attributes=True, ...)`).
- [X] T009 [P] `src/dtos/subscription.py`: quitar `SUBSCRIPTION_TYPES`, `RegisteredSubscriptionType`,
  `_validate_subscription_type` y el alias `SubscriptionType` (y los imports de `Literal`/
  `BeforeValidator` si quedan sin uso); importar `SubscriptionTypeRead` de
  `src/dtos/subscription_type.py`; `SubscriptionRead` cambia `subscription_type: str` por
  `subscription_type: SubscriptionTypeRead`; `SubscriptionCreate` cambia `subscription_type:
  SubscriptionType` por `subscription_type_id: Annotated[int, Field(strict=True, gt=0)]` (sin
  `default`, por lo tanto obligatorio; entero estricto como `SubscriptionStatusChange.status_id`).
  `SubscriptionUpdate` no cambia (sigue sin este campo, a propósito). Hace pasar T004.
- [X] T010 [P] `src/messages.py`: quitar `SUBSCRIPTION_TYPE_INVALID_MESSAGE`; cambiar el texto de
  `SUBSCRIPTION_TYPE_REQUIRED_MESSAGE` al nuevo (tabla de constantes de arriba); añadir
  `SUBSCRIPTION_TYPE_NOT_FOUND_MESSAGE` y `ErrorCode.SUBSCRIPTION_TYPE_NOT_FOUND =
  "subscription_type_not_found"`; en `VALIDATION_MESSAGES["subscriptions"]`, reemplazar las entradas
  `("subscription_type", "required")` y `("subscription_type", "forbidden")` por
  `("subscription_type_id", "required")`, `("subscription_type_id", "invalid")` (ambas con
  `SUBSCRIPTION_TYPE_REQUIRED_MESSAGE`, mismo patrón que `status_id`) y
  `("subscription_type_id", "forbidden")` (con `SUBSCRIPTION_TYPE_IMMUTABLE_MESSAGE`, sin cambios de
  texto). Hace pasar T004.
- [X] T011 [P] `src/exceptions.py`: `class SubscriptionTypeNotFoundError(AppError)` — `code =
  ErrorCode.SUBSCRIPTION_TYPE_NOT_FOUND`, `status_code = 422`, `__init__(self, subscription_type_id:
  int)` usando `SUBSCRIPTION_TYPE_NOT_FOUND_MESSAGE.format(subscription_type_id=subscription_type_id)`
  (mismo patrón que `SubscriptionNotFoundError`).
- [X] T012 [P] `tests/unit/fakes.py` y `tests/helpers.py`: `FakeSubscriptionRepository.add()`/
  `.create()` e `insert_subscription()` (y por lo tanto `Api.insert(...)`) cambian
  `subscription_type: str = "individual"` por `subscription_type_id: int = 1`.
  `FakeSubscriptionRepository.mark_enterprise` escribe `subscription_type_id = 2` (en vez de
  `subscription_type = "enterprise"`).
- [X] T013 [P] `src/repositories/subscription_repository.py`: renombrar `_select_with_status()` a
  `_select_with_relations()`, con `.options(joinedload(Subscription.status),
  joinedload(Subscription.subscription_type))` (actualizar sus tres usos: `list_current`,
  `get_current_by_id`, `_reload`).

**Checkpoint**: `uv run alembic upgrade head`, `uv run alembic check`, y
`uv run pytest tests/integration/test_migrations.py tests/integration/test_subscriptions_constraints.py tests/unit/test_subscription_dtos.py`
en verde. (`SubscriptionRepository.create`/`mark_enterprise` siguen con la firma anterior hasta la
Fase 3/6: esta fase no hace pasar todavía la suite completa.)

---

## Phase 3: User Story 1 - Crear una suscripción indicando su tipo (Priority: P1) 🎯 MVP

**Goal**: crear exige `subscription_type_id` (FR-002); un valor que no es un entero positivo se
rechaza por el DTO, y uno que no existe en el catálogo se rechaza por el Service (sin una lectura
previa, research R5), sin crear nada en ningún caso.

**Independent Test**: ver [spec.md](spec.md#user-story-1---crear-una-suscripción-indicando-su-tipo-priority-p1).

### Tests for User Story 1 (escribirlas primero; deben fallar)

- [X] T014 [P] [US1] `tests/unit/test_subscription_service.py` (reescribir los casos de
  `subscription_type`): `create(data, token)` con `data.subscription_type_id = 1` pasa
  `subscription_type_id=1` a `repository.create(...)`; con `2` pasa `2`. Con un
  `FakeSubscriptionRepository` cuyo `create` lanza `ForeignKeyViolationError("subscriptions_subscription_type_id_fkey")`,
  `create()` levanta `SubscriptionTypeNotFoundError` con ese `subscription_type_id`; con
  `ForeignKeyViolationError("otra_restriccion")`, la excepción se re-lanza sin traducir (como ya hace
  `UniqueViolationError` para un nombre repetido vs. otra violación única).
- [X] T015 [US1] `tests/contract/test_subscriptions_api.py` (reescribir los casos de
  `subscription_type`): `POST /api/v1/subscriptions` con `subscription_type_id: 1` → 201 con
  `subscription_type: {"id": 1, "name": "Individual"}`; con `2` → 201 con `{"id": 2, "name":
  "Empresarial"}`; sin `subscription_type_id`, con `null`, o con `0`/negativo/no-entero → 422 con el
  mensaje exacto «El tipo de suscripción es obligatorio y debe ser un número entero positivo.»; con
  `subscription_type_id: 99` (no existe) → 422 con `code: "subscription_type_not_found"` y el mensaje
  exacto «No se encontró el tipo de suscripción con el identificador 99.»; en los rechazos, la
  suscripción **no** aparece después en `GET /api/v1/subscriptions`.

### Implementation for User Story 1

- [X] T016 [US1] `src/services/subscription_service.py`: `create(data, token)` pasa
  `subscription_type_id=data.subscription_type_id` a `repository.create(...)`; en el mismo bloque
  `try`/`except` que ya traduce `UniqueViolationError`, añadir
  `except ForeignKeyViolationError as error:` que, si
  `error.constraint_name == SUBSCRIPTION_TYPE_FK_NAME`, levanta
  `SubscriptionTypeNotFoundError(data.subscription_type_id) from error`, y si no, `raise` (re-lanza
  sin traducir). Hace pasar T014.
- [X] T017 [US1] `src/repositories/subscription_repository.py`: `create(...)` cambia el parámetro
  `subscription_type: str` por `subscription_type_id: int`, incluido en
  `insert(Subscription).values(...)`. Hace pasar T014/T015.
- [X] T018 [US1] `src/routers/subscriptions.py`: `CREATE_EXAMPLES` («completo» y «mínimo») usan
  `subscription_type_id` (`2` y `1` respectivamente); `CREATED` (y cualquier otro ejemplo de
  respuesta) muestra `subscription_type` como objeto `{"id": ..., "name": ...}`;
  `WRITE_VALIDATION_ERROR` reemplaza `tipo_no_valido` por `tipo_no_encontrado` (`code:
  "subscription_type_not_found"`) y actualiza el mensaje de `tipo_obligatorio`, igual que
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml). Hace pasar T015.

**Checkpoint**: se pueden crear suscripciones Individual y Empresarial por `id`; falta, un valor no
entero, o un `id` que no existe se rechazan sin crear nada. `uv run pytest
tests/contract/test_subscriptions_api.py` en verde.

---

## Phase 4: User Story 2 - Ver el tipo al consultar una suscripción (Priority: P1)

**Goal**: el listado completo y la consulta por identificador muestran `subscription_type` como
objeto `{id, name}` (FR-003), igual que `status`.

**Independent Test**: ver [spec.md](spec.md#user-story-2---ver-el-tipo-al-consultar-una-suscripción-priority-p1).

### Tests for User Story 2

- [X] T019 [P] [US2] `tests/contract/test_subscriptions_api.py` (reescribir los casos de
  `subscription_type`): crear una suscripción Individual (`subscription_type_id: 1`) y otra
  Empresarial (`2`); `GET /api/v1/subscriptions` devuelve cada una con
  `subscription_type: {"id": 1, "name": "Individual"}` / `{"id": 2, "name": "Empresarial"}`, sin
  mezclarse; `GET /api/v1/subscriptions/{id}` de cada una devuelve el mismo objeto correcto.

### Implementation for User Story 2

- [X] T020 [US2] `src/routers/subscriptions.py`: `LIST_EXAMPLE` muestra `subscription_type` como
  objeto `{"id": 2, "name": "Empresarial"}` / `{"id": 1, "name": "Individual"}` en sus dos elementos
  (igual que [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)). La
  Foundational (T007, T009, T013) ya basta para que la respuesta real lo haga bien; esta tarea es
  solo la documentación. Hace pasar T019.

**Checkpoint**: catálogo y detalle exponen el tipo correcto de cada suscripción, como objeto.
`uv run pytest tests/contract/test_subscriptions_api.py` en verde.

---

## Phase 5: User Story 3 - El tipo queda fijo después de creada (Priority: P2)

**Goal**: actualizar rechaza por completo cualquier solicitud que incluya `subscription_type_id`
—con el mismo valor que ya tiene o con otro— sin cambiar ningún dato de esa solicitud (FR-004). Sin
cambios de fondo respecto a la versión anterior de esta feature: solo cambia el nombre del campo.

**Independent Test**: ver [spec.md](spec.md#user-story-3---el-tipo-queda-fijo-después-de-creada-priority-p2).

### Tests for User Story 3

- [X] T021 [US3] `tests/contract/test_subscriptions_api.py` (reescribir el campo del cuerpo):
  `PATCH /api/v1/subscriptions/{id}` sobre una suscripción Individual con `{"subscription_type_id":
  2, "monthly_price": "950.00"}` → 422 con el mensaje exacto «El tipo de suscripción no puede
  modificarse una vez creada.», y `monthly_price` **no** cambia; con `{"subscription_type_id": 1}`
  (el mismo valor que ya tiene) → también 422, mismo mensaje; con `{"monthly_price": "950.00"}` (sin
  `subscription_type_id`) → 200, cambia con normalidad y el tipo permanece igual.

**Sin tareas de implementación**: el rechazo nace de que `subscription_type_id` nunca se agregó a
`SubscriptionUpdate` (T009) y de que `VALIDATION_MESSAGES["subscriptions"][("subscription_type_id",
"forbidden")]` ya da el mensaje exacto (T010); ambas son de la Fase 2.

**Checkpoint**: `uv run pytest tests/contract/test_subscriptions_api.py` en verde.

---

## Phase 6: Datos existentes — reconciliación de tipos (FR-008 a FR-010; sin historia de usuario)

**Purpose**: igual que en la versión anterior, FR-001/FR-002/FR-008 ya quedan resueltos por el
`DEFAULT` de la migración (T005); esta fase resuelve FR-009 (ascender a Empresarial) y FR-010
(reintentar sin límite). **Mucho más pequeña que antes**: el Service y el script son agnósticos del
valor exacto que escribe `mark_enterprise`, así que no cambian; solo su implementación en el
Repository (y el doble) cambian de `"enterprise"` (texto) a `SubscriptionType.ENTERPRISE` (entero).

**Independent Test**: con `FakeClinicsApi(counts={1: 1, 2: 2, 3: 5})` y tres suscripciones (`id` 1, 2
y 3, todas con `subscription_type_id = 1`), tras ejecutar la reconciliación la 1 sigue en `1` y la 2
y la 3 quedan en `2`.

### Tests (escribirlas primero; deben fallar)

- [X] T022 [P] `tests/unit/test_subscription_service.py` (actualizar las aserciones de
  `reconcile_types_from_clinic_counts`, mismos escenarios que ya existían): tras reconciliar,
  `repository.items[2].subscription_type_id == SubscriptionType.ENTERPRISE` y
  `repository.items[3].subscription_type_id == SubscriptionType.ENTERPRISE`;
  `repository.items[1].subscription_type_id == SubscriptionType.INDIVIDUAL`. La lógica de "a quién
  le toca" (research R5 del método, sin cambios) no se repite aquí.
- [X] T023 [P] `tests/integration/test_subscription_repository.py` (actualizar las aserciones de
  `mark_enterprise`, mismos escenarios): tras `mark_enterprise([2, 3])`, `subscription_type_id` es
  `2` para esas filas y sigue en `1` para la que no se tocó; `mark_enterprise([])` no cambia nada;
  `mark_enterprise` también marca una fila en estatus Eliminada.
- [X] T024 `tests/unit/test_backfill_subscription_types.py`: **ejecutar sin cambios** y confirmar que
  sigue en verde (el bucle de reintento no conoce el valor exacto que escribe
  `reconcile_types_from_clinic_counts`, así que no necesita tocarse).

### Implementation

- [X] T025 `src/repositories/subscription_repository.py`: `mark_enterprise(ids)` cambia
  `.values(subscription_type="enterprise")` por
  `.values(subscription_type_id=SubscriptionType.ENTERPRISE)` (importar `SubscriptionType` de
  `src/models/subscription_type.py`). Hace pasar T023.
- [X] T026 [P] `tests/unit/fakes.py`: `FakeSubscriptionRepository.mark_enterprise` (ya existe, T012)
  confirma que escribe `subscription_type_id = 2`, no `subscription_type = "enterprise"`. Hace pasar
  T022.

**Checkpoint**: `uv run pytest tests/unit/test_subscription_service.py
tests/integration/test_subscription_repository.py tests/unit/test_backfill_subscription_types.py` en
verde.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: catálogo de errores (17 → 18 códigos), colección de Postman, y validación de punta a
punta con el diseño corregido.

- [X] T027 `tests/contract/test_openapi_contract.py`: `test_the_error_codes_are_the_seventeen_of_the_catalog`
  pasa a esperar **18** códigos (`len(ErrorCode) == 18`, uno más por `subscription_type_not_found`);
  renombrar la prueba o actualizar su comentario para que ya no diga "diecisiete". Confirmar que
  `schema["info"]["version"] == "3.0.0"` sigue correcto (sin cambios respecto a la corrección
  anterior de esta misma prueba).
- [X] T028 [P] `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`:
  los cuerpos de `create_subscription` (incluido el que ya se había agregado en «1. Catálogo» con
  `subscription_type: "individual"`) cambian a `subscription_type_id` (entero: `1` o `2`); la
  petición `update_subscription: el tipo no se puede modificar (422)` (ya existente) cambia su
  cuerpo a `{"subscription_type_id": 1}` y su aserción al mensaje de inmutabilidad (sin cambios de
  texto); la petición `create_subscription: sin tipo (422)` (ya existente) no cambia su intención,
  solo que ahora el campo ausente es `subscription_type_id`; + nueva petición
  `create_subscription: tipo inexistente (422)` en «1. Catálogo» (`subscription_type_id: 99`,
  espera `code: "subscription_type_not_found"`).
- [X] T029 Ejecutar la guía de validación completa de [quickstart.md](quickstart.md) (niveles 1 a 3,
  incluido el Nivel 2b) contra el diseño corregido: crear con `subscription_type_id`, confirmar la
  forma `{id, name}` en las lecturas, confirmar `subscription_type_not_found` para un id inexistente,
  y repetir la validación del script de reconciliación (reintento incluido) ya hecha para la primera
  versión — debe comportarse igual, solo que ahora escribe `subscription_type_id = 2`.
- [X] T030 [P] Revisión final: ningún identificador nuevo en español (salvo los **datos** del
  catálogo, `name`, que sí van en español a propósito — Convenciones de esta feature); los mensajes
  nuevos coinciden **verbatim** con [contracts/error-catalog.md](contracts/error-catalog.md);
  `project-definition/DATA_SCHEMA.md` y `create_database.sql` (ya corregidos durante
  `/speckit-plan`) siguen coincidiendo con la migración `0005` reescrita (T005): ejecutar
  `create_database.sql` sobre una base local vacía y comparar contra `alembic upgrade head` +
  `alembic check`, igual que ya se validó durante la planificación.

**Checkpoint final**: `uv run pytest`, `uv run alembic check`, Newman y el quickstart completo, todo
en verde, con el diseño del catálogo en tabla.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias; **debe** completarse antes de T005 (revertir la base local
  antes de reescribir la migración).
- **Foundational (Phase 2)**: depende de Setup; **bloquea** US1, US2, US3 y la Fase 6 (todas leen o
  escriben `subscription_type_id`/`subscription_type`).
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: dependen solo de Foundational; no dependen
  entre sí.
- **Datos existentes (Phase 6)**: depende solo de Foundational; no depende de US1/US2/US3 ni
  viceversa.
- **Polish (Phase 7)**: depende de todas las fases anteriores.

### Archivos compartidos (límite real del paralelismo)

Las historias comparten `src/routers/subscriptions.py`, `src/services/subscription_service.py`,
`src/repositories/subscription_repository.py`, `src/dtos/subscription.py`, `tests/unit/fakes.py` y
`tests/contract/test_subscriptions_api.py`. Dentro de cada fase, las tareas que tocan el mismo
archivo se numeran en orden aunque no lleven `[P]`.

### Parallel Opportunities

- Foundational: T002–T004 (pruebas) son `[P]` entre sí; T005–T013 (implementación) son `[P]` entre
  sí (archivos distintos, aunque T007 y T009 usan nombres que T006 y T008 definen: la tabla de
  interfaces de arriba ya fija esos nombres, así que pueden escribirse a la vez).
- Datos existentes: T022–T023 son `[P]` entre sí; T025 y T026 también.
- Polish: T028 y T030 son `[P]`; T027 y T029 se ejecutan/editan en su propio orden.

---

## Parallel Example: Foundational

```bash
# Escribir a la vez las pruebas de Foundational (archivos distintos):
Task: "Migración, tabla nueva y DEFAULT en tests/integration/test_migrations.py"
Task: "Clave foránea en tests/integration/test_subscriptions_constraints.py"
Task: "DTOs (crear, leer, actualizar) en tests/unit/test_subscription_dtos.py"

# Después, las piezas independientes:
Task: "alembic/versions/0005_add_subscription_type.py (reescrita)"
Task: "src/models/subscription_type.py (nuevo)"
Task: "src/models/subscription.py (columna FK + relationship)"
Task: "src/dtos/subscription_type.py (nuevo)"
Task: "src/dtos/subscription.py (subscription_type_id, objeto anidado)"
Task: "src/messages.py (mensajes y código de error nuevos)"
Task: "src/exceptions.py (SubscriptionTypeNotFoundError)"
Task: "tests/unit/fakes.py y tests/helpers.py"
Task: "src/repositories/subscription_repository.py (_select_with_relations)"
```

---

## Implementation Strategy

### MVP de esta corrección (Foundational + US1 + US2)

1. Completar Phase 1 (Setup: revertir la base local) y Phase 2 (Foundational: tabla, columna, DTOs).
2. Completar Phase 3 (US1: ya se pueden crear suscripciones con `subscription_type_id`) y Phase 4
   (US2: ya se puede ver el tipo como objeto).
3. **DETENERSE y validar**: `uv run pytest`; Nivel 2 de [quickstart.md](quickstart.md).

### Incremental Delivery

1. Foundational → la tabla y la columna ya existen; las suscripciones que ya había quedan en
   Individual (`subscription_type_id = 1`) por el `DEFAULT`.
2. + US1 → ya se pueden crear suscripciones con su tipo, por `id`.
3. + US2 → ya se puede ver ese tipo como objeto `{id, name}` (MVP completo).
4. + US3 → confirmado que el tipo no puede cambiarse después.
5. + Datos existentes → las que ya tenían más de una clínica quedan en Empresarial (`2`).
6. Polish → catálogo de errores, Postman y validación de punta a punta.

---

## Notes

- `[P]` = archivos distintos y sin dependencias abiertas; `[Story]` = trazabilidad con la spec.
- US3 sigue sin tareas de implementación: la inmutabilidad nace de la ausencia del campo en
  `SubscriptionUpdate`, no de una comprobación.
- La Fase 6 es deliberadamente pequeña: corregir el diseño no significa reescribir el script de
  reconciliación ni su bucle de reintento, que nunca conocieron el valor exacto que se escribe.
- Verificar que las pruebas **fallan** antes de implementar y que pasan después.
- No hacer commits salvo que la persona los pida.
- Recordar los **puntos a confirmar fuera de este repositorio** de [plan.md](plan.md): quién ejecuta
  el script de reconciliación y con qué token, y que el sistema que administra las clínicas empiece
  a leer `subscription_type.id` (ya no una cadena) antes de asociar una clínica.

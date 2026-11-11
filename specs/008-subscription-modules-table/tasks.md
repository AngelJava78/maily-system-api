---

description: "Task list for feature 008-subscription-modules-table (módulos de la suscripción en su propia tabla)"
---

# Tasks: Guardar los módulos de la suscripción en su propia tabla

**Input**: Design documents from `/specs/008-subscription-modules-table/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md.
Requiere la **constitución v1.1.0** vigente (sin cambios). `007-add-clinics-limit` ya está en `main`.

**Tests**: Incluidas (Principio V). Se sigue TDD dentro de cada fase. Esta feature no cambia el
contrato publicado ni ningún código de error (FR-004 a FR-008): la mayoría de las pruebas que ya
existen sobre el comportamiento de módulos **no cambian sus aserciones**; solo cambian las que
llegan hasta la columna que se quita por SQL crudo.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). US1 y US2 (P1)
son independientes entre sí; US3 (P2) también depende solo de la Fase Foundational. A diferencia de
`007`, casi todo el código de producción de esta feature es compartido por las tres historias (la
migración, el modelo nuevo y el Repository reescrito son el único mecanismo que las tres ponen a
prueba desde ángulos distintos), así que vive en Foundational; cada historia aporta sobre todo
pruebas nuevas o corregidas, no implementación nueva.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1, US2, US3); sin etiqueta en Setup,
  Foundational y Polish

## Referencias rápidas

- Decisiones: [research.md](research.md) (R1–R9)
- Tabla nueva, columna que se quita y repository: [data-model.md](data-model.md)
- Esquema SQL completo: [contracts/database-schema.sql](contracts/database-schema.sql)
- Guía de validación: [quickstart.md](quickstart.md)
- Contrato HTTP, catálogo de errores y matriz de permisos: **sin cambios**, ver
  [specs/007-add-clinics-limit/contracts/](../007-add-clinics-limit/contracts/) (openapi, error
  catalog, permission matrix) y
  [specs/004-correct-subscriptions-api/contracts/error-catalog.md](../004-correct-subscriptions-api/contracts/error-catalog.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json`;
  escribir tokens, contraseñas o secretos reales en cualquier archivo; añadir dependencias fuera de
  la tabla del stack; tocar `specs/001-subscriptions-api/`, `specs/004-correct-subscriptions-api/`,
  `specs/005-health-monitoring/`, `specs/006-add-subscription-type/` ni
  `specs/007-add-clinics-limit/` (quedan como registro histórico).
- **No se toca la migración `0006`**: es una migración nueva, `0007`, que solo agrega/quita sobre lo
  que entregan `0001` a `0006` (nunca reescribe nada de ellas).
- **`project-definition/DATA_SCHEMA.md` y `project-definition/create_database.sql` YA están
  actualizados** (se hizo durante `/speckit-plan`, Principio VI): no hay que tocarlos salvo para
  verificarlos en el Polish (T018).
- **Sin mensajes nuevos que traducir** (Principio VII): esta feature no agrega ningún error ni
  ninguna validación nueva de cara a quien consume la API; los únicos identificadores nuevos son de
  código (`SubscriptionModule`, `subscription_modules`, `module_key`), en inglés.
- **`VERSION` NO cambia** (sigue en `"4.0.0"`): esta feature no agrega, quita ni modifica ningún
  campo del contrato publicado (a diferencia de `006` y `007`).
- **Mecanismo compartido nuevo** (research R7, generalización de lo que ya existe, no una función
  nueva aparte): `execute_and_commit` en `src/repositories/transactions.py` gana un parámetro de
  palabra clave opcional, `then: Callable[[int], Sequence[Executable]] | None = None`. Si se pasa,
  tras ejecutar `statement` y obtener su `id` (y antes del único `commit`), se ejecutan en orden las
  sentencias que devuelva `then(id)`. Sin `then` (el valor por defecto), el comportamiento es
  exactamente el de hoy: cero cambios para quien ya la usa sin ese parámetro.
- **Interfaces compartidas nuevas o modificadas**:
  - `src/models/subscription_module.py` (**nuevo**): `class SubscriptionModule(Base):
    __tablename__ = "subscription_modules"`; `subscription_id: Mapped[int] =
    mapped_column(Integer, ForeignKey("subscriptions.id"), primary_key=True)`;
    `module_key: Mapped[str] = mapped_column(Text, primary_key=True)`. Sin `__table_args__`: la
    clave primaria compuesta (ambas columnas `primary_key=True`) ya es la única restricción
    (research R1); sin relación de vuelta hacia `Subscription` (nada la necesita).
  - `src/models/subscription.py`: se quita `module_keys: Mapped[list[str]] =
    mapped_column(ARRAY(Text), ...)` y la entrada `CheckConstraint("'patients' = ANY(module_keys)",
    name="module_keys_check")` de `__table_args__`; se agrega `modules: Mapped[list["SubscriptionModule"]]
    = relationship(lazy="raise", order_by="SubscriptionModule.module_key")` y la propiedad de solo
    lectura:
    ```python
    @property
    def module_keys(self) -> list[str]:
        return [m.module_key for m in self.modules]
    ```
    (research R3/R4; sin `TYPE_CHECKING` nuevo porque `SubscriptionModule` se referencia como
    cadena, igual que ya hace `status`/`subscription_type` con sus propios modelos).
  - `src/repositories/subscription_repository.py`:
    - `_select_with_relations()`: agrega `.options(selectinload(Subscription.modules))` a las dos
      ya existentes (`joinedload` de `status` y `subscription_type`); importar `selectinload` de
      `sqlalchemy.orm`.
    - `create(...)`: sin cambios en su firma (sigue recibiendo `module_keys: list[str]`). El
      `insert(Subscription).values(...)` ya no incluye `module_keys` (deja de ser una columna);
      usa `execute_and_commit(self._session, statement, then=lambda subscription_id:
      [insert(SubscriptionModule).values([{"subscription_id": subscription_id, "module_key": k}
      for k in module_keys])])`. Importar `SubscriptionModule` de `src.models.subscription_module`.
    - `update(subscription_id, changes)`: sin cambios en su firma pública (sigue recibiendo
      `changes: Mapping[str, Any]`). Al principio del método, `changes = dict(changes)` (copia
      mutable: el parámetro recibido puede no serlo) y luego `module_keys = changes.pop("module_keys",
      _UNSET)` usando un centinela de módulo (p. ej. `_UNSET = object()`) para distinguir "no vino"
      de `[]` (aunque `[]` nunca llega en la práctica, research R5 de `data-model.md`:
      `_resolve_modules` siempre incluye `patients`). El `UPDATE` de `subscriptions` sigue
      ejecutándose **siempre**, incluso si `changes` queda vacío tras sacar `module_keys` (para
      conservar la comprobación de existencia/estatus y disparar `subscriptions_set_updated_at`,
      research R8): `.values(**changes)` no admite un diccionario vacío (SQLAlchemy no genera un
      `SET` sin columnas), así que en ese caso se usa `.values(id=Subscription.id)` en su lugar —una
      reasignación de `id` a sí mismo, sin efecto en ningún dato de negocio, solo para que el
      `UPDATE` tenga al menos una columna—; si `changes` no quedó vacío, se usa `.values(**changes)`
      como hoy. Al resultado (`then`) se le pasa
      `then=lambda subscription_id: [delete(SubscriptionModule).where(SubscriptionModule.subscription_id
      == subscription_id), insert(SubscriptionModule).values([{"subscription_id": subscription_id,
      "module_key": k} for k in module_keys])]` **solo si** `module_keys is not _UNSET`; si no vino,
      `then=None` (ningún cambio en `subscription_modules`). Importar `delete` de `sqlalchemy`.
  - `tests/helpers.py`: `insert_subscription(...)` conserva su firma (`module_keys: Iterable[str] =
    ("patients",)`); internamente, el `values` del `INSERT` de `Subscription` ya no incluye
    `"module_keys"`; tras el `INSERT ... RETURNING id` (sin `commit` todavía), ejecuta
    `insert(SubscriptionModule).values([{"subscription_id": subscription_id, "module_key": k} for k
    in sorted(module_keys)])` y **entonces** `session.commit()` (una sola transacción). Importar
    `SubscriptionModule`.
  - `tests/unit/fakes.py`: `FakeSubscriptionRepository.add()` deja de pasar `module_keys` al
    construir `Subscription(...)`; después de construirla (mismo punto donde ya se asignan
    `.status` y `.subscription_type`), asigna `subscription.modules =
    [SubscriptionModule(module_key=k) for k in sorted(module_keys)]`. En `update()`, antes del
    `for key, value in changes.items(): setattr(...)` genérico, saca `module_keys` de una copia de
    `changes` (`changes = dict(changes); keys = changes.pop("module_keys", None)`) y, si no es
    `None`, asigna `subscription.modules = [SubscriptionModule(module_key=k) for k in
    sorted(keys)]` (en vez de `setattr`, que ya no aplica: `module_keys` no tiene `setter`).
    Importar `SubscriptionModule` de `src.models.subscription_module`.

---

## Phase 1: Setup

**Purpose**: Confirmar el punto de partida.

- [X] T001 Verificar prerrequisitos: `git status --short` no muestra cambios sin seguimiento fuera
  de `specs/008-subscription-modules-table/` y `project-definition/`; `.specify/feature.json`
  contiene `"feature_directory": "specs/008-subscription-modules-table"`; `docker compose up -d db
  && uv run pytest` está en verde (línea base, con `007` ya integrada); `uv run alembic current`
  muestra `0006`.

**Checkpoint**: línea base confirmada, lista para agregar la migración `0007`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: la tabla nueva, el modelo, el mecanismo de transacción y el Repository reescrito que
las tres historias necesitan para existir siquiera. **Ninguna historia puede empezar sin esta
fase.**

### Tests (escribirlos primero; deben fallar contra el código actual, que todavía tiene `module_keys` como columna)

- [X] T002 [P] `tests/integration/test_migrations.py`: tras aplicar `0001` → `0007` sobre una base
  vacía, el conjunto de columnas de `subscriptions` ya NO incluye `module_keys` (mismo patrón que
  las aserciones ya existentes de "columnas que agrega 0003"/"clinics_limit"); existe la tabla
  `subscription_modules` con exactamente las columnas `subscription_id` y `module_key`; `uv run
  alembic check` no detecta diferencias tras `0007`. `uv run alembic downgrade base` revierte las
  siete sin error (quita primero lo de `0007` —`subscription_modules`, columna y `CHECK` de vuelta
  en `subscriptions`—, luego sigue con `0006` a `0001`); tras revertir por debajo de `0007`, el
  conjunto de columnas de `subscriptions` vuelve a incluir `module_keys` y `subscription_modules`
  ya no existe (mismo patrón que la prueba ya existente de "columnas que quita el downgrade de
  0003"). No verifica contenido de datos todavía (eso es US2, T013).
- [X] T003 [P] `tests/integration/test_subscriptions_constraints.py`: quitar las tres pruebas que
  dependen de la columna/`CHECK` que esta migración elimina —
  `test_module_keys_without_patients_is_rejected` (el `CHECK` `subscriptions_module_keys_check` ya
  no existe: esa regla sigue vigente solo por el Service, research R2 — no hay ninguna prueba de
  reemplazo a nivel de base de datos para esto, a propósito), `test_module_keys_with_patients_is_accepted`
  y `test_module_keys_defaults_to_patients_only` (probaban el `DEFAULT ARRAY['patients']` de la
  columna, que tampoco existe ya) —. El resto del archivo (`insert_with`, `BASE_COLUMNS`,
  `test_each_restriction_rejects_its_invalid_row` y las demás pruebas de límites/tipo/nombre) no
  cambia: ninguna otra usa `module_keys`.

### Implementation

- [X] T004 [P] `alembic/versions/0007_subscription_modules_table.py` (**nuevo**; `revision =
  "0007"`, `down_revision = "0006"`): `upgrade()` — `op.create_table("subscription_modules",
  sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"),
  primary_key=True), sa.Column("module_key", sa.Text(), primary_key=True))`; luego
  `op.execute("INSERT INTO subscription_modules (subscription_id, module_key) SELECT id,
  unnest(module_keys) FROM subscriptions")` (research R5, una sola sentencia, sin script aparte);
  luego `op.drop_constraint("subscriptions_module_keys_check", "subscriptions", type_="check")` y
  `op.drop_column("subscriptions", "module_keys")`. `downgrade()` (orden inverso, research R6):
  `op.add_column("subscriptions", sa.Column("module_keys", postgresql.ARRAY(sa.Text()),
  nullable=False, server_default=sa.text("ARRAY['patients']::text[]")))`; luego
  `op.execute("UPDATE subscriptions SET module_keys = (SELECT COALESCE(array_agg(module_key ORDER
  BY module_key), ARRAY['patients']::text[]) FROM subscription_modules WHERE subscription_id =
  subscriptions.id)")`; luego `op.create_check_constraint("subscriptions_module_keys_check",
  "subscriptions", "'patients' = ANY(module_keys)")`; luego `op.drop_table("subscription_modules")`.
  Hace pasar T002.
- [X] T005 [P] `src/models/subscription_module.py` (**nuevo**): `SubscriptionModule(Base)` según la
  interfaz fijada en Convenciones (clave primaria compuesta, sin `__table_args__`, sin relación de
  vuelta).
- [X] T006 `src/models/subscription.py`: quitar la columna `module_keys` y su `CheckConstraint` de
  `__table_args__`; agregar la relación `modules` y la propiedad `module_keys` según Convenciones.
  Depende de T005 (importa `SubscriptionModule`). Debe coincidir exactamente con T004: `uv run
  alembic check` sin diferencias.
- [X] T007 [P] `src/repositories/transactions.py`: `execute_and_commit` gana el parámetro `then`
  según Convenciones (research R7); sin `then`, mismo comportamiento exacto que hoy (ninguna prueba
  ya existente de este archivo cambia).
- [X] T008 `src/repositories/subscription_repository.py`: `_select_with_relations()` agrega
  `selectinload(Subscription.modules)`; `create(...)` y `update(...)` cambian según Convenciones
  (usan `then` de T007 en vez de incluir `module_keys` en `values(**changes)`/`values(...)`
  directamente). Depende de T005, T006, T007. Hace pasar la prueba ya existente de
  `test_subscription_repository.py` (`created.module_keys == ["patients", "scheduling"]`) sin
  tocarla.
- [X] T009 [P] `tests/helpers.py`: `insert_subscription(...)` cambia según Convenciones. Depende de
  T005.
- [X] T010 [P] `tests/unit/fakes.py`: `FakeSubscriptionRepository.add()`/`.update()` cambian según
  Convenciones. Depende de T005.

**Checkpoint**: `uv run alembic upgrade head`, `uv run alembic check`, y (con `docker compose up -d
db`) `uv run pytest tests/integration/test_migrations.py
tests/integration/test_subscriptions_constraints.py tests/integration/test_subscription_repository.py
-m ""` en verde (hay que forzar `-m ""`: son `slow` por defecto); `uv run pytest` (corrida rápida,
sin DB) también en verde — confirma que `tests/unit/fakes.py` y, por lo tanto,
`tests/unit/test_subscription_service.py` siguen funcionando con el modelo nuevo.

---

## Phase 3: User Story 1 - Crear o actualizar los módulos de una suscripción sin que cambie nada (Priority: P1) 🎯 MVP

**Goal**: el comportamiento ya validado de los módulos (contrato, validación contra `users-api`,
prerrequisitos entre módulos, reemplazo completo al actualizar) sigue siendo exactamente el mismo
(FR-004 a FR-009). Toda la lógica que lo garantiza (`SubscriptionService._resolve_modules`, los
DTOs) **no se toca** en esta feature: ya quedó probada por la Fase Foundational a través del
Repository reescrito. Lo único genuinamente nuevo que esta historia necesita demostrar es que el
reemplazo completo al actualizar (FR-009) es atómico con dos tablas de por medio, no solo con una.

**Independent Test**: ver [spec.md](spec.md#user-story-1---crear-o-actualizar-los-módulos-de-una-suscripción-sin-que-cambie-nada-para-quien-la-administra-priority-p1).

### Tests for User Story 1 (escribirla primero; debe fallar contra el `update()` de la Foundational si el reemplazo no fuera atómico)

- [X] T011 [P] [US1] `tests/integration/test_subscription_repository.py`: crear una suscripción con
  `module_keys=["patients", "scheduling", "reminders"]`; `update(id, {"module_keys":
  ["patients", "finance"]})`; releer de la base real y comprobar que `module_keys` es exactamente
  `["finance", "patients"]` — ni `scheduling` ni `reminders` quedan como filas sueltas en
  `subscription_modules` (consultar la tabla directo por SQL para confirmarlo, no solo la
  propiedad del modelo, que podría ocultar una fila huérfana si no se recargara). FR-009.

### Implementation for User Story 1

Ninguna: la Fase Foundational (T008) ya implementa el reemplazo atómico que esta historia prueba.

**Checkpoint**: `uv run pytest tests/integration/test_subscription_repository.py -m ""` en verde
(con `docker compose up -d db`). Además, sin editar nada, confirmar que
`tests/unit/test_subscription_service.py` y `tests/contract/test_subscriptions_api.py` (salvo la
única línea que toca la US3, T015) siguen en verde exactamente como estaban antes de esta feature —
esa ausencia de cambios **es** la prueba de FR-004 a FR-008.

---

## Phase 4: User Story 2 - Conservar los módulos de las suscripciones que ya existen (Priority: P1)

**Goal**: al aplicar la migración `0007` sobre una base con suscripciones ya creadas, cada una
conserva exactamente el mismo conjunto de módulos que tenía (FR-003); al revertir, se reconstruye
igual.

**Independent Test**: ver [spec.md](spec.md#user-story-2---conservar-los-módulos-de-las-suscripciones-que-ya-existen-priority-p1).

### Tests for User Story 2 (escribirla primero; debe fallar si la migración no migrara los datos)

- [X] T012 [US2] `tests/integration/test_migrations.py`: con la base en `0006` (**antes** de
  aplicar `0007` en la prueba), insertar directo por SQL tres suscripciones con `module_keys`
  distintos entre sí (una con solo `["patients"]`, una con `["patients", "scheduling"]`, una con
  `["patients", "finance", "billing"]`); subir a `0007` y comprobar que `subscription_modules`
  tiene, para cada una, exactamente esas mismas claves (ni una más ni una menos; research R5,
  FR-003); revertir con `uv run alembic downgrade` por debajo de `0007` y comprobar que
  `subscriptions.module_keys` de cada una vuelve a ser exactamente el conjunto original, ordenado
  alfabéticamente (research R6).

### Implementation for User Story 2

Ninguna: la Fase Foundational (T004, la propia migración `0007`) ya implementa la migración y la
reversión de los datos que esta historia prueba.

**Checkpoint**: `uv run pytest tests/integration/test_migrations.py -m ""` en verde (con `docker
compose up -d db`).

---

## Phase 5: User Story 3 - Ningún módulo puede quedar duplicado ni huérfano en la base de datos (Priority: P2)

**Goal**: la base de datos, no solo el código del Service, impide un módulo repetido para la misma
suscripción (FR-002) y una fila sin su suscripción (FR-002); la baja lógica de una suscripción
conserva sus filas de módulo sin tocarlas (FR-010).

**Independent Test**: ver [spec.md](spec.md#user-story-3---ningún-módulo-puede-quedar-duplicado-ni-huérfano-en-la-base-de-datos-priority-p2).

### Tests for User Story 3 (escribirlas primero; deben fallar si la tabla no tuviera su clave primaria/`FOREIGN KEY`, o si la baja lógica tocara los módulos)

- [X] T013 [P] [US3] `tests/integration/test_subscriptions_constraints.py`: insertar una
  suscripción con `insert_with(db_session, "Con modulo")`, leer su `id`, insertar directo por SQL
  una fila en `subscription_modules` (`subscription_id=<id>, module_key='scheduling'`) y
  confirmarla con `commit()`; intentar insertar la misma pareja `(subscription_id, module_key)` de
  nuevo → `DBAPIError` SQLSTATE `23505` (la clave primaria compuesta, sin nombre explícito:
  `subscription_modules_pkey`). Por separado, intentar insertar una fila en `subscription_modules`
  con un `subscription_id` que no existe en `subscriptions` (p. ej. `999999`) → SQLSTATE `23503`
  (`subscription_modules_subscription_id_fkey`). FR-001, FR-002.
- [X] T014 [US3] `tests/contract/test_subscriptions_api.py`:
  `test_deleting_does_not_touch_modules_prices_or_limits` deja de hacer `SELECT module_keys,
  consulting_rooms_limit FROM subscriptions WHERE id = :id`; en su lugar, consulta por separado
  `SELECT module_key FROM subscription_modules WHERE subscription_id = :id ORDER BY module_key`
  (esperando `[("billing",), ("finance",), ("patients",)]`) y `SELECT consulting_rooms_limit FROM
  subscriptions WHERE id = :id` (esperando `[(4,)]`), confirmando lo mismo que antes —que la baja
  lógica no toca los módulos ni los límites— ahora contra la tabla nueva. FR-010.

### Implementation for User Story 3

Ninguna: la clave primaria compuesta y la `FOREIGN KEY` de `subscription_modules` (T004/T005) y el
hecho de que `soft_delete()` del Repository nunca tocó `module_keys` (solo cambia `status_id`) ya
garantizan, sin código nuevo, lo que esta historia prueba.

**Checkpoint**: `uv run pytest tests/integration/test_subscriptions_constraints.py
tests/contract/test_subscriptions_api.py -m ""` en verde (con `docker compose up -d db`).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: confirmar que nada de lo que no debía cambiar, cambió. Por la enmienda del Principio V
(2026-10-27), esta fase **no** ejecuta Newman ni la colección manual: eso le toca a la puerta de
calidad antes de integrar a `main`.

- [X] T015 [P] Confirmar, sin editar nada: `src/__init__.py` (`VERSION`), `pyproject.toml` y
  `uv.lock` siguen en `"4.0.0"` (esta feature no la cambia); `uv run pytest
  tests/unit/test_version.py tests/contract/test_openapi_contract.py` en verde con la corrida
  normal, y `test_openapi_contract.py` sigue esperando **18** códigos de error (ninguno nuevo).
- [X] T016 [P] Confirmar, sin editar nada:
  `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json` no necesita
  ningún cambio (FR-004: ningún cuerpo ni respuesta esperada cambia); correr
  `uv run pytest tests/contract/test_postman_collection.py` (prueba de deriva de esa colección) en
  verde con la corrida normal.
- [X] T017 Verificación final rápida (lo único que corre en esta implementación): `uv run pytest`
  (corrida normal, sin DB) en verde. Dejar anotado para quien integre a `main` que falta correr la
  puerta completa: `docker compose up -d db && uv run pytest -m ""` (incluye T002, T003, T011,
  T012, T013, T014) y, aparte, Newman sobre
  `MailySoft-System-Suscripciones.postman_collection.json` (nivel 3 de
  [quickstart.md](quickstart.md)) — ninguna de las dos se ejecuta como parte de esta tarea.
- [X] T018 [P] Revisión final de documentación (sin ejecutar nada contra una base de datos):
  `project-definition/DATA_SCHEMA.md` y `create_database.sql` (ya actualizados durante
  `/speckit-plan`) siguen coincidiendo, línea a línea, con la migración `0007` terminada (revisión
  visual; la comparación ejecutada contra una base real —`create_database.sql` vs. `alembic upgrade
  head` + `alembic check`— queda para la puerta de calidad de T017, no se repite aquí).

**Checkpoint final de esta implementación**: `uv run pytest` en verde (solo pruebas unitarias).
Pendiente, antes de integrar a `main` (fuera de `/speckit-implement`): `uv run pytest -m ""` +
Newman, según T017.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** US1, US2 y US3 (las tres dependen de
  que `subscription_modules`, el modelo y el Repository reescrito existan).
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: dependen solo de Foundational; no
  dependen entre sí.
- **Polish (Phase 6)**: depende de todas las fases anteriores.

### Dentro de Foundational

T002, T003 (pruebas) son `[P]` entre sí. T004 (migración) y T005 (modelo `SubscriptionModule`) son
`[P]` entre sí (archivos distintos, ninguno depende del otro para escribirse, aunque deben
coincidir en la forma de la tabla). T006 (modelo `Subscription`) depende de T005. T007
(`transactions.py`) es `[P]` respecto a T004–T006 (archivo distinto, sin relación). T008
(`subscription_repository.py`) depende de T005, T006 y T007. T009 (`tests/helpers.py`) y T010
(`tests/unit/fakes.py`) dependen solo de T005 (ambos son `[P]` entre sí y respecto a T006–T008).

### Archivos compartidos (límite real del paralelismo)

`tests/integration/test_migrations.py` se toca en Foundational (T002) y en US2 (T012):
T002 primero (fija la forma de la migración), T012 después (prueba sus datos), mismo archivo, sin
`[P]` entre ambas. `tests/integration/test_subscriptions_constraints.py` se toca en Foundational
(T003, quita pruebas obsoletas) y en US3 (T013, agrega las nuevas): mismo orden, mismo archivo, sin
`[P]` entre ambas. `tests/contract/test_subscriptions_api.py` solo se toca una vez, en US3 (T014).

### Parallel Opportunities

- Foundational: T002–T003 (pruebas) son `[P]` entre sí; T004, T005, T007, T009, T010 son `[P]`
  entre sí (ver arriba); T006 y T008 no son `[P]` (dependen de lo anterior).
- US1: solo hay una tarea (T011).
- US3: T013 es `[P]` (no comparte archivo con T014).
- Polish: T015, T016 y T018 son `[P]` entre sí; T017 (la verificación final) se ejecuta aparte,
  después de que todo lo anterior ya esté implementado.

---

## Parallel Example: Foundational

```bash
# Escribir a la vez las pruebas de Foundational (archivos distintos):
Task: "Forma de la migración 0007 en tests/integration/test_migrations.py"
Task: "Quitar las 3 pruebas obsoletas de módulos en tests/integration/test_subscriptions_constraints.py"

# Después, las piezas independientes:
Task: "alembic/versions/0007_subscription_modules_table.py (nueva)"
Task: "src/models/subscription_module.py (nuevo)"
Task: "src/repositories/transactions.py (parámetro then)"
Task: "tests/helpers.py (insert_subscription en dos inserts)"
Task: "tests/unit/fakes.py (FakeSubscriptionRepository sin module_keys en el constructor)"
```

---

## Implementation Strategy

### MVP (Foundational + US1)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational: tabla, modelo, transacción, Repository).
2. Completar Phase 3 (US1: confirmado que crear/actualizar se comporta exactamente igual que
   antes, incluido el reemplazo atómico).
3. **DETENERSE y validar**: `uv run pytest` (rápido, sin DB) en verde; `uv run pytest
   tests/integration/test_subscription_repository.py -m ""` en verde con `docker compose up -d
   db`. El Nivel 2/3 de [quickstart.md](quickstart.md) (pila e2e completa, Newman) quedan para la
   puerta de calidad antes de integrar, no para esta validación intermedia.

### Incremental Delivery

1. Foundational → existe la tabla nueva, el modelo y el Repository reescrito; nada observable
   cambió todavía de cara a quien consume la API.
2. + US1 → confirmado que crear/actualizar/leer módulos se comporta exactamente igual que antes,
   incluido el reemplazo atómico (MVP).
3. + US2 → confirmado que ninguna suscripción pierde ni gana módulos al desplegar esta corrección.
4. + US3 → confirmado que la base de datos, no solo el Service, impide duplicados y huérfanos, y
   que la baja lógica conserva los módulos.
5. Polish → confirmación de que `VERSION`, el catálogo de errores y la colección de Postman
   automatizada **no** necesitaron ningún cambio. La puerta completa (`uv run pytest -m ""` +
   Newman) se corre antes de integrar a `main`, fuera de esta implementación (Principio V).

---

## Notes

- `[P]` = archivos distintos y sin dependencias abiertas; `[Story]` = trazabilidad con la spec.
- A diferencia de `006`/`007`, casi ninguna historia tiene "Implementation" propia: el único
  mecanismo de esta feature (migración + modelo + Repository) es compartido por las tres desde
  Foundational; cada historia aporta la prueba que demuestra su ángulo (comportamiento preservado,
  datos conservados, integridad en la base), no código nuevo.
- Verificar que las pruebas **fallan** antes de implementar y que pasan después: para una prueba
  marcada `slow` (T002, T003, T011, T012, T013, T014), eso significa correrla una vez con `-m ""`
  mientras se escribe, no dejarla correr sola por defecto.
- No hacer commits salvo que la persona los pida.
- La colección manual (`002-manual-postman-collection`) no se toca en esta feature (decisión del
  responsable, 2026-10-27): queda como registro histórico.

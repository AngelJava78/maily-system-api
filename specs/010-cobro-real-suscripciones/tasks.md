---

description: "Task list for feature 006-cobro-real-suscripciones (Cobro Real de Suscripciones de Clínicas)"
---

# Tasks: Cobro Real de Suscripciones de Clínicas

**Input**: Design documents from `specs/006-cobro-real-suscripciones/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere
Docker Desktop (Compose), `uv` con Python 3.14+. El repositorio ya tiene las specs 001 a 005
implementadas; esta feature **no toca** `subscriptions`, `subscription_statuses` ni sus Services.

**Tests**: Incluidas (Principio V y FR-027). TDD dentro de cada historia: la tarea de prueba se
escribe antes que la de implementación y debe fallar primero. Cada fase termina con
`uv run pytest` en verde.

**Organization**: Agrupadas por historia de usuario de [spec.md](spec.md). Orden de construcción:
**Setup** → **Foundational** (modelo de datos + migración + los dos clientes de integración, sin los
cuales ninguna historia corre) → **US1** (asignar) → **US2** (cobrar) → **US3** (conocer el
resultado) → **US4** (consultar/listar) → **US5** (cancelar) → **Polish**. El **MVP** es Setup +
Foundational + US1 + US2 (sin eso, no hay nada que cobrar ni forma de cobrarlo).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin depender de una tarea abierta)
- **[Story]**: US1 a US5; sin etiqueta en Setup, Foundational y Polish
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones: [research.md](research.md) (R1 a R9) · Modelo de datos: [data-model.md](data-model.md)
- SQL de referencia: [contracts/database-schema.sql](contracts/database-schema.sql)
- Contrato HTTP: [contracts/openapi-clinic-subscriptions.yaml](contracts/openapi-clinic-subscriptions.yaml)
- Permisos: [contracts/permission-matrix.md](contracts/permission-matrix.md) · Errores: [contracts/error-catalog.md](contracts/error-catalog.md)
- Usuarios (`/me`): [contracts/users-api-integration.md](contracts/users-api-integration.md) · Pagos: [contracts/payments-api-integration.md](contracts/payments-api-integration.md)
- Simulaciones: [contracts/e2e-stubs.md](contracts/e2e-stubs.md) · Guía: [quickstart.md](quickstart.md)

## Convenciones de esta feature

- **Prohibido**: tocar `src/models/subscription.py`, `src/services/subscription_service.py`,
  `src/routers/subscriptions.py` o sus pruebas; modificar `mailySoft-pagos`; dar de alta
  `payments:*`/`clinic_subscriptions:*` en un catálogo real; añadir dependencias fuera de la tabla
  del stack de la constitución; hacer commits salvo que se pida.
- **Idioma** (Principio VII): identificadores, campos y códigos de error en inglés; mensajes,
  OpenAPI y documentos en español; comentarios/docstrings en inglés.
- **Mensajes exactos**: de [contracts/error-catalog.md](contracts/error-catalog.md), sin paráfrasis.
- **Dinero**: centavos (`int`) solo al construir la llamada a Pagos; todo lo demás es `Decimal`/`NUMERIC`.
- **Constantes** (definir una sola vez, con nombre):

  | Constante | Valor | Módulo |
  |---|---|---|
  | Estatus | `ClinicSubscriptionStatus.ACTIVE = 1`, `PENDING_RESOLUTION = 2`, `CANCELLED = 3` | `src/models/clinic_subscription_status.py` |
  | Estatus de pago reconocidos | `{"pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"}` | `src/integrations/payments_api.py` |
  | Índices | `CLINIC_SUBSCRIPTIONS_ONE_ACTIVE_INDEX = "clinic_subscriptions_one_active_per_tenant_key"`, `CLINIC_SUBSCRIPTION_CHARGES_ONE_PER_PERIOD_INDEX = "clinic_subscription_charges_one_per_period_key"` | `src/models/clinic_subscription.py` / `clinic_subscription_charge.py` |
  | Permisos | `CLINIC_SUBSCRIPTIONS_READ/WRITE/DELETE/CHARGE = "clinic_subscriptions:read\|write\|delete\|charge"` | `src/security.py` |
  | Prefijo de rutas | `CLINIC_SUBSCRIPTIONS_PATH = "/api/v1/clinic-subscriptions"` | `src/routers/clinic_subscriptions.py` |
  | Referencia a Pagos | `PAYMENTS_RESOURCE_TYPE = "system-api:clinic-subscription"` | `src/services/clinic_subscription_service.py` |
  | Tiempo máximo a Pagos | `PAGOS_API_TIMEOUT_SECONDS`, por defecto `5.0` (>0, ≤30) | `src/config.py` |

- **Interfaces compartidas** (usar exactamente estos nombres):
  - `src/integrations/errors.py`: + `PaymentsApiRejectedToken(code: str)`,
    `PaymentsApiPermissionDenied`, `PaymentsApiIdempotencyConflict`, `PaymentsApiUnavailable`.
  - `src/integrations/payments_api.py`: `PaymentView` (dataclass: `id: UUID, status: str,
    checkout_url: str | None, amount: int, currency: str`), `PaymentsApiClient(http_client,
    base_url, timeout_seconds, service_token: str | None)` con `async create_payment(token: str, *,
    idempotency_key: str, amount: int, currency: str, resource_type: str, resource_id: str,
    description: str) -> PaymentView` y `async get_payment(payment_id: UUID) -> PaymentView` (usa
    `service_token`, no el de quien llama — research R8).
  - `src/integrations/users_api.py`: + `CallerAccess` (dataclass: `tenant_id: str | None,
    permissions: frozenset[str], password_change_required: bool`) y `async
    get_current_access(token: str) -> CallerAccess`.
  - `src/services/authorization_service.py`: + `async require_as_caller(token: str, permission:
    str) -> CallerAccess` (lanza `PasswordChangeRequiredError`/`PermissionDeniedError`/etc., nunca
    comprueba `tenant_id`: eso lo decide el Service que la llama, con el dato del recurso).
  - `src/security.py`: + `require_caller(permission: str)` (dependencia `async` que devuelve
    `CallerAccess`), `CLINIC_SUBSCRIPTIONS_*`.
  - `src/repositories/clinic_subscription_repository.py`: `ClinicSubscriptionRepository(session)` con
    `create`, `get_current_by_id`, `list_current(*, tenant_id=None, status_id=None, page, limit) ->
    tuple[list[ClinicSubscription], int]`, `cancel`, `attach_charge(clinic_subscription_id,
    charge) -> ClinicSubscription | None` (crea/actualiza el cobro del periodo y mueve el estatus en
    una sola transacción), `advance_after_approval`.
  - `src/services/clinic_subscription_service.py`: `ClinicSubscriptionService(repository,
    payments_api, subscription_repository)` (reutiliza `SubscriptionRepository` de la spec 001,
    **solo lectura**, para el precio y el estatus vigentes del plan).

## Phase 1: Setup

- [ ] T001 Añadir `PAGOS_API_BASE_URL`, `PAGOS_API_TIMEOUT_SECONDS` (opcional, por defecto `5.0`) y
  `PAGOS_API_SERVICE_TOKEN` (opcional) a `src/config.py` (`IntegrationSettings`), siguiendo
  exactamente el patrón de `CLINICS_API_BASE_URL`/`CLINICS_API_TIMEOUT_SECONDS`; sin
  `PAGOS_API_BASE_URL` el servicio no arranca (igual que `USERS_API_BASE_URL`).
- [ ] T002 [P] Documentar las variables nuevas en `.env.example` (mismo bloque que `CLINICS_API_*`,
  con nota sobre `PAGOS_API_SERVICE_TOKEN` y la degradación de la sincronización — research R8).
- [ ] T003 [P] Añadir `clinic_subscriptions` a `OPENAPI_TAGS` y a la descripción de `src/main.py`
  (no registrar el router todavía: eso es T037).

## Phase 2: Foundational (bloquea todas las historias)

### Modelo de datos y migración

- [ ] T004 Crear `src/models/clinic_subscription_status.py`: modelo ORM `ClinicSubscriptionStatus`
  (tabla `clinic_subscription_statuses`, igual forma que `SubscriptionStatus`) y la clase de
  constantes `ClinicSubscriptionStatus` de la tabla de arriba.
- [ ] T005 [P] Crear `src/models/clinic_subscription_charge.py`: modelo ORM
  `ClinicSubscriptionCharge` con las columnas de [data-model.md](data-model.md) (`CHECK (amount >
  0)`, `CHECK` de los 6 `payment_status`, índice único `(clinic_subscription_id, period)`).
- [ ] T006 Crear `src/models/clinic_subscription.py`: modelo ORM `ClinicSubscription` con las
  columnas de [data-model.md](data-model.md) (`CHECK (billing_cycle IN ('monthly','annual'))`,
  índice único parcial `(tenant_id) WHERE status_id IN (1,2)`; **sin** columna de cobro vigente,
  para no crear un ciclo de llaves foráneas con `ClinicSubscriptionCharge` (que ya referencia esta
  tabla) — el cobro vigente se lee como la fila más reciente de `clinic_subscription_charges`);
  depende de T004-T005 por los `ForeignKey`.
- [ ] T007 Migración `alembic/versions/0005_clinic_subscriptions.py` (`down_revision = "0004"`):
  reproduce [contracts/database-schema.sql](contracts/database-schema.sql) completo (las 2 tablas,
  los 2 índices únicos, los 2 disparadores con la función `set_updated_at()` ya existente, la
  `ALTER TABLE` de la referencia diferida, y el `INSERT` de los 3 estatus); `downgrade()` revierte
  todo en orden inverso.
- [ ] T008 [P] Reflejar el esquema nuevo en `project-definition/DATA_SCHEMA.md` con la marca
  `-- [spec 006-cobro-real-suscripciones]` y en `project-definition/create_database.sql`.
- [ ] T009 [P] [TEST] `tests/integration/test_clinic_subscriptions_migration.py`: sube/baja desde
  cero y con una fila previa (una suscripción de clínica con un cobro); `alembic check` sin
  diferencias; comprobar que los 3 estatus existen tras la migración.
- [ ] T010 [P] [TEST] Ampliar `tests/unit/test_models_match_migrations.py` con los dos modelos
  nuevos (si ese archivo recorre `Base.metadata` genéricamente, confirmar que ya los cubre en vez de
  duplicar).

### Cliente de Pagos y ampliación del cliente de Usuarios

- [ ] T011 [P] Ampliar `src/integrations/errors.py` con las 4 excepciones de Pagos (research R5).
- [ ] T012 `src/integrations/payments_api.py`: `PaymentView`, `PaymentsApiClient.create_payment`
  (`POST /api/v1/payments`, cabecera `Idempotency-Key`, traduce 201/401/403/409/422/503 según
  [contracts/payments-api-integration.md](contracts/payments-api-integration.md)) y `get_payment`
  (`GET /api/v1/payments/{id}`, usa `service_token`; sin él, lanza `PaymentsApiUnavailable` sin
  llamar — research R8). Nunca reenvía el `Idempotency-Key` en `get_payment`.
- [ ] T013 [P] [TEST] `tests/contract/test_payments_api_client.py`: un caso por fila de las dos
  tablas de traducción del contrato, más timeout, redirección no seguida y que el token nunca
  aparece en un log (`caplog`).
- [ ] T014 Ampliar `src/integrations/users_api.py` con `CallerAccess` y `get_current_access`
  (`GET /api/v1/authorization/me`; traduce 401 igual que `check_permission`; `200` exige `tenant_id`
  como clave presente, `roles` como lista con `permissions` como lista en cada elemento, o
  `UsersApiUnavailable`).
- [ ] T015 [P] [TEST] Ampliar `tests/contract/test_users_api_client.py` con `get_current_access`
  (éxito con/sin `tenant_id`, varios roles con permisos distintos → unión, cada fallo de la tabla de
  [contracts/users-api-integration.md](contracts/users-api-integration.md)).
- [ ] T016 Ampliar `src/services/authorization_service.py` con `require_as_caller` (traduce
  `password_change_required`, calcula la unión de permisos, lanza `PermissionDeniedError` si falta
  el permiso pedido) y la excepción nueva `PasswordChangeRequiredError` en `src/exceptions.py` /
  `src/messages.py` (código `password_change_required`, 403).
- [ ] T017 [P] [TEST] `tests/unit/test_authorization_service.py` ampliado: `require_as_caller` con
  permiso presente/ausente, `password_change_required`, Usuarios caído.
- [ ] T018 Ampliar `src/security.py` con `require_caller(permission)` (dependencia que llama a
  `require_as_caller` y devuelve el `CallerAccess`) y las 4 constantes `CLINIC_SUBSCRIPTIONS_*`.
- [ ] T019 [P] [TEST] Ampliar `tests/unit/test_security.py` con `require_caller`.
- [ ] T020 Ampliar `src/dependencies.py`: `get_payments_api_client`, `get_clinic_subscription_repository`,
  `get_clinic_subscription_service` (inyecta también `get_subscription_repository`, de solo
  lectura, para el precio/estatus vigentes del plan — no se reescribe `subscription_service.py`).

### Repositorio

- [ ] T021 `src/repositories/clinic_subscription_repository.py`: `create`, `get_current_by_id` (con
  `joinedload` del estatus y del cobro vigente), `list_current` (paginado, filtros `tenant_id`/`status_id`),
  `cancel` (UPDATE atómico condicionado al estatus actual, igual patrón que
  `SubscriptionRepository.change_status`), `attach_charge` (INSERT/UPDATE de
  `clinic_subscription_charges` por `(clinic_subscription_id, period)` + UPDATE de
  `clinic_subscriptions.status_id` en la misma sesión; el cobro vigente no tiene columna propia:
  se lee con un `MAX(period)`/`ORDER BY period DESC LIMIT 1`), `advance_after_approval`
  (avanza `next_billing_at` un ciclo y vuelve el estatus a Activa).
- [ ] T022 [P] [TEST] `tests/integration/test_clinic_subscription_repository.py` contra PostgreSQL
  real: el índice único por `tenant_id` (dos Activas → `UniqueViolationError`), el índice único por
  periodo (dos cobros del mismo periodo → actualiza, no duplica), `updated_at` cambia con cada UPDATE.

**Checkpoint**: `uv run pytest tests/unit tests/integration tests/contract/test_payments_api_client.py
tests/contract/test_users_api_client.py -k "clinic_subscription or payments_api or users_api or
authorization_service or security"` en verde antes de abrir ninguna historia.

## Phase 3: User Story 1 — Asignar un plan a una clínica (P1)

**Goal**: FR-001 a FR-007. **Independent Test**: crear con cada ciclo y con/sin `trial_days`;
plan no Activo (409); clínica con una vigente (409); datos inválidos (422).

- [ ] T023 [P] [US1] `src/dtos/clinic_subscription.py`: `ClinicSubscriptionCreate` (`tenant_id: UUID`,
  `subscription_id: int = Field(ge=1)`, `billing_cycle: Literal["monthly","annual"]`,
  `started_at: datetime | None`, `extra="forbid"`), `ClinicSubscriptionStatusRead`,
  `ClinicSubscriptionRead` (incluye `current_charge: ClinicSubscriptionChargeRead | None`).
- [ ] T024 [US1] Excepciones nuevas en `src/exceptions.py` + mensajes en `src/messages.py`:
  `ClinicSubscriptionPlanNotActiveError` (409), `ClinicSubscriptionAlreadyActiveError` (409),
  `ClinicSubscriptionNotFoundError` (404) — textos exactos de
  [contracts/error-catalog.md](contracts/error-catalog.md).
- [ ] T025 [US1] `ClinicSubscriptionService.create`: lee el plan con `SubscriptionRepository.
  get_current_by_id` (404/409 si no existe o no está Activo — FR-003), calcula `next_billing_at`
  (FR-005: `started_at + trial_days` o `started_at`), llama al Repository y traduce
  `UniqueViolationError` del índice `clinic_subscriptions_one_active_per_tenant_key` a
  `ClinicSubscriptionAlreadyActiveError`.
- [ ] T026 [US1] `src/routers/clinic_subscriptions.py` (nuevo): `POST /api/v1/clinic-subscriptions`
  con `secured`/`protected`-equivalente para `clinic_subscriptions:write` (`require_permission`, no
  `require_caller`: FR-006/FR-031).
- [ ] T027 [P] [US1] [TEST] `tests/unit/test_clinic_subscription_service.py::test_create_*` (5
  escenarios de la historia 1) con `ClinicSubscriptionRepository`/`SubscriptionRepository` sustituidos
  por dobles.
- [ ] T028 [P] [US1] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_create_*` (misma
  cobertura, contra la app real + PostgreSQL real + stub de Usuarios).
- [ ] T029 [US1] Registrar el router en `src/main.py` (`app.include_router(clinic_subscriptions.router)`).

**Checkpoint**: crear funciona de punta a punta; `uv run pytest -k clinic_subscription` en verde.

## Phase 4: User Story 2 — Cobrar la suscripción de una clínica (P1)

**Goal**: FR-008 a FR-015, FR-030, FR-031. **Independent Test**: cuerpo exacto a Pagos; idempotencia;
no Activa (409); Pagos caído (503); otra organización (404).

- [ ] T030 [P] [US2] `src/dtos/clinic_subscription.py` (ampliar): `ClinicSubscriptionChargeRead`
  (todas las columnas de [data-model.md](data-model.md), `currency` siempre `"MXN"`).
- [ ] T031 [US2] Excepciones + mensajes: `ClinicSubscriptionChargePendingError` (409),
  `ClinicSubscriptionChargeRequiresActivePlanError` (409), `PaymentNotAuthorizedError` (403),
  `ClinicSubscriptionChargeConflictError` (409), `PaymentsUnavailableError` (503).
- [ ] T032 [US2] `ClinicSubscriptionService.charge(clinic_subscription_id, caller: CallerAccess)`:
  busca la suscripción (404 si no existe/Cancelada); **compara `caller.tenant_id` con el
  `tenant_id` de la suscripción antes que cualquier otra regla** (FR-030: distinto o `None` → el
  mismo `ClinicSubscriptionNotFoundError` 404, nunca 403); comprueba elegibilidad (research R7);
  relee el plan (409 `…RequiresActivePlanError` si no está Activo); calcula `amount` en centavos
  (research R2, `Decimal.scaleb(2)` o equivalente, nunca `float`) y la `Idempotency-Key`
  determinista (research R3); llama a `PaymentsApiClient.create_payment` reenviando `caller`'s
  token (no el `service_token`); traduce sus excepciones (T011) a las de T031; persiste con
  `Repository.attach_charge`.
- [ ] T033 [US2] `POST /api/v1/clinic-subscriptions/{id}/charges` en el router, protegida con
  `require_caller(CLINIC_SUBSCRIPTIONS_CHARGE)` (no `require_permission`): el Router recibe el
  `CallerAccess` como dependencia y lo pasa al Service.
- [ ] T034 [P] [US2] [TEST] `tests/unit/test_clinic_subscription_service.py::test_charge_*` (los 7
  escenarios de la historia 2, con `PaymentsApiClient` sustituido por un doble que registra la
  llamada exacta — verificar centavos, `resource_type`, `resource_id`, `Idempotency-Key`).
- [ ] T035 [P] [US2] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_charge_*` (misma
  cobertura, contra el stub real de Pagos — `tests/stubs/payments_api/app.py`, T036).
- [ ] T036 [US2] Crear `tests/stubs/payments_api/app.py` (autocontenido, sin importar `src/`; ver
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md)): `POST /api/v1/payments`, `GET
  /api/v1/payments/{id}`, `/__test__/tokens`, `/__test__/payments/{id}/status`, `/__test__/faults`,
  `/__test__/calls`, `/__test__/reset`; añadir la fixture `payments_stub`/`payments_api_client` a
  `tests/conftest.py` (mismo patrón que `clinics_stub`).

**Checkpoint**: cobrar funciona de punta a punta contra el stub de Pagos.

## Phase 5: User Story 3 — Conocer si el cobro se aprobó o se rechazó (P1)

**Goal**: FR-016 a FR-018. **Independent Test**: un cobro `pending` se sincroniza al leerlo; uno
resuelto no vuelve a llamar a Pagos; Pagos caído durante la sincronización no rompe la lectura.

- [ ] T037 [US3] `ClinicSubscriptionService._sync_if_pending(charge)`: si `charge.payment_status ==
  "pending"`, llama a `PaymentsApiClient.get_payment`; si responde con un estatus distinto,
  persiste (`Repository.attach_charge` o un método dedicado) y, si pasa a `approved`, llama a
  `Repository.advance_after_approval`; si `PaymentsApiUnavailable`, registra una advertencia (en
  inglés) y sigue con el dato local (FR-017, nunca propaga la excepción).
- [ ] T038 [US3] Usar `_sync_if_pending` en `ClinicSubscriptionService.get` y en el método que arma
  `current_charge`/el historial antes de devolver cualquier lectura (US1/US4) cuyo cobro esté
  `pending`.
- [ ] T039 [P] [US3] [TEST] `tests/unit/test_clinic_subscription_service.py::test_sync_*` (los 4
  escenarios de la historia 3).
- [ ] T040 [P] [US3] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_sync_*` (mover el
  estatus a mano en el stub de Pagos con `/__test__/payments/{id}/status`, luego `GET` y comprobar
  el reflejo).

**Checkpoint**: la historia 3 pasa contra el stub con el estatus movido a mano.

## Phase 6: User Story 4 — Consultar y listar (P2)

**Goal**: FR-007. **Independent Test**: listado paginado con el cobro vigente; 404; 403 sin permiso.

- [ ] T041 [US4] `ClinicSubscriptionService.list` / `.get` (ya con `_sync_if_pending`) y
  `.list_charges` / `.get_charge` (historial, paginado, 404 si la suscripción o el cobro no existen).
- [ ] T042 [US4] `GET /api/v1/clinic-subscriptions`, `GET /api/v1/clinic-subscriptions/{id}`, `GET
  .../charges`, `GET .../charges/{charge_id}` en el router, protegidas con
  `clinic_subscriptions:read` (`require_permission`, no `require_caller`).
- [ ] T043 [P] [US4] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_list_*` /
  `test_get_*` (paginación, filtros, 404, 403).

## Phase 7: User Story 5 — Cancelar (P3)

**Goal**: historia 5. **Independent Test**: Activa sin pendiente → Cancelada; con `pending` → 409;
ya Cancelada → 409.

- [ ] T044 [US5] Excepción `ClinicSubscriptionAlreadyCancelledError` (409); `ClinicSubscriptionService.
  cancel` (bloquea si el cobro vigente es `pending` → `ClinicSubscriptionChargePendingError`).
- [ ] T045 [US5] `DELETE /api/v1/clinic-subscriptions/{id}` en el router, `clinic_subscriptions:delete`.
- [ ] T046 [P] [US5] [TEST] Unit + contract de los 3 escenarios de la historia 5.

## Phase 8: Polish & cross-cutting

- [ ] T047 [P] [TEST] `tests/contract/test_clinic_subscriptions_access_control.py`: las 7 operaciones
  sin token/token inválido/sin permiso/Usuarios caído; las 6 de rol de Sistema usan `check`
  (verificar en `/__test__/calls` del stub de Usuarios que nunca llaman a `/me`); `charge_...` usa
  `me` una sola vez por petición.
- [ ] T048 [P] [TEST] Ampliar `tests/contract/test_permission_coverage.py` con las 7 rutas nuevas y
  la tabla de [contracts/permission-matrix.md](contracts/permission-matrix.md).
- [ ] T049 [P] [TEST] `tests/contract/test_clinic_subscriptions_openapi.py`: el esquema generado
  coincide con [contracts/openapi-clinic-subscriptions.yaml](contracts/openapi-clinic-subscriptions.yaml)
  (mismo patrón sin PyYAML que `test_openapi_contract.py`).
- [ ] T050 [P] Ampliar `tests/unit/test_layering.py` con los módulos nuevos (ninguna capa importa lo
  que no debe — Principio I).
- [ ] T051 [P] Ampliar `tests/unit/test_error_messages.py` / `test_config.py` con los códigos y las
  variables nuevas (falta `PAGOS_API_BASE_URL` → no arranca, sin mostrar valores).
- [ ] T052 **No** bumpear `VERSION` (cambio puramente aditivo, Principio IV: no es incompatible;
  `VERSION` no se incrementó en ninguna spec anterior tampoco). Sí actualizar el conteo literal de
  `tests/contract/test_openapi_contract.py::test_the_error_codes_are_the_seventeen_of_the_catalog`
  al nuevo total de `ErrorCode` (17 + los códigos nuevos de esta spec).
- [ ] T053 Actualizar `README.md` (tabla de operaciones, igual que las secciones de las specs 001/003/005).
- [ ] T054 ~~`ruff`/`mypy`~~: no son parte del stack de este repositorio (no están en `pyproject.toml`
  ni en la constitución); la puerta de calidad real es la suite de pytest (Principio V) más
  `tests/unit/test_layering.py`, ya cubiertos por T055.
- [ ] T055 `uv run pytest` completo en verde (incluidas las specs 001 a 005, sin regresiones) y `uv
  run alembic upgrade head && uv run alembic check`.

## Dependencies & Execution Order

- Setup (T001-T003) → Foundational (T004-T022) → US1 (T023-T029) → US2 (T030-T036) → US3
  (T037-T040) → US4 (T041-T043) → US5 (T044-T046) → Polish (T047-T055).
- US2 depende de US1 (necesita una suscripción de clínica que cobrar) y de T011-T020 (cliente de
  Pagos y `require_caller`). US3 depende de US2 (necesita un cobro `pending`). US4 depende de US1
  (y de US2/US3 para mostrar el cobro vigente, aunque su propio código no los modifica). US5 solo
  depende de US1.
- Dentro de cada fase, las tareas `[P]` tocan archivos distintos y pueden ejecutarse en paralelo;
  las que no lo son modifican el mismo archivo que una tarea previa de la misma fase.

## Implementation Strategy

**MVP** = Setup + Foundational + US1 + US2: ya permite asignar un plan y cobrarlo de verdad contra
Mercado Pago (vía el stub en pruebas, vía Pagos real en producción). US3 lo completa (saber si se
aprobó); US4 y US5 son operables sin ellas (se puede inspeccionar con SQL directo mientras tanto, en
desarrollo). Entrega incremental: **US1 → US2 → US3 → US4 → US5 → Polish**, con `uv run pytest` en
verde al final de cada fase.

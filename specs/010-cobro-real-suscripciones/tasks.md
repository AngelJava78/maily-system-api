---

description: "Task list for feature 010-cobro-real-suscripciones (Cobro Real de Suscripciones de Clínicas) — rediseño 2026-11-11"
---

# Tasks: Cobro Real de Suscripciones de Clínicas (rediseño)

**Input**: Design documents from `specs/010-cobro-real-suscripciones/`

**Contexto**: Reemplaza la implementación anterior (comiteada como spec `006-cobro-real-suscripciones`,
commit `a1f1acc`, luego el repo integró `origin/main` con las specs 006-009 propias — merge
`1158b76`). El arquitecto determinó que la asignación clínica↔plan↔ciclo no vive en este servicio
(Principio IX): esta lista **retira** el código de la entrega anterior que asumía lo contrario y
**construye** sobre el nuevo diseño (consultar a Clínicas en vez de guardar `clinic_subscriptions`).

**Tests**: Incluidas (Principio V, FR-028), en los dos niveles de la constitución v1.1.0 (rápido por
defecto; lo que toca PostgreSQL real o la app completa, marcado `slow`).

**Organization**: Setup → Foundational → US1 (cobrar) → US2 (conocer el resultado, mayormente ya
resuelto al construir US1 con el diseño correcto) → US3 (historial) → Polish. **MVP** = Setup +
Foundational + US1.

## Format: `[ID] [P?] [Story] Description`

## Referencias rápidas

[research.md](../010-cobro-real-suscripciones/research.md) (R1-R9) · [data-model.md](../010-cobro-real-suscripciones/data-model.md) ·
[contracts/](../010-cobro-real-suscripciones/contracts/) (7 documentos) · [quickstart.md](../010-cobro-real-suscripciones/quickstart.md)

## Phase 0: Retirar la implementación anterior (asume lo que ya NO es correcto)

- [ ] T001 Borrar `src/models/clinic_subscription.py` y `src/models/clinic_subscription_status.py`
  (esa entidad vive en Clínicas); quitarlos de `src/models/__init__.py`.
- [ ] T002 Borrar `src/repositories/clinic_subscription_repository.py` (sus operaciones de
  crear/cancelar/listar/consultar «la suscripción» ya no existen).
- [ ] T003 Vaciar y reescribir por completo `src/services/clinic_subscription_service.py` y
  `src/routers/clinic_subscriptions.py` (se reconstruyen en las fases siguientes con el alcance
  nuevo: solo cobrar + historial).
- [ ] T004 Borrar las pruebas que asumían la entidad local: `tests/unit/test_clinic_subscription_dtos.py`
  y las partes de `tests/contract/test_permission_coverage.py` que registraban
  `create_clinic_subscription`/`cancel_clinic_subscription`/`list_clinic_subscriptions`/
  `get_clinic_subscription` (revisar `EXPECTED_PERMISSIONS`, `REQUESTS`, `seeded`, `snapshot`: ya no
  hay `clinic_subscriptions` como tabla propia, solo `clinic_subscription_charges`).
- [ ] T005 Reescribir `alembic/versions/0008_clinic_subscription_charges.py` desde cero (una sola
  tabla, sin la referencia diferida ni el catálogo de estatus) según
  [contracts/database-schema.sql](../010-cobro-real-suscripciones/contracts/database-schema.sql).
- [ ] T006 Reescribir `tests/integration/test_clinic_subscriptions_migration.py` para la tabla nueva
  (un solo `CREATE TABLE`, sin catálogo de estatus).
- [ ] T007 Quitar de `src/exceptions.py`/`src/messages.py` los códigos que ya no aplican:
  `clinic_subscription_already_active`, `clinic_subscription_charge_pending`,
  `clinic_subscription_already_cancelled`, `clinic_subscription_charge_requires_active_plan`
  (sustituidos por `clinic_subscription_plan_not_active` y
  `clinic_subscription_charge_already_approved` — ver FR-005, FR-011 y
  [contracts/error-catalog.md](../010-cobro-real-suscripciones/contracts/error-catalog.md)).

## Phase 1: Setup

- [ ] T008 Confirmar que `PAGOS_API_BASE_URL`/`PAGOS_API_TIMEOUT_SECONDS`/`PAGOS_API_SERVICE_TOKEN`
  siguen en `src/config.py` y `.env.example` (de la entrega anterior; sin cambios de fondo).
- [ ] T009 [P] Actualizar la descripción de `clinic-subscriptions` en `src/main.py` (ya no es «la
  suscripción de clínica»: ahora es «el cobro, que consulta a Clínicas»).

## Phase 2: Foundational (bloquea US1-US3)

- [ ] T010 `src/models/clinic_subscription_charge.py`: único modelo ORM de esta spec
  (`clinic_subscription_id: UUID`, `tenant_id: UUID`, sin `ForeignKey` local — ver
  [data-model.md](../010-cobro-real-suscripciones/data-model.md)).
- [ ] T011 [P] [TEST] Ajustar `tests/unit/test_models_match_migrations.py` si recorre modelos por
  nombre (confirmar que el genérico ya cubre el modelo nuevo).
- [ ] T012 `src/integrations/errors.py`: añadir `ClinicsApiNotFound` (junto a la `ClinicsApiUnavailable`
  ya existente); mantener las 4 excepciones de Pagos de la entrega anterior
  (`PaymentsApiRejectedToken`, `PaymentsApiPermissionDenied`, `PaymentsApiIdempotencyConflict`,
  `PaymentsApiUnavailable`) sin cambios.
- [ ] T013 Ampliar `src/integrations/clinics_api.py` con `ClinicSubscriptionInfo` (dataclass:
  `tenant_id: str`, `subscription_id: int`, `billing_cycle: str`) y
  `async get_clinic_subscription(token, clinic_subscription_id) -> ClinicSubscriptionInfo`
  (`GET /api/v1/clinics/clinic-subscriptions/{id}`; traduce 200/404/401/403/503 según
  [contracts/clinics-api-integration.md](../010-cobro-real-suscripciones/contracts/clinics-api-integration.md)).
  `get_counts` (spec 001) no cambia.
- [ ] T014 [P] [TEST] Ampliar `tests/contract/test_clinics_api_client.py` con
  `get_clinic_subscription` (éxito, 404, cada falla de la tabla del contrato).
- [ ] T015 Confirmar `src/integrations/payments_api.py` (`PaymentsApiClient`, `PaymentView`) de la
  entrega anterior: sin cambios de fondo (research R5 no cambió).
- [ ] T016 [P] [TEST] Confirmar `tests/contract/test_payments_api_client.py` de la entrega anterior
  sigue vigente sin cambios.
- [ ] T017 Confirmar en `src/integrations/users_api.py` (`CallerAccess`, `get_current_access`) y
  `src/services/authorization_service.py` (`require_as_caller`) y `src/security.py`
  (`require_caller`, `CLINIC_SUBSCRIPTIONS_READ`, `CLINIC_SUBSCRIPTIONS_CHARGE` — **ya no**
  `WRITE`/`DELETE`, esos permisos no existen tras el rediseño) de la entrega anterior: sin cambios
  de fondo (research R1 no cambió). Quitar `CLINIC_SUBSCRIPTIONS_WRITE`/`_DELETE` si quedaron.
- [ ] T018 [P] [TEST] Confirmar `tests/unit/test_authorization_service.py` y `tests/unit/
  test_security.py` (parte de `require_as_caller`/`require_caller`) siguen vigentes.
- [ ] T019 `src/repositories/clinic_subscription_charge_repository.py`:
  `ClinicSubscriptionChargeRepository(session)` con `save_charge(clinic_subscription_id, tenant_id,
  period, amount, currency, payment_id, payment_status, checkout_url, idempotency_key)` (INSERT/
  UPDATE por `(clinic_subscription_id, period)`, igual patrón que la entrega anterior pero sin
  tocar ninguna fila de «suscripción»), `get_by_id`, `get_by_period(clinic_subscription_id, period)`
  (para FR-011), `list(clinic_subscription_id, *, page, limit)`.
- [ ] T020 [P] [TEST] `tests/integration/test_clinic_subscription_charge_repository.py`: el índice
  único por `(clinic_subscription_id, period)` (INSERT doble → `UniqueViolationError`), `updated_at`
  cambia con cada UPDATE.
- [ ] T021 Ampliar `src/dependencies.py`: `get_clinic_subscription_charge_repository`,
  `get_clinic_subscription_service` (inyecta `ClinicsApiClient`, `PaymentsApiClient`,
  `SubscriptionRepository` de solo lectura y el Repository nuevo).

## Phase 3: User Story 1 — Cobrar la suscripción de una clínica (P1)

**Goal**: FR-001 a FR-012. **Independent Test**: con Clínicas y Pagos simulados, disparar el cobro y
comprobar el cuerpo exacto a Pagos, la idempotencia, y los 404/409/503 de cada dependencia.

- [ ] T022 [P] [US1] `src/dtos/clinic_subscription.py`: `ClinicSubscriptionChargeCreate` (`period:
  date`, `extra="forbid"`), `ClinicSubscriptionChargeRead` (todas las columnas, `currency` siempre
  `"MXN"`).
- [ ] T023 [US1] Excepciones + mensajes (`src/exceptions.py`/`src/messages.py`):
  `ClinicSubscriptionNotFoundError` (404), `ClinicSubscriptionPlanNotActiveError` (409),
  `ClinicSubscriptionChargeAlreadyApprovedError` (409), `PaymentNotAuthorizedError` (403, de la
  entrega anterior), `ClinicSubscriptionChargeConflictError` (409, idem), `PaymentsUnavailableError`
  (503, idem), `PasswordChangeRequiredError` (403, idem) — textos exactos de
  [contracts/error-catalog.md](../010-cobro-real-suscripciones/contracts/error-catalog.md).
- [ ] T024 [US1] `ClinicSubscriptionService.charge(clinic_subscription_id, period, caller:
  CallerAccess, token)`: consulta a Clínicas (`ClinicsApiNotFound` → 404; `ClinicsApiUnavailable` →
  503 `clinics_check_unavailable`); compara `caller.tenant_id` con el `tenant_id` reportado (FR-026:
  distinto o `None` → el mismo 404, nunca 403); lee el plan local (`SubscriptionRepository.
  get_current_by_id(subscription_id)`, 409 si no Activo); calcula `amount` en centavos (research R2)
  y la `Idempotency-Key` determinista por `(clinic_subscription_id, period)` (research R3); si ya
  hay un cobro `approved` de ese par → 409 `ClinicSubscriptionChargeAlreadyApprovedError` (FR-011,
  sin llamar a Pagos); si no, llama a `PaymentsApiClient.create_payment` reenviando el token del
  caller; traduce sus excepciones; persiste con `Repository.save_charge`.
- [ ] T025 [US1] `POST /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges` en
  `src/routers/clinic_subscriptions.py`, protegida con `require_caller(CLINIC_SUBSCRIPTIONS_CHARGE)`
  (el Router recibe el `CallerAccess` y lo pasa al Service junto con el token y el `period` del
  cuerpo).
- [ ] T026 [P] [US1] [TEST] `tests/unit/test_clinic_subscription_service.py::test_charge_*` (los 9
  escenarios de la historia 1) con `ClinicsApiClient`/`PaymentsApiClient`/`SubscriptionRepository`/
  `ClinicSubscriptionChargeRepository` sustituidos por dobles — verificar centavos, `resource_type`,
  `resource_id` (el UUID de Clínicas), `Idempotency-Key`.
- [ ] T027 [P] [US1] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_charge_*` (misma
  cobertura, contra la app real + los 3 stubs reales).
- [ ] T028 [US1] Reescribir `tests/stubs/payments_api/app.py` si no sobrevivió a la Fase 0 intacta
  (debería, sin cambios de fondo); ampliar `tests/stubs/clinics_api/app.py` con
  `GET /api/v1/clinics/clinic-subscriptions/{id}` y su superficie de pruebas (ver
  [contracts/e2e-stubs.md](../010-cobro-real-suscripciones/contracts/e2e-stubs.md)); añadir las
  fixtures que falten a `tests/conftest.py` (`payments_stub`/`payments_api_client` de la entrega
  anterior deberían sobrevivir; confirmar que `clinics_stub`/`clinics_api_client` ya cubren la
  operación nueva sin fixtures adicionales, porque es el mismo stub ampliado).
- [ ] T029 [US1] Registrar/confirmar el router en `src/main.py`.

**Checkpoint**: cobrar funciona de punta a punta contra los stubs de Clínicas y de Pagos.

## Phase 4: User Story 2 — Conocer si el cobro se aprobó o se rechazó (P1)

**Goal**: FR-013 a FR-015. En gran parte ya construido correctamente en US1 si T024 usa el patrón de
sincronización desde el principio; esta fase confirma la lectura.

- [ ] T030 [US2] `ClinicSubscriptionService._sync_if_pending(charge)` (igual research R8 que la
  entrega anterior, **sin** el paso de «avanzar `next_billing_at`»: esa fecha no es de este
  servicio); usarlo en `get_charge`/`list_charges`.
- [ ] T031 [US2] `GET /api/v1/clinic-subscriptions/{id}/charges/{charge_id}` en el router,
  `clinic_subscriptions:read` (`require_permission`, no `require_caller`: FR-027).
- [ ] T032 [P] [US2] [TEST] Unit + contract de los 3 escenarios de la historia 2 (mover el estatus a
  mano en el stub de Pagos, confirmar que la sincronización ocurre al leer).

## Phase 5: User Story 3 — Consultar el historial de cobros (P2)

- [ ] T033 [US3] `ClinicSubscriptionService.list_charges(clinic_subscription_id, *, page, limit)`.
- [ ] T034 [US3] `GET /api/v1/clinic-subscriptions/{id}/charges` en el router,
  `clinic_subscriptions:read`.
- [ ] T035 [P] [US3] [TEST] `tests/contract/test_clinic_subscriptions_api.py::test_list_*` (paginado,
  404, 403).

## Phase 6: Polish & cross-cutting

- [ ] T036 [P] [TEST] `tests/contract/test_clinic_subscriptions_access_control.py`: las 3
  operaciones sin token/inválido/sin permiso/dependencia caída; las 2 de rol de Sistema usan
  `check`; `charge_...` usa `me` una sola vez; 404 por `tenant_id` no coincidente.
- [ ] T037 [P] [TEST] Reescribir la parte de `tests/contract/test_permission_coverage.py` de esta
  spec con las 3 rutas nuevas (ya no 7) y la tabla de
  [contracts/permission-matrix.md](../010-cobro-real-suscripciones/contracts/permission-matrix.md);
  quitar el `ME_BASED_OPERATIONS`/`seeded`/`snapshot` que asumían la tabla `clinic_subscriptions`
  local (Fase 0) y añadir el equivalente para `clinic_subscription_charges` (sin tabla «padre» que
  insertar: los escenarios de «cambia nada» solo necesitan la tabla de cobros).
- [ ] T038 [P] [TEST] `tests/contract/test_clinic_subscriptions_openapi.py`: el esquema generado
  coincide con [contracts/openapi-clinic-subscriptions.yaml](../010-cobro-real-suscripciones/contracts/openapi-clinic-subscriptions.yaml).
- [ ] T039 [P] Ampliar `tests/unit/test_layering.py` con los módulos que falten.
- [ ] T040 Recalcular y corregir el conteo literal de `ErrorCode` en los 4 sitios que lo fijan
  (`tests/contract/test_openapi_contract.py`, `tests/contract/test_dashboard_openapi.py`,
  `tests/unit/test_dashboard_messages.py`, `tests/unit/test_error_messages.py`): base 17 (tras el
  merge de `origin/main`) + 8 códigos nuevos de esta spec (ver
  [contracts/error-catalog.md](../010-cobro-real-suscripciones/contracts/error-catalog.md)) = **25**
  (no 28: la entrega anterior tenía 11 códigos nuevos, esta tiene 8 — 3 menos tras el rediseño).
- [ ] T041 Actualizar `README.md` y `project-definition/DATA_SCHEMA.md` (ya ajustado en el merge;
  confirmar que coincide con el esquema final de una sola tabla) y `project-definition/
  create_database.sql`.
- [ ] T042 `uv run pytest` (rápida) y `uv run pytest -m slow` en verde, cero regresiones en las
  specs 001 a 009; `uv run alembic upgrade head && uv run alembic check`.

## Dependencies & Execution Order

Phase 0 (retirar) → Setup → Foundational → US1 → US2 → US3 → Polish. US2 depende de US1 (necesita un
cobro `pending`); US3 solo depende de Foundational (lee el Repository directamente, no depende de
que exista ya un cobro para tener sentido, aunque sin ninguno la lista está vacía).

## Implementation Strategy

**MVP** = Phase 0 + Setup + Foundational + US1: ya permite disparar un cobro real contra Mercado
Pago (vía los stubs en pruebas) para una suscripción que Clínicas decidió. US2 y US3 lo completan.

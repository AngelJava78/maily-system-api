---

description: "Task list for 012-payment-history-charges"
---

# Tasks: Historial paginado de cobros de la suscripción

**Input**: Design documents from `/specs/012-payment-history-charges/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/charges-operation.md,
contracts/permission-matrix.md, quickstart.md

**Tests**: obligatorias por la constitución (Principio V). Durante `/speckit-implement` solo corre el
nivel rápido (`uv run pytest`); la suite completa (`uv run pytest -m ""`) y Newman son la puerta de la
fase «Verificación completa».

**Organization**: tareas agrupadas por historia de usuario.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ir en paralelo (otro archivo, sin depender de tareas pendientes)
- **[Story]**: historia de usuario de [spec.md](spec.md) (US1 a US3)

## Convenciones de esta feature (valen para todas las tareas)

- Comandos de Python (`uv run …`) desde PowerShell en `C:\Maily\code\maily-system-api`.
- Comentarios, docstrings y nombres en inglés; mensajes y documentos en español (Principio VII).
- Sin migración, sin permiso nuevo, sin variable de entorno nueva (FR-013).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: ninguna (sin migración, sin dependencia nueva): se confirmó leyendo el modelo y la migración
0008 que la tabla ya tiene todo lo necesario (research R4), antes de tocar código.

- [X] T001 Confirmar que `src/models/subscription_charge.py` y `alembic/versions/0008_*.py` ya tienen
  `status`, `closed_reason`, `amount`, `currency`, `billing_period`, `period_starts_at`, `period_ends_at`
  y `created_at` (lectura, sin cambio de código).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: los DTOs que publican el contrato (todas las historias los necesitan).

**⚠️ CRITICAL**: ninguna historia empieza antes de terminar esta fase.

- [X] T002 `SubscriptionChargeRead`/`SubscriptionChargesPageRead` en `src/dtos/subscription_period.py`
  (data-model.md): los nueve campos del cobro con la presencia condicional de `closed_reason`
  (FR-003) y de `period_starts_at`/`period_ends_at` (FR-004); las cinco claves de la página, con
  `total_pages = ceil(total / page_size)` o `0` si `total` es `0`.
- [X] T003 [P] Pruebas del DTO en `tests/unit/test_subscription_period_dtos.py`: los nueve campos
  siempre están, presencia condicional de `closed_reason` y de las fechas del periodo, los cuatro
  valores de `status` y los cuatro de `closed_reason`, el importe con dos decimales, las cinco claves de
  la página, los campos numéricos no pueden ser negativos o cero donde no aplica, y que ningún campo de
  `payment_id`/`attempt`/`token`/`organization_id` existe en ningún DTO de este router (FR-005).

**Checkpoint**: la suite rápida sigue en verde (`uv run pytest`).

---

## Phase 3: User Story 1 - El Dueño ve el historial de su organización (Priority: P1) 🎯 MVP

**Goal**: `GET /{organization_id}/charges` publica los cobros de la organización, con los campos que
corresponden a cada estado, sin los internos de la reconciliación.

**Independent Test**: con una organización con cobros de los tres estados, pedir la operación como su
Dueño y comprobar los campos de cada uno.

### Tests for User Story 1 ⚠️

- [X] T004 [P] [US1] `FakePeriodRepository.list_charges(...)` en `tests/billing_support.py` (mismo orden
  que el Repository real: más reciente primero).
- [X] T005 [P] [US1] Service en `tests/unit/test_subscription_period_service.py`: una organización sin
  cobros responde una lista vacía; con cobros, aparecen del más reciente al más antiguo; un cobro
  aprobado en Pagos que nadie reconcilió sigue `pending` en el historial (R2); el historial solo lista
  los de su propia organización.
- [X] T006 [P] [US1] Repository en `tests/integration/test_subscription_period_repository.py` (nivel
  lento): sin cobros, lista vacía; orden (más reciente primero, desempate por `id`); aislamiento por
  organización; los tres estados con sus campos (`pending` sin fechas, `applied` con las dos,
  `closed` con su razón).
- [X] T007 [P] [US1] Contrato en `tests/contract/test_subscription_periods_api.py` (nivel lento, usa
  `billing_api`): sin cobros, 200 vacío; un cobro pendiente con ambas fechas `null`; uno aplicado con el
  periodo que cubrió; uno cerrado con su `closed_reason` y sin fechas; esta lectura no llama a Pagos
  (R2).

### Implementation for User Story 1

- [X] T008 [US1] `list_charges(...)` en `src/repositories/subscription_period_repository.py`: cuenta y
  selecciona con `offset`/`limit`, orden `created_at` descendente y `id` descendente como desempate
  (mismo patrón que `clinic_subscription_charge_repository.list`, R1).
- [X] T009 [US1] `list_charges(...)` en `src/services/subscription_period_service.py`: solo
  `_read_organization` (el mismo control de acceso de `get_status`), sin `_prepare` completo (R2, R3).
- [X] T010 [US1] `_to_charge_read`/`_to_charges_page_read` y el endpoint
  `GET /{organization_id}/charges` en `src/routers/subscription_periods.py`, con `operation_id`
  `list_subscription_charges`, documentación OpenAPI en español y `Cache-Control: no-store` (FR-012). Sin
  importar `src.models` en el Router (Principio I): los mapeadores reciben el cobro sin anotar su tipo
  ORM, igual que `clinic_subscriptions.py`.

**Checkpoint**: `uv run pytest` en verde; el historial publica los tres estados correctamente.

---

## Phase 4: User Story 2 - El historial se pide por páginas (Priority: P2)

**Goal**: `page`/`page_size` en la consulta, `total`/`total_pages` en el cuerpo; fuera de rango, 422.

**Independent Test**: con más cobros que una página, pedir dos páginas y comprobar que no se repiten.

### Tests for User Story 2 ⚠️

- [X] T011 [P] [US2] Service en `tests/unit/test_subscription_period_service.py`: dos páginas de tamaño 1
  no se repiten y sus totales coinciden (parte de T005, mismo archivo).
- [X] T012 [P] [US2] Repository en `tests/integration/test_subscription_period_repository.py`: paginación
  con `offset`/`limit` reales, y una página más allá de la última responde vacía con el `total` correcto
  (FR-011; parte de T006).
- [X] T013 [P] [US2] Contrato en `tests/contract/test_subscription_periods_api.py`: dos páginas de tamaño
  1 traen cobros distintos con `total_pages` correcto; `page_size` fuera de 1–100 responde 422
  `validation_error` (parte de T007).
- [X] T014 [P] [US2] OpenAPI en `tests/contract/test_subscription_periods_openapi.py`: los parámetros
  `page`/`page_size` están documentados con sus límites (`minimum`/`maximum`) y el esquema de la página
  publica sus cinco campos.

### Implementation for User Story 2

- [X] T015 [US2] `page`/`page_size` como parámetros de consulta en
  `src/routers/subscription_periods.py` (`PageQuery`/`PageSizeQuery`, `ge=1`/`ge=1, le=100`, por omisión
  1 y 10, R6); FastAPI y el manejador de errores ya existente (`src/error_handlers.py`) convierten
  cualquier valor fuera de rango en 422 `validation_error` sin código nuevo.

**Checkpoint**: las 16 filas … no aplica (no hay tabla de referencia en esta feature); en su lugar: las
historias 1 y 2 pasan juntas y por separado.

---

## Phase 5: User Story 3 - Solo el Dueño ve el historial (Priority: P1)

**Goal**: el mismo control de acceso que las otras dos operaciones (401/403/404/503), sin un permiso
nuevo.

**Independent Test**: pedir el historial sin permiso, sin ser el Dueño, y de una organización inexistente.

### Tests for User Story 3 ⚠️

- [X] T016 [P] [US3] Service en `tests/unit/test_subscription_period_service.py`: una organización que
  Clínicas no reconoce es `OrganizationNotFoundError`; Clínicas caída es
  `OrganizationCheckUnavailableError`; en ambos casos nada más se intenta (parte de T005).
- [X] T017 [P] [US3] `"charges"` agregado como tercera operación de
  `tests/contract/test_subscription_periods_access_control.py` (`OPERATIONS`, `PERMISSION_OF`, `call`):
  reutiliza automáticamente todas las comprobaciones ya parametrizadas (token, permiso, organización
  ajena o inexistente, Clínicas caída, orden de las comprobaciones) para la operación nueva.
- [X] T018 [P] [US3] `list_subscription_charges` agregado a `EXPECTED_PERMISSIONS` y a `REQUESTS` de
  `tests/contract/test_permission_coverage.py` (la matriz global, [contracts/permission-matrix.md](contracts/permission-matrix.md)).

### Implementation for User Story 3

- [X] T019 [US3] Sin código nuevo: `list_charges` del Service (T009) ya llama a `_read_organization`, el
  mismo método que usa `get_status`; la declaración `protected(SUBSCRIPTION_PERIODS_READ, …)` del Router
  (T010) ya exige el permiso. Esta tarea es solo la verificación de que T017/T018 pasan sin tocar
  `src/`.

**Checkpoint**: las tres operaciones (consultar, pagar, historial) pasan por las mismas comprobaciones de
acceso.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Colección de Postman: dos solicitudes nuevas (`list_subscription_charges: …`) en
  `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json` (una página vacía en «1.
  Consulta», una con un cobro aplicado y paginación en «3. Pago aprobado»); `OPERATIONS`,
  `REQUESTS_PER_FOLDER` y el nombre de la prueba G2 actualizados en
  `tests/contract/test_periods_postman_collection.py`.
- [X] T021 Revisar capas: `tests/unit/test_layering.py` en verde (el Router no importa `src.models`).
- [X] T022 Nivel rápido completo: `uv run pytest` en verde (cierre de `/speckit-implement`).

---

## Phase 7: Verificación completa (la puerta de la constitución antes de integrar en `main`)

- [X] T023 Suite completa con PostgreSQL 17 real: `uv run pytest -m ""` en verde (incluye migraciones
  desde cero, cobertura de permisos, OpenAPI, capas y los archivos de prueba lenta nuevos).
- [X] T024 Postman/Newman: `npm run e2e:periods --prefix tests/postman` en verde (la pila aislada,
  quickstart §5).

---

## Phase 8: Integración (solicitada por la persona responsable el 2026-11-25)

- [X] T025 Commit (Conventional Commits en inglés) y push de la rama `012-payment-history-charges`; Pull
  Request a `main` con el resumen y los resultados de las puertas.
- [X] T026 Integrar el Pull Request en `main`, confirmar que `main` en GitHub contiene los cambios y
  borrar las ramas `012-payment-history-charges` local y remota.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: después de Setup; bloquea las historias (los DTOs son compartidos).
- **US1 (Phase 3)**: después de Foundational; es el MVP.
- **US2 (Phase 4)**: después de US1 (reutiliza sus mismos archivos de prueba, agregando casos).
- **US3 (Phase 5)**: después de US1 (reutiliza `_read_organization`, ya escrito en T009); independiente de
  US2.
- **Polish (Phase 6)** → **Verificación (Phase 7)** → **Integración (Phase 8)**.

### Within Each User Story

Pruebas primero (deben fallar), luego el código; un archivo a la vez cuando dos tareas lo comparten
(T005/T011/T016 son la misma sección ampliada del mismo archivo, no tres archivos distintos).

### Parallel Opportunities

- T003 (su propio archivo) en paralelo con el resto de Foundational.
- T004, T006, T007 (archivos distintos) en paralelo dentro de US1.
- T017, T018 (archivos distintos) en paralelo dentro de US3.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup (T001) y Foundational (T002, T003).
2. US1 (T004 a T010): el historial publica los tres estados correctamente.
3. **STOP and VALIDATE**: `uv run pytest`.

### Incremental Delivery

1. US1 → US2 (paginación) → US3 (control de acceso, ya cubierto en su mayoría por US1 pero verificado
   explícitamente con las otras dos operaciones).
2. Verificación completa y luego integración.

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes.
- Ningún campo interno de la reconciliación (`payment_id`, `attempt`, `resolved_at`) se publica.
- Si una prueba existente falla, se corrige el código, no la comprobación.

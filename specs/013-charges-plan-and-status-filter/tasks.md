# Tasks: Plan de cada cobro y filtro por estado en el historial

**Input**: Design documents from `/specs/013-charges-plan-and-status-filter/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/charges-plan-and-status.md, quickstart.md

Todas las tareas tocan el mismo módulo de operación (`subscription_periods`); no hay paralelismo real de
archivos entre historias, así que no se marca ninguna `[P]`.

## Phase 1: Setup

- [X] T001 Crear la migración aditiva `alembic/versions/0010_subscription_charges_plan.py`
  (`ADD COLUMN plan VARCHAR(100) NULL`, reversible con `DROP COLUMN`)
- [X] T002 Agregar la columna `plan: Mapped[str | None]` a `SubscriptionCharge` en
  `src/models/subscription_charge.py`, con su comentario de procedencia (spec 013)
- [X] T003 Reflejar la columna nueva en `project-definition/DATA_SCHEMA.md` (tabla `subscription_charges`),
  marcada `[spec 013-charges-plan-and-status-filter]`

## Phase 2: Foundational (bloquea ambas historias)

- [X] T004 Agregar `plan: str | None` a `SubscriptionChargeRead` en `src/dtos/subscription_period.py`,
  con su `Field(description=..., examples=[...])` en el mismo estilo que el resto de los campos
- [X] T005 Agregar el parámetro `plan: str | None = None` a
  `SubscriptionPeriodRepository.add_charge` (`src/repositories/subscription_period_repository.py`),
  incluido en el `INSERT`
- [X] T006 Agregar el parámetro `status: str | None = None` a
  `SubscriptionPeriodRepository.list_charges`, agregado como condición del `WHERE` tanto en el conteo
  como en la selección (mismo filtro para ambos, para que `total` siempre corresponda a `items`)

## Phase 3: User Story 1 - Cada cobro dice con qué plan se generó (Priority: P1)

**Goal**: un cobro nuevo publica el nombre del plan vigente al crearse; uno anterior a esta migración sigue
en `null`.

**Independent Test**: generar un cobro, cambiar el nombre del plan en el catálogo, generar un segundo
cobro, y comprobar que el historial muestra el nombre de cada uno como era al crearse (FR-001 a FR-003).

- [X] T007 [US1] En `SubscriptionPeriodService.start_payment` (`src/services/subscription_period_service.py`),
  pasar `plan=context.plan.name` a `self._periods.add_charge(...)`
- [X] T008 [US1] En `src/routers/subscription_periods.py`, `_to_charge_read` debe incluir `plan=charge.plan`;
  `CHARGE_EXAMPLE` debe incluir `"plan": "Plan Individual"`; `GET_CHARGES_DESCRIPTION` debe documentar el
  campo nuevo
- [X] T009 [US1] `tests/unit/test_subscription_period_dtos.py`: `CHARGE_KEYS` incluye `plan`; el helper
  `charge(...)` lo trae por omisión; prueba nueva que confirma que `plan=None` se publica como `null`
- [X] T010 [US1] `tests/billing_support.py`: `FakePeriodRepository.add_charge` acepta y guarda `plan`
- [X] T011 [US1] `tests/unit/test_subscription_period_service.py`:
  `test_the_history_snapshots_the_plan_name_at_the_time_of_the_charge` (un cobro con un nombre de plan, el
  catálogo se renombra, un segundo cobro con el nombre nuevo; el historial no reescribe el primero)
- [X] T012 [US1] `tests/integration/test_subscription_period_repository.py`: la prueba de registro de un
  cobro verifica también `charge.plan`; prueba nueva `test_a_charge_registered_without_a_plan_keeps_it_null`
  (contra PostgreSQL real)
- [X] T013 [US1] `tests/contract/test_subscription_periods_api.py`: la prueba del cobro pendiente verifica
  también `charge["plan"]` contra el nombre real del plan de la fixture
- [X] T014 [US1] `tests/contract/test_subscription_periods_openapi.py`: `CHARGE_FIELDS` incluye `plan`;
  `CHARGE_NULLABLE_FIELDS` incluye `plan`
- [X] T015 [US1] `tests/unit/test_billing_design_rules.py`: `CHARGE_COLUMNS` incluye `plan`

**Checkpoint**: la historia 1 es verificable de punta a punta de forma independiente.

## Phase 4: User Story 2 - El historial se filtra por estado del lado del servidor (Priority: P1)

**Goal**: `status=pending|applied|closed` filtra `items`, con `total`/`total_pages` del subconjunto; un
valor inválido responde 422; ausente, sin cambios.

**Independent Test**: con cobros de los tres estados, pedir el historial filtrando por cada uno y
comprobar `items`/`total`/`total_pages` (FR-004 a FR-007).

- [X] T016 [US2] Agregar `StatusQuery = Annotated[ChargeStatusName | None, Query(...)]` en
  `src/routers/subscription_periods.py` (importando `ChargeStatusName` de `src/dtos/subscription_period.py`)
  y el parámetro `status: StatusQuery = None` en `list_subscription_charges`, reenviado al Service
- [X] T017 [US2] Agregar `status: str | None = None` a `SubscriptionPeriodService.list_charges`
  (`src/services/subscription_period_service.py`), reenviado sin transformación al Repository
- [X] T018 [US2] Documentar `status` en `GET_CHARGES_DESCRIPTION` (`src/routers/subscription_periods.py`)
- [X] T019 [US2] `tests/billing_support.py`: `FakePeriodRepository.list_charges` acepta `status` y filtra
  en memoria con el mismo criterio que el Repository real
- [X] T020 [US2] `tests/unit/test_subscription_period_service.py`:
  `test_the_history_can_be_filtered_by_status` (un cobro pendiente y uno cerrado; filtrar por cada estado
  trae solo el suyo, con el `total` correcto)
- [X] T021 [US2] `tests/integration/test_subscription_period_repository.py`: la función ayudante
  `list_charges(...)` acepta `status`; prueba nueva `test_the_history_can_be_filtered_by_status` (pending/
  applied/closed, contra PostgreSQL real)
- [X] T022 [US2] `tests/contract/test_subscription_periods_api.py`: pruebas nuevas
  `test_the_history_can_be_filtered_by_status` y `test_the_history_rejects_an_unknown_status` (HTTP de
  punta a punta, incluido el 422)
- [X] T023 [US2] `tests/contract/test_subscription_periods_openapi.py`: el parámetro `status` se agrega a
  la lista esperada de parámetros de la operación, con su `in`/`required`

**Checkpoint**: ambas historias (P1) son verificables de forma independiente y juntas.

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T024 Actualizar la colección de Postman
  (`tests/postman/collections/MailySoft-System-Periodos.postman_collection.json`): las solicitudes de
  historial ya existentes esperan también `plan`; una solicitud nueva ejercita `status`
- [X] T025 Correr `uv run pytest` (rápido) tras cada tarea; antes de integrar, correr la puerta completa:
  `uv run pytest -m ""` (con `docker compose up -d db` + `migrate`), `npm run e2e:periods`
  (`tests/postman/`, stack `docker-compose.e2e.yml`)
- [X] T026 Confirmar que `tests/contract/test_permission_coverage.py` y
  `test_subscription_periods_access_control.py` siguen en verde sin cambios (ni la operación ni su permiso
  cambiaron)

## Dependencies & Execution Order

- Phase 1 (Setup) antes que todo: la columna debe existir antes de que cualquier capa la use.
- Phase 2 (Foundational) antes de ambas historias: el DTO y las dos firmas de Repository son compartidas.
- Historia 1 (T007-T015) e Historia 2 (T016-T023) son independientes entre sí (ninguna depende de los
  cambios de la otra) y ambas son P1: se implementan en el orden que sea más cómodo, pero ambas deben
  cerrarse antes de Polish.
- Phase 5 (Polish) al final: la colección de Postman y la puerta de calidad completa ejercitan ambas
  historias juntas.

## Implementation Strategy

MVP = ambas historias juntas (las dos son P1 y pequeñas; no hay beneficio real en entregarlas por separado
dado que el Frontend las necesita a la vez para su columna «Plan» y sus filtros). Incremento único.

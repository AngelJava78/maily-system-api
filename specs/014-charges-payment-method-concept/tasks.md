# Tasks: Forma de pago y concepto amigable de cada cobro

**Input**: Design documents from `/specs/014-charges-payment-method-concept/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/charges-payment-method-concept.md,
quickstart.md

Todas las tareas tocan el mismo módulo de operación (`subscription_periods`); no hay paralelismo real de
archivos entre historias, así que no se marca ninguna `[P]`.

## Phase 1: Setup

- [X] T001 Crear la migración aditiva `alembic/versions/0011_subscription_charges_concept_method.py`
  (`ADD COLUMN concept VARCHAR(500) NULL`, `ADD COLUMN payment_method VARCHAR(10) NULL`, `CHECK
  (payment_method IS NULL OR payment_method IN ('card','oxxo','transfer'))`, reversible)
- [X] T002 Agregar las columnas `concept: Mapped[str | None]`/`payment_method: Mapped[str | None]` y el
  `StrEnum PaymentMethod` a `src/models/subscription_charge.py`, con su comentario de procedencia (spec
  014) y el `CheckConstraint` correspondiente en `__table_args__`
- [X] T003 Reflejar las dos columnas y el `CHECK` nuevo en `project-definition/DATA_SCHEMA.md` (tabla
  `subscription_charges`), marcados `[spec 014-charges-payment-method-concept]`

## Phase 2: Foundational (bloquea ambas historias)

- [X] T004 Agregar `payment_method_id: str | None = None` y `payment_type_id: str | None = None` a
  `PaymentRecord` en `src/integrations/payments_api.py`, leídos en `_parse` desde la respuesta de la API
  de pagos
- [X] T005 Agregar `concept: str | None` y `payment_method: ChargePaymentMethodName | None` a
  `SubscriptionChargeRead` en `src/dtos/subscription_period.py` (con el nuevo
  `ChargePaymentMethodName = Literal["card", "oxxo", "transfer"]`), con su `Field(description=...,
  examples=[...])` en el mismo estilo que el resto de los campos

## Phase 3: User Story 1 - Cada cobro resuelto dice con qué se pagó (Priority: P1)

**Goal**: un cobro aplicado o cerrado publica `card`/`oxxo`/`transfer` cuando la API de pagos reportó un
método reconocido; `null` mientras sigue pendiente, si no lo reportó, si no se reconoce, o si es anterior
a esta migración.

**Independent Test**: aprobar un cobro con `payment_type_id` de tarjeta y otro de OXXO, y comprobar que el
historial publica `payment_method: "card"`/`"oxxo"` respectivamente (FR-001 a FR-006).

- [X] T006 [US1] Agregar la tabla `_PAYMENT_METHOD_BY_TYPE` y el método estático
  `SubscriptionPeriodService._payment_method_of(payment)` en `src/services/subscription_period_service.py`
- [X] T007 [US1] En `_apply` y `_close` (mismo archivo), calcular `payment_method =
  self._payment_method_of(payment)` y pasarlo a `apply_charge(...)`/`close_charge(...)`; actualizar las
  cuatro llamadas a `_close` dentro de `_settle` para que reciban también `payment`
- [X] T008 [US1] Agregar el parámetro `payment_method: str | None = None` a
  `SubscriptionPeriodRepository.apply_charge` y `.close_charge`
  (`src/repositories/subscription_period_repository.py`), incluido en sus respectivos `UPDATE`
- [X] T009 [US1] En `src/routers/subscription_periods.py`, `_to_charge_read` debe incluir
  `payment_method=charge.payment_method`; `CHARGE_EXAMPLE` debe incluir `"payment_method": "card"`;
  `GET_CHARGES_DESCRIPTION` debe documentar el campo nuevo
- [X] T010 [US1] `tests/stubs/payments_api/app.py`: `StatusIn` acepta `payment_method_id`/
  `payment_type_id`; `read()` los publica en la respuesta simulada
- [X] T011 [US1] `tests/billing_support.py`: `make_payment`/`FakePaymentsApi.set_status` aceptan
  `payment_method_id`/`payment_type_id`; `FakePeriodRepository.close_charge`/`.apply_charge` aceptan y
  guardan `payment_method`
- [X] T012 [US1] `tests/unit/test_subscription_period_dtos.py`: `CHARGE_KEYS` incluye `payment_method`; el
  helper `charge(...)` lo trae por omisión; pruebas nuevas del `null` y de los tres valores válidos, y del
  rechazo de un cuarto valor
- [X] T013 [US1] `tests/unit/test_subscription_period_service.py`:
  `test_an_applied_charge_records_the_payment_method_pagos_reported` (parametrizada: tarjeta, OXXO,
  transferencia, un tipo no reconocido y ninguno) y
  `test_a_closed_charge_also_records_the_payment_method_when_pagos_reported_one`
- [X] T014 [US1] `tests/integration/test_subscription_period_repository.py`:
  `test_applying_a_charge_records_the_payment_method`,
  `test_closing_a_charge_records_the_payment_method_when_given` (contra PostgreSQL real)
- [X] T015 [US1] `tests/contract/test_subscription_periods_api.py`: la prueba del cobro aplicado verifica
  también `payment_method`; pruebas nuevas `test_a_closed_charge_also_shows_the_payment_method_pagos_reported`,
  `test_a_payment_method_this_service_does_not_recognise_is_null_not_guessed`
- [X] T016 [US1] `tests/contract/test_subscription_periods_openapi.py`: `CHARGE_FIELDS`/
  `CHARGE_NULLABLE_FIELDS` incluyen `payment_method`; se verifica su `enum`
- [X] T017 [US1] `tests/unit/test_billing_design_rules.py`: `CHARGE_COLUMNS` incluye `payment_method`

**Checkpoint**: la historia 1 es verificable de punta a punta de forma independiente.

## Phase 4: User Story 2 - Cada cobro tiene un concepto amigable (Priority: P2)

**Goal**: todo cobro nuevo publica el mismo texto que esta API ya le manda a la API de pagos como
`description`; uno anterior a esta migración sigue en `null`.

**Independent Test**: crear un cobro y comprobar que el historial publica el mismo texto enviado a la API
de pagos al crearlo (FR-007 a FR-009).

- [X] T018 [US2] En `SubscriptionPeriodService.start_payment`
  (`src/services/subscription_period_service.py`), pasar `concept=description` a
  `self._periods.add_charge(...)`
- [X] T019 [US2] Agregar el parámetro `concept: str | None = None` a
  `SubscriptionPeriodRepository.add_charge` (`src/repositories/subscription_period_repository.py`),
  incluido en el `INSERT`
- [X] T020 [US2] En `src/routers/subscription_periods.py`, `_to_charge_read` debe incluir
  `concept=charge.concept`; `CHARGE_EXAMPLE` debe incluir `"concept": "Suscripción Plan Individual —
  mensual"`; `GET_CHARGES_DESCRIPTION` debe documentar el campo nuevo
- [X] T021 [US2] `tests/billing_support.py`: `FakePeriodRepository.add_charge` acepta y guarda `concept`
- [X] T022 [US2] `tests/unit/test_subscription_period_dtos.py`: prueba nueva que confirma que
  `concept=None` se publica como `null`
- [X] T023 [US2] `tests/unit/test_subscription_period_service.py`:
  `test_the_history_snapshots_the_concept_at_the_time_of_the_charge`
- [X] T024 [US2] `tests/integration/test_subscription_period_repository.py`:
  `test_a_charge_is_registered_with_its_concept_snapshot`,
  `test_a_charge_registered_without_a_concept_keeps_it_null`,
  `test_the_history_includes_concept_and_payment_method` (contra PostgreSQL real)
- [X] T025 [US2] `tests/contract/test_subscription_periods_api.py`: la prueba del cobro pendiente verifica
  también `charge["concept"]`
- [X] T026 [US2] `tests/contract/test_subscription_periods_openapi.py`: `CHARGE_FIELDS`/
  `CHARGE_NULLABLE_FIELDS` incluyen `concept`
- [X] T027 [US2] `tests/unit/test_billing_design_rules.py`: `CHARGE_COLUMNS` incluye `concept`

**Checkpoint**: ambas historias son verificables de forma independiente y juntas.

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T028 Actualizar la colección de Postman
  (`tests/postman/collections/MailySoft-System-Periodos.postman_collection.json`): la solicitud que
  aprueba un cobro manda `payment_type_id: "credit_card"`; la que lee el historial aplicado comprueba
  `concept` y `payment_method`
- [X] T029 Correr `uv run pytest` (rápido) tras cada tarea; antes de integrar, correr la puerta completa:
  `uv run pytest -m ""` (con `docker compose up -d db` + migración), `npm run e2e:periods`
  (`tests/postman/`, stack `docker-compose.e2e.yml`)
- [X] T030 Confirmar que `tests/contract/test_permission_coverage.py` y
  `test_subscription_periods_access_control.py` siguen en verde sin cambios (ni la operación ni su
  permiso cambiaron)

## Dependencies & Execution Order

- Phase 1 (Setup) antes que todo: las columnas deben existir antes de que cualquier capa las use.
- Phase 2 (Foundational) antes de ambas historias: el puerto de integración y el DTO son compartidos.
- Historia 1 (T006-T017, `payment_method`) e Historia 2 (T018-T027, `concept`) son independientes entre
  sí; Historia 1 es P1 (lo que el rediseño del Frontend necesita primero para distinguir cobros a simple
  vista) e Historia 2 es P2, pero ambas se implementan juntas en esta feature porque comparten la misma
  migración y las mismas pruebas de contrato.
- Phase 5 (Polish) al final: la colección de Postman y la puerta de calidad completa ejercitan ambas
  historias juntas.

## Implementation Strategy

MVP = Historia 1 sola (`payment_method`) sería suficiente para el rediseño del Frontend, pero Historia 2
(`concept`) es tan pequeña y comparte la misma migración que no hay beneficio real en separarlas: se
entregan juntas en un solo incremento.

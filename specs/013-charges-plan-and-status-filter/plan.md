# Implementation Plan: Plan de cada cobro y filtro por estado en el historial

**Branch**: `013-charges-plan-and-status-filter` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-charges-plan-and-status-filter/spec.md`

## Summary

Dos ampliaciones aditivas de `GET /api/v1/subscription-periods/{organization_id}/charges` (spec 012): (1)
cada cobro publica `plan` (texto, nullable), una foto del nombre del plan al momento de crearse, escrita una
sola vez en `start_payment`/`add_charge`, nunca recalculada ([research](research.md) R1, R2); (2) un
parámetro de consulta opcional `status` filtra `items` del lado del Repository, con `total`/`total_pages`
ya reflejando el subconjunto filtrado (R3, R4). Migración aditiva (0010): una columna nullable, sin tocar
restricciones ni índices existentes. Sin permiso nuevo, sin cambio del contrato ya publicado (R5).

## Technical Context

**Language/Version**: Python 3.14+ (igual que el resto del servicio)

**Primary Dependencies**: las del proyecto, sin dependencias nuevas.

**Storage**: PostgreSQL 17; migración `0010_subscription_charges_plan.py` (aditiva: `ADD COLUMN plan
VARCHAR(100) NULL`, reversible).

**Testing**: pytest + pytest-asyncio + httpx. Nivel rápido: DTO (el campo nullable), Service con dobles (el
plan se pasa a `add_charge`, el filtro se pasa a `list_charges`), Repository con el doble en memoria. Nivel
lento: Repository contra PostgreSQL 17 real (la columna persiste, el filtro en SQL), contrato HTTP (filtro
y 422 de un valor inválido), OpenAPI (el campo y el parámetro nuevos). Postman/Newman: las dos solicitudes
de la colección que ya traen un cobro se actualizan para esperar también `plan` en la respuesta; una
solicitud nueva ejercita `status`. `/speckit-implement` corre solo el nivel rápido.

**Target Platform**: igual que el resto del servicio (contenedor Linux, Docker Compose).

**Project Type**: web-service

**Performance Goals**: sin efecto medible; una columna más en una fila ya leída, una condición más en un
`WHERE` ya indexado por `organization_id`.

**Constraints**: `plan` nunca se recalcula ni se consulta al catálogo al leer (R1); los cobros anteriores a
la migración quedan en `null` de forma permanente (R2); `status` acepta un solo valor por consulta (ver
«Clarifications» de spec.md); el contrato ya publicado por spec 012 no cambia (R5).

**Scale/Scope**: 1 migración aditiva; 4 módulos de `src/` modificados de forma aditiva
(`models/subscription_charge.py`, `dtos/subscription_period.py`,
`repositories/subscription_period_repository.py`, `services/subscription_period_service.py`,
`routers/subscription_periods.py`); dobles de prueba (`tests/billing_support.py`) y los archivos de prueba
unitaria, de integración y de contrato ya existentes del router, extendidos; 1 colección de Postman
extendida; sin documentos de despliegue nuevos (sin variable de entorno nueva).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ La columna se añade en el modelo (`src/models/`); el Repository filtra, el Service solo pasa el parámetro, el Router solo lo declara y lo reenvía — ninguna capa invade a otra |
| II. Modelos ≠ DTOs | ✅ | ✅ `plan` se agrega tanto al modelo ORM como al DTO de salida, por separado, como ya exige el resto de los campos de este mismo DTO |
| III. Asincronía | ✅ | ✅ Sin cambio: la misma consulta async ya existente, con una condición más |
| IV. OpenAPI y REST | ✅ | ✅ `plan` documentado como nullable; `status` documentado como parámetro de consulta opcional con sus tres valores; sigue siendo un listado paginado |
| V. Pruebas pytest | ✅ | ✅ DTO, Service y Repository con dobles (rápido); Repository, contrato HTTP y OpenAPI contra PostgreSQL real (lento); Postman actualizado en la misma feature |
| VI. Migraciones Alembic | ✅ | ✅ Migración 0010, aditiva y reversible (`downgrade` quita la columna); `project-definition/DATA_SCHEMA.md` actualizado |
| VII. Idioma | ✅ | ✅ Identificadores en inglés; documentos y descripciones de OpenAPI en español |
| VIII. Control de acceso delegado | ✅ | ✅ Sin cambio: mismo permiso `subscription_periods:read`, ya cubierto por la prueba de cobertura existente (ni la operación ni su permiso cambian) |
| IX. Integraciones | ✅ | ✅ Sin integración nueva |

Sin desviaciones: «Complexity Tracking» queda vacío.

## Ajustes a las pruebas existentes

| Archivo | Ajuste | Por qué |
|---|---|---|
| `tests/billing_support.py` | `FakePeriodRepository.add_charge(..., plan=None)` y `.list_charges(..., status=None)` | El doble del Service necesita los dos parámetros nuevos |
| `tests/unit/test_subscription_period_dtos.py` | `CHARGE_KEYS` incluye `plan`; el helper `charge(...)` lo trae por omisión; prueba nueva del `null` | El campo nuevo es parte del contrato que esta prueba verifica campo por campo |
| `tests/contract/test_subscription_periods_openapi.py` | `CHARGE_FIELDS`/`CHARGE_NULLABLE_FIELDS` incluyen `plan`; el parámetro `status` se agrega a la lista esperada | El esquema publicado creció en un campo y un parámetro |
| `tests/unit/test_billing_design_rules.py` | `CHARGE_COLUMNS` incluye `plan` | La prueba verifica, columna por columna, que el modelo no guarda más de lo que debe |
| `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json` | Las solicitudes existentes de «historial» esperan también `plan`; una solicitud nueva ejercita `status` | El Principio V exige que la colección refleje cada cambio del contrato |

## Documentación y despliegue

- Sin cambios: `.env.example`, `README.md`, `docker-compose.yml` (sin variable de entorno nueva).
- `project-definition/DATA_SCHEMA.md`: se agrega la columna `plan` a la fila de `subscription_charges`
  (Principio VI: todo cambio de esquema se refleja ahí, marcado con el comentario de esta spec).

## Project Structure

### Documentation (this feature)

```text
specs/013-charges-plan-and-status-filter/
├── plan.md                        # Este archivo
├── research.md                    # Fase 0: decisiones R1-R5
├── data-model.md                  # Fase 1: la columna, el DTO, los dos flujos
├── quickstart.md                  # Fase 1: cómo comprobarlo
├── contracts/
│   └── charges-plan-and-status.md # El contrato ampliado
└── tasks.md                       # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
alembic/versions/
└── 0010_subscription_charges_plan.py   # ADD COLUMN plan (nullable), aditiva

src/
├── models/
│   └── subscription_charge.py           # columna `plan`
├── dtos/
│   └── subscription_period.py           # SubscriptionChargeRead.plan
├── repositories/
│   └── subscription_period_repository.py # add_charge(plan=...), list_charges(status=...)
├── services/
│   └── subscription_period_service.py    # list_charges(status=...), start_payment pasa plan.name
└── routers/
    └── subscription_periods.py           # StatusQuery, _to_charge_read(plan=...)

tests/
├── billing_support.py                     # FakePeriodRepository.add_charge/list_charges
├── unit/
│   ├── test_subscription_period_dtos.py
│   ├── test_subscription_period_service.py
│   └── test_billing_design_rules.py
├── integration/
│   └── test_subscription_period_repository.py
└── contract/
    ├── test_subscription_periods_api.py
    └── test_subscription_periods_openapi.py
```

**Structure Decision**: el proyecto único de siempre (`src/` y `tests/`), sin carpetas nuevas.

## Trazabilidad de requisitos

| Requisito | Dónde se cumple | Dónde se prueba |
|---|---|---|
| FR-001, FR-002, FR-003 | `models/subscription_charge.py` (columna `plan`), `services/subscription_period_service.py` (`start_payment` pasa `plan=context.plan.name`), `repositories/subscription_period_repository.py` (`add_charge`) | `test_subscription_period_service.py`, `test_subscription_period_repository.py` |
| FR-004, FR-005, FR-007 | `repositories/subscription_period_repository.py` (`list_charges(status=...)`), `services/subscription_period_service.py`, `routers/subscription_periods.py` (`StatusQuery`) | `test_subscription_period_service.py`, `test_subscription_period_repository.py`, `test_subscription_periods_api.py` |
| FR-006 | `routers/subscription_periods.py` (`Annotated[ChargeStatusName | None, Query(...)]`, FastAPI valida) | `test_subscription_periods_api.py` |
| FR-008 | Revisión (nada de spec 012 se modificó, solo se extendió) | Toda la suite existente de spec 012 sigue en verde |
| FR-009 | `dtos/subscription_period.py` (`SubscriptionChargeRead.plan`), `routers/subscription_periods.py` (`StatusQuery`) | `test_subscription_periods_openapi.py` |

## Complexity Tracking

Sin desviaciones de la constitución que justificar.

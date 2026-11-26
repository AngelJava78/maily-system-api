# Implementation Plan: Forma de pago y concepto amigable de cada cobro

**Branch**: `014-charges-payment-method-concept` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-charges-payment-method-concept/spec.md`

## Summary

Dos ampliaciones aditivas de `GET /api/v1/subscription-periods/{organization_id}/charges` (spec 012,
013): (1) cada cobro publica `payment_method` (nullable, `card`/`oxxo`/`transfer`), traducido por este
servicio desde el `payment_type_id` crudo que ahora reporta la API de pagos (mailySoft-pagos, spec
005-payment-method), escrito solo cuando el cobro se resuelve ([research](research.md) R1, R2); (2) cada
cobro publica `concept` (texto, nullable), el mismo texto que esta API ya construye y envía a la API de
pagos como `description` al crear el cobro, guardado como una foto igual que `plan` (spec 013, R3). Dos
columnas nullable vía una migración aditiva (0011), sin tocar restricciones ni índices existentes. Sin
permiso nuevo, sin cambio del contrato ya publicado (R4).

## Technical Context

**Language/Version**: Python 3.14+ (igual que el resto del servicio)

**Primary Dependencies**: las del proyecto, sin dependencias nuevas.

**Storage**: PostgreSQL 17; migración `0011_subscription_charges_concept_method.py` (aditiva: dos
`ADD COLUMN` nullable más un `CHECK` sobre `payment_method`, reversible).

**Testing**: pytest + pytest-asyncio + httpx. Nivel rápido: integración (`payments_api.py` parsea los dos
campos nuevos de Pagos), DTO (los dos campos nullable), Service con dobles (el mapeo
`payment_type_id` → `card`/`oxxo`/`transfer`, incluido un valor no reconocido, y el `concept` pasado a
`add_charge`), Repository con el doble en memoria. Nivel lento: Repository contra PostgreSQL 17 real (las
dos columnas persisten), contrato HTTP (un cobro aplicado y uno cerrado publican su `payment_method`; uno
pendiente publica `null`), OpenAPI (los dos campos nuevos). Postman/Newman: la solicitud que aprueba un
cobro ahora manda un `payment_type_id`; la que lee el historial comprueba `concept` y `payment_method`.
`/speckit-implement` corre solo el nivel rápido.

**Target Platform**: igual que el resto del servicio (contenedor Linux, Docker Compose).

**Project Type**: web-service

**Performance Goals**: sin efecto medible; dos columnas más en una fila ya leída o escrita, ningún
`JOIN` ni consulta adicional (el mapeo de `payment_method` es una tabla en memoria de cinco entradas).

**Constraints**: `payment_method` solo se escribe al resolver el cobro, nunca mientras sigue `pending`
(R1); un `payment_type_id` no reconocido publica `null`, nunca una de las tres categorías por
aproximación (R2); `concept` se escribe una sola vez, al crear el cobro, igual que `plan` (R3); los
cobros ya existentes quedan en `null` de forma permanente en ambos campos; el contrato ya publicado por
spec 012/013 no cambia (R4).

**Scale/Scope**: 1 migración aditiva; 5 módulos de `src/` modificados de forma aditiva
(`integrations/payments_api.py`, `models/subscription_charge.py`, `dtos/subscription_period.py`,
`repositories/subscription_period_repository.py`, `services/subscription_period_service.py`,
`routers/subscription_periods.py`); dobles de prueba (`tests/billing_support.py`,
`tests/stubs/payments_api/app.py`) y los archivos de prueba unitaria, de integración y de contrato ya
existentes del router, extendidos; 1 colección de Postman extendida; sin documentos de despliegue
nuevos (sin variable de entorno nueva).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ El mapeo de `payment_type_id` vive en el Service (es una regla de negocio: qué cuenta como «tarjeta»); la Integración solo transporta los dos campos crudos; el Repository solo persiste lo que el Service decide; ninguna capa invade a otra |
| II. Modelos ≠ DTOs | ✅ | ✅ `concept`/`payment_method` se agregan tanto al modelo ORM como al DTO de salida, por separado, como ya exige el resto de los campos de este mismo DTO |
| III. Asincronía | ✅ | ✅ Sin cambio: la misma consulta async ya existente a la API de pagos, leyendo dos campos más de la misma respuesta |
| IV. OpenAPI y REST | ✅ | ✅ `payment_method` documentado como nullable con sus tres valores; `concept` documentado como texto nullable; sigue siendo el mismo listado paginado |
| V. Pruebas pytest | ✅ | ✅ Integración, DTO, Service y Repository con dobles (rápido); Repository, contrato HTTP y OpenAPI contra PostgreSQL real (lento); Postman actualizado en la misma feature |
| VI. Migraciones Alembic | ✅ | ✅ Migración 0011, aditiva y reversible (`downgrade` quita el `CHECK` y las dos columnas); `project-definition/DATA_SCHEMA.md` actualizado |
| VII. Idioma | ✅ | ✅ Identificadores en inglés; documentos y descripciones de OpenAPI en español |
| VIII. Control de acceso delegado | ✅ | ✅ Sin cambio: mismo permiso `subscription_periods:read`, ya cubierto por la prueba de cobertura existente |
| IX. Integraciones | ✅ | ✅ Sin integración nueva: se leen dos campos más de la respuesta que la API de pagos ya daba (spec 005-payment-method de mailySoft-pagos, ya fusionada) |

Sin desviaciones: «Complexity Tracking» queda vacío.

## Ajustes a las pruebas existentes

| Archivo | Ajuste | Por qué |
|---|---|---|
| `tests/billing_support.py` | `make_payment(..., payment_method_id=None, payment_type_id=None)`, `FakePaymentsApi.set_status(..., payment_method_id=..., payment_type_id=...)`, `FakePeriodRepository.add_charge(..., concept=None)`, `.close_charge`/`.apply_charge(..., payment_method=None)` | Los dobles del Service necesitan los campos y parámetros nuevos |
| `tests/stubs/payments_api/app.py` | `StatusIn` acepta `payment_method_id`/`payment_type_id`; `read()` los publica | La simulación de Pagos de los niveles lento/Postman debe reportarlos igual que la real (spec 005) |
| `tests/unit/test_subscription_period_dtos.py` | `CHARGE_KEYS` incluye `concept`/`payment_method`; el helper `charge(...)` los trae por omisión; pruebas nuevas de `null` y de los tres valores | Los campos nuevos son parte del contrato que esta prueba verifica campo por campo |
| `tests/contract/test_subscription_periods_openapi.py` | `CHARGE_FIELDS`/`CHARGE_NULLABLE_FIELDS` incluyen ambos; se verifica el `enum` de `payment_method` | El esquema publicado creció en dos campos |
| `tests/unit/test_billing_design_rules.py` | `CHARGE_COLUMNS` incluye `concept`/`payment_method` | La prueba verifica, columna por columna, que el modelo no guarda más de lo que debe |
| `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json` | La solicitud que aprueba un cobro manda `payment_type_id`; la que lee el historial comprueba `concept` y `payment_method` | El Principio V exige que la colección refleje cada cambio del contrato |

## Documentación y despliegue

- Sin cambios: `.env.example`, `README.md`, `docker-compose.yml` (sin variable de entorno nueva).
- `project-definition/DATA_SCHEMA.md`: se agregan `concept` y `payment_method` a la fila de
  `subscription_charges`, y el `CHECK` nuevo a la tabla de restricciones (Principio VI).

## Project Structure

### Documentation (this feature)

```text
specs/014-charges-payment-method-concept/
├── plan.md                                 # Este archivo
├── research.md                             # Fase 0: decisiones R1-R4
├── data-model.md                           # Fase 1: las columnas, el DTO, los dos flujos
├── quickstart.md                           # Fase 1: cómo comprobarlo
├── contracts/
│   └── charges-payment-method-concept.md   # El contrato ampliado
└── tasks.md                                # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
alembic/versions/
└── 0011_subscription_charges_concept_method.py   # ADD COLUMN concept, payment_method (nullable) + CHECK

src/
├── integrations/
│   └── payments_api.py                    # PaymentRecord.payment_method_id/payment_type_id
├── models/
│   └── subscription_charge.py             # columnas concept, payment_method + PaymentMethod enum
├── dtos/
│   └── subscription_period.py             # SubscriptionChargeRead.concept/payment_method
├── repositories/
│   └── subscription_period_repository.py  # add_charge(concept=...), apply_charge/close_charge(payment_method=...)
├── services/
│   └── subscription_period_service.py     # _payment_method_of(), start_payment pasa concept
└── routers/
    └── subscription_periods.py            # _to_charge_read(concept=..., payment_method=...)

tests/
├── billing_support.py
├── stubs/payments_api/app.py
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
| FR-001, FR-002, FR-004 | `services/subscription_period_service.py` (`_payment_method_of`, `_PAYMENT_METHOD_BY_TYPE`), `integrations/payments_api.py` (`PaymentRecord.payment_type_id`) | `test_subscription_period_service.py` |
| FR-003 | `services/subscription_period_service.py` (`_payment_method_of` solo se llama al resolver, nunca para un cobro que sigue `pending`) | `test_subscription_period_service.py`, `test_subscription_periods_api.py` |
| FR-005 | `services/subscription_period_service.py` (`_close` recibe el `payment` y calcula `payment_method` igual que `_apply`) | `test_subscription_period_service.py` |
| FR-006 | Sin backfill (revisión de la migración 0011) | `test_subscription_period_dtos.py` |
| FR-007, FR-008 | `services/subscription_period_service.py` (`start_payment` pasa `concept=description`), `repositories/subscription_period_repository.py` (`add_charge`) | `test_subscription_period_service.py`, `test_subscription_period_repository.py` |
| FR-009 | Sin backfill (revisión de la migración 0011) | `test_subscription_period_dtos.py` |
| FR-010 | Revisión (nada de spec 012/013 se modificó, solo se extendió) | Toda la suite existente sigue en verde |
| FR-011 | `dtos/subscription_period.py` (`ChargePaymentMethodName`, `concept: str | None`) | `test_subscription_periods_openapi.py` |

## Complexity Tracking

Sin desviaciones de la constitución que justificar.

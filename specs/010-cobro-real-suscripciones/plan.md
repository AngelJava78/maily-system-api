# Implementation Plan: Cobro Real de Suscripciones de Clínicas

**Branch**: `010-cobro-real-suscripciones` | **Date**: 2026-11-11 (rediseñado) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-cobro-real-suscripciones/spec.md`

## Summary

Añadir la operación que cobra, contra Mercado Pago a través de `mailySoft-pagos`
(`POST /api/v1/payments`), una suscripción de clínica cuya asignación (clínica, plan, ciclo) **no
vive en este servicio**: se consulta a un nuevo cliente del futuro microservicio Clínicas (ampliación
del `ClinicsApiClient` ya existente desde la spec 001), igual que ya se consulta su conteo de
clínicas por plan. `maily-system-api` guarda solo el **historial de cobros**
(`clinic_subscription_charges`), resolviendo el estatus por consulta a Pagos (sin webhook hacia este
servicio). Dos permisos con audiencias distintas: `clinic_subscriptions:read` (quien administra la
plataforma, vía `/authorization/check`) y `clinic_subscriptions:charge` (una persona de la propia
clínica, vía `/authorization/me`, porque Pagos necesita su `tenant_id`). El cobro periódico
automático queda fuera de esta especificación (FR-030).

**Rediseño (2026-11-11)**: la primera versión de este plan introducía una tabla propia
`clinic_subscriptions` (clínica + plan + ciclo + estatus). El arquitecto del proyecto determinó que
esa asignación pertenece a Clínicas (Principio IX), no a `maily-system-api`: este plan reemplaza esa
tabla por una consulta de solo lectura a un cliente nuevo, y reduce el alcance local a cobrar +
guardar el historial.

## Technical Context

**Language/Version**: Python 3.14 (constitución, Stack Tecnológico)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0 async (asyncpg), Pydantic v2, httpx (clientes de
Pagos, de Usuarios y de Clínicas), Alembic

**Storage**: PostgreSQL 17 — una tabla nueva, `clinic_subscription_charges` (el historial de
cobros); no se toca `subscriptions`, `subscription_statuses` ni ninguna tabla de las specs
006-009 recién integradas

**Testing**: pytest + pytest-asyncio, en los dos niveles de la constitución v1.1.0 (rápido por
defecto; lo que toca PostgreSQL real, marcado `slow`); clientes de Pagos, Usuarios y Clínicas
sustituidos por dobles de prueba (unit) y por simulaciones HTTP propias (contract: ampliación de
`tests/stubs/clinics_api/app.py`, nuevo `tests/stubs/payments_api/app.py`, ampliación de
`tests/stubs/users_api/app.py`)

**Target Platform**: Linux server (contenedor Docker), igual que el resto del servicio

**Project Type**: Servicio web (API REST, un solo proyecto `src/` en capas — Principio I)

**Performance Goals**: Sin objetivo propio distinto del resto del servicio; cada disparo de cobro
hace a lo sumo una llamada a Clínicas, una a Usuarios y una a Pagos, en ese orden (nunca en paralelo
con la escritura local, para no guardar un cobro que Pagos no confirmó)

**Constraints**: Dinero en centavos solo en la llamada a Pagos (Principio VI); ninguna llamada a
Clínicas, Usuarios o Pagos se reintenta automáticamente (Principio IX); el `tenant_id` de un pago
nunca se envía en el cuerpo a Pagos (Principio X de Pagos); la asignación clínica↔plan↔ciclo nunca
se guarda en la base de datos de este servicio (Principio IX, consulta siempre, nunca copia)

**Scale/Scope**: 3 operaciones bajo `/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges`
(crear/disparar, listar, consultar); una ampliación de contrato consumido (Clínicas) y dos clientes
nuevos/ampliados (Pagos nuevo, Clínicas ampliado)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento |
|---|---|
| I. Arquitectura en capas | `src/routers/clinic_subscriptions.py` → `src/services/clinic_subscription_service.py` → `src/repositories/clinic_subscription_charge_repository.py` → `src/database/`; el cliente de Pagos vive en `src/integrations/payments_api.py`; la ampliación del cliente de Clínicas, en el `clinics_api.py` ya existente. Sin desviación. |
| II. Modelos ORM vs DTOs | `src/models/clinic_subscription_charge.py` (único modelo ORM nuevo: ya no hay `ClinicSubscription`/`ClinicSubscriptionStatus`, esa entidad no vive aquí); `src/dtos/clinic_subscription.py` (DTOs). Sin desviación. |
| III. Asincronía de extremo a extremo | Cliente de Pagos y ampliación del de Clínicas con `httpx.AsyncClient`/`asyncio.timeout`, mismo patrón que `UsersApiClient`. Sin desviación. |
| IV. Contratos OpenAPI | 3 operaciones documentadas con `x-required-permission`, el listado paginado. Sin desviación. |
| V. Pruebas con pytest, dos niveles (constitución v1.1.0) | Unitarias (rápidas, por defecto) de `ClinicSubscriptionChargeService` con los tres clientes sustituidos por dobles; de contrato (`slow`) de cada operación contra la app real y las tres simulaciones; de Repository (`slow`) contra PostgreSQL 17 real; `test_permission_coverage` ampliado. `/speckit-implement` se limita al nivel rápido; la suite completa (incluida `slow`) se corre antes de integrar a `main`, responsabilidad de quien integra (sin pipeline de CI todavía). |
| VI. Esquema versionado con Alembic | Una tabla nueva, migración `0008_clinic_subscription_charges.py` (siguiente número libre tras la `0007` de `008-subscription-modules-table`, ya en `main`), reversible; `project-definition/DATA_SCHEMA.md` actualizado con `-- [spec 010-cobro-real-suscripciones]`; dinero en centavos (`INTEGER`, no `NUMERIC`: es lo que se envió a Pagos, no un precio propio). Sin desviación. |
| VII. Idioma | Identificadores, campos y códigos de error en inglés; mensajes y documentación en español. Sin desviación. |
| VIII. Control de acceso delegado | Igual que la versión anterior de este plan: `clinic_subscriptions:read` (listar/consultar el historial) usa `GET /authorization/check`; `clinic_subscriptions:charge` (disparar el cobro) usa `GET /authorization/me` (una sola llamada, informa `tenant_id` para compararlo con el que reporta Clínicas). No exige enmendar la constitución (research R1 del plan original, sin cambios). |
| IX. Integraciones con otros APIs de MailySoft | **Es el principio que motivó el rediseño**: la asignación clínica↔plan↔ciclo pertenece a Clínicas y se consulta, nunca se guarda aquí (como ya hace este servicio con `clinics_count`, spec 001). El contrato nuevo se documenta en `contracts/clinics-api-integration.md` (ampliación) con su simulación; el de Pagos en `contracts/payments-api-integration.md`. El cobro, al ser una escritura, falla cerrado ante cualquiera de las tres dependencias (Clínicas, Usuarios, Pagos): no es una degradación como la de `clinics_count` en la spec 001 (ese es un dato complementario de una lectura; esto es el núcleo de una escritura). |

Ninguna desviación exige una entrada en «Complexity Tracking».

## Project Structure

### Documentation (this feature)

```text
specs/010-cobro-real-suscripciones/
├── plan.md                                  # This file
├── research.md                              # Phase 0 output
├── data-model.md                            # Phase 1 output
├── quickstart.md                            # Phase 1 output
├── contracts/
│   ├── openapi-clinic-subscriptions.yaml    # Contrato publicado (3 operaciones)
│   ├── permission-matrix.md
│   ├── users-api-integration.md             # check (existente) + me (nuevo, para charge)
│   ├── clinics-api-integration.md           # NUEVO: ampliación del contrato de Clínicas
│   ├── payments-api-integration.md          # Contrato consumido: POST/GET de mailySoft-pagos
│   ├── error-catalog.md
│   ├── database-schema.sql
│   └── e2e-stubs.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── models/
│   └── clinic_subscription_charge.py        # NUEVO: único modelo ORM de esta spec
├── dtos/
│   └── clinic_subscription.py               # NUEVO: ChargeCreate/ChargeRead
├── integrations/
│   ├── clinics_api.py                       # AMPLIADO: get_clinic_subscription(...)
│   ├── payments_api.py                      # NUEVO: PaymentsApiClient
│   ├── users_api.py                         # AMPLIADO: get_current_access (para /me)
│   └── errors.py                            # AMPLIADO: ClinicsApiNotFound, Payments*
├── repositories/
│   └── clinic_subscription_charge_repository.py   # NUEVO
├── services/
│   ├── clinic_subscription_service.py       # NUEVO: cobrar, listar, consultar, sincronizar
│   └── authorization_service.py             # AMPLIADO: require_as_caller (usa /me)
├── routers/
│   └── clinic_subscriptions.py              # NUEVO: /api/v1/clinic-subscriptions/{id}/charges
├── security.py                              # AMPLIADO
├── exceptions.py / messages.py              # AMPLIADOS

alembic/versions/
└── 0008_clinic_subscription_charges.py      # NUEVO

tests/
├── contract/
│   ├── test_clinic_subscriptions_api.py
│   ├── test_clinic_subscriptions_access_control.py
│   ├── test_clinic_subscriptions_openapi.py
│   ├── test_payments_api_client.py
│   └── test_clinics_api_client.py            # AMPLIADO: get_clinic_subscription
├── integration/
│   ├── test_clinic_subscription_charge_repository.py
│   └── test_clinic_subscriptions_migration.py
├── unit/
│   └── test_clinic_subscription_service.py
└── stubs/
    ├── payments_api/app.py                   # NUEVO
    └── clinics_api/app.py                    # AMPLIADO: get_clinic_subscription
```

**Structure Decision**: Un solo proyecto (`src/` en capas, Principio I); sin frontend ni un segundo
servicio propio. Más pequeño que la versión anterior de este plan: sin `ClinicSubscription`,
`ClinicSubscriptionStatus`, su Repository de CRUD ni sus 4 operaciones de administración (ahora
responsabilidad de Clínicas).

## Complexity Tracking

*Sin violaciones que justificar.*

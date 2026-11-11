# Implementation Plan: Cobro Real de Suscripciones de Clínicas

**Branch**: `006-cobro-real-suscripciones` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-cobro-real-suscripciones/spec.md`

## Summary

Añadir el dominio «suscripción de clínica» (`clinic_subscriptions`, con su historial de cobros
`clinic_subscription_charges`), que liga una clínica (`tenant_id`) a un plan del catálogo existente
(`subscriptions`) con un ciclo de cobro, y la operación que cobra ese plan contra Mercado Pago a
través de `mailySoft-pagos` (`POST /api/v1/payments`), resolviendo su estatus por consulta a
`GET /api/v1/payments/{id}` (sin webhook de Pagos hacia este servicio). Dos permisos nuevos con
audiencias distintas: `clinic_subscriptions:write/update/delete/read` (quien administra la
plataforma, sin `tenant_id` propio) y `clinic_subscriptions:charge` (una persona de la propia
clínica, cuyo `tenant_id` Pagos necesita para resolver a quién cobra). El cobro periódico automático
queda fuera de esta especificación (FR-029).

## Technical Context

**Language/Version**: Python 3.14 (constitución, Stack Tecnológico)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0 async (asyncpg), Pydantic v2, httpx (cliente de
Pagos y de Usuarios), Alembic

**Storage**: PostgreSQL 17 — dos tablas nuevas (`clinic_subscription_statuses`,
`clinic_subscriptions`, `clinic_subscription_charges`) sin tocar `subscriptions` ni
`subscription_statuses`

**Testing**: pytest + pytest-asyncio; Repositories contra PostgreSQL 17 real (Docker); clientes de
Pagos y de Usuarios sustituidos por dobles de prueba (unit) y por simulaciones HTTP propias
(contract/e2e, igual que `tests/stubs/users_api` y `tests/stubs/clinics_api`)

**Target Platform**: Linux server (contenedor Docker), igual que el resto del servicio

**Project Type**: Servicio web (API REST, un solo proyecto `src/` en capas — Principio I)

**Performance Goals**: Sin objetivo propio distinto del resto del servicio; cada operación hace a lo
sumo una llamada a Pagos y una a Usuarios (Principio VIII/IX: nunca en paralelo con la escritura
local de un cobro, para no guardar un estado que Pagos no confirmó)

**Constraints**: Dinero en enteros (centavos) en la llamada a Pagos, aunque se guarde como
`NUMERIC`/`Decimal` en las tablas propias (Principio VI); ninguna llamada a Pagos o a Usuarios se
reintenta automáticamente (Principio IX); el `tenant_id` de un pago nunca se envía en el cuerpo a
Pagos (Principio X de Pagos, fuera del control de este repositorio)

**Scale/Scope**: 3 recursos nuevos bajo `/api/v1/clinic-subscriptions` (CRUD + cancelar + cobrar) y 2
de solo lectura de su historial de cobros; magnitud comparable a la spec 001 (6 operaciones) más la
integración nueva con Pagos

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumplimiento |
|---|---|
| I. Arquitectura en capas | `src/routers/clinic_subscriptions.py` → `src/services/clinic_subscription_service.py` → `src/repositories/clinic_subscription_repository.py` → `src/database/`; el cliente nuevo de Pagos vive en `src/integrations/payments_api.py`, solo lo invoca el Service (igual que `clinics_api.py` y `users_api.py`). Sin desviación. |
| II. Modelos ORM vs DTOs | `src/models/clinic_subscription.py` y `src/models/clinic_subscription_charge.py` (ORM); `src/dtos/clinic_subscription.py` (DTOs de entrada/salida). Sin desviación. |
| III. Asincronía de extremo a extremo | Cliente de Pagos con `httpx.AsyncClient` y `asyncio.timeout`, mismo patrón que `UsersApiClient`/`ClinicsApiClient`. Sin desviación. |
| IV. Contratos OpenAPI | Nuevas operaciones documentadas con `x-required-permission`, paginadas (listar suscripciones de clínica y listar cobros); se amplía `openapi.json` del servicio. Sin desviación. |
| V. Pruebas con pytest | Unitarias de `ClinicSubscriptionService` con `PaymentsApiClient`/`UsersApiClient` sustituidos por dobles; contrato de cada operación; Repositories contra PostgreSQL 17 real; `test_permission_coverage` ampliado. Sin desviación. |
| VI. Esquema versionado con Alembic | Migración nueva (`0005_clinic_subscriptions.py` o el siguiente número libre), reversible; `project-definition/DATA_SCHEMA.md` actualizado con `-- [spec 006-cobro-real-suscripciones]`; dinero en `NUMERIC`, cómputo en centavos solo al llamar a Pagos. Sin desviación. |
| VII. Idioma | Identificadores, campos y códigos de error en inglés; mensajes y documentación en español. Sin desviación. |
| VIII. Control de acceso delegado | **Desviación documentada, no de constitución**: casi todas las operaciones siguen usando `GET /api/v1/authorization/check` (una consulta, el permiso exacto); la operación de **cobrar** usa en su lugar `GET /api/v1/authorization/me` (también una sola consulta por petición, sin caché) porque, a diferencia de `check`, informa el `tenant_id` de quien llama, que esta operación necesita para decidir si coincide con el de la suscripción de clínica (FR-030) y para reenviar el token a Pagos. Sigue siendo **una sola llamada a Usuarios por petición** (el requisito literal de la constitución); `/me` ya es un contrato publicado de `mailySoft-usuarios` (spec 009, ampliado por la 019) y ya lo consumen `mailySoft-agenda` y `mailySoft-pagos`, así que no hace falta enmendar la constitución de este repositorio (no introduce una tecnología ni un patrón nuevo, solo una operación distinta del mismo API). Se documenta en `contracts/users-api-integration.md` junto al contrato de `check` ya existente. |
| IX. Integraciones con otros APIs de MailySoft | Contrato de Pagos documentado en `contracts/payments-api-integration.md` con su simulación (`tests/stubs/payments_api`); direcciones y tiempos de espera en variables de entorno (`PAGOS_API_BASE_URL`, `PAGOS_API_TIMEOUT_SECONDS`); fallas de Pagos no filtran su cuerpo ni sus cabeceras. El cobro, al ser una escritura, **falla cerrado** si Pagos no responde (no es una dependencia «solo complementaria» como el conteo de clínicas): es coherente con el principio, que reserva la degradación a datos que no son el núcleo de la operación. |

Ninguna desviación exige una entrada en «Complexity Tracking»: usar `/authorization/me` para una sola
operación es un contrato ya existente y publicado, consumido con las mismas reglas (una consulta,
sin caché, falla cerrado) que `/authorization/check`.

## Project Structure

### Documentation (this feature)

```text
specs/006-cobro-real-suscripciones/
├── plan.md                                  # This file
├── research.md                              # Phase 0 output
├── data-model.md                            # Phase 1 output
├── quickstart.md                            # Phase 1 output
├── contracts/
│   ├── openapi-clinic-subscriptions.yaml    # Contrato publicado (nuevas operaciones)
│   ├── permission-matrix.md                 # Matriz operación → permiso de esta spec
│   ├── users-api-integration.md             # Contrato consumido: check (ya existente) + me (nuevo)
│   ├── payments-api-integration.md          # Contrato consumido: POST/GET de mailySoft-pagos
│   ├── error-catalog.md                     # Códigos de error nuevos de esta spec
│   ├── database-schema.sql                  # DDL de referencia (como en la spec 001)
│   └── e2e-stubs.md                         # Simulaciones de Usuarios (ampliada) y de Pagos (nueva)
├── checklists/
│   └── requirements.md
└── tasks.md                                 # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── clinic_subscription.py              # NUEVO: ClinicSubscription (ORM)
│   ├── clinic_subscription_charge.py       # NUEVO: ClinicSubscriptionCharge (ORM)
│   └── clinic_subscription_status.py       # NUEVO: catálogo (Activa/con cobro pendiente/Cancelada)
├── dtos/
│   └── clinic_subscription.py              # NUEVO: Create/Read/ChargeRead/… (Pydantic v2)
├── integrations/
│   ├── payments_api.py                     # NUEVO: PaymentsApiClient (create_payment, get_payment)
│   ├── users_api.py                        # AMPLIADO: get_current_access (para /me)
│   └── errors.py                           # AMPLIADO: PaymentsApiUnavailable, PaymentsApiRejectedToken
├── repositories/
│   └── clinic_subscription_repository.py   # NUEVO
├── services/
│   ├── clinic_subscription_service.py      # NUEVO: asignar, listar, consultar, cancelar, cobrar, sincronizar
│   └── authorization_service.py            # AMPLIADO: require_as_caller (usa /me, devuelve CallerAccess)
├── routers/
│   └── clinic_subscriptions.py             # NUEVO: /api/v1/clinic-subscriptions
├── security.py                              # AMPLIADO: permisos nuevos + dependencia basada en /me
├── exceptions.py                            # AMPLIADO
└── messages.py                              # AMPLIADO

alembic/versions/
└── 0005_clinic_subscriptions.py            # NUEVO (número exacto: el siguiente libre tras 0004)

tests/
├── contract/
│   ├── test_clinic_subscriptions_api.py
│   ├── test_clinic_subscriptions_access_control.py
│   ├── test_clinic_subscriptions_openapi.py
│   └── test_payments_api_client.py          # (junto a test_users_api_client.py, test_clinics_api_client.py)
├── integration/
│   ├── test_clinic_subscription_repository.py
│   └── test_clinic_subscriptions_migration.py
├── unit/
│   ├── test_clinic_subscription_service.py
│   └── test_clinic_subscription_dtos.py
└── stubs/
    └── payments_api/
        └── app.py                            # NUEVO, junto a tests/stubs/users_api (ampliado) y clinics_api
```

**Structure Decision**: Un solo proyecto (`src/` en capas, Principio I); no hay frontend ni un
segundo servicio que esta especificación introduzca. Cada capa nueva sigue exactamente los mismos
directorios y el mismo patrón de nombres que `subscriptions` (spec 001) y las integraciones ya
existentes (`clinics_api.py`, `users_api.py`), por lo que no se introduce ninguna carpeta ni patrón
nuevo de organización.

## Complexity Tracking

*Sin violaciones que justificar: ver la fila del Principio VIII en la tabla anterior, que explica por
qué usar `/authorization/me` para la operación de cobro no es una desviación de la constitución.*

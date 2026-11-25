# Implementation Plan: Historial paginado de cobros de la suscripción

**Branch**: `012-payment-history-charges` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-payment-history-charges/spec.md`

## Summary

Una operación de lectura nueva, `GET /api/v1/subscription-periods/{organization_id}/charges`, que publica
el historial paginado de cobros (`SubscriptionCharge`, spec 010) de una organización: del más reciente al
más antiguo, con el mismo control de acceso (Dueño, permiso `subscription_periods:read`) que ya exige el
periodo completo. Copia el patrón ya resuelto de `clinic-subscriptions` (Router → Service → Repository,
`offset`/`limit` con un conteo aparte), con dos ajustes que pidió el Frontend: `page`/`page_size` como
parámetros de consulta y la paginación en el cuerpo de la respuesta, no en un encabezado ([research](research.md)
R1). No reconcilia con Pagos ni crea el periodo si falta (R2, R3): es una lectura simple de lo que ya está
guardado. Sin migración, sin permiso nuevo (R4, R5).

## Technical Context

**Language/Version**: Python 3.14+ (el entorno de desarrollo ejecuta 3.15.2)

**Primary Dependencies**: las del proyecto, sin dependencias nuevas (FastAPI, Pydantic v2, SQLAlchemy 2.0
async). Desarrollo: pytest, pytest-asyncio; herramienta aparte: Newman.

**Storage**: PostgreSQL 17, sin cambios (la tabla `subscription_charges` de la migración 0008 ya tiene
todo lo que esta feature publica).

**Testing**: pytest + pytest-asyncio + httpx. Nivel rápido: DTO (presencia condicional de campos), Service
con dobles (el permiso ya existente, sin reconciliación, paginación) y Repository con dobles.
Nivel lento: Repository contra PostgreSQL 17 real (orden, paginación, aislamiento por organización),
contrato HTTP con la aplicación real y las tres simulaciones, OpenAPI y cobertura de permisos. Postman/
Newman: dos solicitudes nuevas en la colección ya existente de los periodos (una página vacía y una con
un cobro aplicado y paginación). `/speckit-implement` corre solo el nivel rápido.

**Target Platform**: contenedor Linux (Docker Compose, imagen `python:3.14-slim`), igual que el resto del
servicio.

**Project Type**: web-service

**Performance Goals**: sin efecto medible sobre las otras dos operaciones; una lectura paginada más, del
mismo tamaño que el listado de cobros de clínicas ya existente.

**Constraints**: sin reconciliación con Pagos (R2); sin crear el registro del periodo (R3); la paginación
va en el cuerpo, nunca en un encabezado (R1); nunca expone `payment_id`, `attempt` ni `resolved_at`
(FR-005).

**Scale/Scope**: 1 operación nueva; 4 módulos de `src/` modificados de forma aditiva
(`dtos/subscription_period.py`, `repositories/subscription_period_repository.py`,
`services/subscription_period_service.py`, `routers/subscription_periods.py`); 2 archivos de prueba
extendidos con dobles (`tests/billing_support.py`) más los archivos de prueba unitaria, de integración y
de contrato ya existentes del router; 1 colección de Postman extendida; sin documentos de despliegue
nuevos (sin variable de entorno ni migración).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ DTO en `src/dtos/`, lectura en el Repository, el Service solo comprueba la organización y delega; el Router no importa `src.models` (ajuste tras la primera corrida de `test_layering.py`, ver «Ajustes a las pruebas existentes») |
| II. Modelos ≠ DTOs | ✅ | ✅ `SubscriptionChargeRead`/`SubscriptionChargesPageRead` nuevos; el Router convierte explícitamente, sin anotar el tipo ORM (mismo patrón que `clinic_subscriptions.py`) |
| III. Asincronía | ✅ | ✅ La lectura es una consulta async más del Repository ya existente |
| IV. OpenAPI y REST | ✅ | ✅ Operación nueva documentada con `response_model`, `x-required-permission`, ejemplos y los siete códigos de respuesta; listado paginado (sin excepción del Principio IV) |
| V. Pruebas pytest | ✅ | ✅ DTO, Service y Repository con dobles (rápido); Repository, contrato HTTP, OpenAPI y cobertura de permisos contra PostgreSQL real (lento); Postman actualizado en la misma feature |
| VI. Migraciones Alembic | ✅ | ✅ No aplica: sin cambios en el esquema (FR-013 de la spec, R4) |
| VII. Idioma | ✅ | ✅ Identificadores y mensajes de error en inglés en el código; documentos, descripciones de OpenAPI y mensajes de negocio en español |
| VIII. Control de acceso delegado | ✅ | ✅ Mismo permiso ya existente, declarado con `protected(...)`; la prueba de cobertura se amplía, no se relaja |
| IX. Integraciones | ✅ | ✅ Sin integración nueva: usa el mismo cliente de Clínicas ya inyectado en el Service |

Sin desviaciones: «Complexity Tracking» queda vacío.

## Ajustes a las pruebas existentes

| Archivo | Ajuste | Por qué |
|---|---|---|
| `tests/billing_support.py` | `FakePeriodRepository.list_charges(...)` (mismo orden y paginación que el Repository real); `BillingApi.list_charges(...)` (la petición HTTP) | El doble del Service y el ayudante de las pruebas de contrato necesitan la operación nueva |
| `tests/contract/test_permission_coverage.py` | `list_subscription_charges` agregado a `EXPECTED_PERMISSIONS` y a `REQUESTS` | La prueba de cobertura es global: recorre toda operación protegida |
| `tests/contract/test_subscription_periods_access_control.py` | `"charges"` agregado a `OPERATIONS`/`PERMISSION_OF`/`call(...)` | Las mismas comprobaciones de control de acceso de las otras dos operaciones aplican también a esta (mismo patrón, sin duplicar código) |
| `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json` | 2 solicitudes nuevas (`list_subscription_charges: …`) en las carpetas «1. Consulta» y «3. Pago aprobado» | G2 (cobertura de operaciones) y el Principio V exigen que la colección se actualice en el mismo cambio que cambia la API |
| `tests/contract/test_periods_postman_collection.py` | `OPERATIONS`, `REQUESTS_PER_FOLDER` y el nombre de `test_g2_...` actualizados | Reflejan la operación y las solicitudes nuevas |

## Documentación y despliegue

- Sin cambios: `.env.example`, `README.md`, `docker-compose.yml` (sin variable de entorno nueva).
- `project-definition/DATA_SCHEMA.md`: sin cambios (sin cambio de esquema, R4).

## Project Structure

### Documentation (this feature)

```text
specs/012-payment-history-charges/
├── plan.md                        # Este archivo
├── research.md                    # Fase 0: decisiones R1-R7
├── data-model.md                  # Fase 1: los dos DTOs y el orden
├── quickstart.md                  # Fase 1: cómo comprobarlo
├── contracts/
│   ├── charges-operation.md       # El contrato publicado (respuesta al pedido del Frontend)
│   └── permission-matrix.md       # La fila nueva de la matriz operación → permiso
├── checklists/
│   └── requirements.md            # Calidad de la especificación
└── tasks.md                       # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── dtos/
│   └── subscription_period.py           # SubscriptionChargeRead, SubscriptionChargesPageRead
├── repositories/
│   └── subscription_period_repository.py # list_charges(...)
├── services/
│   └── subscription_period_service.py    # list_charges(...) (solo comprueba la organización)
└── routers/
    └── subscription_periods.py           # GET /{organization_id}/charges

tests/
├── billing_support.py                     # FakePeriodRepository.list_charges, BillingApi.list_charges
├── unit/
│   ├── test_subscription_period_dtos.py          # presencia condicional de campos
│   └── test_subscription_period_service.py       # permiso, sin reconciliación, paginación, aislamiento
├── integration/
│   └── test_subscription_period_repository.py    # orden, paginación, aislamiento por organización (real)
└── contract/
    ├── test_subscription_periods_api.py          # los tres estados, paginación, control de acceso (real)
    ├── test_subscription_periods_access_control.py  # "charges" como tercera operación del mismo patrón
    ├── test_subscription_periods_openapi.py      # el contrato publicado
    └── test_permission_coverage.py               # la matriz global
```

**Structure Decision**: el proyecto único de siempre (`src/` y `tests/`), sin carpetas nuevas.

## Trazabilidad de requisitos

| Requisito | Dónde se cumple | Dónde se prueba |
|---|---|---|
| FR-001, FR-008, FR-009, FR-010, FR-011 | `routers/subscription_periods.py` (`list_subscription_charges`), `repositories/subscription_period_repository.py` (`list_charges`) | `test_subscription_period_repository.py`, `test_subscription_periods_api.py` |
| FR-002, FR-003, FR-004, FR-005 | `dtos/subscription_period.py` (`SubscriptionChargeRead`) | `test_subscription_period_dtos.py`, `test_subscription_periods_openapi.py` |
| FR-006 | `services/subscription_period_service.py` (`list_charges`, reutiliza `_read_organization`), `security.py` (`SUBSCRIPTION_PERIODS_READ`) | `test_subscription_period_service.py`, `test_subscription_periods_access_control.py`, `test_permission_coverage.py` |
| FR-007 | `services/subscription_period_service.py` (no llama a `_prepare`) | `test_subscription_period_service.py`, `test_subscription_periods_api.py` |
| FR-012 | `routers/subscription_periods.py` (`Cache-Control: no-store`) | `test_subscription_periods_api.py`, `test_subscription_periods_openapi.py` |
| FR-013 | — (sin migración, sin permiso nuevo) | Revisión; `test_permission_coverage.py` confirma que no hace falta ninguno |

## Complexity Tracking

Sin desviaciones de la constitución que justificar.

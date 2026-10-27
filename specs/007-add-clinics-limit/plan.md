# Implementation Plan: Límite de clínicas por suscripción

**Branch**: `007-add-clinics-limit` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-add-clinics-limit/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`006-add-subscription-type` ya está implementada en `main`. Esta feature agrega un quinto límite
de la clínica, `clinics_limit`, junto a los cuatro que ya existen (consultorios, doctores,
asistentes, pacientes nuevos al año). Su rango permitido depende del tipo de la suscripción
(ya existente, 006): exactamente `1` y fijo para siempre si es Individual; de `1` a `100` y
modificable si no lo es.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Representación (R1)**: una columna simple (`int4 NOT NULL`), no un catálogo — a diferencia de
  `subscription_type_id`, aquí no hay un conjunto cerrado de valores con nombre.
- **Validación en dos capas, sin ninguna consulta nueva (R2, R3)**: el rango base (1–100) es un
  `Field` de Pydantic en `SubscriptionCreate`/`SubscriptionUpdate`, igual que los otros cuatro
  límites. La restricción "exactamente 1 si es Individual" al crear es un `model_validator(mode=
  "after")` nuevo en `SubscriptionCreate` (cruza `clinics_limit` con `subscription_type_id`, ambos
  ya validados). La inmutabilidad al actualizar una Individual no puede vivir en el DTO (no conoce
  el tipo vigente): `SubscriptionService.update()` la comprueba leyendo la suscripción primero,
  reutilizando la misma lectura que ya dispara `module_keys` cuando ambos llegan juntos. Sin
  carrera posible: `subscription_type_id` es fijo para siempre (006), así que el tipo leído antes
  de escribir es el mismo que tendrá la fila después.
- **Ningún código de error nuevo (R4)**: ambas reglas se presentan como `validation_error` (422)
  con un elemento de `errors[]`, igual forma que cualquier campo inválido. La de actualización
  necesita una excepción nueva, `SubscriptionDataError` (versión para suscripciones de
  `MonitoredComponentDataError`, ya existente en `src/exceptions.py` desde la 005); se sube
  `field_error` a la clase base `AppError` para que ambas la compartan.
- **Datos existentes (R5)**: la migración agrega la columna con `DEFAULT 1`, válido para cualquier
  fila existente (único valor posible si ya es Individual; el más bajo del rango si no lo es). A
  diferencia de 006, esta feature no necesita ningún script de reconciliación fuera de Alembic.
- **Restricción `CHECK` de dos columnas (R6)**: respaldo defensivo en la base de datos, igual
  criterio que los otros cuatro límites; por construcción nunca debería dispararse a través de la
  API (Pydantic y el Service ya lo garantizan).
- **Contrato**: `SubscriptionCreate` gana un campo obligatorio nuevo y `SubscriptionRead` gana un
  campo más (cambio incompatible de forma); `VERSION` sube a `4.0.0` (R7).

## Technical Context

**Language/Version**: Python 3.14+ (sin cambios)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, uvicorn,
httpx. Sin dependencias nuevas.

**Storage**: PostgreSQL 17; una migración nueva (`0006`) que agrega `subscriptions.clinics_limit`
(`int4 NOT NULL DEFAULT 1`) y una restricción `CHECK` de dos columnas.

**Testing**: pytest + pytest-asyncio + httpx, igual que `001`/`004`/`006`. `tests/unit/fakes.py`
(`FakeSubscriptionRepository`) gana `clinics_limit` en `add`/`create`/`update`.

**Target Platform**: igual que `006` (contenedor Linux, Docker Compose). Sin componentes nuevos de
despliegue (a diferencia de 006, que sí agregó un script de reconciliación).

**Project Type**: web-service (ampliación de una feature existente)

**Performance Goals**: sin cambios respecto a `006` (SC-001 de 001). La comprobación de
inmutabilidad en `update()` agrega, como máximo, una lectura que ya existía para otro caso
(`module_keys`); nunca dos lecturas separadas cuando ambos campos llegan juntos.

**Constraints**: las mismas de `006`, sin ninguna nueva (no hay integración externa involucrada en
esta feature: `clinics_limit` no se valida contra la API de clínicas, FR-010).

**Scale/Scope**: mismas 6 operaciones y los mismos 4 permisos externos ya usados; ningún permiso
externo adicional. Una migración nueva; una columna nueva; un `CHECK` nuevo; **cero** códigos de
error nuevos (a diferencia de 006, que agregó uno); una clase de excepción nueva, genérica,
reutilizando un mecanismo que ya existe (`MonitoredComponentDataError`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas | ✅ Solo se tocan capas ya existentes, sin paquetes nuevos | ✅ Sin Routers, Services ni Repositories nuevos: `SubscriptionService.update()` se extiende, no se duplica; `SubscriptionDataError` vive en `src/exceptions.py`, igual capa que `AppError`/`MonitoredComponentDataError` |
| II. Modelos ≠ DTOs | ✅ | ✅ `clinics_limit` es una columna del modelo ORM y, por separado, un campo de los tres DTOs; la regla cruzada de `SubscriptionCreate` compara dos campos del propio DTO (sin tocar el modelo); el DTO sigue sin importar constantes de `src/models/` (el `1` de Individual se escribe literal, igual que ya hace `SubscriptionStatusChange.status_id`) |
| III. Asincronía | ✅ | ✅ La lectura que decide la inmutabilidad en `update()` ya era async (reutiliza `get_current_by_id`, ya existente); no se agrega ninguna llamada nueva a otro sistema |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) actualizado (`version: 4.0.0`, cambio incompatible declarado); `clinics_limit` documentado en los tres esquemas y en los ejemplos 422 de `create_subscription`/`update_subscription` |
| V. Pruebas pytest | ✅ | ✅ Mismo patrón que los otros cuatro límites (DTO, Service, Repository, contrato) más un caso nuevo de inmutabilidad condicionada al tipo en `test_subscription_service.py`/`test_subscriptions_api.py` |
| VI. Migraciones Alembic | ✅ | ✅ `0006_add_clinics_limit` (nueva, reversible); `project-definition/DATA_SCHEMA.md` y `create_database.sql` ya actualizados con la columna y el `CHECK` nuevos (incluido `alembic_version` → `'0006'`); ninguna migración llama a otro servicio |
| VII. Idioma | ✅ | ✅ `clinics_limit` en inglés (identificador); sus mensajes, en español |
| VIII. Control de acceso delegado | ✅ Sin cambios | ✅ Sin cambios: mismos 4 permisos, sin ninguno nuevo para este campo |
| IX. Integraciones | ✅ Sin cambios | ✅ `clinics_limit` no se valida contra la API de clínicas (FR-010): es informativo, igual que los otros cuatro límites |
| Stack obligatorio | ✅ | ✅ Sin dependencias nuevas |
| Flujo y puertas de calidad | ✅ | ✅ Constitution Check incluido |

**Resultado**: PASS contra los principios I a IX, sin necesidad de enmendar la constitución.

## Project Structure

### Documentation (this feature)

```text
specs/007-add-clinics-limit/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: R1–R7
├── data-model.md                        # Fase 1: columna clinics_limit, CHECK, DTOs
├── quickstart.md                        # Fase 1: guía de validación (delta sobre 006)
├── contracts/
│   ├── openapi-subscriptions.yaml       # Fase 1: contrato HTTP completo actualizado (reemplaza al de 006)
│   ├── permission-matrix.md             # Fase 1: sin permisos nuevos
│   ├── error-catalog.md                 # Fase 1: CERO códigos nuevos (delta sobre 006)
│   └── database-schema.sql              # Fase 1: esquema completo, incluida la columna y el CHECK nuevos
│   # users-api-integration.md, clinics-api-integration.md, e2e-stubs.md: SIN CAMBIOS (ver 001)
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks; aún no existe)
```

### Source Code (repository root)

Todo lo de abajo **ya existe** (de `001`, `004`, `005` y `006`), salvo lo genuinamente nuevo
(`NUEVO`) o lo que esta feature modifica (`MODIFICA`).

```text
src/
├── __init__.py                   # MODIFICA: VERSION "4.0.0"
├── messages.py                   # MODIFICA: + SUBSCRIPTION_CLINICS_LIMIT_INVALID_MESSAGE,
│                                  #   SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE,
│                                  #   SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE; + 2 entradas
│                                  #   ("clinics_limit", "required"/"invalid") en
│                                  #   VALIDATION_MESSAGES["subscriptions"]
├── exceptions.py                 # MODIFICA: sube `field_error` de MonitoredComponentDataError a
│                                  #   AppError (clase base); + SubscriptionDataError(errors),
│                                  #   code=VALIDATION_ERROR, status_code=422 (sin ErrorCode nuevo)
├── routers/
│   └── subscriptions.py          # MODIFICA: ejemplos de documentación con clinics_limit (crear,
│                                  #   leer, actualizar); nuevos ejemplos 422 de rango y de
│                                  #   inmutabilidad en Individual
├── services/
│   └── subscription_service.py   # MODIFICA: update() lee la suscripción primero también cuando
│                                  #   "clinics_limit" está en los campos enviados (reutiliza la
│                                  #   lectura si module_keys también vino); si el tipo vigente es
│                                  #   Individual, lanza SubscriptionDataError antes de llamar al
│                                  #   repositorio; create() sin cambios (la regla de creación ya
│                                  #   la resuelve el DTO)
├── models/
│   └── subscription.py           # MODIFICA: + clinics_limit: Mapped[int] (server_default="1",
│                                  #   igual criterio que subscription_type_id); + CheckConstraint
│                                  #   de dos columnas, nombre "subscriptions_clinics_limit_check"
└── dtos/
    └── subscription.py           # MODIFICA: SubscriptionRead gana clinics_limit: int;
                                   #   SubscriptionCreate gana clinics_limit: int (Field ge=1,
                                   #   le=100) + model_validator(mode="after") que lo cruza con
                                   #   subscription_type_id; SubscriptionUpdate gana
                                   #   clinics_limit: int | None (mismo Field, + validador
                                   #   "no nulo" como los otros cuatro límites)

alembic/versions/
└── 0006_add_clinics_limit.py      # NUEVO: agrega la columna (server_default="1") y el CHECK;
                                    #   downgrade() los quita en orden inverso

tests/
├── unit/
│   ├── fakes.py                            # MODIFICA: FakeSubscriptionRepository.add/create/
│   │                                       #   update ganan clinics_limit: int = 1
│   ├── test_subscription_dtos.py          # MODIFICA: + casos de clinics_limit (obligatorio,
│   │                                       #   rango 1–100, regla cruzada con el tipo al crear,
│   │                                       #   "no nulo" al actualizar)
│   └── test_subscription_service.py       # MODIFICA: + casos de inmutabilidad en Individual al
│                                            #   actualizar (con y sin otros campos válidos) y de
│                                            #   actualización permitida en una no Individual
├── integration/
│   ├── test_subscription_repository.py    # MODIFICA: create()/update() con clinics_limit
│   ├── test_subscriptions_constraints.py  # MODIFICA: + casos del CHECK de dos columnas (23514)
│   └── test_migrations.py                 # MODIFICA: + el DEFAULT de clinics_limit se prueba
│                                            #   igual que el de subscription_type_id en 006
└── contract/
    ├── test_subscriptions_api.py          # MODIFICA: + casos de creación, lectura y actualización
    │                                       #   de clinics_limit (ver quickstart.md)
    └── test_openapi_contract.py           # sin cambios de fondo (sigue contando 18 códigos)

tests/postman/collections/
└── MailySoft-System-Suscripciones.postman_collection.json   # MODIFICA: cuerpos de ejemplo con
                                                               # clinics_limit; nuevos casos 422

project-definition/
├── DATA_SCHEMA.md                # MODIFICA: columna y CHECK nuevos, marcados [spec 007-add-clinics-limit]
└── create_database.sql           # MODIFICA: igual contenido que contracts/database-schema.sql
```

**Structure Decision**: ninguna capa ni archivo nuevo de aplicación (a diferencia de `006`, que
agregó dos archivos por el catálogo nuevo): esta feature extiende archivos que ya existen, con una
sola excepción real — `SubscriptionDataError` en `src/exceptions.py`, que reutiliza (subiéndolo a
la clase base) un mecanismo que `MonitoredComponentDataError` ya probó en `005-health-monitoring`
para el mismo problema ("el Service rechaza un campo con la forma de un error de validación").

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación. El único elemento "nuevo" (`SubscriptionDataError`) es la generalización de una
clase que ya existe (`MonitoredComponentDataError`, 005) a una clase base compartida; no introduce
ninguna estructura, capa ni patrón que la constitución no haya contemplado ya.

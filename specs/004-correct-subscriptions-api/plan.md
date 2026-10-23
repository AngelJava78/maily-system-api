# Implementation Plan: Corrección del modelo de datos de la API de Suscripciones

**Branch**: `004-correct-subscriptions-api` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-correct-subscriptions-api/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`001-subscriptions-api` ya está implementada en `main` (6 operaciones REST bajo `/api/v1/subscriptions`),
pero con un modelo de datos mínimo: nombre, descripción, precio mensual y una lista de texto libre
(`features`) que mezcla módulos, límites y otras funcionalidades. Esta feature **corrige ese modelo**
para que coincida con el mockup del Backoffice, sin tocar las 6 operaciones ni el control de acceso
que ya funcionan. Añade: precio anual, días de prueba, autoconsumo, cuatro límites de la clínica
estructurados, y separa «módulos incluidos» (un catálogo **externo**, propiedad de la API de usuarios)
de «otras funcionalidades» (la antigua `features`, renombrada y acotada a lo que no es un módulo).

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Módulos (US1, US3, US5)**: el catálogo de los 9 módulos de clínica **no se crea aquí**: se
  consulta en la API de usuarios (`GET /api/v1/modules?type_id=2`, feature `013-modules-permissions-catalogs`
  de `mailySoft-usuarios`, **hoy sin comprometer a git ni desplegada**). Cada módulo se referencia por
  su `key` (slug estable que esa API nunca cambia tras crear el módulo), no por su `id` numérico
  (opaco) ni por su nombre. `UsersApiClient` gana un método `list_clinic_module_keys(token)`; la
  dependencia y el «siempre incluido» (Pacientes) son reglas **locales** de este servicio
  (`src/clinic_modules.py`, sin tabla ni llamada de red), porque la API de usuarios no las modela.
  La API de usuarios solo se consulta por módulos **al crear o actualizar módulos**, nunca al listar o
  consultar (R5); si no responde, la operación se rechaza (`module_check_unavailable`, 503).
- **Datos nuevos**: una sola migración (`0003`) sobre la tabla `subscriptions` ya existente: renombra
  `features` → `other_features`; añade `annual_price numeric(10,2) NOT NULL`, `trial_days` (≥0, por
  defecto 0), `self_service boolean NOT NULL DEFAULT false`, `module_keys text[]` (siempre incluye
  `patients`, con `CHECK`) y los cuatro límites (`consulting_rooms_limit`, `doctors_limit`,
  `assistants_limit`, `new_patients_per_year_limit`, cada uno `NOT NULL CHECK (>= 0)`). Precio y
  límites son `NOT NULL` sin `DEFAULT`: la migración asume una tabla vacía (supuesto del spec), no
  añade backfill.
- **Precedencia de errores nuevos**: validación de Pydantic (422) → módulo no reconocido por la API
  de usuarios (`subscription_module_not_found`, 422) → módulo sin su prerrequisito
  (`subscription_module_prerequisite_missing`, 409, regla local, sin red) → existencia/conflictos de
  siempre (404/409). La API de usuarios solo se llama si la solicitud trae módulos además de
  Pacientes.
- **Sin cambios**: control de acceso (FR-001 a FR-005), integración con el API de clínicas, baja
  lógica, cambio de estatus, unicidad del nombre, CORS, advertencia de `http://`. Se reutilizan tal
  cual de `001-subscriptions-api`.
- **Contrato**: la forma de `SubscriptionRead/Create/Update` cambia de forma incompatible (nuevos
  campos obligatorios). La ruta sigue siendo `/api/v1` (sin consumidores reales que proteger, por
  supuesto del spec), pero el `version` de OpenAPI sube a `2.0.0` para que quede declarado (R10).

## Technical Context

**Language/Version**: Python 3.14+ (sin cambios respecto a `001-subscriptions-api`)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, uvicorn,
httpx. Sin dependencias nuevas: la consulta de módulos reutiliza `UsersApiClient` (mismo
`USERS_API_BASE_URL`, mismo `httpx.AsyncClient` compartido).

**Storage**: PostgreSQL 17; una migración nueva (`0003`) que modifica la tabla `subscriptions` ya
existente (renombra una columna, añade siete). Ningún catálogo nuevo en este servicio: el catálogo de
módulos vive en la base de datos de `mailySoft-usuarios`, no en la de este servicio (Principio IX).

**Testing**: pytest + pytest-asyncio + httpx, igual que `001-subscriptions-api`. El stub
`tests/stubs/users_api/app.py` gana `GET /api/v1/modules` (sembrado con los 9 módulos propuestos) y
un campo `operation` en `/__test__/faults` para fallar `check` o `modules` por separado.

**Target Platform**: Igual que `001-subscriptions-api` (contenedor Linux, Docker Compose); sin
servicios nuevos en `docker-compose.yml` (la API de usuarios simulada ya existe como stub).

**Project Type**: web-service (corrección de una feature existente, no un proyecto nuevo)

**Performance Goals**: el listado y la consulta individual **no** llaman a la API de usuarios por
módulos (Clarifications Q4): conservan el mismo presupuesto que `001-subscriptions-api` (< 2 s al
95 % para el catálogo completo, SC-001). Crear/actualizar módulos añade, como máximo, **una** llamada
adicional a la API de usuarios (nunca una por módulo).

**Constraints**: los mismos de `001-subscriptions-api` (falla cerrada en control de acceso, sin
caché de permisos, sin reintentos, el token no sigue redirecciones) más: la validación de módulos
también falla cerrada (si la API de usuarios no responde al validar módulos, no se crea ni se
actualiza nada); los límites de la clínica **no** fallan cerrado (bajarlos siempre se permite, FR-022).

**Scale/Scope**: mismas 6 operaciones y los mismos 2 permisos externos ya usados
(`subscriptions:*` sin cambios); **un permiso externo adicional que coordinar**: `modules:read` en la
API de usuarios, para el mismo rol que ya tiene `subscriptions:write`/`update` (si no lo tiene, la
validación de módulos falla siempre como «no disponible», aunque la API de usuarios esté sana). Una
migración nueva; siete columnas nuevas y una renombrada; tres códigos de error nuevos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas | ✅ Solo se tocan capas ya existentes | ✅ `src/clinic_modules.py` (constantes y reglas de dependencia puras, sin I/O) vive junto a `messages.py`/`security.py`, no en `models/` (no hay tabla) ni en `integrations/` (no habla HTTP). `UsersApiClient.list_clinic_module_keys` es la única función que llama a la API de usuarios por módulos; solo la invoca `SubscriptionService` |
| II. Modelos ≠ DTOs | ✅ | ✅ `SubscriptionRead/Create/Update` ganan los 7 campos nuevos como atributos del DTO, no como columnas expuestas directamente: `module_keys` en la respuesta es la columna propia (ya validada), nunca el resultado crudo de la API de usuarios |
| III. Asincronía | ✅ | ✅ `list_clinic_module_keys` es `async`, con el mismo `asyncio.timeout(USERS_API_TIMEOUT_SECONDS)` que `check_permission`; sin librerías nuevas ni bloqueantes |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) actualizado (OpenAPI 3.1, `version: 2.0.0`, mismas 6 operaciones); 3 respuestas nuevas (422, 409, 503) documentadas en `create_subscription` y `update_subscription`. El listado sigue sin paginar (excepción ya declarada en 001, sin cambios) |
| V. Pruebas pytest | ✅ | ✅ Mismo patrón: Service con dobles (`FakeUsersApi` gana `list_clinic_module_keys`), Repository contra PostgreSQL 17 real, endpoints por HTTP con el stub ampliado; **ninguna prueba llama a la API de usuarios real** |
| VI. Migraciones Alembic | ✅ | ✅ `0003_subscription_pricing_modules_limits`, reversible; `project-definition/DATA_SCHEMA.md` actualizado con marcas `-- [spec 004-correct-subscriptions-api]` sobre las reglas que cambian; precios y límites siguen en `NUMERIC`/`integer`, nunca `float` |
| VII. Idioma | ✅ | ✅ Identificadores nuevos en inglés (`annual_price`, `trial_days`, `self_service`, `module_keys`, `consulting_rooms_limit`, `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit`, `other_features`); mensajes y documentos en español |
| VIII. Control de acceso delegado | ✅ Sin cambios | ✅ Las 6 operaciones conservan exactamente su `protected(...)`; no se añade ni se quita ningún permiso propio. La llamada de módulos **reutiliza el token de la persona** (como ya hace `ClinicsApiClient`), no credenciales nuevas |
| IX. Integraciones | ✅ | ✅ El catálogo de módulos no se copia: solo se validan los `key` recibidos contra una consulta en vivo; no se guarda su nombre ni descripción (Clarifications Q4). La disponibilidad de las **lecturas** no depende de la API de usuarios por módulos (R5); la de las **escrituras de módulos**, sí, y falla cerrado (como ya hace eliminar con el API de clínicas) |
| Stack obligatorio | ✅ | ✅ Sin dependencias nuevas |
| Flujo y puertas de calidad | ✅ | ✅ Constitution Check incluido; matriz de permisos y colección de Postman se actualizan en el mismo cambio (contracts/) |

**Resultado**: PASS contra los principios I a IX, sin necesidad de enmendar la constitución y sin
desviaciones nuevas que justificar (la única desviación conocida, permiso antes que validación salvo
JSON ilegible, ya está aceptada desde `001-subscriptions-api` y no cambia aquí).

## Puntos a confirmar fuera de este repositorio (no bloquean el plan, pero bloquean producción)

1. **`mailySoft-usuarios`, feature `013-modules-permissions-catalogs`**: a la fecha de este plan
   (2026-10-23) existe su spec, su plan y la mayor parte de su código, pero **nada está comprometido a
   git** (`git status` la muestra como `Untracked`/`modified` sobre `main`, sin commit) ni desplegada.
   Debe terminarse (falta, al menos, la regla de compatibilidad de tipo rol↔módulo y el filtro de
   estatus en roles/permisos), comprometerse y desplegarse antes de integrar esta feature.
2. **Los 9 módulos de tipo Clínica**: hoy no existe ninguno en esa API (solo los 4 protegidos de tipo
   Sistema). Alguien con `modules:write` debe crearlos ahí, con las claves propuestas en
   [contracts/users-api-integration.md](contracts/users-api-integration.md) (`patients`, `scheduling`,
   `reminders`, `clinical_records`, `clinical_record_templates`, `prescriptions`, `finance`,
   `reports`, `billing`) — las claves son una **propuesta** de este repositorio, no un hecho
   garantizado; si quien las crea usa otras, hay que actualizar `src/clinic_modules.py`.
3. **Permiso `modules:read`**: el rol que tenga `subscriptions:write` y `subscriptions:update` en la
   API de usuarios también necesita `modules:read`, o la validación de módulos de esta API fallará
   siempre como «no disponible» (503) aunque la API de usuarios esté sana.
4. **API de clínicas**: sin cambios respecto a `001-subscriptions-api`; sigue pendiente de confirmar
   igual que entonces.

## Project Structure

### Documentation (this feature)

```text
specs/004-correct-subscriptions-api/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: decisiones nuevas (R1–R13) sobre la base de 001
├── data-model.md                        # Fase 1: columnas nuevas, DTOs y reglas de módulos
├── quickstart.md                        # Fase 1: guía de validación (delta sobre la de 001)
├── contracts/
│   ├── openapi-subscriptions.yaml       # Fase 1: contrato HTTP actualizado (reemplaza al de 001)
│   ├── permission-matrix.md             # Fase 1: sin cambios en permisos propios; nota de modules:read
│   ├── error-catalog.md                 # Fase 1: catálogo completo con los 3 códigos nuevos
│   ├── database-schema.sql              # Fase 1: esquema completo de `subscriptions` tras el cambio
│   ├── users-api-integration.md         # Fase 1: añade la operación de módulos al contrato ya existente
│   └── e2e-stubs.md                     # Fase 1: ampliación del stub de usuarios y de la colección Postman
│   # clinics-api-integration.md: SIN CAMBIOS; se sigue usando specs/001-subscriptions-api/contracts/clinics-api-integration.md
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

Todo lo de abajo **ya existe** (de `001-subscriptions-api` y `003-platform-dashboard`); se marca
`NUEVO` lo que añade esta feature y `MODIFICA` lo que cambia.

```text
src/
├── main.py                       # MODIFICA: VERSION "2.0.0" (R10); descripción menciona módulos/límites
├── config.py                     # sin cambios (USERS_API_* ya existe y se reutiliza)
├── dependencies.py               # MODIFICA: get_subscription_service también inyecta UsersApiClient
├── security.py                   # sin cambios (los 4 permisos de subscriptions ya existen)
├── exceptions.py                 # MODIFICA: + SubscriptionModuleNotFoundError (422),
│                                  #   SubscriptionModulePrerequisiteMissingError (409),
│                                  #   ModuleCheckUnavailableError (503)
├── messages.py                   # MODIFICA: + ErrorCode y mensajes de los 3 errores nuevos y de los
│                                  #   7 campos nuevos; VALIDATION_MESSAGES["subscriptions"] crece
├── clinic_modules.py              # NUEVO: claves propuestas de los 9 módulos de clínica, PATIENTS_KEY,
│                                  #   MODULE_DEPENDENCIES (dependiente → prerrequisito),
│                                  #   missing_prerequisite(keys) -> (dependiente, prerrequisito) | None
├── integrations/
│   ├── users_api.py              # MODIFICA: + list_clinic_module_keys(token) -> frozenset[str]
│   └── clinics_api.py            # sin cambios
├── routers/
│   └── subscriptions.py          # MODIFICA: nuevas respuestas documentadas (422/409/503) en create y
│                                  #   update; el resto de las rutas no cambia
├── services/
│   ├── authorization_service.py  # sin cambios
│   └── subscription_service.py   # MODIFICA: create/update validan módulos antes de escribir
│                                  #   (R5, R6); update añade una comprobación de existencia previa
│                                  #   cuando la solicitud trae módulos (R6)
├── repositories/
│   └── subscription_repository.py # MODIFICA: create/update reciben y persisten las 7 columnas nuevas
├── models/
│   └── subscription.py           # MODIFICA: + annual_price, trial_days, self_service, module_keys,
│                                  #   consulting_rooms_limit, doctors_limit, assistants_limit,
│                                  #   new_patients_per_year_limit; features -> other_features
└── dtos/
    └── subscription.py           # MODIFICA: SubscriptionRead/Create/Update ganan los campos nuevos;
                                   #   features -> other_features; validadores "no puede ser nulo"
                                   #   para los campos nuevos que no admiten `null`

alembic/versions/
└── 0003_subscription_pricing_modules_limits.py   # NUEVO (ver data-model.md)

tests/
├── stubs/users_api/app.py        # MODIFICA: + GET /api/v1/modules (sembrado con los 9 módulos);
│                                  #   /__test__/faults gana "operation": "check"|"modules"
├── unit/
│   ├── test_subscription_dtos.py          # MODIFICA: + casos de los campos nuevos
│   ├── test_subscription_service.py       # MODIFICA: + validación de módulos (reconocidos,
│   │                                       #   prerrequisitos, Pacientes siempre incluido, 503)
│   ├── fakes.py                           # MODIFICA: FakeUsersApi gana list_clinic_module_keys
│   └── test_clinic_modules.py             # NUEVO: missing_prerequisite() por cada uno de los 4 pares
├── integration/
│   ├── test_subscription_repository.py    # MODIFICA: + columnas nuevas
│   ├── test_subscriptions_constraints.py  # MODIFICA: + CHECK nuevos (límites, 'patients' en
│   │                                       #   module_keys, trial_days 0–3650)
│   ├── test_migrations.py                 # MODIFICA: aplica 0001 a 0003 y las revierte
│   └── test_models_match_migrations.py    # sin cambios de fondo (sigue comparando modelos ↔ migraciones)
└── contract/
    ├── test_subscriptions_api.py          # MODIFICA: + escenarios de módulos, límites, precio anual
    ├── test_users_api_client.py           # MODIFICA: + list_clinic_module_keys (éxito y fallos)
    └── test_openapi_contract.py           # sin cambios de fondo (sigue comparando contra el YAML)

tests/postman/collections/
└── MailySoft-System-Suscripciones.postman_collection.json   # MODIFICA: cuerpos de ejemplo con los
                                                               # campos nuevos; carpeta nueva de errores
                                                               # de módulos

project-definition/
└── DATA_SCHEMA.md                # MODIFICA: refleja `subscriptions` tras 0003, marcado
                                   #   `-- [spec 004-correct-subscriptions-api]`
```

**Structure Decision**: no se crean capas, Routers ni Services nuevos: es una corrección del mismo
recurso de `001-subscriptions-api`. La única pieza nueva de dominio (`src/clinic_modules.py`) es
deliberadamente un módulo plano sin I/O (como `messages.py`), porque no respalda ninguna tabla propia
ni habla con una red: solo codifica una regla de negocio que esta API decidió mantener aunque su dato
de origen (el catálogo de módulos) viva en otro servicio.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación nueva. La única desviación conocida del proyecto (Principio VIII: el permiso se
comprueba antes de validar, salvo un cuerpo que no es JSON legible) ya está aceptada y documentada en
`specs/001-subscriptions-api/plan.md` y no cambia con esta feature.

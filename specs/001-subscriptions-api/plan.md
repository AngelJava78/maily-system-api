# Implementation Plan: API REST de Suscripciones

**Branch**: `001-subscriptions-api` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-subscriptions-api/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Primera feature del servicio **MailySoft System API**: un catálogo de **suscripciones** (planes) con
su estatus (Activa, Inactiva, Bloqueada y, para la baja lógica, Eliminada) y 6 operaciones REST bajo
`/api/v1/subscriptions`: listar (completo, sin paginar), consultar, crear, actualizar, cambiar el estatus y
eliminar. Cada operación exige un token de Auth0 y un permiso `subscriptions:*` que **decide el API de
usuarios**; el número de clínicas por plan lo aporta el **API de clínicas**. Es un servicio nuevo, con la
misma arquitectura y herramientas que `mailySoft-usuarios`.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Acceso (US2)**: este servicio **no verifica tokens**. Una dependencia de FastAPI (`src/security.py`)
  reenvía el `Bearer` recibido a `GET /api/v1/authorization/check?permission=…` del API de usuarios, **una
  llamada por petición, sin caché ni reintentos**, con un tiempo máximo total de 5 s. `allowed: true` →
  sigue; `allowed: false` → 403; token rechazado → 401 con el mismo código; cualquier otra cosa → 503
  (**falla cerrada**). La comprobación va antes de validar la solicitud (probado: sin token y con
  cuerpo inválido responde 401). Cada ruta declara `x-required-permission` y una prueba recorre todas
  las rutas (R2, R3, R4).
- **Datos**: dos tablas, `subscription_statuses` (catálogo 1–4 cargado por migración) y
  `subscriptions` (precio `NUMERIC(10,2)`, `features text[]`, índice único parcial por `lower(name)`
  donde el estatus ≠ 4, disparador de `updated_at`). Esquema validado contra PostgreSQL 17 real
  (R8, R9, R11; [data-model.md](data-model.md)).
- **Escrituras sin carreras**: el índice único decide los nombres repetidos; la baja y el cambio de
  estatus son una sola sentencia condicionada (R11, R12).
- **Clínicas (US1, US7)**: una operación consumida,
  `GET /api/v1/clinics/subscription-counts`, reenviando el token de la persona. En lecturas se consulta
  **en paralelo** con la base de datos y, si falla, `clinics_count` es `null` (nunca 0 inventado); al crear
  es `0` sin llamar; al **eliminar** se rechaza si tiene clínicas (409) o si no puede comprobarse (503)
  (R5, R6, R7).
- **Listado (US1)**: arreglo JSON completo ordenado por `created_at` e `id`; umbral de 500 (R13).
- **Pruebas sin servicios reales**: dos simulaciones (`tests/stubs/users_api`, `tests/stubs/clinics_api`)
  usadas por pytest (`ASGITransport`, ejercitando el código real de los clientes) y por la pila de
  Newman (R15, R16).
- **Configuración**: `USERS_API_*`, `CLINICS_API_*` y `CORS_ALLOWED_ORIGINS` (opcional), validadas al
  arrancar; el servicio no arranca si falta una obligatoria y el mensaje nunca muestra valores (R14).

## Technical Context

**Language/Version**: Python 3.14+ (el entorno de la referencia ejecuta 3.15.0)

**Primary Dependencies**: FastAPI 0.143.x, Pydantic v2 (+ pydantic-settings), SQLAlchemy 2.0 async +
asyncpg, Alembic, uvicorn y **httpx** (producción: llamadas a los otros APIs). Sin PyJWT ni
`cryptography`: el token no se verifica aquí. Desarrollo: pytest, pytest-asyncio, python-dotenv.
Herramienta de desarrollo aparte: Newman (npm), fuera de la imagen.

**Storage**: PostgreSQL 17; esquema nuevo con 2 tablas y 2 migraciones (`0001` esquema, `0002` datos del
catálogo de estatus). Sin estado en memoria en el servicio (no hay cachés).

**Testing**: pytest + pytest-asyncio + httpx; Services con dobles (`FakeUsersApi`, `FakeClinicsApi`,
Repository falso); Repositories contra PostgreSQL 17 real; endpoints por HTTP contra la aplicación con
las simulaciones montadas en el cliente real; prueba de cobertura de permisos; prueba de capas con
`ast`; Postman/Newman contra la pila aislada con las simulaciones como servicios.

**Target Platform**: Contenedor Linux (Docker Compose: `db`, `migrate`, `api`; en la pila e2e, además,
`users-api-stub` y `clinics-api-stub`); desarrollo en Windows con VS Code. Imagen `python:3.14-slim`.

**Project Type**: web-service

**Performance Goals**: catálogo completo (hasta 100 suscripciones; 500 en la prueba) en < 2 s en el 95 %
de las consultas (SC-001), suponiendo que los otros APIs responden en < 500 ms; el servicio añade
< 100 ms propios a las dependencias (medido en `test_catalog_scale.py` con las simulaciones).

**Constraints**: falla cerrada en el control de acceso (sin verificar no se deja pasar); efecto
inmediato de bloqueos y cambios de permisos (sin caché de decisiones); cada llamada a otro API con tiempo
máximo total de 5 s y sin reintentos; las lecturas **nunca** dependen del API de clínicas; el token no
aparece en registros, respuestas ni mensajes; ninguna prueba automatizada llama a un API real; ninguna
transacción abierta mientras se espera a otro servicio.

**Scale/Scope**: 6 operaciones; 2 tablas; 2 migraciones; 12 códigos de error; 2 integraciones externas
(1 operación consumida de cada una); 2 simulaciones; 5 variables de entorno del servicio
(`DATABASE_URL` y 4 de integraciones, dos de ellas con valor por defecto) y 1 opcional (CORS).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ Servicio nuevo, sin código previo | ✅ `src/` con `routers/`, `services/`, `repositories/`, `integrations/`, `database/`, `models/`, `dtos/` y `security.py`. Los dos clientes de otros APIs (`users_api.py`, `clinics_api.py`) viven en `src/integrations/`, solo los invocan Services y la dependencia de seguridad, y no importan capas superiores. `test_layering.py` lo comprueba |
| II. Modelos ≠ DTOs | ✅ | ✅ `SubscriptionCreate/Update/StatusChange/Read` son DTOs; los modelos no se exponen; `clinics_count` es un campo de solo lectura del DTO de salida, no una columna; ningún DTO contiene el token |
| III. Asincronía | ✅ | ✅ Todo `async`: SQLAlchemy/asyncpg y un `httpx.AsyncClient` compartido (creado y cerrado en el `lifespan`); tiempo máximo total con `asyncio.timeout`. Sin librerías bloqueantes |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) validado (OpenAPI 3.1, 6 operaciones); 201/204/401/403/404/409/422/503; formato de error uniforme. **Listado sin paginar**: es la excepción prevista y la spec (FR-006) declara el máximo esperado (100), el umbral (500) y el orden determinista; si se supera, se versiona (R13) |
| V. Pruebas pytest | ✅ | ✅ Services con dobles; endpoints con cliente async; Repositories contra PostgreSQL 17; **ninguna prueba llama a un API real** (simulaciones que reproducen también los fallos); prueba que recorre las rutas; Postman complementa y no sustituye |
| VI. Migraciones Alembic | ✅ | ✅ `0001` y `0002`, reversibles, async; datos del catálogo por migración; precio `NUMERIC(10,2)` (nunca `float`); baja lógica con catálogo de estatus; `project-definition/DATA_SCHEMA.md` **se crea en esta feature** con las marcas `-- [spec 001-subscriptions-api]` ([database-schema.sql](contracts/database-schema.sql), validado en PostgreSQL 17) |
| VII. Idioma | ✅ | ✅ Identificadores, campos (`monthly_price`, `clinics_count`, `status_id`) y códigos en inglés; mensajes, OpenAPI y documentos en español; comentarios y docstrings en inglés |
| VIII. Control de acceso delegado | ✅ | ✅ Token reenviado al API de usuarios, una consulta por petición, sin caché, falla cerrada; 401/403/503 según [users-api-integration.md](contracts/users-api-integration.md); dependencias en `src/security.py` que pasan por `AuthorizationService`; `BearerAuth` + `x-required-permission` en cada operación; el permiso se comprueba **antes** de validar (comprobado; **limitación conocida**: un JSON sintácticamente roto responde 422 antes que 401, igual que la referencia, R4); sin secretos ni tokens en registros |
| IX. Integraciones | ✅ | ✅ El conteo de clínicas no se copia ni se guarda; tiempo máximo y sin reintentos; fallas traducidas a errores propios sin filtrar el cuerpo ni la dirección del otro servicio; las **lecturas** siguen disponibles sin el API de clínicas (`null`); **eliminar** falla cerrada (escritura destructiva); contratos consumidos documentados y con simulación |
| Stack obligatorio | ✅ | ✅ Solo tecnologías de la tabla (httpx incluido); sin PyJWT ni Auth0; sin dependencias nuevas |
| Configuración por entorno, sin secretos | ✅ | ✅ Variables validadas al arrancar; no hay secretos propios (la cadena de la base de datos viene de `.env`, que no se versiona); el mensaje de arranque nombra variables, nunca valores |
| Docker y Compose | ✅ | ✅ `Dockerfile`, `docker-compose.yml` (`db`, `migrate`, `api`) y pila e2e aislada; puertos por defecto distintos de los de `mailySoft-usuarios` (5433 y 8010) |
| Flujo y puertas de calidad | ✅ | ✅ Este plan incluye el Constitution Check; estructura `src/`, `tests/`, `alembic/`; matriz de permisos y colección de Postman se actualizan con la API |

**Resultado**: PASS contra los principios I a IX, sin violaciones y sin necesidad de enmendar la
constitución. Dos limitaciones conocidas y aceptadas (no son violaciones): el JSON roto que responde
422 antes que 401 (R4) y la carrera entre la comprobación de clínicas y la baja, que no puede ser atómica
entre dos servicios (R7).

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **API de usuarios**: que publique `GET /api/v1/authorization/check` (spec 008 de `mailySoft-usuarios`) y
   que su catálogo incluya `subscriptions:read|write|update|delete` asociados a los roles que
   correspondan ([users-api-integration.md](contracts/users-api-integration.md)).
2. **API de clínicas**: que acepte la operación propuesta, el token de la persona y que no asigne
   suscripciones Eliminadas ([clinics-api-integration.md](contracts/clinics-api-integration.md)).
   Mientras no exista, el conteo sale como «no disponible» y eliminar responde 503: comportamiento ya
   especificado.
3. **CORS**: la variable opcional `CORS_ALLOWED_ORIGINS` existe porque el Front es de navegador (R18);
   se puede quitar si el Front llama por un servidor propio.

## Project Structure

### Documentation (this feature)

```text
specs/001-subscriptions-api/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: decisiones R1–R21, evidencia y puntos a confirmar
├── data-model.md                        # Fase 1: entidades, estatus, reglas derivadas y DTOs
├── quickstart.md                        # Fase 1: guía de validación en tres niveles
├── contracts/
│   ├── openapi-subscriptions.yaml       # Fase 1: contrato HTTP (OpenAPI 3.1, validado)
│   ├── permission-matrix.md             # Fase 1: operación → permiso (6 operaciones)
│   ├── error-catalog.md                 # Fase 1: 12 códigos, mensajes y precedencia
│   ├── database-schema.sql              # Fase 1: esquema y datos del catálogo (validado en PostgreSQL 17)
│   ├── users-api-integration.md         # Fase 1: contrato consumido del API de usuarios
│   ├── clinics-api-integration.md       # Fase 1: contrato consumido (propuesto) del API de clínicas
│   └── e2e-stubs.md                     # Fase 1: simulaciones, pila de Newman y colección de Postman
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

Todo es nuevo: el repositorio solo tiene `README.md`, `.gitignore` y la configuración de Spec Kit.

```text
src/
├── __init__.py
├── main.py                       # create_app() sin efectos secundarios, lifespan (valida la configuración, crea/cierra el cliente HTTP), VERSION 1.0.0, DESCRIPTION y tags, CORS opcional, nivel de registro de httpx
├── config.py                     # Settings (base de datos) e IntegrationSettings (URL y tiempos de los otros APIs, CORS); errores de arranque que nombran variables sin valores
├── dependencies.py               # raíz de composición: cliente HTTP compartido, UsersApiClient, ClinicsApiClient, Repository y Services
├── security.py                   # (Principio VIII) esquema BearerAuth, extracción del token, require_permission(nombre)
├── exceptions.py                 # AppError y los errores de identidad, permiso, suscripción y dependencias
├── error_handlers.py             # formato uniforme (401, 403, 404, 409, 422, 500, 503) con mensajes de validación en español
├── messages.py                   # ErrorCode y mensajes en español (ver contracts/error-catalog.md)
├── integrations/                 # clientes de sistemas externos (Principio I)
│   ├── __init__.py
│   ├── errors.py                 # excepciones propias (no son errores HTTP): UsersApiRejectedToken, UsersApiUnavailable, ClinicsApiUnavailable
│   ├── users_api.py              # UsersApiClient.check_permission(token, permission) → bool
│   └── clinics_api.py            # ClinicsApiClient.get_counts(subscription_ids | None) → dict[int, int]
├── routers/
│   ├── __init__.py
│   ├── openapi_docs.py           # error_response, example_response y protected(permission): dependencia + x-required-permission + respuestas 401/403/503
│   └── subscriptions.py          # las 6 operaciones de /api/v1/subscriptions
├── services/
│   ├── __init__.py
│   ├── authorization_service.py  # require(token, permission): traduce las respuestas del API de usuarios a errores de la aplicación
│   └── subscription_service.py   # reglas de negocio: estatus, baja con comprobación de clínicas, degradación del conteo
├── repositories/
│   ├── __init__.py               # INT4_MAX
│   ├── errors.py                 # UniqueViolationError, ForeignKeyViolationError
│   ├── transactions.py           # execute_and_commit
│   └── subscription_repository.py
├── database/
│   ├── __init__.py
│   └── session.py                # engine async, fábrica de sesiones, get_session
├── models/
│   ├── __init__.py
│   ├── base.py                   # Base + NAMING_CONVENTION (nombres automáticos de PostgreSQL)
│   ├── subscription.py           # Subscription + índice parcial único del nombre
│   └── subscription_status.py    # SubscriptionStatus (ACTIVE=1, INACTIVE=2, BLOCKED=3, DELETED=4)
└── dtos/
    ├── __init__.py
    ├── errors.py                 # ErrorResponse, FieldError
    ├── status.py                 # StatusRead
    └── subscription.py           # SubscriptionRead, SubscriptionCreate, SubscriptionUpdate, SubscriptionStatusChange

alembic/
├── env.py                        # Alembic en modo async (patrón de la referencia)
├── script.py.mako
└── versions/
    ├── 0001_subscriptions_schema.py
    └── 0002_seed_subscription_statuses.py

tests/
├── conftest.py                   # base de pruebas (*_test), sesiones, simulaciones montadas con ASGITransport
├── helpers.py
├── stubs/
│   ├── users_api/app.py          # simulación del API de usuarios (no importa nada de src/)
│   └── clinics_api/app.py        # simulación del API de clínicas (no importa nada de src/)
├── unit/                         # sin base de datos: DTOs, Services, seguridad, mensajes, configuración, capas
│   ├── test_layering.py
│   ├── test_subscription_dtos.py
│   ├── test_subscription_service.py
│   ├── test_authorization_service.py
│   ├── test_security.py
│   ├── test_config.py
│   └── test_error_messages.py
├── integration/                  # PostgreSQL 17 real
│   ├── test_migrations.py
│   ├── test_models_match_migrations.py
│   ├── test_seed_data.py
│   ├── test_subscription_repository.py
│   ├── test_subscriptions_constraints.py
│   └── test_catalog_scale.py
├── contract/                     # la API por HTTP, el OpenAPI y la colección de Postman
│   ├── test_subscriptions_api.py
│   ├── test_access_control.py
│   ├── test_permission_coverage.py
│   ├── test_clinics_degradation.py
│   ├── test_users_api_client.py
│   ├── test_clinics_api_client.py
│   ├── test_openapi_contract.py
│   └── test_postman_collection.py
└── postman/                      # colección, entornos y pila aislada (Newman); node_modules/ y reports/ fuera de Git
    ├── collections/MailySoft-System-Suscripciones.postman_collection.json
    ├── environments/{e2e,dev}.postman_environment.json
    ├── docker-compose.e2e.yml
    └── package.json

project-definition/
└── DATA_SCHEMA.md                # esquema objetivo (Principio VI), con las marcas -- [spec 001-subscriptions-api]

docker/postgres/init/01-create-test-db.sql   # crea la base de pruebas `maily_system_test`
Dockerfile · docker-compose.yml · .dockerignore · alembic.ini · pyproject.toml · uv.lock
.env.example                      # variables sin valores secretos (puertos 5433 y 8010 por defecto)
.gitignore                        # (modificado) añade tests/postman/node_modules/ y tests/postman/reports/
README.md                         # (modificado) qué incluye, puesta en marcha, pruebas, estructura
```

**Structure Decision**: proyecto único de servicio web con la estructura obligatoria de la
constitución (Principio I). Un solo Router (`subscriptions.py`) y un solo Service de dominio, porque la
feature tiene un único recurso; el Service de autorización es transversal y lo usa `src/security.py`.
Cuando lleguen otros dominios (clínicas, etc.), cada uno añade su Router, Service y Repository sin
tocar los de suscripciones.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Sin violaciones: no hay nada que justificar. Las dos limitaciones conocidas (JSON roto y carrera de la
baja) están descritas en el Constitution Check y en [research.md](research.md) (R4 y R7).

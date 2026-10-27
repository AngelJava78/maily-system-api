# Implementation Plan: Tipo de suscripción (Individual o Empresarial)

**Branch**: `006-add-subscription-type` | **Date**: 2026-10-26 (revisado tras Clarifications) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-add-subscription-type/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

**Revisión**: esta versión del plan **reemplaza** a la anterior. El responsable del proyecto corrigió,
vía `/speckit-clarify`, la decisión central de la primera versión: el tipo **no** es una columna con
`CHECK` fijo a dos valores — es un catálogo propio (tabla), igual que el estatus de la suscripción,
para poder agregar un tercer tipo en el futuro sin una migración que reescriba una restricción. Todo
este documento, `research.md`, `data-model.md`, `contracts/` y `quickstart.md` quedaron reescritos
con ese diseño. El código que ya se había implementado con el diseño anterior (migración `0005`,
modelo, DTOs) **todavía no refleja esta corrección**: lo rehace `/speckit-tasks` + `/speckit-implement`.

## Summary

`004-correct-subscriptions-api` ya está implementada en `main`. Esta feature agrega un dato nuevo,
el tipo de suscripción, sin tocar nombre, módulos, límites ni características ya existentes. Es
obligatorio al crear, visible en toda lectura e inmutable para siempre.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Representación (R1, R2, R8)**: una tabla nueva, `subscription_types` (`id`, `name`,
  `description`), **idéntica en forma** a `subscription_statuses` (Clarifications 2026-10-26:
  confirmado explícitamente por el responsable del proyecto). `subscriptions` gana
  `subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types(id)`. Se siembra con
  `(1, 'Individual')` y `(2, 'Empresarial')` en la misma migración. El código que necesita el
  significado de negocio de estos dos valores usa constantes (`SubscriptionType.INDIVIDUAL`/
  `.ENTERPRISE`, como ya hace `SubscriptionStatus.DELETED`), nunca el número suelto ni un texto.
  Agregar un tercer tipo en el futuro es insertar una fila; ninguna regla de negocio lo reconocería
  hasta que una especificación futura la agregue (igual que un quinto estatus agregado a mano hoy
  no dispara ninguna regla nueva).
- **Contrato de lectura y escritura (R2)**: `SubscriptionRead.subscription_type` es un objeto
  `{id, name}` (como `status`), vía un DTO nuevo `SubscriptionTypeRead` (idéntico a `StatusRead`).
  `SubscriptionCreate` recibe `subscription_type_id` (entero, como
  `SubscriptionStatusChange.status_id`), no un texto.
- **Validación sin lectura previa (R5)**: si `subscription_type_id` no existe en el catálogo, se
  descubre **al intentar el `INSERT`**, no con una consulta de existencia por separado: la clave
  foránea lo rechaza, `execute_and_commit` ya traduce eso a `ForeignKeyViolationError`
  (`src/repositories/errors.py`, ya existe, hoy sin usar en este flujo), y el Service la traduce a
  `SubscriptionTypeNotFoundError` (código nuevo `subscription_type_not_found`, 422) — exactamente el
  mismo patrón que ya usa `UniqueViolationError` para el nombre repetido.
- **Datos existentes (R3, R4, R7; sin cambios de fondo respecto a la primera versión)**: la migración
  agrega la columna con `DEFAULT 1`, así que ninguna suscripción existente queda sin tipo. El script
  de reconciliación (`src/scripts/backfill_subscription_types.py`) sigue siendo quien, fuera de
  Alembic, asciende a `subscription_type_id = 2` ("Empresarial") las que ya tenían más de una
  clínica, reintentando sin límite; sigue sin vivir en Alembic porque la API de clínicas no tiene
  credenciales de servicio.
- **Límite de clínicas por tipo (FR-006, FR-007)**: sin cambios de fondo; esta API no ejecuta
  ninguna operación de "asociar clínica": expone el tipo (ahora como `{id, name}`) para que el
  sistema que administra las clínicas decida.
- **Errores y permisos**: **un** código de error nuevo (`subscription_type_not_found`, 422), no cero
  como se pensó en la primera versión (R5); cero permisos nuevos.
- **Contrato**: `SubscriptionCreate` gana un campo obligatorio nuevo y la forma de
  `subscription_type` en las lecturas cambia de cadena a objeto (cambio incompatible de forma);
  `VERSION` sube a `3.0.0`, igual que la primera versión de este plan.

## Technical Context

**Language/Version**: Python 3.14+ (sin cambios)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, uvicorn,
httpx. Sin dependencias nuevas.

**Storage**: PostgreSQL 17; una migración nueva (`0005`) que crea `subscription_types` (2 filas
sembradas) y agrega `subscriptions.subscription_type_id` (clave foránea a esa tabla nueva).

**Testing**: pytest + pytest-asyncio + httpx, igual que `001`/`004`/`005`. `tests/unit/fakes.py`
(`FakeSubscriptionRepository`) gana lo necesario para `subscription_type_id` y para la
reconciliación; el bucle de reintento del script se extrae a una función testable con una espera
inyectada.

**Target Platform**: igual que `004` (contenedor Linux, Docker Compose). El script de reconciliación
corre dentro de la misma imagen de la aplicación.

**Project Type**: web-service (ampliación de una feature existente)

**Performance Goals**: sin cambios respecto a `004` (SC-001). La validación de
`subscription_type_id` no agrega ninguna consulta extra: se resuelve con el mismo `INSERT` que ya
se hacía (sin una lectura de existencia previa, research R5).

**Constraints**: las mismas de `004` más: el script de reconciliación reintenta sin límite su única
llamada (`get_counts`, un GET idempotente) ante `ClinicsApiUnavailable`, pero ese reintento vive en
el script, no en `ClinicsApiClient` (que sigue sin reintentos para toda llamada en el camino de una
petición, Principio IX sin cambios).

**Scale/Scope**: mismas 6 operaciones y los mismos 4 permisos externos ya usados; ningún permiso
externo adicional. Una migración nueva; una tabla nueva (2 filas sembradas); una columna nueva; **un**
código de error nuevo (no cero, a diferencia de la primera versión de este plan); un script de
despliegue nuevo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas | ✅ Solo se tocan capas ya existentes, más un paquete nuevo fuera de las 6 de capa | ✅ `src/scripts/backfill_subscription_types.py` sigue siendo un entrypoint delgado sin lógica de negocio (sin cambios respecto a la primera versión); `tests/unit/test_layering.py` ya declara su regla para `scripts`. `src/models/subscription_type.py` (modelo) y `src/dtos/subscription_type.py` (DTO) son archivos nuevos, en sus capas de siempre, idénticos en forma a `subscription_status.py`/`status.py` |
| II. Modelos ≠ DTOs | ✅ | ✅ `SubscriptionType` (modelo ORM) vive en `src/models/`; `SubscriptionTypeRead` (DTO de salida) en `src/dtos/`, separado; `SubscriptionRead.subscription_type` nunca expone la fila cruda del catálogo sin pasar por el DTO |
| III. Asincronía | ✅ | ✅ Sin cambios: la comprobación de existencia del tipo no agrega ninguna consulta nueva (se resuelve con el `INSERT` ya async existente, no con un `SELECT` adicional) |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) actualizado (`version: 3.0.0`); `SubscriptionTypeRead` como esquema reutilizable (idéntico en forma a `StatusRead`); nuevo ejemplo 422 `subscription_type_not_found` documentado en `create_subscription` |
| V. Pruebas pytest | ✅ | ✅ Mismo patrón; `FakeSubscriptionRepository` gana `subscription_type_id`; una prueba de integración nueva confirma que un `subscription_type_id` inexistente dispara `ForeignKeyViolationError` desde la base de datos real, no solo desde el doble |
| VI. Migraciones Alembic | ✅ | ✅ `0005_add_subscription_type` (reescrita: crea la tabla, la siembra, agrega la columna), reversible; `project-definition/DATA_SCHEMA.md` y `create_database.sql` ya actualizados con la tabla nueva; ninguna migración llama a otro servicio |
| VII. Idioma | ✅ | ✅ `subscription_type_id`/`subscription_types` en inglés; los **datos** del catálogo (`name`) en español ("Individual", "Empresarial"), igual que `subscription_statuses` ("Activa", "Inactiva") — ya no inglés como en la primera versión de este plan, porque ahora el `id` (no el texto) es el valor estable |
| VIII. Control de acceso delegado | ✅ Sin cambios | ✅ Sin cambios respecto a la primera versión: el catálogo no tiene operación ni permiso propio (igual que el estatus) |
| IX. Integraciones | ✅ | ✅ Sin cambios respecto a la primera versión |
| Stack obligatorio | ✅ | ✅ Sin dependencias nuevas |
| Flujo y puertas de calidad | ✅ | ✅ Constitution Check incluido |

**Resultado**: PASS contra los principios I a IX, sin necesidad de enmendar la constitución.

## Puntos a confirmar fuera de este repositorio (no bloquean el plan, pero bloquean producción)

Sin cambios respecto a la primera versión de este plan:

1. Quién ejecuta el script de reconciliación y con qué token (un paso manual de despliegue).
2. El sistema que administra las clínicas debe empezar a consultar `subscription_type.id` (ya no
   una cadena) antes de asociar una clínica a una suscripción.
3. API de clínicas y de usuarios: sin cambios, siguen pendientes de confirmar igual que antes.

## Project Structure

### Documentation (this feature)

```text
specs/006-add-subscription-type/
├── plan.md                              # Este archivo (reescrito)
├── research.md                          # Fase 0: R1–R8 (R1, R2, R5 corregidos; R8 nuevo)
├── data-model.md                        # Fase 1: tabla subscription_types, columna FK, DTOs
├── quickstart.md                        # Fase 1: guía de validación (reescrita con el nuevo contrato)
├── contracts/
│   ├── openapi-subscriptions.yaml       # Fase 1: contrato HTTP actualizado (reemplaza al de 004)
│   ├── permission-matrix.md             # Fase 1: sin permisos nuevos
│   ├── error-catalog.md                 # Fase 1: UN código nuevo (subscription_type_not_found)
│   └── database-schema.sql              # Fase 1: esquema completo, incluida subscription_types
│   # users-api-integration.md, clinics-api-integration.md, e2e-stubs.md: SIN CAMBIOS
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks; existe de la primera versión,
                                          #   necesita regenerarse para el diseño nuevo)
```

### Source Code (repository root)

Todo lo de abajo **ya existe** (de `001`, `004` y `005`), salvo lo ya escrito en la primera pasada
de esta misma feature (marcado `REESCRIBE` porque su diseño cambia de fondo) y lo genuinamente nuevo
(`NUEVO`).

```text
src/
├── __init__.py                   # MODIFICA: VERSION "3.0.0" (sin cambios respecto a la primera versión)
├── scripts/                      # Sin cambios de forma respecto a la primera versión
│   ├── __init__.py
│   └── backfill_subscription_types.py  # REESCRIBE: marca `enterprise` escribiendo
│                                  #   subscription_type_id = SubscriptionType.ENTERPRISE (2), no
│                                  #   un texto; el resto (reintento, token) no cambia
├── messages.py                   # REESCRIBE: quita SUBSCRIPTION_TYPE_INVALID_MESSAGE (ya no aplica:
│                                  #   no hay una lista fija que validar); SUBSCRIPTION_TYPE_REQUIRED_MESSAGE
│                                  #   se reformula para un entero ("…obligatorio y debe ser un número
│                                  #   entero positivo"); + SUBSCRIPTION_TYPE_NOT_FOUND_MESSAGE (nueva,
│                                  #   para el AppError); SUBSCRIPTION_TYPE_IMMUTABLE_MESSAGE sin cambios
│                                  #   de texto (solo cambia la clave: subscription_type_id)
├── exceptions.py                 # MODIFICA: + SubscriptionTypeNotFoundError(subscription_type_id) (422)
├── integrations/
│   └── clinics_api.py            # sin cambios
├── routers/
│   └── subscriptions.py          # MODIFICA: ejemplos de documentación con subscription_type_id
│                                  #   (crear) y subscription_type: {id, name} (lecturas); nuevo
│                                  #   ejemplo 422 subscription_type_not_found
├── services/
│   └── subscription_service.py   # MODIFICA: create() pasa subscription_type_id; atrapa
│                                  #   ForeignKeyViolationError (de la FK subscription_type_id) y la
│                                  #   traduce a SubscriptionTypeNotFoundError, igual patrón que
│                                  #   UniqueViolationError → SubscriptionNameAlreadyExistsError; +
│                                  #   reconcile_types_from_clinic_counts (sin cambios de firma,
│                                  #   solo el valor que escribe)
├── repositories/
│   └── subscription_repository.py # MODIFICA: create() recibe subscription_type_id (antes
│                                  #   subscription_type); _select_with_status() también
│                                  #   joinedload(Subscription.subscription_type) (como ya hace con
│                                  #   .status); mark_enterprise(ids) escribe
│                                  #   subscription_type_id = 2, no un texto
├── models/
│   ├── subscription_type.py      # NUEVO: clase SubscriptionType(Base), idéntica forma a
│   │                              #   subscription_status.py (id, name, description) +
│   │                              #   INDIVIDUAL: ClassVar[int] = 1, ENTERPRISE: ClassVar[int] = 2
│   └── subscription.py           # MODIFICA: subscription_type_id: Mapped[int] (FK a
│                                  #   subscription_types.id, server_default 1) reemplaza a
│                                  #   subscription_type: Mapped[str]; + relationship
│                                  #   subscription_type (lazy="raise", como status)
└── dtos/
    ├── subscription_type.py      # NUEVO: SubscriptionTypeRead (id, name), idéntico a status.py
    └── subscription.py           # MODIFICA: quita SUBSCRIPTION_TYPES/SubscriptionType/
                                   #   _validate_subscription_type (ya no aplican); SubscriptionRead
                                   #   gana subscription_type: SubscriptionTypeRead; SubscriptionCreate
                                   #   gana subscription_type_id: int (estricto, > 0); SubscriptionUpdate
                                   #   sigue sin este campo

alembic/versions/
└── 0005_add_subscription_type.py  # REESCRIBE (no se apila una 0006: 0005 nunca se usó fuera de
                                    #   este repositorio): crea subscription_types, la siembra,
                                    #   agrega subscriptions.subscription_type_id

tests/
├── unit/
│   ├── fakes.py                           # MODIFICA: FakeSubscriptionRepository.add/create ganan
│   │                                       #   subscription_type_id: int = 1 (reemplaza a
│   │                                       #   subscription_type: str); mark_enterprise escribe 2
│   ├── test_subscription_dtos.py          # REESCRIBE los casos de subscription_type: entero
│   │                                       #   obligatorio (no un texto de una lista fija);
│   │                                       #   subscription_type_id no permitido en Update
│   ├── test_subscription_service.py       # MODIFICA: create() con subscription_type_id; +
│   │                                       #   ForeignKeyViolationError → SubscriptionTypeNotFoundError
│   └── test_backfill_subscription_types.py # Sin cambios de forma (prueba el bucle de reintento,
│                                            #   agnóstico de qué valor exacto se escribe)
├── integration/
│   ├── test_subscription_repository.py    # MODIFICA: create()/mark_enterprise con
│   │                                       #   subscription_type_id; + prueba de la FK real
│   ├── test_subscriptions_constraints.py  # REESCRIBE los casos de subscription_type: ahora
│   │                                       #   prueban la FK (23503), no un CHECK (23514)
│   └── test_migrations.py                 # MODIFICA: + subscription_types se crea y se siembra;
│                                            #   el DEFAULT 1 sigue probándose igual
└── contract/
    ├── test_subscriptions_api.py          # REESCRIBE los casos de subscription_type: crear con
    │                                       #   subscription_type_id (entero); leer como {id, name};
    │                                       #   subscription_type_not_found para un id inexistente
    └── test_openapi_contract.py           # sin cambios de fondo

tests/postman/collections/
└── MailySoft-System-Suscripciones.postman_collection.json   # MODIFICA: cuerpos de ejemplo con
                                                               # subscription_type_id (crear); nuevo
                                                               # caso 422 de tipo inexistente

project-definition/
├── DATA_SCHEMA.md                # Ya actualizado en esta revisión del plan (tabla subscription_types)
└── create_database.sql           # Ya actualizado en esta revisión del plan (crea y siembra la tabla)
```

**Structure Decision**: dos archivos nuevos (`src/models/subscription_type.py`,
`src/dtos/subscription_type.py`), deliberadamente copias de forma de `subscription_status.py`/
`status.py` — mismo patrón ya probado en este proyecto para "un catálogo pequeño, administrado a
mano, referenciado por FK, con un `id` estable que el código usa como constante para sus dos valores
con significado de negocio". No se crean Routers, Services ni Repositories nuevos.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación. `src/scripts/` sigue justificado como en la primera versión de este plan (ver su
Complexity Tracking, sin cambios). No hay ninguna otra desviación nueva que justificar: el diseño
corregido añade una tabla y una clave foránea, ambas con el mismo patrón que `subscription_statuses`
ya usaba desde `001-subscriptions-api`, así que no introduce ninguna estructura que la constitución
no haya contemplado ya.

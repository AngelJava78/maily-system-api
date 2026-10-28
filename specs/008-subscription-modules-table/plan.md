# Implementation Plan: Guardar los módulos de la suscripción en su propia tabla

**Branch**: `008-subscription-modules-table` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-subscription-modules-table/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Los módulos de una suscripción (`module_keys`) hoy se guardan en una sola columna `text[]` de
`subscriptions`, con un `CHECK` que exige que siempre contenga `patients`. Esta feature los mueve
a una tabla propia, `subscription_modules` (una fila por módulo), sin tocar en nada el contrato
publicado ni la validación ya vigente contra `users-api` (004): es una corrección interna de
almacenamiento, no un cambio de comportamiento.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Forma de la relación (R1)**: `subscription_modules (subscription_id, module_key)` con clave
  primaria compuesta (sin `id` propio) — da, sin ninguna columna extra, FR-001 (una fila por
  módulo) y FR-002 (sin duplicados por la clave primaria; sin huérfanos por la `FOREIGN KEY`).
- **`patients` siempre incluido deja de ser un `CHECK` (R2)**: un `CHECK` de PostgreSQL no ve otras
  filas de la misma tabla, así que esa regla —igual que ya pasa hoy con la validación contra
  `users-api` y los prerrequisitos entre módulos— sigue siendo una garantía exclusiva del Service
  (`_resolve_modules`, sin cambios). Se documenta como una pérdida consciente de la red de
  seguridad que hoy da el `CHECK` solo contra una escritura directa en la base que se salte la API.
- **Cero cambios en los DTOs ni en el Router (R3, R4)**: `src/models/subscription.py` gana una
  propiedad de solo lectura `module_keys` (sobre la relación `modules`, con `order_by` alfabético)
  que `SubscriptionRead.model_validate(subscription)` sigue leyendo exactamente igual.
- **Migración de los datos existentes sin script fuera de Alembic (R5)**: `INSERT INTO
  subscription_modules SELECT id, unnest(module_keys) FROM subscriptions`, una sola sentencia
  dentro de la propia migración `0007` (a diferencia de `006`, que sí necesitó un script aparte
  porque dependía de la API de clínicas).
- **Reversible (R6)**: `downgrade()` reconstruye `module_keys` desde `subscription_modules` con
  `array_agg`, recrea el `CHECK` y elimina la tabla nueva.
- **Atomicidad en el Repository (R7, R8)**: `create()`/`update()` siguen siendo una operación con
  un solo commit aunque ahora escriban en dos tablas (`src/repositories/transactions.py` gana una
  variante de `execute_and_commit` para más de una sentencia); `update()` conserva su firma pública
  (`changes: Mapping[str, Any]`) sacando `module_keys` antes de construir el `UPDATE` de
  `subscriptions`, que siempre se ejecuta (comprobación de existencia/estatus y disparador de
  `updated_at`, aunque los módulos sean el único cambio).
- **Sin índice nuevo sobre `module_key` por sí solo (R9)**: ninguna consulta de esta especificación
  lo necesita; no se adelanta un caso de uso que ninguna especificación pide todavía.
- **Contrato**: sin cambios (`SubscriptionRead`/`SubscriptionCreate`/`SubscriptionUpdate` son los
  mismos de `007`); `VERSION` permanece en `4.0.0` (no hay cambio incompatible que versionar).

## Technical Context

**Language/Version**: Python 3.14+ (sin cambios)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, uvicorn,
httpx. Sin dependencias nuevas.

**Storage**: PostgreSQL 17; una migración nueva (`0007`) que crea `subscription_modules`, migra a
ella los módulos ya guardados y quita `module_keys` y su `CHECK` de `subscriptions`.

**Testing**: pytest + pytest-asyncio + httpx, igual que `001`/`004`/`006`/`007`. Dos niveles de
ejecución (Principio V, v1.1.0): `/speckit-implement` de esta feature MUST limitarse a la corrida
rápida por defecto (unitarias, sin PostgreSQL real); las de integración/contrato de esta feature
(ver [quickstart.md](quickstart.md)) y la colección de Postman automatizada (que no cambia, FR-004)
quedan para la puerta de calidad antes de integrar a `main`. `tests/unit/fakes.py` y
`tests/helpers.py` dejan de construir `Subscription(module_keys=...)` (ya no es un argumento
válido: `module_keys` pasa a ser una propiedad de solo lectura) y pasan a poblar la relación
`modules` directamente (ver Project Structure).

**Target Platform**: igual que `007` (contenedor Linux, Docker Compose). Sin componentes nuevos de
despliegue.

**Project Type**: web-service (corrección interna sobre una feature existente)

**Performance Goals**: sin cambios de forma. `create()`/`update()` pasan de una sentencia de
escritura a dos cuando hay módulos involucrados (la de `subscriptions` y la de
`subscription_modules`), siempre dentro de la misma transacción y el mismo viaje de red hacia la
base de datos; no se agrega ninguna llamada nueva a otro sistema.

**Constraints**: las mismas de `007`, sin ninguna nueva (ninguna integración externa nueva).

**Scale/Scope**: mismas 6 operaciones y los mismos 4 permisos externos; ningún permiso nuevo. Una
migración nueva; una tabla nueva; un modelo ORM nuevo; **cero** códigos de error nuevos; **cero**
campos nuevos de la API (a diferencia de `006` y `007`, que sí agregaron campos).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas | ✅ Solo se tocan `src/models/`, `src/repositories/`; sin Routers, Services ni DTOs nuevos | ✅ El propio objetivo de esta feature demuestra la separación de capas: cambiar cómo persiste algo sin tocar Service, Router ni DTOs; `subscription_module.py` vive en `src/models/`, la misma capa que `subscription.py` |
| II. Modelos ≠ DTOs | ✅ | ✅ `module_keys` pasa de columna de modelo a propiedad derivada del modelo; los DTOs (`SubscriptionRead`/`Create`/`Update`) no cambian ni una línea |
| III. Asincronía | ✅ | ✅ El `INSERT`/`DELETE`+`INSERT` extra de `subscription_modules` usa la misma `AsyncSession` ya async; sin ninguna llamada nueva a otro sistema |
| IV. OpenAPI y REST | ✅ Sin cambio de contrato | ✅ `SubscriptionRead`/`Create`/`Update` idénticos a los de [007](../007-add-clinics-limit/contracts/openapi-subscriptions.yaml); no se genera un `openapi-subscriptions.yaml` propio porque no hay nada que cambiar en él |
| V. Pruebas pytest | ✅ | ✅ Las pruebas que ya cubrían el comportamiento de módulos (DTO, Service) no cambian sus aserciones (prueban una capa que no cambió); las de Repository, restricciones y migraciones sí cambian, porque prueban la capa que esta feature corrige (ver `tasks.md`); dos niveles de ejecución sin cambios respecto a `007` |
| VI. Migraciones Alembic | ✅ | ✅ `0007_subscription_modules_table` (nueva, reversible); `project-definition/DATA_SCHEMA.md` y `create_database.sql` actualizados con la tabla nueva y la columna que se quita |
| VII. Idioma | ✅ | ✅ `subscription_modules`, `SubscriptionModule`, `module_key` en inglés (identificadores); sin mensajes nuevos que traducir (no hay comportamiento nuevo que explicarle a una persona) |
| VIII. Control de acceso delegado | ✅ Sin cambios | ✅ Sin cambios: mismos 4 permisos, sin ninguno nuevo |
| IX. Integraciones | ✅ Sin cambios | ✅ El catálogo de módulos sigue siendo de `users-api`; esta tabla solo guarda qué claves eligió cada suscripción, igual responsabilidad que ya tenía la columna que sustituye |
| Stack obligatorio | ✅ | ✅ Sin dependencias nuevas |
| Flujo y puertas de calidad | ✅ | ✅ Constitution Check incluido |

**Resultado**: PASS contra los principios I a IX, sin necesidad de enmendar la constitución. Única
nota de transparencia (no una violación): R2 retira una red de seguridad que hoy existe solo a
nivel de base de datos (el `CHECK` de `patients`) contra una escritura que se salte la API por
completo; la propia API sigue garantizando la regla sin excepción, igual que ya hace con la
validación contra `users-api`, que tampoco es un `CHECK`.

## Project Structure

### Documentation (this feature)

```text
specs/008-subscription-modules-table/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: R1–R9
├── data-model.md                        # Fase 1: tabla subscription_modules, columna que se quita
├── quickstart.md                        # Fase 1: guía de validación (delta sobre 007)
├── contracts/
│   └── database-schema.sql              # Fase 1: esquema completo, con subscription_modules y sin module_keys
│   # openapi-subscriptions.yaml, error-catalog.md, permission-matrix.md, users-api-integration.md,
│   # clinics-api-integration.md, e2e-stubs.md: SIN CAMBIOS (ver 007, 004 y 001; esta feature no
│   # cambia el contrato publicado ni ningún código de error)
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks; aún no existe)
```

### Source Code (repository root)

Todo lo de abajo **ya existe** (de `001`, `004`, `005`, `006` y `007`), salvo lo genuinamente
nuevo (`NUEVO`), lo que esta feature modifica (`MODIFICA`) o lo que deja de tener sentido y se
elimina (`ELIMINA`).

```text
src/
├── models/
│   ├── subscription.py           # MODIFICA: quita la columna `module_keys` y su CheckConstraint;
│   │                              #   + relación `modules: Mapped[list["SubscriptionModule"]]`
│   │                              #   (lazy="raise", order_by="SubscriptionModule.module_key");
│   │                              #   + propiedad de solo lectura `module_keys` (= [m.module_key
│   │                              #   for m in self.modules], research R3/R4)
│   └── subscription_module.py    # NUEVO: SubscriptionModule(Base); __tablename__ =
│                                   #   "subscription_modules"; subscription_id (FK a
│                                   #   subscriptions.id) y module_key, ambos parte de la
│                                   #   PRIMARY KEY compuesta (research R1)
└── repositories/
    ├── transactions.py           # MODIFICA: + variante de execute_and_commit para más de una
    │                              #   sentencia de escritura antes de un único commit, misma
    │                              #   traducción de IntegrityError (research R7)
    └── subscription_repository.py # MODIFICA: _select_with_relations() agrega
                                    #   selectinload(Subscription.modules) (colección uno-a-muchos:
                                    #   selectinload, no joinedload, para no multiplicar filas en
                                    #   list_current()); create() inserta la suscripción y, en la
                                    #   misma transacción, sus filas de módulo; update() saca
                                    #   "module_keys" de `changes` antes del UPDATE de
                                    #   `subscriptions` (que sigue ejecutándose siempre) y, si
                                    #   estaba, reemplaza por completo las filas de
                                    #   subscription_modules (DELETE + INSERT, research R7/R8)

alembic/versions/
└── 0007_subscription_modules_table.py  # NUEVO: crea subscription_modules; migra los datos
                                          #   (INSERT ... SELECT id, unnest(module_keys), research
                                          #   R5); quita el CHECK y la columna module_keys de
                                          #   subscriptions. downgrade(): reconstruye module_keys
                                          #   con array_agg, recrea el CHECK, elimina la tabla
                                          #   (research R6)

tests/
├── helpers.py                           # MODIFICA: insert_subscription() ya no puede mandar
│                                         #   "module_keys" en los values() del INSERT de
│                                         #   Subscription (deja de ser una columna); inserta la
│                                         #   suscripción y, con el id devuelto, sus filas en
│                                         #   subscription_modules, en la misma sesión antes de un
│                                         #   solo commit
├── unit/
│   └── fakes.py                         # MODIFICA: FakeSubscriptionRepository.add() deja de
│                                         #   pasar module_keys al construir Subscription(...) (ya
│                                         #   no es un argumento válido); asigna
│                                         #   subscription.modules = [SubscriptionModule(module_key=k)
│                                         #   for k in sorted(module_keys)] después de construirla,
│                                         #   mismo patrón que ya usa para .status y
│                                         #   .subscription_type; update() saca "module_keys" de
│                                         #   changes y lo traduce al mismo reemplazo de .modules
│                                         #   en vez de usar el setattr genérico (que ya no aplica:
│                                         #   module_keys no tiene setter)
├── integration/
│   ├── test_subscription_repository.py  # MODIFICA: create()/update() comprueban las filas de
│   │                                     #   subscription_modules (no solo created.module_keys,
│   │                                     #   que sigue funcionando igual vía la propiedad); + caso
│   │                                     #   de reemplazo atómico (FR-009) y de que la baja
│   │                                     #   lógica conserva las filas (FR-010)
│   ├── test_subscriptions_constraints.py # ELIMINA test_module_keys_without_patients_is_rejected
│   │                                     #   (el CHECK que probaba ya no existe, research R2: la
│   │                                     #   regla sigue vigente por la API, no por una escritura
│   │                                     #   directa en la base); MODIFICA los otros dos casos de
│   │                                     #   módulos para leer subscription_modules en vez de la
│   │                                     #   columna; + casos nuevos de FR-002 (23505 de la clave
│   │                                     #   primaria compuesta; 23503 de la FOREIGN KEY)
│   └── test_migrations.py               # MODIFICA: el conjunto de columnas de subscriptions ya
│                                         #   NO incluye module_keys tras el head; + caso de
│                                         #   migración de datos (filas insertadas antes de 0007
│                                         #   terminan con las mismas claves en subscription_modules,
│                                         #   research R5) y de reversibilidad (downgrade reconstruye
│                                         #   module_keys igual que estaba, research R6)
└── contract/
    └── test_subscriptions_api.py        # Sin cambios de aserciones salvo una excepción puntual:
                                          #   test_deleting_does_not_touch_modules_prices_or_limits
                                          #   hace hoy `SELECT module_keys, consulting_rooms_limit
                                          #   FROM subscriptions` (SQL crudo contra la columna que
                                          #   se quita); pasa a leer `subscription_modules` por
                                          #   separado para los módulos. El resto del archivo prueba
                                          #   el contrato, que no cambia (FR-004), y se repite tal
                                          #   cual como regresión

tests/postman/collections/
└── MailySoft-System-Suscripciones.postman_collection.json   # SIN CAMBIOS (FR-004): ningún cuerpo
                                                               # ni respuesta esperada cambia

project-definition/
├── DATA_SCHEMA.md                # MODIFICA: + tabla subscription_modules y su fila en «Nombres de
│                                  #   restricciones»; quita subscriptions_module_keys_check de esa
│                                  #   misma tabla; actualiza la lista de migraciones aplicadas
└── create_database.sql           # MODIFICA: igual contenido que contracts/database-schema.sql
```

**Structure Decision**: un archivo de aplicación genuinamente nuevo (`src/models/subscription_module.py`),
simétrico a los modelos ya existentes (`subscription_status.py`, `subscription_type.py`): una tabla
más, el mismo patrón de capas. El resto de los cambios de `src/` son modificaciones de archivos que
ya existen, confinadas a las dos capas que la constitución señala como dueñas de la persistencia
(Modelos y Repositories, Principio I): ninguna capa superior (Service, Router, DTOs) se toca.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación. La única pieza genuinamente nueva de infraestructura
(`execute_and_commit` con más de una sentencia, en `src/repositories/transactions.py`) es una
generalización del mecanismo que ya existe en ese mismo archivo (una escritura, un commit, una
traducción de `IntegrityError`), no una estructura ni un patrón que el proyecto no contemplara ya.

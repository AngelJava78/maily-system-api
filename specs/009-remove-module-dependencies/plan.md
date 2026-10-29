# Implementation Plan: Quitar dependencias entre módulos

**Branch**: `009-remove-module-dependencies` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-remove-module-dependencies/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`src/clinic_modules.py` hoy fija, en código, nueve claves de módulo y cuatro reglas de dependencia
entre ellas (`MODULE_DEPENDENCIES`, aplicadas por `missing_prerequisite`); esas claves ya no existen
en el catálogo real de `users-api`, así que la regla rechaza con 409 suscripciones válidas (p. ej.
«Saturno» con los 18 módulos hoy activos, porque `reminders` exigía `scheduling`). Esta feature
retira esa regla por completo: el único catálogo de módulos válidos pasa a ser, en cada operación,
exactamente lo que `GET /api/v1/modules?type_id=2&status_id=1` devuelva en ese momento; la única
clave que el servicio sigue conociendo de antemano es `patients`.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Dónde se quita (R1)**: el único bloque local (sin red) de `SubscriptionService._resolve_modules`
  que llamaba a `missing_prerequisite` y lanzaba `SubscriptionModulePrerequisiteMissingError`. El
  resto de `_resolve_modules` (patients siempre incluido, sin llamada si solo se pide patients,
  validar contra el catálogo de `users-api`, devolver ordenado) no cambia de forma.
- **Qué queda de `src/clinic_modules.py` (R2)**: solo `PATIENTS_KEY`. Se eliminan
  `CLINIC_MODULE_KEYS`, `MODULE_DEPENDENCIES` y `missing_prerequisite` enteros (FR-004), no solo su
  contenido.
- **Qué se elimina del catálogo de errores (R3)**: `SubscriptionModulePrerequisiteMissingError`,
  `ErrorCode.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING` y su mensaje, completos (FR-005).
  `src/error_handlers.py` no se toca: las tres excepciones de módulos son subclases planas de
  `AppError` sin lógica especial por tipo.
- **Sin versionar el contrato (R4)**: `VERSION` se queda en `4.0.0`. Aflojar una validación nunca
  rompe a quien ya tenía éxito, y un código de error que el servidor ya no emite no es algo que un
  cliente necesite seguir reconociendo; ninguna de las dos cosas es un cambio incompatible
  (Principio IV).
- **Contratos que se vuelven a publicar (R5, R6)**: copia completa de
  `contracts/openapi-subscriptions.yaml` (supersede a `007`); documentos delta de
  `contracts/error-catalog.md`, `contracts/users-api-integration.md` y `contracts/e2e-stubs.md`
  (sobre `004`, que es donde se documentó esta integración por última vez). `permission-matrix.md`,
  `clinics-api-integration.md` y el esquema de base de datos no cambian: no se vuelven a publicar.
  Las carpetas de specs ya cerradas (`004` a `008`) no se editan.
- **Catálogo de prueba del stub (R7)**: `tests/stubs/users_api/app.py` deja de sembrar los 9
  módulos obsoletos que copiaba de `src/clinic_modules.py` y pasa a sembrar las 18 claves reales
  que `spec.md` usa en sus propios criterios de aceptación; `scheduling` deja de estar sembrada a
  propósito, para servir de ejemplo de «módulo no reconocido» (Historia 2).
- **Pruebas que se eliminan, se invierten o se dejan igual (R8)**: detalle completo en
  [research.md](research.md#r8--pruebas-que-se-eliminan-se-invierten-o-se-dejan-igual); las
  pruebas de catálogo/formato/`patients`/`module_check_unavailable` no cambian porque prueban
  capas que esta feature no toca.

## Technical Context

**Language/Version**: Python 3.14+ (sin cambios)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, uvicorn,
httpx. Sin dependencias nuevas; ninguna se retira.

**Storage**: PostgreSQL 17; **sin ninguna migración nueva** (ver [data-model.md](data-model.md)):
esta feature es puramente de código (Service, catálogo de errores, documentación del contrato),
no de esquema.

**Testing**: pytest + pytest-asyncio + httpx, igual que `001`/`004`/`006`/`007`/`008`. Dos niveles
de ejecución (Principio V, v1.1.0): `/speckit-implement` de esta feature MUST limitarse a la
corrida rápida por defecto (unitarias, sin PostgreSQL real); las de contrato de esta feature (que
sí cambian, ver [quickstart.md](quickstart.md)) y la colección de Postman automatizada (que sí
cambia, a diferencia de `008`) quedan para la puerta de calidad antes de integrar a `main`.

**Target Platform**: igual que `008` (contenedor Linux, Docker Compose). Sin componentes nuevos de
despliegue.

**Project Type**: web-service (corrección de una regla de negocio sobre una feature existente)

**Performance Goals**: sin cambios de forma; si acaso, una llamada menos de CPU por operación (ya
no se evalúa `missing_prerequisite`), sin ninguna llamada de red nueva ni menos.

**Constraints**: las mismas de `008`, sin ninguna nueva.

**Scale/Scope**: mismas 6 operaciones y los mismos 4 permisos externos; ningún permiso nuevo;
**cero** migraciones, **cero** tablas o columnas nuevas; **se retira un** código de error (de 18
quedan 17, ver R3); **cero** campos nuevos de los DTOs (`module_keys` conserva su tipo, su patrón y
sus límites).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas | ✅ Solo se tocan `src/clinic_modules.py`, `src/services/`, `src/exceptions.py`, `src/messages.py` y la descripción de `src/routers/subscriptions.py`; sin Repositories, modelos ni DTOs | ✅ La regla vivía en el Service (Principio I: ahí vive toda regla de negocio) y solo ahí se quita; el Router solo pierde texto de documentación, no lógica |
| II. Modelos ≠ DTOs | ✅ Sin cambios | ✅ Los DTOs de `module_keys` (tipo, patrón, límites) no cambian ni una línea; solo cambia una frase de su `description` |
| III. Asincronía | ✅ Sin cambios | ✅ `_resolve_modules` sigue haciendo como mucho una llamada async a `users-api`; se quita un chequeo local (sin I/O), no se agrega ninguno |
| IV. OpenAPI y REST | ✅ Cambia una descripción, un ejemplo y el `enum` de `ErrorResponse.code`; ningún cambio incompatible (R4) | ✅ `contracts/openapi-subscriptions.yaml` (copia completa) documenta exactamente ese delta sin subir `version` (R4); razonado explícitamente, no una omisión |
| V. Pruebas pytest | ✅ | ✅ Dos niveles de ejecución sin cambios respecto a `008`; se eliminan/invierten/ajustan pruebas exactamente donde cambia el comportamiento (R8), el resto se repite sin modificar sus aserciones |
| VI. Migraciones Alembic | ✅ Sin cambios: ninguna migración nueva | ✅ Confirmado en [data-model.md](data-model.md): cero cambios de esquema, `DATA_SCHEMA.md` y `create_database.sql` no se tocan |
| VII. Idioma | ✅ | ✅ Sin identificadores nuevos que no estén en inglés; los mensajes que se retiran lo hacen enteros (código + texto en español), sin dejar ninguno a medias |
| VIII. Control de acceso delegado | ✅ Sin cambios | ✅ Mismos 4 permisos, sin ninguno nuevo |
| IX. Integraciones | ✅ Sin cambios de forma; se documenta en `contracts/users-api-integration.md` que ya no hay ningún catálogo mínimo asumido | ✅ El catálogo de módulos sigue siendo propiedad exclusiva de `users-api`, consultado igual que siempre; esta feature hace esa propiedad más estricta (cero suposiciones de claves fijas), no menos |
| Stack obligatorio | ✅ | ✅ Sin dependencias nuevas |
| Flujo y puertas de calidad | ✅ | ✅ Constitution Check incluido |

**Resultado**: PASS contra los principios I a IX, sin necesidad de enmendar la constitución. Única
nota de transparencia (no una violación, igual estilo que R2 de `008`): R4 decide explícitamente no
versionar el contrato pese a que el catálogo de errores cambia; la justificación (aflojar una
validación y retirar un código que el servidor ya no emite son, ambos, compatibles hacia atrás) se
documenta en detalle en `research.md` para que el responsable del proyecto pueda revisarla y, si lo
prefiere, pedir lo contrario sin que eso afecte ningún otro aspecto de esta feature.

## Project Structure

### Documentation (this feature)

```text
specs/009-remove-module-dependencies/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: R1–R8
├── data-model.md                        # Fase 1: sin cambios de esquema
├── quickstart.md                        # Fase 1: guía de validación (delta sobre 008)
├── contracts/
│   ├── openapi-subscriptions.yaml       # Fase 1: copia completa, supersede a 007
│   ├── error-catalog.md                 # Fase 1: delta sobre 004 (se retira 1 código)
│   ├── users-api-integration.md         # Fase 1: delta sobre 004 (sin paso de dependencias)
│   └── e2e-stubs.md                     # Fase 1: delta sobre 004 (catálogo sembrado nuevo)
│   # permission-matrix.md, clinics-api-integration.md, database-schema.sql: SIN CAMBIOS (ver
│   # specs/007-add-clinics-limit y specs/008-subscription-modules-table; esta feature no agrega
│   # ni quita ningún permiso, no toca el API de clínicas ni el esquema de base de datos)
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks; aún no existe)
```

### Source Code (repository root)

Todo lo de abajo **ya existe**; esta feature no crea ningún archivo de aplicación nuevo, solo
modifica los que ya tienen la regla que se retira (`MODIFICA`) o reduce los que quedan con menos
contenido del que tenían (`REDUCE`).

```text
src/
├── clinic_modules.py              # REDUCE: queda solo PATIENTS_KEY y su docstring; se eliminan
│                                   #   CLINIC_MODULE_KEYS, MODULE_DEPENDENCIES y
│                                   #   missing_prerequisite enteros (FR-004, research R2)
├── services/
│   └── subscription_service.py   # MODIFICA: _resolve_modules pierde el bloque local (sin red)
│                                   #   que llamaba a missing_prerequisite y lanzaba
│                                   #   SubscriptionModulePrerequisiteMissingError; se quita ese
│                                   #   import y el de missing_prerequisite (el de PATIENTS_KEY se
│                                   #   conserva, research R1)
├── exceptions.py                   # MODIFICA: elimina la clase
│                                   #   SubscriptionModulePrerequisiteMissingError entera y el
│                                   #   import de su mensaje (research R3)
├── messages.py                     # MODIFICA: elimina
│                                   #   ErrorCode.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING y
│                                   #   SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE; el
│                                   #   docstring del módulo pasa a citar también
│                                   #   specs/009-remove-module-dependencies/contracts/error-catalog.md
│                                   #   como fuente de los mensajes de módulos que sobreviven
└── routers/
    └── subscriptions.py           # MODIFICA: quita el ejemplo prerrequisito_faltante de
                                    #   WRITE_CONFLICT; las descripciones de create_subscription y
                                    #   update_subscription dejan de mencionar «y contra las
                                    #   dependencias de esta API»

tests/
├── unit/
│   ├── test_clinic_modules.py     # REDUCE: solo queda test_patients_key; se eliminan las
│   │                               #   pruebas de CLINIC_MODULE_KEYS/MODULE_DEPENDENCIES/
│   │                               #   missing_prerequisite (research R8)
│   ├── test_subscription_service.py  # MODIFICA: quita el import de
│   │                               #   SubscriptionModulePrerequisiteMissingError y las dos
│   │                               #   pruebas de dependencias (crear y actualizar); el resto
│   │                               #   (patients siempre incluido, subscription_module_not_found,
│   │                               #   module_check_unavailable, sin llamada con solo patients)
│   │                               #   no cambia de aserciones
│   └── test_error_messages.py     # MODIFICA: quita el import, la entrada en EXPECTED_MESSAGES,
│                                   #   el caso parametrizado de la excepción, y ajusta a 17 el
│                                   #   recuento/nombre de «todos los códigos del catálogo»
├── contract/
│   └── test_subscriptions_api.py  # MODIFICA: invierte (ahora esperan 201/200, no 409)
│                                   #   test_a_module_without_its_prerequisite_is_a_conflict y
│                                   #   test_updating_to_a_module_without_its_prerequisite_is_a_conflict_and_nothing_changes
│                                   #   (son los Acceptance Scenarios 2 y 3 de la Historia 1); +
│                                   #   caso nuevo del Acceptance Scenario 1 (Saturno, 18 módulos);
│                                   #   ajusta el comentario (no la aserción) de
│                                   #   test_excluding_a_module_does_not_exclude_what_depends_on_it;
│                                   #   el resto (not_found, unavailable, reemplazo completo) no
│                                   #   cambia de aserciones (research R8)
└── stubs/
    └── users_api/
        └── app.py                 # MODIFICA: CLINIC_MODULE_NAMES pasa de las 9 claves obsoletas
                                    #   (copiadas en su momento de src/clinic_modules.py) a las 18
                                    #   claves reales de spec.md; scheduling deja de estar
                                    #   sembrada, para servir de ejemplo de «módulo no reconocido»
                                    #   (research R7)

tests/postman/collections/
└── MailySoft-System-Suscripciones.postman_collection.json   # MODIFICA: elimina el request del
                                                               # 409 de prerrequisito; agrega el de
                                                               # «Saturno» con los 18 módulos;
                                                               # actualiza los cuerpos de ejemplo
                                                               # que usaban claves retiradas
                                                               # (detalle en contracts/e2e-stubs.md)
```

**No se tocan** (confirmado en el inventario de research, sin cambios de aserciones ni de forma):
`src/integrations/users_api.py` (el cliente HTTP nunca conoció la regla de dependencias),
`src/error_handlers.py` (sin lógica especial por tipo de excepción), `src/dtos/subscription.py`
(ningún validador de catálogo/dependencias vivía ahí), `tests/unit/fakes.py` (`FakeUsersApi` ya
recibe su catálogo como parámetro), `tests/contract/test_users_api_client.py`,
`tests/unit/test_subscription_dtos.py`, las pruebas de integración de Repository/migraciones/
restricciones (usan `module_keys` como strings arbitrarios de round-trip, nunca la regla de
dependencias), `project-definition/DATA_SCHEMA.md` y `project-definition/create_database.sql`.

**Structure Decision**: ninguna capa nueva ni archivo de aplicación nuevo. Todos los cambios de
`src/` caen exactamente en la capa que la constitución señala como dueña de las reglas de negocio
de módulos (el Service, Principio I) y en los dos archivos de vocabulario compartido que esa regla
necesitaba (`clinic_modules.py`, `exceptions.py`/`messages.py`); el Router solo pierde texto de
documentación, nunca lógica. Es, en ese sentido, el espejo exacto de `008`: una corrección que
demuestra la separación de capas en vez de necesitar romperla.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación. No hay ninguna pieza de infraestructura nueva que justificar: esta feature solo
elimina código y documentación que ya existían.

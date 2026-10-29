---

description: "Task list for feature 009-remove-module-dependencies (quitar dependencias entre módulos)"
---

# Tasks: Quitar dependencias entre módulos

**Input**: Design documents from `/specs/009-remove-module-dependencies/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md.
Requiere la **constitución v1.1.0** vigente (sin cambios). `008-subscription-modules-table` ya
está en `main`.

**Tests**: Incluidas (Principio V). Esta feature **retira comportamiento** (una validación y un
código de error), así que "escribir la prueba primero" significa, en varios casos, invertir una
prueba ya existente (que hoy espera 409) para que espere éxito, y comprobar que **sigue fallando**
contra el código actual antes de tocarlo.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). US1 (P1) es el
único cambio de comportamiento observable; US2 (P2) y US3 (P3) demuestran, con pruebas nuevas, dos
garantías que ya quedan ciertas en cuanto termina la Fase Foundational (ninguna de las dos necesita
código de implementación propio).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1, US2, US3); sin etiqueta en Setup,
  Foundational y Polish

## Referencias rápidas

- Decisiones: [research.md](research.md) (R1–R8)
- Sin cambios de esquema: [data-model.md](data-model.md)
- Guía de validación: [quickstart.md](quickstart.md)
- Contrato HTTP objetivo (copia completa, 17 códigos de error): [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
- Delta del catálogo de errores, de la integración con `users-api` y de las simulaciones:
  [contracts/error-catalog.md](contracts/error-catalog.md),
  [contracts/users-api-integration.md](contracts/users-api-integration.md),
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: hacer commits (solo si la persona lo pide); modificar `.specify/feature.json`;
  escribir tokens, contraseñas o secretos reales en cualquier archivo; añadir dependencias fuera de
  la tabla del stack; tocar `specs/001-subscriptions-api/` a `specs/008-subscription-modules-table/`
  (quedan como registro histórico, research R6).
- **`VERSION` NO cambia** (sigue en `"4.0.0"`, research R4): esta feature no versiona el contrato.
- **Sin migraciones**: `project-definition/DATA_SCHEMA.md` y `create_database.sql` no se tocan
  (data-model.md).
- **El catálogo real de 18 módulos** (criterios de aceptación de `spec.md`): `appointments`,
  `billing`, `clinics`, `consulting_rooms`, `expenses`, `finance`, `incomes`, `overview`,
  `patient_diagnoses`, `patients`, `prescriptions`, `reminders`, `reports`, `schedule`, `services`,
  `staff`, `templates`, `vital_signs`.
- **`scheduling`, `clinical_records` y `clinical_record_templates` dejan de ser válidas** en el
  catálogo de prueba (research R7): cualquier prueba que las use para demostrar éxito debe migrar a
  una clave del catálogo real de arriba; cualquier prueba que las use para demostrar un rechazo
  (por dependencia, ya eliminada) debe invertirse o eliminarse, no migrarse.

---

## Phase 1: Setup

**Purpose**: Confirmar el punto de partida y reproducir el defecto que esta feature corrige.

- [X] T001 Verificar prerrequisitos: `git status --short` no muestra cambios sin seguimiento fuera
  de `specs/009-remove-module-dependencies/`; `.specify/feature.json` contiene
  `"feature_directory": "specs/009-remove-module-dependencies"`; `uv run pytest` (corrida rápida)
  está en verde (línea base, con `008` ya integrada). Reproducir el defecto manualmente: con
  `docker compose up -d db` y la app corriendo, un `POST /api/v1/subscriptions` con
  `module_keys: ["reminders"]` (sin `schedule` ni `appointments`) responde **409**
  `subscription_module_prerequisite_missing` — este es el estado "rojo" que las Fases 2 y 3
  corrigen.

**Checkpoint**: línea base confirmada y el defecto reproducido antes de tocar ningún archivo.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: quitar el único punto donde vive la regla de dependencias (research R1), retirar el
código de error que esa regla producía (R3) y poner al día el catálogo de módulos de prueba (R7)
— sin esto, ninguna de las tres historias se puede verificar de forma significativa.

### Tests (escribirlos primero; deben fallar contra el código actual, que todavía aplica dependencias)

- [X] T002 [P] En `tests/contract/test_subscriptions_api.py`: arreglar las dos pruebas que hoy
  dependen de que el stub de `users-api` siga teniendo `scheduling`/`clinical_records` como válidas
  (consecuencia de T006, no un cambio de comportamiento):
  - El diccionario `PRO` (línea ~41-51) pasa de `module_keys: ["scheduling", "reminders",
    "clinical_records"]` a `["appointments", "reminders", "prescriptions"]` (tres claves del
    catálogo real, sin ninguna relación de dependencia entre ellas: ya no existe esa regla).
  - `test_creating_a_subscription_answers_201_with_everything_the_contract_promises` (línea ~291):
    la aserción `body["module_keys"] == ["clinical_records", "patients", "reminders",
    "scheduling"]` pasa a `== ["appointments", "patients", "prescriptions", "reminders"]` (orden
    alfabético de las nuevas claves + `patients`).
  - `test_patients_is_always_included_even_if_the_request_excludes_it` (línea ~442-447):
    `module_keys=["scheduling"]` pasa a `module_keys=["reminders"]`; la aserción
    `== ["patients", "scheduling"]` pasa a `== ["patients", "reminders"]`.
  - El comentario de la línea 33 (`# The nine clinic-module keys the stub seeds by default
    (src/clinic_modules.py)`) se corrige: ya no son nueve ni vienen de `src/clinic_modules.py`
    (research R7); apuntar a [contracts/e2e-stubs.md](contracts/e2e-stubs.md).
  - Debe **fallar** contra el stub actual (9 claves viejas) y pasar después de T006.
- [X] T003 [P] En `tests/unit/test_subscription_service.py`: eliminar
  `test_create_with_a_dependent_module_without_its_prerequisite_fails_without_asking_the_users_api`
  y `test_updating_to_a_module_without_its_prerequisite_fails_and_nothing_changes` (ambas prueban
  la regla de dependencias que esta feature retira, FR-003); quitar el import de
  `SubscriptionModulePrerequisiteMissingError`. El resto del archivo (catálogo no reconocido,
  `module_check_unavailable`, `patients` siempre incluido, sin llamada con solo `patients`) no
  cambia. Debe seguir **pasando** tal cual contra el código actual (las dos pruebas que se quitan
  siguen en verde hasta que T007 cambie el comportamiento); el punto de esta tarea es dejar el
  archivo listo para cuando T007 lo vuelva rojo y luego verde.
- [X] T004 [P] En `tests/unit/test_error_messages.py`: quitar el import de
  `SubscriptionModulePrerequisiteMissingError`, su entrada en `EXPECTED_MESSAGES`, y el caso
  parametrizado de `test_every_error_has_its_code_status_headers_and_message` que la usa. Ajustar
  `test_the_error_codes_are_exactly_the_eighteen_of_the_catalog` (nombre y el set literal): quita
  `"subscription_module_prerequisite_missing"` y pasa a esperar **17** códigos, no 18. Debe
  **fallar** contra el código actual (el `ErrorCode` todavía tiene 18 miembros) y pasar después de
  T008.

### Implementation

- [X] T005 En `src/services/subscription_service.py`: en `_resolve_modules` (el método que
  construye `wanted`/`extra` y valida contra la API de usuarios), quitar por completo el bloque
  local (sin red) que llama a `missing_prerequisite(wanted)` y, si devuelve un par, lanza
  `SubscriptionModulePrerequisiteMissingError(*pair)`. El resto del método no cambia de forma:
  `wanted = frozenset(requested or ()) | {PATIENTS_KEY}`; si `extra` (`wanted - {PATIENTS_KEY}`)
  está vacío, `return [PATIENTS_KEY]` sin llamar a la API; si no, llamar a
  `self._users_api.list_clinic_module_keys(token)` (traduciendo `UsersApiUnavailable` a
  `ModuleCheckUnavailableError`), calcular `unknown = extra - valid`, lanzar
  `SubscriptionModuleNotFoundError(sorted(unknown)[0])` si `unknown` no está vacío, y `return
  sorted(wanted)`. Quitar el import de `missing_prerequisite` (se conserva el de `PATIENTS_KEY`) y
  el de `SubscriptionModulePrerequisiteMissingError`. Hace pasar T003 (research R1).
- [X] T006 [P] En `tests/stubs/users_api/app.py`: reemplazar `CLINIC_MODULE_NAMES` (las 9 claves
  obsoletas que copiaba de `src/clinic_modules.py`) por las 18 claves reales listadas en
  Convenciones, con un nombre en español razonable para cada una (mismo patrón que las entradas ya
  existentes: `"appointments": "Citas"`, etc.). `scheduling`, `clinical_records` y
  `clinical_record_templates` dejan de estar sembradas. No tocar `SYSTEM_MODULE_NAMES` ni
  `default_modules()` (solo cambia el contenido del diccionario, no su forma). Hace pasar T002
  (research R7).
- [X] T007 [P] En `src/clinic_modules.py`: quitar `CLINIC_MODULE_KEYS`, `MODULE_DEPENDENCIES` y
  `missing_prerequisite` enteros; solo queda `PATIENTS_KEY = "patients"` y un docstring que explique
  por qué esa única clave sigue siendo una constante de este servicio (research R2). Depende de
  T005 (nada debe importar ya lo que se quita).
- [X] T008 [P] En `src/exceptions.py` y `src/messages.py`: eliminar la clase
  `SubscriptionModulePrerequisiteMissingError` entera (y el import de su mensaje en
  `exceptions.py`); eliminar `ErrorCode.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING` y
  `SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE` de `messages.py`. Actualizar el docstring de
  `messages.py` (líneas 6-9) para citar también
  `specs/009-remove-module-dependencies/contracts/error-catalog.md` como fuente de los mensajes de
  módulos que sobreviven. Depende de T005 (nada debe lanzarla ya). Hace pasar T004 (research R3).
- [X] T009 [P] En `src/routers/subscriptions.py`: quitar el ejemplo `prerrequisito_faltante` de
  `WRITE_CONFLICT` (el diccionario de ejemplos del 409 reutilizado por `create_subscription` y
  `update_subscription`); en la descripción de `create_subscription`, quitar la frase sobre
  validar "contra las dependencias de esta API..."; en la de `update_subscription`, quitar la
  referencia equivalente. El texto final debe coincidir con
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml) (ya escrito en
  `/speckit-plan`). Depende de T008 (el código que cita ya no existe).

**Checkpoint**: `uv run pytest` (corrida rápida) en verde, incluidos T002, T003 (sin las dos
pruebas eliminadas), T004; con `docker compose up -d db`, `uv run pytest -m ""` también en verde
(confirma T002/T006 contra el stub real). Visitar `/docs` o `/openapi.json` y confirmar que
`ErrorResponse.code` ya no incluye `subscription_module_prerequisite_missing` (17 valores) y que
ningún ejemplo de `create_subscription`/`update_subscription` lo menciona.

---

## Phase 3: User Story 1 - Crear o modificar una suscripción con cualquier combinación de módulos vigentes (Priority: P1) 🎯 MVP

**Goal**: ninguna combinación de módulos del catálogo activo se rechaza ya por dependencia
(FR-001, FR-003); el escenario concreto que motivó esta feature (el plan «Saturno» con los 18
módulos activos) se puede crear.

**Independent Test**: ver [spec.md](spec.md#user-story-1---crear-o-modificar-una-suscripción-con-cualquier-combinación-de-módulos-vigentes-priority-p1).

### Tests for User Story 1 (invertir las que ya existen; deben fallar contra el código previo a la Fase 2, y pasar después)

- [X] T010 [US1] En `tests/contract/test_subscriptions_api.py`:
  - Invertir `test_a_module_without_its_prerequisite_is_a_conflict` (Acceptance Scenario 3,
    `billing` sin `finance`): ahora espera **201**, no 409; el cuerpo de la respuesta incluye
    `"billing"` en `module_keys` (junto con `"patients"`) y la fila sí queda en
    `subscriptions`/`subscription_modules`. Renombrar a algo como
    `test_a_module_without_what_used_to_be_its_prerequisite_is_accepted`.
  - Invertir `test_updating_to_a_module_without_its_prerequisite_is_a_conflict_and_nothing_changes`
    (Acceptance Scenario 2 al actualizar, `billing` solo): ahora espera **200**, no 409; tras la
    actualización, `module_keys` es `["billing", "patients"]` (ya no `["patients", "scheduling"]`,
    el valor previo). Renombrar en consecuencia.
  - Agregar `test_creating_saturno_with_all_eighteen_active_modules_is_accepted` (Acceptance
    Scenario 1): `POST /api/v1/subscriptions` con los 18 `module_keys` del catálogo real (ver
    Convenciones) más los demás campos obligatorios → 201; `module_keys` de la respuesta son los
    18 más `patients` (19 en total), ordenados alfabéticamente.
  - Ajustar el comentario de `test_excluding_a_module_does_not_exclude_what_depends_on_it` (línea
    ~115, "billing depende de finance"): ya no hay dependencia que explicar; reformular como
    "excluir un módulo no excluye ningún otro, sean o no afines" (research R8). La aserción no
    cambia.
  - Depende de T005 (comportamiento) y T006/T002 (catálogo del stub ya al día).

### Implementation for User Story 1

Ninguna: la Fase Foundational (T005) ya implementa la ausencia de dependencias que esta historia
prueba.

**Checkpoint**: `docker compose up -d db && uv run pytest tests/contract/test_subscriptions_api.py
-m ""` en verde.

---

## Phase 4: User Story 2 - Rechazar un módulo que no existe en el catálogo activo de la API de usuarios (Priority: P2)

**Goal**: una clave retirada del catálogo real (el ejemplo de `spec.md`: `scheduling`) se sigue
rechazando con `subscription_module_not_found`, ahora que la validación de catálogo es la única
que queda (FR-002).

**Independent Test**: ver [spec.md](spec.md#user-story-2---rechazar-un-módulo-que-no-existe-en-el-catálogo-activo-de-la-api-de-usuarios-priority-p2).

### Tests for User Story 2 (ya existen pruebas genéricas de este caso; se amplían con el ejemplo literal de `spec.md`)

- [X] T011 [P] [US2] En `tests/unit/test_subscription_service.py`: parametrizar (o añadir un caso
  a) la prueba existente de módulo no reconocido con `"scheduling"` como la clave que la API de
  usuarios ya no reconoce (hoy esa prueba usa una clave inventada cualquiera): confirmar
  `SubscriptionModuleNotFoundError("scheduling")`. No afecta el caso ya existente con una clave
  arbitraria, que se conserva.
- [X] T012 [P] [US2] En `tests/contract/test_subscriptions_api.py`: parametrizar (o añadir un caso
  a) `test_an_unrecognised_module_is_a_validation_error` con `module_keys=["scheduling"]` (en vez
  de, o además de, `"no_existe"`), esperando 422 `subscription_module_not_found` con el mensaje
  citando `«scheduling»`. Depende de T006 (el stub ya no debe sembrar `scheduling`).

### Implementation for User Story 2

Ninguna: `SubscriptionService._resolve_modules` (sin cambios desde antes de esta feature para este
caso) ya rechaza cualquier clave fuera del catálogo que devuelva la API de usuarios.

**Checkpoint**: `uv run pytest` (T011, rápida) y, con `docker compose up -d db`, `uv run pytest
tests/contract/test_subscriptions_api.py -m ""` (T012) en verde.

---

## Phase 5: User Story 3 - Un módulo nuevo se puede usar sin cambiar código de este servicio (Priority: P3)

**Goal**: demostrar, con una clave que nunca existió en ningún catálogo ni en ningún código de
este servicio, que se acepta igual que cualquier otra — porque no hay ninguna lista fija que
actualizar (FR-004); y que `src/clinic_modules.py` en efecto no tiene ya ninguna lista de ese tipo.

**Independent Test**: ver [spec.md](spec.md#user-story-3---un-módulo-nuevo-se-puede-usar-sin-cambiar-código-de-este-servicio-priority-p3).

### Tests for User Story 3 (escribirlas primero; deben fallar si quedara cualquier lista fija)

- [X] T013 [P] [US3] En `tests/unit/test_subscription_service.py`: nueva prueba (p. ej.
  `test_a_brand_new_module_the_service_never_coded_is_accepted`) que configura `FakeUsersApi` con
  `clinic_module_keys=frozenset({PATIENTS_KEY, "un_modulo_que_nadie_codifico"})` (una clave
  inventada que no aparece en ningún otro archivo del repositorio) y confirma que crear con
  `module_keys=["un_modulo_que_nadie_codifico"]` tiene éxito. Debe fallar si algún código todavía
  comparara contra una lista fija de claves conocidas (ya no debería haber ninguna tras T005/T007).
- [X] T014 [P] [US3] Reducir `tests/unit/test_clinic_modules.py` a solo `test_patients_key`:
  eliminar todas las pruebas de `CLINIC_MODULE_KEYS`, `MODULE_DEPENDENCIES` y
  `missing_prerequisite` (ya no existen tras T007). Depende de T007.

### Implementation for User Story 3

Ninguna: T005 (ningún chequeo local contra una lista fija) y T007 (`src/clinic_modules.py` sin
`CLINIC_MODULE_KEYS` ni `MODULE_DEPENDENCIES`) ya implementan lo que esta historia prueba.

**Checkpoint**: `uv run pytest tests/unit/test_subscription_service.py
tests/unit/test_clinic_modules.py` en verde.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: confirmar que nada de lo que no debía cambiar, cambió, y poner al día la colección de
Postman (que sí cambia, a diferencia de `008`).

- [X] T015 [P] Actualizar `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`
  según [contracts/e2e-stubs.md](contracts/e2e-stubs.md): eliminar el request del 409 de
  prerrequisito; agregar el de «Saturno» con los 18 módulos (201); actualizar los cuerpos de
  ejemplo que usaban `scheduling`/`clinical_records`/`clinical_record_templates` como válidas al
  catálogo nuevo. Esta tarea no se ejecuta con Newman aquí (eso es la puerta de calidad, T017);
  solo edita el JSON.
- [X] T016 [P] Confirmar, sin editar nada: `src/__init__.py` (`VERSION`) sigue en `"4.0.0"`; `uv
  run pytest tests/unit/test_version.py` en verde; el esquema servido en `/openapi.json` tiene
  `info.version: "4.0.0"` y coincide con
  [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml).
- [X] T017 Verificación final (lo único que corre en esta implementación): `uv run pytest` (corrida
  rápida, sin DB) en verde. Dejar anotado para quien integre a `main` que falta correr la puerta
  completa: `docker compose up -d db && uv run pytest -m ""` (incluye T002, T010, T012) y, aparte,
  Newman sobre `MailySoft-System-Suscripciones.postman_collection.json` (Nivel 3 de
  [quickstart.md](quickstart.md)) — ninguna de las dos se ejecuta como parte de esta tarea.
- [X] T018 [P] Revisión final de documentación (sin ejecutar nada contra una base de datos):
  confirmar que ninguna mención de `subscription_module_prerequisite_missing` sobrevive en
  `src/`, `tests/` ni `tests/postman/collections/` (`grep -r
  subscription_module_prerequisite_missing src tests` sin resultados, salvo en los documentos
  históricos de `specs/004` a `specs/008`, que no se tocan).

**Checkpoint final de esta implementación**: `uv run pytest` en verde (solo pruebas unitarias).
Pendiente, antes de integrar a `main` (fuera de `/speckit-implement`): `uv run pytest -m ""` +
Newman, según T017.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** US1, US2 y US3 (las tres dependen de
  que la regla de dependencias ya no exista y de que el stub tenga el catálogo nuevo).
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: dependen solo de Foundational; no
  dependen entre sí.
- **Polish (Phase 6)**: depende de todas las fases anteriores.

### Dentro de Foundational

T002, T003, T004 (pruebas) son `[P]` entre sí (archivos distintos). T005 (el cambio de
comportamiento en el Service) depende de que T003 ya esté escrita (para poder confirmar que la
vuelve roja y luego verde), pero no de T002/T004. T006 (stub) es `[P]` respecto a T005/T007/T008
(archivo distinto). T007 (`clinic_modules.py`) depende de T005. T008
(`exceptions.py`/`messages.py`) depende de T005. T009 (`routers/subscriptions.py`) depende de T008.

### Archivos compartidos (límite real del paralelismo)

`tests/contract/test_subscriptions_api.py` se toca en Foundational (T002, arregla lo que rompe el
catálogo nuevo del stub) y en US1 (T010, invierte/agrega casos) y en US2 (T012, agrega el caso de
`scheduling`): T002 primero, T010 y T012 después, mismo archivo, sin `[P]` entre ninguna de las
tres. `tests/unit/test_subscription_service.py` se toca en Foundational (T003, quita las dos
pruebas de dependencias), en US2 (T011) y en US3 (T013): mismo orden relativo (T003 primero).
`src/clinic_modules.py` (T007) y `tests/unit/test_clinic_modules.py` (T014, US3) están
relacionados pero son archivos distintos: T014 depende de T007, no comparten archivo.

### Parallel Opportunities

- Foundational: T002, T003, T004 (pruebas) son `[P]` entre sí; T006 es `[P]` respecto a
  T005/T007/T008/T009 (cadena secuencial por dependencia real, no por archivo compartido).
- US1: una sola tarea (T010).
- US2: T011 y T012 son `[P]` entre sí (archivos distintos).
- US3: T013 y T014 son `[P]` entre sí (archivos distintos).
- Polish: T015, T016 y T018 son `[P]` entre sí; T017 (verificación final) se ejecuta aparte, al
  final.

---

## Parallel Example: Foundational

```bash
# Escribir a la vez las pruebas que deben fallar primero (archivos distintos):
Task: "Arreglar PRO y el caso de patients-siempre-incluido en tests/contract/test_subscriptions_api.py"
Task: "Quitar las dos pruebas de dependencias en tests/unit/test_subscription_service.py"
Task: "Ajustar el catálogo de 18 a 17 códigos en tests/unit/test_error_messages.py"

# Después de T005 (el cambio real), en paralelo:
Task: "Catálogo de 18 módulos reales en tests/stubs/users_api/app.py"
```

---

## Implementation Strategy

### MVP (Foundational + US1)

1. Completar Phase 1 (Setup: reproducir el 409 de «Saturno»).
2. Completar Phase 2 (Foundational: quitar la regla, el error y poner al día el stub).
3. Completar Phase 3 (US1: los casos invertidos y «Saturno» en verde).
4. **DETENERSE y validar**: `uv run pytest` (rápido) en verde; `docker compose up -d db && uv run
   pytest tests/contract/test_subscriptions_api.py -m ""` en verde. El Nivel 3 de
   [quickstart.md](quickstart.md) (Newman) queda para la puerta de calidad antes de integrar.

### Incremental Delivery

1. Foundational → la regla de dependencias ya no existe en ningún punto del código; el stub tiene
   el catálogo real.
2. + US1 (MVP) → «Saturno» y las combinaciones antes rechazadas por dependencia ahora se aceptan.
3. + US2 → confirmado, con el ejemplo literal de `spec.md`, que un módulo retirado (`scheduling`)
   sigue rechazándose.
4. + US3 → confirmado que un módulo nunca antes visto se acepta igual, y que no queda ninguna
   lista fija que mantener.
5. Polish → Postman al día; `VERSION` y el catálogo de errores confirmados; cero menciones
   sobrevivientes del error retirado. La puerta completa (`uv run pytest -m ""` + Newman) se corre
   antes de integrar a `main`, fuera de esta implementación (Principio V).

---

## Notes

- `[P]` = archivos distintos y sin dependencias abiertas; `[Story]` = trazabilidad con la spec.
- A diferencia de `008`, esta feature **retira** comportamiento: varias "pruebas nuevas" de este
  plan son, en realidad, pruebas ya existentes invertidas (de esperar 409 a esperar éxito), no
  pruebas añadidas desde cero.
- Verificar que las pruebas de contrato/integración (T002, T010, T012) **fallan** antes de
  implementar y pasan después: al estar marcadas `slow` por defecto, eso significa correrlas con
  `-m ""` mientras se escriben, no dejarlas correr solas por defecto.
- No hacer commits salvo que la persona los pida.
- La colección manual (`002-manual-postman-collection`) no se toca en esta feature (decisión del
  responsable, 2026-10-27): queda como registro histórico.

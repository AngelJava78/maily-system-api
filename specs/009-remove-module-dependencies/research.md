# Research: quitar dependencias entre módulos

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## R1 — Dónde se quita la validación de dependencias

**Decisión**: se elimina por completo el bloque de `SubscriptionService._resolve_modules`
(`src/services/subscription_service.py`) que llama a `missing_prerequisite(wanted)` y lanza
`SubscriptionModulePrerequisiteMissingError`. Ese chequeo es **local** (no hace ninguna llamada de
red): corre antes de preguntarle nada a la API de usuarios. Al quitarlo, `_resolve_modules` queda
así, en el mismo orden que ya tenía para los demás pasos:

1. `wanted = frozenset(requested or ()) | {PATIENTS_KEY}` (sin cambios: `patients` siempre
   incluido, FR-006).
2. Si `wanted` no pide nada más que `patients`, se devuelve de inmediato sin llamar a la API de
   usuarios (sin cambios, FR-008).
3. Se llama a `list_clinic_module_keys` (sin cambios).
4. `unknown = extra - valid`; si no está vacío, `SubscriptionModuleNotFoundError` (sin cambios,
   FR-002).
5. Se devuelve `sorted(wanted)` (sin cambios).

**Rationale**: es el único punto del código donde vivía la regla (Principio I: la regla de negocio
vive en el Service); quitarla ahí basta para que ninguna combinación se rechace por dependencia, sin
tocar el cliente HTTP (`src/integrations/users_api.py`), que nunca conoció esa regla.

**Alternativas consideradas**: ninguna — no hay una segunda copia de esta regla en ningún otro
punto del código (confirmado por búsqueda exhaustiva: `MODULE_DEPENDENCIES` y
`missing_prerequisite` solo se usan en `subscription_service.py` y en sus propias pruebas
unitarias).

## R2 — Qué queda de `src/clinic_modules.py`

**Decisión**: el módulo queda reducido a `PATIENTS_KEY = "patients"` y su docstring, que pasa de
explicar «el catálogo y la dependencia entre módulos» a explicar solo por qué `patients` sigue
siendo una constante de este servicio (FR-006) mientras que el resto del catálogo deja de tener
cualquier representación en código (FR-004). Se eliminan `CLINIC_MODULE_KEYS`,
`MODULE_DEPENDENCIES` y `missing_prerequisite` enteros, no solo su contenido.

**Rationale**: FR-004 es explícito («el sistema MUST NOT mantener... ninguna lista fija de claves
ni de dependencias»); dejar la función `missing_prerequisite` sin usar, o la lista vacía, deja código
muerto que invita a que alguien la vuelva a llamar.

## R3 — Qué excepción, código y mensaje se eliminan, y qué pasa con el manejador de errores

**Decisión**: se eliminan por completo `SubscriptionModulePrerequisiteMissingError`
(`src/exceptions.py`), `ErrorCode.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING` y
`SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE` (ambos en `src/messages.py`), y sus imports en
`subscription_service.py`. **`src/error_handlers.py` no se toca**: las tres excepciones de módulos
son subclases planas de `AppError` sin ninguna lógica especial por tipo (se traducen con el mismo
`app_error_handler` genérico que usa `error.status_code`/`error.code`/`error.message`); quitar una
no requiere ningún cambio ahí.

**Rationale**: FR-005 pide la eliminación completa, no solo dejar de lanzarla; una excepción, un
`ErrorCode` o un mensaje que ya nadie produce es lo mismo que código muerto.

## R4 — Versión del contrato publicado: no se versiona

**Decisión**: `src/__init__.py` (`VERSION`) y el `info.version` del OpenAPI publicado **se quedan
en `4.0.0`**; no hay enmienda de versión con esta feature.

**Rationale**: el Principio IV exige versionar **cambios incompatibles**. Esta feature hace dos
cosas, y ninguna de las dos lo es:

1. **Afloja una validación** (antes rechazaba ciertas combinaciones de módulos con 409; ahora las
   acepta). Ninguna llamada que ya funcionaba deja de funcionar: lo único que cambia es que
   llamadas que antes fallaban ahora tienen éxito. Es, por definición, compatible hacia atrás.
2. **Retira un código de error** (`subscription_module_prerequisite_missing`) que el servidor ya
   no puede emitir. Quitar un valor de un enum que el *servidor* produce no es lo mismo que quitar
   un valor de un enum que el *cliente* debe enviar (eso sí sería incompatible): un cliente que
   dejó de ver ese código nunca necesita reconocerlo para seguir funcionando.

**Alternativas consideradas**: versionar a `5.0.0`, igual que hicieron `005`/`006`/`007` (cada uno
agregó un recurso, un campo obligatorio nuevo o un campo con reglas cruzadas). Se descarta porque
esos tres casos sí eran incompatibles en la dirección que importa (un cliente antiguo que no envía
el campo nuevo, o que no conoce el recurso nuevo, se rompe); aquí no hay ningún campo nuevo, ningún
campo que se vuelva obligatorio ni ningún campo que se quite de un DTO. Es el mismo argumento que ya
usó `008-subscription-modules-table` (research R-sin número, «Contrato: sin cambios») para no
versionar una corrección interna; aquí el contrato sí cambia un poco (una descripción, un ejemplo,
un código de error retirado), pero el criterio de compatibilidad es el mismo.

**Nota de transparencia** (no una violación, igual que la R2 de `008`): si el responsable del
proyecto prefiere versionar de todos modos por disciplina (toda corrección del catálogo de errores
sube versión, sin excepción), es una decisión legítima y reversible con un solo cambio de línea en
`src/__init__.py` y en el `info.version` de `contracts/openapi-subscriptions.yaml`; no cambia nada
más de esta feature.

## R5 — Qué contratos de `specs/` se vuelven a publicar (y cuáles no)

**Decisión**: siguiendo la misma convención que `006`/`007`/`008` (cada feature que toca el
contrato público republica, en su propia carpeta, una copia completa o un documento delta de lo que
cambia; nunca edita retroactivamente la carpeta de una spec ya cerrada), esta feature publica:

- `contracts/openapi-subscriptions.yaml`: **copia completa**, porque es un documento que debe ser
  válido y completo por sí mismo (no admite «delta»). Supersede a la de `007`.
- `contracts/error-catalog.md`: **documento delta** (mismo estilo que `006`/`007`), porque apunta
  de vuelta al catálogo completo de `004` y solo describe qué código se retira.
- `contracts/users-api-integration.md`: **documento delta** sobre el de `004` (el único que
  describía esta integración; `006`/`007`/`008` no la tocaron).
- `contracts/e2e-stubs.md`: **documento delta** sobre el de `004` (por la misma razón).

**No se publican** (sin cambios, se siguen leyendo donde ya están):

- `permission-matrix.md`: ningún permiso nuevo ni distinto (ver `specs/007-add-clinics-limit/contracts/permission-matrix.md`).
- `clinics-api-integration.md`: esta feature no toca nada relacionado con el API de clínicas.
- `database-schema.sql`: ver [data-model.md](data-model.md) — cero cambios de esquema.

**Rationale**: reproducir sin necesidad un documento que no cambia (como hizo, por ejemplo,
`permission-matrix.md` en cada feature desde `006`) sería trabajo sin valor y una fuente más de
divergencia a mantener.

## R6 — Qué pasa con las carpetas de specs ya cerradas (`004`)

**Decisión**: `specs/004-correct-subscriptions-api/{plan.md,research.md,data-model.md,quickstart.md}`
**no se editan**. Quedan como registro histórico de una decisión que esta feature reemplaza
(exactamente la misma convención que ya se siguió con `005`, `006`, `007` y `008`, ninguna de las
cuales volvió a `004` a corregirlo). Solo los documentos de `contracts/` que otro código o
documentación sigue citando como vigentes (ver R5) se vuelven a publicar, en la carpeta de `009`,
no en la de `004`.

**Rationale**: mantener la historia de decisiones legible (qué se creyó y por qué en su momento) es
más valioso que una carpeta «siempre actualizada»; el patrón de «supersede, no edites» ya es el que
usa este proyecto.

## R7 — Catálogo de prueba del stub de la API de usuarios

**Decisión**: `tests/stubs/users_api/app.py` deja de sembrar los 9 módulos que `004` copió de
`src/clinic_modules.py` (`scheduling`, `clinical_records` y `clinical_record_templates` entre
ellos, ninguno de los cuales existe ya en el catálogo real) y pasa a sembrar las 18 claves reales
que `spec.md` usa en sus propios criterios de aceptación (`appointments`, `billing`, `clinics`,
`consulting_rooms`, `expenses`, `finance`, `incomes`, `overview`, `patient_diagnoses`, `patients`,
`prescriptions`, `reminders`, `reports`, `schedule`, `services`, `staff`, `templates`,
`vital_signs`). `scheduling` deja de estar sembrada a propósito: pasa a ser la clave que las
pruebas usan para demostrar «módulo no reconocido» (Historia 2 de `spec.md`), porque ya no existe
en ningún catálogo, real o de prueba — exactamente el ejemplo que el propio `spec.md` usa.

**Rationale**: el stub nunca debió describirse como «un espejo de `src/clinic_modules.py»
(`tests/stubs/users_api/app.py` ya declara en su docstring que no importa de `src/`: siempre fueron
datos de prueba duplicados a mano); ahora que `src/clinic_modules.py` deja de tener un catálogo que
copiar, seguir usando esas 9 claves obsoletas solo crearía confusión (claves que no existen en
ningún sistema real) sin aportar nada. Usar las 18 claves reales permite además que el escenario
«Saturno» de la Historia 1 de `spec.md` (Acceptance Scenario 1) se pueda demostrar de punta a
punta con Postman, no solo a nivel de pruebas unitarias con un doble configurado a mano.

**Nota sobre el criterio «ni el código ni las pruebas referencian claves concretas» (spec.md,
criterio de aceptación)**: esa regla se interpreta como «ninguna prueba codifica una *regla de
negocio* con una clave concreta» (que es, precisamente, lo que esta feature elimina), no como
«ninguna prueba puede usar jamás una cadena de texto concreta como módulo de ejemplo» — eso sería
imposible de cumplir para cualquier prueba de punta a punta, que por definición necesita datos. Los
dobles unitarios (`tests/unit/fakes.py`, `FakeUsersApi`) ya reciben su catálogo como parámetro del
constructor (`clinic_module_keys: frozenset[str]`), sin cambios necesarios: eso es lo que garantiza
que ninguna prueba unitaria de `SubscriptionService` dependa de qué claves use el stub de punta a
punta, ni viceversa.

## R8 — Pruebas que se eliminan, se invierten o se dejan igual

**Decisión** (detalle completo en `tasks.md`, generado por `/speckit-tasks`):

- **Se eliminan**: todas las pruebas de `tests/unit/test_clinic_modules.py` salvo
  `test_patients_key`; las dos pruebas de dependencias en `tests/unit/test_subscription_service.py`
  (crear y actualizar sin prerrequisito); la entrada de
  `SubscriptionModulePrerequisiteMissingError` en `tests/unit/test_error_messages.py` (código,
  mensaje y el caso parametrizado); el request de Postman del 409 de prerrequisito.
- **Se invierten** (de «se rechaza con 409» a «se acepta»): `test_a_module_without_its_prerequisite_is_a_conflict`
  y `test_updating_to_a_module_without_its_prerequisite_is_a_conflict_and_nothing_changes` en
  `tests/contract/test_subscriptions_api.py` — son, literalmente, los Acceptance Scenarios 2 y 3 de
  la Historia 1 de `spec.md` (`reminders` sin `schedule`, `billing` sin `finance`, ahora 201/200).
- **Se dejan igual** (prueban una capa o un caso que esta feature no toca): todas las de
  `subscription_module_not_found`/`module_check_unavailable`/«patients siempre incluido» en
  `test_subscription_service.py` y `test_subscriptions_api.py`; todas las de
  `test_users_api_client.py` (el cliente HTTP nunca conoció la regla de dependencias); todas las de
  `test_subscription_dtos.py` (solo validan formato de la clave, no catálogo ni dependencias).
- **Se ajusta el comentario, no la aserción**: `test_excluding_a_module_does_not_exclude_what_depends_on_it`
  en `test_subscriptions_api.py` inserta filas directo en la base (sin pasar por el Service, nunca
  ejerció la validación de dependencias); su comentario sobre «billing depende de finance» se
  corrige para no referenciar una regla que ya no existe, pero lo que la prueba demuestra (una
  exclusión parcial no arrastra otras filas) sigue siendo válido y no cambia de forma.

**Rationale**: invertir en vez de eliminar, cuando el escenario sigue siendo relevante (ahora para
demostrar lo contrario), preserva la cobertura de un caso de la API que sigue existiendo
(crear/actualizar con una combinación de módulos) en vez de simplemente borrar la prueba y perder
esa cobertura.

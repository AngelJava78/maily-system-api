# Investigación (Fase 0): Corrección del modelo de datos de la API de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Fecha**: 2026-10-23

Esta feature corrige `001-subscriptions-api`, ya implementada en `main`. La base técnica (stack,
capas, control de acceso, pruebas, Alembic, Docker) **no cambia** y no se repite aquí: sigue siendo la
de `specs/001-subscriptions-api/research.md` (R1 a R21). Este documento solo resuelve las decisiones
**nuevas** que exige `spec.md`, con evidencia tomada del código real ya implementado (`src/`,
`alembic/`, `tests/`) y de investigar `C:\Maily\code\mailySoft-usuarios`.

**Puntos que conviene confirmar fuera de este repositorio** (no bloquean el plan; detalle en
[plan.md](plan.md)): que la feature `013-modules-permissions-catalogs` de `mailySoft-usuarios` se
termine, se comprometa y se despliegue; que alguien cree ahí los 9 módulos de tipo Clínica; que el
rol con `subscriptions:write`/`update` tenga también `modules:read`.

---

## R1. Identificador estable de un módulo: `key`, no `id` numérico

- **Decisión**: esta API referencia cada módulo por su `key` (cadena, p. ej. `"patients"`), **no**
  por su `id` (entero autoincremental de la tabla `modules` de la API de usuarios).
- **Evidencia** (`specs/013-modules-permissions-catalogs/contracts/openapi-modules.yaml` y
  `data-model.md` de `mailySoft-usuarios`, investigados el 2026-10-23): `ModuleCreate` exige `key`
  (patrón `^[a-z][a-z0-9_]*$`, máx. 50) y `type_id`; `ModuleUpdate` **excluye explícitamente** `key` y
  `type_id` de los campos modificables «porque ninguno de los dos cambia nunca tras crear el módulo»
  (cita de esa spec). El `id` es un entero autoincremental cuyo valor depende del orden de creación de
  **todos** los módulos que existan (incluidos otros tipos a futuro): no es predecible desde este
  repositorio.
- **Consecuencia**: `src/clinic_modules.py` fija las 9 claves propuestas y los 4 pares de dependencia
  usando `key`, nunca un número. La columna `module_keys` es `text[]`, no `integer[]`.
- **Alternativas descartadas**: `id` numérico (frágil: depende de un orden de creación fuera del
  control de este repositorio); `name` (es el único dato que la API de usuarios sí permite editar
  después de crear un módulo, así que no es estable).

## R2. Las 9 claves de módulo son una propuesta, no un hecho garantizado

- **Decisión**: se proponen estas claves (snake_case, cumplen `^[a-z][a-z0-9_]*$`), una por cada
  módulo del mockup:

  | Módulo (mockup) | `key` propuesta | Prerrequisito (`key`) |
  |---|---|---|
  | Pacientes | `patients` | — (siempre incluido) |
  | Agenda y citas | `scheduling` | — |
  | Recordatorios | `reminders` | `scheduling` |
  | Expediente clínico | `clinical_records` | — |
  | Plantillas de expediente | `clinical_record_templates` | `clinical_records` |
  | Recetas | `prescriptions` | `clinical_records` |
  | Finanzas | `finance` | — |
  | Reportes | `reports` | — |
  | Facturación | `billing` | `finance` |

- **Motivo**: hoy esa API no tiene sembrado ningún módulo de tipo Clínica (solo 4 protegidos de tipo
  Sistema: `users`, `roles`, `permissions`, `modules`); alguien tiene que crearlos con
  `POST /api/v1/modules` y **debe** usar estas claves (o este archivo y `src/clinic_modules.py` deben
  actualizarse juntos si usa otras). Es, en sí mismo, el **punto a confirmar más importante** de esta
  feature.
- **Alternativas descartadas**: esperar a que la feature 013 esté terminada y desplegada antes de
  escribir esta especificación (bloquearía indefinidamente una corrección que el responsable del
  proyecto pidió ahora; en vez de eso, se documenta la dependencia explícitamente, igual que
  `001-subscriptions-api` ya documentó depender de una operación de la API de usuarios que, a su vez,
  tampoco estaba desplegada cuando se escribió esa spec).

## R3. Dónde vive la regla de dependencias y de «Pacientes siempre incluido»

- **Decisión**: `src/clinic_modules.py`, un módulo plano sin E/S (como `src/messages.py`), con:
  - `PATIENTS_KEY = "patients"`.
  - `MODULE_DEPENDENCIES: dict[str, str]` (clave del módulo dependiente → clave de su prerrequisito),
    con los 4 pares de R2.
  - `missing_prerequisite(keys: frozenset[str]) -> tuple[str, str] | None`: recorre
    `MODULE_DEPENDENCIES` y devuelve el primer par `(dependiente, prerrequisito)` cuyo dependiente esté
    en `keys` pero el prerrequisito no; `None` si todo está satisfecho. Pura, sin red ni base de datos.
- **Motivo** (Clarifications, sesión 2026-10-23, preguntas 2 y 3): la API de usuarios no modela
  dependencias entre módulos ni un «siempre incluido»; esta API las sigue validando por su cuenta. No
  es una tabla porque no tiene identidad ni ciclo de vida propios (no se crea, ni se lee, ni se
  actualiza por separado): es una regla de negocio fija, igual que los 4 permisos
  `subscriptions:*` ya son constantes de `src/security.py` y no una tabla.
- **Alternativas descartadas**: una tabla `module_dependencies` en este servicio (duplicaría, con otro
  nombre, un concepto que la API de usuarios podría modelar algún día; además exigiría una migración y
  datos semilla por un dato que no cambia); pedirle a la API de usuarios que modele las dependencias
  (está fuera del alcance de la feature 013 ya escrita en `mailySoft-usuarios`, y bloquearía esta
  corrección a que la otra API se vuelva a planificar).

## R4. Ampliar `UsersApiClient`, no crear un cliente nuevo

- **Decisión**: `src/integrations/users_api.py` gana un método,
  `list_clinic_module_keys(token: str) -> frozenset[str]`, que llama a
  `GET {USERS_API_BASE_URL}/api/v1/modules?type_id=2&status_id=1` con la misma cabecera
  `Authorization: Bearer <token>` (reenviada, sin modificar) y el mismo
  `asyncio.timeout(USERS_API_TIMEOUT_SECONDS)` que ya usa `check_permission`. Devuelve el conjunto de
  `key` de los módulos recibidos; lanza `UsersApiUnavailable` (la **misma** excepción que ya existe,
  no una nueva) ante cualquier respuesta que no sea exactamente la esperada — mismo criterio de
  «fallar cerrado» que `check_permission` y el mismo patrón de análisis estricto que
  `ClinicsApiClient._parse`.
- **Motivo**: es la misma API externa (mismo `USERS_API_BASE_URL`, el mismo tiempo máximo, la misma
  política de no seguir redirecciones y de advertir sobre `http://`): separar un segundo cliente
  duplicaría esa configuración sin ninguna ganancia. `UsersApiUnavailable` ya significa «esta API
  externa no respondió como se esperaba»; crear `UsersApiModulesUnavailable` solo para distinguir el
  sitio donde se atrapa la excepción no aporta nada que el `except` de cada Service no distinga ya por
  sí mismo.
- **Parámetros de la consulta**: `type_id=2` (Clínica) y `status_id=1` (Activo) **explícitos**, aunque
  `status_id` sea el valor por defecto de esa API: así el contrato no depende de que ese valor por
  defecto no cambie.
- **Alternativas descartadas**: `ModulesApiClient` aparte (duplica `base_url`/`timeout`/manejo de
  errores sin necesidad); cachear el catálogo de módulos en memoria (viola el mismo principio que ya
  prohíbe cachear decisiones de permiso: un módulo bloqueado o creado en la API de usuarios debe
  surtir efecto en la siguiente escritura, no en la siguiente reinicialización del proceso).

## R5. Cuándo se llama a la API de usuarios por módulos

- **Decisión** (Clarifications, pregunta 4, y FR-008/FR-015): **nunca** en `list_subscriptions` ni en
  `get_subscription` (el listado y el detalle solo devuelven los `module_keys` ya guardados, sin
  resolver nombre ni validarlos de nuevo). **Solo** en `create_subscription` y en `update_subscription`
  cuando la solicitud trae módulos, y **solo si el conjunto pedido tiene algo además de `patients`**
  (pedir solo `patients`, o no enviar `module_keys`, no genera ninguna llamada: no hay nada que
  validar contra un catálogo externo).
- **Motivo**: mantiene el listado tan rápido e independiente de la API de usuarios por módulos como ya
  lo es del API de clínicas para lecturas (SC-001); limita el coste de la nueva integración a como
  mucho **una** llamada por escritura, nunca una por módulo ni una por suscripción del catálogo.
- **Alternativas descartadas**: validar también en las lecturas (contradice Clarifications Q4 y
  degradaría SC-001 si la API de usuarios responde lento); validar siempre, incluso con solo
  `patients` (llamada de red innecesaria: `patients` no tiene prerrequisito y su presencia no depende
  de lo que la persona haya enviado).

## R6. Precedencia y orden de las escrituras cuando hay módulos

- **Decisión**:
  - **Crear**: (1) si `module_keys` trae algo además de `patients`, validar dependencias localmente
    (`missing_prerequisite`, sin red) y, si pasa, preguntar a la API de usuarios por el catálogo de
    Clínica; (2) con el conjunto final validado (`module_keys` enviados ∪ `{patients}`), intentar el
    `INSERT` (la unicidad del nombre se sigue resolviendo como en R11 de 001: se intenta escribir y se
    traduce el error del índice, no se comprueba antes).
  - **Actualizar**: si la solicitud trae `module_keys`, **primero** se comprueba que la suscripción
    exista y no esté Eliminada (`get_current_by_id`); si no, `404` **antes** de llamar a la API de
    usuarios (evita gastar la llamada externa en un recurso que no existe). Si existe, se valida igual
    que al crear y luego se aplica el `UPDATE`. Si la solicitud **no** trae `module_keys`, el flujo no
    cambia respecto a `001-subscriptions-api` (una sola sentencia condicionada, sin lectura previa).
  - **Orden de los errores cuando hay varias causas**: validación de Pydantic (422, p. ej. una clave
    con mayúsculas) → `subscription_module_not_found` (422, la API de usuarios no reconoce alguna
    clave) → `subscription_module_prerequisite_missing` (409, local) → existencia de la suscripción y
    demás conflictos (404, `subscription_name_already_exists` 409).

    Dentro del propio bloque de módulos, el orden interno es **dependencias antes que catálogo
    externo** (R5: una comprobación local y gratuita antes que una llamada de red), pero de cara al
    resto de la API, «módulo no reconocido» (422) se documenta antes que «módulo sin prerrequisito»
    (409) en el catálogo de errores, porque así ordena esta especificación sus propias categorías
    (FR-032: «datos no válidos» antes que «conflicto») y porque mantiene el mismo principio que ya usa
    el catálogo de errores de 001: validación antes que conflicto.
- **Motivo**: evita gastar la llamada a la API de usuarios en una suscripción que ya se sabe que no
  existe (mismo criterio que ya aplica `delete` con el API de clínicas, R7 de 001) y mantiene un orden
  de precedencia único y documentado para todos los errores de la API, nuevos y viejos.
- **Alternativas descartadas**: comprobar módulos después de intentar el `UPDATE` (si la suscripción no
  existe, ya es tarde: la llamada a la API de usuarios se hizo en vano); una sola sentencia que
  intente el `UPDATE` y revierta si los módulos no son válidos (Postgres no puede validar algo que
  depende de una llamada HTTP dentro de la misma transacción sin dejarla abierta durante la llamada de
  red, que el Principio III prohíbe).

## R7. Columna `module_keys`: incluye `patients`, con `CHECK`, orden alfabético en la respuesta

- **Decisión**: `module_keys text[] NOT NULL DEFAULT ARRAY['patients']::text[]`, con
  `CHECK ('patients' = ANY(module_keys))`. El Service calcula el conjunto completo
  (`sorted({*enviados, "patients"})`) antes de escribir, así que la columna siempre es la respuesta
  final, sin que el Router tenga que añadir `patients` por su cuenta al leer. Se devuelve **ordenada
  alfabéticamente** (determinista; esta API no conoce el orden de presentación que use el mockup, que
  es responsabilidad de quien la consuma).
- **Motivo**: igual que `monthly_price_check` o `features_check` en 001, es una regla de datos que
  conviene que la base de datos también exija (defensa en profundidad), y simplifica la capa de
  lectura (sin lógica condicional para añadir `patients` en cada DTO de salida).
- **Alternativas descartadas**: `CHECK` que restrinja `module_keys` a exactamente las 9 claves de hoy
  (rompería en cuanto la API de usuarios sume un décimo módulo de Clínica, algo que FR-016 ya
  anticipa como posible); guardar `patients` implícito y añadirlo solo en el DTO de salida (más código
  en dos sitios —creación y lectura— por ninguna ventaja).

## R8. Migración `0003`: una sola, columnas con/sin `DEFAULT` según si son obligatorias

- **Decisión**: una migración, `0003_subscription_pricing_modules_limits`, sobre la tabla
  `subscriptions` ya desplegada por `0001`:
  - `ALTER TABLE subscriptions RENAME COLUMN features TO other_features;` y se renombra también el
    `CHECK` (`features_check` → `other_features_check`) para que el nombre siga describiendo la
    columna; no cambia su regla (`cardinality(...) <= 20`).
  - `trial_days integer NOT NULL DEFAULT 0 CHECK (BETWEEN 0 AND 3650)`,
    `self_service boolean NOT NULL DEFAULT false` y `module_keys` (R7): las tres llevan `DEFAULT`, así
    que son seguras aunque la tabla ya tenga filas.
  - `annual_price numeric(10,2) NOT NULL CHECK (>= 0)`, `consulting_rooms_limit`, `doctors_limit`,
    `assistants_limit`, `new_patients_per_year_limit` (los cuatro `integer NOT NULL CHECK (BETWEEN 0
    AND 1000000)`): **sin** `DEFAULT`, porque la spec los exige obligatorios al crear (FR-012, FR-021)
    y un valor inventado sería peor que fallar. **Esta migración asume que la tabla está vacía**
    (supuesto del spec, sección Assumptions: no hay información real en producción que migrar); si
    algún entorno ya tiene filas, `ALTER TABLE ... ADD COLUMN ... NOT NULL` sin `DEFAULT` falla con un
    error claro de Postgres, y haría falta un `UPDATE` de backfill antes de aplicarla — deliberadamente
    no se añade ese backfill porque no hay datos reales que lo necesiten.
- **Motivo**: siete columnas nuevas sobre la misma tabla son un solo cambio de esquema coherente de
  esta feature; separarlas en varias migraciones no aportaría nada (a diferencia de 001, donde el
  esquema y los datos semilla eran conceptualmente distintos).
- **Evidencia**: `alembic/versions/0001_subscriptions_schema.py` y
  `project-definition/DATA_SCHEMA.md` confirman los nombres automáticos de PostgreSQL de los que
  depende `src/models/base.py` (`NAMING_CONVENTION`); el `CHECK` de un límite sigue el mismo patrón
  (`ck: "%(table_name)s_%(constraint_name)s"`).
- **Alternativas descartadas**: añadir `DEFAULT 0` a los cuatro límites y al precio anual «para que la
  migración nunca falle» (un límite o un precio en `0` no pedido por nadie es peor que una migración
  que exige una tabla vacía: esconde un dato que la spec declaró obligatorio).

## R9. Versión del contrato: sube el `version` de OpenAPI, la ruta sigue en `/api/v1`

- **Decisión**: `src/main.py` pasa `VERSION` de `"1.0.0"` a `"2.0.0"` (cambio incompatible de forma:
  `annual_price` y los cuatro límites pasan a ser obligatorios en `SubscriptionCreate`, y `features`
  deja de existir con ese nombre). La ruta sigue siendo `/api/v1/subscriptions`: no se publica un
  `/api/v2` nuevo.
- **Motivo**: el Principio IV exige declarar los cambios incompatibles; el `version` semántico de
  OpenAPI es el lugar donde se declara sin forzar una migración de ruta. Forzar `/api/v2` (dos
  Routers, dos conjuntos de DTOs conviviendo) solo tiene sentido para proteger a consumidores
  existentes del contrato anterior, y el propio spec (Assumptions) asume que no hay datos reales en
  producción con el modelo de 001 que deba convivir con el nuevo.
- **Alternativas descartadas**: mantener `1.0.0` (oculta que el contrato cambió de forma incompatible,
  contradice el Principio IV); publicar `/api/v2/subscriptions` en paralelo (coste de dos Routers y
  dos DTOs para proteger a un consumidor que, según el propio spec, no existe todavía).

## R10. Stub de la API de usuarios: mismo módulo, `GET /api/v1/modules`, fallos por operación

- **Decisión**: `tests/stubs/users_api/app.py` gana una ruta nueva,
  `GET /api/v1/modules?type_id=&status_id=`, sembrada en memoria con los 9 módulos de R2 (más, si
  conviene a alguna prueba, los 4 protegidos de tipo Sistema para comprobar que el filtro
  `type_id=2` los excluye). `POST /__test__/faults` gana un campo opcional `"operation":
  "check"|"modules"` (por omisión, `"check"`, para no romper los fallos que las pruebas de 001 ya
  registran sin ese campo); cada ruta real consume solo los fallos de su propia operación.
- **Motivo**: es la misma simulación de la misma API externa (Principio V: ninguna prueba llama a la
  API de usuarios real); separar `calls`/`reset` en dos apps duplicaría la superficie de pruebas sin
  necesidad.
- **Alternativas descartadas**: una simulación nueva, `tests/stubs/modules_api` (misma API externa:
  duplicar el módulo de pruebas no refleja la realidad y haría más difícil probar, por ejemplo, un
  token con permiso de módulos pero no de suscripciones).

## R11. Mensajes y códigos de error nuevos

- **Decisión**: tres `AppError` nuevos en `src/exceptions.py` (detalle completo en
  [contracts/error-catalog.md](contracts/error-catalog.md)):
  - `SubscriptionModuleNotFoundError` → `subscription_module_not_found`, 422.
  - `SubscriptionModulePrerequisiteMissingError` → `subscription_module_prerequisite_missing`, 409.
  - `ModuleCheckUnavailableError` → `module_check_unavailable`, 503.

  Más los mensajes de validación (Pydantic) de los 7 campos nuevos en
  `VALIDATION_MESSAGES["subscriptions"]`, siguiendo exactamente el patrón `(campo, tipo) -> mensaje`
  que ya usa `src/messages.py`.
- **Motivo**: `subscription_module_not_found` y `subscription_module_prerequisite_missing` no pueden
  viajar por el camino genérico de `validation_error` (ese camino lo dispara `RequestValidationError`
  de Pydantic, síncrono, **antes** de que el Service pueda llamar a la API de usuarios); necesitan su
  propio código, igual que `subscription_name_already_exists` no usa `validation_error` aunque también
  sea un rechazo del cuerpo de la solicitud.

## R12. `dependencies.py`: `UsersApiClient` también lo recibe `SubscriptionService`

- **Decisión**: `get_subscription_service` pasa a inyectar tres dependencias:
  `(repository, clinics_api, users_api)`. No se crea un nuevo proveedor: `get_users_api_client` ya
  existe (lo usa `get_authorization_service`) y FastAPI lo resuelve una vez por petición.
- **Motivo**: es la composición mínima; `SubscriptionService` ya recibía dos integraciones
  (`repository`, `clinics_api`) y sigue el mismo patrón para la tercera.

## R13. Impacto en la colección de Postman

- **Decisión**: los cuerpos de ejemplo de «1. Catálogo» y «2. Consultar y actualizar» se actualizan
  con los campos nuevos (sin crear carpetas nuevas por eso); se añade una petición a «2.» que
  intenta un módulo sin su prerrequisito (409) y otra con una clave que la API de usuarios no
  reconoce (422, requiere que el stub de usuarios esté sembrado con los 9 módulos antes de ejecutar
  la colección). La preparación («0. Preparación») registra también el permiso `modules:read` para el
  token de prueba.
- **Motivo**: sigue el mismo principio que ya rige la colección (Constitución: complementa a pytest,
  recorridos de punta a punta y errores clave, no repite las pruebas unitarias). El detalle completo
  está en [contracts/e2e-stubs.md](contracts/e2e-stubs.md).

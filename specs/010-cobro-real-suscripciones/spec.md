# Feature Specification: Cobro Real de Suscripciones de Clínicas

**Feature Branch**: `006-cobro-real-suscripciones`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "En maily-system-api, construir el cobro real de suscripciones de
clínicas usando mailySoft-pagos (microservicio de pagos genérico, ya con Mercado Pago funcionando).
Hoy `subscriptions` es solo el catálogo de planes (nombre, monthly_price, annual_price, límites); no
existe ninguna relación clínica↔suscripción. Hay que: (1) añadir el dominio de 'suscripción de una
clínica' (clinic_subscriptions): qué clínica (tenant_id), qué plan (subscription_id), desde cuándo,
ciclo de cobro (mensual/anual) y estatus — la pieza completa, no una versión mínima de cobro manual
sin ciclo, aunque la automatización del cobro periódico (cron) puede quedar para una spec posterior;
(2) la operación de cobrar: llama a POST /api/v1/payments de mailySoft-pagos con provider:
mercado_pago, resource_type: system-api:subscription, resource_id = id de la suscripción de la
clínica, amount en centavos del monthly_price/annual_price según el ciclo, currency: MXN (el
tenant_id lo decide quien llama, nunca se envía en el cuerpo); (3) cómo se entera System API de que
el pago se aprobó o rechazó — Pagos no notifica a sus consumidores, así que System API debe
resolverlo con el diseño que mejor encaje; (4) seguir el flujo de Spec Kit de este repositorio. Fuera
de alcance: modificar mailySoft-pagos (si el plan descubre que hace falta, documentarlo y avisar en
vez de modificarlo) y dar de alta `payments:*` en el catálogo real de mailySoft-usuarios (se
desarrolla y prueba contra una simulación, igual que ya hacen Agenda y Pagos con la suya)."

## Clarifications

### Session 2026-11-10

- Q: ¿Quién puede crear o modificar la suscripción de una clínica (asignar un plan, su ciclo de
  cobro y, si aplica, cancelarla) y de dónde sale el `tenant_id` de esa clínica? → A: Quien
  administra la plataforma (el mismo tipo de persona que hoy mantiene `subscriptions`, sin
  organización propia), enviando `tenant_id` explícito en el cuerpo, igual que cualquier otro dato de
  la suscripción de clínica — el mismo patrón que ya usa este servicio para el catálogo y el
  dashboard.
- Q: Dado que Pagos exige que el `tenant_id` de un pago salga únicamente del token de quien llama
  (nunca del cuerpo), ¿quién está autorizado a disparar el cobro de la suscripción de una clínica, de
  modo que ese mismo token se pueda reenviar a Pagos? → A: Una persona de la propia clínica (p. ej.
  su Owner), cuyo token System API reenvía a Pagos sin modificar; es la única forma de que Pagos
  resuelva el `tenant_id` correcto con su propio `GET /api/v1/authorization/me`, sin tocar su
  contrato. Quien administra la plataforma (respuesta anterior) asigna el plan, pero no puede
  disparar el cobro: no tiene `tenant_id` propio.
- Q: ¿Hay que guardar cada intento de cobro (incluidos los rechazados) como historial propio, o basta
  con el último cobro y su estatus por suscripción de clínica? → A: Historial completo: una tabla
  (`clinic_subscription_charges`) con una fila por intento, rechazados incluidos, necesaria para
  auditoría, soporte y para reintentar un cobro rechazado sin perder el anterior.

## User Scenarios & Testing *(mandatory)*

Los actores son: **quien administra la plataforma** (ya existe, spec 001: crea y mantiene
`subscriptions`; sin organización propia, `tenant_id` nulo en `mailySoft-usuarios`), que ahora
también asigna, modifica y cancela la suscripción de una clínica (enviando su `tenant_id` explícito);
**una persona de la propia clínica** (p. ej. su Owner, con `tenant_id` propio), la única que puede
disparar el cobro de su suscripción, porque Pagos resuelve el `tenant_id` del pago exclusivamente con
el token de quien llama; y **mailySoft-pagos**, el microservicio al que este servicio delega el cobro
real sin conocer tarjetas, proveedores ni nada del dominio de pagos (solo referencia un recurso propio
con `resource_type` y `resource_id`, principio X de Pagos).

Hoy `subscriptions` es únicamente el catálogo de planes: no existe ninguna fila que diga qué clínica
tiene cuál plan, ni una sola operación que cobre nada. Esta especificación añade esa relación
(«suscripción de una clínica») con su ciclo de cobro y estatus, y la operación que la cobra contra
Mercado Pago a través de Pagos, dejando lista la pieza completa aunque el disparo periódico
automático (cron) se implemente después.

### User Story 1 - Asignar un plan del catálogo a una clínica (Priority: P1)

Quien administra la plataforma elige un plan ya existente en `subscriptions` y lo asigna a una
clínica, indicando su `tenant_id` explícitamente (no tiene organización propia: es quien decide a
cuál clínica se asigna), con un ciclo de cobro (mensual o anual) y una fecha de inicio. El sistema
guarda esa suscripción de clínica con un estatus propio (Activa) y, si el plan tiene días de prueba
(`trial_days` > 0), programa su primer cobro después del periodo de prueba; si no, lo programa de
inmediato.

**Why this priority**: Sin esta pieza no hay nada que cobrar: es la relación clínica↔plan que hoy no
existe y que el resto de la especificación necesita.

**Independent Test**: Con un plan Activo del catálogo, asignarlo a una clínica con cada ciclo
(mensual y anual) y comprobar que la suscripción de clínica queda creada, Activa, con la fecha de
próximo cobro correcta (inmediata, o después de `trial_days` si el plan tiene prueba).

**Acceptance Scenarios**:

1. **Given** un plan Activo del catálogo sin días de prueba, **When** se asigna a una clínica con
   ciclo mensual, **Then** la suscripción de clínica queda creada, Activa, y su próximo cobro es
   inmediato (no hay prueba que esperar).
2. **Given** un plan Activo con `trial_days` = 14, **When** se asigna a una clínica, **Then** la
   suscripción de clínica queda creada, Activa, y su próximo cobro queda programado 14 días después
   de la fecha de inicio, sin cobrar nada todavía.
3. **Given** un plan Inactivo, Bloqueado o Eliminado, **When** se intenta asignar a una clínica,
   **Then** la operación se rechaza (409) y no se crea nada.
4. **Given** una clínica que ya tiene una suscripción Activa, **When** se intenta asignarle otro plan
   sin antes cancelar o sustituir la vigente, **Then** la operación se rechaza (409): una clínica
   tiene a lo sumo una suscripción Activa a la vez.
5. **Given** datos de entrada inválidos (ciclo que no es `monthly` ni `annual`, fecha de inicio en el
   pasado más allá de lo razonable, `tenant_id` que no es un UUID), **When** se envían, **Then** se
   rechaza con 422 y el formato de error común, sin crear nada.

---

### User Story 2 - Cobrar la suscripción de una clínica (Priority: P1)

Una persona de la propia clínica (de la misma organización que la suscripción, p. ej. su Owner)
dispara el cobro de su suscripción de clínica vigente. El sistema calcula el
monto exacto (en centavos) a partir del `monthly_price` o `annual_price` del plan asignado según el
ciclo, y pide a mailySoft-pagos que cree un pago genérico (`provider: mercado_pago`,
`resource_type: system-api:clinic-subscription`, `resource_id` = el identificador de la suscripción
de la clínica, `amount`, `currency: MXN`), con una clave de idempotencia propia del periodo que se
está cobrando para que repetir la petición no duplique el cargo. La respuesta de Pagos (con la URL de
checkout mientras el pago no se resuelva) se guarda como un cobro de esa suscripción de clínica.

**Why this priority**: Es la razón de ser de la especificación: sin esto, asignar un plan a una
clínica no produce ningún cargo real.

**Independent Test**: Con una suscripción de clínica Activa y Pagos simulado, disparar el cobro y
comprobar que se llama a `POST /api/v1/payments` con los campos exactos esperados y que la respuesta
(incluida la URL de checkout) queda asociada a esa suscripción de clínica.

**Acceptance Scenarios**:

1. **Given** una suscripción de clínica Activa con ciclo mensual y un plan de `monthly_price`
   1299.00, **When** se dispara su cobro, **Then** Pagos recibe `amount: 129900`, `currency: MXN`,
   `resource_type: system-api:clinic-subscription` y el `resource_id` de la suscripción de clínica, y
   la respuesta (con su `id` de pago y su `checkout_url`) queda guardada como el cobro vigente de esa
   suscripción.
2. **Given** la misma suscripción de clínica y el mismo periodo, **When** el cobro se dispara dos
   veces (p. ej. un reintento tras un corte de red), **Then** Pagos recibe la misma
   `Idempotency-Key` las dos veces y responde con el mismo pago ya creado, sin cobrar dos veces.
3. **Given** una suscripción de clínica Cancelada, **When** se intenta disparar su cobro, **Then**
   se rechaza (409) sin llamar a Pagos. (Un cobro `approved` no puede quedar «vigente para el
   periodo actual»: aprobarlo ya avanzó `next_billing_at` al siguiente periodo — research R7.)
4. **Given** que Pagos no responde, agota el tiempo de espera o contesta algo inesperado, **When** se
   dispara el cobro, **Then** la operación responde 503, no se crea ningún cobro local y la
   suscripción de clínica no cambia.
5. **Given** que Pagos rechaza el token (401) o responde que no hay permiso (403) para
   `payments:write`, **When** se dispara el cobro, **Then** System API traduce esa respuesta a su
   propio error (401 o 403) sin filtrar el cuerpo ni las cabeceras de Pagos, y no se crea ningún cobro
   local.
6. **Given** un plan con `annual_price` 12990.00 y ciclo anual, **When** se dispara el cobro,
   **Then** el monto enviado a Pagos es `1299000` (centavos exactos, sin redondeos de punto flotante).
7. **Given** una suscripción de clínica de la organización A, **When** una persona Activa de la
   organización B (u otra sin organización, como un Administrator) intenta disparar su cobro,
   **Then** responde 404 (no 403): no revela que la suscripción existe, igual que el patrón de «misma
   organización» de `mailySoft-usuarios` (spec 019) y de `mailySoft-pagos` con un pago de otra
   organización.

---

### User Story 3 - Conocer si el cobro se aprobó o se rechazó (Priority: P1)

Como mailySoft-pagos no notifica a quien lo integra (no emite webhooks propios, solo los recibe de
Mercado Pago), System API resuelve el estatus de un cobro consultando `GET /api/v1/payments/{id}` de
Pagos. Quien consulta un cobro que sigue pendiente obtiene una respuesta ya actualizada (System API
pregunta a Pagos en el momento de la consulta, no solo lee lo que guardó la última vez); un cobro ya
resuelto (aprobado, rechazado, reembolsado…) se responde con el dato local, sin volver a preguntar.

**Why this priority**: Sin esto, una suscripción de clínica se queda cobrando «a ciegas»: nadie sabría
si el cargo entró o si hay que reintentar o avisar a la clínica.

**Independent Test**: Crear un cobro pendiente, cambiar su estatus en la simulación de Pagos a
aprobado, consultarlo desde System API y comprobar que la respuesta ya refleja «aprobado» sin que
nadie haya llamado a una operación de sincronización aparte.

**Acceptance Scenarios**:

1. **Given** un cobro cuyo estatus en Pagos sigue siendo `pending`, **When** se consulta ese cobro (o
   la suscripción de clínica que lo tiene vigente), **Then** System API pregunta a Pagos en ese
   instante y la respuesta refleja el estatus vigente en Pagos.
2. **Given** un cobro cuyo estatus en Pagos ya es `approved`, `rejected`, `cancelled`,
   `partially_refunded` o `refunded`, **When** se consulta de nuevo, **Then** System API responde con
   el dato guardado localmente, sin llamar otra vez a Pagos.
3. **Given** un cobro `pending`, **When** se consulta y Pagos no responde o agota el tiempo de
   espera, **Then** System API responde con el último estatus conocido localmente (`pending`) en vez
   de fallar la consulta completa, y no se pierde el cobro.
4. **Given** una suscripción de clínica cuyo cobro vigente queda `rejected` tras consultarlo,
   **Then** la suscripción de clínica pasa a un estatus que señala el problema (p. ej. «con cobro
   pendiente de resolver»), visible al consultarla, sin que nadie tenga que inspeccionar el cobro por
   separado.

---

### User Story 4 - Consultar las suscripciones de una clínica y su historial de cobros (Priority: P2)

Quien tiene permiso (`clinic_subscriptions:read`) puede listar y consultar las suscripciones de una
clínica (paginadas, igual que cualquier listado del Principio IV) y, de cada una, ver su cobro
vigente y su historial de cobros anteriores (`clinic_subscription_charges`, rechazados incluidos).

**Why this priority**: Es la visibilidad que hace operable todo lo anterior (soporte, facturación,
auditoría), pero el sistema ya es útil sin ella si solo se necesita cobrar.

**Independent Test**: Con varias suscripciones de clínica y varios cobros, listar y consultar por
identificador y comprobar que la forma de la respuesta coincide con el contrato.

**Acceptance Scenarios**:

1. **Given** varias suscripciones de clínica, **When** se listan, **Then** la respuesta está
   paginada y cada una trae su plan, su ciclo, su estatus y su cobro vigente (o `null` si aún no se ha
   disparado ninguno).
2. **Given** una suscripción de clínica que no existe o fue cancelada, **When** se consulta por
   identificador, **Then** responde 404.
3. **Given** una persona sin el permiso de lectura, **When** intenta listar o consultar, **Then**
   responde 403, sin revelar ningún dato.

---

### User Story 5 - Cancelar la suscripción de una clínica (Priority: P3)

Quien administra la plataforma (`clinic_subscriptions:delete`, FR-006) puede cancelar la suscripción
de una clínica (baja lógica, igual que el catálogo de planes). Una suscripción Cancelada no vuelve a
cobrarse y no cuenta para la regla de «a lo sumo una Activa por clínica» de la historia 1.

**Why this priority**: Resuelve el cambio de plan (cancelar y crear una nueva) y el fin de la relación
con una clínica, pero no bloquea el cobro de las suscripciones que ya existen.

**Independent Test**: Cancelar una suscripción de clínica Activa y comprobar que deja de poder
cobrarse (historia 2, escenario 3) y que la clínica puede recibir una nueva suscripción Activa.

**Acceptance Scenarios**:

1. **Given** una suscripción de clínica Activa sin cobro pendiente, **When** se cancela, **Then**
   queda en estatus Cancelada y ya no admite nuevos cobros.
2. **Given** una suscripción de clínica con un cobro `pending` (checkout ya entregado a la clínica),
   **When** se intenta cancelar, **Then** la operación se rechaza (409) hasta que ese cobro se
   resuelva (aprobado o rechazado), para no cancelar un cargo que podría completarse.
3. **Given** una suscripción de clínica ya Cancelada, **When** se intenta cancelar de nuevo,
   **Then** responde 409 (ya está en ese estatus), igual que el patrón de cambio de estatus del
   catálogo de planes (spec 001).

---

### Edge Cases

- **Clínica inexistente**: no hay módulo de Organizaciones (igual que en `mailySoft-usuarios`, spec
  019); `tenant_id` es un UUID que este servicio no valida contra ningún catálogo de clínicas. Dos
  suscripciones con el mismo `tenant_id` son de la misma clínica.
- **Plan modificado o eliminado después de asignarlo**: la suscripción de clínica guarda una
  referencia al plan (`subscription_id`), no una copia de su precio; el cobro siempre usa el precio
  **vigente** del plan en el momento de cobrar. Si el plan fue eliminado (baja lógica, spec 001), no
  se puede disparar un nuevo cobro para esa suscripción de clínica (409) hasta que se le asigne un
  plan vigente.
- **Pagos responde con un pago ya existente por la `Idempotency-Key`** pero con un monto distinto al
  calculado ahora (p. ej. el plan cambió de precio entre dos intentos del mismo periodo): se trata
  como el 409 de conflicto de idempotencia que define el contrato de Pagos, sin inventar una
  resolución local.
- **Moneda distinta de pesos mexicanos**: fuera de alcance; esta especificación fija `currency: MXN`
  siempre, igual que hace este servicio con `monthly_price`/`annual_price` (Principio VI).
- **`payments:write` no existe todavía en el catálogo real de `mailySoft-usuarios`**: el cobro falla
  con 503/403 contra el Usuarios real hasta que se dé de alta (fuera de alcance, ver Assumptions);
  mientras tanto el desarrollo y las pruebas usan una simulación.
- **Reintento automático**: System API nunca reintenta un cobro por sí mismo si la llamada a Pagos
  falla (503): quien lo disparó decide si lo intenta de nuevo, con la misma `Idempotency-Key` del
  periodo.

## Requirements *(mandatory)*

### Functional Requirements

**Suscripción de una clínica (modelo y asignación)**

- **FR-001**: El sistema MUST introducir la entidad «suscripción de clínica» (`clinic_subscriptions`)
  que liga una clínica (`tenant_id`, UUID) con un plan del catálogo existente (`subscription_id`),
  distinta del catálogo de planes (`subscriptions`, spec 001), que no cambia.
- **FR-002**: Cada suscripción de clínica MUST guardar: `tenant_id`, `subscription_id`, el ciclo de
  cobro (`monthly` o `annual`), la fecha de inicio (`started_at`), la fecha de su próximo cobro
  (`next_billing_at`) y su propio estatus (Activa, con cobro pendiente de resolver, o Cancelada; ver
  FR-015).
- **FR-003**: Crear una suscripción de clínica MUST exigir que el plan indicado exista y esté Activo
  (409 si está Inactivo, Bloqueado, Eliminado o no existe).
- **FR-004**: Una clínica (`tenant_id`) MUST tener a lo sumo una suscripción de clínica Activa o con
  cobro pendiente de resolver a la vez; crear una nueva mientras exista una en ese estado se rechaza
  (409). Una clínica puede tener varias suscripciones Canceladas en su historial.
- **FR-005**: Si el plan asignado tiene `trial_days` > 0, `next_billing_at` MUST calcularse como
  `started_at` + `trial_days`; si no, MUST ser igual a `started_at` (el primer cobro puede dispararse
  de inmediato).
- **FR-006**: Crear, modificar y cancelar una suscripción de clínica MUST hacerlo quien administra la
  plataforma (el mismo tipo de persona que hoy mantiene `subscriptions`, sin organización propia, es
  decir con `tenant_id` nulo en `mailySoft-usuarios`), con los permisos `clinic_subscriptions:write`
  (crear), `clinic_subscriptions:update` (modificar) y `clinic_subscriptions:delete` (cancelar).
  `tenant_id` MUST enviarse explícito en el cuerpo al crear (como cualquier otro dato de la
  suscripción de clínica): MUST NOT derivarse del token de quien crea (que no tiene organización
  propia). No se valida contra ningún catálogo de clínicas (no existe todavía, ver Edge Cases).
- **FR-007**: Listar y consultar suscripciones de clínica MUST estar paginado (Principio IV), con
  filtros al menos por `tenant_id` y por estatus.

**Cobro**

- **FR-008**: El sistema MUST exponer una operación que dispara el cobro de una suscripción de
  clínica que no esté Cancelada (409 si lo está). Un cobro vigente `pending` o `rejected` del mismo
  periodo MUST NOT bloquear el disparo: la operación reintenta contra Pagos con la misma
  `Idempotency-Key` determinista (research R3, R7) en vez de rechazarlo localmente — es la única
  forma de cumplir la idempotencia de la historia 2 (escenario 2).
- **FR-009**: El monto a cobrar MUST calcularse en la unidad mínima de la moneda (centavos) a partir
  del precio **vigente** del plan asignado (`monthly_price` si el ciclo es `monthly`,
  `annual_price` si es `annual`), sin redondeos de punto flotante (los precios ya son `NUMERIC(10,2)`:
  multiplicar por 100 siempre da un entero exacto).
- **FR-010**: El sistema MUST llamar a `POST /api/v1/payments` de mailySoft-pagos con
  `provider: mercado_pago`, `amount` (FR-009), `currency: MXN`,
  `resource_type: system-api:clinic-subscription`, `resource_id` = el identificador de la suscripción
  de clínica (como texto) y una `Idempotency-Key` propia, determinista para el mismo periodo de cobro
  (misma suscripción de clínica + mismo `next_billing_at`), de modo que repetir la operación para el
  mismo periodo nunca duplique el cargo.
- **FR-011**: El `tenant_id` del pago MUST seguir siendo responsabilidad exclusiva de Pagos: System
  API MUST NOT enviarlo en el cuerpo de `POST /api/v1/payments` (Principio X de Pagos) y MUST reenviar,
  sin modificar, el token de quien disparó el cobro, para que Pagos resuelva el `tenant_id` con su
  propio `GET /api/v1/authorization/me`.
- **FR-012**: Disparar el cobro (historia 2) MUST exigir el permiso `clinic_subscriptions:charge`, que
  a diferencia de los de FR-006 MUST poder asignarse a un rol de tipo Clínica en el catálogo de
  `mailySoft-usuarios` (p. ej. Owner), no solo a un rol de Sistema: quien lo dispara MUST pertenecer a
  la misma clínica de la suscripción (su `tenant_id`, resuelto con `GET /api/v1/authorization/me` de
  Usuarios — FR-030), porque ese es el único token que Pagos puede traducir al `tenant_id` correcto
  (FR-011). Quien administra la plataforma (FR-006) MUST NOT poder disparar el cobro de una clínica a
  la que no pertenece: resolverlo (p. ej. «cobrar en nombre de») queda fuera de alcance de esta
  especificación.
- **FR-013**: El sistema MUST guardar la respuesta de Pagos (identificador del pago, estatus,
  `checkout_url`, monto, moneda y la `Idempotency-Key` usada) como el cobro vigente de la suscripción
  de clínica.
- **FR-014**: Si Pagos no responde, agota el tiempo de espera o responde algo inesperado, la
  operación de cobro MUST responder 503 y MUST NOT crear ningún cobro local ni cambiar la suscripción
  de clínica (ninguna duda ejecuta el cobro, igual que el Principio VIII/IX de este servicio con sus
  otras dependencias).
- **FR-015**: Mientras un cobro esté `pending`, la suscripción de clínica MUST mostrar un estatus que
  señale que tiene un cobro pendiente de resolver; si Pagos lo marca `approved`, la suscripción MUST
  volver a Activa y `next_billing_at` MUST avanzar un ciclo (un mes o un año, según corresponda) desde
  el periodo cobrado; si lo marca `rejected` o `cancelled`, la suscripción MUST quedar con el cobro
  rechazado visible y disponible para un nuevo intento (historia 2), sin avanzar `next_billing_at`.

**Conocer el resultado del cobro**

- **FR-016**: El sistema MUST resolver el estatus de un cobro `pending` consultando
  `GET /api/v1/payments/{id}` de Pagos en el momento en que se consulta ese cobro o la suscripción de
  clínica que lo tiene vigente (sin que haga falta una operación de sincronización aparte); un cobro ya
  resuelto (`approved`, `rejected`, `cancelled`, `partially_refunded`, `refunded`) MUST responderse
  con el dato guardado localmente, sin volver a llamar a Pagos.
- **FR-017**: Si al consultar un cobro `pending` Pagos no responde o agota el tiempo de espera, la
  consulta MUST responder con el último estatus conocido localmente (`pending`) en vez de fallar toda
  la operación; MUST NOT perderse el cobro ni la suscripción de clínica.
- **FR-018**: Toda actualización del estatus local de un cobro a partir de la respuesta de Pagos
  MUST ser una traducción explícita del estatus de Pagos (`PaymentStatus`, contrato de Pagos); un
  estatus de Pagos que este servicio no reconozca MUST tratarse como «no disponible» (igual que una
  falla de Pagos), nunca como un estatus inventado.

**Integración con mailySoft-pagos**

- **FR-019**: Toda llamada a Pagos (crear un cobro, consultarlo) MUST ser asíncrona (httpx), con un
  tiempo máximo de espera total propio (variable de entorno) y MUST NOT reintentarse automáticamente.
- **FR-020**: Las fallas de Pagos MUST traducirse a los errores propios de este servicio (código en
  inglés, mensaje en español); MUST NOT filtrarse al cliente el cuerpo, las cabeceras ni la dirección
  interna de Pagos.
- **FR-021**: La dirección, el tiempo de espera y, si aplica, las credenciales para llamar a Pagos
  MUST provenir de variables de entorno validadas al arrancar (mismo patrón que `USERS_API_BASE_URL` y
  `CLINICS_API_BASE_URL`).
- **FR-022**: El contrato consumido de Pagos (`POST /api/v1/payments`, `GET /api/v1/payments/{id}`,
  sus campos, sus códigos de error y su traducción) MUST documentarse en esta especificación
  (`contracts/payments-api-integration.md`), con su simulación en las pruebas (Principio V), igual
  que ya existe para el API de usuarios y el de clínicas.
- **FR-023**: Esta especificación MUST NOT modificar `mailySoft-pagos`. Si al planear se descubre que
  algo de lo pedido exige cambiar su contrato o sus reglas, el plan MUST documentarlo como hallazgo y
  avisar al responsable del proyecto en vez de modificar ese repositorio.

**Control de acceso y permisos**

- **FR-024**: Toda operación de esta especificación MUST exigir token y su permiso
  (`clinic_subscriptions:read` para listar y consultar, `clinic_subscriptions:write` para crear,
  `clinic_subscriptions:update` para modificar, `clinic_subscriptions:delete` para cancelar, y
  `clinic_subscriptions:charge` para disparar el cobro — FR-006 y FR-012), comprobado contra
  `mailySoft-usuarios` igual que el resto de la API (Principio VIII), y declarado en
  `contracts/permission-matrix.md`.
- **FR-025**: Los permisos nuevos de esta especificación (los de `clinic_subscriptions:*` en
  `mailySoft-usuarios`, y `payments:write` y `payments:read` que exige Pagos, Principio VIII de
  Pagos) MUST NOT darse de alta en el catálogo real de `mailySoft-usuarios` como parte de esta
  especificación: es un prerrequisito documentado (igual que ya lo hacen `mailySoft-agenda` y
  `mailySoft-pagos` con los suyos) y el desarrollo y las pruebas MUST usar una simulación que
  reproduzca ese catálogo ya existente.
- **FR-026**: Mientras el prerrequisito de FR-025 no esté resuelto en el `mailySoft-usuarios` real,
  esta funcionalidad MUST seguir funcionando contra la simulación sin cambios de código; sustituir la
  simulación por el servicio real MUST ser solo un cambio de configuración (`USERS_API_BASE_URL`,
  `PAGOS_API_BASE_URL`), igual que las demás integraciones de este servicio.

**Gobierno y pruebas**

- **FR-027**: Toda la funcionalidad MUST tener pruebas automatizadas (Principio V): unitarias de
  Services con los clientes de Pagos y de Usuarios sustituidos por dobles de prueba, de contrato de
  cada operación, de Repositories contra PostgreSQL 17 real, y la prueba que recorre todas las rutas y
  falla si alguna carece de permiso declarado.
- **FR-028**: El cambio de esquema (tablas nuevas, catálogo de estatus de la suscripción de clínica)
  MUST entregarse con una migración de Alembic reversible y reflejarse en
  `project-definition/DATA_SCHEMA.md` con la marca `-- [spec 006-cobro-real-suscripciones]`.
- **FR-029**: La automatización del cobro periódico (disparar el cobro de todas las suscripciones de
  clínica cuyo `next_billing_at` ya llegó, sin que alguien lo pida manualmente) MUST NOT implementarse
  en esta especificación: queda para una especificación posterior (decisión ya tomada por el
  responsable del proyecto). Esta especificación solo deja lista la estructura completa (modelo de
  datos con ciclo y próximo cobro, y la operación de cobro manual) sobre la que esa automatización se
  apoyará.
- **FR-030**: Para la operación de cobro (FR-012), el sistema MUST resolver el `tenant_id` de quien la
  dispara consultando `GET /api/v1/authorization/me` del API de usuarios (no solo
  `GET /api/v1/authorization/check`, que no informa de organización: es una ampliación del contrato
  consumido respecto al resto de este servicio, spec 001). Si ese `tenant_id` es `null` o distinto del
  `tenant_id` de la suscripción de clínica, la operación MUST responder 404 (no 403, para no revelar
  que la suscripción existe — historia 2, escenario 7); si el API de usuarios no responde o no puede
  resolver la identidad, MUST responder 503, igual que cualquier otra duda de autorización.
- **FR-031**: El resto de operaciones de esta especificación (FR-006: crear, modificar, cancelar,
  listar y consultar) MUST seguir comprobándose con `GET /api/v1/authorization/check`, igual que el
  resto de esta API: no necesitan el `tenant_id` de quien llama, porque lo reciben explícito en el
  cuerpo o en la ruta.

### Key Entities

- **Suscripción de clínica** (`clinic_subscriptions`): liga una clínica (`tenant_id`) con un plan del
  catálogo (`subscription_id`, hacia `subscriptions`), con su ciclo de cobro (mensual o anual), la
  fecha en que empezó, la fecha de su próximo cobro y su propio estatus (Activa, con cobro pendiente
  de resolver, o Cancelada). Es la pieza que hoy no existe entre `subscriptions` (el catálogo) y una
  clínica real.
- **Cobro de una suscripción de clínica** (`clinic_subscription_charges`): un intento de cobro contra
  Pagos (historial completo, una fila por intento, rechazados incluidos): el periodo que cubre, el
  monto en centavos, la moneda, el identificador del pago en Pagos, su estatus (reflejo del
  `PaymentStatus` de Pagos), su `checkout_url` mientras esté pendiente y la `Idempotency-Key` usada.
  La suscripción de clínica referencia su cobro **vigente** (el más reciente) entre los varios que
  puede acumular en su historial.
- **Plan** (`subscriptions`): ya existe (spec 001); esta especificación lo referencia por
  `subscription_id`, sin copiar su precio ni sus límites.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las suscripciones de clínica creadas con un plan Activo quedan con el
  `next_billing_at` correcto (inmediato o tras `trial_days`), verificado con y sin periodo de prueba.
- **SC-002**: Disparar el cobro de una suscripción de clínica produce, contra la simulación de Pagos,
  exactamente el cuerpo esperado (`amount` en centavos exactos, `currency: MXN`, `resource_type` y
  `resource_id` correctos) en el 100 % de los casos de prueba (mensual, anual, con y sin centavos en
  el precio).
- **SC-003**: Repetir la operación de cobro para el mismo periodo de la misma suscripción de clínica
  nunca produce un segundo cargo: la simulación de Pagos recibe la misma `Idempotency-Key` y responde
  con el pago ya creado en el 100 % de los reintentos probados.
- **SC-004**: Un cobro que la simulación de Pagos marca `approved` se refleja en la siguiente consulta
  de esa suscripción de clínica sin ninguna acción manual aparte de consultarla, y su estatus pasa a
  Activa con `next_billing_at` avanzado un ciclo.
- **SC-005**: Ninguna prueba de la suite depende de que `mailySoft-pagos` o `mailySoft-usuarios`
  reales estén disponibles (Principio V); toda ella pasa solo con las simulaciones de este
  repositorio.
- **SC-006**: La suite completa de pytest de este repositorio sigue en verde después de esta
  especificación, incluidas las pruebas de las specs 001 a 005 ya existentes.

## Assumptions

- **Automatización periódica fuera de alcance** (FR-029): esta especificación no dispara cobros por sí
  sola según el calendario; alguien (una persona o, en una spec futura, un proceso programado) debe
  pedir cada cobro a través de la operación de la historia 2.
- **mailySoft-pagos no cambia**: su contrato (`resource_type`/`resource_id` opacos, dinero en enteros,
  `tenant_id` solo desde el token de quien llama) ya es genérico y estable; esta especificación se
  adapta a él. Si el plan encuentra que algo exige cambiarlo, se documenta y se avisa (FR-023) en vez
  de modificarlo.
- **`payments:*` y `clinic_subscriptions:*` como prerrequisito simulado** (FR-025, FR-026): igual que
  Agenda hizo con `schedules:*`/`appointments:*` antes de que Usuarios los tuviera (spec 019 de
  Usuarios), y que Pagos hace con los suyos: se desarrolla y prueba contra una simulación propia de
  este repositorio; dar de alta esos permisos en el Usuarios real es trabajo de otra especificación,
  en otro repositorio.
- **Moneda fija**: todo cobro de esta especificación es en pesos mexicanos (`MXN`), igual que los
  precios del catálogo de planes; no hay multi-moneda.
- **Una Activa por clínica**: una clínica tiene a lo sumo una suscripción de clínica Activa (o con
  cobro pendiente de resolver) a la vez; cambiar de plan es cancelar la vigente y crear una nueva, no
  una operación de «cambiar de plan» en sitio.
- **El precio del cobro es el vigente del plan al momento de cobrar**, no uno copiado al asignar la
  suscripción: un cambio de precio del plan afecta al siguiente cobro, nunca a uno ya creado en Pagos.
- **Sincronización por consulta, no por tarea en segundo plano**: esta especificación resuelve el
  estatus de un cobro `pending` preguntando a Pagos en el momento en que alguien lo consulta (historia
  3), no con un proceso periódico propio que recorra todos los cobros pendientes; eso, si hiciera
  falta, es parte de la misma automatización diferida de FR-029.
- **Dos personas distintas, dos tokens distintos**: quien administra la plataforma (FR-006) y quien
  dispara el cobro de su propia clínica (FR-012) nunca son la misma llamada. Esto implica que, para
  que una clínica recién asignada pueda pagar, alguien de esa clínica necesita enterarse (fuera de
  alcance de esta especificación: notificarlo es un problema de otro sistema, p. ej. `maily-backoffice`
  o un correo).
- **`GET /api/v1/authorization/me` ya existe en el `mailySoft-usuarios` real** (spec 019, consumida
  hoy por `mailySoft-agenda` y `mailySoft-pagos`): extender la integración de este servicio para
  usarla (FR-030), además de `GET /api/v1/authorization/check` que ya usa, no exige ningún cambio en
  `mailySoft-usuarios`.

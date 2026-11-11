# Feature Specification: Cobro Real de Suscripciones de Clínicas

**Feature Branch**: `010-cobro-real-suscripciones`

**Created**: 2026-11-10 · **Rediseñada**: 2026-11-11 (ver «Clarifications», sesión 2026-11-11)

**Status**: Draft

**Input**: User description: "En maily-system-api, construir el cobro real de suscripciones de
clínicas usando mailySoft-pagos (microservicio de pagos genérico, ya con Mercado Pago funcionando).
(1) la operación de cobrar: llama a POST /api/v1/payments de mailySoft-pagos con provider:
mercado_pago, resource_type/resource_id, amount en centavos del precio del plan según el ciclo,
currency: MXN (el tenant_id lo decide quien llama, nunca se envía en el cuerpo); (2) cómo se entera
System API de que el pago se aprobó o rechazó — Pagos no notifica a sus consumidores, así que System
API debe resolverlo con el diseño que mejor encaje; (3) seguir el flujo de Spec Kit de este
repositorio. Fuera de alcance: modificar mailySoft-pagos y dar de alta `payments:*` en el catálogo
real de mailySoft-usuarios (se desarrolla y prueba contra una simulación, igual que ya hacen Agenda y
Pagos con la suya)."

## Clarifications

### Session 2026-11-10

- Q: Dado que Pagos exige que el `tenant_id` de un pago salga únicamente del token de quien llama
  (nunca del cuerpo), ¿quién está autorizado a disparar el cobro de la suscripción de una clínica, de
  modo que ese mismo token se pueda reenviar a Pagos? → A: Una persona de la propia clínica (p. ej.
  su Owner), cuyo token System API reenvía a Pagos sin modificar; es la única forma de que Pagos
  resuelva el `tenant_id` correcto con su propio `GET /api/v1/authorization/me`, sin tocar su
  contrato.
- Q: ¿Hay que guardar cada intento de cobro (incluidos los rechazados) como historial propio, o basta
  con el último cobro y su estatus? → A: Historial completo: una tabla
  (`clinic_subscription_charges`) con una fila por intento, rechazados incluidos, necesaria para
  auditoría, soporte y para reintentar un cobro rechazado sin perder el anterior.

### Session 2026-11-11 — Rediseño de dónde vive la asignación clínica↔plan

- Q: La primera versión de esta especificación introducía su propia tabla `clinic_subscriptions`
  (clínica + plan + ciclo + estatus) dentro de `maily-system-api`. El arquitecto del proyecto revisó
  ese diseño: ¿dónde debe vivir esa asignación? → A: **En el futuro microservicio «Clínicas»,
  no en `maily-system-api`.** Es exactamente el mismo precedente que ya sigue este repositorio con el
  número de clínicas por plan (Principio IX, `clinics-api-integration.md` de la spec 001): un dato
  que pertenece a otro sistema se consulta, nunca se copia ni se guarda aquí. `maily-system-api`
  pasa a ser, para esta pieza, solo **quien ejecuta el cobro y guarda su historial** — nunca quien
  decide qué clínica tiene qué plan.
- Q: Si `maily-system-api` ya no guarda la asignación, ¿de dónde saca lo que necesita para cobrar
  (a quién pertenece, qué plan, qué ciclo) y qué periodo cobra cada vez? → A: Lo pide a Clínicas
  (una consulta de solo lectura, nueva, documentada como prerrequisito — Clínicas no existe todavía,
  igual que «módulos de clínica» no existía para Usuarios antes de su spec 013) para el `tenant_id`,
  el `subscription_id` (el plan, del catálogo de **este** servicio) y el ciclo de cobro; **el periodo
  que se cobra lo decide quien dispara el cobro** (lo envía en la solicitud), porque Clínicas es quien
  sabrá, en su propia interfaz, cuál es el periodo pendiente — `maily-system-api` no necesita
  calcularlo ni Clínicas necesita enterarse del resultado para que esta pieza funcione (ver
  Assumptions: avisar a Clínicas del resultado queda fuera de alcance).

## User Scenarios & Testing *(mandatory)*

Los actores son: **una persona de la propia clínica** (p. ej. su Owner, con `tenant_id` propio), la
única que puede disparar el cobro de su suscripción, porque Pagos resuelve el `tenant_id` del pago
exclusivamente con el token de quien llama; **quien administra la plataforma** (ya existe, spec 001:
mantiene `subscriptions`, el catálogo de planes; sin organización propia), que ahora solo **consulta**
el historial de cobros (nunca lo crea a mano); **Clínicas**, el futuro microservicio que decide qué
clínica tiene qué plan y con qué ciclo (`maily-system-api` lo consulta, nunca lo guarda — Principio
IX); y **mailySoft-pagos**, el microservicio al que este servicio delega el cobro real sin conocer
tarjetas, proveedores ni nada del dominio de pagos (solo referencia un recurso propio con
`resource_type` y `resource_id`, principio X de Pagos).

Hoy `subscriptions` es únicamente el catálogo de planes: no existe ninguna operación que cobre nada.
Esta especificación añade la operación que cobra un plan del catálogo, para una suscripción de
clínica que Clínicas ya decidió, contra Mercado Pago a través de Pagos — y el historial de esos
cobros, que sí es responsabilidad de este servicio. Asignar un plan a una clínica, su ciclo de cobro
y cancelarla **no** son parte de esta especificación: viven en Clínicas.

### User Story 1 - Cobrar la suscripción de una clínica (Priority: P1)

Una persona de la propia clínica dispara el cobro de su suscripción, indicando qué suscripción
(`clinic_subscription_id`, un identificador que pertenece a Clínicas) y qué periodo cubre (una
fecha). El sistema consulta a Clínicas los datos de esa suscripción (a qué clínica pertenece, qué
plan del catálogo y su ciclo), comprueba que quien llama pertenece a esa misma clínica, calcula el
monto exacto (en centavos) a partir del `monthly_price` o `annual_price` **vigente** del plan según
el ciclo, y pide a mailySoft-pagos que cree un pago genérico (`provider: mercado_pago`,
`resource_type: system-api:clinic-subscription`, `resource_id` = el `clinic_subscription_id` de
Clínicas, `amount`, `currency: MXN`), con una clave de idempotencia propia del periodo para que
repetir la petición no duplique el cargo. La respuesta de Pagos (con la URL de checkout mientras el
pago no se resuelva) queda guardada en el historial de cobros de este servicio.

**Why this priority**: Es la razón de ser de la especificación: sin esto, el catálogo de planes y la
asignación que haga Clínicas no producen ningún cargo real.

**Independent Test**: Con la simulación de Clínicas devolviendo una suscripción válida y Pagos
simulado, disparar el cobro y comprobar que se llama a `POST /api/v1/payments` con los campos
exactos esperados y que la respuesta (incluida la URL de checkout) queda en el historial.

**Acceptance Scenarios**:

1. **Given** Clínicas reporta una suscripción de clínica con ciclo mensual y un plan de
   `monthly_price` 1299.00, **When** se dispara su cobro para un periodo, **Then** Pagos recibe
   `amount: 129900`, `currency: MXN`, `resource_type: system-api:clinic-subscription` y el
   `resource_id` de esa suscripción de clínica, y la respuesta (con su `id` de pago y su
   `checkout_url`) queda guardada en el historial con ese periodo.
2. **Given** la misma suscripción de clínica y el mismo periodo, **When** el cobro se dispara dos
   veces (p. ej. un reintento tras un corte de red), **Then** Pagos recibe la misma
   `Idempotency-Key` las dos veces y responde con el mismo pago ya creado, sin cobrar dos veces.
3. **Given** que Clínicas responde que esa suscripción no existe, está cancelada, o no pertenece a la
   organización de quien llama, **When** se intenta disparar su cobro, **Then** responde 404 (no
   revela cuál de los tres motivos fue, igual que el patrón de «misma organización» de
   `mailySoft-usuarios` spec 019) y no se llama a Pagos.
4. **Given** que Clínicas no responde, agota el tiempo de espera o contesta algo inesperado, **When**
   se dispara el cobro, **Then** responde 503 y no se llama a Pagos ni se guarda nada.
5. **Given** que el plan que Clínicas reporta para esa suscripción ya no está Activo en el catálogo de
   este servicio (fue eliminado o bloqueado), **When** se dispara el cobro, **Then** responde 409 sin
   llamar a Pagos.
6. **Given** que Pagos no responde, agota el tiempo de espera o contesta algo inesperado, **When** se
   dispara el cobro, **Then** la operación responde 503 y no se guarda ningún cobro.
7. **Given** que Pagos rechaza el token (401) o responde que no hay permiso (403) para
   `payments:write`, **When** se dispara el cobro, **Then** System API traduce esa respuesta a su
   propio error (401 o 403) sin filtrar el cuerpo ni las cabeceras de Pagos, y no se guarda ningún
   cobro.
8. **Given** un plan con `annual_price` 12990.00 y ciclo anual, **When** se dispara el cobro, **Then**
   el monto enviado a Pagos es `1299000` (centavos exactos, sin redondeos de punto flotante).
9. **Given** la misma suscripción de clínica y el mismo periodo, con un cobro anterior ya `approved`,
   **When** se intenta disparar el cobro de nuevo, **Then** responde 409 (ese periodo ya está
   cobrado) sin llamar a Pagos. Un cobro anterior `rejected` o `cancelled` del mismo periodo **no**
   bloquea el reintento (escenario 2).

---

### User Story 2 - Conocer si el cobro se aprobó o se rechazó (Priority: P1)

Como mailySoft-pagos no notifica a quien lo integra (no emite webhooks propios, solo los recibe de
Mercado Pago), System API resuelve el estatus de un cobro consultando `GET /api/v1/payments/{id}` de
Pagos. Quien consulta un cobro que sigue pendiente obtiene una respuesta ya actualizada (System API
pregunta a Pagos en el momento de la consulta, no solo lee lo que guardó la última vez); un cobro ya
resuelto (aprobado, rechazado, reembolsado…) se responde con el dato local, sin volver a preguntar.

**Why this priority**: Sin esto, un cobro se queda «a ciegas»: nadie sabría si el cargo entró o si hay
que reintentar o avisar a la clínica.

**Independent Test**: Crear un cobro pendiente, cambiar su estatus en la simulación de Pagos a
aprobado, consultarlo desde System API y comprobar que la respuesta ya refleja «aprobado» sin que
nadie haya llamado a una operación de sincronización aparte.

**Acceptance Scenarios**:

1. **Given** un cobro cuyo estatus en Pagos sigue siendo `pending`, **When** se consulta ese cobro,
   **Then** System API pregunta a Pagos en ese instante y la respuesta refleja el estatus vigente.
2. **Given** un cobro cuyo estatus en Pagos ya es `approved`, `rejected`, `cancelled`,
   `partially_refunded` o `refunded`, **When** se consulta de nuevo, **Then** System API responde con
   el dato guardado localmente, sin llamar otra vez a Pagos.
3. **Given** un cobro `pending`, **When** se consulta y Pagos no responde o agota el tiempo de
   espera, **Then** System API responde con el último estatus conocido localmente (`pending`) en vez
   de fallar la consulta completa, y no se pierde el cobro.

---

### User Story 3 - Consultar el historial de cobros (Priority: P2)

Quien tiene permiso (`clinic_subscriptions:read`, de rol de Sistema — quien administra la
plataforma) puede listar y consultar el historial de cobros (paginado, filtrable por
`clinic_subscription_id` y por `tenant_id`), rechazados incluidos.

**Why this priority**: Es la visibilidad que hace operable todo lo anterior (soporte, facturación,
auditoría), pero el sistema ya es útil sin ella si solo se necesita cobrar.

**Independent Test**: Con varios cobros de distintas suscripciones de clínica, listar y consultar por
identificador y comprobar que la forma de la respuesta coincide con el contrato.

**Acceptance Scenarios**:

1. **Given** varios cobros, **When** se listan, **Then** la respuesta está paginada, del más reciente
   al más antiguo, y cada uno trae su `clinic_subscription_id`, su `tenant_id`, su periodo, su monto,
   su estatus y su `checkout_url` (o `null`).
2. **Given** un cobro que no existe, **When** se consulta por identificador, **Then** responde 404.
3. **Given** una persona sin el permiso de lectura, **When** intenta listar o consultar, **Then**
   responde 403, sin revelar ningún dato.

---

### Edge Cases

- **Clínicas no existe todavía como servicio real**: se desarrolla y prueba contra una simulación
  propia de este repositorio (igual que `payments:*`, ver Assumptions); sustituirla por el servicio
  real es solo un cambio de configuración (`CLINICS_API_BASE_URL`, que ya existe desde la spec 001).
- **Plan modificado o eliminado después de cobrar una vez**: el cobro siempre usa el precio
  **vigente** del plan en el momento de cobrar (nunca uno copiado); si el plan ya no está Activo, no
  se puede disparar un nuevo cobro (409) hasta que Clínicas le asigne uno vigente — eso lo decide
  Clínicas, no esta especificación.
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
- **Dos periodos distintos del mismo `clinic_subscription_id` pedidos el mismo día**: son dos cobros
  distintos (claves de idempotencia distintas); esta especificación no valida que el periodo
  «tenga sentido» (p. ej. que sea el que realmente toca según el ciclo): esa validación, si hace
  falta, es de Clínicas o de quien dispara el cobro.

## Requirements *(mandatory)*

### Functional Requirements

**Cobro**

- **FR-001**: El sistema MUST exponer una operación que dispara el cobro de un
  `clinic_subscription_id` (identificador opaco que pertenece a Clínicas) para un periodo dado
  (fecha), enviados por quien dispara el cobro.
- **FR-002**: El sistema MUST consultar a Clínicas (operación nueva, solo lectura — ver «Integración
  con Clínicas») los datos de ese `clinic_subscription_id`: su `tenant_id`, el `subscription_id` (el
  plan, del catálogo de este servicio) y el ciclo de cobro (`monthly` o `annual`). MUST NOT
  guardarse ninguno de estos datos de forma permanente: se usan solo durante la operación (Principio
  IX, igual que `clinics_count`).
- **FR-003**: Si Clínicas responde que esa suscripción no existe, está cancelada, o pertenece a otra
  organización que la de quien llama, el sistema MUST responder 404, sin revelar cuál de los tres
  motivos fue.
- **FR-004**: Si Clínicas no responde, agota el tiempo de espera o responde algo inesperado, el
  sistema MUST responder 503 y MUST NOT llamar a Pagos ni guardar nada (fail closed, igual que el
  resto de dependencias obligatorias de este servicio).
- **FR-005**: El sistema MUST leer el plan (`subscription_id` de FR-002) del catálogo existente
  (`subscriptions`, spec 001) y exigir que esté Activo (409 si no existe, está Inactivo, Bloqueado o
  Eliminado).
- **FR-006**: El monto a cobrar MUST calcularse en la unidad mínima de la moneda (centavos) a partir
  del precio **vigente** del plan (`monthly_price` si el ciclo es `monthly`, `annual_price` si es
  `annual`), sin redondeos de punto flotante (los precios son `NUMERIC(10,2)`: multiplicar por 100
  siempre da un entero exacto).
- **FR-007**: El sistema MUST llamar a `POST /api/v1/payments` de mailySoft-pagos con
  `provider: mercado_pago`, `amount` (FR-006), `currency: MXN`,
  `resource_type: system-api:clinic-subscription`, `resource_id` = el `clinic_subscription_id` (como
  texto) y una `Idempotency-Key` propia, determinista para el mismo periodo de cobro (mismo
  `clinic_subscription_id` + mismo periodo), de modo que repetir la operación para el mismo periodo
  nunca duplique el cargo.
- **FR-008**: El `tenant_id` del pago MUST seguir siendo responsabilidad exclusiva de Pagos: System
  API MUST NOT enviarlo en el cuerpo de `POST /api/v1/payments` (Principio X de Pagos) y MUST
  reenviar, sin modificar, el token de quien disparó el cobro, para que Pagos resuelva el `tenant_id`
  con su propio `GET /api/v1/authorization/me`.
- **FR-009**: Disparar el cobro MUST exigir el permiso `clinic_subscriptions:charge`, que MUST poder
  asignarse a un rol de tipo Clínica en el catálogo de `mailySoft-usuarios` (p. ej. Owner): quien lo
  dispara MUST pertenecer a la misma organización que reportó Clínicas para ese
  `clinic_subscription_id` (su `tenant_id`, resuelto con `GET /api/v1/authorization/me` de Usuarios —
  FR-016), porque ese es el único token que Pagos puede traducir al `tenant_id` correcto (FR-008).
- **FR-010**: El sistema MUST guardar la respuesta de Pagos (identificador del pago, estatus,
  `checkout_url`, monto, moneda y la `Idempotency-Key` usada) como una fila del historial de cobros,
  junto con el `clinic_subscription_id`, el `tenant_id` (de FR-002, para que quien administra la
  plataforma pueda filtrar sin volver a preguntar a Clínicas) y el periodo.
- **FR-011**: El sistema MUST rechazar (409) un nuevo cobro del mismo `clinic_subscription_id` y
  periodo si ya existe uno `approved` en el historial; uno `pending`, `rejected` o `cancelled` del
  mismo periodo MUST NOT bloquearlo: la operación reintenta contra Pagos con la misma
  `Idempotency-Key` determinista (research R3, R7) en vez de rechazarlo localmente.
- **FR-012**: Si Pagos no responde, agota el tiempo de espera o responde algo inesperado, la
  operación de cobro MUST responder 503 y MUST NOT guardar ningún cobro (ninguna duda ejecuta el
  cobro).

**Conocer el resultado del cobro**

- **FR-013**: El sistema MUST resolver el estatus de un cobro `pending` consultando
  `GET /api/v1/payments/{id}` de Pagos en el momento en que se consulta ese cobro (sin que haga falta
  una operación de sincronización aparte); un cobro ya resuelto (`approved`, `rejected`, `cancelled`,
  `partially_refunded`, `refunded`) MUST responderse con el dato guardado localmente, sin volver a
  llamar a Pagos.
- **FR-014**: Si al consultar un cobro `pending` Pagos no responde o agota el tiempo de espera, la
  consulta MUST responder con el último estatus conocido localmente (`pending`) en vez de fallar toda
  la operación; MUST NOT perderse el cobro.
- **FR-015**: Toda actualización del estatus local de un cobro a partir de la respuesta de Pagos MUST
  ser una traducción explícita del estatus de Pagos (`PaymentStatus`, contrato de Pagos); un estatus
  de Pagos que este servicio no reconozca MUST tratarse como «no disponible» (igual que una falla de
  Pagos), nunca como un estatus inventado.

**Integración con Clínicas**

- **FR-016**: El sistema MUST ampliar el cliente ya existente del API de clínicas
  (`src/integrations/clinics_api.py`, spec 001) con una operación nueva de solo lectura que, dado un
  `clinic_subscription_id`, devuelve su `tenant_id`, su `subscription_id` y su ciclo de cobro, o que
  no existe/no pertenece a quien pregunta (sin revelar cuál). Esta operación MUST documentarse como
  contrato consumido (`contracts/clinics-api-integration.md`) y MUST NOT darse de alta en ningún
  servicio real como parte de esta especificación: es un prerrequisito de Clínicas, que **no existe
  todavía** (a diferencia de `mailySoft-usuarios`, que sí existe y solo le falta el catálogo de
  permisos).
- **FR-017**: El desarrollo y las pruebas MUST usar una simulación de esta operación (ampliación de
  `tests/stubs/clinics_api/app.py`), igual que ya hace este servicio con la cuenta de clínicas por
  plan (Principio V).

**Integración con mailySoft-pagos**

- **FR-018**: Toda llamada a Pagos (crear un cobro, consultarlo) MUST ser asíncrona (httpx), con un
  tiempo máximo de espera total propio (variable de entorno) y MUST NOT reintentarse automáticamente.
- **FR-019**: Las fallas de Pagos MUST traducirse a los errores propios de este servicio (código en
  inglés, mensaje en español); MUST NOT filtrarse al cliente el cuerpo, las cabeceras ni la dirección
  interna de Pagos.
- **FR-020**: La dirección, el tiempo de espera y, si aplica, las credenciales para llamar a Pagos
  MUST provenir de variables de entorno validadas al arrancar (mismo patrón que `USERS_API_BASE_URL` y
  `CLINICS_API_BASE_URL`).
- **FR-021**: El contrato consumido de Pagos (`POST /api/v1/payments`, `GET /api/v1/payments/{id}`,
  sus campos, sus códigos de error y su traducción) MUST documentarse en esta especificación
  (`contracts/payments-api-integration.md`), con su simulación en las pruebas (Principio V).
- **FR-022**: Esta especificación MUST NOT modificar `mailySoft-pagos`. Si al planear se descubre que
  algo de lo pedido exige cambiar su contrato o sus reglas, el plan MUST documentarlo como hallazgo y
  avisar al responsable del proyecto en vez de modificar ese repositorio.

**Control de acceso y permisos**

- **FR-023**: Toda operación de esta especificación MUST exigir token y su permiso
  (`clinic_subscriptions:read` para listar y consultar el historial, `clinic_subscriptions:charge`
  para disparar el cobro — FR-009), comprobado contra `mailySoft-usuarios` igual que el resto de la
  API (Principio VIII), y declarado en `contracts/permission-matrix.md`.
- **FR-024**: Los permisos nuevos de esta especificación (`clinic_subscriptions:*` en
  `mailySoft-usuarios`, y `payments:write`/`payments:read` que exige Pagos) MUST NOT darse de alta en
  el catálogo real de `mailySoft-usuarios` como parte de esta especificación: es un prerrequisito
  documentado (igual que ya lo hacen `mailySoft-agenda` y `mailySoft-pagos` con los suyos) y el
  desarrollo y las pruebas MUST usar una simulación que reproduzca ese catálogo ya existente.
- **FR-025**: Mientras los prerrequisitos de FR-016 y FR-024 no estén resueltos en los servicios
  reales, esta funcionalidad MUST seguir funcionando contra las simulaciones sin cambios de código;
  sustituirlas MUST ser solo un cambio de configuración (`CLINICS_API_BASE_URL`,
  `USERS_API_BASE_URL`, `PAGOS_API_BASE_URL`), igual que las demás integraciones de este servicio.
- **FR-026**: Para la operación de cobro (FR-009), el sistema MUST resolver el `tenant_id` de quien la
  dispara consultando `GET /api/v1/authorization/me` del API de usuarios (no solo
  `GET /api/v1/authorization/check`, que no informa de organización). Si ese `tenant_id` es `null` o
  distinto del `tenant_id` que reportó Clínicas para ese `clinic_subscription_id`, la operación MUST
  responder 404 (no 403, para no revelar que la suscripción existe — historia 1, escenario 3); si el
  API de usuarios no responde o no puede resolver la identidad, MUST responder 503.
- **FR-027**: Listar y consultar el historial de cobros MUST seguir comprobándose con
  `GET /api/v1/authorization/check`, igual que el resto de esta API: no necesita el `tenant_id` de
  quien llama.

**Gobierno y pruebas**

- **FR-028**: Toda la funcionalidad MUST tener pruebas automatizadas (Principio V): unitarias de
  Services con los clientes de Pagos, de Usuarios y de Clínicas sustituidos por dobles de prueba, de
  contrato de cada operación, de Repositories contra PostgreSQL 17 real, y la prueba que recorre
  todas las rutas y falla si alguna carece de permiso declarado.
- **FR-029**: El cambio de esquema (la tabla del historial de cobros) MUST entregarse con una
  migración de Alembic reversible y reflejarse en `project-definition/DATA_SCHEMA.md` con la marca
  `-- [spec 010-cobro-real-suscripciones]`.
- **FR-030**: La automatización del cobro periódico (recorrer las suscripciones de clínica que
  Clínicas marque como pendientes de cobrar y disparar su cobro sin que alguien lo pida manualmente)
  MUST NOT implementarse en esta especificación: queda para una especificación posterior (decisión ya
  tomada por el responsable del proyecto). Esta especificación solo deja lista la operación de cobro
  manual y su historial, sobre los que esa automatización se apoyará.

### Key Entities

- **Cobro** (`clinic_subscription_charges`): un intento de cobro contra Pagos para un
  `clinic_subscription_id` (identificador opaco que pertenece a Clínicas, fuera de este servicio) y
  un periodo (historial completo, una fila por intento, rechazados incluidos): el `tenant_id` (copiado
  de la respuesta de Clínicas al momento de cobrar, para filtrar sin volver a preguntarle), el monto
  en centavos, la moneda, el identificador del pago en Pagos, su estatus (reflejo del `PaymentStatus`
  de Pagos), su `checkout_url` mientras esté pendiente y la `Idempotency-Key` usada.
- **Plan** (`subscriptions`): ya existe (spec 001); esta especificación lo referencia por
  `subscription_id` (que Clínicas reporta para cada suscripción de clínica), sin copiar su precio ni
  sus límites.
- **Suscripción de una clínica**: **no es una entidad de este servicio.** Vive en el futuro
  microservicio Clínicas (qué clínica, qué plan, qué ciclo, su estatus); `maily-system-api` solo la
  referencia por su identificador opaco (`clinic_subscription_id`) al cobrar y al guardar el
  historial.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Disparar el cobro de una suscripción de clínica produce, contra las simulaciones de
  Clínicas y de Pagos, exactamente el cuerpo esperado (`amount` en centavos exactos, `currency: MXN`,
  `resource_type` y `resource_id` correctos) en el 100 % de los casos de prueba (mensual, anual, con
  y sin centavos en el precio).
- **SC-002**: Repetir la operación de cobro para el mismo periodo del mismo `clinic_subscription_id`
  nunca produce un segundo cargo: la simulación de Pagos recibe la misma `Idempotency-Key` y responde
  con el pago ya creado en el 100 % de los reintentos probados.
- **SC-003**: Un cobro que la simulación de Pagos marca `approved` se refleja en la siguiente consulta
  de ese cobro sin ninguna acción manual aparte de consultarlo.
- **SC-004**: Ninguna prueba de la suite depende de que `mailySoft-pagos`, `mailySoft-usuarios` o
  Clínicas reales estén disponibles (Principio V); toda ella pasa solo con las simulaciones de este
  repositorio.
- **SC-005**: La suite completa de pytest de este repositorio sigue en verde después de esta
  especificación, incluidas las pruebas de las specs 001 a 009 ya existentes.

## Assumptions

- **Automatización periódica fuera de alcance** (FR-030): esta especificación no dispara cobros por sí
  sola según el calendario; alguien (una persona o, en una spec futura, un proceso programado) debe
  pedir cada cobro a través de la operación de la historia 1.
- **mailySoft-pagos no cambia**: su contrato (`resource_type`/`resource_id` opacos, dinero en enteros,
  `tenant_id` solo desde el token de quien llama) ya es genérico y estable; esta especificación se
  adapta a él.
- **`payments:*` y `clinic_subscriptions:*` como prerrequisito simulado en Usuarios** (FR-024,
  FR-025): igual que Agenda hizo con `schedules:*`/`appointments:*` antes de que Usuarios los tuviera
  (spec 019 de Usuarios), y que Pagos hace con los suyos.
- **Clínicas como prerrequisito simulado, pero el servicio en sí no existe todavía** (FR-016, FR-017):
  a diferencia de Usuarios (que ya existe y solo le falta un permiso), Clínicas no es un servicio real
  hoy en este workspace. La simulación de pruebas (`tests/stubs/clinics_api/app.py`, ampliada) es la
  única fuente de la operación nueva hasta que exista; sustituirla por el servicio real es trabajo de
  otro repositorio, no de esta especificación.
- **Qué periodo se cobra lo decide quien dispara el cobro**, no `maily-system-api` ni Clínicas en esta
  entrega: se envía en la solicitud (fecha). Calcular automáticamente «cuál es el periodo pendiente»
  es parte de la automatización diferida (FR-030) y de Clínicas, que es quien sabrá mostrarlo.
- **No se avisa a Clínicas del resultado del cobro**: esta especificación no notifica a Clínicas si un
  cobro quedó aprobado o rechazado (no hay, todavía, un contrato de escritura hacia ella). El
  historial de este servicio es la fuente de verdad de lo que `maily-system-api` hizo; si Clínicas
  necesita enterarse (p. ej. para avanzar su propio «próximo cobro»), es una pieza de su propia
  especificación futura, fuera de alcance aquí.
- **El precio del cobro es el vigente del plan al momento de cobrar**, no uno copiado: un cambio de
  precio del plan afecta al siguiente cobro, nunca a uno ya creado en Pagos.
- **Moneda fija**: todo cobro de esta especificación es en pesos mexicanos (`MXN`).
- **`GET /api/v1/authorization/me` ya existe en el `mailySoft-usuarios` real** (spec 019, consumida
  hoy por `mailySoft-agenda` y `mailySoft-pagos`): extender la integración de este servicio para
  usarla (FR-026), además de `GET /api/v1/authorization/check` que ya usa, no exige ningún cambio en
  `mailySoft-usuarios`.

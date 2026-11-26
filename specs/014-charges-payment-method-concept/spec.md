# Feature Specification: Forma de pago y concepto amigable de cada cobro

**Feature Branch**: `014-charges-payment-method-concept`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "A los pagos les hace falta identificar la forma de pago y la referencia o
concepto amigable del pago." (seguimiento directo del rediseño de la pantalla de pago del Frontend
(mailySoft-frontend) y de las specs 012-payment-history-charges / 013-charges-plan-and-status-filter de
este mismo servicio). Dos campos nuevos en `GET /api/v1/subscription-periods/{organization_id}/charges`:
(1) `payment_method` (`card`/`oxxo`/`transfer`), con qué se pagó, conocido solo cuando el cobro se
resuelve, traducido por este servicio desde lo que reporta Pagos (spec `005-payment-method` de
mailySoft-pagos, que expone `payment_method_id`/`payment_type_id` en crudo); (2) `concept`, el mismo texto
amigable que ya se le manda a Pagos como `description` al crear el cobro, nunca guardado localmente hasta
ahora.

## Clarifications

### Session 2026-11-25

La persona responsable pidió ejecutar el ciclo completo de Spec Kit sin preguntas y con la opción
recomendada en cada duda.

- Q: ¿Quién traduce el `payment_type_id` de Mercado Pago a `card`/`oxxo`/`transfer`? → A: Este servicio,
  nunca Pagos. Pagos (spec 005) expone el valor en crudo, sin opinión de negocio; traducirlo a estas tres
  categorías es una decisión de qué es una «suscripción», que le toca a quien sabe eso.
- Q: ¿Qué pasa con un `payment_type_id` que Pagos reporta pero que este servicio no reconoce (por ejemplo
  una billetera digital)? → A: `payment_method: null`, nunca adivinar ni forzarlo a una de las tres
  categorías conocidas.
- Q: ¿Se puede reconstruir la forma de pago o el concepto de los cobros que ya existen? → A: No. La forma
  de pago nunca se preguntó antes de esta spec (ni este servicio ni Pagos la guardaban); el concepto se le
  mandaba a Pagos pero nunca se guardaba una copia local. Ambos campos publican `null` en los cobros
  anteriores a esta migración, sin backfill.
- Q: ¿Un cobro cerrado (rechazado, cancelado) también publica la forma de pago? → A: Sí, cuando Pagos la
  reportó: un pago rechazado con tarjeta todavía dice que fue con tarjeta. Solo queda `null` si Pagos nunca
  llegó a reportarla (por ejemplo, un cobro que se cerró sin que el pagador llegara a elegir método).

## User Scenarios & Testing *(mandatory)*

El actor principal sigue siendo **el Dueño de una organización**, que ahora ve en su historial de pagos
(Frontend) con qué se pagó cada cobro y un concepto legible, sin tener que adivinarlo por el monto o la
fecha.

### User Story 1 - Cada cobro resuelto dice con qué se pagó (Priority: P1)

El Dueño ve, junto a cada cobro aplicado o cerrado de su historial, si fue con tarjeta, en efectivo (OXXO)
o por transferencia/depósito bancario (SPEI) — las tres categorías que ya usa la pantalla de pago del
Frontend.

**Why this priority**: es el dato que el rediseño del Frontend necesita mostrar junto al estado de cada
cobro; sin él, dos cobros del mismo monto e idéntico plan no se distinguen a simple vista.

**Independent Test**: aprobar un cobro cuyo pago fue con tarjeta y otro con OXXO, y comprobar que el
historial publica `payment_method: "card"` y `payment_method: "oxxo"` respectivamente.

**Acceptance Scenarios**:

1. **Given** un cobro que Pagos resuelve como aprobado con `payment_type_id: "credit_card"`, **When** se
   pide el historial, **Then** ese cobro publica `payment_method: "card"` (FR-001, FR-002).
2. **Given** el mismo caso con `payment_type_id: "ticket"` o `"bank_transfer"`, **When** se pide el
   historial, **Then** publica `"oxxo"` o `"transfer"` respectivamente.
3. **Given** un cobro todavía `pending`, **When** se pide el historial, **Then** publica
   `payment_method: null` (FR-003): no se conoce hasta que se resuelve.
4. **Given** un cobro que Pagos resuelve con un `payment_type_id` que este servicio no reconoce, **When**
   se pide el historial, **Then** publica `payment_method: null`, nunca una de las tres categorías por
   aproximación (FR-004).
5. **Given** un cobro rechazado o cancelado para el que Pagos sí reportó un método, **When** se pide el
   historial, **Then** ese cobro también publica su `payment_method` (FR-005).
6. **Given** un cobro creado antes de esta migración, **When** se pide el historial, **Then** publica
   `payment_method: null` de forma permanente (FR-006).

---

### User Story 2 - Cada cobro tiene un concepto amigable (Priority: P2)

El Dueño ve, junto a cada cobro, el mismo texto legible que ya recibe Mercado Pago como concepto del cobro
(«Suscripción Titán — mensual»), en vez de tener que inferirlo del monto y la fecha.

**Why this priority**: ya existe el texto (se le manda a Pagos desde que existe el cobro de suscripciones,
spec 010); falta guardarlo localmente para no depender de una llamada adicional a Pagos solo para leerlo.

**Independent Test**: crear un cobro y comprobar que el historial publica el mismo texto que se envió a
Pagos como `description` al crearlo.

**Acceptance Scenarios**:

1. **Given** una organización en «Plan Titán» con cobro mensual, **When** se genera un cobro y luego se
   pide el historial, **Then** ese cobro publica `concept: "Suscripción Titán — mensual"` (FR-007,
   FR-008).
2. **Given** un cobro creado antes de esta migración, **When** se pide el historial, **Then** publica
   `concept: null` (FR-009); no se intenta reconstruir desde Pagos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cada cobro publicado por `GET /api/v1/subscription-periods/{organization_id}/charges` MUST
  incluir un campo `payment_method` (nullable), uno de `card`/`oxxo`/`transfer`.
- **FR-002**: `payment_method` MUST calcularse, al resolver el cobro (aplicado o cerrado), a partir del
  `payment_type_id` que reporta la API de pagos (mailySoft-pagos, spec `005-payment-method`): `credit_card`,
  `debit_card` y `prepaid_card` MUST mapear a `card`; `ticket` MUST mapear a `oxxo`; `bank_transfer` MUST
  mapear a `transfer`.
- **FR-003**: Mientras un cobro sigue `pending`, `payment_method` MUST ser `null`.
- **FR-004**: Un `payment_type_id` que no sea ninguno de los reconocidos por FR-002, o ausente, MUST
  publicarse como `payment_method: null`; esta feature MUST NOT adivinar ni forzar una de las tres
  categorías conocidas.
- **FR-005**: Un cobro cerrado (`closed_reason` cualquiera) para el que la API de pagos sí reportó un
  `payment_type_id` reconocido MUST publicar su `payment_method` igual que uno aplicado.
- **FR-006**: Los cobros resueltos antes de este cambio MUST publicar `payment_method: null` de forma
  permanente; esta feature MUST NOT intentar reconstruirlo.
- **FR-007**: Cada cobro MUST incluir un campo `concept` (texto, nullable): el mismo texto amigable que
  esta API ya construye y envía a la API de pagos como `description` al crear el cobro (`start_payment`,
  spec 010).
- **FR-008**: `concept` MUST guardarse como una foto en el momento de crear el cobro, igual que `plan`
  (spec 013): nunca recalculado al leer.
- **FR-009**: Los cobros creados antes de este cambio MUST publicar `concept: null`; esta feature MUST NOT
  intentar reconstruirlo.
- **FR-010**: Esta feature MUST NOT cambiar el control de acceso, la paginación, el filtro `status` (spec
  013) ni ningún otro campo ya publicado por esta operación; es estrictamente aditiva.
- **FR-011**: El esquema OpenAPI MUST declarar `payment_method` como nullable con sus tres valores válidos,
  y `concept` como texto nullable.

### Key Entities

- **Cobro (`SubscriptionCharge`)**: gana dos columnas nullable vía una migración aditiva: `concept` (texto,
  foto al crear el cobro) y `payment_method` (texto corto, escrito solo al resolver el cobro); sin cambios
  en sus demás columnas ni en sus restricciones existentes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cobros resueltos cuya API de pagos reportó un `payment_type_id` reconocido
  publica el `payment_method` correspondiente; el resto (pendientes, no reconocidos o anteriores a esta
  migración) publica `null` (FR-001 a FR-006).
- **SC-002**: El 100 % de los cobros creados después de este cambio publica el mismo `concept` que se envió
  a la API de pagos al crearlo; el 100 % de los anteriores publica `null` (FR-007 a FR-009).
- **SC-003**: El Frontend (rediseño de 030-payment-history/032-payment-page-redesign) puede mostrar la
  forma de pago y el concepto de cada cobro de su historial contra el servicio real, sin una llamada
  adicional a la API de pagos.

## Assumptions

- **Solo este servicio**: cambio únicamente de `maily-system-api`; el consumo real de estos dos campos del
  lado de `mailySoft-frontend` es una spec separada de ese repositorio, que se construye contra este mismo
  contrato.
- **Sin backfill**: ver «Clarifications»; los cobros anteriores a esta migración se quedan con
  `payment_method: null` y `concept: null` de forma permanente, no transitoria.
- **Traducción de responsabilidad de este servicio, no de Pagos**: ver «Clarifications»; Pagos (spec
  005-payment-method, ya fusionada) expone `payment_method_id`/`payment_type_id` en crudo, sin traducir;
  el mapeo a `card`/`oxxo`/`transfer` es una decisión de negocio de las suscripciones, no de un
  microservicio genérico de pagos.

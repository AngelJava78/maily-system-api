# Feature Specification: Plan de cada cobro y filtro por estado en el historial

**Feature Branch**: `013-charges-plan-and-status-filter`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "El Frontend (mailySoft-frontend) está rediseñando la pantalla de pago y su
historial de cobros (`GET /api/v1/subscription-periods/{organization_id}/charges`, spec
012-payment-history-charges de este mismo servicio) para mostrar insignias de color, filtros por estado y
una columna con el plan de cada cobro. Dos cosas le faltan a esta operación para soportarlo: (1) cada cobro
no dice con qué plan se generó (si la organización cambia de plan, el historial no puede mostrar cuál tenía
cada pago pasado); (2) no hay forma de filtrar el listado por estado del lado del servidor (hoy el Frontend
tendría que traer todo y filtrar él mismo, lo que rompe la paginación). Agregar un campo `plan` (nombre del
plan, una foto al momento del cobro, nunca una consulta al catálogo) a cada cobro del historial, y un
parámetro de consulta opcional `status` que filtre `items` del lado del servidor, con `total`/`total_pages`
reflejando ya el filtro."

## Clarifications

### Session 2026-11-25

La persona responsable pidió ejecutar el ciclo completo de Spec Kit sin preguntas y con la opción
recomendada en cada duda.

- Q: ¿Se puede reconstruir el plan de los cobros que ya existen (antes de este cambio)? → A: No con certeza:
  el catálogo de planes no guarda su propio historial de cambios, así que no hay de dónde tomar «qué plan
  tenía la organización en esa fecha exacta» sin arriesgarse a adivinar. Los cobros existentes publican
  `plan: null`; solo los que se creen de ahora en adelante lo traen.
- Q: ¿`status` admite varios valores a la vez (por ejemplo `pending,closed`)? → A: No en esta spec: uno solo
  por consulta, igual que el resto de los filtros de un solo valor que ya tiene este servicio. Pedir varios
  estados a la vez (p. ej. «todo menos cerrado») queda fuera; el Frontend ya resuelve «Todos» simplemente
  omitiendo el parámetro.
- Q: ¿Qué pasa con un `status` que no es ninguno de los tres válidos? → A: 422 `validation_error`, igual que
  cualquier otro parámetro de consulta mal formado de este servicio (mismo tratamiento que un `page_size`
  fuera de rango).

## User Scenarios & Testing *(mandatory)*

El actor principal sigue siendo **el Dueño de una organización**, que ahora ve en su historial de pagos
(Frontend) de qué plan fue cada cobro y puede filtrarlo por estado (Pagados/Pendientes/Cerrados) sin perder
la paginación.

### User Story 1 - Cada cobro dice con qué plan se generó (Priority: P1)

El Dueño ve, junto a cada cobro de su historial, el nombre del plan que tenía en ese momento — incluso si
después cambió de plan y el catálogo ya tiene otro nombre u otro plan activo.

**Why this priority**: es el cambio que el rediseño del Frontend necesita mostrar como columna; sin esto, un
cambio de plan deja huecos o datos incorrectos en el historial.

**Independent Test**: generar un cobro con un plan, cambiar el nombre del plan en el catálogo, generar un
segundo cobro, y comprobar que el historial muestra el nombre de cada uno como era cuando se generó.

**Acceptance Scenarios**:

1. **Given** una organización en «Plan Esencial» que genera un cobro, **When** luego el plan se renombra a
   «Plan Esencial Plus» en el catálogo, **Then** el historial sigue mostrando ese cobro con `plan: "Plan
   Esencial"` (FR-001, FR-002).
2. **Given** una organización que cambia de plan entre dos cobros, **When** se pide su historial, **Then**
   cada cobro trae el nombre del plan que tenía al momento de generarse, no el plan vigente ahora.
3. **Given** un cobro creado antes de este cambio, **When** se pide el historial, **Then** ese cobro publica
   `plan: null` (FR-003); no se intenta adivinar ni reconstruir.

---

### User Story 2 - El historial se filtra por estado del lado del servidor (Priority: P1)

El Dueño elige «Pagados», «Pendientes» o «Cerrados» en el Frontend y recibe solo esos cobros, con la
paginación ya calculada sobre el subconjunto filtrado.

**Why this priority**: sin esto, el Frontend tendría que traer todas las páginas y filtrar él mismo, lo que
rompe la paginación del servidor (`total`/`total_pages` dejarían de significar lo que dicen).

**Independent Test**: con cobros de los tres estados, pedir el historial filtrando por cada uno y comprobar
que `items`, `total` y `total_pages` corresponden solo a ese estado.

**Acceptance Scenarios**:

1. **Given** una organización con un cobro aplicado, uno pendiente y uno cerrado, **When** se pide el
   historial con `status=pending`, **Then** responde solo el pendiente, con `total: 1`.
2. **Given** la misma organización, **When** se pide sin `status`, **Then** responde los tres, igual que
   hoy (el filtro es opcional y no cambia el comportamiento por omisión).
3. **Given** un estado sin ningún cobro (por ejemplo `status=closed` sin cobros cerrados), **When** se pide
   el historial, **Then** responde 200 con `items: []`, `total: 0`, `total_pages: 0`.
4. **Given** un valor de `status` que no es `pending`, `applied` ni `closed`, **When** se pide el historial,
   **Then** responde 422 `validation_error`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cada cobro publicado por `GET /api/v1/subscription-periods/{organization_id}/charges` MUST
  incluir un campo `plan` (texto, nullable): el nombre del plan de la organización en el instante en que el
  cobro se generó.
- **FR-002**: `plan` MUST guardarse como una foto en el momento de crear el cobro (en `start_payment` /
  `POST .../payments`, spec 010), nunca como una referencia al catálogo ni recalculado al leer: un cambio
  posterior del nombre del plan, o de qué plan tiene la organización, MUST NOT cambiar el `plan` de un cobro
  ya creado.
- **FR-003**: Los cobros creados antes de este cambio MUST publicar `plan: null`; esta feature MUST NOT
  intentar reconstruirlo ni adivinarlo.
- **FR-004**: La operación de listado MUST aceptar un parámetro de consulta opcional `status`, uno de
  `pending`/`applied`/`closed`. Cuando se da, MUST filtrar `items` a ese estado del lado del servidor, y
  `total`/`total_pages` MUST reflejar el total ya filtrado, no el de toda la organización.
- **FR-005**: Un `status` ausente MUST comportarse exactamente como hoy (sin filtrar).
- **FR-006**: Un `status` que no sea uno de los tres valores válidos MUST responder 422 `validation_error`,
  sin leer ningún cobro.
- **FR-007**: `page`/`page_size` MUST seguir aplicándose sobre el conjunto ya filtrado por `status` cuando
  se da, exactamente como ya hacen hoy sin filtro.
- **FR-008**: Esta feature MUST NOT cambiar el control de acceso, el formato de paginación (cuerpo, no
  encabezado) ni ningún otro campo ya publicado por esta operación (spec 012); es estrictamente aditiva.
- **FR-009**: El esquema OpenAPI MUST declarar `plan` como nullable y `status` como parámetro de consulta
  opcional con sus tres valores válidos.

### Key Entities

- **Cobro (`SubscriptionCharge`)**: gana una columna `plan` (texto, nullable) vía una migración aditiva; sin
  cambios en sus demás columnas ni en sus restricciones existentes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cobros creados después de este cambio publica el nombre del plan vigente en
  ese instante; el 100 % de los anteriores publica `null` (FR-001 a FR-003).
- **SC-002**: El 100 % de las peticiones con un `status` válido devuelve únicamente cobros de ese estado,
  con `total`/`total_pages` consistentes con el subconjunto filtrado (FR-004, FR-007).
- **SC-003**: El 100 % de las peticiones con un `status` no reconocido se rechaza con 422 sin leer ningún
  cobro (FR-006).
- **SC-004**: El Frontend (rediseño de 030-payment-history) puede mostrar la columna «Plan» y los filtros
  «Pagados/Pendientes/Cerrados» de su historial contra el servicio real, sin traer todas las páginas por
  su cuenta.

## Assumptions

- **Solo este servicio**: cambio únicamente de `maily-system-api`; el consumo real de estos dos campos del
  lado de `mailySoft-frontend` es una spec separada de ese repositorio, que se construye contra este mismo
  contrato.
- **Sin backfill**: ver «Clarifications» y FR-003; los cobros anteriores a esta migración se quedan con
  `plan: null` de forma permanente, no transitoria.
- **Un solo valor de `status` por consulta**: ver «Clarifications»; varios valores a la vez queda fuera de
  esta spec.

# Feature Specification: Historial paginado de cobros de la suscripción

**Feature Branch**: `012-payment-history-charges`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Atender en maily-system-api el pedido de mailySoft-frontend
(`mailySoft-frontend/specs/030-payment-history/contracts/pedido-system-api-charges.md`): la pantalla de
pago de la suscripción (`/payment`) necesita mostrar el historial de cobros de la organización —pagados,
pendientes y cerrados— para que el Dueño vea qué se le ha cobrado sin entrar a mailySoft-pagos. Hoy
`subscription_periods.py` no tiene ninguna operación de listado; el modelo de datos ya existe
(`SubscriptionCharge`, tabla `subscription_charges`, migración 0008). Agregar
`GET /api/v1/subscription-periods/{organization_id}/charges`, paginada, con el mismo control de acceso
(Dueño, permiso `subscription_periods:read`) que ya exige el periodo completo, copiando el patrón ya
resuelto de `GET /api/v1/clinic-subscriptions/{id}/charges`
(`src/routers/clinic_subscriptions.py:164-181`) con un solo cambio deliberado: el total de la paginación
va en el **cuerpo** de la respuesta (`total`/`total_pages`), no en el encabezado `X-Total-Count`, porque el
cliente HTTP del Frontend nunca lee encabezados de respuesta; y los nombres de los parámetros de
paginación son `page`/`page_size` (no `page`/`limit`), para que coincidan con el resto de los listados
paginados que ya consume ese mismo Frontend (Pacientes)."

## Clarifications

### Session 2026-11-25

La persona responsable pidió ejecutar el ciclo completo de Spec Kit sin preguntas y con la opción
recomendada en cada duda. El pedido ya resolvía la mayoría de las decisiones (es su propósito); las dos
que quedaban abiertas se cierran así:

- Q: ¿Esta lectura sincroniza los cobros pendientes con Pagos, como hace consultar el periodo completo? →
  A: No. Es una lectura simple de lo que ya hay guardado: la reconciliación ya ocurre cada vez que se
  consulta el periodo completo (que el Frontend siempre pide junto con el historial en `/payment`), así
  que repetirla aquí sería una llamada más a Pagos sin ningún beneficio para quien solo quiere ver su
  historial. Un cobro `pending` puede seguir mostrándose así en el historial aunque ya esté decidido; la
  siguiente consulta del periodo lo resuelve.
- Q: ¿Qué tamaño de página por omisión? → A: 10, igual que `SUBSCRIPTION_CHARGES_PAGE_SIZE` ya fijado del
  lado del Frontend (`mailySoft-frontend/specs/030-payment-history`); máximo 100 por página, la misma cota
  que ya usa el listado de cobros de clínicas.

## User Scenarios & Testing *(mandatory)*

El actor principal es **el Dueño (rol Owner) de una organización cliente de MailySoft**, que abre la
pantalla de pago de su suscripción (el Frontend) y quiere ver qué se le ha cobrado: pagos aplicados,
alguno pendiente y los que se cerraron sin pagarse.

### User Story 1 - El Dueño ve el historial de su organización (Priority: P1)

El Dueño abre la pantalla de pago; la aplicación pide esta operación con el identificador de su
organización y muestra la lista: cada cobro con su importe, su periodo de cobro, el periodo que cubrió (si
se aplicó) y su estado.

**Why this priority**: es todo el valor de la feature — sin esto el Frontend no tiene de dónde leer el
historial que ya construyó (030-payment-history) contra una simulación.

**Independent Test**: con una organización que tiene cobros de los tres estados, pedir la operación como su
Dueño y comprobar que la respuesta trae los tres, con los campos que corresponden a cada estado.

**Acceptance Scenarios**:

1. **Given** una organización con un cobro aplicado, uno pendiente y uno cerrado, **When** su Dueño pide el
   historial, **Then** responde 200 con los tres, del más reciente al más antiguo, cada uno con `status`,
   `amount`, `currency`, `billing_period` y `created_at`; el aplicado trae además
   `period_starts_at`/`period_ends_at`; el cerrado trae `closed_reason`; los demás valen `null` donde no
   aplican.
2. **Given** una organización sin ningún cobro, **When** su Dueño pide el historial, **Then** responde 200
   con `items: []`, `total: 0` y `total_pages: 0`.
3. **Given** un cobro pendiente que Pagos ya resolvió pero que nadie ha vuelto a consultar en el periodo
   completo, **When** su Dueño pide el historial, **Then** sigue apareciendo `pending` (esta lectura no
   sincroniza nada con Pagos).
4. **Given** la respuesta, **When** se inspeccionan sus campos, **Then** nunca trae el identificador del
   pago en Pagos (`payment_id`), el número de intento (`attempt`) ni cuándo se resolvió (`resolved_at`): son
   del manejo interno de la reconciliación.

---

### User Story 2 - El historial de muchos cobros se pide por páginas (Priority: P2)

Una organización con muchos cobros (clínicas con años de antigüedad, varios intentos fallidos) no recibe
todos de golpe: la aplicación pide una página a la vez.

**Why this priority**: sin paginar, una organización antigua podría devolver una lista sin límite; es P2
porque la mayoría de las organizaciones tiene pocos cobros y la historia 1 ya es útil sin ella.

**Independent Test**: con más cobros que el tamaño de una página, pedir dos páginas distintas y comprobar
que no se repiten y que la paginación (`total`, `total_pages`) es consistente.

**Acceptance Scenarios**:

1. **Given** una organización con 3 cobros, **When** se pide la página 1 de tamaño 1, **Then** trae el más
   reciente, `total: 3` y `total_pages: 3`.
2. **Given** la misma organización, **When** se pide la página 2 de tamaño 1, **Then** trae el siguiente,
   distinto del de la página 1.
3. **Given** ningún parámetro de paginación, **When** se pide el historial, **Then** usa página 1 de tamaño
   10 (FR-008).
4. **Given** un tamaño de página de 0, negativo o mayor que 100, **When** se pide el historial, **Then**
   responde 422 `validation_error`.

---

### User Story 3 - Solo el Dueño ve el historial de su organización (Priority: P1)

Quien no es el Dueño de la organización, o no tiene el permiso, no puede ver su historial de cobros; quien
pide la de otra organización, o una que no existe, recibe la misma respuesta (no se distingue cuál).

**Why this priority**: el historial de cobros es información financiera de la organización; el mismo
control de acceso que ya protege consultar el periodo y pagar aplica aquí.

**Independent Test**: pedir el historial sin el permiso, sin ser el Dueño, y de una organización
inexistente; comprobar que ninguna de las tres deja ver nada.

**Acceptance Scenarios**:

1. **Given** una persona sin el permiso `subscription_periods:read`, **When** pide el historial de
   cualquier organización, **Then** responde 403 `permission_denied`.
2. **Given** una persona con el permiso pero que no es el Dueño de la organización (u organización
   inexistente), **When** pide su historial, **Then** responde 404 `organization_not_found`, igual que
   consultar su periodo completo.
3. **Given** Clínicas no responde, **When** se pide el historial, **Then** responde 503
   `organization_check_unavailable` y no se lee ningún cobro.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST publicar `GET /api/v1/subscription-periods/{organization_id}/charges`, que
  devuelve una página del historial de cobros de la organización, del más reciente al más antiguo
  (`created_at` descendente; en empate, `id` descendente).
- **FR-002**: Cada cobro MUST publicar: `id`, `status` (`pending`/`applied`/`closed`), `closed_reason`
  (los cuatro valores existentes del modelo, o `null`), `amount` (texto con dos decimales, igual que el
  resto de los importes de este contrato), `currency` (siempre `MXN`), `billing_period`
  (`monthly`/`annual`), `period_starts_at`/`period_ends_at` (ISO 8601 UTC o `null`) y `created_at` (ISO
  8601 UTC).
- **FR-003**: `closed_reason` MUST estar presente únicamente cuando `status` es `closed`; `null` en
  cualquier otro caso.
- **FR-004**: `period_starts_at` y `period_ends_at` MUST estar presentes únicamente cuando `status` es
  `applied` (el periodo que ese pago cubrió); `null` en cualquier otro caso.
- **FR-005**: La respuesta MUST NOT incluir `payment_id`, `attempt`, `resolved_at` ni ningún otro dato
  interno de la reconciliación de la spec 010.
- **FR-006**: La operación MUST exigir el mismo control de acceso que `GET /{organization_id}` (el
  permiso `subscription_periods:read` y que la persona sea el Dueño de la organización, verificado con
  Clínicas): 401 sin token, 403 sin el permiso, 404 si no es el Dueño o la organización no existe, 503 si
  Clínicas no responde.
- **FR-007**: La operación MUST NOT sincronizar los cobros pendientes con Pagos ni crear el registro del
  periodo si no existe: es una lectura de lo que ya está guardado, nada más (decisión de la sesión
  2026-11-25).
- **FR-008**: La paginación MUST tomar `page` (entero, 1 o mayor, por omisión 1) y `page_size` (entero, de
  1 a 100, por omisión 10) como parámetros de consulta, y MUST publicar `total`, `page`, `page_size` y
  `total_pages` en el **cuerpo** de la respuesta (nunca en un encabezado).
- **FR-009**: Un `page_size` fuera de su rango, o un `page` menor que 1, MUST responder 422
  `validation_error`.
- **FR-010**: Una organización sin ningún cobro MUST responder 200 con `items: []`, `total: 0` y
  `total_pages: 0`.
- **FR-011**: Una página más allá de la última MUST responder 200 con `items: []` y el `total` real (no un
  error).
- **FR-012**: La respuesta MUST declararse `Cache-Control: no-store`, como las otras dos operaciones de
  este router.
- **FR-013**: Esta feature MUST NOT requerir ninguna migración de esquema (la tabla `subscription_charges`
  y su modelo ya existen, migración 0008) ni ningún permiso nuevo (reutiliza
  `subscription_periods:read`).

### Key Entities

- **Cobro (`SubscriptionCharge`)**: ya existe (spec 010); esta feature solo lo publica en una lectura
  nueva, sin agregar columnas.
- **Página del historial**: `{items, total, page, page_size, total_pages}`; no es una entidad de datos,
  es la forma de esta respuesta.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cobros de una organización (en cualquiera de sus tres estados) aparece en su
  historial, con los campos que corresponden a su estado (FR-002 a FR-004).
- **SC-002**: El 100 % de las peticiones sin el permiso, sin ser el Dueño o con Clínicas caída se rechaza
  sin leer ningún cobro (FR-006).
- **SC-003**: 0 campos internos de la reconciliación (`payment_id`, `attempt`, `resolved_at`) llegan a la
  respuesta (FR-005).
- **SC-004**: El Frontend (030-payment-history, hoy contra una simulación con esta misma forma) deja de
  responder «No encontrado» al consultar el historial real, sin ningún cambio de su lado.

## Assumptions

- **Solo este servicio**: es un cambio únicamente de `maily-system-api`; no hay cambio de
  `mailySoft-frontend` en esta spec (ya construido y probado contra esta forma exacta, spec
  030-payment-history de ese repositorio).
- **Sin reconciliación**: ver FR-007; quien quiera el estado más reciente de un cobro pendiente debe
  consultar el periodo completo (lo que el Frontend ya hace en la misma pantalla).
- **Tamaño de página por omisión, 10; máximo, 100**: ver «Clarifications».

# Research: forma de pago y concepto amigable de cada cobro

## R1 — `payment_method` se traduce aquí, no en mailySoft-pagos

**Decision**: `SubscriptionPeriodService` mapea el `payment_type_id` que reporta la API de pagos (spec
`005-payment-method` de `mailySoft-pagos`, ya fusionada) a una de tres categorías propias:
`credit_card`/`debit_card`/`prepaid_card` → `card`; `ticket` → `oxxo`; `bank_transfer` → `transfer`. La
tabla de mapeo (`_PAYMENT_METHOD_BY_TYPE`) vive junto al resto de las reglas de negocio del Service.

**Rationale**: mailySoft-pagos es, por su propio principio de arquitectura, un microservicio genérico de
pagos que expone lo que el proveedor reporta sin opinar sobre su significado de negocio (igual que ya
hace con `resource_type`/`resource_id`, dos campos opacos para él). Decidir que un `ticket` de Mercado
Pago "es" un pago en efectivo de una suscripción es una decisión de este dominio (suscripciones), no de
Pagos; que Pagos la tomara acoplaría su contrato genérico a un negocio concreto.

**Alternatives considered**: pedirle a Pagos que publique ya traducido `card`/`oxxo`/`transfer` —
descartado: Pagos sirve a más de un dominio (también el cobro de clínicas) y cada uno podría necesitar
categorías distintas; mantener la traducción en el consumidor es más flexible y no infla el contrato
genérico de Pagos con vocabulario de negocio ajeno.

## R2 — Un valor no reconocido es `null`, nunca una aproximación

**Decision**: un `payment_type_id` que no esté en la tabla de mapeo (por ejemplo una billetera digital, o
un valor nuevo que Mercado Pago agregue después) publica `payment_method: null`, igual que cuando Pagos no
lo reportó.

**Rationale**: mismo criterio que ya usa este servicio para `plan: null` (spec 013) o
`payment_in_progress: null`: mejor un `null` explícito y honesto que forzar un valor a una de las tres
categorías conocidas solo por no dejar el campo vacío. Forzarlo arriesgaría mostrarle a una persona "se
pagó con tarjeta" cuando en realidad fue con un método que este servicio ni conoce todavía.

**Alternatives considered**: una cuarta categoría `"otro"` — descartada: el Frontend no pidió un cuarto
estado visual y agregarlo sin que haga falta es complejidad que nadie usa; `null` ya tiene un tratamiento
definido en la pantalla de pago (texto vacío o guión, igual que otros campos nullable de este mismo DTO).

## R3 — `payment_method` se escribe al resolver, `concept` al crear: dos momentos, dos capas de la
escritura

**Decision**: `concept` sigue exactamente el patrón de `plan` (spec 013): se calcula una sola vez en
`start_payment` (ya existe como la variable local `description`) y se pasa a `add_charge`. `payment_method`
en cambio solo se conoce cuando Pagos resuelve el pago (aprobado, rechazado, cancelado, etc.), así que se
calcula en `_apply`/`_close` —los dos puntos donde el Service ya recibe el `PaymentRecord` actualizado— y
se pasa a `apply_charge`/`close_charge` respectivamente, nunca a `add_charge`.

**Rationale**: forzar los dos campos por el mismo camino de escritura sería incorrecto: `concept` sí se
conoce desde el primer instante (es un texto que este mismo servicio construye), pero inventar un
`payment_method` antes de que Pagos conteste sería adivinar. Seguir el momento real en que cada dato existe
evita necesitar una actualización posterior de una fila que ya se escribió.

**Alternatives considered**: consultar a Pagos un dato adicional solo para rellenar `payment_method` de un
cobro ya cerrado sin él — descartado: no hay forma de saber qué cobros cerrados antes de esta spec lo
tendrían, y añadiría una llamada de red que esta spec no necesita para los cobros nuevos.

## R4 — Sin migración de datos, sin permiso nuevo, sin cambio de contrato existente

**Decision**: la migración (0011) solo agrega dos columnas nullable y un `CHECK` sobre la nueva
`payment_method`; no se toca ninguna restricción, índice ni disparador existente de
`subscription_charges`. El permiso sigue siendo `subscription_periods:read`. Los campos y el formato de
paginación que ya publica esta operación (spec 012, 013) no cambian: los dos agregados son estrictamente
aditivos.

**Rationale**: esto es una ampliación de un contrato ya publicado, no una versión incompatible: no hace
falta otro prefijo de ruta ni avisar a nadie más que ya lo consuma (el único consumidor real hoy es la
simulación del Frontend, que se actualiza en su propia spec contra este mismo contrato).

**Alternatives considered**: ninguna — ver «Clarifications» de spec.md.

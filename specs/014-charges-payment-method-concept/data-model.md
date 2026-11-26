# Data Model: forma de pago y concepto amigable de cada cobro

## Cambio de esquema (migración 0011, aditiva)

`subscription_charges` (spec 010, migraciones 0008/0009, ampliada por 0010) gana dos columnas:

| Columna | Tipo | Nullable | Descripción |
|---|---|---|---|
| `concept` | `VARCHAR(500)` | sí | El mismo texto amigable que esta API ya construye y envía a la API de pagos como `description` al crear el cobro (foto, nunca recalculado). `NULL` en los cobros creados antes de esta migración. |
| `payment_method` | `VARCHAR(10)` | sí | `card`, `oxxo` o `transfer` — la categoría de este servicio, nunca el vocabulario de Mercado Pago. Se escribe solo al resolver el cobro (aplicado o cerrado); `NULL` mientras sigue `pending`, si la API de pagos no reportó un método reconocido, o en los cobros resueltos antes de esta migración. |

Un `CheckConstraint` nuevo (`payment_method_check`): `payment_method IS NULL OR payment_method IN
('card', 'oxxo', 'transfer')`. Sin cambios en ninguna restricción, índice ni disparador existente de la
tabla. El modelo `src/models/subscription_charge.py` (`SubscriptionCharge`) agrega los dos campos y un
`StrEnum PaymentMethod` para los tres valores válidos.

## Puerto de integración (`src/integrations/payments_api.py`)

`PaymentRecord` (lo que esta API lee de `mailySoft-pagos`) gana dos campos opcionales, ambos `str | None`,
`None` por omisión: `payment_method_id` y `payment_type_id` — el vocabulario crudo de Mercado Pago,
reenviado verbatim por Pagos (spec 005-payment-method). `_parse` los lee de la respuesta de Pagos sin
validarlos contra ningún catálogo propio (son opacos para esta capa, igual que el resto de los campos que
solo transportan).

## DTO (`src/dtos/subscription_period.py`)

`SubscriptionChargeRead` gana dos campos, ambos requeridos en el JSON con valor posiblemente `null` —
mismo patrón que `plan`/`closed_reason`:

- `concept: str | None`
- `payment_method: ChargePaymentMethodName | None` (`ChargePaymentMethodName = Literal["card", "oxxo",
  "transfer"]`, un tipo nuevo junto a `ChargeStatusName`/`ClosedReasonName`).

`SubscriptionChargesPageRead` no cambia.

## Flujo de escritura de `concept` (al crear el cobro)

`SubscriptionPeriodService.start_payment` ya construye la variable local `description` (el texto que
envía a la API de pagos) antes de llamar a `SubscriptionPeriodRepository.add_charge`; esta feature solo
agrega `concept=description` a esa llamada — mismo momento y mismo mecanismo que `plan=context.plan.name`
(spec 013).

## Flujo de escritura de `payment_method` (al resolver el cobro)

`SubscriptionPeriodService._settle` ya recibe el `PaymentRecord` actualizado y decide si el cobro se
aplica (`_apply`) o se cierra (`_close`) en cada una de sus cuatro ramas (aprobado y coincide, rechazado,
cancelado, reembolsado/parcialmente reembolsado; la rama de "aprobado pero no coincide" también cierra,
como `inconsistent`). Un método nuevo, `_payment_method_of(payment)`, traduce `payment.payment_type_id`
con la tabla `_PAYMENT_METHOD_BY_TYPE`; su resultado (`str | None`) se pasa como `payment_method=...` a
`SubscriptionPeriodRepository.apply_charge` o `.close_charge`, según corresponda. Ningún otro punto de
escritura de `subscription_charges` toca estas dos columnas.

## Flujo de lectura

Sin cambios respecto a spec 013: `SubscriptionPeriodService.list_charges`/
`SubscriptionPeriodRepository.list_charges` no necesitan tocarse — los dos campos nuevos viajan con la
misma fila que ya se lee, y el Router (`_to_charge_read`) los copia al DTO de salida junto al resto.

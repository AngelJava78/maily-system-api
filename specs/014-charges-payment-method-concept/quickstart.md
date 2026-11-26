# Quickstart: validar la forma de pago y el concepto de cada cobro

Prerrequisito: el servicio corriendo con la base migrada hasta `0011` (`alembic upgrade head`), y
`mailySoft-pagos` desplegado con su spec `005-payment-method` (ya fusionada) para que `GET
/api/v1/payments/{id}` reporte `payment_method_id`/`payment_type_id`.

## 1. Un cobro nuevo trae su concepto desde el momento de crearse

```http
POST /api/v1/subscription-periods/{organization_id}/payments
Authorization: Bearer <token del Dueño>
```

```http
GET /api/v1/subscription-periods/{organization_id}/charges
Authorization: Bearer <token del Dueño>
```

El cobro recién creado debe traer `"concept"` con el mismo texto que esta API envió a Pagos (p. ej.
`"Suscripción Titán — mensual"`), y `"payment_method": null` (todavía pendiente).

## 2. Un cobro aprobado con tarjeta trae `payment_method: "card"`

Aprobar el pago en la simulación de Pagos con `payment_type_id: "credit_card"` (o, contra el servicio
real, pagar con tarjeta en el checkout de Mercado Pago) y volver a leer el periodo
(`GET /api/v1/subscription-periods/{organization_id}`, que reconcilia) antes de pedir el historial de
nuevo: el cobro debe mostrar `"status": "applied"` y `"payment_method": "card"`.

## 3. Un cobro aprobado con OXXO o transferencia trae `"oxxo"`/`"transfer"`

Mismo paso, con `payment_type_id: "ticket"` o `"bank_transfer"` respectivamente.

## 4. Un cobro de antes de esta migración sigue en `null`

Si la organización ya tenía cobros antes de aplicar la migración `0011`, esos siguen publicando
`"concept": null` y `"payment_method": null` — no se reconstruyen.

## Pruebas automatizadas equivalentes

- `tests/unit/test_subscription_period_dtos.py` — los campos `concept`/`payment_method` del DTO,
  nullable, y el rechazo de un valor que no sea uno de los tres.
- `tests/unit/test_subscription_period_service.py` —
  `test_the_history_snapshots_the_concept_at_the_time_of_the_charge`,
  `test_an_applied_charge_records_the_payment_method_pagos_reported`,
  `test_a_closed_charge_also_records_the_payment_method_when_pagos_reported_one`.
- `tests/integration/test_subscription_period_repository.py` —
  `test_a_charge_is_registered_with_its_concept_snapshot`, `test_applying_a_charge_records_the_payment_method`,
  `test_closing_a_charge_records_the_payment_method_when_given` (contra PostgreSQL real).
- `tests/contract/test_subscription_periods_api.py` — `test_an_applied_charge_shows_the_period_it_covered`
  (ahora también comprueba `payment_method`), `test_a_closed_charge_also_shows_the_payment_method_pagos_reported`,
  `test_a_payment_method_this_service_does_not_recognise_is_null_not_guessed` (HTTP de punta a punta).

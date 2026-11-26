# Contrato: `payment_method` y `concept` por cobro en el historial

Ampliación de `GET /api/v1/subscription-periods/{organization_id}/charges` (spec 012, 013).
Estrictamente aditiva: ningún campo ni comportamiento ya publicado cambia.

```http
GET /api/v1/subscription-periods/{organization_id}/charges?page=1&page_size=10
Authorization: Bearer <token del Dueño>
```

```json
{
  "items": [
    {
      "id": "6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70",
      "status": "applied",
      "closed_reason": null,
      "amount": "499.00",
      "currency": "MXN",
      "billing_period": "monthly",
      "plan": "Plan Individual",
      "concept": "Suscripción Plan Individual — mensual",
      "payment_method": "card",
      "period_starts_at": "2026-10-19T12:00:00Z",
      "period_ends_at": "2026-11-19T12:00:00Z",
      "created_at": "2026-10-19T11:58:03Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10,
  "total_pages": 1
}
```

- `concept`: texto o `null`. `null` en los cobros creados antes de esta feature; en los creados después,
  el mismo texto que esta API ya le manda a la API de pagos como `description` al crear el cobro.
- `payment_method`: `"card"`, `"oxxo"`, `"transfer"` o `null`. `null` mientras el cobro sigue `pending`, si
  la API de pagos no reportó un método que este servicio reconozca, o en los cobros resueltos antes de
  esta feature. Se calcula a partir del `payment_type_id` crudo que reporta `GET /api/v1/payments/{id}`
  de `mailySoft-pagos` (spec `005-payment-method`): `credit_card`/`debit_card`/`prepaid_card` → `card`;
  `ticket` → `oxxo`; `bank_transfer` → `transfer`; cualquier otro valor → `null`.
- Todo lo demás (permiso, control de Dueño, `page`/`page_size`, `status`, errores
  401/403/404/422/500/503, `Cache-Control: no-store`) es idéntico a spec 012/013; no se repite aquí.

## Dependencia

Esta feature asume que `mailySoft-pagos` ya reporta `payment_method_id`/`payment_type_id` en
`GET /api/v1/payments/{id}` (spec `005-payment-method`, fusionada el 2026-11-25, PR
Quint4n4/mailySoft-pagos#6). Sin esa dependencia, `payment_method` sería siempre `null` (no un error: la
API de pagos simplemente no tendría el dato que traducir).

## Consumidor

`mailySoft-frontend`, en el rediseño de su página de pago (una spec propia de ese repositorio, construida
contra esta misma forma): la forma de pago y el concepto de cada fila del historial.

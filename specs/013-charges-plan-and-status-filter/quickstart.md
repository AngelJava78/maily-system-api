# Quickstart: validar el plan de cada cobro y el filtro por estado

Prerrequisito: el servicio corriendo con la base migrada hasta `0010` (`alembic upgrade head`), y un
organización con al menos un cobro generado después de este cambio (`POST .../payments` con un pago
aprobado, o simplemente un cobro `pending` recién creado).

## 1. Un cobro nuevo trae el nombre del plan

```http
POST /api/v1/subscription-periods/{organization_id}/payments
Authorization: Bearer <token del Dueño>
```

```http
GET /api/v1/subscription-periods/{organization_id}/charges
Authorization: Bearer <token del Dueño>
```

El cobro recién creado debe traer `"plan"` con el nombre del plan vigente de la organización (p. ej.
`"Plan Individual"`), no `null`.

## 2. Un cobro de antes de esta migración sigue en `null`

Si la organización ya tenía cobros antes de aplicar la migración `0010`, esos siguen publicando
`"plan": null` — no se reconstruyen.

## 3. Filtrar por estado

```http
GET /api/v1/subscription-periods/{organization_id}/charges?status=pending
Authorization: Bearer <token del Dueño>
```

`items` debe traer únicamente cobros `pending`, y `total`/`total_pages` deben corresponder solo a ese
subconjunto (compararlo con el mismo pedido sin `status`, que debe traer igual o más).

## 4. Un `status` inválido se rechaza

```http
GET /api/v1/subscription-periods/{organization_id}/charges?status=approved
Authorization: Bearer <token del Dueño>
```

Debe responder 422 con `"code": "validation_error"`.

## Pruebas automatizadas equivalentes

- `tests/unit/test_subscription_period_dtos.py` — el campo `plan` del DTO, nullable.
- `tests/unit/test_subscription_period_service.py` — `test_the_history_snapshots_the_plan_name_at_the_time_of_the_charge`,
  `test_the_history_can_be_filtered_by_status`.
- `tests/integration/test_subscription_period_repository.py` — `test_a_charge_registered_without_a_plan_keeps_it_null`,
  `test_the_history_can_be_filtered_by_status` (contra PostgreSQL real).
- `tests/contract/test_subscription_periods_api.py` — `test_the_history_can_be_filtered_by_status`,
  `test_the_history_rejects_an_unknown_status` (HTTP de punta a punta).

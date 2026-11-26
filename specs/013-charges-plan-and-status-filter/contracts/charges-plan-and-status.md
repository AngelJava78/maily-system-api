# Contrato: `plan` por cobro y filtro `status` en el historial

Ampliación de `GET /api/v1/subscription-periods/{organization_id}/charges` (spec 012). Estrictamente
aditiva: ningún campo ni comportamiento ya publicado cambia.

```http
GET /api/v1/subscription-periods/{organization_id}/charges?page=1&page_size=10&status=applied
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

- `plan`: texto o `null`. `null` en los cobros creados antes de esta feature; en los creados después, el
  nombre del plan de la organización al instante del cobro (nunca el plan vigente ahora, si cambió).
- `status` (query, opcional): `pending`/`applied`/`closed`. Ausente ⇒ sin filtrar. Otro valor ⇒ 422
  `validation_error`.
- Con `status` presente, `total`/`total_pages` reflejan solo los cobros de ese estado.
- Todo lo demás (permiso, control de Dueño, `page`/`page_size`, errores 401/403/404/422/500/503,
  `Cache-Control: no-store`) es idéntico a spec 012; no se repite aquí.

## Consumidor

`mailySoft-frontend`, en el rediseño de su historial de pagos (una spec propia de ese repositorio,
construida contra esta misma forma): la columna «Plan» de cada fila y los filtros «Pagados / Pendientes /
Cerrados» de su historial.

# Contrato publicado: historial de cobros de la suscripción

Responde el pedido de `mailySoft-frontend`
(`specs/030-payment-history/contracts/pedido-system-api-charges.md` de ese repositorio): esta sección es
la versión **publicada** de ese pedido, tal como quedó implementada.

```http
GET /api/v1/subscription-periods/{organization_id}/charges?page=1&page_size=10
Authorization: Bearer <token de la persona>
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

- **Permiso**: `subscription_periods:read` (ver [permission-matrix.md](permission-matrix.md)).
- **Control de acceso**: idéntico a `GET /{organization_id}` — 401 sin token, 403 sin el permiso, 404 si
  no es el Dueño o la organización no existe, 503 si Clínicas no responde.
- **Paginación**: `page` (≥ 1, por omisión 1) y `page_size` (de 1 a 100, por omisión 10) en la consulta;
  `total`/`page`/`page_size`/`total_pages` en el **cuerpo** de la respuesta, nunca en un encabezado (R1 de
  [research.md](../research.md)). Fuera de ese rango, 422 `validation_error`.
- **Orden**: `created_at` descendente (el más reciente primero), desempate por `id` descendente.
- **No sincroniza con Pagos**: a diferencia de consultar el periodo completo, esta lectura no reconcilia
  los cobros pendientes (R2); un cobro `pending` puede seguir mostrándose así hasta que se consulte el
  periodo.
- **`Cache-Control: no-store`**, igual que las otras dos operaciones de este router.
- Comparado con el pedido original: coincide exactamente en forma, nombres de campo y reglas de
  presencia de `closed_reason`/`period_starts_at`/`period_ends_at` (FR-003, FR-004). La única diferencia
  es el tamaño de página por omisión (el pedido no lo fijaba; esta implementación usa 10, el mismo valor
  que ya tenía fijado el Frontend — ver R6 de [research.md](../research.md)).

## Qué desbloquea

El Frontend (`mailySoft-frontend`, feature 030-payment-history) ya está construido y probado contra esta
forma exacta, con la operación marcada como pendiente
(`PENDING_OPERATIONS` en `src/shared/subscription/operations.ts` de ese repositorio). Con esta operación
publicada, ese repositorio puede moverla a `PUBLISHED_OPERATIONS` y dejar de ver «No encontrado» al abrir
`/payment` contra el servicio real — cambio que queda del lado de ese otro repositorio, fuera de esta
spec.

# Contrato consumido: API de pagos (FR-020, FR-026 a FR-031, FR-047, FR-050; Principio IX)

> **Estado**: las dos operaciones **existen hoy** (`mailySoft-pagos`, spec 001, «completa y verificada»); lo que
> falta para usarlas desde esta API son **permisos y un dato de identidad en Usuarios** y, como mejora, una
> dirección de regreso y una fecha de aprobación ([pedidos-pagos.md](pedidos-pagos.md),
> [pedidos-usuarios.md](pedidos-usuarios.md)). Las pruebas usan la simulación (`tests/stubs/payments_api`).

Los pagos son datos **ajenos**: su estatus y su dirección de checkout se piden a Pagos en cada uso y **no se
guardan**. De cada pago esta API registra solo su identificador y lo que ella misma pidió (importe, moneda,
periodo): es la base para decidir si un pago «cuenta» (FR-027).

## Operaciones consumidas

### Crear el pago

```http
POST {PAYMENTS_API_BASE_URL}/api/v1/payments
Authorization: Bearer <el token de la persona, tal como llegó>
Idempotency-Key: sub-0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b-3a9c1d7e5b2f4a6c8e0d1b3f
Content-Type: application/json
Accept: application/json

{
  "provider": "mercado_pago",
  "amount": 49900,
  "currency": "MXN",
  "resource_type": "system-api:subscription",
  "resource_id": "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b",
  "description": "Suscripción Plan Individual — mensual",
  "metadata": { "billing_period": "monthly", "settles_due_at": "2026-12-04T15:30:00Z" }
}
```

- `amount`: entero en la unidad mínima (centavos): 499.00 → 49900 (FR-017). `currency`: `MXN`.
- `Idempotency-Key`: 1 a 100 caracteres; la forma determinista de esta API está en
  [research R6](../research.md#r6-idempotencia-determinista-con-pagos-fr-022-a-fr-025) (65 caracteres).
  Repetirla con el mismo cuerpo devuelve el pago ya creado; con otro cuerpo, `409 idempotency_key_conflict`.
- `resource_type` cumple `^[a-z0-9-]+:[a-z0-9_-]+$`; `resource_id`, hasta 200 caracteres: el UUID de la
  organización. `metadata`: JSON plano de hasta 4 KiB (solo referencias; nada personal).
- `201` (o `200` ante una clave repetida) con un `PaymentRead` (abajo).

### Consultar un pago

```http
GET {PAYMENTS_API_BASE_URL}/api/v1/payments/{payment_id}
Authorization: Bearer <el token de la persona>
Accept: application/json
```

`200` con un `PaymentRead`; `404 payment_not_found` si el pago no existe **en la organización de quien
llama** (Pagos aísla por el `tenant_id` del llamador).

### `PaymentRead` (los campos que esta API usa; el resto se ignora)

```json
{
  "id": "6b0a0b1e-2d3c-4e5f-8a9b-0c1d2e3f4a5b",
  "status": "pending",
  "amount": 49900,
  "currency": "MXN",
  "resource_type": "system-api:subscription",
  "resource_id": "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b",
  "checkout_url": "https://www.mercadopago.com.mx/checkout/v1/redirect?pref_id=123456789-abc",
  "updated_at": "2026-12-01T10:00:00Z"
}
```

| Campo | Validación estricta de esta API |
|---|---|
| `id` | UUID; en la consulta, igual al pedido |
| `status` | Uno de `pending`, `approved`, `rejected`, `cancelled`, `partially_refunded`, `refunded`; otro valor → «no disponible» |
| `amount` | Entero (no booleano) |
| `currency` | Texto de tres letras |
| `resource_type`, `resource_id` | Texto |
| `checkout_url` | Texto o `null` («presente mientras el pago no haya sido notificado») |
| `updated_at` | ISO 8601 **con zona**; es la fecha de la última actualización (se usa como fecha de aprobación, FR-031) |

## Uso, conciliación y degradación (FR-026 a FR-031, FR-036)

| Estatus que reporta Pagos | Efecto sobre el cobro de esta API |
|---|---|
| `pending` | Sigue pendiente (`payment_in_progress: true`) |
| `approved` y coinciden importe, moneda y referencia | **Se aplica**: la fecha del siguiente pago se mueve, una vez |
| `approved` y no coinciden | Se cierra `inconsistent`, sin mover fechas; queda un `WARNING` sin datos personales |
| `rejected`, `cancelled` | Se cierra sin mover fechas |
| `partially_refunded`, `refunded` (sin aplicar) | Se cierra `refunded` sin aplicar (D3) |
| Sin respuesta, tiempo agotado, `401`/`403`/`404`/`409`/`5xx`, redirección, cuerpo o estatus inesperado | **No verificable**: el cobro sigue sin resolver; la consulta responde 200 con `payment_in_progress: null` |

Al **crear** el pago, cualquier falla o respuesta inesperada → `503 payments_unavailable` y no se registra
ningún cobro. Un pago creado sin `checkout_url` o ya no pendiente se registra (para que la siguiente
conciliación lo resuelva) y también responde `503 payments_unavailable`.

## Reglas de la integración

- **Autenticación**: se reenvía el token de la persona; Pagos lo reenvía a Usuarios y decide con
  `payments:write` (crear) y `payments:read` (consultar). El Dueño necesita ambos permisos y que Usuarios
  publique su `tenant_id` ([pedidos-usuarios.md](pedidos-usuarios.md)).
- **Tiempo máximo total** de `PAYMENTS_API_TIMEOUT_SECONDS` (5 s por defecto); **sin reintentos**
  automáticos; **sin redirecciones**; **sin caché**. La consulta de varios cobros pendientes es en paralelo.
- **Pagos no avisa** cuando un pago cambia de estatus (pedido (d) de la descripción): esta API consulta.
- **Un pago creado directamente en Pagos** por otra vía no es un cobro de esta API y nunca mueve fechas
  (FR-027).
- **Errores**: el cuerpo, la dirección y el token de Pagos nunca llegan al cliente ni a los registros.
- **Capas**: `PaymentsApiClient` (en `src/integrations/payments_api.py`) solo habla HTTP, valida la forma y
  devuelve un `PaymentRecord` o lanza `PaymentsApiUnavailable`; el Service decide qué error devolver y cómo
  degradar.

## Puntos a confirmar con quien mantenga el API de pagos

1. Que acepte las direcciones de regreso tras el checkout (`redirect_urls`/`back_urls`) para que la persona
   vuelva a la aplicación; hoy Mercado Pago no redirige al terminar (`mercado-pago-integration.md`).
2. Que publique la **fecha de aprobación** del pago (hoy solo `updated_at`).
3. Que la misma `Idempotency-Key` con el mismo cuerpo devuelva siempre el mismo pago, también si ya cambió de
   estatus (esta API depende de ello si se pierde una respuesta).

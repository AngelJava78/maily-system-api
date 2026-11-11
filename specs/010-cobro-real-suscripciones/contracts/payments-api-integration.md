# Contrato consumido: mailySoft-pagos (FR-007, FR-008, FR-013 a FR-019; research R2 a R5, R8)

Fuente de verdad: `mailySoft-pagos/specs/001-payments-foundation/contracts/openapi-pagos.yaml`. Este
servicio **no modifica** Pagos (FR-022): usa su contrato tal cual.

## Crear un cobro

```http
POST {PAGOS_API_BASE_URL}/api/v1/payments
Authorization: Bearer <el token de quien disparó el cobro, tal como llegó>
Idempotency-Key: clinic-subscription:<clinic_subscription_id>:<period>
Content-Type: application/json

{
  "provider": "mercado_pago",
  "amount": 129900,
  "currency": "MXN",
  "resource_type": "system-api:clinic-subscription",
  "resource_id": "<clinic_subscription_id>",
  "description": "Suscripción de clínica <clinic_subscription_id> — periodo <period>"
}
```

- `amount`: centavos del precio **vigente** del plan que reportó Clínicas, según el ciclo también
  reportado por Clínicas (research R2; `contracts/clinics-api-integration.md`).
- `resource_id`: el `clinic_subscription_id` **de Clínicas**, tal cual (research R4): sigue siendo
  una referencia opaca para Pagos, igual que antes del rediseño; solo cambió quién es su dueño.
- `Idempotency-Key`: determinista por `(clinic_subscription_id, period)` (research R3). **No** se
  envía `tenant_id` en el cuerpo (Principio X de Pagos): lo resuelve Pagos con el token reenviado
  (FR-008).

### Traducción de la respuesta

| Respuesta de Pagos | Resultado aquí |
|---|---|
| `201`, cuerpo `PaymentRead` | Se guarda como la fila nueva (o actualizada, si ya existía por el mismo `(clinic_subscription_id, period)`) del historial: `payment_id = id`, `payment_status = status` (`pending` normalmente), `checkout_url`, `amount`, `currency`, `idempotency_key`. |
| `401` con `code` = `unauthenticated` / `token_expired` / `invalid_token` | Igual código, `401`, sin guardar ningún cobro |
| `403` (`permission_denied`, `organization_required`, `password_change_required` — todos **en Pagos**) | `403 payment_not_authorized` (código propio: no se reexpone el `code` de Pagos — FR-019) |
| `409` (`idempotency_key_conflict`) | `409 clinic_subscription_charge_conflict` (el precio u otro dato cambió entre dos intentos del mismo periodo) |
| `422` (`provider_not_supported`, `validation_error`) | `503 payments_unavailable` (no debería ocurrir con los datos que este servicio construye) |
| `503`, cualquier otro `5xx`, `429`, tiempo agotado, error de red/TLS, cuerpo inesperado, `3xx` (no se sigue) | `503 payments_unavailable` |

**Falla cerrada** (FR-012): cualquier caso no listado es `503 payments_unavailable`; no se guarda
ningún cobro.

## Consultar un cobro (sincronización, historia 2)

```http
GET {PAGOS_API_BASE_URL}/api/v1/payments/{payment_id}
Authorization: Bearer <credencial de aplicación de este servicio>
Accept: application/json
```

- Solo se llama cuando el `payment_status` guardado localmente es `pending` (research R8); un cobro
  ya resuelto nunca dispara esta llamada.
- **Credenciales**: no se guarda el token de quien disparó el cobro (Principio VIII: este servicio
  nunca guarda tokens), así que esta consulta usa una credencial de **aplicación** propia
  (`PAGOS_API_SERVICE_TOKEN`, variable de entorno opcional) con `payments:read` en Usuarios. Sin esa
  variable, la sincronización se omite (se devuelve el último estatus local) y se registra una
  advertencia al arrancar.

### Traducción de la respuesta

| Respuesta de Pagos | Resultado aquí |
|---|---|
| `200`, cuerpo `PaymentRead` con `status` distinto del guardado | Se actualiza `payment_status` (y `checkout_url` a `null` si ya no es `pending`) de la fila |
| `200`, cuerpo `PaymentRead` con el mismo `status` guardado (`pending`) | Sin cambios |
| `404` (`payment_not_found`) | «No disponible» (FR-014): no se borra el cobro local; se registra un error (no debería ocurrir con un `payment_id` que este servicio creó) |
| `401`/`403`/`503`/cualquier otro `5xx`/`429`/tiempo agotado/cuerpo inesperado/`3xx` | «No disponible» (FR-014): se devuelve el último estatus local conocido |

## Variables de entorno (FR-020)

| Variable | Uso |
|---|---|
| `PAGOS_API_BASE_URL` | Dirección de `mailySoft-pagos` |
| `PAGOS_API_TIMEOUT_SECONDS` | Tiempo máximo total de cada llamada (por defecto 5 s) |
| `PAGOS_API_SERVICE_TOKEN` | Credencial de aplicación para la sincronización (opcional) |

## Reglas de la integración

- Asíncrona (`httpx.AsyncClient`), sin reintentos automáticos, sin seguir redirecciones.
- Las fallas de Pagos nunca filtran su cuerpo, sus cabeceras ni su dirección (FR-019).
- `src/integrations/payments_api.py` (`PaymentsApiClient`) solo habla HTTP; `ClinicSubscriptionService`
  lo invoca y traduce sus excepciones a los errores propios de este servicio.

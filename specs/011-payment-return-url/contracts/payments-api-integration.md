# Contrato consumido: mailySoft-pagos — dirección de regreso al crear un pago

Cambio sobre el contrato que consume la spec 010-subscription-periods
([su documento](../../010-subscription-periods/contracts/payments-api-integration.md)), que sigue vigente
en todo lo demás. Verificado leyendo mailySoft-pagos en solo lectura: feature
`002-checkout-return-urls`, integrada en su `main` el 2026-11-25 (su contrato:
`specs/002-checkout-return-urls/contracts/api-redirect-urls.md`; el pedido que esta feature atiende:
`specs/002-checkout-return-urls/contracts/pedido-system-api.md`).

## Operación

`POST /api/v1/payments` — misma operación, mismos encabezados (`Authorization` con el token de la persona,
`Idempotency-Key`, `Accept`), mismas respuestas válidas (200 o 201 con el pago).

## Campo nuevo del cuerpo (opcional)

```json
{
  "provider": "mercado_pago",
  "amount": 49900,
  "currency": "MXN",
  "resource_type": "system-api:subscription",
  "resource_id": "<organization_id>",
  "description": "Suscripción Luna — Mensual",
  "metadata": { "billing_period": "monthly", "settles_due_at": "2026-12-04T15:30:00Z" },
  "redirect_urls": { "success": "https://app.mailysoft.com/payment" }
}
```

| Campo | Lo que acepta Pagos | Lo que envía esta API |
|---|---|---|
| `redirect_urls` | Opcional. Objeto sin campos extra | Solo con `PAYMENTS_RETURN_URL` definida; si no, la clave no aparece |
| `redirect_urls.success` | Obligatorio dentro del objeto; texto de 1 a 2048 caracteres | El valor de la variable tal como se configuró (sin espacios externos) |
| `redirect_urls.pending`, `redirect_urls.failure` | Opcionales; si faltan, Pagos usa `success` | Nunca se envían |

**Reglas que Pagos aplica a cada dirección** (si alguna falla: 422 `validation_error`, sin crear el pago):
esquema `https`; sin credenciales ni fragmento; sin espacios ni caracteres de control; a lo más 2048
caracteres; nunca un equipo local ni de una red privada; y su origen (`https://equipo[:puerto]`) en la
lista de Pagos `CHECKOUT_RETURN_ALLOWED_ORIGINS` (vacía: ninguna dirección es válida). Esta API revisa todas
al arrancar **excepto la lista de orígenes**, que es configuración de Pagos (research R2).

## Errores nuevos o cambiados

| Respuesta de Pagos | Cuándo | Lo que hace esta API |
|---|---|---|
| 422 `validation_error` con `errors[0].field = "body.redirect_urls.success"` | El origen no está permitido en Pagos o la dirección incumple una regla | Como cualquier respuesta inesperada: 503 `payments_unavailable` y ningún cobro registrado. Registra que se envió una dirección de regreso (sin la dirección) para orientar a quien opera (FR-010) |
| 422 `validation_error` que señala `body.redirect_urls` | Un Pagos anterior a su feature 002: su `PaymentCreate` no admite campos desconocidos (`extra="forbid"`) | Igual: 503, ningún cobro y el mismo registro de la fila anterior |
| 409 `idempotency_key_conflict` | La misma clave con otro cuerpo; desde la feature 002, la dirección es parte del cuerpo | Igual que hoy: 503. La clave de esta API incluye la dirección (FR-008), así que no reutiliza una clave con otra dirección |

## Idempotencia

Pagos calcula la huella de una creación con todo el cuerpo, incluida la dirección cuando viene, y conserva
la huella anterior cuando no viene. Esta API no envía la clave `redirect_urls` sin la variable, así que las
huellas y las claves de los cobros de hoy no cambian (SC-002).

## Lo que hace Mercado Pago con la dirección (por Pagos)

- Pagos la envía como `back_urls` (las tres iguales a `success` cuando solo viene esa) con
  `auto_return: "approved"`: Mercado Pago regresa solo a la persona **solo** cuando el pago se aprueba; en
  pendiente o rechazo muestra su pantalla con un botón de volver a la misma dirección.
- Mercado Pago agrega a la dirección parámetros con el resultado (por ejemplo `collection_status`,
  `payment_id`, `status`, `external_reference`). **No son prueba de pago**: esta API no los recibe ni los
  usa; un cobro solo se aplica cuando `GET /api/v1/payments/{id}` lo reporta `approved` (spec 010, FR-026 a
  FR-028; esta spec, FR-012).

## Simulación en las pruebas

`tests/stubs/payments_api/app.py` reproduce este contrato (Principio V):

- Valida `redirect_urls` como Pagos: objeto solo con `success`, `pending` y `failure`; `success`
  obligatorio; cada valor, un texto que empieza con `https://` y tiene de 1 a 2048 caracteres. Si no, 422
  `validation_error`.
- Guarda el objeto con el pago (visible en `GET /__test__/payments`) y lo incluye en la huella de
  idempotencia (ya usa todo el cuerpo).
- Modo de falla nuevo `return_not_allowed` (operación `create`): 422 `validation_error` con
  `errors: [{"field": "body.redirect_urls.success", "message": "El origen de la dirección de regreso no está permitido."}]`,
  como responde Pagos a un origen que no está en su lista.

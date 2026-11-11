# Contrato consumido: mailySoft-pagos (FR-010, FR-011, FR-016 a FR-022; research R2 a R5)

Fuente de verdad: `mailySoft-pagos/specs/001-payments-foundation/contracts/openapi-pagos.yaml`. Este
servicio **no modifica** Pagos (FR-023): usa su contrato tal cual. Solo se documenta aquí lo que este
servicio llama, con qué datos y cómo traduce cada respuesta.

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

- `amount`: centavos del precio **vigente** del plan asignado (research R2); nunca el precio en
  pesos ni un `float`.
- `resource_type`/`resource_id`: referencia opaca (research R4); Pagos no los valida.
- `Idempotency-Key`: determinista por periodo (research R3). **No** se envía `tenant_id` en el
  cuerpo (Principio X de Pagos): lo resuelve Pagos con el token reenviado (FR-011).
- El `provider` es siempre `mercado_pago` en esta especificación (el único que Pagos implementa hoy).

### Traducción de la respuesta

| Respuesta de Pagos | Resultado aquí |
|---|---|
| `201`, cuerpo `PaymentRead` | Se guarda como la fila nueva (o actualizada, si ya existía por el mismo `(clinic_subscription_id, period)`) de `clinic_subscription_charges`: `payment_id = id`, `payment_status = status` (`pending` normalmente), `checkout_url`, `amount`, `currency`, `idempotency_key`. La suscripción de clínica pasa a estatus 2 («con cobro pendiente de resolver»). |
| `401` con `code` = `unauthenticated` / `token_expired` / `invalid_token` | Igual código, `401`, sin crear ningún cobro local (el mismo que ya usa este servicio para sus propios 401) |
| `403` (`permission_denied` — falta `payments:write`, o `organization_required` — quien llama no tiene organización en Usuarios, o `password_change_required`) | `403 payment_not_authorized` (código propio: no se reexpone el `code` de Pagos tal cual, para no acoplar el contrato público de este servicio al de Pagos — FR-020) |
| `409` (`idempotency_key_conflict`) | `409 clinic_subscription_charge_conflict` (research R5; edge case de la spec: el precio cambió entre dos intentos del mismo periodo) |
| `422` (`provider_not_supported`, `validation_error`) | `503 payments_unavailable` (no debería ocurrir con los datos que este servicio construye; si ocurre, es un error de este servicio, no un dato inválido de quien llama, así que no se expone como 422 propio) |
| `503` (`authorization_unavailable`, `payment_provider_unavailable`), cualquier otro `5xx`, `429`, tiempo agotado, error de red/TLS, cuerpo que no es JSON o que no cumple `PaymentRead`, `3xx` (no se sigue) | `503 payments_unavailable` |

**Falla cerrada** (FR-014): cualquier caso no listado es `503 payments_unavailable`; no se crea
ningún cobro local ni cambia la suscripción de clínica.

## Consultar un cobro (sincronización, historia 3)

```http
GET {PAGOS_API_BASE_URL}/api/v1/payments/{payment_id}
Authorization: Bearer <el token de quien disparó el cobro originalmente>
Accept: application/json
```

- Solo se llama cuando el `payment_status` guardado localmente es `pending` (research R8); un cobro
  ya resuelto nunca dispara esta llamada.
- El token reenviado es el que se guardó al **crear** el cobro (no hay sesión activa de quien
  consulta: puede ser otra persona, p. ej. quien administra la plataforma, leyendo el historial).
  Guardar un token de acceso para usarlo después contradice el resto de este servicio (que nunca
  guarda tokens): por eso este servicio **no reenvía ningún token propio** a esta consulta — ver
  «Credenciales de la sincronización» más abajo.

### Credenciales de la sincronización

Pagos exige `payments:read` del token de quien consulta (su propio Principio VIII); este servicio no
guarda el token de quien disparó el cobro (nunca se guardan tokens, Principio VIII de este servicio).
La sincronización usa, por tanto, unas credenciales de **aplicación** propias de este servicio hacia
Pagos (una cuenta de servicio con `payments:read`, fuera del flujo de una persona), configuradas con
`PAGOS_API_SERVICE_TOKEN` (variable de entorno, nunca en el código ni en los registros). Si esa
variable no está configurada, la sincronización se omite (se devuelve el último estatus local
conocido, igual que si Pagos no respondiera: FR-017) y se registra una advertencia al arrancar
(mismo patrón que una variable opcional no configurada en otras integraciones de este servicio).

### Traducción de la respuesta

| Respuesta de Pagos | Resultado aquí |
|---|---|
| `200`, cuerpo `PaymentRead` con `status` distinto del guardado | Se actualiza `payment_status` (y `checkout_url` a `null` si ya no es `pending`) de la fila de `clinic_subscription_charges`; si pasa a `approved`, la suscripción de clínica vuelve a estatus 1 y `next_billing_at` avanza un ciclo (FR-015); si pasa a `rejected`/`cancelled`, la suscripción se queda en estatus 2 (disponible para un nuevo intento) |
| `200`, cuerpo `PaymentRead` con el mismo `status` guardado (`pending`) | Sin cambios |
| `404` (`payment_not_found`) | Se trata como «no disponible» (FR-017): no se borra el cobro local ni se inventa un estatus; se registra un error (en inglés) porque no debería ocurrir con un `payment_id` que este servicio creó |
| `401`/`403`/`503`/cualquier otro `5xx`/`429`/tiempo agotado/cuerpo inesperado/`3xx` | «No disponible» (FR-017): se devuelve el último estatus local conocido, sin fallar la lectura completa |

## Variables de entorno (FR-021)

| Variable | Uso |
|---|---|
| `PAGOS_API_BASE_URL` | Dirección de `mailySoft-pagos` (mismo patrón que `USERS_API_BASE_URL`/`CLINICS_API_BASE_URL`) |
| `PAGOS_API_TIMEOUT_SECONDS` | Tiempo máximo total de cada llamada (por defecto 5 s, igual que las demás integraciones) |
| `PAGOS_API_SERVICE_TOKEN` | Credencial de aplicación para la sincronización (opcional; sin ella, la sincronización se omite) |

## Reglas de la integración (iguales al patrón ya existente)

- Asíncrona (`httpx.AsyncClient`), sin reintentos automáticos, sin seguir redirecciones.
- Las fallas de Pagos nunca filtran su cuerpo, sus cabeceras ni su dirección (FR-020); se registra
  solo el tipo de falla (en inglés), nunca el token.
- `src/integrations/payments_api.py` (`PaymentsApiClient`) solo habla HTTP; `ClinicSubscriptionService`
  lo invoca y traduce sus excepciones a los errores propios de este servicio (misma separación de
  capas que `ClinicsApiClient`/`UsersApiClient`, Principio I).

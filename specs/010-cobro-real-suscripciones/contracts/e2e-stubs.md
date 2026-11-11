# Contrato: simulaciones (Principio V)

Amplía `specs/001-subscriptions-api/contracts/e2e-stubs.md`. Las pruebas automatizadas **no pueden
depender de `mailySoft-pagos`, `mailySoft-usuarios` ni Clínicas reales** (Principio V). Se usan en
pytest, montadas en memoria con `httpx.ASGITransport` (sin red ni Docker).

## `tests/stubs/clinics_api/app.py` — ampliación: `GET /api/v1/clinics/clinic-subscriptions/{id}`

El stub ya existe (spec 001, solo con `GET /api/v1/clinics/subscription-counts`, que no cambia).

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/clinics/clinic-subscriptions/{id}` | Sin `Authorization` → `401`. Id desconocido, o registrado con otro `tenant_id` que el del token → `404` (indistinguibles). Si no, `200` con `{"tenant_id", "subscription_id", "billing_cycle"}`. |

Superficie de pruebas ampliada:

| Llamada | Para qué |
|---|---|
| `POST /__test__/clinic-subscriptions` `{ "id": "<uuid>", "tenant_id": "<uuid>", "subscription_id": 2, "billing_cycle": "monthly" }` | Registra una suscripción de clínica a mano (simula lo que Clínicas reportaría) |
| `POST /__test__/faults` con `"operation": "clinic_subscription"` (se añade a las operaciones de falla ya existentes) | Mismos modos que las demás consultas del stub (`unavailable`, `not_json`, `redirect`, `slow`…), aplicados a esta operación |

`GET /__test__/calls` y `POST /__test__/reset` se amplían para cubrir también esta operación.

## `tests/stubs/users_api/app.py` — ampliación: `GET /api/v1/authorization/me`

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/authorization/me` | Sin `Authorization` → `401 unauthenticated`. Token desconocido → `401 invalid_token`; vencido → `401 token_expired`. Si no, `200` con `{"user": {...}, "tenant_id", "roles": [{"id", "name", "permissions": [...]}], "password_change_required"}`, construido de lo que registre `/__test__/tokens` (ampliado con `tenant_id` y `password_change_required`, por omisión `null`/`false`). `GET /authorization/check` no cambia.

## `tests/stubs/payments_api/app.py` — simulación de `mailySoft-pagos` (nuevo)

Autocontenido (no importa `src/`), mismo estilo que los stubs existentes.

| Llamada | Comportamiento |
|---|---|
| `POST /api/v1/payments` | Sin `Authorization` → `401`. Sin `payments:write` → `403`. `Idempotency-Key` repetida con el mismo cuerpo → `201` con el pago ya creado; con otro cuerpo → `409 idempotency_key_conflict`. Si no, `201` con un pago nuevo, `status: pending`, `checkout_url` determinista. |
| `GET /api/v1/payments/{id}` | Sin `Authorization` → `401`. Sin `payments:read` → `403`. Id desconocido → `404 payment_not_found`. Si no, el pago guardado (su `status` puede haberse movido a mano). |

Superficie de pruebas: `POST /__test__/tokens`, `POST /__test__/payments/{id}/status`,
`POST /__test__/faults` (`operation: "create"|"get"`), `GET /__test__/calls`, `POST /__test__/reset`
— igual diseño que los demás stubs.

## Dónde se usan

- **pytest, unitarias de `ClinicSubscriptionService`**: dobles de prueba simples (no HTTP).
- **pytest, contrato** (`test_clinic_subscriptions_api.py`, `test_clinics_api_client.py`,
  `test_payments_api_client.py`): la aplicación real sobre `httpx.ASGITransport`, con los tres
  stubs montados en memoria (fixtures `clinics_stub`/`clinics_api_client` ampliados,
  `payments_stub`/`payments_api_client` nuevos, análogos a los ya existentes).
- **Pila de punta a punta (Newman) y colección de Postman**: fuera de alcance de esta entrega
  (igual que la versión anterior de este documento): pytest ya cumple el Principio V sin depender de
  servicios reales.

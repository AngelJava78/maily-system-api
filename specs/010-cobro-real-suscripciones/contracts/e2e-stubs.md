# Contrato: simulaciones (Principio V)

Amplía `specs/001-subscriptions-api/contracts/e2e-stubs.md`. Las pruebas automatizadas **no pueden
depender de `mailySoft-pagos` ni de `mailySoft-usuarios` reales** (Principio V). Se usan en pytest,
montadas en memoria con `httpx.ASGITransport` (sin red ni Docker), igual que `users_api`/`clinics_api`.

## `tests/stubs/users_api/app.py` — ampliación: `GET /api/v1/authorization/me`

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/authorization/me` | Sin `Authorization: Bearer …` → `401 unauthenticated`. Token desconocido → `401 invalid_token`; vencido → `401 token_expired`. Si no, `200` con `{"user": {"id", "status"}, "tenant_id", "roles": [{"id", "name", "permissions": [...]}], "password_change_required"}`, construido a partir de lo que registre `/__test__/tokens` (ampliado, ver abajo). |

Superficie de pruebas ampliada:

| Llamada | Para qué |
|---|---|
| `POST /__test__/tokens` `{ "token", "permissions": [...], "expired": false, "tenant_id": "…"\|null, "password_change_required": false }` | Registra un token con sus permisos (usados por `check` **y** por `me`), su `tenant_id` (nuevo campo, por omisión `null`) y si debe pedir cambio de contraseña (nuevo campo, por omisión `false`). `GET /authorization/check` no cambia su comportamiento. |
| `POST /__test__/faults` con `"operation": "me"` (se añade a `FAULT_OPERATIONS`) | Mismos modos que para `check` (`unavailable`, `malformed`, `not_json`, `redirect`, `slow`, `unauthorized_unreadable`, `unauthorized_unknown`…), aplicados a `/me`. |

`GET /__test__/calls` y `POST /__test__/reset` no cambian de forma (siguen cubriendo también `/me`).

## `tests/stubs/payments_api/app.py` — simulación de `mailySoft-pagos` (nuevo)

Autocontenido (no importa nada de `src/`), mismo estilo que los stubs existentes.

| Llamada | Comportamiento |
|---|---|
| `POST /api/v1/payments` | Sin `Authorization` → `401 unauthenticated`. Token desconocido → `401 invalid_token`. Sin `payments:write` en los permisos registrados del token → `403 permission_denied`. Con `Idempotency-Key` ya usada: mismo cuerpo → `201` con el pago ya creado (sin crear otro); cuerpo distinto → `409 idempotency_key_conflict`. Si no, `201` con un `PaymentRead` nuevo, `status: pending`, `checkout_url` determinista (`https://pagos.test/checkout/{id}`). |
| `GET /api/v1/payments/{id}` | Sin `Authorization` → `401`. Sin `payments:read` → `403`. Id desconocido → `404 payment_not_found`. Si no, el `PaymentRead` guardado (su `status` puede haberse movido a mano, ver abajo). |

Superficie de pruebas:

| Llamada | Para qué |
|---|---|
| `POST /__test__/tokens` `{ "token", "permissions": ["payments:write", "payments:read"], "expired": false }` | Registra un token (independiente de los de `users_api`: son servicios distintos) |
| `POST /__test__/payments/{id}/status` `{ "status": "approved" }` | Mueve a mano el estatus de un pago ya creado (historia 3: simula lo que Mercado Pago resolvería) |
| `POST /__test__/faults` `{ "mode": "unavailable\|forbidden\|not_found\|malformed\|not_json\|redirect\|slow", "count": 1, "delay_seconds": 30, "operation": "create\|get" }` | Hace fallar las próximas `count` llamadas de `create` o `get` |
| `GET /__test__/calls` | Peticiones recibidas: `path`, cuerpo relevante (`amount`, `currency`, `resource_type`, `resource_id`, `idempotency_key`) y si traían `Authorization` (para comprobar el reenvío del token) |
| `POST /__test__/reset` | Borra pagos, tokens, fallos y llamadas |

## Dónde se usan

- **pytest, unitarias de `ClinicSubscriptionService`**: dobles de prueba simples (no HTTP) para
  `PaymentsApiClient`/`UsersApiClient`, igual que ya hace `test_subscription_service.py` con
  `ClinicsApiClient`/`UsersApiClient`.
- **pytest, contrato** (`test_clinic_subscriptions_api.py`, `test_payments_api_client.py`): la
  aplicación real sobre `httpx.ASGITransport`, con los dos stubs también montados en memoria
  (fixture `payments_stub`/`payments_api_client`, análoga a `clinics_stub`/`clinics_api_client` de
  `tests/conftest.py`).
- **Pila de punta a punta (Newman) y colección de Postman**: fuera de alcance de esta entrega
  (Assumptions del plan): el contrato y los stubs de arriba ya cubren Principio V (pytest no depende
  de servicios reales); ampliar `docker-compose.e2e.yml` y la colección de Postman con el recorrido
  de cobro queda documentado aquí como trabajo pendiente, no bloqueante para esta especificación
  (FR-027 solo exige pytest; la constitución reserva Postman como complemento, nunca como sustituto).

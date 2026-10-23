# Contrato: simulación ampliada y colección de Postman (delta sobre `001-subscriptions-api`)

La base (dos simulaciones FastAPI autocontenidas, montadas con `httpx.ASGITransport` en pytest y
como servicios de Docker Compose en la pila e2e) **no cambia**: ver
[specs/001-subscriptions-api/contracts/e2e-stubs.md](../../001-subscriptions-api/contracts/e2e-stubs.md).
Este documento solo describe lo que esta feature añade a `tests/stubs/users_api/app.py` y a la
colección de Postman. `tests/stubs/clinics_api/app.py` no cambia.

## 1. `tests/stubs/users_api/app.py`: nueva ruta y fallos por operación

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/modules?type_id=&status_id=` | Sin `Authorization: Bearer …` → `401 unauthenticated` (mismo formato que `/api/v1/authorization/check`). Si no, `200` con los módulos sembrados cuyo `type_id`/`status_id` coincidan con los pedidos (por omisión, si no se pasan, todos) |

**Sembrado por defecto** (en memoria, se reinicia con `/__test__/reset`): los 9 módulos de tipo
Clínica (`type_id: 2`) de `src/clinic_modules.py` (research R2), todos `status_id: 1` (Activo), más
los 4 protegidos de tipo Sistema (`type_id: 1`) que ya describe la spec 013 de `mailySoft-usuarios`
(`users`, `roles`, `permissions`, `modules`), para poder probar que el filtro `type_id=2` los excluye.
Cada módulo sembrado trae `id` (correlativo, empezando en 1), `key`, `name` (en español, solo para que
la simulación sea legible; esta API no lo usa), `status: {id, name}`, `type: {id, name}`.

Superficie de pruebas ampliada (`/__test__/…`):

| Llamada | Para qué |
|---|---|
| `POST /__test__/faults` `{ "mode": "...", "count": 1, "delay_seconds": 30, "operation": "check"\|"modules" }` | **Campo nuevo, opcional**: `"operation"` decide si el fallo se consume en `/api/v1/authorization/check` o en `/api/v1/modules`. Por omisión (si se omite, como ya hacían las pruebas de 001), `"check"` — así ninguna prueba existente se rompe. Los modos ya existentes (`unavailable`, `not_json`, `malformed`, `redirect`, `slow`, …) aplican igual a la operación que indique `operation`; `wrong_permission`/`unauthorized_unreadable`/`unauthorized_unknown` solo tienen sentido para `"check"` |
| `POST /__test__/modules/reset` | Repone el sembrado por defecto de los 9 + 4 módulos (separado de `/__test__/reset`, que sigue limpiando tokens, fallos y llamadas; los módulos sembrados son parte del estado base, no algo que cada prueba registre) |
| `GET /__test__/calls` | Sin cambios de forma; ahora también registra las llamadas a `/api/v1/modules` (con `path` distinto, sin `permission`) |

## 2. Pila de punta a punta

Sin cambios en los servicios de `docker-compose.e2e.yml`: el stub de usuarios ya existente sirve
también `/api/v1/modules`, así que no hace falta un contenedor nuevo.

## 3. Colección de Postman

Se actualiza `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`
(misma convención de nombres que 001: `<operationId>: <descripción>`, `setup: …`, `docs: …`).

| Carpeta | Cambio |
|---|---|
| 0. Preparación | El token de prueba registra también el permiso `modules:read` (research «Puntos a confirmar») |
| 1. Catálogo | El cuerpo de `create_subscription: crear «Pro»` incluye los 7 campos nuevos (p. ej. `annual_price`, los 4 límites, `module_keys: ["scheduling"]`) |
| 2. Consultar y actualizar | + `update_subscription: módulo sin prerrequisito (409)` (pide `billing` sin `finance`) y `update_subscription: módulo no reconocido (422)` (pide una clave inventada) |
| 3 a 6 | Sin cambios de fondo; los cuerpos de ejemplo que crean una suscripción se actualizan con los campos obligatorios nuevos para no romper el recorrido |

La prueba `tests/contract/test_postman_collection.py` sigue sin cambios de fondo: sigue comparando la
colección contra las operaciones del OpenAPI (que no cambian de nombre ni de cantidad).

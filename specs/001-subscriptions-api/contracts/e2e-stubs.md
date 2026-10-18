# Contrato: simulaciones, pila de punta a punta y colección de Postman (Principio V)

Las pruebas automatizadas **no pueden depender del API de usuarios ni del API de clínicas reales**
(Principio V, SC-002, SC-005). Esta feature entrega **dos simulaciones mínimas** que cumplen los
contratos de [users-api-integration.md](users-api-integration.md) y
[clinics-api-integration.md](clinics-api-integration.md), y que se usan en dos sitios:

1. **pytest**: se montan en memoria con `httpx.ASGITransport` (sin red ni Docker) como transporte del
   cliente HTTP compartido de la aplicación; así se ejercita **el código real** de los clientes
   (`UsersApiClient`, `ClinicsApiClient`) y su traducción de respuestas y de fallos.
2. **Pila de punta a punta** (Newman): corren como servicios de Docker Compose; la API y Newman hablan
   con ellas por HTTP.

Decisión y alternativas en [research.md](../research.md), R15 y R16.

## 1. Las aplicaciones

Dos módulos autocontenidos (FastAPI; **no importan nada de `src/`**), con estado **en memoria** que se
reinicia con el proceso. Los ejecuta la imagen del proyecto (ya incluye FastAPI y uvicorn).

### `tests/stubs/users_api/app.py` — simulación del API de usuarios

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/authorization/check?permission=` | Sin `Authorization: Bearer …` → `401 unauthenticated` (con cuerpo `{code, message}`). Token desconocido → `401 invalid_token`; token registrado como vencido → `401 token_expired`. Permiso con formato inválido → `422`. Si no, `200 {permission, allowed}` según los permisos registrados del token |

Superficie solo de pruebas (`/__test__/…`; nunca se publica fuera de la pila aislada):

| Llamada | Para qué |
|---|---|
| `POST /__test__/tokens` `{ "token": "...", "permissions": ["subscriptions:read"], "expired": false }` | Registra un token (opaco para la simulación) y los permisos de su persona |
| `POST /__test__/faults` `{ "mode": "unavailable\|rate_limited\|forbidden\|not_found\|malformed\|wrong_permission\|not_json\|slow", "count": 1, "delay_seconds": 30 }` | Hace fallar las próximas `count` consultas: `503`, `429`, `403`, `404`, `200` sin `allowed`, `200` con otro `permission`, `200` que no es JSON o una respuesta que tarda `delay_seconds` (las pruebas de tiempo máximo usan 1 s con un tiempo máximo de 0,2 s) |
| `GET /__test__/calls` | Peticiones recibidas: `permission` y si traían `Authorization` (para comprobar **una llamada por petición**, el permiso pedido y el reenvío del token) |
| `POST /__test__/reset` | Borra tokens, fallos y llamadas |

### `tests/stubs/clinics_api/app.py` — simulación del API de clínicas

| Llamada | Comportamiento |
|---|---|
| `GET /api/v1/clinics/subscription-counts[?subscription_id=…]` | Sin `Authorization: Bearer …` → `401`. Si no, `200 {items:[…]}` con los conteos configurados (solo ≥ 1), filtrados por los `subscription_id` pedidos |

| Llamada | Para qué |
|---|---|
| `POST /__test__/counts` `{ "1": 2, "6": 14 }` | Fija los conteos por suscripción (sustituye a los anteriores) |
| `POST /__test__/faults` `{ "mode": "unavailable\|unauthorized\|forbidden\|malformed\|negative_count\|unrequested_id\|duplicate_id\|not_json\|slow", "count": 1, "delay_seconds": 30 }` | Hace fallar las próximas `count` consultas: `503`, `401`, `403`, `200` sin `items`, con un conteo negativo, con un `subscription_id` no pedido, con dos elementos del mismo id, que no es JSON o lenta |
| `GET /__test__/calls` | Peticiones recibidas: `subscription_id` pedidos y la cabecera `Authorization` recibida (para comprobar que **se reenvió el token de la persona**) |
| `POST /__test__/reset` | Borra conteos, fallos y llamadas |

## 2. Pila de punta a punta (`tests/postman/docker-compose.e2e.yml`)

Proyecto de Compose aislado `maily-system-e2e`, sobre `docker-compose.yml`:

```yaml
services:
  db:
    ports: !override []                    # base de datos desechable, sin puerto publicado
  users-api-stub:                          # (nuevo) la imagen del proyecto ejecuta la simulación
    build: .
    command: ["uvicorn", "app:app", "--app-dir", "/stub", "--host", "0.0.0.0", "--port", "8080"]
    volumes: ["./tests/stubs/users_api:/stub:ro"]
    ports: ["127.0.0.1:${E2E_USERS_STUB_PORT:-8012}:8080"]
    healthcheck: { … }                     # GET /__test__/calls
  clinics-api-stub:                        # (nuevo)
    build: .
    command: ["uvicorn", "app:app", "--app-dir", "/stub", "--host", "0.0.0.0", "--port", "8080"]
    volumes: ["./tests/stubs/clinics_api:/stub:ro"]
    ports: ["127.0.0.1:${E2E_CLINICS_STUB_PORT:-8013}:8080"]
    healthcheck: { … }
  api:
    depends_on: [users-api-stub, clinics-api-stub]
    environment:
      USERS_API_BASE_URL: http://users-api-stub:8080
      CLINICS_API_BASE_URL: http://clinics-api-stub:8080
    ports: !override ["127.0.0.1:${E2E_API_PORT:-8011}:8000"]
    healthcheck: { … }                     # GET /openapi.json
```

Todos los valores son ficticios y la pila nunca apunta a datos reales (constitución: las colecciones de
Postman usan una base de datos dedicada a pruebas). Requiere Docker Compose 2.24 o superior (`!override`).

## 3. Colección de Postman (`tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`)

Complementa a pytest (no lo sustituye) y se limita a **recorridos de punta a punta** y a los errores
clave. Variables: `baseUrl` (API), `usersStubUrl`, `clinicsStubUrl`, `accessToken` (se rellena en la
carpeta 0; el bloque Bearer solo referencia `{{accessToken}}`, que **no** es un secreto) y los
identificadores que rellenan las peticiones de creación.

| Carpeta | Recorrido |
|---|---|
| 0. Preparación | Reinicia las simulaciones, registra un token con los cuatro permisos y fija conteos |
| 1. Catálogo | Lista vacía → crear «Pro» → aparece en el listado con estatus Activa y `clinics_count: 0` |
| 2. Consultar y actualizar | Detalle, cambio de precio, nombre repetido (409), campo no permitido (422) |
| 3. Cambiar el estatus | Activa → Inactiva → Bloqueada → Activa; estatus repetido (409); estatus 4 (422) |
| 4. Eliminar | Con clínicas (409 `subscription_has_clinics`); sin clínicas (204); luego no se encuentra (404) y el nombre queda libre |
| 5. Control de acceso | Sin token (401), token inválido (401), sin permiso (403), API de usuarios caído (503); la documentación sigue pública |
| 6. Degradación de clínicas | Con el API de clínicas caído: el listado sigue con `clinics_count: null`; eliminar responde 503 `clinics_check_unavailable` |

La prueba `tests/contract/test_postman_collection.py`, parte de `uv run pytest` (no necesita Docker ni
Node.js), falla nombrando las operaciones del OpenAPI que la colección no cubre o que sobran. Los
informes (`tests/postman/reports/`) quedan fuera de Git.

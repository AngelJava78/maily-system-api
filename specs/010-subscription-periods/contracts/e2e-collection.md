# Contrato: pruebas de punta a punta de los periodos de suscripción (FR-048, FR-052; research R16, R18)

Una colección de Postman **nueva e independiente**, `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json`,
que corre con Newman contra el servicio real en la **pila aislada** de la feature 001, ahora con **cuatro**
simulaciones: Usuarios, Clínicas, componentes monitoreados y **Pagos** (nueva). No modifica las colecciones
existentes. No lleva secretos: los tokens se generan al azar en cada ejecución y viven solo en variables de
colección.

## La pila (`tests/postman/docker-compose.e2e.yml`, ajuste A9)

- **Servicio nuevo `payments-api-stub`**: la imagen del proyecto ejecuta `tests/stubs/payments_api/app.py`
  (autocontenido, sin importar `src/`), puerto del host `127.0.0.1:${E2E_PAYMENTS_STUB_PORT:-8015}`, con el
  mismo `healthcheck` que las demás simulaciones.
- **`api`**: `depends_on` de la simulación nueva y variables `PAYMENTS_API_BASE_URL: http://payments-api-stub:8080`
  y `BILLING_CUTOFF_AT: "2020-01-01T00:00:00Z"` (muy en el pasado: la fecha de corte no interviene y **manda la
  antigüedad** que cada escenario fija en la simulación de Clínicas; así no hace falta mover el reloj real).
- **Entorno** `e2e.postman_environment.json` (ajuste A10): clave nueva `paymentsStubUrl` =
  `http://127.0.0.1:8015`.
- **`package.json`** (ajuste A11): `e2e:periods` (`reports/junit-periods.xml`) y
  `e2e:all` = `npm run e2e && npm run e2e:dashboard && npm run e2e:health && npm run e2e:periods`.

## Las simulaciones (extensiones y novedades)

**Clínicas** (`tests/stubs/clinics_api/app.py`, modifica de forma aditiva):

- `GET /api/v1/organizations/{id}`: sin token → 401; token que no es el del Dueño registrado, o
  organización desconocida → `404 {"code": "not_found"}` (como el API real); si no, 200 con `id`,
  `subscription_id`, `billing_period`, `created_at` y algún campo extra (`name`) que la API debe ignorar.
- `POST /__test__/organizations` `{id, subscription_id, billing_period, created_at, owner_token}`.
- Las fallas existentes aceptan un `operation` (`counts`, por omisión, o `organizations`) y se añaden
  `missing_billing_period` e `invalid_billing_period`. `POST /__test__/reset` también vacía las organizaciones.

**Pagos** (`tests/stubs/payments_api/app.py`, nueva):

- `POST /api/v1/payments` (idempotente por `Idempotency-Key`: mismo cuerpo → el mismo pago; otro cuerpo →
  `409 idempotency_key_conflict`) y `GET /api/v1/payments/{id}` (`404 payment_not_found` si no existe), con el
  `PaymentRead` del contrato real; `checkout_url` solo mientras el pago esté `pending`.
- `POST /__test__/payments/{id}/status` `{status, amount?, currency?}` (cambia el estatus y `updated_at`),
  `POST /__test__/payments` (crea un pago «por otra vía», con el estatus y la referencia que se indiquen),
  `GET /__test__/payments`, `GET /__test__/calls` (con la cabecera `Authorization` recibida y la clave de
  idempotencia), `POST /__test__/faults` (`unavailable`, `unauthorized`, `forbidden`, `organization_required`,
  `malformed`, `not_json`, `redirect`, `slow`, `unknown_status`, `no_checkout`; con `operation`: `create`,
  `get` o `any`) y `POST /__test__/reset`.
- Todos los cuerpos de falla llevan la marca `SECRETO-INTERNO`, para comprobar que nada interno llega al
  cliente de la API.

**Usuarios**: sin cambios (concede cualquier permiso `recurso:acción`).

## Variables y personas de prueba

El script previo de la colección registra en la simulación de Usuarios, con un sufijo aleatorio, cuatro
personas: `ownerToken` (`subscription_periods:read` y `:write`), `readerToken` (solo `:read`), `plainToken`
(sin permisos) y `adminToken` (permisos de suscripciones y `modules:read`, solo para preparar y limpiar los
planes). Cada organización de prueba se da de alta en la simulación de Clínicas con su propio Dueño
(`owner_token` = `ownerToken`, salvo en el escenario de «otra organización»).

## Estructura (carpetas y recorridos)

| Carpeta | Qué hace | Peticiones |
|---|---|---|
| 0. Preparación | Reinicia las tres simulaciones, comprueba que la API publica las dos operaciones y crea los planes (14 días de prueba mensual 499.00/anual 4990.00; sin prueba; sin cobro) | `setup: …` |
| 1. Consulta | Organización en prueba (`trial`, 9 días), la misma consulta devuelve las mismas fechas, vencida (`overdue`, −26), sin prueba (`trial_ends_at` `null`), sin cobro (`no_charge`, nulos), anual (importe 4990.00) | `get_subscription_period: …` |
| 2. Iniciar el pago | 201 con el checkout (y comprobar en Pagos: importe 49900, `MXN`, referencia), repetir → 200 y el mismo checkout, la consulta informa el cobro en curso, sin cobro → 409 | `create_subscription_payment: …`, `get_subscription_period: …` |
| 3. Pago aprobado | Aprobar en Pagos → la consulta mueve la fecha un mes y una segunda consulta no la mueve otra vez; rechazado → se cierra y se puede pagar de nuevo (201 con otro checkout); aprobado con otro importe → no se aplica; un pago «por otra vía» no mueve nada | `get_subscription_period: …`, `create_subscription_payment: …` |
| 4. Control de acceso | Sin token (401), token inválido (401), sin permiso (403), solo lectura al iniciar el pago (403), organización de otra persona (404), `organization_id` inválido (422), el permiso antes que el formato (403), Usuarios caído (503) | ambas |
| 5. Degradación | Clínicas caída (503), Clínicas sin `billing_period` (503), Pagos caído al consultar con un cobro pendiente (200 y `payment_in_progress` `null`), Pagos caído al iniciar el pago (503 y sin cobro nuevo) | ambas |
| 6. Contrato | El contrato publicado declara el permiso de cada operación y la forma de las respuestas | `docs: …` |
| 7. Limpieza | Elimina los planes que creó la preparación y reinicia las simulaciones | `setup: …` |

Los casos que dependen de mover el reloj (límites exactos del tiempo, meses cortos, año bisiesto, el orden
de dos pagos) **no** van aquí: los cubren las pruebas unitarias y de contrato con reloj fijo (Principio V:
Postman no repite pytest).

## Pruebas guardianas (`tests/contract/test_periods_postman_collection.py`, reglas G1 a G9)

Solo leen archivos del repositorio y el OpenAPI que genera la aplicación; no necesitan servicios, Node ni
Postman. Cada regla es una función `check_*` cuyos mensajes dicen qué falta o sobra, y las pruebas también la
ejecutan sobre copias alteradas en memoria.

| Regla | Comprueba |
|---|---|
| G1 | La colección es un documento de formato v2.1 |
| G2 | Cada `operationId` de las rutas `/api/v1/subscription-periods` tiene al menos una petición, y toda petición nombrada «`<operationId>: …`» corresponde a una operación de la API (`setup` y `docs` son ayudas) |
| G3 | La colección, cada carpeta y cada petición tienen descripción, y cada petición tiene al menos un `pm.test` |
| G4 | Hay un caso para cada estatus del contrato: 200, 201, 401, 403, 404, 409, 422 y 503 |
| G5 | La autenticación solo referencia variables (`{{accessToken}}`, `{{ownerToken}}`, `{{readerToken}}`, `{{plainToken}}`, `{{adminToken}}`, `{{badToken}}`) |
| G6 | Ningún token, JWT, `Bearer` literal ni la palabra «secret»; la marca de la simulación no se escribe entera |
| G7 | Las simulaciones solo se tocan por `/__test__/`; la API solo se escribe con `POST …/payments` y, en la preparación y la limpieza, con `POST`/`DELETE` de `/api/v1/subscriptions`; ninguna otra ruta |
| G8 | Ninguna variable del entorno oculta una de la colección |
| G9 | Las **cinco** colecciones juntas cubren exactamente las operaciones de la API (la regla existente se amplía, ajuste A8) |

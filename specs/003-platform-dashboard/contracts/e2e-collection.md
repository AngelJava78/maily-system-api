# Contrato: colección de Postman del dashboard (FR-036, Aclaración 4)

**Archivo**: `tests/postman/collections/MailySoft-System-Dashboard.postman_collection.json` (nuevo) |
**Entorno**: el existente `tests/postman/environments/e2e.postman_environment.json`, sin cambios (usa
`baseUrl` y `usersStubUrl`) | **Ejecuta**: Newman contra la pila aislada de punta a punta de la feature 001.

Es una colección **nueva e independiente**: no se toca la colección de suscripciones ni la manual. Es de solo
lectura sobre la API (no crea ni cambia nada, así que puede repetirse sin limpiar), y no repite lo que ya
cubre la suite de pytest (Principio V). Lo que Postman **no** puede cubrir —menos clínicas que el límite,
conjunto vacío, variable de configuración válida e inválida, la degradación de una fuente— lo cubre pytest,
porque la pila real corre con los datos ficticios fijos y no cambia su configuración.

## Convenciones (las mismas de la colección de suscripciones)

- Cada petición se llama `<operationId>: <descripción>`; las auxiliares usan `setup: …` (preparan la simulación
  del API de usuarios) o `docs: …` (comprueban el contrato publicado). La única operación es `get_dashboard`.
- Toda petición tiene descripción y un evento `test` con al menos un `pm.test("…")`.
- **Autenticación**: la colección usa Bearer `{{accessToken}}`; las peticiones heredan, son `noauth` o llevan
  exactamente `{{plainToken}}`, `{{subscriptionsToken}}` o `{{badToken}}`. Ningún token se escribe en el archivo.
- **Sin secretos**: nada de la palabra «secret», ningún JWT, ningún `Bearer <literal>` (los barre
  `test_no_file_of_the_postman_folder_holds_a_token_or_a_secret`, que ya recorre toda la carpeta).
- Variables de colección: `firstBody` (cuerpo de la primera respuesta, para comparar la segunda). Ninguna
  coincide con las claves del entorno (`baseUrl`, `usersStubUrl`, `clinicsStubUrl`).

## Script previo de la colección

Mismo patrón que la colección de suscripciones: la primera vez, registra en la simulación del API de usuarios
(`{{usersStubUrl}}/__test__/tokens`) a tres personas con tokens al azar, que quedan **solo en variables de
colección**:

| Variable | Persona | Permisos |
|---|---|---|
| `accessToken` | Administrador de plataforma | `dashboard:read` |
| `plainToken` | Persona sin permisos | ninguno |
| `subscriptionsToken` | Persona con permisos de otro recurso | `subscriptions:read`, `subscriptions:write`, `subscriptions:update`, `subscriptions:delete` |

`badToken` (un token no registrado) se genera en cada petición. Si el registro falla, el script lanza un error
en español ("¿Está levantada la pila de pruebas?"). Tras reiniciar la simulación se descartan las tres
variables para que el script previo las registre de nuevo.

## Carpetas y peticiones

Las comprobaciones de la forma de la respuesta verifican **invariantes** (que sirven también cuando existan las
fuentes reales) y, donde se indica, los valores concretos de los datos ficticios de
[data-model.md](../data-model.md).

### 0. Preparación

| Petición | Qué hace / comprueba |
|---|---|
| `setup: reiniciar la simulación del API de usuarios` | `POST {{usersStubUrl}}/__test__/reset` → 200; descarta los tres tokens |
| `setup: la API responde y las personas de prueba están registradas` | `GET /openapi.json` sin token → 200; el título; el contrato incluye `get_dashboard`; hay tres tokens |

### 1. Resumen (US1 y US3)

| Petición | Comprueba |
|---|---|
| `get_dashboard: sin limit devuelve el resumen con 5 clínicas` | 200; `Cache-Control: no-store`; exactamente las 7 claves del contrato; seis enteros ≥ 0; 5 clínicas con `id` UUID, `name`, `created_at` `…Z` y `status` `{id, name}` (y **solo** esas 4 claves); orden descendente por fecha; invariantes I1 a I4; guarda `firstBody` |
| `get_dashboard: una segunda consulta devuelve exactamente lo mismo` | Cuerpo idéntico a `firstBody` (determinismo, FR-021) |
| `get_dashboard: limit=1 devuelve una clínica` | 1 clínica: la más reciente (Clínica Santa Aurora) |
| `get_dashboard: limit=3 devuelve las 3 más recientes` | 3 clínicas, ids de las filas 1 a 3 |
| `get_dashboard: limit=4 resuelve el empate por identificador` | 4 clínicas; la cuarta es Dental Sonríe (`41902d77-…`, id menor del par con la misma fecha) |
| `get_dashboard: limit=10 devuelve 10 con el orden y el desempate` | 10 clínicas; hay estatus «Activa» (id 1) y «En prueba» (id 2); posiciones 4 y 5: Dental Sonríe y Clínica San Rafael, con el **mismo** `created_at` e ids ascendentes |
| `get_dashboard: limit=11 devuelve 10 sin error` | 200 con 10 clínicas |
| `get_dashboard: un limit enorme devuelve 10 sin error` | Un entero de 30 cifras → 200 con 10 clínicas (`limit=1000` y el de 5 000 dígitos los cubre pytest) |

### 2. `limit` inválido (US3, 422)

Cinco peticiones `get_dashboard: limit=… se rechaza` con `limit=0`, `limit=abc`, `limit=` (vacío), `limit=5.5` y
`limit=3&limit=5`. Cada una comprueba: 422; `code` `validation_error`; `errors[0].field` `limit`; el mensaje
exacto en español («El parámetro «limit» debe ser un número entero mayor o igual que 1.»); que el mensaje no
repite el valor enviado; y que el cuerpo no trae `recent_clinics` ni ningún indicador.

### 3. Control de acceso (US2)

| Petición | Comprueba |
|---|---|
| `get_dashboard: sin token se pide iniciar sesión` | `noauth` → 401 `unauthenticated` |
| `get_dashboard: un token inválido se rechaza` | `{{badToken}}` → 401 `invalid_token` |
| `get_dashboard: una persona sin permisos recibe 403` | `{{plainToken}}` → 403 `permission_denied`; el mensaje nombra `dashboard:read` |
| `get_dashboard: los permisos de suscripciones no autorizan el dashboard` | `{{subscriptionsToken}}` → 403 `permission_denied` |
| `get_dashboard: el permiso se comprueba antes que limit` | `{{plainToken}}` con `limit=abc` → **403**, no 422 |
| `setup: el API de usuarios dejará de responder una vez` | `POST {{usersStubUrl}}/__test__/faults` (`unavailable`, 1) → 200 |
| `get_dashboard: con el API de usuarios caído se rechaza antes de validar limit` | `limit=abc` → **503** `authorization_unavailable` (falla cerrada y permiso antes que validación) |
| `get_dashboard: con el API de usuarios sano vuelve a responder` | La falla ya se consumió → 200 |
| `docs: el contrato publicado declara el permiso y el parámetro limit` | `GET /openapi.json` sin token → `get_dashboard` con `x-required-permission` `dashboard:read` y el parámetro `limit` de tipo `integer` |

## Pruebas guardianas (`tests/contract/test_dashboard_postman_collection.py`)

Solo leen archivos y el OpenAPI generado (sin Node.js, sin Postman, sin red), igual que las de las otras
colecciones. Cada regla nombra lo que falta o sobra.

| Id | Regla |
|---|---|
| G1 | JSON válido; `info.schema` termina en `/collection/v2.1.0/collection.json` |
| G2 | Los prefijos de petición (sin `setup` ni `docs`) son **exactamente** las operaciones de la API bajo `/api/v1/dashboard`; ninguna petición sin prefijo válido ni repetida |
| G3 | Toda petición, carpeta y la colección tienen `description` no vacía; toda petición tiene un `test` con `pm.test` |
| G4 | Hay al menos una petición que comprueba cada estatus 200, 401, 403, 422 y 503 |
| G5 | La autenticación de la colección es Bearer `{{accessToken}}`; cada petición hereda, es `noauth` o es Bearer con exactamente `{{plainToken}}`, `{{subscriptionsToken}}` o `{{badToken}}` |
| G6 | Sin secretos: ningún JWT, ningún `Bearer <literal>`, ninguna variable de colección cuyo nombre contenga `token`, `secret` o `password` con valor, y ningún valor que parezca una clave |
| G7 | Solo lectura: toda petición a `{{baseUrl}}` es `GET` y no usa rutas de suscripciones; las `setup` o manejan la simulación (`{{usersStubUrl}}/__test__/…`) o son un `GET /openapi.json` (la que comprueba que la API responde) |
| G8 | Ninguna variable de la colección coincide con una clave del entorno `e2e` (la de entorno la ocultaría) |
| G9 | Las tres colecciones **juntas** cubren exactamente las operaciones del OpenAPI de la API (restituye la garantía global que A3 acota; [plan](../plan.md)) |

## Ejecución

```text
cd tests/postman
npm install                       # una vez (Newman es solo una herramienta de desarrollo)
npm run e2e:dashboard             # solo esta colección → reports/junit-dashboard.xml
npm run e2e:all                   # suscripciones y luego el dashboard
```

`e2e` (la colección de suscripciones) queda como estaba. La pila aislada se levanta y se desmonta igual que
para la feature 001 ([quickstart](../quickstart.md)); `DASHBOARD_RECENT_CLINICS_LIMIT` no se define en ella, así
que rige el valor por defecto 5 (de lo que dependen las aserciones). Los informes (`reports/`) no se versionan.

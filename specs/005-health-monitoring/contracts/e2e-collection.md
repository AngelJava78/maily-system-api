# Contrato: colección de Postman de salud y su pila de punta a punta (FR-042, SC-012)

**Archivo**: `tests/postman/collections/MailySoft-System-Salud.postman_collection.json` (nuevo, v2.1) |
**Entorno**: `tests/postman/environments/e2e.postman_environment.json` con una clave nueva,
`componentsStubUrl` (`http://127.0.0.1:8014`) | **Ejecuta**: Newman contra la pila aislada
`maily-system-e2e`, ampliada con la simulación de componentes.

Colección **nueva e independiente**: no se tocan las de suscripciones, dashboard ni la manual (FR-040). Crea,
modifica y elimina componentes, solo en la base de datos desechable de la pila. No repite lo que cubre pytest
(Principio V): el horario y `next_start_at`, la copia en memoria, la base de datos caída (500 y
`/health/ready` 503), el periodo mínimo del estado público y los límites de depuración se prueban solo con
pytest, porque Newman no puede detener la base ni mover el reloj del servicio.

## Pila de punta a punta (cambios en `tests/postman/docker-compose.e2e.yml`)

- Servicio nuevo `components-stub`: la imagen del proyecto ejecuta `tests/stubs/components/app.py`
  (`uvicorn app:app --app-dir /stub --port 8080`), autocontenido como las otras simulaciones; publicado solo
  en `127.0.0.1:${E2E_COMPONENTS_STUB_PORT:-8014}` para su superficie `/__test__/`; con su `healthcheck`.
- La API depende de él (`service_healthy`) y recibe `HEALTH_ALLOWED_HOSTS: components-stub,missing-service.invalid`
  (el segundo nunca resuelve: RFC 6761), `HEALTH_CHECK_TIMEOUT_SECONDS: "2"` y `HEALTH_CACHE_SECONDS: "0"`
  (cada consulta de salud agrega de nuevo y las aserciones no dependen de la caché). Sin horario.

### Simulación de componentes (`tests/stubs/components/app.py`)

Un mismo proceso imita varios componentes, cada uno bajo un prefijo de ruta (su `base_url` es
`http://components-stub:8080/<prefijo>`):

| Prefijo | `live` | `ready` | `info` |
|---|---|---|---|
| `healthy` | 200 `{"status":"ok"}` | 200 `ok` con un chequeo `database` | 200 con versión, commit, fecha y entorno |
| `not-ready` | 200 | 503 `unavailable` con un chequeo `database` en `timeout` | 200 |
| `html` | 200 HTML | 200 HTML | 200 HTML |
| `not-json` | 200 `text/plain` | ídem | ídem |
| `redirect` | 307 a `/healthy/...` | ídem | ídem |
| `slow` | Espera 30 s | ídem | ídem |
| `too-large` | 200 con 70 KiB | ídem | ídem |
| `info-incomplete` | 200 | 200 | 200 con tipos y fechas inválidos y textos de 100 caracteres |
| `error` | 500 con el marcador `SECRETO-INTERNO` | ídem | ídem |
| `spa` | 200 HTML en **cualquier** ruta (como el *catch-all* de Maily360) | — | — |

`/__test__/calls` devuelve las llamadas recibidas (ruta, nombres de cabeceras, si traían `Authorization` o
`Cookie`) y `/__test__/reset` las borra. pytest monta la misma aplicación en memoria.

## Convenciones (las mismas de las otras colecciones)

- Cada petición se llama `<operationId>: <descripción>`; las auxiliares, `setup: …` (preparan simulaciones o
  limpian el registro) o `docs: …` (contrato publicado).
- Toda petición tiene descripción y un evento `test` con al menos un `pm.test("…")`.
- Autenticación de la colección: Bearer `{{accessToken}}`; cada petición hereda, es `noauth` o lleva
  exactamente `{{readerToken}}`, `{{plainToken}}`, `{{subscriptionsToken}}` o `{{badToken}}`. Ningún token se
  escribe en el archivo.
- Sin secretos (sin la palabra «secret», sin JWT ni `Bearer <literal>`); las variables de colección no
  coinciden con claves del entorno (`baseUrl`, `usersStubUrl`, `clinicsStubUrl`, `componentsStubUrl`).

## Script previo de la colección

La primera vez registra en la simulación del API de usuarios, con tokens al azar que quedan solo en
variables de colección:

| Variable | Persona | Permisos |
|---|---|---|
| `accessToken` | Administración de la plataforma | `health:read`, `health:write`, `health:update`, `health:delete` |
| `readerToken` | Solo consulta | `health:read` |
| `plainToken` | Sin permisos | ninguno |
| `subscriptionsToken` | Permisos de otro recurso | `subscriptions:*` y `dashboard:read` |

`badToken` (no registrado) se genera en cada petición.

## Carpetas y peticiones

### 0. Preparación

| Petición | Qué hace / comprueba |
|---|---|
| `setup: reiniciar la simulación del API de usuarios` | `POST {{usersStubUrl}}/__test__/reset` → 200; descarta los tokens |
| `setup: reiniciar la simulación de componentes` | `POST {{componentsStubUrl}}/__test__/reset` → 200 |
| `setup: vaciar el registro` | Lista el registro y elimina cada componente (con `pm.sendRequest`), para que la colección pueda repetirse |

### 1. Contrato de salud (público)

| Petición | Comprueba |
|---|---|
| `get_health_live: responde sin token` | `noauth` → 200 `{"status":"ok"}`; `Cache-Control: no-store` |
| `get_health_ready: la base de datos responde` | 200; `status` `ok`; un chequeo `database` `ok` con `latency_ms` entero; `no-store` |
| `get_info: identifica el build` | 200; `service` `maily-system-api`; `version` igual a `info.version` de `/openapi.json`; `commit`, `build_date` y `environment` presentes (en la pila valen `unknown`) |
| `get_health_status: estado público sin token` | 200; `no-store`; solo `status`, `checked_at` y `components`; cada componente solo con `code`, `name`, `kind`, `status` y `next_start_at` |
| `get_health_status: un token no cambia nada` | Con `{{badToken}}` → 200 y la misma forma; la simulación del API de usuarios no registró ninguna consulta |
| `docs: las rutas públicas no exigen token` | `GET /openapi.json`: las cuatro operaciones públicas sin `security` y con la etiqueta «Salud» |

### 2. Registro

| Petición | Comprueba |
|---|---|
| `create_monitored_component: un servicio sano` | 201; `Location`; `id` UUID; rutas por defecto; `enabled` `true`; `sort_order` 0; fechas `…Z` |
| `create_monitored_component: un servicio que no está listo` | 201 (`not-ready`, `sort_order` 10) |
| `create_monitored_component: un frontend` | 201 (`spa`, `live_path` `/healthz/`, sin `ready_path`; `info_path` nula) |
| `get_monitored_component: por su identificador` | 200 con los mismos datos |
| `list_monitored_components: todos, en orden` | 200; lista sin envoltorio; orden por `sort_order` y `code` |
| `get_health: aparecen los registrados` | 200; `no-store`; los dos integrados primero; el sano `up`, el no listo `degraded` con `not_ready`, el frontend `up`; 13 campos por componente; **ningún** `base_url` ni `components-stub` en el cuerpo |
| `update_monitored_component: cambia el nombre` | 200; `updated_at` posterior |
| `update_monitored_component: deshabilitar` | 200; `enabled` `false` |
| `get_health: el deshabilitado no aparece` | 200 sin ese `code`; sigue en el listado |
| `update_monitored_component: habilitar de nuevo` | 200; vuelve a aparecer en la salud |
| `delete_monitored_component: baja lógica` | 204 |
| `get_monitored_component: el eliminado no se encuentra` | 404 `monitored_component_not_found` |
| `create_monitored_component: reutilizar el código` | 201 con otro `id` |
| `setup: las llamadas a los componentes no llevan token` | `GET {{componentsStubUrl}}/__test__/calls` → ninguna con `Authorization` ni `Cookie` |

### 3. Componentes caídos

| Petición | Comprueba |
|---|---|
| `create_monitored_component: un servicio lento` | 201 (`slow`) |
| `create_monitored_component: un servicio que devuelve HTML` | 201 (`html`) |
| `create_monitored_component: un servicio que no resuelve` | 201 (`http://missing-service.invalid`) |
| `get_health: con componentes caídos responde 200` | 200; global `down`; `slow` `down` con `timeout`; `html` `down` con `invalid_response`; el que no resuelve `down` con `dns_error`; ningún texto `SECRETO-INTERNO` ni cuerpo crudo |
| `get_health_status: el estado público coincide` | 200; mismos códigos, orden y estados que la consulta anterior, sin campos extra |

### 4. Errores del registro

| Petición | Comprueba |
|---|---|
| `create_monitored_component: código repetido` | 409 `monitored_component_code_already_exists` |
| `create_monitored_component: código reservado` | `database` → 409 |
| `create_monitored_component: host no permitido` | `http://not-allowed.test` → 422 en `base_url`; el mensaje no repite la dirección |
| `create_monitored_component: dirección con credenciales` | `http://usuario:clave@components-stub:8080` → 422; el mensaje no contiene `clave` |
| `create_monitored_component: frontend con ruta de disponibilidad` | 422 en `ready_path` |
| `create_monitored_component: campo no reconocido` | 422 |
| `update_monitored_component: sin ningún dato` | 422 |
| `get_monitored_component: identificador inexistente` | 404 |
| `get_monitored_component: identificador que no es UUID` | 422 en `component_id` |

### 5. Control de acceso

| Petición | Comprueba |
|---|---|
| `get_health: sin token se pide iniciar sesión` | `noauth` → 401 `unauthenticated`; sin datos de salud |
| `get_health: un token inválido se rechaza` | `{{badToken}}` → 401 `invalid_token` |
| `get_health: sin permisos recibe 403` | `{{plainToken}}` → 403; el mensaje nombra `health:read` |
| `get_health: los permisos de otros recursos no autorizan` | `{{subscriptionsToken}}` → 403 |
| `create_monitored_component: solo lectura no registra, aunque los datos sean inválidos` | `{{readerToken}}` con un cuerpo inválido → **403** (el permiso va antes que la validación) |
| `delete_monitored_component: solo lectura no elimina` | `{{readerToken}}` → 403 |
| `setup: el API de usuarios dejará de responder una vez` | `POST {{usersStubUrl}}/__test__/faults` (`unavailable`, 1) → 200 |
| `get_health_status: responde aunque el API de usuarios no` | 200 (la falla no se consume: no hay consulta de permisos) |
| `get_health: con el API de usuarios caído se rechaza` | 503 `authorization_unavailable`; consume la falla |
| `get_health: vuelve a responder` | 200 |

## Pruebas guardianas (`tests/contract/test_health_postman_collection.py`)

Solo leen archivos y el OpenAPI generado (sin Node.js, Postman ni red). Cada regla es una función
`check_*(...) -> list[str]` y se prueba también sobre copias alteradas en memoria.

| Id | Regla |
|---|---|
| G1 | JSON válido; `info.schema` termina en `/collection/v2.1.0/collection.json` |
| G2 | Los prefijos (sin `setup` ni `docs`) son **exactamente** las diez operaciones de salud del OpenAPI (rutas `/health/…`, `/info`, `/api/v1/health` y `/api/v1/monitored-components…`); ningún nombre repetido |
| G3 | Toda petición, carpeta y la colección tienen descripción; toda petición tiene un `pm.test` |
| G4 | Hay al menos un caso para cada estatus 200, 201, 204, 401, 403, 404, 409, 422 y 503 |
| G5 | Autenticación solo por variables: Bearer `{{accessToken}}` en la colección; en cada petición, herencia, `noauth` o uno de los tokens permitidos |
| G6 | Sin secretos: ningún JWT, ningún `Bearer <literal>`, ninguna variable con `token`, `secret` o `password` en el nombre y un valor, ningún valor que parezca una clave |
| G7 | Las escrituras a `{{baseUrl}}` solo van a `/api/v1/monitored-components`; ninguna petición toca suscripciones ni el dashboard; las simulaciones solo se usan por `/__test__/` |
| G8 | Ninguna variable de la colección coincide con una clave del entorno `e2e` |

La garantía global (las colecciones **juntas** cubren exactamente las operaciones de la API) la sigue dando
G9 de `test_dashboard_postman_collection.py`, ampliada a las cuatro colecciones (ajuste A6 del
[plan](../plan.md)).

## Ejecución

```text
cd tests/postman
npm ci                             # una vez (Newman es solo una herramienta de desarrollo)
npm run e2e:health                 # solo esta colección → reports/junit-health.xml
npm run e2e:all                    # suscripciones, dashboard y salud, una tras otra
```

Los informes (`reports/`) no se versionan.

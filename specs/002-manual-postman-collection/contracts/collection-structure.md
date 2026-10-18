# Contrato: estructura de la colección manual

**Archivo**: `tests/postman/collections/MailySoft-System-Manual.postman_collection.json` (v2.1) |
**Spec**: FR-001 a FR-005, FR-013 a FR-018 | **Modelo**: [../data-model.md](../data-model.md)

Cuatro carpetas, **44 peticiones**. Cada una se llama `<operationId>: <descripción>`; las que no son
operaciones de la API usan el prefijo `docs` o `sim`. En «Casos de error», la descripción empieza por el estatus
HTTP (`401 sin token`): la prueba de desfase lo usa para comprobar que existe un caso de cada tipo (regla D2).

Convenciones comunes: la URL siempre empieza por `{{baseUrl}}` (o `{{clinicsStubUrl}}` en la carpeta 3);
los cuerpos son JSON; la autenticación se **hereda** de la colección (Bearer `{{accessToken}}`) salvo donde se indica;
todos los textos visibles están en español. «Tests» son comprobaciones ligeras (estatus, `code`, campos
clave); los mensajes que fija el contrato se comprueban literalmente.

## Carpeta `0. Empezar`

Primeros pasos: comprobar que el acceso funciona y que la API publica su documentación.

| # | Nombre | Método y ruta | Auth | Respuesta esperada y comprobaciones |
|---|---|---|---|---|
| 0.1 | `list_subscriptions: comprobar el acceso y ver el catálogo` | `GET /api/v1/subscriptions` | hereda | 200; es un arreglo; cada elemento trae `id`, `name`, `monthly_price` (cadena), `features` (arreglo), `status {id,name}` y `clinics_count` (número o `null`). La descripción lleva el paso a paso de arranque, el permiso `subscriptions:read` y qué significa cada 401/403/503 |
| 0.2 | `docs: contrato OpenAPI` | `GET /openapi.json` | `noauth` | 200 sin token; trae `openapi` y las rutas de suscripciones |
| 0.3 | `docs: documentación interactiva` | `GET /docs` | `noauth` | 200 sin token; es HTML |

## Carpeta `1. Ciclo de vida de una suscripción`

Se recorre **en orden**; las peticiones 1.2 a 1.10 actúan solo sobre la suscripción que crea la 1.1.

| # | Nombre | Método y ruta | Cuerpo de ejemplo | Respuesta esperada y comprobaciones |
|---|---|---|---|---|
| 1.1 | `create_subscription: crear la suscripción de prueba` | `POST /api/v1/subscriptions` | `{"name":"Prueba manual {{newSuffix}}","description":"Creada desde la colección manual.","monthly_price":4500,"features":["Hasta 5 consultorios","Usuarios ilimitados"]}`; el script de acceso genera `newSuffix` | 201; nace Activa (`status {id:1,name:"Activa"}`); `monthly_price` `"4500.00"`; `clinics_count` 0. **Guarda** `subscriptionId` y `subscriptionName` |
| 1.2 | `get_subscription: consultar la suscripción creada` | `GET …/{{subscriptionId}}` | — | 200; mismo `id`; `clinics_count` es número o `null` («no disponible», explicado) |
| 1.3 | `list_subscriptions: la suscripción creada aparece en el catálogo` | `GET /api/v1/subscriptions` | — | 200; el arreglo contiene el `id` guardado |
| 1.4 | `update_subscription: cambiar el precio y las funciones` | `PATCH …/{{subscriptionId}}` | `{"monthly_price":4700,"features":["Hasta 8 consultorios"]}` | 200; `monthly_price` `"4700.00"` |
| 1.5 | `update_subscription: cambiar el nombre` | `PATCH …/{{subscriptionId}}` | `{"name":"{{subscriptionName}} renombrada"}` | 200; el nombre cambió. **Actualiza** `subscriptionName` |
| 1.6 | `change_subscription_status: pasar a Inactiva` | `PATCH …/{{subscriptionId}}/status` | `{"status_id":2}` | 200; `status {id:2,name:"Inactiva"}` |
| 1.7 | `change_subscription_status: pasar a Bloqueada` | ídem | `{"status_id":3}` | 200; Bloqueada |
| 1.8 | `change_subscription_status: volver a Activa` | ídem | `{"status_id":1}` | 200; Activa |
| 1.9 | `delete_subscription: eliminar la suscripción de prueba` | `DELETE …/{{subscriptionId}}` | — | **204, 409 o 503**; cada uno tiene su título (eliminada / «tiene clínicas» / «no se pudo comprobar, es lo esperado sin API de clínicas ni simulación»). Con 204 **guarda** `deletedSubscriptionId` |
| 1.10 | `get_subscription: la eliminada ya no se encuentra` | `GET …/{{subscriptionId}}` | — | Si 1.9 dio 204: 404 `subscription_not_found`. Si no, la suscripción sigue existiendo: 200 y el título lo explica |

## Carpeta `2. Casos de error`

Cada petición provoca **un** error y lo explica. Las dos primeras preparan los datos que usan las demás; la
última limpia. **Ninguna** petición de esta carpeta actúa sobre datos que no haya creado la colección.

| # | Nombre | Método, ruta y auth | Respuesta esperada |
|---|---|---|---|
| 2.1 | `create_subscription: crear la suscripción para los casos de error` | `POST` (hereda) | 201; guarda `subscriptionId`/`subscriptionName` (sustituye a la anterior) |
| 2.2 | `create_subscription: crear otra suscripción para el choque de nombres` | `POST` (hereda) | 201; guarda `otherSubscriptionId`/`otherSubscriptionName` |
| 2.3 | `list_subscriptions: 401 sin token` | `GET`, `noauth` | 401 `unauthenticated`, «Debe iniciar sesión para usar esta operación.» |
| 2.4 | `list_subscriptions: 401 token inválido` | `GET`, Bearer `{{badToken}}` | 401 `invalid_token`, «El token de acceso no es válido.» |
| 2.5 | `list_subscriptions: 403 persona sin permiso` | `GET`, Bearer `{{plainToken}}` | 403 `permission_denied`, nombra `subscriptions:read`. **Opcional**: sin segunda aplicación se omite y explica (FR-014) |
| 2.6 | `create_subscription: 403 persona sin permiso no crea nada` | `POST`, Bearer `{{plainToken}}` | 403, nombra `subscriptions:write`. Opcional (ídem) |
| 2.7 | `get_subscription: 404 identificador inexistente` | `GET …/{{nonexistentSubscriptionId}}` | 404 `subscription_not_found` con el identificador en el mensaje |
| 2.8 | `get_subscription: 404 suscripción eliminada` | `GET …/{{deletedSubscriptionId}}` | 404; si aún no hay una eliminada, se omite y dice que primero se complete la carpeta 1 |
| 2.9 | `create_subscription: 409 nombre repetido` | `POST`, nombre `{{subscriptionName}}` | 409 `subscription_name_already_exists` |
| 2.10 | `update_subscription: 409 nombre de otra suscripción` | `PATCH …/{{otherSubscriptionId}}`, `{"name":"{{subscriptionName}}"}` | 409 |
| 2.11 | `change_subscription_status: 409 estatus repetido` | `PATCH …/{{subscriptionId}}/status`, `{"status_id":1}` | 409 `subscription_status_unchanged` |
| 2.12 | `create_subscription: 422 nombre ausente` | `POST`, sin `name` | 422 `validation_error`; `errors[]` nombra el campo |
| 2.13 | `create_subscription: 422 precio negativo` | `POST`, `monthly_price: -1` | 422 |
| 2.14 | `create_subscription: 422 precio con tres decimales` | `POST`, `monthly_price: "10.125"` | 422 |
| 2.15 | `create_subscription: 422 lista de funciones nula` | `POST`, `features: null` | 422 |
| 2.16 | `update_subscription: 422 campo no permitido` | `PATCH …/{{subscriptionId}}`, `{"status":2}` | 422, «El campo «status» no está permitido.» |
| 2.17 | `change_subscription_status: 422 estatus no permitido` | `PATCH …/{{subscriptionId}}/status`, `{"status_id":4}` | 422; el campo es `status_id` |
| 2.18 | `delete_subscription: 503 no se puede comprobar el API de clínicas` | `DELETE …/{{subscriptionId}}` | **503** `clinics_check_unavailable` sin simulación de clínicas (no se elimina nada). Si la simulación responde: 204 o 409, con título que lo explica; no es un fallo |
| 2.19 | `delete_subscription: limpiar la otra suscripción` | `DELETE …/{{otherSubscriptionId}}` | 204 (o 503, explicado) |

Descripciones obligatorias en la carpeta (FR-015, sin provocarlos): **503 por permiso no verificable** (el API de usuarios
no responde, `authorization_unavailable`) y **403 generalizado** (la persona no está registrada en el API de usuarios
o su rol no tiene los cuatro permisos de suscripciones).

## Carpeta `3. Simulación de clínicas (solo local)` — opcional

Requiere la simulación en `{{clinicsStubUrl}}` (`http://127.0.0.1:8001`). Si esa variable está vacía (entorno
desplegado), **cada** petición se omite con un mensaje propio y no cuenta como fallo (FR-017). Las `sim` no
llevan autenticación.

| # | Nombre | Método y ruta | Cuerpo | Respuesta esperada |
|---|---|---|---|---|
| 3.1 | `sim: reiniciar la simulación` | `POST {{clinicsStubUrl}}/__test__/reset` | — | 200 |
| 3.2 | `create_subscription: crear la suscripción para la simulación` | `POST {{baseUrl}}/api/v1/subscriptions` | como 1.1 | 201; guarda `subscriptionId`/`subscriptionName` |
| 3.3 | `sim: fijar 3 clínicas a la suscripción de prueba` | `POST …/__test__/counts` | `{"{{subscriptionId}}":3}` | 200. La descripción avisa: **reemplaza todos los conteos** |
| 3.4 | `get_subscription: el detalle muestra 3 clínicas` | `GET …/{{subscriptionId}}` | — | 200; `clinics_count` 3 |
| 3.5 | `delete_subscription: con clínicas asignadas se rechaza` | `DELETE …/{{subscriptionId}}` | — | 409 `subscription_has_clinics`; sigue existiendo |
| 3.6 | `sim: provocar un fallo del API de clínicas` | `POST …/__test__/faults` | `{"mode":"unavailable","count":3}` | 200; las tres siguientes consultas de clínicas fallan (la de 3.7, la comprobación previa de propiedad que hace la colección antes de eliminar y la propia eliminación) |
| 3.7 | `get_subscription: con la simulación fallando el conteo es null` | `GET …/{{subscriptionId}}` | — | 200; `clinics_count` `null` y la consulta sigue funcionando |
| 3.8 | `delete_subscription: con la simulación fallando no se elimina` | `DELETE …/{{subscriptionId}}` | — | 503 `clinics_check_unavailable` |
| 3.9 | `sim: dejar la suscripción sin clínicas` | `POST …/__test__/counts` | `{"{{subscriptionId}}":0}` | 200 |
| 3.10 | `delete_subscription: sin clínicas se elimina` | `DELETE …/{{subscriptionId}}` | — | 204; guarda `deletedSubscriptionId` |
| 3.11 | `sim: ver las llamadas recibidas por la simulación` | `GET …/__test__/calls` | — | 200; informativa (muestra qué preguntó la API) |
| 3.12 | `sim: dejar la simulación limpia al terminar` | `POST …/__test__/reset` | — | 200 (deja la simulación limpia) |

La descripción de la carpeta enumera cómo levantar la simulación, la lista de modos de `faults` y qué se
espera **sin** simulación ni API de clínicas: `clinics_count` `null` y eliminar 503 (FR-018).

## Variables de colección declaradas

Ver [../data-model.md](../data-model.md) § «Variables de colección declaradas». Los cuerpos y las rutas solo usan
variables de esa lista o del entorno.

## Cobertura de requisitos

| Requisito | Dónde |
|---|---|
| FR-001 (6 operaciones + docs) | 1.1–1.10 (las 6) y 0.2–0.3 |
| FR-002 (carpetas por propósito y orden) | 4 carpetas; regla D11 |
| FR-003 / FR-005 | `description` y `test` en cada petición; reglas D3 |
| FR-004 | 1.1, 2.1, 2.2, 3.2 guardan; el resto usa lo guardado y el script protege ([access-script.md](access-script.md)) |
| FR-013 (401, 403, 404, 409, 422, 503) | 2.3–2.18 (regla D2) |
| FR-014 (persona sin permiso opcional) | 2.5, 2.6 |
| FR-015 | descripción de la carpeta 2 |
| FR-016, FR-017, FR-018 | carpeta 3 |

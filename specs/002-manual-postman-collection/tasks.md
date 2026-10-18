---

description: "Task list for feature 002-manual-postman-collection (Colección de Postman para pruebas manuales)"
---

# Tasks: Colección de Postman para Probar a Mano la API de Sistema

**Input**: Design documents from `/specs/002-manual-postman-collection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.0.0**, la API de la spec 001 ya implementada, `uv` con Python 3.14 o superior, Docker Desktop
con Compose 2.24 o superior y Node.js con npm (solo para verificar con Newman 6.2.3, que ya está declarado en
`tests/postman/package.json`). **Esta feature no modifica `src/`, `alembic/` ni el esquema (FR-024).**

**Tests**: Incluidas. La spec exige una prueba de pytest de desfase y de secretos (FR-019, FR-020, historia 6), y
cada historia de la colección termina con una **tarea de verificación con Newman** contra la pila de la spec 001
y un Auth0 simulado (quickstart V9). Lo que Newman no puede comprobar (la aplicación de escritorio de Postman y un
tenant real de Auth0) se entrega como lista de verificación manual en la última tarea.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md). Las dos P1 (US1 acceso, US2
operaciones) forman el **MVP**; después las P2 (US3 errores, US4 entorno desplegado) y las P3 (US5 simulación de
clínicas, US6 desfase y secretos, US7 documentación).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US7); sin etiqueta en Setup, Foundational y Polish
- Todas las rutas son relativas a la raíz del repositorio. `<scratch>` es el directorio temporal de la sesión
  (**fuera del repositorio, no versionado**)

## Cómo se construye la colección (leer antes de empezar)

La colección es **un solo archivo JSON** y su fuente de verdad es ese JSON (research M14). Para no editar a mano
cientos de líneas de JSON con scripts escapados, se genera con un **generador desechable** en
`<scratch>/manual/build_manual_collection.py` (como en la spec 001): cada tarea de colección **añade** carpetas,
peticiones o fragmentos del script al generador y **vuelve a generar** el archivo. Por eso las tareas que tocan la
colección **no llevan [P]**: comparten un archivo. El generador y el material de verificación **no se versionan**.

Reglas de contenido para toda tarea de colección:

- Mensajes, descripciones y títulos de `pm.test` en **español**; nombres de archivos, variables, funciones y
  **comentarios del script y de Python en inglés** (Principio VII).
- Cada petición: `description` no vacía (qué hace, **qué permiso requiere** y **qué respuestas esperar**) y un
  evento `test` con `pm.test("…")` en español (FR-003, FR-005). Cada carpeta y la colección: `description`.
- Nombre de petición `<operationId>: <descripción>` (prefijos auxiliares: `docs`, `sim`); en `2. Casos de error` la
  descripción empieza por el estatus (`401 sin token`).
- Ningún token ni secreto en el JSON: la autenticación solo referencia `{{accessToken}}`, `{{plainToken}}` o
  `{{badToken}}`; los cuerpos y URL solo usan variables de [data-model.md](data-model.md).
- Formato del generador: escribe UTF-8, `ensure_ascii=False`, sangría de 2 espacios y salto de
  línea final; `exec` de los scripts es un arreglo de líneas.

## Referencias rápidas

- Decisiones y evidencia del prototipo: [research.md](research.md) (M1 a M15)
- Variables, entornos y estados: [data-model.md](data-model.md)
- Carpetas y peticiones (44): [contracts/collection-structure.md](contracts/collection-structure.md)
- Algoritmo, mensajes A-01…A-13 e invariantes del script: [contracts/access-script.md](contracts/access-script.md)
- Reglas D0–D11 de la prueba de desfase: [contracts/drift-test.md](contracts/drift-test.md)
- Validación por niveles (V1–V9): [quickstart.md](quickstart.md)
- Mensajes y códigos de error exactos de la API: `src/messages.py` y
  [`specs/001-subscriptions-api/contracts/error-catalog.md`](../001-subscriptions-api/contracts/error-catalog.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Línea base verde y herramientas desechables para construir y verificar la colección.

- [X] T001 Confirmar la línea base: `docker compose up -d db`, `uv run pytest -q` en verde y `git status --short` mostrando solo `specs/002-manual-postman-collection/`; comprobar que `tests/postman/node_modules/.bin/newman --version` da `6.2.3` (si falta, `npm ci --prefix tests/postman`). Anotar el número de pruebas para compararlo al final
- [X] T002 [P] Crear el generador desechable `<scratch>/manual/build_manual_collection.py` (Python, sin dependencias): funciones `request(name, method, url, *, description, body=None, auth=None, tests=(), headers=())`, `folder(name, description, items)`, `script(lines)` (arreglo `exec`), la constante `OUT` = `tests/postman/collections/MailySoft-System-Manual.postman_collection.json` y `write()` que serializa con UTF-8, `ensure_ascii=False`, `indent=2` y salto de línea final. Una URL se escribe como cadena `{{baseUrl}}/api/v1/…` y el generador la convierte al objeto `url` de v2.1 (`raw`, `host`, `path`, y `variable` solo si hace falta)
- [X] T003 [P] Crear el Auth0 simulado con TLS en `<scratch>/manual/harness/mock_auth0.py` (partir del prototipo de la investigación si existe en el directorio temporal; si no, recrearlo): `POST /oauth/token` (JSON) con certificado autofirmado generado con `openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj /CN=localhost`; comportamiento por `client_id`: `admin-app` → 200 con `access_token` fijo `manual-admin-token`; `plain-app` → 200 con `manual-plain-token`; sufijo `-short` → mismo token con `expires_in: 30`; secreto `wrong` → 401; `no-grant` → 403; `limit` → 429; `garbage` → 200 sin `access_token`; `notjson` → 200 con HTML; `expires_in` 86400 en el resto. Registrar en `/__log` cada llamada **sin** el secreto. Puerto 9443
- [X] T004 Crear `<scratch>/manual/harness/run.ps1` y `<scratch>/manual/harness/run_manual.mjs` (depende de T003): `run.ps1` levanta la pila `docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api` (API `127.0.0.1:8011`, simulación de usuarios `:8012`, de clínicas `:8013`), registra con `POST http://127.0.0.1:8012/__test__/tokens` el token `manual-admin-token` con `["subscriptions:read","subscriptions:write","subscriptions:update","subscriptions:delete"]` y `manual-plain-token` con `[]`, y arranca el Auth0 simulado; `run_manual.mjs` usa la API programática de `newman` (de `tests/postman/node_modules`) con `insecure: true`, carga la colección y el entorno local del repositorio, aplica `--env-var` equivalentes (`baseUrl=http://127.0.0.1:8011`, `auth0Domain=localhost:9443`, `auth0Audience=https://usuarios.test`, `auth0ClientId=admin-app`, `auth0ClientSecret=<cualquier texto>`, `clinicsStubUrl=http://127.0.0.1:8013`), permite elegir carpeta y sobrescribir variables por escenario, e imprime por petición: enviada u omitida, resultado de cada `pm.test` y los mensajes de consola

**Checkpoint**: se puede generar el JSON y ejecutarlo contra una pila real con un Auth0 simulado.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lo que bloquea a todas las historias: el apoyo compartido de las pruebas (y desbloquear la comprobación textual de
secretos que, si no, falla en cuanto exista un archivo manual), el entorno local y el esqueleto de la colección.

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase.

- [X] T005 [P] Crear `tests/contract/postman_support.py` (docstrings y comentarios en inglés): mover desde `tests/contract/test_postman_collection.py` las rutas `POSTMAN`, la colección de la spec 001 y las funciones `requests_of`, `prefix_of` y `operation_ids_of_the_api` (que usa `create_app().openapi()`), y la expresión `JWT_PATTERN`; añadir `MANUAL_COLLECTION` (`collections/MailySoft-System-Manual.postman_collection.json`), `MANUAL_ENVIRONMENTS` (`environments/manual-local.postman_environment.json` y `environments/manual-deployed-test.postman_environment.json`), `folders_of(items)`, `scripts_of(item, listen)` (texto de `exec` unido con saltos de línea), `BEARER_LITERAL_PATTERN` (`Bearer [A-Za-z0-9._~+/=-]{8,}`) y `HIGH_ENTROPY_PATTERN` (≥ 32 caracteres `[A-Za-z0-9_-]` sin espacios)
- [X] T006 Actualizar `tests/contract/test_postman_collection.py` (depende de T005): importar del módulo de apoyo en lugar de definir lo movido, y acotar `test_no_file_of_the_postman_folder_holds_a_token_or_a_secret` a los archivos de la spec 001: recorrer `tests/postman/` **excluyendo** `node_modules/`, `reports/`, `package-lock.json`, la colección `MailySoft-System-Manual.postman_collection.json` y los entornos `manual-*.postman_environment.json` (con un comentario que explique el motivo: los archivos manuales deben nombrar `auth0ClientSecret` y el tipo `secret`, y se vigilan por estructura en `test_manual_postman_collection.py`); conservar la aserción de que hay archivos que comprobar. `uv run pytest tests/contract/test_postman_collection.py -q` en verde, con las mismas pruebas que antes
- [X] T007 Crear `tests/postman/environments/manual-local.postman_environment.json` (depende de T006: la comprobación textual antigua rechazaría la palabra «secret» de este archivo) con exactamente la forma del entorno `dev` existente (`name`, `values[]` con `key`/`value`/`type`/`enabled: true`, `"_postman_variable_scope": "environment"`): `name` = `MailySoft System API - Manual - local (solo bases de datos de pruebas)`; las **nueve** variables de [data-model.md](data-model.md) en este orden: `baseUrl` = `http://127.0.0.1:8010` (`default`), `auth0Domain` = `""`, `auth0Audience` = `""`, `auth0ClientId` = `""`, `auth0ClientSecret` = `""` con `"type": "secret"`, `plainClientId` = `""`, `plainClientSecret` = `""` con `"type": "secret"`, `clinicsStubUrl` = `http://127.0.0.1:8001`, `testDatabaseNotice` = aviso en español (p. ej. «Este entorno debe apuntar SOLO a una base de datos dedicada a pruebas (en local, `maily_system_manual`; nunca la de desarrollo ni la de pytest), nunca a datos reales: la colección crea y elimina —de forma lógica— suscripciones.»). Ninguna otra variable; ningún valor de acceso relleno
- [X] T008 Generar el esqueleto de la colección en `tests/postman/collections/MailySoft-System-Manual.postman_collection.json` mediante el generador (depende de T002): `info.name` = `MailySoft System API - Manual`, `info.schema` = `https://schema.getpostman.com/json/collection/v2.1.0/collection.json`, `info.description` provisional (se completa en T011), `auth` = Bearer con `{{accessToken}}`, `variable` con las 16 variables de colección de [data-model.md](data-model.md) (`accessToken`, `accessTokenExpiresAt`, `accessTokenKey`, `plainToken`, `plainTokenExpiresAt`, `plainTokenKey`, `badToken`, `accessProblem`, `sessionApi`, `subscriptionId`, `subscriptionName`, `otherSubscriptionId`, `otherSubscriptionName`, `deletedSubscriptionId`, `newSuffix` con valor inicial **vacío**, y `nonexistentSubscriptionId` = `2147483647`), cada una con `description` breve, y `item` vacío. Comprobar que el JSON carga con `python -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))"` y que `uv run pytest tests/contract/test_postman_collection.py -q` sigue en verde

**Checkpoint**: Foundation lista: apoyo compartido, entorno local y esqueleto. Las historias pueden empezar.

---

## Phase 3: User Story 1 - Entrar sin pegar tokens (Priority: P1) 🎯 MVP

**Goal**: la colección pide, reutiliza y renueva sola el token de Auth0 y, si no puede, **no envía** la petición y
explica por qué en español.

**Independent Test**: con el Auth0 simulado, `list_subscriptions: comprobar el acceso…` responde 200 sin token pegado,
una segunda petición no vuelve a llamar a `/oauth/token`, y cada fallo (valor ausente, dominio mal escrito, Auth0 sin
respuesta, credenciales rechazadas, aplicación no autorizada, 429, respuesta inesperada) omite la petición con su mensaje.

### Implementation for User Story 1

- [X] T009 [US1] Escribir en el generador el **script de acceso** (evento `prerequest` de la colección) según [contracts/access-script.md](contracts/access-script.md), partes de esta historia: constantes `SAFETY_MARGIN_MS = 60 * 1000` y `DEFAULT_LIFETIME_SECONDS = 86400`; tabla de identidades (`accessToken` ← `auth0ClientId`/`auth0ClientSecret`; `plainToken` ← `plainClientId`/`plainClientSecret`, opcional); `finish(problem)` (`console.error("[Colección manual] " + problem)`, `accessProblem` y `pm.execution.skipRequest()`; sin problema borra `accessProblem`); detección de identidad con `pm.request.auth` (hereda → `accessToken`; `noauth` → ninguna; Bearer `{{plainToken}}`/`{{badToken}}`; otra → ninguna); `badToken` = `invalid-` + aleatorio sin llamar a Auth0; `ensureToken(name, who, done)` **con callbacks de `pm.sendRequest`** (sin `await`, sin `require`) que implementa A-01 a A-08 con los textos exactos del contrato, valida el dominio con `/[\/:]/.test(domain.replace(/:\d+$/, ""))`, reutiliza el token si coincide la clave `dominio|audience|clientId` y quedan **más de 60 s**, y guarda `…`, `…ExpiresAt` (milisegundos) y `…Key`; `POST https://{auth0Domain}/oauth/token` con JSON `{grant_type:"client_credentials", client_id, client_secret, audience}`. Invariante I1: ninguna llamada a `console.*` menciona el secreto ni el token (solo nombres de variables y el mensaje)
- [X] T010 [US1] Añadir al generador la carpeta `0. Empezar` (con `description`: es lo primero que se envía; los pasos 1 a 4 de [quickstart.md](quickstart.md) V2) y su primera petición `list_subscriptions: comprobar el acceso y ver el catálogo` (`GET {{baseUrl}}/api/v1/subscriptions`, hereda autenticación) según la fila 0.1 de [contracts/collection-structure.md](contracts/collection-structure.md): `description` con el permiso `subscriptions:read`, el significado de 200/401/403/503 y «si pulsas Enviar y no pasa nada, abre la Consola de Postman»; pruebas en español: «responde 200», «es un arreglo», «cada suscripción trae los campos del contrato» (`id`, `name`, `monthly_price` como cadena, `features` arreglo, `status` con `id` y `name`, `clinics_count` número o `null`); regenerar
- [X] T011 [US1] Redactar `info.description` de la colección en el generador (español, Markdown): abre con «Si pulsas Enviar y no pasa nada, abre la Consola de Postman (Ver → Mostrar Consola de Postman): ahí se explica por qué no se envió la petición»; resume los pasos de arranque (importar, elegir entorno, rellenar `auth0Domain` sin `https://`, `auth0Audience`, `auth0ClientId` y `auth0ClientSecret` **solo en la copia local**, enviar la primera petición); lista los requisitos previos de FR-023 (Auth0, `sub` registrado, rol con los cuatro permisos; aviso de que `bootstrap_admin.sql` solo concede al Administrator los 12 de usuarios, roles y permisos); advierte de que la colección solo debe apuntar a una base de datos dedicada a pruebas (en local, `maily_system_manual`, nunca la de desarrollo `maily_system` ni la de pytest), de no escribir el secreto en un valor que se sincronice y de no compartir capturas de la Consola (Postman registra la petición a Auth0, cuerpo incluido); regenerar
- [X] T012 [US1] Verificar con el material desechable (T004) los escenarios de acceso sobre la **colección real** y anotar los resultados: (a) 3 peticiones seguidas → 1 sola llamada a `/oauth/token` y las 3 con el mismo token; (b) `auth0ClientId=admin-app-short` → una llamada por petición; (c) cada fallo omite la petición y la consola muestra el mensaje exacto: `auth0Audience` vacío y secreto vacío (A-01, nombrando ambas), `auth0Domain=https://localhost:9443` (A-02), `auth0Domain=localhost:9` (A-03), secreto `wrong` (A-04), `no-grant` (A-05), `limit` (A-06), `garbage` y `notjson` (A-07); (d) 0 peticiones llegan a la API en (c); (e) ninguna línea de consola contiene el secreto ni el token. Si algo falla, corregir T009 y repetir

**Checkpoint**: US1 funcional y comprobada con Newman. (La Consola y la presentación de una petición omitida en la aplicación de Postman se verifican a mano: tarea final.)

---

## Phase 4: User Story 2 - Recorrer las operaciones con datos de ejemplo (Priority: P1) 🎯 MVP

**Goal**: ciclo de vida completo (crear → consultar → listar → actualizar → cambiar estatus → eliminar → comprobar) sin
editar nada, más la documentación pública, y **sin tocar nunca datos que no creó la colección**.

**Independent Test**: carpetas `0.` y `1.` enteras en verde contra la pila de la spec 001; «Eliminar» o «Actualizar» enviados antes de crear nada no
salen y lo explican; con un identificador guardado que ahora pertenece a otra suscripción, la modificación no sale.

### Implementation for User Story 2

- [X] T013 [US2] Ampliar el script de acceso en el generador con las protecciones de esta historia, en el orden de [contracts/access-script.md](contracts/access-script.md): (1) **descartar datos de otra API**: si `sessionApi` ≠ `baseUrl`, `unset` de `subscriptionId`, `subscriptionName`, `otherSubscriptionId`, `otherSubscriptionName` y `deletedSubscriptionId`, y guardar `sessionApi`; (3) **`newSuffix`**: si la URL o el cuerpo contienen `{{newSuffix}}`, generar `Date.now().toString(36)` + 4 caracteres aleatorios y guardarlo; **toda `{{variable}}` (`\w+`, las `{{$…}}` no cuentan) de la URL y del cuerpo en bruto debe tener valor**, si no, A-09 con las pistas de `subscriptionId` («Esta petición actúa solo sobre la suscripción que crea la colección: envía primero «create_subscription: crear la suscripción de prueba»»), `otherSubscriptionId` («…«create_subscription: crear otra suscripción para el choque de nombres»»), `deletedSubscriptionId` («Elimina primero la suscripción de la carpeta 1»), `baseUrl` («Elige un entorno y rellena baseUrl») y `clinicsStubUrl` («Esta carpeta solo funciona en local, con la simulación de clínicas levantada en http://127.0.0.1:8001; en el entorno desplegado no se usa»); (5) **propiedad**: antes de un `PATCH`/`PUT`/`DELETE` con `{{subscriptionId}}` u `{{otherSubscriptionId}}` en la URL, `GET {baseUrl}/api/v1/subscriptions/{id}` con el token principal (callbacks) y omitir con A-10 (404), A-11 (otro estatus o la API no responde), A-12 (**no hay nombre guardado**, mensaje propio) o A-13 (nombre distinto); nombrar en los mensajes las peticiones que crean (`create_subscription: crear la suscripción de prueba` / `create_subscription: crear otra suscripción para el choque de nombres`, que deben existir con ese nombre exacto); esos nombres se guardan como **literales completos** `create_subscription: …` en la tabla `OWNED` (campo `creator`) y en las pistas de A-09, para que la regla D8 los vea
- [X] T014 [US2] Añadir a `0. Empezar` las dos peticiones de documentación pública (`docs: contrato OpenAPI`, `GET {{baseUrl}}/openapi.json`, y `docs: documentación interactiva`, `GET {{baseUrl}}/docs`), ambas con autenticación `noauth`, `description` («es pública, no pide token») y pruebas: 200 sin token, `openapi` presente y las rutas `/api/v1/subscriptions` y `/api/v1/subscriptions/{subscription_id}` (la primera); 200 y contenido HTML (la segunda). Regenerar
- [X] T015 [US2] Crear la carpeta `1. Ciclo de vida de una suscripción` (con su `description`: se recorre en orden; solo actúa sobre lo que crea) y añadir las peticiones 1.1 a 1.5 de [contracts/collection-structure.md](contracts/collection-structure.md): `create_subscription: crear la suscripción de prueba` (cuerpo `{"name":"Prueba manual {{newSuffix}}","description":"Creada desde la colección manual.","monthly_price":4500,"features":["Hasta 5 consultorios","Usuarios ilimitados"]}`; pruebas: 201, estatus `{id:1,name:"Activa"}`, `monthly_price` `"4500.00"`, `clinics_count` 0; **guarda** `subscriptionId` y `subscriptionName`), `get_subscription: consultar la suscripción creada` (200, mismo `id`, `clinics_count` número o `null` con título que explique el `null`), `list_subscriptions: la suscripción creada aparece en el catálogo`, `update_subscription: cambiar el precio y las funciones` (`{"monthly_price":4700,"features":["Hasta 8 consultorios"]}` → 200, `"4700.00"`) y `update_subscription: cambiar el nombre` (`{"name":"{{subscriptionName}} renombrada"}` → 200; actualiza `subscriptionName`). Cada una con descripción (qué hace, permiso `subscriptions:read`/`write`/`update`, respuestas esperadas). Regenerar
- [X] T016 [US2] Añadir a la carpeta 1 las peticiones 1.6 a 1.10: `change_subscription_status: pasar a Inactiva` (`{"status_id":2}`), `…pasar a Bloqueada` (`3`), `…volver a Activa` (`1`), cada una con 200 y `status` `{id,name}` esperado (`Inactiva`, `Bloqueada`, `Activa`); `delete_subscription: eliminar la suscripción de prueba` (`DELETE …/{{subscriptionId}}`) que **acepta 204, 409 y 503** con un `pm.test` de título distinto para cada caso («se eliminó (204)», «tiene clínicas asignadas (409)», «no se pudo comprobar el API de clínicas (503): es lo esperado sin API de clínicas ni simulación»), guardando `deletedSubscriptionId` solo con 204; y `get_subscription: la eliminada ya no se encuentra` (si `deletedSubscriptionId` es igual a `subscriptionId`, el borrado se hizo y espera 404 `subscription_not_found`; si no, la suscripción sigue existiendo y espera 200 con el título que lo explica). Regenerar
- [X] T017 [US2] Verificar con el material desechable (T004), sobre la colección real, y anotar: (a) carpetas `0.` y `1.` completas en verde contra la pila (borrado 204 con la simulación de clínicas sin conteos); (b) repetir la carpeta 1 dos veces seguidas sin chocar de nombre; (c) con `docker compose -p maily-system-e2e … stop clinics-api-stub` el borrado da 503 y **sus pruebas pasan** con el título del 503 y la `1.10` explica que la suscripción sigue existiendo (volver a levantarla después); (d) con las variables de sesión vacías, `update_subscription`, `change_subscription_status` y `delete_subscription` **no salen** (A-09) y no llega ninguna petición a la API; (e) fijar `subscriptionId` a una suscripción creada aparte con **otro nombre**: `PATCH` y `DELETE` no salen (A-13) y esa suscripción queda intacta; con `subscriptionId` de una inexistente: A-10; sin `subscriptionName`: A-12; (f) un cuerpo con `{{subscriptionName}}` vacío no llega a la API; (g) cambiar `baseUrl` entre dos peticiones descarta los datos guardados. Corregir T013 a T016 si algo falla

**Checkpoint**: US1 y US2 completas = **MVP**: se obtiene el token solo y se recorre el ciclo de vida con garantías.

---

## Phase 5: User Story 3 - Provocar y entender los errores clave (Priority: P2)

**Goal**: casos preparados para 401, 403, 404, 409, 422 y 503, cada uno con estatus, código y mensaje en español comprobados y
con una descripción que explique causa y arreglo.

**Independent Test**: la carpeta `2.` entera en verde; sin segunda aplicación configurada los casos 403 se omiten (no fallan); al repetirla no choca consigo misma.

### Implementation for User Story 3

- [X] T018 [US3] Crear la carpeta `2. Casos de error` (su `description` explica, **sin provocarlos**, el 503 por permiso no verificable —`authorization_unavailable`, el API de usuarios no responde— y el 403 generalizado —la persona no está registrada en el API de usuarios o su rol no tiene los cuatro permisos de suscripciones—, FR-015; y que cada caso provoca un error a propósito) y añadir 2.1 y 2.2 (`create_subscription: crear la suscripción para los casos de error` y `…crear otra suscripción para el choque de nombres`, con el nombre `Prueba manual otra {{newSuffix}}` la segunda; 201; guardan `subscriptionId`/`subscriptionName` y `otherSubscriptionId`/`otherSubscriptionName`) y los casos de acceso 2.3 a 2.6: `list_subscriptions: 401 sin token` (`noauth`; 401, `code` `unauthenticated`, mensaje «Debe iniciar sesión para usar esta operación.»), `list_subscriptions: 401 token inválido` (Bearer `{{badToken}}`; 401, `invalid_token`, «El token de acceso no es válido.»), `list_subscriptions: 403 persona sin permiso` y `create_subscription: 403 persona sin permiso no crea nada` (Bearer `{{plainToken}}`; 403, `permission_denied`, mensaje con «Permiso requerido: subscriptions:read.» / «…subscriptions:write.»; su descripción explica que usan la segunda aplicación **opcional** y qué pasa si no está configurada, FR-014). Regenerar
- [X] T019 [US3] Añadir 2.7 a 2.11: `get_subscription: 404 identificador inexistente` (`{{nonexistentSubscriptionId}}`; 404, `subscription_not_found`, mensaje con el identificador), `get_subscription: 404 suscripción eliminada` (`{{deletedSubscriptionId}}`; solo `GET`; su descripción avisa de que requiere haber eliminado una en la carpeta 1), `create_subscription: 409 nombre repetido` (nombre `{{subscriptionName}}`; 409, `subscription_name_already_exists`, «Ya existe una suscripción con el nombre «…».»), `update_subscription: 409 nombre de otra suscripción` (`PATCH …/{{otherSubscriptionId}}`, `{"name":"{{subscriptionName}}"}`; 409) y `change_subscription_status: 409 estatus repetido` (`PATCH …/{{subscriptionId}}/status`, `{"status_id":1}`; 409, `subscription_status_unchanged`). Regenerar
- [X] T020 [US3] Añadir 2.12 a 2.17 (422, `code` `validation_error`, `errors[]` con `field` y el **mensaje literal** tomado de `src/messages.py`/error-catalog, comprobando antes la respuesta real con el material desechable): `create_subscription: 422 nombre ausente`, `…422 precio negativo` (`monthly_price: -1`), `…422 precio con tres decimales` (`"10.125"`), `…422 lista de funciones nula` (`features: null`), `update_subscription: 422 campo no permitido` (`{"status":2}` → «El campo «status» no está permitido.») y `change_subscription_status: 422 estatus no permitido` (`{"status_id":4}`, campo `status_id`). Las cuatro de crear no crean nada. Regenerar
- [X] T021 [US3] Añadir 2.18 y 2.19: `delete_subscription: 503 no se puede comprobar el API de clínicas` (`DELETE …/{{subscriptionId}}`; **esperado 503** `clinics_check_unavailable`, «No se pudo comprobar si la suscripción con el identificador … tiene clínicas asignadas. No se eliminó; inténtelo de nuevo más tarde.»; si la simulación de clínicas responde, 204 o 409 con título que lo explique y sin marcarlo como fallo; la descripción dice que para ver el 503 hay que apagar la simulación o usar la carpeta 3) y `delete_subscription: limpiar la otra suscripción` (`…/{{otherSubscriptionId}}`; 204, o 503 explicado). Regenerar
- [X] T022 [US3] Verificar con el material desechable y anotar: (a) la carpeta `2.` en verde con el cliente `plain-app` configurado como segunda aplicación (`plainClientId=plain-app`, `plainClientSecret` cualquiera); (b) sin segunda aplicación, 2.5 y 2.6 se omiten con A-08 y el resto pasa; (c) 2.8 se omite si todavía no hay `deletedSubscriptionId` (A-09) y pasa tras la carpeta 1; (d) 2.18 da 503 con la simulación de clínicas apagada y 204 con ella encendida, sin fallos; (e) los seis estatus 401/403/404/409/422/503 aparecen al menos una vez; (f) repetir la carpeta no choca. Corregir T018 a T021 si algo falla

**Checkpoint**: US1, US2 y US3 funcionan.

---

## Phase 6: User Story 4 - Usar la colección en un entorno desplegado de pruebas (Priority: P2)

**Goal**: el mismo material sin editar ninguna petición contra un segundo entorno, con la advertencia de bases de datos de pruebas, y sin tocar datos preexistentes.

**Independent Test**: importar `manual-deployed-test` y recorrer `0.` y `1.` rellenando solo `baseUrl` y los valores de acceso; una suscripción preexistente del entorno queda intacta.

### Implementation for User Story 4

- [X] T023 [P] [US4] Crear `tests/postman/environments/manual-deployed-test.postman_environment.json` con **las mismas nueve claves y orden** que el local (T007): `name` = `MailySoft System API - Manual - desplegado de pruebas (solo bases de datos de pruebas)`; `baseUrl` = `""` y `clinicsStubUrl` = `""` (la simulación no existe allí); `auth0*` y `plain*` = `""`; `auth0ClientSecret` y `plainClientSecret` de tipo `secret` y valor `""`; `testDatabaseNotice` con un aviso más enérgico («NO apuntes este entorno a una base de datos con datos reales: la colección crea y elimina suscripciones. Debe ser una base de pruebas dedicada.»)
- [X] T024 [US4] Añadir al generador, en la `description` de la colección (T011) y en la de las carpetas 1 y 3, la guía del entorno desplegado: cómo cambiar de entorno (solo elegirlo y rellenar sus valores; 0 ediciones en las peticiones), que el token y los datos de la sesión no se reutilizan al cambiar (el token cambia de clave; los datos se descartan si cambia `baseUrl`), que la carpeta 3 no funciona allí y se omite sin fallar, y la advertencia de bases de datos de pruebas; regenerar
- [X] T025 [US4] Verificar con el material desechable y anotar: (a) **SC-006**: crear aparte, con el token del Auth0 simulado, dos suscripciones «preexistentes» (nombres que no empiezan por `Prueba manual`) y ejecutar las carpetas `1.` y `2.`; después listar y confirmar que las dos **siguen idénticas** (nombre, precio, estatus); (b) cambio de entorno a mitad de sesión (sobrescribir `auth0Audience`, y por separado `baseUrl` a `http://localhost:8011`): la petición siguiente pide un token nuevo y las modificaciones no salen hasta crear de nuevo (A-09), sin reutilizar el token ni los identificadores anteriores; (c) el entorno desplegado con valores equivalentes recorre `0.` y `1.` sin editar ninguna petición. Corregir T013/T024 si algo falla

**Checkpoint**: US4 completa.

---

## Phase 7: User Story 5 - Probar las clínicas con la simulación local (Priority: P3)

**Goal**: carpeta opcional para fijar conteos, provocar fallos y reiniciar la simulación de clínicas; se omite sola si no hay `clinicsStubUrl`.

**Independent Test**: con la simulación en marcha, 3 clínicas → conteo 3 → eliminar rechazado (409) → fallo provocado → conteo `null` y 503 → 0 clínicas → eliminar 204; con `clinicsStubUrl` vacío ninguna petición sale.

### Implementation for User Story 5

- [X] T026 [US5] Añadir la carpeta `3. Simulación de clínicas (solo local)` con las peticiones 3.1 a 3.12 de [contracts/collection-structure.md](contracts/collection-structure.md): las `sim` (`POST {{clinicsStubUrl}}/__test__/reset`, `…/__test__/counts` con `{"{{subscriptionId}}":3}` y `{"{{subscriptionId}}":0}`, `…/__test__/faults` con `{"mode":"unavailable","count":3}` (la consulta de 3.7, la comprobación previa de propiedad y la propia eliminación), `GET …/__test__/calls`, y un segundo reinicio al final, que se llama `sim: dejar la simulación limpia al terminar` porque los nombres no pueden repetirse, D10) con autenticación **`noauth`**, y las de la API (`create_subscription: crear la suscripción para la simulación`, `get_subscription` con conteo 3, `delete_subscription` rechazado 409 `subscription_has_clinics`, `get_subscription` con `clinics_count` `null` y 200, `delete_subscription` 503 `clinics_check_unavailable`, `delete_subscription` 204 guardando `deletedSubscriptionId`). La `description` de la carpeta explica: es **opcional y solo local**; cómo levantar la simulación (`uv run uvicorn app:app --app-dir tests/stubs/clinics_api --port 8001`); que `counts` **reemplaza todos los conteos**; la lista de los diez modos de `faults` de `tests/stubs/clinics_api/app.py` (`unavailable`, `unauthorized`, `forbidden`, `malformed`, `negative_count`, `unrequested_id`, `duplicate_id`, `not_json`, `redirect`, `slow`); que sin simulación ni API de clínicas el comportamiento esperado es `clinics_count` `null` y eliminar 503 (FR-018); y que en el entorno desplegado se omite sola (FR-017). Regenerar
- [X] T027 [US5] Verificar con el material desechable y anotar: (a) la carpeta `3.` entera en verde con `clinicsStubUrl=http://127.0.0.1:8013` (la simulación de la pila); (b) con `clinicsStubUrl` vacío las 12 peticiones se omiten y no llega nada a la API ni a la simulación: las 6 `sim` (pista A-09 de `clinicsStubUrl`) y la creación (script de la carpeta, mismo texto) dicen que la carpeta solo funciona en local, y las 5 que dependen de la creación piden crear primero; (c) arrancar de verdad la simulación autónoma con el comando de la descripción en el puerto 8001 (comprobar que responde en `/__test__/calls` y detenerla); (d) sin simulación (`clinicsStubUrl` a un puerto cerrado) la colección explica el `null`/503 esperado. Corregir T026 si algo falla

**Checkpoint**: US5 completa; la colección tiene sus 44 peticiones.

---

## Phase 8: User Story 6 - Detectar que la colección se quedó atrás de la API (Priority: P3)

**Goal**: una prueba de la suite normal (solo lee archivos y el OpenAPI generado) que falla nombrando operaciones que falten o sobren y cualquier secreto en los archivos manuales.

**Independent Test**: quitar una petición de la colección o poner un valor en `auth0ClientSecret` hace fallar la prueba y la nombra; restaurar la hace pasar; corre sin servicio, Node ni Postman.

### Tests for User Story 6

- [X] T028 [US6] Crear `tests/contract/test_manual_postman_collection.py` (docstring y comentarios en inglés; importa de `tests/contract/postman_support.py`) con las reglas **de estructura y cobertura** de [contracts/drift-test.md](contracts/drift-test.md) como funciones puras `check_*(collection, environments) -> list[str]` (devuelven los problemas, vacío si todo bien) y una prueba por regla sobre los archivos reales: D0 (JSON válido, `info.schema` v2.1.0, `_postman_variable_scope`), D1 (operaciones ↔ prefijos, **ambos sentidos**, sin `docs` ni `sim`; el mensaje nombra «operaciones sin petición» y «peticiones de operaciones que la API no tiene»), D2 (cada operación en la carpeta `1.` y cada estatus de {401, 403, 404, 409, 422, 503} en la `2.`), D3 (descripciones y `pm.test` no vacíos), D10 (nombres `<prefijo>: <descripción>` bien formados y sin repetir) y D11 (orden que funciona dentro de cada carpeta)
- [X] T029 [US6] Añadir a `tests/contract/test_manual_postman_collection.py` (mismo archivo, tras T028) las reglas **de acceso, secretos y entornos**: D4 (existe el *pre-request* de acceso con `skipRequest` y `/oauth/token`; autenticación de colección Bearer `{{accessToken}}`; cada petición hereda, es `noauth` o Bearer exactamente `{{plainToken}}`/`{{badToken}}`), D5 (en los entornos, toda variable `secret` y las de acceso `auth0Domain`, `auth0Audience`, `auth0ClientId`, `auth0ClientSecret`, `plainClientId`, `plainClientSecret` con `value: ""`, y las dos secretas de tipo `secret`; en la colección, toda variable cuyo nombre contenga `token`, `secret` o `password` con valor vacío; ningún JWT en ninguna cadena; ningún `Bearer <literal>` en cabeceras ni bloques `auth`; ningún valor de variable que parezca una clave; el mensaje nombra **archivo y variable**), D5b (ninguna línea con `console.` en los scripts menciona `secret`, `access_token`, `accessToken` ni `plainToken`, sin distinguir mayúsculas), D6 (mismas nueve claves en los dos entornos, ninguna igual a una variable de colección, valores locales `http://127.0.0.1:8010` y `http://127.0.0.1:8001`, desplegado con `baseUrl` y `clinicsStubUrl` vacíos, `testDatabaseNotice` no vacía, nombre con «bases de datos de pruebas») y D9 (independencia: sin `usersStubUrl`, sin prefijo `setup:`, nombre de colección distinto del de la spec 001)
- [X] T030 [US6] Añadir al mismo archivo (tras T029) las reglas **de seguridad de datos y de mensajes**: D7 (todo `PATCH`/`PUT`/`DELETE` usa en su ruta solo `{{subscriptionId}}` u `{{otherSubscriptionId}}`; `{{deletedSubscriptionId}}` y `{{nonexistentSubscriptionId}}` solo en `GET`; ninguna ruta con identificador numérico literal; las `sim` son `GET`/`POST` con URL que empieza por `{{clinicsStubUrl}}/__test__/`) y D8 (todo **fragmento del texto** del script que empiece por un `operationId` de la API seguido de `: ` y llegue hasta la siguiente comilla o «»» es el nombre exacto de una petición de la colección; incluye tanto los `creator` de la tabla `OWNED` (literales completos) como las citas dentro de las pistas de A-09)
- [X] T031 [US6] Añadir a `tests/contract/test_manual_postman_collection.py` los **casos negativos del propio detector** sobre copias en memoria (`copy.deepcopy`, sin tocar disco), cada uno comprobando que la regla correspondiente devuelve el problema esperado y que el mensaje **nombra** lo que falla: quitar todas las peticiones `delete_subscription` → D1; añadir una petición con prefijo inexistente → D1/D10; quitar el caso 409 → D2; poner un valor en `auth0ClientSecret` del entorno local → D5 (nombra el archivo y la variable); poner un JWT de ejemplo (`eyJhbGciOiJIUzI1NiJ9.e30.xxx`) en una cabecera → D5; quitar `testDatabaseNotice` de un entorno → D6; cambiar el Bearer de una petición a un literal → D4; usar `{{deletedSubscriptionId}}` en un `DELETE` → D7; renombrar `create_subscription: crear la suscripción de prueba` (citada por `OWNED` y por las pistas de A-09) → D8; mover una petición con `{{subscriptionId}}` antes de la que crea → D11
- [X] T032 [US6] Ejecutar `uv run pytest tests/contract/test_manual_postman_collection.py tests/contract/test_postman_collection.py -q` (todo en verde) y la **comprobación de que la guarda muerde** del quickstart V1 sobre los archivos reales: borrar temporalmente de la colección todas las `delete_subscription` y ver D1 fallar nombrándolas; escribir un valor temporal en `auth0ClientSecret` de `manual-local` y ver D5 fallar nombrando archivo y variable; **revertir ambos** y confirmar con `git status --short` que solo quedan los cambios previstos. Si una regla da falsos positivos, corregir la regla o el contenido, no relajar la regla

**Checkpoint**: US6 completa; la suite protege la colección.

---

## Phase 9: User Story 7 - Ponerse en marcha siguiendo solo la documentación (Priority: P3)

**Goal**: una persona que no participó puede importar, preparar su acceso y enviar la primera petición solo con el README y las descripciones.

**Independent Test**: seguir el README desde cero y obtener 200 del catálogo; encontrar la causa de un 403 generalizado.

### Implementation for User Story 7

- [X] T033 [P] [US7] Añadir a `README.md` la sección «Colección manual de Postman» (español; junto a «Pruebas de punta a punta (Postman)»): qué es y qué no es (manual, independiente de la de Newman, sin cuenta de Postman, solo habla con Auth0 y la API); **Requisitos previos** de FR-023 (aplicación M2M autorizada para el *audience* del API de usuarios; su `sub` terminado en `@clients` registrado como usuario; rol con `subscriptions:read`, `write`, `update` y `delete`, con un ejemplo SQL **tomado y comprobado** de `C:\maily\code\mailySoft-usuarios\project-definition\bootstrap_admin.sql` y de su `create_database.sql` —sin credenciales—, y la aclaración de que ese script solo asocia al Administrator los 12 permisos de usuarios, roles y permisos; segunda aplicación opcional sin permisos, apartado «Persona sin permisos»); **Pasos** (importar colección y entorno, elegir entorno, rellenar `auth0Domain` sin `https://`, `auth0Audience`, `auth0ClientId` y `auth0ClientSecret` solo en la copia local, enviar `0.`); **Base de datos dedicada a las pruebas manuales** (constitución: una base dedicada a pruebas, nunca la de desarrollo `maily_system` ni la de pytest `maily_system_test`, que pytest borra y recrea): crearla una vez con `docker compose exec db psql -U postgres -c "CREATE DATABASE maily_system_manual"` (el script de inicio de `docker/postgres/init/` solo corre al crear el volumen, por eso no se usa), y en la terminal donde se arranca la API fijar `$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/maily_system_manual"`, aplicar `uv run alembic upgrade head` (Alembic y uvicorn leen `DATABASE_URL` del entorno antes que del `.env`); **ejecutar estos comandos de verdad contra el contenedor `db` antes de dar la sección por buena** (comprobar que `maily_system` queda intacta); **Levantar en local** (la API en `http://127.0.0.1:8010` con `uv run uvicorn src.main:app --port 8010` en esa misma terminal —no con `docker compose up api`, que usa `maily_system`—, el API de usuarios en `http://localhost:8000`, el `.env` con `USERS_API_BASE_URL` y `CLINICS_API_BASE_URL`, y la simulación de clínicas con `uv run uvicorn app:app --app-dir tests/stubs/clinics_api --port 8001`); **Entorno desplegado de pruebas**; **Qué hacer si no pasa nada al pulsar Enviar** (abrir la Consola de Postman) con una **tabla de los mensajes A-01 a A-13** y su arreglo, el caso «todas las respuestas son 403» y «todo responde 503 `authorization_unavailable`»; y **Advertencias** (solo bases de datos de pruebas; el secreto nunca en un valor que se sincronice; la Consola de Postman registra la petición a Auth0, no compartas capturas; el borrado es lógico y deja filas «Eliminada»)
- [X] T034 [US7] Actualizar el resto del `README.md` (tras T033): en «Pruebas de punta a punta», sustituir la viñeta «Si la API cambia» por la regla de FR-021 —toda feature que añada, quite o cambie operaciones actualiza **las dos colecciones** en el mismo cambio— nombrando `tests/contract/test_postman_collection.py` y `tests/contract/test_manual_postman_collection.py` (ambas parte de `uv run pytest`); en el árbol «Estructura», describir `tests/postman/` como «colección y entornos de las pruebas de punta a punta (Newman) y de la colección manual» y añadir `tests/contract/postman_support.py`; sin tocar el resto

**Checkpoint**: US7 completa; el README es la puerta de entrada.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Cierre y evidencia de que nada se rompió ni se filtró.

- [X] T035 Ejecutar la **suite completa** (`docker compose up -d db` y `uv run pytest -q`) y confirmar que todas las pruebas previas siguen en verde y que el recuento solo aumentó con las pruebas nuevas; ejecutar la colección **de punta a punta de la spec 001** con su comando (`npm run e2e --prefix tests/postman` contra su pila) para confirmar que sigue pasando intacta
- [X] T036 Higiene y secretos del cambio: `git status --short` debe mostrar **solo** `specs/002-manual-postman-collection/`, `tests/postman/collections/MailySoft-System-Manual.postman_collection.json`, `tests/postman/environments/manual-*.postman_environment.json`, `tests/contract/postman_support.py`, `tests/contract/test_manual_postman_collection.py`, `tests/contract/test_postman_collection.py` y `README.md`; `git diff --stat` **vacío** para `src/`, `alembic/`, la colección `MailySoft-System-Suscripciones.postman_collection.json` y los entornos `e2e`/`dev`; buscar en los archivos nuevos cadenas tipo JWT (`eyJ`), `client_secret` con valor, el texto `manual-admin-token`/`manual-plain-token` y cualquier certificado: no debe haber ninguno; confirmar que `tests/postman/reports/` sigue sin versionarse
- [X] T037 Desmontar el material desechable: detener el Auth0 simulado, `docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v`, borrar `cert.pem`/`key.pem` y confirmar que no queda nada del harness dentro del repositorio
- [X] T038 Informar a la persona dueña del resultado y **entregarle la lista de verificación manual** que solo puede hacerse en la aplicación de escritorio de Postman y con su tenant de Auth0: quickstart V2 (importar y primera petición, SC-001), V3 (cada fallo de acceso: sin respuesta, mensaje en la Consola, ni el secreto ni el token en ella; en el *Collection Runner* la petición aparece omitida, no fallida; 401/403 reales de Auth0), V7 (entorno desplegado) y V8 (cambio de entorno y base reiniciada); más la revisión por una persona ajena a la feature que solo siga el README (SC-009). Incluir los resultados de las tareas T012, T017, T022, T025 y T027, y recordar la recomendación de enmendar la constitución (PATCH) para nombrar las colecciones manuales

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias; T002 y T003 en paralelo, T004 después de T003.
- **Foundational (Phase 2)**: depende de Setup (T008 necesita T002). T005 puede ir en paralelo con los de Setup; T006 va después de T005 y **antes** de T007 y T008, porque
  en cuanto existe un archivo manual la comprobación textual antigua de «secret» fallaría.
  **Bloquea todas las historias**.
- **User Stories (Phase 3+)**: todas dependen de Foundational. **Comparten el archivo de la colección y el generador**, así que las tareas de colección
  se hacen en este orden: US1 → US2 → US3 → US5 (y US4 en cualquier punto después de US2). US6 necesita la colección completa (US1 a US5) y los dos entornos (US4). US7 puede empezar tras US1 y conviene cerrarla al final.
- **Polish (Phase 10)**: depende de todas las historias.

### User Story Dependencies

- **US1 (P1)**: tras Foundational. Sin dependencias de otras historias. Entrega el script de acceso.
- **US2 (P1)**: tras US1 (usa el script y la carpeta `0.`). Amplía el script con las protecciones de datos.
- **US3 (P2)**: tras US2 (usa `subscriptionId`, `deletedSubscriptionId` y las protecciones).
- **US4 (P2)**: el entorno (T023) es independiente; su verificación necesita US2. Puede hacerse en paralelo con US3 y US5 salvo T024/T025, que tocan el generador.
- **US5 (P3)**: tras US2. Independiente de US3.
- **US6 (P3)**: tras US1–US5 (la colección debe estar completa) y T023.
- **US7 (P3)**: el contenido es independiente, pero describe lo construido; T033 es [P] con US6 (archivos distintos).

### Within Each User Story

- Script antes que peticiones que dependen de él; peticiones antes de la verificación con Newman.
- Cada verificación (T012, T017, T022, T025, T027) **debe pasar antes de seguir**; si falla, se corrige la tarea que la causó.
- Pruebas de pytest: reglas (T028–T030), luego sus casos negativos (T031), luego ejecución (T032).

### Parallel Opportunities

- Setup: T002 ‖ T003.
- Foundational: T005 ‖ Setup (T002, T003); T006, T007 y T008 en ese orden.
- US4: T023 (entorno) ‖ cualquier tarea del generador.
- US6 ‖ US7: T033 (README) mientras se escriben T028–T031 (otro archivo).
- Las tareas que tocan `tests/contract/test_manual_postman_collection.py` (T028–T031) y las que tocan el generador/colección **no** son paralelas entre sí.

---

## Parallel Example: Setup y Foundational

```bash
# Setup: el generador y el Auth0 simulado no se tocan entre sí
Task: "T002 Crear el generador desechable <scratch>/manual/build_manual_collection.py"
Task: "T003 Crear el Auth0 simulado con TLS <scratch>/manual/harness/mock_auth0.py"

# Foundational: el apoyo de pruebas no depende del generador ni del Auth0 simulado
Task: "T005 Crear tests/contract/postman_support.py"
Task: "T002 Crear el generador desechable"   # (de Setup, otro archivo)
```

## Parallel Example: US6 y US7

```bash
# Con la colección ya completa
Task: "T028 … T031 tests/contract/test_manual_postman_collection.py"   # una sola persona: mismo archivo
Task: "T033 README.md sección «Colección manual de Postman»"            # en paralelo: otro archivo
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Setup + Foundational (T001–T008).
2. US1: script de acceso y primera petición (T009–T012). **Parar y validar**: token automático y fallos explicados.
3. US2: protecciones y ciclo de vida (T013–T017). **Parar y validar**: recorrido completo sin tocar datos ajenos. Esto ya es una colección útil.

### Incremental Delivery

1. MVP → US3 (errores) → US4 (entorno desplegado) → US5 (clínicas).
2. US6 cuando la colección está completa: congela el contrato frente a la API y a los secretos.
3. US7 y Polish: README, evidencia y lista de verificación manual.

### Notas

- Cada historia de la colección se puede enseñar al terminar su verificación; ninguna rompe a la anterior porque solo añade peticiones o protecciones.
- El riesgo principal (que una petición omitida «no haga nada» a la vista en la aplicación) **no se puede cerrar desde aquí**: T038 lo deja como verificación manual explícita.
- Commit tras cada fase o grupo lógico **solo si la persona dueña lo pide**.

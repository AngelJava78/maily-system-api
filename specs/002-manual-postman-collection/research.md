# Investigación (Fase 0): Colección de Postman para pruebas manuales

**Feature**: `002-manual-postman-collection` | **Fecha**: 2026-10-18 | **Spec**: [spec.md](spec.md)

No quedan marcadores «NEEDS CLARIFICATION»: la spec ya traía las cuatro decisiones de alcance. Esta fase
resuelve **cómo** hacerlo en Postman y deja la evidencia de cada afirmación técnica.

## Cómo se obtuvo la evidencia

- **Prototipo desechable en Newman 6.2.3** (la versión que ya usa el repositorio), fuera del repositorio y
  no versionado: un Auth0 simulado con TLS (`POST /oauth/token`, con respuestas 200, 401, 403, 429, sin
  `access_token`, que no es JSON y con `expires_in` corto) y una API simulada que registra lo que recibe.
  Sobre él se ejecutó el **script de acceso real** de esta feature en 25 escenarios (16 de token y 9 de
  protección de datos). Los resultados se citan abajo como «prototipo».
- **Documentación de Postman** (learning.postman.com: `pm.execution`, pre-request scripts, variables).
- **Lo que NO se pudo verificar aquí** y queda como verificación manual en la aplicación de escritorio
  (ver [quickstart.md](quickstart.md), V2 y V3): cómo muestra Postman una petición omitida, la
  Consola de Postman, y un tenant real de Auth0. Los códigos de Auth0 de los escenarios se tomaron de su
  comportamiento documentado, no de una prueba contra un tenant.

---

## M1 — El acceso se resuelve con un único script previo a nivel de colección

**Decisión**: un *pre-request script* en la colección (se ejecuta antes de cada petición, incluidas las de
carpetas) asegura el token, comprueba los datos de la petición y decide si sale o no.

**Justificación**: es lo decidido en la spec (Clarifications) y es la única forma de que la persona no
haga nada: el flujo de OAuth 2.0 integrado de Postman exige pulsar «Get New Access Token», guarda el
token en su propio almacén y no ofrece mensajes en español ni renovación con *client credentials*.

**Alternativas descartadas**: OAuth 2.0 integrado de Postman (manual, sin mensajes propios); un script por
carpeta o por petición (se desincronizarían; la prueba de desfase tendría que vigilar N copias); pegar el
token a mano (es justo lo que se quiere evitar).

## M2 — «No enviar» se hace con `pm.execution.skipRequest()`, nunca lanzando un error

**Decisión**: cuando algo impide dejar la petición lista, el script la omite con
`pm.execution.skipRequest()`.

**Evidencia**: la documentación de Postman dice que, en un pre-request script, la petición **no se envía**,
se saltan el resto de scripts y **no se ejecutan pruebas**; en el *Collection Runner* se muestra sin
respuesta ni pruebas (no cuenta como prueba fallida) y funciona en Newman y en la CLI de Postman. Su propio
ejemplo es «omitir la petición si falta el token».
**Prototipo**: con un error de sintaxis en el script, **Newman envió la petición igualmente, sin token**
(`Authorization: Bearer {{accessToken}}` sin resolver). Un error de script **no es una forma segura de
parar**; `skipRequest` sí (en todos los escenarios de fallo la petición no salió).

**Alternativas descartadas**: lanzar una excepción (puede acabar enviando la petición sin credenciales:
incumple FR-010); dejar la cabecera vacía y que la API responda 401 (envía una petición sin token:
incumple FR-010 y confunde con un 401 real); dirigir la petición a una dirección inválida (truco opaco).

**Límite conocido**: `skipRequest` no es compatible con el *post-response*; aquí solo se usa en el
pre-request, donde sí lo es. La documentación no publica desde qué versión de Postman existe: se exige la
aplicación de escritorio actual y se verifica a mano en la versión instalada (V2).

## M3 — El motivo se explica en la Consola de Postman y en la variable `accessProblem`

**Decisión**: al omitir una petición, el script escribe **un solo mensaje en español** con `console.error`
(prefijo `[Colección manual]`) y lo guarda en la variable de colección `accessProblem`. No existe una
ventana emergente en Postman desde un script.

**Consecuencia de diseño (visibilidad)**: una petición omitida muestra **«sin respuesta»**; la persona debe
saber que el motivo está en la Consola (Ver → Mostrar Consola de Postman). Por eso la descripción de la
colección y la del README empiezan por esa instrucción y por «si no pasa nada al pulsar Enviar, abre la
Consola». Es el principal riesgo de experiencia de la feature; V3 lo comprueba en la aplicación.

**Alternativas descartadas**: dejar salir la petición para que la API responda 401 (ver M2); mostrar el
motivo con una prueba fallida (las pruebas no se ejecutan si se omite la petición).

## M4 — El script usa *callbacks*, no `await` de nivel superior

**Decisión**: `pm.sendRequest(solicitud, function (error, respuesta) { … })` y funciones que reciben un
`done(problema | null)`.

**Prototipo**: la primera versión con `await pm.sendRequest(…)` **falló en Newman 6.2.3** con `SyntaxError:
await is only valid in async functions and the top level bodies of modules`, y como consecuencia (ver M2)
**la petición salió sin token**. La versión con *callbacks* pasó los 25 escenarios. La aplicación de
escritorio acepta ambas formas; los *callbacks* funcionan en cualquier versión.

## M5 — Caché del token: tres variables de colección, renovación 60 s antes

**Decisión**: por identidad se guardan `accessToken`, `accessTokenExpiresAt` (milisegundos desde la época) y
`accessTokenKey` (`dominio|audience|clientId`). El token guardado sirve si la clave coincide y
`vencimiento − ahora > 60 s`. Si `expires_in` falta o no es positivo, se asume 24 h.

**Prototipo**: S1 (token de 24 h): 1 llamada a Auth0 para 3 peticiones y las 3 con el mismo token. S2
(`expires_in=30`, menor que el margen): una llamada por petición (renueva siempre). S16 (cambia el
*audience* a mitad): la siguiente petición pidió un token nuevo. Con esto se cumplen los escenarios 1, 2, 3 y
6 de la historia 1.

**Por qué en la clave no va el secreto**: el secreto nunca se copia a otra variable ni se deriva en nada
guardado. Cambiar solo el secreto, con el mismo cliente, no invalida un token ya válido: es inocuo.

## M6 — La petición a Auth0 y la traducción de sus fallos

**Decisión**: `POST https://{auth0Domain}/oauth/token`, `Content-Type: application/json`, cuerpo
`{"grant_type":"client_credentials","client_id":…,"client_secret":…,"audience":…}`. Traducción:

| Resultado | Mensaje (resumen) |
|---|---|
| Faltan variables | nombra cuáles faltan y que el secreto va solo en el valor local |
| Dominio con `https://`, `/` o `:` | pide el dominio sin esquema (se admite `:puerto`, pensando en simulaciones) |
| Sin respuesta | revisa `auth0Domain` y la conexión |
| 401 | Auth0 rechazó las credenciales: revisa el cliente y su secreto |
| 403 | la aplicación no está autorizada para ese *audience*: revisa que sea idéntico al identificador de la API de usuarios (con la barra final si la tiene) y la autorización de la aplicación |
| 429 | demasiadas solicitudes: espera un minuto |
| Otro estatus, sin JSON o sin `access_token` | respuesta inesperada, con el estatus |

**Prototipo**: cada fila produjo su mensaje y 0 peticiones a la API (S3 a S10). Ningún mensaje contiene el
secreto ni el token: solo **nombres** de variables.

**Pendiente de verificar**: 401 y 403 con un tenant real (V3).

## M7 — Qué identidad usa cada petición: se lee `pm.request.auth`

**Decisión**: el script mira la autenticación efectiva de la petición:

| `pm.request.auth` | Significado | Acción |
|---|---|---|
| sin definir (hereda) | la de la colección: `{{accessToken}}` | asegura el token principal |
| `noauth` | sin autenticación (documentación, simulaciones, caso 401) | no pide nada |
| `bearer` con `{{plainToken}}` | la segunda aplicación (opcional) | asegura el token de esa identidad |
| `bearer` con `{{badToken}}` | token inventado | genera uno aleatorio; no llama a Auth0 |

**Prototipo** (Newman): se comprobó que la herencia aparece como `undefined`, `noauth` como `noauth` y el
bloque de la petición como `{"token":"{{plainToken}}"}`; S11 a S14 se comportaron como la tabla.

**Regla derivada**: ninguna petición puede escribir un token literal (lo vigila la prueba de desfase,
[contracts/drift-test.md](contracts/drift-test.md), regla D5). Un bloque Bearer que solo referencia una
variable no es un secreto (constitución).

## M8 — Tres protecciones antes de enviar (todas «fallan cerradas»)

1. **Variables sin valor** (FR-004): toda `{{variable}}` de la **URL y del cuerpo** debe tener valor; si no, no
   sale y se explica qué petición enviar antes. *Hay que revisar también el cuerpo*: un
   `{"name":"{{subscriptionName}}"}` sin resolver **crearía una suscripción con ese texto literal**.
   (S15 verifica la URL; la revisión del cuerpo es parte del diseño y se prueba en la implementación.)
2. **Propiedad de lo que se modifica** (FR-004, SC-006): antes de un `PATCH`, `PUT` o `DELETE` sobre
   `{{subscriptionId}}` o `{{otherSubscriptionId}}`, el script hace un `GET` y exige que **exista y que su
   nombre sea el que guardó la colección**. Cubre el caso real de una base de datos de pruebas reiniciada
   donde **otra persona** reutiliza el mismo identificador: sin esta comprobación, el `DELETE` borraría datos
   ajenos. **Prototipo**: G1 (propia: sale, con 1 `GET`), G2 (otro nombre: no sale), G3 (404: no sale), G4
   (la comprobación recibe 403: no sale), G5 (una lectura no comprueba), G7 (sin nombre guardado: no sale),
   G8 (la otra suscripción también). Coste: 1 `GET` extra por petición que modifica; requiere
   `subscriptions:read`, que ya forma parte de los cuatro permisos.
3. **Datos de otra API** (US1 escenario 6 y caso límite): los identificadores y nombres guardados se guardan
   junto a la dirección de la API (`sessionApi`); si `baseUrl` cambia, se **descartan** (G6: tras cambiar,
   una petición de modificar no sale y pide crear primero).

**Regla derivada (vigilada por la prueba de desfase, D7)**: una petición que modifica o elimina solo puede
usar `{{subscriptionId}}` o `{{otherSubscriptionId}}` en su ruta. Los casos 404 usan **solo `GET`** con
`{{nonexistentSubscriptionId}}` (constante `2147483647`) o `{{deletedSubscriptionId}}`: ese segundo
identificador **nunca** acompaña a un `DELETE` o `PATCH`, porque tras reiniciar la base podría apuntar a datos
ajenos (G9 muestra que no tiene comprobación).

**Mejora detectada en el prototipo**: G7 («sin nombre guardado») reutiliza el mensaje de «otro nombre»; la
implementación debe darle su propio mensaje.

## M9 — Datos de ejemplo únicos por ejecución

**Decisión**: el **script de acceso** genera `newSuffix` (milisegundos en base 36 más 4 caracteres
aleatorios) cada vez que la URL o el cuerpo de la petición lo usan, justo antes de comprobar las variables, y el
cuerpo dice `Prueba manual {{newSuffix}}`; la prueba de la petición guarda `subscriptionId` y `subscriptionName`
(y los de la otra suscripción en la suya). *Por qué no en el pre-request de la propia petición*: Postman ejecuta
primero el de la colección, y su comprobación de M8.1 vería `newSuffix` vacío y omitiría la petición. El nombre mide ~25
caracteres (límite de la API: 100). Cada ejecución crea un nombre nuevo, así que repetir el recorrido no
choca con el anterior (las suscripciones eliminadas quedan como «Eliminada» y su nombre vuelve a quedar libre).

## M10 — Dónde vive cada valor y qué es un «secreto» en este formato

- **Entorno** (dos archivos, mismas variables, sin secretos): `baseUrl`, `auth0Domain`, `auth0Audience`,
  `auth0ClientId`, `auth0ClientSecret` (tipo `secret`), `plainClientId`, `plainClientSecret` (tipo `secret`),
  `clinicsStubUrl` y `testDatabaseNotice`. Los valores de los archivos están **vacíos** salvo `baseUrl` y
  `clinicsStubUrl` del entorno local (direcciones locales sin significado secreto) y el aviso.
- **Colección** (valores locales, nunca en archivos): token, vencimiento y clave de cada identidad,
  `accessProblem`, `sessionApi` y los datos de la sesión ([data-model.md](data-model.md)).
- **Precedencia**: una variable de entorno oculta a una de colección con el mismo nombre. Por eso
  ninguna variable de colección se llama como una del entorno (D6), igual que en la colección de la spec 001.
- **Modelo de variables de Postman**: la aplicación pasó de «valor inicial (sincronizado) / valor actual
  (local)» a valores locales por defecto que solo se sincronizan si se comparten. La diferencia no cambia
  la regla del repositorio: **los archivos llevan siempre el valor vacío** y la persona escribe el secreto
  en su copia local. La documentación se redacta sin depender de qué modelo tenga su versión.
- **El formato de entorno v2.1 no tiene campo de descripción.** El aviso de «solo bases de datos de pruebas»
  (FR-008) va en el **nombre** del entorno y en la variable informativa `testDatabaseNotice`, además de la
  descripción de la colección y del README.
- **Cambia la spec (ajuste menor)**: FR-008 pasa de «descripción» a «nombre y variable informativa».

## M11 — Las comprobaciones de cada petición son ligeras y en español

Cada petición lleva un evento `test` con `pm.test("…en español…")`: estatus esperado, `code` de error y campos
clave que fija el contrato ([error-catalog](../001-subscriptions-api/contracts/error-catalog.md)), sin
repetir las pruebas de pytest. Particularidades:

- **Eliminar** acepta 204, 409 (hay clínicas) y 503 (no se pudo comprobar) y su título dice cuál ocurrió y
  por qué (FR-005, US2 escenario 5). Tras un 204 guarda `deletedSubscriptionId`.
- **El caso 503** se prepara sin simulación de clínicas; si la simulación responde, el título explica que
  por eso se eliminó y cómo provocar el 503 (carpeta de simulación). No se marca como fallo.
- El 503 por permiso no verificable y el 403 generalizado **no se provocan**: se explican en las
  descripciones (FR-015).

## M12 — Carpeta de simulación de clínicas: reutiliza la simulación de la spec 001

**Decisión**: la carpeta «Simulación de clínicas (solo local)» llama a los puntos de prueba de la simulación
de la spec 001 (`/__test__/counts`, `/__test__/faults`, `/__test__/reset`, `/__test__/calls`). Hechos que condicionan
el diseño, verificados en [`tests/stubs/clinics_api/app.py`](../../tests/stubs/clinics_api/app.py):

- `POST /__test__/counts` **reemplaza todos los conteos** (el cuerpo es `{"<id>": n}`): fijar uno borra el
  resto. Se documenta; es una simulación local desechable.
- `POST /__test__/faults` admite `mode` entre diez valores y `count` (cuántas respuestas fallan);
  la carpeta ofrece los dos que explican el comportamiento de la spec (`unavailable` ×2 y `malformed`) y la
  descripción remite a la lista completa.
- Se levanta aparte: `uvicorn app:app --app-dir tests/stubs/clinics_api --port 8001` (autónoma, sin importar
  código de la aplicación), el puerto que ya usa `.env.example`.
- Sin simulación ni API de clínicas: el conteo sale `null` y eliminar responde 503 (FR-018).
- Las peticiones de esta carpeta no llevan autenticación (la simulación no la usa) y, si `clinicsStubUrl`
  está vacío (entorno desplegado), la protección de variables (M8.1) las omite **con un mensaje propio** que dice
  que la carpeta solo funciona en local (FR-017).

- **Hallazgos al implementar** (verificados con Newman contra la pila de la spec 001):
  - Antes de cada `PATCH`/`DELETE` la colección hace un `GET` de comprobación de propiedad (M8.2) y **ese `GET` también
    consulta al API de clínicas**: por eso `faults` se fija con `count` 3 (la consulta de 3.7, la comprobación previa y la
    eliminación) y no con 2.
  - Un script previo de **carpeta** (`pm.execution.skipRequest()` también funciona ahí) omite las peticiones de la carpeta 3 que
    van a la API cuando `clinicsStubUrl` está vacío, para no crear nada en el entorno desplegado (FR-017). Las que dependen de la
    creación muestran antes el aviso de «crea primero» del script de la colección.

## M13 — La prueba de desfase: nuevo archivo, módulo de apoyo compartido y análisis del JSON

**Decisión**: añadir `tests/contract/test_manual_postman_collection.py` y mover a
`tests/contract/postman_support.py` lo que ya tiene `test_postman_collection.py` (`requests_of`, `prefix_of`,
`operation_ids_of_the_api`, rutas). Las reglas D1 a D10 están en [contracts/drift-test.md](contracts/drift-test.md).

**Hallazgo que obliga a cambiar la prueba existente**: `test_no_file_of_the_postman_folder_holds_a_token_or_a_secret`
rechaza la palabra «secret» en **cualquier** archivo de `tests/postman/`. La colección manual y sus
entornos **deben** nombrar `auth0ClientSecret` y declarar el tipo `secret`. Se acota esa comprobación
textual a los archivos de la colección de punta a punta, y la manual pasa a comprobarse **por estructura**
(el valor de cada variable secreta es vacío, ningún valor de variable parece un secreto, ninguna cadena es
un JWT ni un `Bearer` literal). Es más estricta donde importa y no da falsos positivos por un nombre.

**Alternativas descartadas**: una sola prueba que mire palabras (falsos positivos permanentes o lista de
excepciones que se oxida); comparar con el OpenAPI en vivo contra la API levantada (la prueba debe correr sin
servicio, FR-019); leer el OpenAPI de `specs/…/openapi-subscriptions.yaml` (se desfasa de la API real: se usa
`create_app().openapi()` como la prueba existente).

## M14 — El script vive dentro del JSON, sin copia aparte

**Decisión**: la fuente de verdad es el JSON de la colección (el campo `event[].script.exec`). No se
versiona un `access.js` suelto ni un generador. La primera versión se genera con un script desechable (como
en la spec 001) y a partir de ahí se edita el JSON a mano o en Postman y se exporta.

**Justificación**: Postman solo lee lo que está dentro del JSON; una copia aparte se desfasaría y exigiría
otra prueba para compararlas. La revisión de cambios es legible porque `exec` es un arreglo de líneas.

**Alternativa descartada**: `tests/postman/scripts/access.js` + generador que lo incrusta (más piezas que
mantener para una sola colección).

## M15 — Verificación durante la implementación (no forma parte del repositorio)

Como la colección es solo manual, no tendrá un comando de Newman. Pero se **ejecutará con Newman una vez, de
forma desechable**, para no entregar 37 peticiones sin haberlas probado: la pila de la spec 001 (API real +
base de datos desechable + simulación de usuarios) más un Auth0 simulado con TLS que entrega un token
registrado en la simulación de usuarios con los cuatro permisos (y otro sin permisos para el caso 403).
Los resultados se informan; el harness queda fuera del repositorio. Lo que Newman no puede probar (la
aplicación de escritorio, un tenant real) queda en el [quickstart](quickstart.md) como verificación manual.

## Riesgos y límites aceptados

| Riesgo | Mitigación | Estado |
|---|---|---|
| La petición omitida «no hace nada» a la vista | descripciones y README abren con «mira la Consola de Postman»; `accessProblem` visible en las variables | V3 en la aplicación |
| La Consola de Postman muestra la petición a Auth0, **cuerpo incluido**, aunque el script no escriba el secreto | es local y no se sincroniza; se advierte de no compartir capturas de la Consola; no hay forma de ocultarla desde un script | Aceptado y documentado (ajuste a FR-011) |
| `skipRequest` en versiones antiguas de Postman | se pide la aplicación actual (la documentación no publica versión mínima) | V2 |
| Auth0 cambia su respuesta de error | cualquier respuesta no reconocida cae en «inesperada» y **no envía** | Cubierto (S6, S7) |
| Identificador reutilizado por otra persona tras reiniciar la base | comprobación de propiedad antes de modificar (M8.2) | Cubierto (G2) |
| El valor de un secreto escrito en el valor *inicial* en una cuenta que sincroniza | la prueba solo ve los archivos del repositorio; la advertencia es documental | Aceptado (spec, caso límite) |

# Contrato: pruebas de desfase y de secretos de la colección manual

**Archivos**: `tests/contract/test_manual_postman_collection.py` (nuevo), `tests/contract/postman_support.py`
(nuevo, apoyo compartido) y `tests/contract/test_postman_collection.py` (se ajusta) | **Spec**: FR-019, FR-020,
FR-021, SC-008 | **Investigación**: [research.md](../research.md) M13

Se ejecutan con `uv run pytest`: **solo leen archivos del repositorio y la definición de la API**
(`create_app().openapi()`); sin servicio, sin Node.js, sin Postman, sin red (FR-019, historia 6 escenario 4).
Cada regla es una función de prueba y su mensaje de fallo **nombra** lo que falta o sobra.

## `postman_support.py` (apoyo compartido)

Contiene lo que ya hay en `test_postman_collection.py` y lo que necesita la nueva prueba:

| Elemento | Uso |
|---|---|
| `POSTMAN`, `MANUAL_COLLECTION`, `MANUAL_ENVIRONMENTS`, `E2E_*` | rutas |
| `requests_of(items)`, `folders_of(items)`, `prefix_of(name)` | recorrer y nombrar |
| `operation_ids_of_the_api()` | operaciones según el OpenAPI generado |
| `scripts_of(item, listen)` | texto del script (`exec` unido) de un evento |
| `JWT_PATTERN`, `BEARER_LITERAL_PATTERN`, `HIGH_ENTROPY_PATTERN` | detección de secretos |

## Cambio en la prueba existente

`test_no_file_of_the_postman_folder_holds_a_token_or_a_secret` pasa a recorrer **solo** los archivos de la
colección de punta a punta (todo `tests/postman/` salvo la colección y los dos entornos manuales, `reports/`,
`node_modules/`). Motivo: la colección manual debe nombrar `auth0ClientSecret` y usar el tipo `secret`
(M13). Sus comprobaciones pasan a ser las reglas D5 de abajo. La regla «hay archivos que comprobar» se mantiene.

## Reglas

| Id | Regla | Falla cuando… |
|---|---|---|
| **D0** | La colección y los entornos son JSON válido; `info.schema` termina en `/collection/v2.1.0/collection.json`; los entornos tienen `_postman_variable_scope: "environment"` | formato distinto de v2.1 |
| **D1** | Operaciones ↔ peticiones, **en ambos sentidos**: el conjunto de `operationId` del OpenAPI es igual al de prefijos de petición, sin contar `docs` ni `sim` | falta una operación («operaciones sin petición: […]») o sobra una («peticiones de operaciones que la API no tiene: […]») |
| **D2** | Cada operación tiene al menos una petición en `1. Ciclo de vida…`; en `2. Casos de error` hay al menos un caso para cada estatus de {401, 403, 404, 409, 422, 503} (el nombre es `<op>: <NNN> …`) | un estatus sin caso («estatus sin caso de error: […]») |
| **D3** | La colección, cada carpeta y cada petición tienen `description` no vacía; cada petición tiene un evento `test` con al menos un `pm.test("…")` de título no vacío | descripción o comprobación vacías (nombra la petición) |
| **D4** | Existe el *pre-request* de colección con el script de acceso (contiene `skipRequest` y `/oauth/token`); la autenticación de la colección es Bearer `{{accessToken}}`; cada petición hereda, es `noauth` o es Bearer con exactamente `{{plainToken}}` o `{{badToken}}` | Bearer con un valor literal u otra variable |
| **D5** | **Sin secretos** (por estructura): en los entornos, toda variable de tipo `secret` y toda variable de acceso (`auth0Domain`, `auth0Audience`, `auth0ClientId`, `auth0ClientSecret`, `plainClientId`, `plainClientSecret`) tiene `value: ""`; `auth0ClientSecret` y `plainClientSecret` son de tipo `secret`; en la colección, toda variable cuyo nombre contenga `token`, `secret` o `password` (sin distinguir mayúsculas) tiene valor vacío; ninguna cadena del JSON coincide con un JWT (`eyJ…\.`); ninguna cabecera (`request.header[].value`) ni bloque `auth` contiene `Bearer <literal>`, y todo bloque `auth` Bearer lleva solo una `{{variable}}` (nunca un token escrito) (no se mira el texto de las descripciones, que puede decir «Bearer» en prosa); ningún valor de variable parece una clave (≥ 32 caracteres `[A-Za-z0-9_-]` sin espacios) | indica el **archivo y la variable** |
| **D5b** | Los scripts no escriben secretos en consola: ninguna llamada `console.<método>(…)` (`log`, `info`, `warn`, `error` o `debug`) menciona `secret`, `access_token`, `accessToken` ni `plainToken` (sin distinguir mayúsculas; un comentario que hable de «la consola» no cuenta) | nombra la petición/evento y la línea |
| **D6** | Los dos entornos definen **exactamente las mismas claves** (las nueve de [data-model.md](../data-model.md)); ninguna clave de entorno coincide con una variable de colección (la de entorno la ocultaría); `baseUrl` y `clinicsStubUrl` del local valen `http://127.0.0.1:8010` y `http://127.0.0.1:8001`; en el desplegado ambos están vacíos; `testDatabaseNotice` no está vacía en ninguno; el nombre de cada entorno incluye «bases de datos de pruebas» | claves distintas (nombra cuáles y de qué entorno) |
| **D7** | **No se toca lo ajeno**: toda petición `PATCH`/`PUT`/`DELETE` usa en su ruta solo `{{subscriptionId}}` o `{{otherSubscriptionId}}`; `{{deletedSubscriptionId}}` y `{{nonexistentSubscriptionId}}` solo aparecen en `GET`; ninguna ruta lleva un identificador numérico literal; las peticiones `sim` son `GET`/`POST` y su URL empieza por `{{clinicsStubUrl}}/__test__/` | nombra la petición |
| **D8** | Todo **fragmento del texto** de los scripts de la colección que empiece por un `operationId` de la API seguido de `: ` y llegue hasta la siguiente comilla o «»» —sea un literal completo, como el campo `creator` de `OWNED`, o una cita dentro de una pista o de un mensaje— es el **nombre exacto** de una petición | un mensaje remite a una petición que ya no existe |
| **D9** | Independencia (FR-001): ninguna petición ni script de la colección manual menciona `usersStubUrl`, ni empieza por `setup:`, y la colección manual no comparte nombre con la de punta a punta | dependencia de las simulaciones de usuarios o de Newman |
| **D10** | Los nombres de petición cumplen `<prefijo>: <descripción>` con prefijo en {operationIds de la API, `docs`, `sim`}; no hay dos peticiones con el mismo nombre dentro de la colección | nombre mal formado o repetido |
| **D11** | **Orden que funciona** (FR-002): dentro de cada carpeta, antes de la primera petición que usa `{{subscriptionId}}` (en la ruta o en el cuerpo) hay una `create_subscription` cuyo evento `test` guarda `subscriptionId`; lo mismo con `otherSubscriptionId`. (La excepción es la que solo lee ids ya guardados por otra carpeta: `deletedSubscriptionId`, que depende del ciclo de vida y se avisa en su descripción) | una petición usa un id que su carpeta aún no ha creado |

## Mapa de requisitos → reglas

| Requisito | Reglas |
|---|---|
| FR-001 | D1, D9 |
| FR-002 | D11 |
| FR-003, FR-005 | D3 |
| FR-004 | D7, D11 |
| FR-011, FR-020 | D4, D5, D5b, D6 |
| FR-013 | D2 |
| FR-019 | D1 y que el archivo solo lee JSON y el OpenAPI |
| FR-025 | D10 (identificadores en inglés) |
| SC-008 | D1 (operación sin petición), D5 (secreto en el archivo) |

## Pruebas del propio detector (obligatorias en las tareas)

Para que las reglas no sean decorativas, la prueba incluye casos negativos sobre **copias en memoria** de la
colección y de los entornos (sin tocar disco): quitar una petición → D1 falla y la nombra; añadir una con prefijo
inexistente → D1/D10; poner un valor en `auth0ClientSecret` → D5; quitar `testDatabaseNotice` a un entorno → D6;
cambiar el Bearer de una petición a un literal → D4; usar `{{deletedSubscriptionId}}` en un `DELETE` → D7. La
regla se escribe como función pura `check_*(collection, environments) -> list[str]` y la prueba la ejercita con la
real (sin problemas) y con las mutadas (con el problema esperado).

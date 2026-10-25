# Investigación (Fase 0): Monitoreo de salud de los servicios de Maily

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Fecha**: 2026-10-24

Aquí se resuelven las incógnitas técnicas del plan. No quedan marcadores `NEEDS CLARIFICATION`: las
decisiones de negocio están en la especificación (29 decisiones de «Assumptions») y este documento solo
decide el *cómo*. Lo marcado como **Evidencia** se comprobó en esta sesión: leyendo el código de las
versiones fijadas en `uv.lock` (FastAPI 0.143.3, Starlette 1.8.0, httpx 0.28.1, httpcore 1.0.9, SQLAlchemy
2.0.55, asyncpg 0.32.0) desde la caché local de uv, con un experimento en Python 3.14.8 (solo biblioteca
estándar y el paquete `tzdata` 2026.5 ya presente en esa caché, sin instalar nada en el proyecto) y
dentro de la imagen del servicio ya construida (`maily-system-e2e-api`, `python:3.14-slim`). El resto se
leyó del código y de las pruebas del repositorio.

## Resumen de decisiones

| Id | Tema | Decisión |
|---|---|---|
| R1 | Versión de una sola fuente (FR-007) | `VERSION = "2.0.0"` en `src/__init__.py`; `pyproject.toml` pasa de `0.1.0` a `2.0.0` y una prueba exige que coincidan con el OpenAPI y con `/info`. No se sube la versión (cambio compatible) |
| R2 | Capas y módulos | Dos Routers, cinco módulos de Service, dos de integración, dos Repositories, un modelo y dos módulos de DTOs, todos en carpetas existentes de `src/` |
| R3 | Rutas públicas (Principio VIII) | Un router sin dependencias de seguridad para las cuatro rutas públicas; no aparecen con `security` en el OpenAPI; `/health/status` no lee `Authorization` |
| R4 | Permiso antes de validar | `protected(...)` de siempre. Verificado en FastAPI 0.143.3: las dependencias van antes que la validación, salvo un cuerpo JSON ilegible (desviación ya aceptada en la spec 001) |
| R5 | Chequeo de la base de datos | `SELECT 1` en un Repository, con sesión propia del engine compartido y `asyncio.timeout`; falla clasificada por fase; `/health/ready` comparte la comprobación en curso entre peticiones simultáneas |
| R6 | Llamadas a los componentes | Cliente httpx propio: solo `GET`, tiempo total por llamada, sin redirecciones, sin reintentos, sin keep-alive, sin cookies ni `trust_env`, `Accept-Encoding: identity` y lectura cruda de 64 KiB como máximo |
| R7 | Depuración del contrato v1 | En `src/integrations/health_contract.py`: solo campos conocidos, textos de 64 caracteres sin controles, 20 chequeos, fechas a UTC, códigos fuera de lista → `unexpected_error` |
| R8 | Reglas de estado | En el Service: tabla de decisión de servicio, frontend y base de datos; estado global de FR-017 |
| R9 | Agregación en paralelo | Base de datos y registro a la vez; los chequeos empiezan al conocerse la lista; cada componente aislado de las fallas de los demás |
| R10 | Caché y agregación compartida | `HealthState` por proceso: último resultado, una agregación en curso y un contador de generación; edad máxima `HEALTH_CACHE_SECONDS` (consulta) o `max(HEALTH_CACHE_SECONDS, 15)` (estado público) |
| R11 | Copia del registro en memoria | Tupla inmutable reemplazada en cada lectura exitosa; `None` = nunca se leyó |
| R12 | Horario y `next_start_at` | `zoneinfo`; ventana `[inicio, fin)` en la hora local; próximo inicio por fecha local con manejo del hueco y del doble horario del cambio de horario de verano |
| R13 | `zoneinfo` y `tzdata` | `tzdata` como dependencia del servicio (sin marcador de plataforma); no se considera tecnología nueva: se registra en Complexity Tracking (C2, aprobado el 2026-10-24) |
| R14 | SSRF y lista permitida | Formato estricto de `base_url` y rutas en el DTO; lista permitida en el Service (al registrar) y en cada agregación; guardia del host en cada llamada |
| R15 | Registro de componentes | Tabla `monitored_components` (migración 0004), baja lógica con `deleted_at`, índice único parcial, orden `COLLATE "C"`, modificación con `SELECT … FOR UPDATE` |
| R16 | Configuración y arranque | `HealthSettings` y `BuildSettings`, validación textual estricta; el horario se valida con una función que nombra las variables; un solo mensaje de error al arrancar |
| R17 | Datos de build y Docker | `ARG`/`ENV` al final del `Dockerfile`; en Compose van como argumentos de build, no como entorno (una variable vacía taparía el valor de la imagen) |
| R18 | CORS (FR-050) | El `CORSMiddleware` global ya cubre las rutas de salud; solo se añaden pruebas y documentación |
| R19 | OpenAPI | Etiqueta «Salud» para las diez operaciones; identificadores de operación de FR-001; el 503 de `/health/ready` usa el esquema del contrato v1 |
| R20 | Pruebas | Reloj controlable, simulación de componentes reutilizada por pytest y por Newman, transporte con fallas para DNS y conexión, base de datos real para el Repository |
| R21 | Ajustes a pruebas existentes (FR-039) | Diez ajustes enumerados en el plan; ninguno cambia lo que se verifica de suscripciones ni del dashboard |
| R22 | Colección de Postman y pila e2e | Colección nueva `MailySoft-System-Salud`, simulación de componentes en la pila aislada y prueba guardiana propia |
| R23 | Registros (logs) | Un aviso solo cuando cambia el estado de un componente o el de `/health/ready`; código del componente y de la falla, nunca dirección, token ni cuerpo |
| R24 | Alineación con usuarios 016 y pacientes 008 | Los nombres de las variables ya coinciden en las tres specs; nada que alinear |

---

## R1. Versión de una sola fuente (FR-007, SC-008)

**Decisión**. La constante `VERSION = "2.0.0"` se mueve de `src/main.py` a `src/__init__.py` (hoy vacío) y
es la única fuente en el código: la leen `create_app()` (versión del OpenAPI) y el Service de salud (`/info`
y el componente integrado `maily-system-api`). `pyproject.toml` pasa de `version = "0.1.0"` a `"2.0.0"`, y
`uv lock` actualiza la línea del paquete raíz en `uv.lock`. Una prueba nueva (`tests/unit/test_version.py`)
lee `pyproject.toml` con `tomllib` (biblioteca estándar) y exige que coincida con `src.VERSION`, con
`info.version` del OpenAPI y con la versión de `/info`. La versión publicada **no cambia** (`2.0.0`).

**Por qué**.

- `pyproject.toml` declara `[tool.uv] package = false`: el proyecto no se instala, así que
  `importlib.metadata.version()` no puede leer su versión, y una versión dinámica exigiría un *build
  backend* que el proyecto no tiene. La fuente tiene que estar en el código.
- `src/__init__.py` ya es un módulo raíz admitido por `tests/unit/test_layering.py` (`ROOT_MODULES`), así
  que no hace falta tocar esa prueba; un `src/version.py` nuevo sí la obligaría a cambiar.
- El Router de `/info` no puede importar `src.main` (importación circular: `main` importa los Routers).
- Convención del repositorio: la spec 003 añadió una operación sin subir la versión y la 004 la subió por
  un cambio incompatible (`test_dashboard_openapi.py` lo deja escrito). Esta feature solo añade
  operaciones, campos y una tabla, así que `2.0.0` se mantiene y cumple «no retroceder» (decisión 21).

**Alternativas descartadas**. Leer `pyproject.toml` en tiempo de ejecución (acopla el servicio a un archivo
de empaquetado y añade E/S al arrancar); versión dinámica con hatchling (tecnología nueva); subir a
`2.1.0` (rompe la convención y obligaría a tocar tres pruebas que fijan `2.0.0`).

## R2. Capas y módulos (Principio I)

**Decisión**. Todo vive en las carpetas existentes de `src/` (no hay carpeta nueva, así que
`test_layering.py` no cambia):

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Routers | `routers/health.py` | `public_router` (las cuatro rutas públicas) y `router` (`GET /api/v1/health`) |
| Routers | `routers/monitored_components.py` | Las cinco operaciones del registro |
| Services | `services/health_service.py` | Disponibilidad, información de build, agregación, reglas de estado, estado global y vista pública |
| Services | `services/health_state.py` | Memoria del proceso: caché, agregación en curso, generación, copia del registro y comprobación de disponibilidad en curso (sin E/S) |
| Services | `services/health_schedule.py` | Ventana de encendido y próximo encendido (funciones puras) |
| Services | `services/clock.py` | `Clock` (protocolo) y `SystemClock`: hora UTC y reloj monótono |
| Services | `services/monitored_component_service.py` | Reglas del registro: lista permitida, códigos reservados, validación del componente resultante, conflictos e invalidación de la caché |
| Integraciones | `integrations/health_probe.py` | Llamadas HTTP a los componentes y traducción de sus fallas a los códigos de FR-018 |
| Integraciones | `integrations/health_contract.py` | Lectura y depuración de los cuerpos del contrato v1 (`live`, `ready`, `info`) |
| Repositories | `repositories/monitored_component_repository.py` | Persistencia del registro |
| Repositories | `repositories/database_health_repository.py` | La consulta trivial de la base de datos y la traducción de sus fallas |
| Modelos | `models/monitored_component.py` | Tabla `monitored_components` |
| DTOs | `dtos/health.py`, `dtos/monitored_component.py` | Respuestas de salud y entrada/salida del registro |

La raíz de composición (`dependencies.py`) arma dos funciones que la agregación usa con **sesiones
propias**, no con la sesión de la petición: `read_enabled_components()` (Repository del registro) y
`ping_database()` (Repository de la base). El Service las recibe como `Callable` y les pone el tiempo
máximo; así no importa `sqlalchemy` (prohibido para los Services) y la agregación compartida no depende de
recursos de una petición que puede terminar antes que ella (R10).

**Por qué**. La depuración de las respuestas de otro sistema es «traducción de sus respuestas y de sus
fallos», que el Principio I asigna a `src/integrations/`; decidir `up`/`degraded`/`down` es una regla de
negocio y va al Service. `/health/live` no pasa por ningún Service ni dependencia (devuelve una constante)
para responder aunque falle cualquier otra pieza (FR-004).

## R3. Rutas públicas y Principio VIII (FR-002, FR-045)

**Decisión**. `public_router` (sin prefijo, etiqueta «Salud») declara `/health/live`, `/health/ready`, `/info`
y `/health/status` **sin** `protected(...)` y sin ninguna dependencia que lea `Authorization`
(`get_bearer_token`, `bearer_scheme`). Por eso FastAPI no les pone `security` en el OpenAPI y una cabecera
`Authorization` en `/health/status` se ignora sin validarse ni reenviarse (escenario 6-8). Las seis
protegidas usan `protected(HEALTH_*)` como las demás. `test_permission_coverage.py` reconoce las cuatro
rutas como públicas (ocho con las de documentación) y sigue fallando ante cualquier otra ruta sin permiso
(ajuste A1 del plan).

**Por qué**. El Principio VIII admite «las comprobaciones de salud, si la especificación las define»; la
spec las define y las limita a esas cuatro (FR-002). `/info` es parte del contrato de salud y
`/health/status` es una vista mínima del resultado de salud sin datos sensibles (FR-047). No hace falta
enmendar la constitución.

## R4. Permiso antes de validar (FR-003, FR-030, escenario 3-10)

**Decisión**. Las seis operaciones protegidas usan `protected(...)`; el identificador de ruta es
`component_id: UUID` (validado por FastAPI) y los cuerpos son DTOs con `extra="forbid"`.

**Evidencia** (`fastapi/routing.py::get_request_handler`, 0.143.3): el manejador lee y decodifica el
cuerpo JSON **antes** de `solve_dependencies`; si el JSON es ilegible lanza `RequestValidationError` en ese
punto. Todo lo demás (parámetros de ruta, de consulta y la validación del cuerpo contra el DTO) se acumula
como error *después* de resolver las dependencias, que van primero y cortan con 401/403/503. Resultado:

- Sin permiso y con datos que no cumplen el DTO (campo desconocido, `code` inválido, UUID mal escrito) →
  **403** (o 401/503): el permiso va antes, como exige el escenario 3-10.
- Sin permiso y con un cuerpo que **no es JSON legible** → 422. Es la desviación que ya aceptó la spec 001
  (su FR-004 y su Complexity Tracking) para las operaciones con cuerpo; aquí afecta a
  `create_monitored_component` y `update_monitored_component`. Se registra en el Complexity Tracking del
  plan como desviación heredada (no nueva, C3); la spec 005 no la mencionaba y la persona responsable la
  confirmó para estas dos rutas el 2026-10-24.

**Orden de los errores del registro** (FR-030): acceso → datos del DTO y lista permitida (422) → existencia
(404) → reglas del componente resultante de una modificación (422, necesitan la fila) → conflicto (409). El
único 422 que llega después del 404 es el de la combinación resultante (por ejemplo, pasar `kind` a
`frontend` con `ready_path` guardada): no se puede evaluar sin el componente.

## R5. Chequeo de la base de datos (FR-005, FR-016, SC-007)

**Decisión**.

- `DatabaseHealthRepository(session).ping()` ejecuta `SELECT 1` en dos fases: obtener la conexión
  (`await session.connection()`) y ejecutar la consulta. Traduce las fallas a
  `DatabaseUnavailableError(kind)` (nueva, en `src/repositories/errors.py`): cualquier falla al obtener la
  conexión → `connection_error`; al ejecutar, un `DBAPIError` con `connection_invalidated` →
  `connection_error`; cualquier otra → `unexpected_error`. No atrapa `BaseException` (la cancelación debe
  propagarse).
- El Service mide la latencia (`time.perf_counter`) y pone el límite con `asyncio.timeout`:
  `HEALTH_READY_TIMEOUT_SECONDS` en `/health/ready` y `HEALTH_CHECK_TIMEOUT_SECONDS` en la agregación.
  `TimeoutError` → `timeout`. Cualquier otra excepción inesperada → `unexpected_error` (nunca un 500).
- Se usa el engine compartido (`get_session_factory()`), con una sesión propia por chequeo.
- **`/health/ready` comparte la comprobación en curso**: si llegan varias peticiones a la vez, esperan la
  misma consulta (`HealthState.readiness_task`, con `asyncio.shield`); al terminar no se guarda nada, así
  que la siguiente petición vuelve a consultar. No es una caché: evita que una ráfaga de peticiones a una
  ruta pública acapare el pool de conexiones que usan las suscripciones.

**Evidencia** (`sqlalchemy/pool/base.py` y `connectors/asyncio.py`, 2.0.55): una cancelación que llega
durante la conexión (`__connect`: `except BaseException` cierra la conexión «varada»), durante la
obtención del pool (`_checkin_failed` invalida el registro) o durante el cierre (`terminate()` maneja
`CancelledError`) deja el pool consistente. Por eso basta `asyncio.timeout` sobre el engine compartido y
no hace falta un engine aparte.

**Cota de conexiones**: a lo más una para `/health/ready` y dos para la agregación en curso (consulta y
registro) por proceso, de las 15 del pool por defecto (5 + 10).

**Alternativas descartadas**. Un engine propio con `NullPool` (una conexión TCP+TLS nueva por petición
pública: una ráfaga podría agotar las conexiones del servidor de Azure); confiar solo en los tiempos de
asyncpg (`timeout` de conexión de 60 s por defecto y sin cota total); una caché del resultado de `ready`
(una *probe* debe reflejar el estado actual).

## R6. Llamadas a los componentes (FR-019, FR-021, SC-004, SC-005)

**Decisión**. `lifespan` crea un segundo `httpx.AsyncClient`, solo para los chequeos
(`app.state.health_http_client`), y lo cierra al apagar:

| Ajuste | Valor | Por qué |
|---|---|---|
| `follow_redirects` | `False` (también por petición) | Un 3xx es `unexpected_status` (FR-019); nunca se salta a otro host |
| `trust_env` | `False` | Sin proxies del entorno ni credenciales de `.netrc`: ninguna llamada lleva credenciales (FR-021) |
| Cookies | Tarro con política que rechaza todas | Ninguna cookie de una respuesta viaja en otra llamada |
| `verify` | `True` (por defecto) | Certificados TLS verificados (FR-021) |
| `limits` | `max_connections=200`, `max_keepalive_connections=0` | Sin espera por el pool con 50 componentes × 3 llamadas; sin reutilizar conexiones viejas, que darían `connection_error` falsos |
| `timeout` | `httpx.Timeout(HEALTH_CHECK_TIMEOUT_SECONDS)` | Respaldo por fase; el límite real es total (abajo) |
| Cabeceras | `Accept` (`application/json` en servicios), `Accept-Encoding: identity`, `User-Agent: maily-system-api-health/<versión>` | Ninguna de la petición original: ni token ni `X-*` |

Cada llamada (`HealthProbeClient`) es un `GET` con `asyncio.timeout(T)` alrededor de **todo** (DNS,
conexión, cabeceras y cuerpo), sin reintentos. Con `client.stream(...)`:

- `Content-Length` mayor que 65 536 → `response_too_large` sin leer nada.
- Un `Content-Encoding` distinto de `identity` → `invalid_response` (se pidió `identity`; leer en crudo
  evita que una «bomba» comprimida se expanda en memoria).
- El cuerpo se lee con `aiter_raw()` acumulando hasta 65 536 bytes; uno más → `response_too_large` y se
  deja de leer.
- En un frontend no se lee el cuerpo: solo cuenta el código de estado (FR-015).

**Traducción de fallas** (FR-018): `TimeoutError` o `httpx.TimeoutException` → `timeout`; `httpx.ConnectError`
cuya cadena de causas contiene `socket.gaierror` → `dns_error`; cualquier otro `ConnectError`, `ReadError`,
`WriteError` o `RemoteProtocolError` (conexión rechazada o cortada, TLS, certificado) → `connection_error`;
cualquier otra excepción → `unexpected_error`. El registro (log) nombra el código del componente y el de la
falla; nunca la dirección, el cuerpo ni el mensaje de la excepción.

**Evidencia** (`httpcore/_backends/anyio.py` y `_exceptions.py`, 1.0.9; `httpx/_transports/default.py`,
0.28.1): `connect_tcp` traduce `OSError` (y `socket.gaierror` es uno) a `httpcore.ConnectError` con
`raise … from exc`, y httpx lo vuelve a envolver con `from exc`: la `gaierror` queda en la cadena
`__cause__`. `ssl.SSLError` también se traduce a `ConnectError`. httpx pide `gzip, deflate` por defecto
(`ACCEPT_ENCODING`), por eso se fija `identity`.

**Guardia del host** (FR-026): la dirección se arma concatenando `base_url` y la ruta; antes de llamar se
analiza con `httpx.URL` y, si su esquema, host o puerto no son los de `base_url`, no se llama y el
componente queda `unknown` con `host_not_allowed`. Con las reglas de formato de R14 no puede ocurrir; cubre
filas alteradas a mano en la base de datos.

**Riesgo aceptado**: no se filtra por la IP resuelta (*DNS rebinding*) ni se bloquean rangos privados, porque
los servicios a monitorear son internos (nombres de Docker, IP privadas). El control es la lista permitida,
que fija quien opera; el README recomienda hosts exactos (spec, «Lista permitida prudente»).

## R7. Depuración del contrato v1 (FR-013, FR-014, FR-015)

**Decisión**. `src/integrations/health_contract.py` (funciones puras, sin red) convierte una respuesta en
registros internos y nunca devuelve texto crudo:

| Respuesta | Bien | Mal |
|---|---|---|
| `live` | 200 y objeto JSON con `status == "ok"` (los campos extra se ignoran) | Otro código → `unexpected_status`; cuerpo no JSON, no objeto o sin ese `status` → `invalid_response` |
| `ready` | 200 y objeto con `status == "ok"` y `checks` lista | 503 con `status == "unavailable"` y `checks` lista → `not_ready` con sus chequeos; 200/503 con otro cuerpo → `invalid_response`; otro código → `unexpected_status` |
| `info` | 200 y objeto JSON: cada campo por separado | Cualquier falla → los cuatro datos de build en `unknown`; un campo ausente o inválido → solo ese en `unknown` |

Reglas de los valores:

- **Textos** (`version`, `commit`, `environment`, nombre de un chequeo): se quitan los caracteres de control
  (categoría Unicode `C*`), se recortan los espacios y se cortan a 64 caracteres; vacío o no texto →
  `unknown` (un chequeo sin nombre se descarta).
- **`build_date`**: `datetime.fromisoformat` con zona (`Z` o desfase), normalizado a UTC con `Z`; sin zona,
  inválido o no texto → `unknown`.
- **Chequeos**: se toman los primeros 20 elementos de la lista y se descartan los mal formados (sin `name`
  de texto o con `status` distinto de `ok`/`error`). `latency_ms`: entero ≥ 0 (no `bool`) o `null`. `error`:
  `null` si `status` es `ok`; si es `error`, uno de `timeout`, `connection_error`, `not_configured` o
  `unexpected_error`, y cualquier otro valor (o ninguno) → `unexpected_error`.

## R8. Reglas de estado (FR-014 a FR-018)

**Decisión**. El Service aplica estas tablas sobre los registros de R7:

**Servicio** (`live`, `ready` e `info` en paralelo):

| `live` | `ready` | Estado | `error` |
|---|---|---|---|
| bien | bien | `up` | `null` |
| bien | 503 del contrato | `degraded` | `not_ready` (con sus `checks`) |
| bien | cualquier otra falla | `degraded` | el código de la falla de `ready` |
| falla | (cualquiera) | `down` | el código de la falla de `live` |

`info` nunca cambia el estado; `checks` son los de `ready` (vacía si no los trae); `latency_ms` es la de
`live`.

**Frontend**: 2xx en `live_path` → `up`; cualquier otra respuesta → `down` con `unexpected_status`; una
falla de red → `down` con su código. Con `info_path`, se lee como la de un servicio; sin ella, `unknown`.

**Integrados**: `database` → `up` si la consulta respondió; si no, `down` o `stopped` según el horario
(R12), con `error` = la causa observada, `checks` vacía y datos de build `unknown`. `maily-system-api` →
`up` si esa misma consulta respondió, o `degraded` con `not_ready`; sus `checks` son
`[{"name": "database", …}]`, su latencia la de la consulta y sus datos de build los de `/info`. **Nunca se
llama por HTTP a sí mismo**: no hay componente registrado con ese código (reservado) y la prueba lo
comprueba registrando las llamadas del cliente HTTP.

**Host fuera de la lista vigente** → `unknown` con `host_not_allowed`, `latency_ms` `null`, sin llamada.
**Excepción inesperada del propio agregador** al evaluar un componente → ese componente `unknown` con
`unexpected_error`; el resto sigue (FR-018).

**Estado global** (FR-017): `down` si alguno está `down`; si no, `degraded` si alguno está `degraded`,
`stopped` o `unknown`; si no, `ok`. `registry_available` no lo cambia.

## R9. Agregación en paralelo y su duración (FR-019, SC-001)

**Decisión**. Una agregación:

1. Lanza a la vez la consulta a la base (`ping_database`, límite `T` = `HEALTH_CHECK_TIMEOUT_SECONDS`) y la
   lectura del registro (`read_enabled_components`, límite `T`).
2. En cuanto termina la lectura (bien, o con falla y la copia en memoria, R11), lanza todos los chequeos
   de los componentes registrados habilitados (cada llamada con límite `T`), sin esperar a la base.
3. Espera la base y los chequeos (`asyncio.gather`), arma los dos integrados, ordena y calcula el estado
   global. `checked_at` = el instante en que termina.

Duración: `max(T_base, T_registro + T_chequeos)` ≤ `T + T`, más el trabajo propio (milisegundos), dentro de
`2T + 1 s`; con la base respondiendo, la lectura del registro tarda milisegundos y la agregación queda en
`T + 1 s` (SC-001). Cada componente se evalúa en su propia tarea con su propia guarda: uno lento o roto no
retrasa ni estropea a los demás.

**Orden** (FR-011): los dos integrados; después los registrados por `(sort_order, code)` con el orden de
puntos de código de Python, el mismo que `COLLATE "C"` en la base (R15).

## R10. Caché, agregación compartida y periodo mínimo del estado público (FR-020, FR-048, SC-006, SC-016)

**Decisión**. `HealthState` (uno por aplicación, creado en `create_app()` en `app.state.health`; no hace E/S)
guarda: `last` (resultado, instante monótono en que terminó y su generación), `in_flight` (generación y
`asyncio.Task` de la agregación en curso), `generation` (entero que se incrementa al invalidar) y la copia
del registro. El Service ofrece `current_result(max_age)`:

1. Si `last` es de la generación vigente y su edad (reloj monótono) es menor que `max_age` → se devuelve
   tal cual, con sus `checked_at` originales.
2. Si no, y hay una agregación en curso de la generación vigente → se espera su resultado.
3. Si no hay ninguna → se lanza una (`asyncio.create_task`) y se espera.
4. Las esperas usan `asyncio.shield`: si la persona que lanzó la agregación corta la conexión, la
   agregación sigue para las demás.
5. Al terminar, la agregación se guarda en `last` solo si su generación sigue vigente y libera `in_flight`
   (en `finally`).

`max_age` = `HEALTH_CACHE_SECONDS` en `GET /api/v1/health` (con 0 nunca reutiliza un resultado terminado,
pero sí comparte la agregación en curso) y `max(HEALTH_CACHE_SECONDS, 15)` en `/health/status`. Como
ambas rutas comparten `last`, una consulta autenticada puede adelantar la siguiente ronda y las peticiones
públicas no (FR-048). La caché guarda resultados, nunca decisiones de permiso: la dependencia de
seguridad corre antes que el Service en cada petición (FR-003).

**Invalidación** (FR-020, FR-031): alta, modificación y baja exitosas llaman a `HealthState.invalidate()`
(incrementa la generación y borra `last`). Si en ese momento hay una agregación en curso que ya leyó el
registro anterior:

- `GET /api/v1/health` (que debe ver el cambio) **espera a que termine** y lanza otra: nunca hay dos a la
  vez (FR-020). En esa carrera, una consulta puede tardar hasta dos agregaciones; solo ocurre en el
  proceso que atendió el cambio y con la base respondiendo (las escrituras fallan si no), y se documenta.
- `/health/status` acepta unirse a la agregación en curso aunque sea de la generación anterior (solo
  acota chequeos, FR-048); su resultado no se guarda, así que la siguiente petición pública lanza una
  agregación nueva.

**Concurrencia**: un solo bucle de eventos por proceso y ningún `await` entre comprobar y asignar
`in_flight`, así que no hace falta un candado. Varias réplicas tienen cada una su estado (edge case de la
spec).

**Alternativas descartadas**. Lanzar una segunda agregación en la carrera (rompe «a lo más una a la vez»);
cancelar la agregación vieja (sus esperas tendrían que reintentar y tardarían lo mismo); una caché por ruta
(dos rondas en vez de una); trabajos en segundo plano (prohibidos por FR-019 y FR-043).

## R11. Copia del registro en memoria (FR-036, SC-009)

**Decisión**. `HealthState.registry_snapshot`: `None` hasta la primera lectura exitosa; después, una tupla
inmutable de `ComponentTarget` (registros congelados con lo necesario para chequear: `id`, `code`, `name`,
`kind`, `base_url`, rutas y `sort_order`), que se reemplaza entera en cada lectura exitosa (también si
vuelve vacía). Si la lectura falla o agota su tiempo: se usa la copia y `registry_available` es `false`;
sin copia, solo los integrados. No se guarda en disco ni caduca. Se guardan registros propios y no objetos
ORM, que quedarían separados de su sesión.

**Por qué**. La copia es un dato propio del servicio (su registro), no una copia de datos de otro sistema
(Principio IX). La lectura que la renueva es la misma que hace cada agregación: no hay lecturas extra.

## R12. Horario de la base de datos y `next_start_at` (FR-033, FR-034, FR-035, FR-044, SC-003, SC-013)

**Decisión**. `DatabaseSchedule` (en `src/config.py`): `ZoneInfo`, conjunto de días (`0`=lunes … `6`=domingo),
`start` y `end` (`datetime.time`). `src/services/health_schedule.py`:

- `in_window(schedule, instant)`: `local = instant.astimezone(zone)`; dentro si `local.weekday()` está en los
  días y `start <= local.time() < end`. El día y la hora se evalúan en la zona, con sus reglas en ese
  instante (FR-034).
- `next_start(schedule, instant)`: recorre las fechas locales desde la de la observación (hasta 8 días);
  para cada fecha incluida en los días calcula el instante en que la hora local es `start` y devuelve el
  primero **posterior** a la observación. Si esa hora local existe dos veces (se atrasa el reloj), se usa
  `fold=0`: la primera. Si no existe (se adelanta), se detecta porque el instante no vuelve a la misma hora
  local, y se busca por bisección (≤ 17 pasos, al segundo) el primer instante con el desfase nuevo: el
  instante del salto.
- Estado de `database` cuando la consulta falla: sin horario → `down`; con horario, dentro de la ventana →
  `down` y `next_start_at` `null`; fuera → `stopped`, `error` = la causa observada y `next_start_at` =
  `next_start(...)` en ISO 8601 UTC con `Z`. Se calcula con el `now()` del reloj del Service, al terminar
  la consulta, y se sirve tal cual desde la caché.

**Evidencia** (experimento con `zoneinfo` y `tzdata` 2026e): con lunes a viernes de 08:00 a 20:00 en
America/Mexico_City, una falla el martes a las 21:00 da `2026-10-28T14:00:00Z`; el viernes 23 de octubre de
2026 a las 21:15 (`2026-10-24T03:15:00Z`) da `2026-10-26T14:00:00Z`; el viernes a las 19:30 (sábado 01:30
UTC) queda dentro de la ventana; las 20:00 en punto quedan fuera y las 08:00 en punto dentro. En
America/Tijuana, una falla el viernes 30 de octubre de 2026 a las 21:00 (UTC−7) da `2026-11-02T16:00:00Z`
(lunes 08:00, ya en UTC−8). Con una ventana de domingo a las 02:30 (hora que no existe el 14 de marzo de
2027) da `2027-03-14T10:00:00Z`, el salto; a las 01:30 (que existe dos veces el 7 de noviembre de 2027) da
`2027-11-07T08:30:00Z`, la primera. Todos coinciden con los escenarios de la spec.

**Validación de las variables** (R16): zona aceptada por `ZoneInfo` (si no existe o no hay datos de zonas
→ no arranca); días en inglés sin distinguir mayúsculas, separados por comas, sin vacíos ni repetidos;
horas `HH:MM` de 00:00 a 23:59 con dos dígitos; inicio menor que fin; las cuatro juntas o ninguna.

**Por qué**. Es la semántica del runbook (`Deploy-PgAutoShutdown.ps1`: zona `America/Mexico_City`,
`StartTimeOfDay` 08:00, `StopTimeOfDay` 20:00 y `weekDays` de lunes a viernes, escritos igual). Leer la
zona una vez al arrancar evita E/S en las peticiones (Principio III): `ZoneInfo` carga el archivo de la
zona de forma síncrona solo en la validación y lo guarda en su caché.

## R13. `zoneinfo` y `tzdata` en la tabla de stack

**Evidencia**.

- Windows, Python 3.14.8 (donde corre la suite local): `zoneinfo.TZPATH` está vacío, `tzdata` no está
  instalado y `ZoneInfo("America/Mexico_City")` lanza `ZoneInfoNotFoundError`. `uv.lock` no incluye
  `tzdata` (ni como dependencia transitiva).
- Imagen del servicio (`python:3.14-slim`, Debian 13): trae el paquete del sistema `tzdata` 2026c en
  `/usr/share/zoneinfo`, y `ZoneInfo` funciona sin el paquete de Python.

**Decisión**. Añadir `tzdata` como dependencia del servicio (`uv add tzdata`: `pyproject.toml` y
`uv.lock`), **sin** marcador de plataforma. `zoneinfo` busca primero los datos del sistema y solo usa el
paquete si no los encuentra; en la imagen sigue usando los del sistema, y en Windows usa el paquete. No se
importa `tzdata` en ningún módulo de `src/`.

**¿Requiere enmienda?** **No**: `tzdata` no es una tecnología, sino la base de datos de zonas de la IANA
empaquetada por el equipo de CPython como la fuente de respaldo de `zoneinfo` (PEP 615); la documentación
de `zoneinfo` recomienda declararla en los proyectos multiplataforma. No añade un «ámbito» a la tabla ni una
API que el código use. Como la tabla de stack enumera hoy todas las dependencias directas, se dejó
**registrado en Complexity Tracking (C2)** y la persona responsable lo aprobó sin enmienda el 2026-10-24. Si
más adelante se prefiere que la tabla lo diga expresamente, basta una enmienda PATCH posterior (por
ejemplo, «Python 3.14 o superior, con `tzdata` como datos de zonas de `zoneinfo`»), que este plan no hace.

**Alternativas descartadas**. Marcador `sys_platform == 'win32'` (la imagen dependería solo de que la base
`python:slim` siga trayendo los datos del sistema; si los perdiera, el servicio no arrancaría con horario);
solo como dependencia de desarrollo (también es un paquete fuera de la tabla y dejaría sin datos un
`uv sync --no-dev` en Windows); desfases fijos en lugar de zonas IANA (contradice FR-033, FR-034 y FR-044).

## R14. SSRF y lista permitida (FR-025, FR-026, FR-027, SC-004)

**Decisión**.

**`base_url`** (validador del DTO; mensajes que no repiten la dirección ni revelan la lista):

1. Se quitan los espacios de los extremos; hasta 255 caracteres; solo ASCII imprimible, sin espacios, sin
   `\`, sin `?` y sin `#` en ningún lugar (así se rechazan también `?` y `#` vacíos, que `urlsplit` no
   distingue).
2. `urlsplit`: esquema `http` o `https` (sin distinguir mayúsculas); `netloc` sin `@` (usuario o
   contraseña); puerto, si lo hay, de 1 a 65 535.
3. Host: IP literal (IPv4, o IPv6 entre corchetes) o nombre ASCII de etiquetas `[a-z0-9-]` de 1 a 63
   caracteres que no empiezan ni terminan con guion, hasta 253 caracteres y sin punto final. Si la última
   etiqueta es solo dígitos, tiene que ser una IP válida (así `2130706433` o `0x7f.1` no pasan por
   nombres).
4. Ruta opcional con las reglas de las rutas de abajo.
5. Se guarda con esquema y host en minúsculas y sin barra final.

**Rutas** (`live_path`, `ready_path`, `info_path`): empiezan con una sola `/`; solo caracteres
`A-Z a-z 0-9 - . _ ~ ! $ & ' ( ) * + , ; = : @ /` (los de un segmento de RFC 3986 **sin** `%`, así no hay
codificaciones tramposas como `%2e%2e` o `%2f`); sin `//`; sin segmentos `.` ni `..`; hasta 200
caracteres. La barra final se permite (`/healthz/`).

**Lista permitida** (`AllowedHosts`, en `src/config.py`): entradas separadas por comas, sin distinguir
mayúsculas y sin espacios alrededor. Una entrada es un host exacto (nombre con las reglas de arriba, o IP
literal sin corchetes) o un sufijo con punto inicial (`.maily.internal`), que admite sus subdominios pero
no el dominio solo ni `otromaily.internal`. Una entrada vacía, un punto solo, `*`, `://`, `/` o un puerto
(`:` que no forma una IPv6 válida) impiden arrancar. La variable vacía (o solo espacios) equivale a no
configurada: sin lista.

**Dónde se comprueba**: al registrar y al cambiar `base_url`, en el Service (422 en `base_url`, FR-030); y en
cada agregación, contra la lista vigente (R8), antes de cualquier llamada.

## R15. Registro de componentes (FR-023 a FR-032, FR-037)

**Decisión** (el DDL completo está en [contracts/database-schema.sql](contracts/database-schema.sql)):

- Tabla `monitored_components`, migración `0004` (revisa `0003`), reversible. `id uuid` con
  `DEFAULT gen_random_uuid()` (nativa desde PostgreSQL 13); `deleted_at timestamptz` es la marca de baja
  lógica (nula = vigente); `updated_at` lo mantiene un disparador nuevo que reutiliza la función
  `set_updated_at()` de la migración 0001 (el `downgrade` de 0004 no la borra).
- `CHECK` que repiten las invariantes del DTO como red de seguridad: formato y longitud de `code` (sin los
  reservados), `name` sin espacios en los extremos ni vacío, `kind` en (`service`, `frontend`),
  `sort_order` de 0 a 9999, un servicio con sus tres rutas y un frontend sin `ready_path`.
- Índice único parcial `monitored_components_code_not_deleted_key` sobre `code` donde `deleted_at IS NULL`:
  decide la unicidad y las carreras (dos altas simultáneas → una 201 y otra 409), igual que el índice del
  nombre de las suscripciones; el Service lo reconoce por su nombre en `UniqueViolationError`.
- **Orden**: `ORDER BY sort_order, code COLLATE "C"`. Con la intercalación del servidor (por ejemplo
  `en_US.UTF-8`, que ignora el guion en la primera pasada) `a-c` y `ab` podrían ordenarse distinto que en
  Python; con `"C"` el orden es el de los puntos de código, el mismo que usa la agregación.
- **Modificación**: en una transacción, `SELECT … FOR UPDATE` de la fila vigente (404 si no está), fusión de
  los campos enviados, valores por defecto de un servicio si pasa de frontend a servicio sin enviar sus
  rutas, validación del resultado con las reglas del alta (422), código reservado (409) y `UPDATE … RETURNING`
  con `commit` (índice único → 409). Dos modificaciones simultáneas se serializan en la fila y la segunda se
  valida sobre el resultado de la primera.
- **Baja**: un `UPDATE … SET deleted_at = CURRENT_TIMESTAMP WHERE id = … AND deleted_at IS NULL RETURNING id`
  atómico (204, o 404 si no aplicó).
- **Base de datos no disponible** (FR-037): el Repository deja pasar la falla, el manejador genérico responde
  500 `internal_error` sin detalles (comportamiento vigente, decisión 23), no se invalida nada y la
  consulta de salud sigue con la copia en memoria.

## R16. Configuración y arranque (FR-038, SC-010)

**Decisión**.

- `HealthSettings` (pydantic-settings, `env_ignore_empty=True` como las demás): `health_check_timeout_seconds`
  (1–10, 3), `health_cache_seconds` (0–300, 15), `health_ready_timeout_seconds` (1–10, 2),
  `health_allowed_hosts` (→ `AllowedHosts`) y las cuatro `database_schedule_*` como texto. Los enteros se
  validan como en `DASHBOARD_RECENT_CLINICS_LIMIT`: solo dígitos ASCII (sin signo, decimales ni espacios
  internos) y dentro del rango.
- `BuildSettings`: `app_commit_sha` (7–64 hexadecimales, se publica en minúsculas), `app_build_date` (ISO 8601
  con zona, se publica en UTC con `Z`) y `app_environment` (1–50 de `[A-Za-z0-9._-]`). Ausentes o vacías →
  `unknown`.
- El horario se valida con `database_schedule_from(settings)`, que conoce los nombres de las cuatro
  variables y lanza `InvalidSettingsError(variables)` nombrando las que faltan o no son válidas (Pydantic no
  puede poner la ubicación de un error entre campos, y un validador de modelo diría «?»).
- `lifespan` carga todas las configuraciones antes de rendirse y `configuration_error_message` se amplía
  para recibir también esos nombres: **un solo mensaje** nombra todas las variables inválidas, nunca sus
  valores (patrón actual).
- **`DATABASE_URL` también se valida al arrancar** (se añade `get_settings` a la lista de `lifespan`). Hoy
  `lifespan` no la carga y el servicio arranca sin ella (el engine se crea al primer uso), aunque la spec
  (FR-005) da por hecho que «no arranca sin `DATABASE_URL`» y la constitución exige no arrancar sin una
  variable obligatoria. Las pruebas no cambian: la fixture de sesión de `tests/conftest.py` siempre la
  define. Como cambia el arranque de una configuración hoy incompleta, se pidió confirmarlo y la persona
  responsable lo aprobó el 2026-10-24. Aun sin este cambio, `/health/ready` nunca emitiría
  `not_configured`: una configuración ausente sería `unexpected_error`.

**Riesgo anotado**. Las pruebas de arranque existentes no aíslan las clases nuevas del `.env` local: con un
valor inválido en una variable nueva de `.env`, fallarían. Las pruebas nuevas aíslan sus clases
(`env_file=None`, como `test_dashboard_startup.py`).

## R17. Datos de build, Dockerfile y Compose (FR-006, FR-009)

**Decisión**.

- `Dockerfile`: al final (después de `COPY src ./src` y antes de `CMD`), `ARG APP_COMMIT_SHA=""`,
  `ARG APP_BUILD_DATE=""` y `ENV APP_COMMIT_SHA=$APP_COMMIT_SHA APP_BUILD_DATE=$APP_BUILD_DATE`. Al final
  para que un commit nuevo no invalide la capa de dependencias (`uv sync`). Sin argumentos, las variables
  quedan vacías: `unknown`.
- `docker-compose.yml`: el servicio `api` pasa `APP_COMMIT_SHA` y `APP_BUILD_DATE` como **argumentos de
  build** (`build.args`), no en `environment`: en Compose, `APP_COMMIT_SHA: ${APP_COMMIT_SHA:-}` en
  `environment` pondría una cadena vacía que taparía el valor horneado en la imagen. `APP_ENVIRONMENT`, las
  `HEALTH_*` y las `DATABASE_SCHEDULE_*` sí van en `environment` (vacías = por defecto), como las variables
  actuales.
- El README documenta cómo construir con
  `--build-arg APP_COMMIT_SHA=$(git rev-parse HEAD) --build-arg APP_BUILD_DATE=…` y el ejemplo de *probes*.

## R18. CORS en las rutas de salud (FR-050)

**Decisión**. No hay código nuevo: `create_app()` añade `CORSMiddleware` a toda la aplicación cuando
`CORS_ALLOWED_ORIGINS` tiene orígenes (`allow_credentials=False`). Las pruebas nuevas comprueban, en
`/health/live`, `/health/ready` (también su 503) y `/health/status`, que un origen permitido recibe
`Access-Control-Allow-Origin` y ninguna `Access-Control-Allow-Credentials`, y que uno no permitido no recibe
cabeceras CORS.

**Evidencia** (`starlette/middleware/cors.py`, 1.8.0): en una petición simple, el middleware añade
`Access-Control-Allow-Origin` (y `Vary: Origin`) a cualquier respuesta, también a un 503 que devuelve la
ruta, si el origen está permitido. Un `GET` sin `Authorization` (el del Backoffice a `/health/status`) no
necesita *preflight*.

El proxy del Backoffice (si existe) es configuración de maily-backoffice 016, no de este repositorio.

## R19. OpenAPI (Principio IV, FR-008, FR-045)

**Decisión**. Una etiqueta nueva, «Salud», para las diez operaciones (la página del Backoffice es «Salud
de servicios»); identificadores de operación de FR-001. Cada operación declara `response_model`, códigos y
descripciones en español; las cuatro públicas, sin `security` ni `x-required-permission`; las seis
protegidas, con `BearerAuth` y su permiso (`protected`). Las respuestas 200 de salud documentan
`Cache-Control: no-store`. El 503 de `/health/ready` documenta el mismo esquema que su 200 (`ReadyRead`):
no es un error de la API, es la respuesta de disponibilidad del contrato v1. El alta devuelve `Location`
como las suscripciones. El contrato está en [contracts/openapi-health.yaml](contracts/openapi-health.yaml).

## R20. Pruebas (Principio V, FR-041, FR-049)

**Decisión**.

- **Reloj controlable**: `FakeClock` (en `tests/health_support.py`) con `now()` y `monotonic()` que se
  avanzan a mano; se inyecta sobrescribiendo `get_clock`. Las latencias usan `perf_counter` y no dependen
  del reloj falso.
- **Simulación de componentes**: `tests/stubs/components/app.py`, autocontenida como las otras (no importa
  `src/`), que imita servicios y frontends por prefijo de ruta (`/healthy`, `/not-ready`, `/html`,
  `/not-json`, `/redirect`, `/slow`, `/too-large`, `/info-incomplete`, `/frontend`…), registra las
  cabeceras de cada llamada y ofrece `/__test__/` para cambiar el modo y leer las llamadas. pytest la monta
  en memoria con `httpx.ASGITransport`; la pila de punta a punta la levanta como contenedor.
- **Fallas de red**: un transporte de pruebas envuelve al ASGI y, según el host, lanza `httpx.ConnectError`
  con `socket.gaierror` como causa (DNS) o con `ConnectionRefusedError` (conexión). Opcional y marcada
  `slow`: una prueba con un nombre `.invalid` (RFC 6761) para ver la cadena real de excepciones.
- **Tiempos cortos**: el Service recibe los tiempos como valores, así que las pruebas usan 0,2 s sin pasar
  por la validación del entorno (de 1 a 10).
- **Capas**: Service con dobles (sondeo, lector del registro, consulta a la base, reloj); integración con la
  simulación; Router por HTTP; Repository y migración contra PostgreSQL 17 real; Postman de punta a punta.
- **Sin servicios reales**: el API de usuarios es la simulación actual (`tests/stubs/users_api`, que ya
  acepta cualquier permiso con forma `recurso:acción`, así que concede y niega los cuatro `health:*` sin
  cambios).

## R21. Ajustes a las pruebas existentes (FR-039, FR-040)

El barrido (`grep` de `PUBLIC_ROUTES`, `len(ErrorCode)`, `security`, `operation_ids_of_the_api` y de las
fixtures compartidas) encontró los puntos que dan por hechas «estas operaciones» o «estos códigos». La
tabla completa, con el porqué de cada uno, está en el plan («Ajustes a las pruebas existentes»). Ninguno
cambia una comprobación de comportamiento de suscripciones o del dashboard.

## R22. Colección de Postman y pila de punta a punta (FR-042, SC-012)

**Decisión**. Colección nueva `tests/postman/collections/MailySoft-System-Salud.postman_collection.json`
(v2.1), con su prueba guardiana `tests/contract/test_health_postman_collection.py` (reglas G1 a G9 de
[contracts/e2e-collection.md](contracts/e2e-collection.md)). La pila `maily-system-e2e` añade el servicio
`components-stub` y pasa a la API `HEALTH_ALLOWED_HOSTS=components-stub`, `HEALTH_CACHE_SECONDS=0` y
`HEALTH_CHECK_TIMEOUT_SECONDS=2`. El entorno `e2e` gana `componentsStubUrl`; `package.json`, el script
`e2e:health` (y `e2e:all` lo incluye). Las colecciones existentes no se tocan (FR-040).

## R23. Registros (logs) (FR-021, Principio VIII)

**Decisión**. Un aviso (`WARNING`) cuando un componente cambia de estado entre dos agregaciones del
proceso, y cuando cambia el resultado de `/health/ready`, con el código del componente, el estado y el
código de la falla. Sin aviso en cada ronda (con la base detenida de noche serían miles). Una excepción
inesperada del agregador se registra con su tipo, sin mensaje ni traza (podrían incluir la dirección).
Nunca dirección, token, cabeceras ni cuerpos.

## R24. Alineación con mailySoft-usuarios 016 y mailySoft-pacientes 008 (decisión 22)

**Evidencia**: las tres specs usan `HEALTH_READY_TIMEOUT_SECONDS`, `APP_COMMIT_SHA`, `APP_BUILD_DATE` y
`APP_ENVIRONMENT`, y el mismo cuerpo de `ready` (incluido `not_configured`) y de `info`. No hay nombres que
alinear. Diferencia observada, que no bloquea: pacientes 008 acepta decimales en
`HEALTH_READY_TIMEOUT_SECONDS` (0,1 a 10) y, si es inválida, avisa y usa el valor por defecto; esta spec
admite enteros de 1 a 10 y no arranca con un valor inválido. Cada servicio valida su configuración; el
contrato común no cambia.

# Investigación (Fase 0): API REST de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Fecha**: 2026-10-17

Este documento resuelve las decisiones técnicas del plan. La base es la constitución v1.0.0 y el
repositorio de referencia `mailySoft-usuarios` (constitución v1.5.0, specs 001–008), del que se
reutilizan patrones ya probados. Cada decisión indica su motivo y las alternativas descartadas.

**Evidencia medida** (entorno de la referencia, `C:\maily\code\mailySoft-usuarios\.venv`, sin instalar
nada): Python 3.15.0, FastAPI 0.143.2, Pydantic 2.14.1, httpx 0.28.1, Starlette 1.8.0. Las pruebas de
R4, R10 y R14 se ejecutaron ahí con un script desechable; sus resultados se citan en cada decisión.

**Puntos que conviene confirmar fuera de este repositorio** (no bloquean el plan; ver R2 y R5):

1. El API de usuarios debe tener publicada la operación de consulta de permisos de su spec 008 (a la
   fecha, su especificación y su plan existen; su código aún no la sirve) y el catálogo debe incluir
   `subscriptions:read|write|update|delete`.
2. El API de clínicas debe ofrecer el conteo por suscripción tal como lo define
   [contracts/clinics-api-integration.md](contracts/clinics-api-integration.md) y aceptar el token de la
   persona que llama (R5).

---

## R1. Base del proyecto: se replica la de la referencia

- **Decisión**: mismo esqueleto y herramientas que `mailySoft-usuarios`: `pyproject.toml` con uv
  (`package = false`, `uv.lock`), `Dockerfile` de una etapa sobre `python:3.14-slim`
  (`uv sync --frozen --no-dev`), `docker-compose.yml` con `db` (postgres:17), `migrate` y `api`,
  Alembic en modo async, pytest con `asyncio_mode = "auto"` y bucle de sesión. Dependencias de
  producción: `alembic`, `asyncpg`, `fastapi`, `httpx`, `pydantic-settings`, `sqlalchemy[asyncio]<2.1`,
  `uvicorn`. De desarrollo: `pytest`, `pytest-asyncio`, `python-dotenv`.
- **Diferencia con la referencia**: **no** hay `pyjwt[crypto]`; el token no se verifica aquí (R2).
  `httpx` va en producción porque el servicio llama a otras APIs (Principio III) y el `Dockerfile`
  instala con `--no-dev`.
- **Motivo**: la persona responsable pidió el mismo stack y las mismas reglas; el esqueleto ya está
  validado en Python 3.14/3.15.
- **Alternativas**: Poetry/pip (la constitución fija uv); varias etapas en el `Dockerfile` (sin
  beneficio con `--no-dev` y wheels disponibles).
- **A verificar al implementar**: que `uv lock` resuelva las mismas versiones mínimas que la
  referencia (`fastapi>=0.143`, `httpx>=0.28`, `pydantic-settings>=2.6`, `alembic>=1.14`,
  `asyncpg>=0.30`, `uvicorn>=0.30`).

## R2. Control de acceso: reenviar el token al API de usuarios

- **Decisión** (confirmada por la persona responsable, sesión 2026-10-17): cada operación llama a
  `GET {USERS_API_BASE_URL}/api/v1/authorization/check?permission=<permiso>` con la cabecera
  `Authorization: Bearer <token>` recibida, sin modificarla. Contrato y tabla de traducción en
  [contracts/users-api-integration.md](contracts/users-api-integration.md).
  - `200` con `allowed: true` → se ejecuta la operación.
  - `200` con `allowed: false` → `403 permission_denied`.
  - `401` del API de usuarios (`unauthenticated`, `token_expired`, `invalid_token`) → el mismo código
    aquí con su `WWW-Authenticate`; un `401` con cuerpo ilegible → `invalid_token`.
  - Cualquier otra cosa (tiempo agotado, conexión rechazada, 5xx, 429, 4xx inesperado, cuerpo que no
    es el esperado o cuyo `permission` no coincide con el pedido) → `503 authorization_unavailable`.
    **Falla cerrada**: jamás se ejecuta la operación.
- Sin cabecera `Authorization`, con otro esquema que `Bearer`, o con un token de más de **8 192
  bytes**, la petición se rechaza localmente (`unauthenticated` / `invalid_token`) sin llamar al API
  de usuarios. El tope evita reenviar cabeceras desmesuradas. El cliente **no sigue redirecciones** (`follow_redirects=False`): una respuesta `3xx` es «no disponible» y el token jamás viaja a otro servidor (FR-024); y el arranque advierte si una dirección usa `http://` no local (R14).
- **Sin caché** de decisiones (Principio VIII y SC-003): una llamada por petición protegida. El costo
  es una ida y vuelta de red por petición; según la investigación de la spec 008 de la referencia, su
  consulta de permisos tarda 3,2 ms de media (8 clientes, 110 000 usuarios), así que el tiempo lo
  domina la red, no el API de usuarios.
- **Sin reintentos** automáticos: las consultas son idempotentes, pero reintentar duplica la espera
  máxima y el cliente ya puede reintentar.
- **Motivo**: un solo servicio decide identidad y permisos; este servicio no duplica criptografía,
  claves ni configuración de Auth0.
- **Alternativas descartadas**: verificar el JWT aquí con PyJWT y consultar solo permisos (duplica
  configuración de Auth0 y añade `cryptography`; descartada por la persona responsable); cachear
  decisiones unos segundos (retrasa bloqueos; prohibido por el Principio VIII).
- **Riesgo conocido**: si el API de usuarios cae, **todo** este servicio responde 503 salvo la
  documentación. Es la consecuencia buscada de fallar cerrado.

## R3. Cómo se declara y se comprueba el permiso de cada ruta

- **Decisión**: `src/security.py` expone el esquema `HTTPBearer(scheme_name="BearerAuth",
  auto_error=False)`, una dependencia que extrae el token y una fábrica `require_permission(nombre)`
  que devuelve una dependencia. Esa dependencia llama a `AuthorizationService.require(token,
  permiso)` (Service), que usa `UsersApiClient` (`src/integrations/`). Cada Router la aplica con
  `dependencies=[Depends(require_permission("subscriptions:read"))]`.
- Un ayudante en `src/routers/openapi_docs.py` (`protected(permission)`) devuelve de una vez la
  dependencia, `openapi_extra={"x-required-permission": permission}` y las respuestas documentadas
  401, 403 y 503, para que declarar el permiso y documentarlo sea **un único gesto**.
- **Prueba de cobertura** (`tests/contract/test_permission_coverage.py`): recorre `app.routes` y el
  OpenAPI generado y falla si una ruta no tiene `x-required-permission` y no está en la lista de
  excepciones públicas (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`); y compara las
  rutas con la matriz esperada, de modo que ni sobre ni falte ninguna.
- **Ampliar la lista** (requisito de la persona responsable): una operación nueva = una fila en la
  matriz ([contracts/permission-matrix.md](contracts/permission-matrix.md)), `protected("...")` en su
  ruta y el permiso dado de alta en el catálogo del API de usuarios. No exige enmendar la
  constitución.
- **Motivo**: el reference hizo lo mismo (`require_permission` + `x-required-permission` + prueba que
  recorre las rutas) y la constitución lo exige (Principios V y VIII).
- **Alternativas**: un middleware ASGI (resuelve el caso del JSON roto de R4, pero no documenta el
  permiso en OpenAPI y se salta la inyección de FastAPI); un decorador propio (reinventa
  `Depends`).

## R4. Precedencia de errores (identidad → permiso → validación)

- **Decisión**: la comprobación es una dependencia de la ruta, y FastAPI resuelve las dependencias
  antes de validar ruta, consulta y cuerpo. Orden resultante: identidad → permiso → validación →
  existencia y reglas de negocio.
- **Evidencia (script desechable)**: sin token y con cuerpo válido → `401`; sin token y con cuerpo
  inválido (`monthly_price: -5`) → `401` (no `422`); con token y cuerpo inválido → `422`. **Excepción aceptada (spec FR-004, clarificación del 2026-10-17)**: un cuerpo que no es JSON sintácticamente válido → `422` incluso sin token, porque
  Starlette lo decodifica antes de las dependencias. Es la misma limitación que acepta la referencia (precedencia 1 de su catálogo de errores); no revela datos y se documenta en el catálogo de errores. La desviación respecto al Principio VIII se justifica en Complexity Tracking del plan; alternativas descartadas: leer el cuerpo a mano en las 3 rutas que lo reciben (se pierde el esquema de entrada en OpenAPI y la validación de Pydantic) o un middleware ASGI (no documenta el permiso).
- **Motivo**: cumple la spec (historia 2, escenario 6) para todo lo que no sea JSON roto, sin código
  extra.

## R5. Integración con el API de clínicas (conteo por suscripción)

- **Decisión**: una sola operación consumida,
  `GET {CLINICS_API_BASE_URL}/api/v1/clinics/subscription-counts[?subscription_id=…]`, que devuelve el
  número de clínicas por suscripción solo para las que tienen al menos una (`items[]` con
  `subscription_id` y `clinics_count`); una suscripción ausente del resultado tiene 0 clínicas
  **porque el API respondió** (un cero verdadero, no inventado). Sin `subscription_id` devuelve todas;
  con uno o varios, solo esas. Detalle en
  [contracts/clinics-api-integration.md](contracts/clinics-api-integration.md).
- **Autenticación hacia el API de clínicas**: se **reenvía el token de la persona** que llama (como
  con el API de usuarios). No hay credenciales de servicio, no hay secretos nuevos y este servicio no
  habla con Auth0 (Principio VIII). Consecuencia: el API de clínicas decide si esa persona puede leer
  los conteos; si responde `401` o `403`, el conteo queda «no disponible» (en lecturas) o la
  eliminación se rechaza por no poder comprobarse (R7).
- **Este contrato es una propuesta de este repositorio**: el API de clínicas todavía no está
  especificado aquí (la spec lo delega a la planificación). Hasta que exista, las pruebas usan su
  simulación y, en producción, el conteo sale como «no disponible» (comportamiento ya especificado).
- **Alternativas descartadas**: una consulta por suscripción (N+1 en el catálogo); credenciales de
  máquina a máquina con Auth0 (rompe la regla de no hablar con Auth0 y añade un secreto); clave
  compartida en variable de entorno (un secreto más y se salta el permiso de la persona).
- **Punto a confirmar** con quien mantenga el API de clínicas: nombre de la operación, que acepte el
  token de la persona y el permiso que exige (p. ej. `clinics:read`).

## R6. Lecturas con degradación y ejecución en paralelo

- **Decisión**:
  - **Listado**: el API de clínicas se consulta **sin filtro** (todas las que tienen clínicas), así que
    no depende de los identificadores y se ejecuta **en paralelo** con la lectura de la base de datos
    (`asyncio.gather`). Si falla, el conteo de **todas** las suscripciones es `null`.
  - **Detalle, actualización y cambio de estatus**: la lectura o escritura de la base de datos va
    primero (para devolver `404` sin molestar al API de clínicas) y luego se consulta el conteo de esa
    suscripción; si falla, `clinics_count` es `null` y la operación **sigue siendo exitosa**.
  - **Creación**: la suscripción acaba de nacer, así que no puede tener clínicas: `clinics_count` es `0`
    **sin llamar** al API de clínicas (un cero verdadero, no inventado).
- **Motivo**: cumple FR-009 y SC-005 (nada de la lectura depende del API de clínicas) y mantiene el
  catálogo cerca del mayor de los dos tiempos, no de su suma (SC-001).
- **Alternativas**: caché del conteo (datos viejos y estado compartido; no necesario con ≤ 100
  planes); esperar al API de clínicas antes de leer la base de datos (suma las esperas).

## R7. Eliminación: comprobar clínicas y baja lógica atómica

- **Decisión**: `delete` = (1) leer que la suscripción exista y no esté Eliminada (`404`);
  (2) preguntar al API de clínicas por **esa** suscripción: si falla de cualquier modo →
  `503 clinics_check_unavailable`, si trae ≥ 1 → `409 subscription_has_clinics`; (3) `UPDATE …
  SET status_id = 4 WHERE id = :id AND status_id <> 4 RETURNING id`; si no devuelve fila (otra
  petición la eliminó antes) → `404`. Nunca se mantiene una transacción abierta durante la llamada de
  red.
- **Riesgo residual declarado**: entre (2) y (3) otro sistema podría asignar una clínica a la
  suscripción; una comprobación entre dos servicios no puede ser atómica. Se mitiga fuera de este
  servicio (el API de clínicas no debería asignar suscripciones Eliminadas, que ya no se pueden
  consultar aquí) y queda anotado en el plan; no se añaden bloqueos distribuidos (YAGNI).
- **Bloquear e inactivar** no consultan al API de clínicas (Clarifications: se permiten siempre).
- **Motivo**: es la regla confirmada (Q1 = A) y respeta los Principios VIII y IX (lecturas
  disponibles; la escritura destructiva falla cerrada).

## R8. Catálogo de estatus y baja lógica

- **Decisión**: tabla `subscription_statuses` (como `role_statuses` de la referencia) con ids
  1 Activa, 2 Inactiva, 3 Bloqueada y 4 Eliminada, cargada por migración (Principio VI). El código
  reconoce los estatus **por su identificador** (`SubscriptionStatus.ACTIVE = 1`, `INACTIVE = 2`,
  `BLOCKED = 3`, `DELETED = 4`), nunca por su nombre. Una suscripción es **vigente** si su estatus es
  distinto de 4: un estatus añadido a mano (id ≥ 5) aparece en el catálogo con su estatus y solo puede
  cambiarse a 1, 2 o 3. La secuencia se ajusta a 4 para que los estatus manuales empiecen en 5.
- **Estatus como objeto** `{id, name}` en todas las respuestas; quien consume la API se basa en `id`
  (FR-022).
- **Alternativas**: columna `status` con `CHECK`/enum de PostgreSQL (cambiar un estatus exige
  migración y la constitución habla de un catálogo administrable); borrado físico (descartado por la
  persona responsable).

## R9. Modelo de datos

- **Decisión**: dos tablas (`subscription_statuses`, `subscriptions`); detalle en
  [data-model.md](data-model.md) y [contracts/database-schema.sql](contracts/database-schema.sql).
  - `monthly_price numeric(10,2) NOT NULL CHECK (>= 0)` (Principio VI: nunca `float`).
  - `features text[] NOT NULL DEFAULT '{}'` con `CHECK (cardinality(features) <= 20)`: lista ordenada de
    textos libres (Clarifications Q2 = A). El largo de cada texto (1–150) lo valida el DTO.
  - `created_at` y `updated_at` `timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`; `updated_at` lo
    mantiene un disparador `BEFORE UPDATE`, igual que en `users` de la referencia (cualquier cambio,
    incluido el de estatus, actualiza la fecha de última modificación).
- **Evidencia (PostgreSQL 17 desechable, imagen `postgres:17`)**: el DDL de
  [contracts/database-schema.sql](contracts/database-schema.sql) se aplica sin errores; `4500` se
  guarda y devuelve como `4500.00`; el precio negativo, el nombre en blanco, más de 20 funciones y un
  estatus inexistente se rechazan con las restricciones `subscriptions_monthly_price_check`,
  `subscriptions_name_check`, `subscriptions_features_check` y `subscriptions_status_id_fkey`; un
  precio de 100 000 000 desborda `numeric(10,2)` (el DTO lo rechaza antes, R10); el disparador cambia
  `updated_at` en un `UPDATE`; los nombres automáticos de las restricciones son los previstos.
- **Alternativas**: `jsonb` para las funciones (acepta cualquier cosa; hay que validar tipos fuera de
  la base de datos); tabla hija `subscription_features(position, text)` (más tablas y una consulta
  extra para una lista que solo se lee y escribe completa, sin búsquedas por función).
- **Sin tabla de clínicas ni de asignaciones** (R5, Principio IX).

## R10. Precio en la API

- **Decisión**: `Decimal` con `max_digits=10, decimal_places=2, ge=0` en el DTO de entrada, aceptando
  número JSON o cadena numérica; en la salida, **cadena decimal con dos decimales** (`"4500.00"`).
- **Evidencia (script desechable)**: `4500`, `4500.5`, `"4500.50"`, `1e3` y `0` se aceptan; `4500.555`
  → `decimal_max_places`; `-1` → `greater_than_equal`; `100000000` → `decimal_whole_digits`;
  `"abc"` → `decimal_parsing`; `null` → `decimal_type`. Un `Decimal` se serializa a JSON como **cadena**
  y conserva los ceros (`Decimal('1500.00')` → `"1500.00"`), pero lo que se acepta sin ceros se
  serializaría sin ellos (`"4500"`): por eso la respuesta se construye **siempre desde la fila
  recargada** (el `NUMERIC(10,2)` ya trae dos decimales) y el DTO de salida añade un serializador que
  fija dos decimales.
- **Tope**: 99 999 999,99 (lo que cabe en `numeric(10,2)`); un valor mayor es un error de validación,
  nunca un error interno.
- **Alternativas**: entero en centavos (obliga a todos los consumidores a convertir y no coincide con el
  Front, que muestra pesos); número JSON (los consumidores en JavaScript perderían precisión).

## R11. Unicidad del nombre y concurrencia

- **Decisión**: índice único parcial funcional
  `subscriptions_name_not_deleted_key ON subscriptions (lower(name)) WHERE status_id <> 4`, como el de
  roles. El Service **no comprueba antes**: intenta escribir y traduce `UniqueViolationError` por el
  nombre del índice a `409 subscription_name_already_exists`; así dos solicitudes simultáneas no
  compiten (SC-006). Los textos se recortan en el DTO, de modo que « Pro » y «Pro» son el mismo
  nombre. Una Inactiva o Bloqueada sigue reservando su nombre; el de una Eliminada queda libre.
- **Nota**: `lower()` depende de la configuración regional de la base de datos. **Evidencia** (imagen
  `postgres:17`, UTF-8): `Pro` y `pro` chocan, `Básico` y `BÁSICO` chocan, el nombre de una Eliminada
  queda libre y el de una Inactiva sigue reservado. Una prueba de integración lo fija.
- **Alternativas**: comprobar y luego insertar (carrera); `citext` (extensión extra sin necesidad).

## R12. Cambio de estatus atómico

- **Decisión**: una sola sentencia
  `UPDATE subscriptions SET status_id = :nuevo WHERE id = :id AND status_id <> 4 AND status_id <> :nuevo
  RETURNING id`. Si devuelve fila → recargar y responder. Si no → leer el estatus: no existe o es
  Eliminada → `404`; ya tiene el estatus pedido → `409 subscription_status_unchanged`.
- **Validación**: el cuerpo es `{ "status_id": n }` y solo admite 1, 2 o 3; `4`, un número desconocido
  o un tipo equivocado → `422 validation_error` (campo `status_id`). Un identificador > 2 147 483 647
  se trata como «no existe» sin consultar (patrón `INT4_MAX` de la referencia).
- **Operación única** `PATCH /api/v1/subscriptions/{id}/status` en lugar de un verbo por estatus: con
  tres estatus manejables, un cuerpo con el id evita tres rutas y tres filas de permiso idénticas.
- **Alternativas**: `block`/`unblock` como en la referencia (no alcanzan para tres estatus);
  `PUT …/status` (su semántica idempotente contradice el `409` por estatus repetido de la spec).

## R13. Listado sin paginar

- **Decisión**: `GET /api/v1/subscriptions` devuelve un **arreglo JSON** (como `GET /roles` en la
  referencia) con las suscripciones vigentes, ordenadas por `created_at` ascendente y `id` ascendente
  (FR-006). Cantidad esperada ≤ 100; umbral para devolver completo ≤ 500 (Principio IV). No se aplica
  `LIMIT`: truncar en silencio sería peor que superar el umbral; si el catálogo lo supera, el cambio a
  paginado es una versión nueva del contrato. Una prueba de integración carga 500 suscripciones y
  comprueba el orden y el tiempo (SC-001).
- **Alternativas**: envoltorio `{items, total}` (anticiparía una paginación que el Principio IV exige
  versionar de todos modos); orden alfabético (el Front hoy muestra el orden de creación).

## R14. Configuración y arranque

- **Decisión**: `src/config.py` con dos clases de `pydantic-settings`: `Settings` (base de datos, como
  la referencia) y `IntegrationSettings` (`USERS_API_BASE_URL`, `USERS_API_TIMEOUT_SECONDS`
  [por defecto 5], `CLINICS_API_BASE_URL`, `CLINICS_API_TIMEOUT_SECONDS` [por defecto 5],
  `CORS_ALLOWED_ORIGINS` opcional). Las URL deben ser `http(s)` y se normalizan sin `/` final; los
  tiempos, mayores que 0 y no más de 30 s.
- **Arranque** (`lifespan`): valida `IntegrationSettings` y crea **un** `httpx.AsyncClient`
  compartido (con `limits` acotados), que cierra al terminar. Si falta una variable obligatoria el
  servicio **no arranca** y el mensaje nombra **solo las variables** que faltan o son inválidas, nunca
  sus valores (el `ValidationError` de Pydantic repite el valor recibido; se captura y se reescribe).
  `create_app()` no abre conexiones ni exige variables (solo lee `CORS_ALLOWED_ORIGINS`, opcional), para poder importarla en las pruebas. El arranque registra una **advertencia** por cada dirección `http://` cuyo host no es `localhost`, `127.0.0.1`, `::1` ni un nombre sin punto (FR-024); la advertencia nombra la variable, nunca la dirección ni credenciales, y no impide arrancar porque las redes privadas entre servicios suelen usar `http` (clarificación del 2026-10-17).
- **Tiempo máximo total** por llamada: `asyncio.timeout(n)` envolviendo la llamada de `httpx`
  (el `Timeout` de `httpx` limita cada fase por separado, no el total). Evidencia: `asyncio.timeout`
  lanza `TimeoutError` a los 0,1 s en el entorno de referencia.
- **Alternativas**: leer las variables en cada petición (error tardío); un cliente `httpx` por
  petición (pierde el *pool* de conexiones).

## R15. Pruebas: simulaciones de los dos APIs

- **Decisión**: dos aplicaciones FastAPI autocontenidas, `tests/stubs/users_api/app.py` y
  `tests/stubs/clinics_api/app.py` (no importan nada de `src/`), con estado en memoria y una superficie
  `/__test__/…` para montar escenarios y fallos. Se usan de dos maneras, igual que `auth0_stub` en la
  referencia: **en pytest** con `httpx.ASGITransport` (sin red ni Docker) inyectadas en el cliente
  compartido, de modo que **el código real de los clientes** (traducción de respuestas y de fallos) se
  ejercita; y **en la pila e2e** como servicios de Docker Compose. Detalle en
  [contracts/e2e-stubs.md](contracts/e2e-stubs.md).
- **Capas de pruebas** (Principio V): Services con dobles de los clientes (`FakeUsersApi`,
  `FakeClinicsApi`) y del Repository; Repositories contra PostgreSQL 17 real; endpoints por HTTP contra
  la aplicación con las simulaciones; Postman/Newman solo de punta a punta.
- **Ninguna prueba llama a un API real** (Principio V): las simulaciones reproducen también los fallos
  (sin permiso, token rechazado, tiempo agotado, caída, cuerpo inesperado).
- **Alternativas**: `respx`/`pytest-httpx` (dependencia nueva fuera de la tabla del stack); mockear el
  cliente por completo (no probaría su traducción de errores).

## R16. Pila de punta a punta con Newman

- **Decisión**: proyecto de Compose aislado `maily-system-e2e` (`tests/postman/docker-compose.e2e.yml`):
  base de datos desechable sin puerto publicado, `api` solo en `127.0.0.1:8011`, y dos servicios
  nuevos que ejecutan las simulaciones con la imagen del proyecto montando `tests/stubs/*` en modo
  lectura (puertos de Newman en `127.0.0.1:8012` y `8013`). La colección vive en `tests/postman/`
  y una prueba (`test_postman_collection.py`) falla nombrando las operaciones que faltan o sobran
  respecto al OpenAPI. Newman solo como herramienta de desarrollo (Node fuera de la imagen).
- **Motivo**: es lo que exige la constitución (Postman complementa a pytest, pila aislada, sin
  secretos: el bloque Bearer solo referencia `{{accessToken}}`).

## R17. Entorno local

- **Decisión**: base de datos `maily_system` y de pruebas `maily_system_test` (el nombre debe terminar
  en `_test`; la suite se niega a ejecutarse si no, como en la referencia). Puertos por defecto
  distintos de los de la referencia para poder tener ambos servicios levantados en el mismo equipo:
  PostgreSQL `5434` y API `8010` (el `5433` ya lo ocupa la base de datos de `mailySoft-usuarios` en este equipo; se comprobó al implementar).
- **Alternativas**: reutilizar 5432/8000 (choca con `mailySoft-usuarios`, que es justo el servicio al
  que este llama en local).

## R18. CORS

- **Decisión**: variable opcional `CORS_ALLOWED_ORIGINS` (lista separada por comas); vacía = sin CORS.
  Si se define, `CORSMiddleware` con esos orígenes, métodos de la API y cabeceras `Authorization` y
  `Content-Type`, sin credenciales ni comodines.
- **Motivo**: es requisito de la spec (FR-025): el Front es una aplicación de navegador y, por clarificación del 2026-10-17, llama directamente a la API; sin CORS el navegador bloquearía las respuestas. Desactivada por defecto (sin lista, ningún sitio web). Se prueba en `tests/unit/test_main.py`.

## R19. Registros (logs) y secretos

- **Decisión**: el token nunca se escribe en un registro, mensaje de error ni respuesta; los errores
  inesperados registran la ruta y la traza (en inglés), nunca el cuerpo ni las cabeceras; el nivel de
  `httpx` se fija en `WARNING` (a `INFO` imprime cada URL). Las fallas de los otros APIs se registran
  con el código de estado y la operación, sin cuerpo. Una prueba fija que ningún mensaje de error
  contenga el token enviado.

## R20. Versionado y compatibilidad

- **Decisión**: es el primer contrato del servicio, publicado bajo `/api/v1` con OpenAPI `1.0.0`. No hay
  cambio incompatible que versionar (Principio IV). Pasar el listado a paginado, si algún día el
  catálogo supera 500, sería `/api/v2`.

## R21. Límites de entrada (de la spec, verificados)

| Dato | Regla | Dónde se valida |
|---|---|---|
| `name` | 1–100 caracteres tras recortar; no puede ser nulo | DTO + `CHECK` (no vacío) |
| `description` | hasta 500; vacía o `null` = sin descripción | DTO + `varchar(500)` |
| `monthly_price` | ≥ 0, ≤ 99 999 999,99, ≤ 2 decimales | DTO + `numeric(10,2)` + `CHECK` |
| `features` | hasta 20 elementos de 1–150 caracteres (recortados); puede estar vacía | DTO + `CHECK (cardinality ≤ 20)` |
| Campos desconocidos | se rechaza toda la solicitud, indicando el campo | DTO (`extra="forbid"`) |
| Actualización vacía | `{}` se rechaza: hay que enviar al menos un dato | DTO |
| `subscription_id` | entero positivo; > `INT4_MAX` = no existe | Router + Repository |

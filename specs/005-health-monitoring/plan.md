# Implementation Plan: Monitoreo de salud de los servicios de Maily

**Branch**: `005-health-monitoring` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-health-monitoring/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

La MailySoft System API pasa a ser el **agregador de salud** de Maily. Cumple el contrato de salud v1 en su
raíz (`/health/live`, `/health/ready` con la base de datos e `/info` con versión, commit, fecha de build y
entorno), publica sin token un **estado público** mínimo (`/health/status`), ofrece la **consulta agregada**
`GET /api/v1/health` (permiso `health:read`, siempre 200) con este servicio, la base de datos de Azure y los
servicios y frontends **registrados** en la tabla `monitored_components`, administrable con cinco operaciones
`health:*` y protegida contra SSRF con `HEALTH_ALLOWED_HOSTS`. La base de datos fuera del horario del runbook
se informa `stopped` con su próximo encendido, y si el registro no puede leerse se sigue informando con la
última copia en memoria.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Versión única (R1)**: `VERSION = "2.0.0"` en `src/__init__.py`; `pyproject.toml` pasa de `0.1.0` a `2.0.0`;
  una prueba exige que coincidan con el OpenAPI y con `/info`. La versión publicada no cambia.
- **Rutas públicas (R3, R19)**: un router sin dependencias de seguridad, en la raíz y con la etiqueta «Salud».
  `/health/live` devuelve una constante sin tocar nada; `/health/ready` solo consulta la base de datos.
- **Llamadas a los componentes (R6, R7)**: un cliente httpx propio, solo `GET`, con tiempo máximo **total**
  por llamada (`asyncio.timeout`), sin reintentos, sin redirecciones, sin keep-alive, sin cookies ni
  `trust_env`, sin el token de la persona, `Accept-Encoding: identity` y lectura cruda de 64 KiB como
  máximo; las respuestas se depuran a los campos del contrato v1.
- **Agregación (R8, R9)**: base de datos y registro en paralelo; los chequeos de los registrados empiezan al
  conocerse la lista; reglas de estado y estado global en el Service; `maily-system-api` se calcula dentro
  del proceso, sin llamarse por HTTP.
- **Caché compartida (R10)**: `HealthState` por proceso con el último resultado, **una** agregación en curso y
  un contador de generación; edad máxima `HEALTH_CACHE_SECONDS` en la consulta y `max(HEALTH_CACHE_SECONDS,
  15)` en el estado público; los cambios del registro invalidan.
- **Copia del registro (R11)**: tupla inmutable que se renueva en cada lectura exitosa; `None` = nunca leído.
- **Horario (R12, R13)**: `zoneinfo` con `tzdata` (nueva dependencia de datos, sin enmienda: aprobado, C2);
  ventana `[inicio, fin)` en la hora local; `next_start_at` con el hueco y el doble horario del cambio de
  horario de verano resueltos (verificado con los ejemplos de la spec).
- **Registro (R14, R15)**: migración Alembic `0004` reversible; baja lógica con `deleted_at`; índice único
  parcial del código; orden `COLLATE "C"`; modificación con `SELECT … FOR UPDATE`; formato estricto de
  `base_url` y rutas y lista permitida al registrar y en cada agregación.
- **Configuración y build (R16, R17)**: once variables nuevas validadas al arrancar en un solo mensaje;
  `Dockerfile` con `ARG`/`ENV` de `APP_COMMIT_SHA` y `APP_BUILD_DATE`; README con las *probes* de
  Kubernetes.
- **CORS (R18)**: el middleware global ya cubre las rutas de salud (FR-050); se añaden pruebas.
- **Pruebas (R20 a R22)**: reloj controlable, simulación de componentes compartida por pytest y Newman, base
  de datos real para el Repository; colección de Postman nueva; diez ajustes enumerados a pruebas e
  infraestructura existentes, ninguno de comportamiento.

## Technical Context

**Language/Version**: Python 3.14+ (desarrollo: 3.14.8 en Windows; imagen: 3.14.9 en Debian 13)

**Primary Dependencies**: las del proyecto (FastAPI 0.143.3 sobre Starlette 1.8.0, Pydantic 2.14.1 +
pydantic-settings 2.16.0, SQLAlchemy 2.0.55 async + asyncpg 0.32.0, Alembic 1.20.0, httpx 0.28.1, uvicorn
0.54.0) y la biblioteca estándar (`zoneinfo`, `ipaddress`, `asyncio`, `tomllib` en las pruebas). **Nueva**:
`tzdata` (datos IANA de zonas para `zoneinfo`; [R13](research.md#r13-zoneinfo-y-tzdata-en-la-tabla-de-stack),
Complexity Tracking C2). Desarrollo: pytest 9.1.1, pytest-asyncio 1.4.0; herramienta aparte: Newman 6.2.3.

**Storage**: PostgreSQL 17. Una tabla nueva, `monitored_components` (migración 0004); ninguna otra cambia.
Sin almacenamiento propio del resultado de salud: vive en la memoria del proceso.

**Testing**: pytest + pytest-asyncio + httpx. Service con dobles y `FakeClock`; integraciones contra la
simulación de componentes en memoria (`httpx.ASGITransport`) y un transporte con fallas de DNS y conexión;
endpoints por HTTP con la simulación del API de usuarios; Repository y migración contra PostgreSQL 17 real;
prueba de cobertura de permisos; Postman/Newman contra la pila aislada.

**Target Platform**: contenedor Linux (`python:3.14-slim`, Debian 13, con los datos de zonas del sistema);
Docker Compose en local; Kubernetes como orquestador de referencia (solo el ejemplo de *probes*).

**Project Type**: web-service

**Performance Goals**: con hasta 20 registrados, la consulta de salud responde en < `HEALTH_CHECK_TIMEOUT_SECONDS`
+ 1 s (4 s por defecto) con la base respondiendo y en < 2 × T + 1 s (7 s) sin ella (SC-001, SC-015);
`/health/live` < 100 ms en el 95 % (SC-007); a lo más una ronda de chequeos por proceso y periodo de caché ante
50 consultas simultáneas o 1 000 peticiones públicas por minuto (SC-006, SC-016).

**Constraints**: el permiso antes de validar y de servir resultados; ninguna dirección, cuerpo crudo, token
ni mensaje de excepción en respuestas o registros; 0 llamadas fuera de la lista permitida vigente; sin
trabajos en segundo plano; sin cambiar el comportamiento ni el contrato de suscripciones y dashboard
(FR-040); ninguna prueba llama a un servicio real.

**Scale/Scope**: 10 operaciones (4 públicas, 6 protegidas); 1 tabla y 1 migración; 2 códigos de error nuevos
(15 → 17); 11 variables de entorno opcionales; hasta ~50 componentes registrados (máximo esperado del listado
sin paginar); 14 módulos nuevos en `src/` y 10 modificados de forma aditiva; 1 simulación y 1 colección de
Postman nuevas; 10 ajustes a pruebas e infraestructura existentes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ Todo en las carpetas existentes ([R2](research.md#r2-capas-y-módulos-principio-i)). Routers: reciben, validan con DTOs, llaman al Service y serializan (`/health/live` solo devuelve una constante). Services: reglas de estado, caché, horario y registro; no importan `fastapi` ni `sqlalchemy`: la raíz de composición les da `read_enabled_components()` y `ping_database()`, que abren su propia sesión. Integraciones: HTTP a los componentes y depuración del contrato v1, sin FastAPI, DTOs ni base de datos. Repositories: únicas consultas (`SELECT 1` incluido). `test_layering.py` lo vigila sin cambios |
| II. Modelos ≠ DTOs | ✅ | ✅ `MonitoredComponent` (ORM) separado de `MonitoredComponentCreate/Update/Read`; conversión explícita (`from_attributes`); `deleted_at` no se publica. El resultado de salud son registros congelados del Service convertidos a DTOs propios; el estado público se arma campo por campo (lista cerrada, FR-047) |
| III. Asincronía | ✅ | ✅ httpx y SQLAlchemy async en todo el camino de una petición. Única E/S síncrona: `ZoneInfo` lee el archivo de la zona **una vez al arrancar**, en la validación de la configuración, y lo guarda en su caché (R12): no está en el camino de ninguna petición, así que no necesita `run_in_threadpool` |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-health.yaml](contracts/openapi-health.yaml) (OpenAPI 3.1, 10 operaciones; sintaxis y referencias comprobadas). Recursos en plural (`monitored-components`); 201 con `Location`, 204, 401/403/404/409/422/503; cuerpo de error uniforme. **Listado sin paginar**: excepción declarada en la spec (FR-023) con máximo de 50 (≤ 500) y orden determinista (`sort_order`, `code`); también acota `components` de la consulta de salud. El 503 de `/health/ready` no es un error de la API: es la respuesta del contrato v1, documentada con su esquema. **Observación**: con la base de datos caída, el registro responde 500 `internal_error` (comportamiento vigente, decisión 23): la base es la persistencia propia del servicio y el 503 de la constitución queda para las dependencias externas; no es una desviación nueva |
| V. Pruebas pytest | ✅ | ✅ Service con dobles; endpoints por HTTP; Repository contra PostgreSQL 17 real; sin servicios reales (simulaciones del API de usuarios y de componentes); la prueba de cobertura reconoce 8 rutas públicas y 13 protegidas; Postman complementa sin repetir ([R20](research.md#r20-pruebas-principio-v-fr-041-fr-049), [R22](research.md#r22-colección-de-postman-y-pila-de-punta-a-punta-fr-042-sc-012)) |
| VI. Migraciones Alembic | ✅ | ✅ Migración `0004` reversible que crea `monitored_components` con la unicidad del código entre los no eliminados; modelo consistente (`test_models_match_migrations.py`); cambio declarado en la spec y en [data-model.md](data-model.md); `DATA_SCHEMA.md` lo refleja con `-- [spec 005-health-monitoring]`; sin datos iniciales (el registro empieza vacío) |
| VII. Idioma | ✅ | ✅ Rutas, campos, permisos y códigos en inglés; mensajes, OpenAPI (incluida la etiqueta «Salud») y documentos en español; comentarios y docstrings en inglés |
| VIII. Control de acceso delegado | ✅ | ✅ Las seis protegidas: token reenviado sin modificar a `/api/v1/authorization/check`, permiso exacto, por petición, sin caché, falla cerrada (401/403/503), `BearerAuth` + `x-required-permission`; la caché guarda resultados, nunca decisiones. **Rutas públicas**: el principio admite «las comprobaciones de salud, si la especificación las define»; la spec las define y son solo `/health/live`, `/health/ready`, `/info` y `/health/status` (FR-002): no hace falta enmendar. Fila nueva en la [matriz](contracts/permission-matrix.md). **Desviación heredada** (no nueva): un cuerpo JSON ilegible responde 422 antes que 401/403 en el alta y la modificación (Complexity Tracking C3, confirmada el 2026-10-24) |
| IX. Integraciones | ✅ con justificación | ✅ con justificación. Llamadas asíncronas, con tiempo total, sin reintentos, `GET` idempotentes; fallas traducidas a códigos propios en inglés; nunca el cuerpo, la dirección ni credenciales; contrato consumido documentado ([health-contract-v1.md](contracts/health-contract-v1.md)) y simulado. **Desviación justificada**: las direcciones de los componentes registrados salen del registro (la base de datos) y no de variables de entorno (FR-022); del entorno salen la lista permitida que las acota y los tiempos (Complexity Tracking C1, aprobada el 2026-10-24). La copia del registro y la caché de resultados son datos propios (observaciones de este servicio), en memoria y de corta vida, no copias de datos de otro sistema |
| Stack obligatorio | ⚠️ `tzdata` | ✅ httpx (ya en el stack) y `zoneinfo` (biblioteca estándar); ni APScheduler ni trabajos en segundo plano. `zoneinfo` necesita `tzdata` en Windows (evidencia: `ZoneInfoNotFoundError` sin él) y no está en `uv.lock`: se añade como dependencia; no es tecnología nueva (son los datos IANA de la biblioteca estándar) y por eso **no requiere enmienda** (Complexity Tracking C2, aprobada el 2026-10-24) |
| Configuración por entorno, sin secretos | ✅ | ✅ Once variables nuevas validadas al arrancar; los mensajes nombran las variables, nunca sus valores; ningún secreto nuevo. `DATABASE_URL` también se valida al arrancar ([R16](research.md#r16-configuración-y-arranque-fr-038-sc-010); confirmado el 2026-10-24): hoy no se valida aunque es obligatoria |
| Docker y Compose | ✅ | ✅ `Dockerfile` con `ARG`/`ENV` de build al final; Compose pasa las variables nuevas (las de build como argumentos de build, R17); la pila e2e suma la simulación de componentes y sigue aislada |
| Flujo y puertas de calidad | ✅ | ✅ Este plan incluye el Constitution Check; la matriz «operación → permiso» y la colección de Postman se actualizan **en el mismo cambio** que las operaciones; puertas comprobables en el [quickstart](quickstart.md) |

**Resultado**: PASS contra los principios I a IX, **sin enmendar la constitución**. Los tres puntos de
Complexity Tracking quedaron **aprobados por la persona responsable el 2026-10-24**: C1 (desviación del
Principio IX que la spec ordena justificar, justificada aquí y no con una enmienda), C2 (`tzdata` como
dependencia sin enmienda de la tabla de stack) y C3 (la desviación ya aceptada por la spec 001 se extiende a
las dos operaciones nuevas con cuerpo). También aprobó validar `DATABASE_URL` al arrancar (R16).

## Ajustes a las pruebas existentes (FR-039, FR-040)

Las pruebas de comportamiento de suscripciones y dashboard **quedan intactas**. El barrido (`PUBLIC_ROUTES`,
`len(ErrorCode)`, `security`, `operation_ids_of_the_api` y las fixtures compartidas) encontró estos puntos;
todos se ajustan solo para **reconocer lo nuevo**:

| Id | Archivo | Ajuste | Por qué |
|---|---|---|---|
| A1 | `tests/contract/test_permission_coverage.py` | `PUBLIC_ROUTES` suma `/health/live`, `/health/ready`, `/info` y `/health/status` (**8**); el recorrido trata como pública una `APIRoute` cuya ruta esté en `PUBLIC_ROUTES` (la anota en `public_seen` y no la cuenta); `EXPECTED_PERMISSIONS` y `REQUESTS` suman las 6 protegidas (**13**, el conteo `checked == len(EXPECTED_PERMISSIONS)`); la fixture `seeded` inserta también un componente con un UUID fijo (para consultar, modificar y eliminar) y `snapshot` incluye `monitored_components` | Las rutas públicas de salud son `APIRoute` sin permiso y harían fallar el recorrido; las protegidas nuevas tienen que estar en la matriz. Ninguna aserción se debilita: «no cambia nada» pasa a vigilar también el registro |
| A2 | `tests/contract/test_openapi_contract.py` | `test_the_error_codes_are_the_fifteen_of_the_catalog` → 17 (se renombra a `seventeen`); en `test_the_documentation_routes_declare_no_security`, la aserción de que toda operación tiene `security` excluye solo las cuatro rutas públicas de salud | Fija 15 códigos y exige `security` en todas las operaciones |
| A3 | `tests/contract/test_dashboard_openapi.py` | `test_no_error_code_was_added` → 17 (comentario: la spec 005 añadió 2 del registro, revisado, sin impacto en el dashboard); `test_every_operation_of_the_api_declares_security_and_permission` excluye solo las cuatro rutas públicas de salud | Ídem |
| A4 | `tests/unit/test_error_messages.py` | `test_the_error_codes_are_exactly_the_fifteen_of_the_catalog` suma los dos códigos nuevos (se renombra a `seventeen`) | Fija el conjunto exacto de códigos |
| A5 | `tests/unit/test_dashboard_messages.py` | `test_no_error_code_was_added` → 17 (mismo comentario que A3) | Fija 15 |
| A6 | `tests/contract/test_dashboard_postman_collection.py` | G9: el mapa de colecciones suma la de salud (`prefixes_of_the_collections`, cuatro); la prueba pasa a «las cuatro colecciones juntas» | La cobertura conjunta debe incluir la colección nueva con sus diez operaciones (FR-039) |
| A7 | `tests/conftest.py` (fixture `api`) | Sobrescribe el cliente HTTP de los chequeos (simulación de componentes) y la configuración de salud (lista permitida de prueba); al terminar vacía también `monitored_components` | Sin `lifespan` no existe el cliente de chequeos; las operaciones nuevas de A1 lo necesitan |
| A8 | `tests/postman/docker-compose.e2e.yml` | Servicio `components-stub` y variables de salud de la API ([e2e-collection.md](contracts/e2e-collection.md)) | La colección nueva necesita componentes simulados |
| A9 | `tests/postman/environments/e2e.postman_environment.json` | Clave nueva `componentsStubUrl` | Ídem |
| A10 | `tests/postman/package.json` | Script `e2e:health`; `e2e:all` lo incluye | Ídem; `e2e` y `e2e:dashboard` no cambian |

**Nada se debilita**: las exclusiones de A2 y A3 nombran las cuatro rutas, así que una operación nueva sin
`security` que no sea una de ellas sigue haciéndolas fallar; y `test_health_openapi.py` comprueba que esas
cuatro **no** tienen seguridad ni permiso y que las seis protegidas sí. No cambian `test_layering.py` (no hay
carpeta ni módulo raíz nuevos: la versión va en `src/__init__.py`), las colecciones existentes ni sus
pruebas guardianas G1–G8.

## Documentación y despliegue

- **README**: sección «Salud del servicio» (las cuatro rutas públicas, que `/health/status` **no es una
  *probe***, la consulta agregada, el registro y sus permisos, la lista permitida y por qué conviene usar hosts
  exactos, el horario alineado con `Deploy-PgAutoShutdown.ps1`, la relación de tiempos `ready` < agregador,
  cómo construir la imagen con `APP_COMMIT_SHA`/`APP_BUILD_DATE`), filas nuevas en la tabla de
  configuración, la colección de salud en «Pruebas de punta a punta» y la estructura. Ejemplo de *probes*
  (sin crear manifiestos; la imagen arranca por defecto con `alembic upgrade head`, así que el contenedor de
  la API fija el comando de uvicorn):

  ```yaml
  livenessProbe:            # el proceso atiende; no depende de la base de datos
    httpGet: { path: /health/live, port: 8000 }
    periodSeconds: 10
    timeoutSeconds: 2
    failureThreshold: 3
  readinessProbe:           # falla mientras la base de datos está detenida: deja de recibir tráfico
    httpGet: { path: /health/ready, port: 8000 }
    periodSeconds: 10
    timeoutSeconds: 3       # mayor que HEALTH_READY_TIMEOUT_SECONDS (2 s)
    failureThreshold: 3
  startupProbe:             # arranque rápido; umbral amplio
    httpGet: { path: /health/live, port: 8000 }
    periodSeconds: 5
    failureThreshold: 30
  ```

  Readiness falla mientras la base de datos está detenida (lo esperado: el orquestador deja de enviarle
  tráfico) y liveness no (no se reinicia el contenedor).
- **`.env.example`**: las once variables, comentadas, con sus valores admitidos, su valor por defecto y los
  del runbook para el horario.
- **`docker-compose.yml`**: el servicio `api` pasa `HEALTH_*`, `DATABASE_SCHEDULE_*` y `APP_ENVIRONMENT` en
  `environment` (vacías = por defecto) y `APP_COMMIT_SHA`/`APP_BUILD_DATE` como `build.args` (R17).

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **mailySoft-usuarios 016**: crear el módulo «Salud de servicios» y los cuatro permisos `health:*` asignados
   a `Administrator`. Hasta entonces, en ambientes reales las seis operaciones protegidas responden 403.
2. **maily-backoffice 016**: su origen debe estar en `CORS_ALLOWED_ORIGINS` de cada ambiente; si usa un
   proxy en su mismo origen, ese proxy enruta también `/health/*` e `/info` bajo la URL base del cliente
   `subscriptions` (FR-050).
3. **Operación**: al desplegar, fijar `HEALTH_ALLOWED_HOSTS` con hosts exactos, las `DATABASE_SCHEDULE_*` con
   los valores del runbook y registrar desde el Backoffice mailySoft-usuarios, mailySoft-pacientes y
   MailySoft (`/healthz/`, con barra final). El *pipeline* de la imagen pasa `APP_COMMIT_SHA` y
   `APP_BUILD_DATE`; el despliegue, `APP_ENVIRONMENT`.
4. **mailySoft-pacientes 008**: valida `HEALTH_READY_TIMEOUT_SECONDS` distinto (decimales; avisa en vez de no
   arrancar). No afecta al contrato común ([R24](research.md#r24-alineación-con-mailysoft-usuarios-016-y-mailysoft-pacientes-008-decisión-22)).

## Project Structure

### Documentation (this feature)

```text
specs/005-health-monitoring/
├── plan.md                          # Este archivo
├── research.md                      # Fase 0: decisiones R1–R24 y su evidencia
├── data-model.md                    # Fase 1: tabla, DTOs, registros internos, estado en memoria y configuración
├── quickstart.md                    # Fase 1: guía de validación en cinco niveles
├── contracts/
│   ├── openapi-health.yaml          # Fase 1: las diez operaciones (OpenAPI 3.1)
│   ├── health-contract-v1.md        # Fase 1: contrato de salud v1 implementado y consumido
│   ├── permission-matrix.md         # Fase 1: 6 filas nuevas (13 protegidas) y 4 rutas públicas (8)
│   ├── error-catalog.md             # Fase 1: 2 códigos nuevos (17), mensajes, precedencia y códigos de componente
│   ├── database-schema.sql          # Fase 1: tabla monitored_components (migración 0004)
│   └── e2e-collection.md            # Fase 1: colección de Postman, simulación de componentes y pruebas guardianas
├── checklists/
│   └── requirements.md
└── tasks.md                         # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

```text
src/
├── __init__.py                          # (modifica) VERSION = "2.0.0": fuente única de la versión
├── main.py                              # (modifica) usa src.VERSION; incluye los routers de salud y del registro; etiqueta «Salud» y párrafo en DESCRIPTION; create_app crea app.state.health (HealthState); lifespan valida HealthSettings, BuildSettings, el horario y DATABASE_URL (Settings), y crea y cierra el cliente HTTP de chequeos
├── config.py                            # (modifica) HealthSettings, BuildSettings, AllowedHosts, DatabaseSchedule, database_schedule_from, InvalidSettingsError; configuration_error_message acepta nombres de variables
├── dependencies.py                      # (modifica) get_health_http_client, get_clock, get_health_state, get_health_service, get_monitored_component_repository, get_monitored_component_service; read_enabled_components y ping_database con sesiones propias
├── security.py                          # (modifica) HEALTH_READ, HEALTH_WRITE, HEALTH_UPDATE, HEALTH_DELETE
├── messages.py                          # (modifica) 2 ErrorCode y sus mensajes; VALIDATION_MESSAGES["monitored-components"]
├── exceptions.py                        # (modifica) MonitoredComponentNotFoundError (404), MonitoredComponentCodeAlreadyExistsError (409), MonitoredComponentDataError (422 validation_error)
├── error_handlers.py                    # (modifica) traduce MonitoredComponentDataError con translate_validation_errors; `uuid_parsing` en _KINDS
├── routers/
│   ├── health.py                        # (nuevo) public_router: /health/live, /health/ready, /info, /health/status; router: GET /api/v1/health
│   └── monitored_components.py          # (nuevo) las cinco operaciones del registro
├── services/
│   ├── clock.py                         # (nuevo) Clock (Protocol) y SystemClock
│   ├── health_state.py                  # (nuevo) HealthState: caché, agregación en curso, generación, copia del registro, ready en curso
│   ├── health_schedule.py               # (nuevo) in_window y next_start (cambio de horario de verano)
│   ├── health_service.py                # (nuevo) HealthService: readiness, info, agregación, reglas, estado global, vista pública
│   └── monitored_component_service.py   # (nuevo) alta, consulta, listado, modificación y baja; lista permitida; invalidación
├── integrations/
│   ├── health_probe.py                  # (nuevo) HealthProbeClient: GET acotado y traducción de fallas (FR-018)
│   └── health_contract.py               # (nuevo) lectura y depuración del contrato v1
├── repositories/
│   ├── errors.py                        # (modifica) DatabaseUnavailableError
│   ├── database_health_repository.py    # (nuevo) ping (SELECT 1)
│   └── monitored_component_repository.py  # (nuevo) CRUD, bloqueo para modificar, baja lógica y lectura de habilitados
├── models/
│   ├── __init__.py                      # (modifica) exporta MonitoredComponent
│   └── monitored_component.py           # (nuevo)
└── dtos/
    ├── health.py                        # (nuevo) LiveRead, ReadyRead, CheckRead, InfoRead, HealthRead, ComponentHealthRead, PublicStatusRead, PublicComponentRead
    └── monitored_component.py           # (nuevo) MonitoredComponentCreate, MonitoredComponentUpdate, MonitoredComponentRead

alembic/versions/0004_monitored_components.py   # (nuevo) tabla, índice parcial y disparador; downgrade reversible

tests/
├── health_support.py                    # (nuevo) FakeClock, transporte con fallas, constructores de componentes y ayuda HTTP
├── conftest.py                          # (ajuste A7)
├── stubs/components/{__init__,app}.py   # (nuevo) simulación de componentes (pytest y pila e2e)
├── unit/
│   ├── test_health_schedule.py          # (nuevo) ventana, límites, día en la zona, next_start_at, Tijuana, hueco y doble horario
│   ├── test_health_settings.py          # (nuevo) once variables: válidas, vacías e inválidas; el horario junto o nada
│   ├── test_allowed_hosts.py            # (nuevo) exactos, sufijos, mayúsculas, entradas inválidas
│   ├── test_monitored_component_dtos.py # (nuevo) code, name, kind, base_url (SSRF), rutas, reglas por kind, campos desconocidos
│   ├── test_monitored_component_service.py  # (nuevo) lista permitida, reservados, combinación resultante, invalidación
│   ├── test_health_contract.py          # (nuevo) depuración: recortes, controles, 20 chequeos, fechas, códigos
│   ├── test_health_probe.py             # (nuevo) contra la simulación y el transporte con fallas; sin token; 64 KiB; sin redirecciones
│   ├── test_health_service.py           # (nuevo) reglas, estado global, orden, integrados, caché, agregación compartida, periodo mínimo, copia del registro, tiempos
│   ├── test_health_startup.py           # (nuevo) lifespan: un solo mensaje sin valores; cliente de chequeos
│   ├── test_health_messages.py          # (nuevo) mensajes exactos del catálogo
│   ├── test_version.py                  # (nuevo) pyproject.toml = src.VERSION = OpenAPI = /info
│   ├── test_error_messages.py           # (ajuste A4)
│   └── test_dashboard_messages.py       # (ajuste A5)
├── contract/
│   ├── test_health_public_api.py        # (nuevo) live, ready (200/503), info, status; no-store; Authorization ignorada; CORS (FR-050)
│   ├── test_health_api.py               # (nuevo) GET /api/v1/health: 200 siempre, campos, orden, sin direcciones ni token, registro no disponible
│   ├── test_health_access_control.py    # (nuevo) 401/403/503 sin consultar componentes; permiso antes de validar; 50 consultas → 50 permisos y 1 ronda
│   ├── test_monitored_components_api.py # (nuevo) historia 3 completa; 404/409/422; base de datos caída → 500
│   ├── test_health_public_fields.py     # (nuevo) lista cerrada del estado público con todos los estados (SC-014)
│   ├── test_health_openapi.py           # (nuevo) etiqueta, seguridad, permisos, respuestas y esquemas
│   ├── test_health_postman_collection.py  # (nuevo) reglas G1–G8
│   ├── test_permission_coverage.py      # (ajuste A1)
│   ├── test_openapi_contract.py         # (ajuste A2)
│   ├── test_dashboard_openapi.py        # (ajuste A3)
│   └── test_dashboard_postman_collection.py  # (ajuste A6)
├── integration/
│   ├── test_monitored_component_repository.py  # (nuevo) contra PostgreSQL 17: CRUD, unicidad parcial, carrera de altas, baja, orden "C", FOR UPDATE
│   ├── test_monitored_components_migration.py  # (nuevo) 0004 sube y baja; la función de 0001 sobrevive
│   └── test_database_health_repository.py      # (nuevo) ping bien y con una dirección que no conecta
└── postman/
    ├── collections/MailySoft-System-Salud.postman_collection.json  # (nuevo)
    ├── environments/e2e.postman_environment.json                    # (ajuste A9)
    ├── docker-compose.e2e.yml                                       # (ajuste A8)
    └── package.json                                                 # (ajuste A10)

pyproject.toml                    # (modifica) version 2.0.0; dependencia tzdata
uv.lock                           # (modifica) uv lock: tzdata y la versión del paquete raíz
Dockerfile                        # (modifica) ARG/ENV APP_COMMIT_SHA y APP_BUILD_DATE al final
docker-compose.yml                # (modifica) variables nuevas del servicio api y sus argumentos de build
.env.example                      # (modifica) las once variables
README.md                         # (modifica) salud, configuración, probes, pruebas y estructura
project-definition/DATA_SCHEMA.md # (modifica) monitored_components -- [spec 005-health-monitoring]
```

Sin cambios: las colecciones de Postman existentes, `tests/stubs/users_api` (ya acepta cualquier permiso
`recurso:acción`), `tests/stubs/clinics_api`, `project-definition/create_database.sql` (crea hasta 0002;
`alembic upgrade head` aplica después 0003 y 0004) y el código de suscripciones y dashboard.

**Structure Decision**: proyecto único de servicio web con la estructura obligatoria del Principio I. La
salud es un recurso nuevo con sus propios Routers, Services, integraciones, Repositories, modelo y DTOs, que
no tocan los de suscripciones ni los del dashboard. El estado del proceso (`HealthState`) vive en
`app.state`, así cada aplicación (y cada prueba) tiene el suyo.

## Trazabilidad de requisitos

| Requisitos de la spec | Dónde se cumplen |
|---|---|
| FR-001 a FR-003 (rutas, permisos, públicas, acceso) | R3, R4; [permission-matrix.md](contracts/permission-matrix.md); [openapi-health.yaml](contracts/openapi-health.yaml); ajuste A1 |
| FR-004 a FR-009 (contrato v1, versión, reglas comunes, Docker, probes) | R1, R5, R17, R19; [health-contract-v1.md](contracts/health-contract-v1.md); «Documentación y despliegue» |
| FR-010 a FR-018 (consulta agregada, orden, campos, depuración, estados, códigos) | R7, R8, R9; [error-catalog.md](contracts/error-catalog.md) sección 2; [data-model.md](data-model.md) secciones 4, 5 y 8 |
| FR-019 a FR-022 (paralelo, caché, llamadas, desviación del IX) | R6, R9, R10; Complexity Tracking C1 |
| FR-023 a FR-032 (registro, SSRF, lista permitida, baja lógica, migración) | R14, R15; [data-model.md](data-model.md) secciones 1 a 3; [database-schema.sql](contracts/database-schema.sql) |
| FR-033 a FR-035, FR-044 (horario, `stopped`, `next_start_at`) | R12, R13; Complexity Tracking C2 |
| FR-036, FR-037 (copia en memoria, base caída) | R11, R15 |
| FR-038 (configuración) | R16; [data-model.md](data-model.md) sección 7 |
| FR-039, FR-040 (ajustes, sin regresiones) | «Ajustes a las pruebas existentes» (A1–A10); R21 |
| FR-041, FR-042, FR-049 (pruebas, Postman) | R20, R22; [e2e-collection.md](contracts/e2e-collection.md); [quickstart.md](quickstart.md) |
| FR-043 (stack y principios) | Constitution Check |
| FR-045 a FR-048 (estado público, lista cerrada, protección contra abuso) | R3, R10; [data-model.md](data-model.md) sección 5 |
| FR-050 (CORS) | R18 |

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Id | Violación o punto a justificar | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|---|
| C1 | **Principio IX**: «las direcciones … de cada API MUST provenir de variables de entorno». Las direcciones de los componentes registrados salen del registro (la base de datos), FR-022. **Aprobada** por la persona responsable (2026-10-24): se justifica aquí, sin enmienda | Monitorear un microservicio nuevo sin redesplegar ni reiniciar es el objetivo de la historia 3 (FR-031, SC-002) y la decisión 2 de la spec. Lo que sí viene del entorno acota el riesgo: `HEALTH_ALLOWED_HOSTS` (a qué hosts se puede llamar, comprobado al registrar y en cada agregación), los tiempos máximos y ninguna credencial (no se envía el token ni nada de la petición original). Las respuestas se depuran y nunca se devuelve una dirección fuera del registro | Una variable con la lista de componentes exige reiniciar el servicio por cada cambio (contradice FR-031). Una **enmienda MINOR** del Principio IX («salvo las direcciones del registro de salud, acotadas por una lista permitida del entorno») es posible vía `/speckit-constitution` si se prefiere fijarlo como regla general; este plan no la hace |
| C2 | **Tabla de stack**: dependencia nueva `tzdata`. **Aprobada** por la persona responsable (2026-10-24): dependencia del servicio sin enmienda | `zoneinfo` (biblioteca estándar, FR-043) no encuentra zonas en Windows, donde corre la suite (evidencia en R13); sin datos, el horario no puede validarse ni usarse. `tzdata` son los datos IANA que CPython publica como respaldo oficial de `zoneinfo` (PEP 615): no añaden API ni ámbito, y el código nunca lo importa. **No** es tecnología nueva y no requiere enmienda | Marcador `sys_platform == 'win32'` (la imagen dependería solo de los datos del sistema de la base `python:slim`); solo en desarrollo (igual de fuera de la tabla y deja sin datos un `uv sync --no-dev` en Windows); desfases fijos (contradice FR-033/FR-034/FR-044); una **enmienda PATCH** que lo mencione en la tabla (válida si se quiere dejarlo explícito; este plan no la hace) |
| C3 | **Principio VIII** (heredada de la spec 001, no nueva): un cuerpo que no es JSON legible responde 422 antes que 401/403 en `create_monitored_component` y `update_monitored_component`. **Confirmada** por la persona responsable (2026-10-24) para estas dos rutas (la spec 005 no lo mencionaba) | FastAPI 0.143.3 decodifica el cuerpo antes de resolver las dependencias (evidencia en R4). Un cuerpo ilegible no contiene datos que proteger y la respuesta no revela nada ni permite probar permisos | Leer el cuerpo a mano en las dos rutas pierde el esquema de entrada en OpenAPI y la validación de Pydantic; un middleware ASGI no documenta el permiso y esquiva la inyección de dependencias (mismos motivos que en la spec 001) |

Limitaciones aceptadas, que no son violaciones:

- **Carrera con un cambio del registro** (R10): una consulta autenticada que llega mientras corre una
  agregación iniciada antes del cambio espera a que termine y lanza otra, para no tener dos a la vez; puede
  tardar hasta dos agregaciones. Solo pasa en el proceso que atendió el cambio y con la base respondiendo.
- **Sin filtro por IP resuelta** (R6): un host permitido cuyo DNS apunte a otra IP no se detecta; el control
  es la lista permitida de hosts exactos que fija quien opera.
- **Varias réplicas**: cada una tiene su caché, su copia del registro y su periodo mínimo (edge case de la
  spec).

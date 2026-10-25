# Guía de validación: Monitoreo de salud de los servicios de Maily

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Contratos**: [contracts/](contracts/)

Cómo comprobar que la feature funciona de punta a punta, en cinco niveles. Los comandos son de PowerShell,
desde la raíz del repositorio. Ninguno llama a un servicio real: el API de usuarios y los componentes se
sustituyen por sus simulaciones (`tests/stubs/users_api` y `tests/stubs/components`).

## Requisitos

- Los de la [guía de la feature 001](../001-subscriptions-api/quickstart.md): `uv`, Python 3.14 o superior,
  Docker Desktop y, solo para el nivel 5, Node.js con npm.
- `uv sync` instala `tzdata` (los datos de zonas horarias que `zoneinfo` no encuentra en Windows,
  [research R13](research.md#r13-zoneinfo-y-tzdata-en-la-tabla-de-stack)). Comprobación rápida:
  `uv run python -c "import zoneinfo; print(zoneinfo.ZoneInfo('America/Mexico_City'))"` imprime la zona
  (sin `tzdata` lanzaría `ZoneInfoNotFoundError`).

## Nivel 1 — Pruebas unitarias (rápidas, sin Docker)

```powershell
uv sync
uv run pytest tests/unit -k "health or schedule or allowed_hosts or monitored or version"
```

Cubren, con dobles y un reloj controlable: el horario y `next_start_at` (noches, fines de semana, las 08:00 y
las 20:00 en punto, el día en la zona y no en UTC, y America/Tijuana con su cambio de horario), las reglas de
estado y el estado global, la depuración de respuestas, la caché y la agregación compartida (50 consultas
simultáneas → una ronda; `HEALTH_CACHE_SECONDS=0`; periodo mínimo de 15 s del estado público), la copia del
registro en memoria, la validación SSRF de `base_url` y de las rutas, la lista permitida, la configuración al
arrancar y la versión de una sola fuente. Resultado esperado: todo en verde.

## Nivel 2 — Suite completa y puertas de calidad

```powershell
docker compose up -d db
uv run pytest                                  # suite completa: debe pasar íntegra
```

| Puerta | Cómo se comprueba |
|---|---|
| Suite en verde; suscripciones y dashboard **sin cambios de comportamiento** (SC-011) | `uv run pytest` |
| Cobertura de permisos: 13 protegidas y 8 públicas | `uv run pytest tests/contract/test_permission_coverage.py` |
| Migración 0004 aplicable desde cero y reversible; modelo igual a la migración | `uv run pytest tests/integration -k "migration or models_match or monitored"` |
| Repository del registro contra PostgreSQL 17 real (unicidad parcial, baja lógica, orden, carrera de altas) | `uv run pytest tests/integration -k monitored` |
| OpenAPI generado sin errores, con la etiqueta «Salud» y las cuatro rutas públicas sin seguridad | `uv run pytest tests/contract/test_health_openapi.py` |
| Lista cerrada del estado público (SC-014) | `uv run pytest tests/contract -k public_fields` |
| Capas respetadas | `uv run pytest tests/unit/test_layering.py` |
| Colecciones de Postman coherentes con la API (las cuatro juntas) | `uv run pytest tests/contract -k postman` |
| Versión única: `pyproject.toml`, OpenAPI y `/info` (SC-008) | `uv run pytest tests/unit/test_version.py` |

## Nivel 3 — La API real con sus simulaciones

Cuatro terminales. La base de datos sí hace falta (la consulta trivial y el registro).

```powershell
# Terminal 1 — simulación del API de usuarios
uv run uvicorn app:app --app-dir tests/stubs/users_api --port 8012

# Terminal 2 — simulación de componentes
uv run uvicorn app:app --app-dir tests/stubs/components --port 8014

# Terminal 3 — la API (base de datos de docker compose ya migrada: docker compose run --rm migrate)
$env:USERS_API_BASE_URL = "http://127.0.0.1:8012"
$env:CLINICS_API_BASE_URL = "http://127.0.0.1:8013"
$env:HEALTH_ALLOWED_HOSTS = "127.0.0.1"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:5173"
uv run uvicorn src.main:app --port 8010
```

**Comprobación 1 — contrato v1 sin token (historia 2).**

```powershell
curl.exe -s -i http://127.0.0.1:8010/health/live      # 200 {"status":"ok"} y Cache-Control: no-store
curl.exe -s -i http://127.0.0.1:8010/health/ready     # 200 con el chequeo database en ok y su latency_ms
curl.exe -s -i http://127.0.0.1:8010/info             # 200; version 2.0.0; commit, build_date y environment en unknown
curl.exe -s -i -H "Origin: http://localhost:5173" http://127.0.0.1:8010/health/status   # 200 y Access-Control-Allow-Origin
curl.exe -s -i -H "Origin: http://otro.example" http://127.0.0.1:8010/health/live      # 200 sin cabeceras CORS
```

**Comprobación 2 — registrar y consultar (historias 1 y 3).**

```powershell
$h = @{ "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/tokens -Headers $h `
  -Body '{"token":"admin","permissions":["health:read","health:write","health:update","health:delete"]}'
$auth = @{ Authorization = "Bearer admin"; "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post http://127.0.0.1:8010/api/v1/monitored-components -Headers $auth `
  -Body '{"code":"sano","name":"Servicio sano","kind":"service","base_url":"http://127.0.0.1:8014/healthy"}'
Invoke-RestMethod -Method Post http://127.0.0.1:8010/api/v1/monitored-components -Headers $auth `
  -Body '{"code":"lento","name":"Servicio lento","kind":"service","base_url":"http://127.0.0.1:8014/slow","sort_order":5}'
Invoke-RestMethod http://127.0.0.1:8010/api/v1/health -Headers $auth | ConvertTo-Json -Depth 6
```

Se espera 200 con `status` `down`, `registry_available` `true` y, en orden, `maily-system-api` (`up`),
`database` (`up`), `sano` (`up`, con la versión de la simulación) y `lento` (`down`, `timeout`). La
respuesta llega en menos de 4 s y **ningún** campo trae `127.0.0.1:8014`. `GET
http://127.0.0.1:8014/__test__/calls` muestra que ninguna llamada llevó `Authorization`.

**Comprobación 3 — errores del registro.**

```powershell
# El cuerpo entra por la entrada estándar: así no hay que escapar las comillas (PowerShell 5.1 y 7).
'{"code":"fuera","name":"Fuera","kind":"service","base_url":"http://otro-host:8000"}' |
  curl.exe -s -i -X POST http://127.0.0.1:8010/api/v1/monitored-components -H "Authorization: Bearer admin" -H "Content-Type: application/json" --data-binary "@-"   # 422 en base_url, sin repetir la dirección
'{"code":"database","name":"X","kind":"service","base_url":"http://127.0.0.1:8014/healthy"}' |
  curl.exe -s -i -X POST http://127.0.0.1:8010/api/v1/monitored-components -H "Authorization: Bearer admin" -H "Content-Type: application/json" --data-binary "@-"   # 409 código reservado
```

Deshabilitar (`PATCH … {"enabled": false}`) hace desaparecer `lento` de la siguiente consulta de salud; la
baja (`DELETE`) responde 204 y después 404; el mismo `code` se puede registrar de nuevo con otro `id`.

**Comprobación 4 — base de datos detenida por horario y estado público (historias 4, 5 y 6).** Detén la API
(terminal 3) y arráncala con un horario que **no** incluya el día de hoy, por ejemplo:

```powershell
$env:DATABASE_SCHEDULE_TIMEZONE = "America/Mexico_City"
$env:DATABASE_SCHEDULE_DAYS = "Sunday"          # cualquier día que no sea hoy
$env:DATABASE_SCHEDULE_START = "08:00"
$env:DATABASE_SCHEDULE_END = "20:00"
uv run uvicorn src.main:app --port 8010
```

Consulta la salud una vez (para que el proceso lea el registro), detén la base (`docker compose stop db`) y
**espera más de 15 segundos**: hasta entonces las consultas devuelven el resultado en caché de antes de
detenerla (`HEALTH_CACHE_SECONDS`; el estado público lo reutiliza al menos 15 s).

- `GET /health/live` sigue en 200 y `GET /health/ready` responde 503 con `connection_error` o `timeout` en
  menos de 3 s.
- `GET /health/status` (sin token) responde 200: `database` `stopped` con `next_start_at` el próximo domingo
  a las 08:00 de la Ciudad de México en UTC (14:00 Z); `maily-system-api` `degraded`; los registrados siguen
  apareciendo (copia en memoria); y no trae versiones, latencias, chequeos ni errores.
- `GET /api/v1/health` responde 200 con `registry_available` `false` y los mismos componentes.
- Registrar un componente responde 500 `internal_error` y no cambia nada.
- Vuelve a encender la base (`docker compose start db`): `registry_available` regresa a `true`.

Sin las variables `DATABASE_SCHEDULE_*`, la misma falla es `down` con `next_start_at` `null`. Limpieza:
`Remove-Item Env:DATABASE_SCHEDULE_*`.

**Comprobación 5 — la configuración no válida impide arrancar (SC-010).** Con cada uno de estos valores, el
servicio no arranca y el mensaje nombra la variable **sin** mostrar su valor:
`HEALTH_CHECK_TIMEOUT_SECONDS=0`, `HEALTH_CACHE_SECONDS=301`, `HEALTH_ALLOWED_HOSTS=*.maily.internal`,
`DATABASE_SCHEDULE_DAYS=Lunes` (con las otras tres), solo `DATABASE_SCHEDULE_TIMEZONE` sin las demás,
`DATABASE_SCHEDULE_START=20:00` con `END=08:00`, `APP_COMMIT_SHA=xyz` y `APP_BUILD_DATE=ayer`.

## Nivel 4 — La imagen con su identificación de build (FR-009)

```powershell
$sha = git rev-parse HEAD
$date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
docker build -t maily-system-api:health --build-arg APP_COMMIT_SHA=$sha --build-arg APP_BUILD_DATE=$date .
docker run --rm -d --name maily-health -p 8016:8000 -e APP_ENVIRONMENT=local `
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5434/maily_system `
  -e USERS_API_BASE_URL=http://host.docker.internal:8012 -e CLINICS_API_BASE_URL=http://host.docker.internal:8013 `
  maily-system-api:health uvicorn src.main:app --host 0.0.0.0 --port 8000
curl.exe -s http://127.0.0.1:8016/info        # commit = $sha, build_date = $date (UTC), environment = local
docker rm -f maily-health
```

Construida **sin** los argumentos, la imagen arranca igual y `/info` devuelve `unknown` en los tres campos.
El ejemplo de *probes* de Kubernetes está en el README (liveness y startup a `/health/live`, readiness a
`/health/ready`; `/health/status` no es una *probe*).

## Nivel 5 — Pruebas de punta a punta (Postman con Newman)

```powershell
npm ci --prefix tests/postman                                           # una vez
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --build --wait api
npm run e2e:health --prefix tests/postman                               # salud → reports/junit-health.xml
npm run e2e:all --prefix tests/postman                                  # suscripciones, dashboard y salud, una tras otra
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

Resultado esperado: código de salida `0`. La colección vacía el registro al empezar, así que se puede
repetir. Sus casos están en [contracts/e2e-collection.md](contracts/e2e-collection.md).

Usa `--build`: sin él, Compose reutiliza las imágenes de una ejecución anterior del proyecto
`maily-system-e2e` y la API podría no llevar el código actual (la colección de salud fallaría con 404).

## Mapa historia → comprobación

| Historia | Pruebas automáticas | Comprobación manual |
|---|---|---|
| 1. Salud de todos los componentes | `test_health_service.py`, `test_health_api.py`, `test_health_probe.py`, `test_health_contract.py` | Nivel 3, comprobación 2 |
| 2. Contrato v1 propio e integrado | `test_health_public_api.py`, `test_version.py`, `test_health_startup.py` | Nivel 3, comprobación 1; nivel 4 |
| 3. Registro sin redesplegar | `test_monitored_components_api.py`, `test_monitored_component_dtos.py`, `test_monitored_component_repository.py`, `test_allowed_hosts.py` | Nivel 3, comprobaciones 2 y 3 |
| 4. Base de datos detenida por horario | `test_health_schedule.py`, `test_health_service.py`, `test_health_settings.py` | Nivel 3, comprobación 4 |
| 5. Registro no disponible | `test_health_service.py`, `test_health_api.py` (lectura que falla, nunca leída, vacía, tiempo agotado) | Nivel 3, comprobación 4 |
| 6. Estado público sin sesión | `test_health_public_api.py`, `test_health_public_fields.py`, `test_health_service.py` (periodo mínimo) | Nivel 3, comprobaciones 1 y 4 |
| Control de acceso y cobertura (FR-001 a FR-003) | `test_health_access_control.py`, `test_permission_coverage.py` | Nivel 5 |
| Postman y ajustes (FR-039, FR-042) | `test_health_postman_collection.py`, `test_dashboard_postman_collection.py` (G9) | Nivel 5 |

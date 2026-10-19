# Guía de validación: Dashboard de Plataforma

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Contratos**: [contracts/](contracts/)

Cómo comprobar que la feature funciona de punta a punta, en cuatro niveles. Los comandos son de PowerShell,
desde la raíz del repositorio. Ninguno llama a un API real: el API de usuarios se sustituye por su simulación
(`tests/stubs/users_api`) y los datos del dashboard son los ficticios de la Fase 1.

## Requisitos

- Los de la [guía de la feature 001](../001-subscriptions-api/quickstart.md): `uv`, Python 3.14 o superior,
  Docker Desktop y, solo para el nivel 4, Node.js con npm.
- Las pruebas del dashboard (nivel 1) **no necesitan** PostgreSQL ni Docker: la operación no toca la base de
  datos. La suite completa (nivel 2) sí.

## Nivel 1 — Pruebas del dashboard (rápidas, sin Docker)

```powershell
uv sync
uv run pytest tests/unit/test_dashboard_service.py tests/unit/test_dashboard_dtos.py `
              tests/unit/test_dummy_dashboard_source.py tests/unit/test_dashboard_config.py `
              tests/unit/test_dashboard_messages.py `
              tests/unit/test_dashboard_startup.py tests/unit/test_dashboard_layering.py `
              tests/contract/test_dashboard_api.py tests/contract/test_dashboard_access_control.py `
              tests/contract/test_dashboard_degradation.py tests/contract/test_dashboard_openapi.py `
              tests/contract/test_dashboard_postman_collection.py
```

(O, más corto, `uv run pytest -k dashboard`, que además recoge los 5 casos de `get_dashboard` de la prueba de
cobertura de permisos; esa sí necesita la base de datos y por eso `-k` pide `docker compose up -d db`.)
Resultado esperado: todo en verde, sin más servicios levantados.

## Nivel 2 — Suite completa y puertas de calidad

```powershell
docker compose up -d db
uv run pytest                                  # suite completa: debe pasar íntegra
```

Comprobaciones que exige la constitución y qué las cubre:

| Puerta | Cómo se comprueba |
|---|---|
| Suite de pytest en verde, incluidas las pruebas de suscripciones **sin cambios de comportamiento** | `uv run pytest` |
| Cobertura de permisos (la ruta del dashboard declara `dashboard:read` y coincide con la matriz) | `uv run pytest tests/contract/test_permission_coverage.py` |
| Esquema OpenAPI generado sin errores | `uv run python -c "import json; from src.main import create_app; print(len(json.dumps(create_app().openapi())))"` |
| Capas respetadas (el dashboard no toca la base de datos) | `uv run pytest tests/unit/test_layering.py tests/unit/test_dashboard_layering.py` |
| Sin migraciones ni cambios de esquema (SC-009) | `git status --short alembic src/models src/repositories project-definition` → **sin salida** |
| Migraciones aplicables desde cero | `uv run pytest tests/integration/test_migrations.py` |

## Nivel 3 — La API real, con la simulación del API de usuarios

Tres terminales. La base de datos no hace falta (el dashboard no la usa); el arranque solo exige las dos
direcciones de los otros APIs.

```powershell
# Terminal 1 — simulación del API de usuarios
uv run uvicorn app:app --app-dir tests/stubs/users_api --port 8012

# Terminal 2 — la API
$env:USERS_API_BASE_URL = "http://127.0.0.1:8012"
$env:CLINICS_API_BASE_URL = "http://127.0.0.1:8013"      # el dashboard no la llama
uv run uvicorn src.main:app --port 8010
```

**Comprobación 1 — el aviso de datos ficticios (FR-024).** Al arrancar, la terminal 2 muestra un aviso
(`WARNING`) que dice que el dashboard devuelve datos ficticios. No muestra ningún secreto.

```powershell
# Terminal 3 — registrar a una persona con el permiso y consultar
$h = @{ "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/tokens -Headers $h `
  -Body '{"token":"demo","permissions":["dashboard:read"]}'
Invoke-RestMethod http://127.0.0.1:8010/api/v1/dashboard -Headers @{ Authorization = "Bearer demo" } | ConvertTo-Json -Depth 5
```

**Comprobación 2 — el resumen (historia 1).** Llegan los seis indicadores (`12, 8, 3, 37, 1284, 52`) y 5
clínicas recientes: Santa Aurora, Del Valle, Horizonte, **Dental Sonríe** y San Rafael (las dos últimas con
la misma fecha, en orden de identificador). Repetir la consulta da exactamente lo mismo.

**Comprobación 3 — `limit` (historia 3).**

```powershell
$auth = @{ Authorization = "Bearer demo" }
(Invoke-RestMethod "http://127.0.0.1:8010/api/v1/dashboard?limit=3" -Headers $auth).recent_clinics.Count      # 3
(Invoke-RestMethod "http://127.0.0.1:8010/api/v1/dashboard?limit=1000" -Headers $auth).recent_clinics.Count   # 10, sin error
curl.exe -s -i "http://127.0.0.1:8010/api/v1/dashboard?limit=abc" -H "Authorization: Bearer demo"             # 422 validation_error
curl.exe -s -i "http://127.0.0.1:8010/api/v1/dashboard?limit=3&limit=5" -H "Authorization: Bearer demo"       # 422
curl.exe -s -i "http://127.0.0.1:8010/api/v1/dashboard" -H "Authorization: Bearer demo"                       # 200 y Cache-Control: no-store
```

**Comprobación 4 — control de acceso (historia 2).**

```powershell
curl.exe -s -i "http://127.0.0.1:8010/api/v1/dashboard"                                                      # 401 unauthenticated
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/tokens -Headers $h `
  -Body '{"token":"sinpermiso","permissions":["subscriptions:read"]}'
curl.exe -s -i "http://127.0.0.1:8010/api/v1/dashboard?limit=abc" -H "Authorization: Bearer sinpermiso"       # 403 (no 422): el permiso va primero
# detener la terminal 1 (API de usuarios) y repetir la consulta con "demo"                                  # 503 authorization_unavailable
```

**Comprobación 5 — la configuración (historia 4).** Detén la API (terminal 2) y arráncala de nuevo con:

```powershell
$env:DASHBOARD_RECENT_CLINICS_LIMIT = "4"
uv run uvicorn src.main:app --port 8010
```

El servicio **no arranca**: el error nombra `DASHBOARD_RECENT_CLINICS_LIMIT` y **no** muestra el `4`. Repite
con `0`, `11`, `abc` y `5.5` (mismo resultado). Con `3` y con `10` arranca y, sin `limit`, devuelve 3 y 10
clínicas; sin la variable (o vacía), 5. Cambiarla con la API en marcha no tiene efecto hasta reiniciar.
Quita la variable al terminar: `Remove-Item Env:DASHBOARD_RECENT_CLINICS_LIMIT`.

## Nivel 4 — Pruebas de punta a punta (Postman con Newman)

```powershell
npm ci --prefix tests/postman                                           # una vez
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api
npm run e2e:dashboard --prefix tests/postman                            # solo el dashboard → reports/junit-dashboard.xml
npm run e2e:all --prefix tests/postman                                  # suscripciones y luego dashboard
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

Resultado esperado: código de salida `0`. La colección del dashboard es de solo lectura, así que se puede
repetir sin limpiar nada. Su estructura y sus casos están en
[contracts/e2e-collection.md](contracts/e2e-collection.md).

## Mapa historia → comprobación

| Historia | Pruebas automáticas | Comprobación manual |
|---|---|---|
| 1. Ver el resumen | `test_dashboard_api.py`, `test_dashboard_dtos.py`, `test_dummy_dashboard_source.py` | Nivel 3, comprobación 2 |
| 2. Solo quien tiene el permiso | `test_dashboard_access_control.py`, `test_permission_coverage.py` | Nivel 3, comprobación 4 |
| 3. Elegir cuántas clínicas ver | `test_dashboard_service.py`, `test_dashboard_messages.py`, `test_dashboard_api.py` | Nivel 3, comprobación 3 |
| 4. Cantidad por defecto | `test_dashboard_config.py`, `test_dashboard_startup.py`, `test_dashboard_api.py` | Nivel 3, comprobación 5 |
| 5. Datos ficticios y avisados | `test_dummy_dashboard_source.py`, `test_dashboard_startup.py`, `test_dashboard_layering.py` | Nivel 3, comprobación 1; `git status` del nivel 2 |
| 6. Contrato estable y degradación | `test_dashboard_degradation.py`, `test_dashboard_service.py`, `test_dashboard_openapi.py` | — (con fuentes reales: especificaciones futuras) |
| Verificación (FR-034 a FR-037) | `test_dashboard_postman_collection.py`, `test_permission_coverage.py` | Nivel 4 |

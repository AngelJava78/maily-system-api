# Guía de validación (quickstart): API REST de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Cómo comprobar, en tres niveles, que la feature funciona de punta a punta. Esta guía se ejecuta
**cuando la feature esté implementada** (`/speckit-implement`); aquí solo se fija qué se comprueba y
qué se espera. El contrato está en [contracts/](contracts/) y el modelo de datos en
[data-model.md](data-model.md).

**Requisitos**: Docker Desktop con Compose 2.24 o superior; [uv](https://docs.astral.sh/uv/) y Python
3.14 o superior; Node.js con npm (solo para el nivel 3, como herramienta de desarrollo). Ninguna prueba
necesita el API de usuarios ni el de clínicas reales: usan sus simulaciones
([contracts/e2e-stubs.md](contracts/e2e-stubs.md)).

## Nivel 1 — Suite automatizada (pytest)

```powershell
Copy-Item .env.example .env              # ajusta credenciales/puertos si hace falta
docker compose up -d db                  # PostgreSQL 17 (bases `maily_system` y `maily_system_test`)
uv sync                                  # instala las dependencias
uv run pytest                            # suite completa
uv run alembic upgrade head              # aplicar migraciones
uv run alembic check                     # ¿los modelos coinciden con las migraciones?
uv run alembic downgrade base            # revertirlas todas (solo en desarrollo)
```

**Esperado**: la suite en verde; `alembic check` responde «No new upgrade operations detected»; las
migraciones suben y bajan sin error. Las pruebas **eliminan y recrean el esquema** de
`TEST_DATABASE_URL`, por eso su nombre debe terminar en `_test` (si no, la suite se niega a ejecutarse).

### Mapa historia → pruebas

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| 1 (catálogo) FR-006 a FR-009 | Devuelve Activas, Inactivas y Bloqueadas con su estatus; no devuelve Eliminadas; mismo orden en dos consultas; vacío = `[]`; con el API de clínicas caído, `clinics_count: null`; con 500 suscripciones, orden correcto y < 2 s | `tests/contract/test_subscriptions_api.py`, `test_clinics_degradation.py`; `tests/integration/test_catalog_scale.py` |
| 2 (acceso) FR-001 a FR-005, SC-002, SC-003 | Para cada operación: sin token, token inválido/vencido, sin permiso, con permiso y API de usuarios caído; una llamada por petición con el permiso exacto; token reenviado sin cambios; permiso revocado = efecto en la siguiente petición; el permiso se comprueba antes que la validación; ninguna ruta sin permiso declarado | `tests/contract/test_access_control.py`, `test_permission_coverage.py`, `test_users_api_client.py`; `tests/unit/test_security.py`, `test_authorization_service.py` |
| 3 (crear) FR-011 a FR-014, SC-006 | Nace Activa con `clinics_count: 0`; nombre repetido (otra capitalización, con espacios, con acentos) → 409; el de una Eliminada queda libre; el de una Inactiva sigue reservado; 50 creaciones simultáneas con el mismo nombre → exactamente una; campos no permitidos y precios inválidos → 422 | `tests/contract/test_subscriptions_api.py`; `tests/integration/test_subscription_repository.py`, `test_subscriptions_constraints.py`; `tests/unit/test_subscription_dtos.py`, `test_subscription_service.py` |
| 4 (consultar) FR-010 | Activa/Inactiva/Bloqueada se devuelven; Eliminada e inexistente → 404 | `tests/contract/test_subscriptions_api.py` |
| 5 (actualizar) FR-015 | Solo cambia lo enviado; `updated_at` cambia; nombre de otra → 409; cuerpo vacío o con `status`/`id` → 422; Eliminada → 404 | `tests/contract/test_subscriptions_api.py`; `tests/integration/test_subscriptions_constraints.py` |
| 6 (estatus) FR-016 | Cualquier dirección entre 1, 2 y 3; el mismo estatus → 409; 4 o desconocido → 422; con clínicas se permite | `tests/contract/test_subscriptions_api.py`; `tests/unit/test_subscription_service.py` |
| 7 (eliminar) FR-017, FR-018, SC-009 | Sin clínicas → 204 y deja de verse; con clínicas → 409; con el API de clínicas caído o con respuesta inesperada → 503 y no cambia nada; no se puede actualizar ni cambiar de estatus después | `tests/contract/test_subscriptions_api.py`, `test_clinics_degradation.py`; `tests/unit/test_subscription_service.py` |
| Errores FR-019 a FR-023, SC-008 | Formato uniforme y mensajes en español; el token nunca aparece en una respuesta ni en un registro; OpenAPI generado sin errores y con permiso en cada operación | `tests/unit/test_error_messages.py`; `tests/contract/test_openapi_contract.py` |
| Reenvío del token y navegador (FR-024, FR-025) | Los clientes no siguen redirecciones (modo `redirect` de las simulaciones); advertencia al arrancar por una dirección `http://` no local, sin mostrar la dirección; CORS desactivado por defecto y, con lista, solo el sitio permitido y sin credenciales | `tests/contract/test_users_api_client.py`, `test_clinics_api_client.py`; `tests/unit/test_config.py`, `test_main.py` |
| Capas (Principio I) | Ninguna capa importa lo que no debe (`ast`) | `tests/unit/test_layering.py` |
| Configuración (Principio VIII/IX) | Falta una variable obligatoria → no arranca y nombra la variable sin mostrar valores | `tests/unit/test_config.py` |

## Nivel 2 — La API de verdad, con las simulaciones (manual)

Levanta la pila aislada de punta a punta (con la base de datos desechable y las dos simulaciones):

```powershell
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api
```

La API queda en `http://127.0.0.1:8011`, la simulación del API de usuarios en `:8012` y la de clínicas en
`:8013`. Registra una persona con permisos y fija conteos de clínicas:

```powershell
$h = @{ "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/tokens -Headers $h -Body '{"token":"demo","permissions":["subscriptions:read","subscriptions:write","subscriptions:update","subscriptions:delete"]}'
Invoke-RestMethod -Method Post http://127.0.0.1:8013/__test__/counts -Headers $h -Body '{}'
```

Recorrido (con `curl.exe`; el token es `demo`):

```powershell
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions                                    # 401 unauthenticated
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo"    # 200 []
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Pro\",\"monthly_price\":4500,\"features\":[\"Hasta 5 consultorios\",\"Usuarios ilimitados\"]}'
# 201: status {id:1, name:"Activa"}, monthly_price "4500.00", clinics_count 0
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo"  # detalle
curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1/status -H "Authorization: Bearer demo" -H "Content-Type: application/json" -d '{\"status_id\":2}'   # Inactiva
curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1/status -H "Authorization: Bearer demo" -H "Content-Type: application/json" -d '{\"status_id\":2}'   # 409 subscription_status_unchanged
```

Eliminar y degradar:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8013/__test__/counts -Headers $h -Body '{"1":3}'
curl.exe -s -X DELETE http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo"   # 409 subscription_has_clinics
Invoke-RestMethod -Method Post http://127.0.0.1:8013/__test__/faults -Headers $h -Body '{"mode":"unavailable","count":2}'
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo"               # 200 con clinics_count: null
curl.exe -s -X DELETE http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo"   # 503 clinics_check_unavailable
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/faults -Headers $h -Body '{"mode":"unavailable","count":1}'
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo"               # 503 authorization_unavailable
```

**Esperado**: los códigos y cuerpos indicados en cada línea; `http://127.0.0.1:8011/docs` se abre sin
token y cada operación muestra su permiso requerido. Desmontar la pila:

```powershell
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

## Nivel 3 — Postman con Newman (punta a punta)

Complementa a pytest, **no lo sustituye**. No necesita cuenta de Postman ni envía nada a servicios
externos. Con la pila del nivel 2 arriba:

```powershell
npm ci --prefix tests/postman                              # instala Newman (una vez)
npm run e2e --prefix tests/postman                         # colección completa: consola + tests/postman/reports/junit.xml
npm run e2e --prefix tests/postman -- --folder "5. Control de acceso"   # solo una carpeta (las 2 a 4 usan lo que crea la 1)
```

**Esperado**: código de salida `0` con todas las comprobaciones en verde (carpetas 0 a 6 de
[contracts/e2e-stubs.md](contracts/e2e-stubs.md)); `1` si falla alguna o la API no responde.
**No apuntes nunca la colección a un servicio con datos reales**: crea y elimina de forma lógica
suscripciones, así que quedan filas «Eliminada».

## Criterios de éxito → dónde se miden

| Criterio | Cómo se comprueba |
|---|---|
| SC-001 (catálogo en < 2 s) | `test_catalog_scale.py` con 500 suscripciones y las simulaciones |
| SC-002 (todo rechazo sin cambios; cobertura de rutas) | `test_access_control.py` + `test_permission_coverage.py` |
| SC-003 (permiso revocado = siguiente petición) | `test_access_control.py` (cambia los permisos de la simulación entre dos peticiones) |
| SC-004 (estatus en todas las respuestas; Eliminadas fuera) | `test_subscriptions_api.py` |
| SC-005 (clínicas caído ≠ error) | `test_clinics_degradation.py` + carpeta 6 de Postman |
| SC-006 (50 creaciones simultáneas → una) | `test_subscription_repository.py` / `test_subscriptions_api.py` |
| SC-007 (crear y verla en < 1 min) | Recorrido del nivel 2 / carpeta 1 de Postman |
| SC-008 (errores en español, formato uniforme) | `test_error_messages.py` |
| SC-009 (0 eliminaciones con clínicas) | `test_clinics_degradation.py` + carpeta 4 de Postman |

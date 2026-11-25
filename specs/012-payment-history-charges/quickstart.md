# Quickstart: comprobar el historial de cobros (012-payment-history-charges)

## 1. Nivel rápido (sin PostgreSQL), lo que corre `/speckit-implement`

```powershell
uv run pytest
```

Debe pasar completo (incluye los DTO, el Service con dobles y el resto de la suite rápida del servicio).

## 2. Nivel lento (PostgreSQL 17 real), antes de integrar a `main`

```powershell
docker compose up -d db
docker compose run --rm migrate
uv run pytest -m ""
```

Debe pasar completo: incluye `tests/integration/test_subscription_period_repository.py` (orden,
paginación, aislamiento por organización contra la base real), `tests/contract/test_subscription_periods_api.py`
(los tres estados de un cobro, control de acceso, paginación), `test_subscription_periods_openapi.py` y
`test_permission_coverage.py`.

## 3. Comprobación manual contra la aplicación real

```powershell
# con el token de la persona (Dueño de la organización) en $env:TOKEN
curl -H "Authorization: Bearer $env:TOKEN" `
  "http://localhost:8010/api/v1/subscription-periods/<organization_id>/charges?page=1&page_size=10"
```

Una organización sin ningún cobro responde:

```json
{"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
```

## 4. OpenAPI publicado sin errores

```powershell
uv run python -c "from src.main import create_app; create_app().openapi()"
```

No debe lanzar ninguna excepción; `schema['paths']['/api/v1/subscription-periods/{organization_id}/charges']`
debe existir con `operationId: list_subscription_charges`.

## 5. Postman/Newman (la pila aislada, punta a punta)

```powershell
cd tests/postman
npm run e2e:periods
```

Las dos solicitudes nuevas (`list_subscription_charges: …`) deben pasar junto con el resto de la
colección de los periodos de suscripción.

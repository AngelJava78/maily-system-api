# Guía de validación (quickstart): Cobro Real de Suscripciones de Clínicas

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía se ejecuta cuando la feature esté implementada (`/speckit-implement`). El contrato está en
[contracts/](contracts/) y el modelo de datos en [data-model.md](data-model.md).

**Requisitos**: los mismos que la spec 001 — Docker Desktop (Compose), [uv](https://docs.astral.sh/uv/)
y Python 3.14+. Ninguna prueba necesita `mailySoft-pagos` ni `mailySoft-usuarios` reales: usan sus
simulaciones ([contracts/e2e-stubs.md](contracts/e2e-stubs.md)).

## Nivel 1 — Suite automatizada (pytest)

```powershell
docker compose up -d db                  # PostgreSQL 17 (si no estaba ya levantada)
uv sync
uv run pytest
uv run alembic upgrade head
uv run alembic check                     # ¿los modelos coinciden con las migraciones?
```

**Esperado**: la suite en verde (incluida la de las specs 001 a 005, sin cambios de expectativas);
`alembic check` responde «No new upgrade operations detected»; la migración 0005 sube y baja sin
error, también sobre una base con datos (una suscripción de clínica ya creada).

### Mapa historia → pruebas

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| 1 (asignar) FR-001 a FR-007 | Ciclo mensual/anual; `next_billing_at` inmediato o tras `trial_days`; plan no Activo → 409; clínica con una vigente → 409; `tenant_id`/`billing_cycle` inválidos → 422 | `tests/contract/test_clinic_subscriptions_api.py`; `tests/integration/test_clinic_subscription_repository.py`; `tests/unit/test_clinic_subscription_service.py` |
| 2 (cobrar) FR-008 a FR-015, SC-002, SC-003, SC-006 | Cuerpo exacto a Pagos (centavos, `resource_type`/`resource_id`); misma `Idempotency-Key` en un reintento del mismo periodo; no Activa → 409; Pagos caído → 503 sin crear nada; 401/403 de Pagos traducidos sin filtrar su cuerpo; otra organización → 404 | `tests/contract/test_clinic_subscriptions_api.py`, `test_payments_api_client.py`; `tests/unit/test_clinic_subscription_service.py` |
| 3 (conocer el resultado) FR-016 a FR-018, SC-004 | Un cobro `pending` se sincroniza al consultarlo; uno ya resuelto no vuelve a llamar a Pagos; Pagos caído durante la sincronización → se devuelve el último estatus local, sin fallar la lectura; `approved` avanza `next_billing_at` y vuelve a Activa | `tests/contract/test_clinic_subscriptions_api.py`; `tests/unit/test_clinic_subscription_service.py` |
| 4 (consultar/listar) FR-007 | Paginado; incluye el cobro vigente (o `null`); inexistente/cancelada → 404; sin permiso → 403 | `tests/contract/test_clinic_subscriptions_api.py` |
| 5 (cancelar) | Activa sin cobro pendiente → Cancelada; con cobro `pending` → 409; ya Cancelada → 409 | `tests/contract/test_clinic_subscriptions_api.py`; `tests/unit/test_clinic_subscription_service.py` |
| Control de acceso (FR-024, FR-030, FR-031) | Las 6 operaciones de rol de Sistema siguen usando `check`; `charge_clinic_subscription` usa `me` (una sola llamada), compara `tenant_id`, `password_change_required` → 403, permiso ausente en la unión de `roles[].permissions` → 403 | `tests/contract/test_clinic_subscriptions_access_control.py`, `test_permission_coverage.py`; `tests/unit/test_authorization_service.py` |
| Integración con Pagos (FR-019 a FR-023, SC-005) | Asíncrona, sin reintentos, sin seguir redirecciones; variables de entorno obligatorias/opcionales; nunca filtra el cuerpo de Pagos | `tests/contract/test_payments_api_client.py` |
| Esquema (Principio VI) | Migración 0005 sube/baja desde cero y con datos previos; `project-definition/DATA_SCHEMA.md` actualizado | `tests/integration/test_clinic_subscriptions_migration.py`, `test_models_match_migrations.py` |
| Capas (Principio I) | `payments_api.py`/`clinic_subscription_service.py`/etc. no importan lo que no deben | `tests/unit/test_layering.py` (ampliado) |

## Nivel 2 — Prueba manual contra las simulaciones (opcional)

Con la aplicación levantada (`docker compose up -d db api` tras aplicar la migración) y
`USERS_API_BASE_URL`/`PAGOS_API_BASE_URL` apuntando a instancias locales de los stubs
(`uvicorn app:app --app-dir tests/stubs/users_api --port 8099`,
`uvicorn app:app --app-dir tests/stubs/payments_api --port 8098`):

1. Registrar un token de plataforma (`clinic_subscriptions:write/read/delete`) y uno de clínica
   (`clinic_subscriptions:charge`, con `tenant_id` igual al que se use al crear).
2. `POST /api/v1/clinic-subscriptions` con el token de plataforma → 201, Activa.
3. `POST /api/v1/clinic-subscriptions/{id}/charges` con el token de **clínica** → 201, `pending`,
   con `checkout_url`.
4. Mover el pago a `approved` en el stub de Pagos (`POST /__test__/payments/{payment_id}/status`).
5. `GET /api/v1/clinic-subscriptions/{id}` con el token de plataforma → Activa de nuevo,
   `next_billing_at` avanzado, el cobro reflejado como `approved`.

## Nivel 3 — Pila de punta a punta (Newman/Postman)

**Diferido** (Assumptions del plan): esta especificación no amplía `docker-compose.e2e.yml` ni la
colección de Postman con el recorrido de cobro; el contrato y los stubs de pytest ya cumplen el
Principio V. Queda documentado como trabajo pendiente en
[contracts/e2e-stubs.md](contracts/e2e-stubs.md).

# Guía de validación (quickstart): Cobro Real de Suscripciones de Clínicas

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía se ejecuta cuando la feature esté implementada. El contrato está en
[contracts/](contracts/) y el modelo de datos en [data-model.md](data-model.md).

**Requisitos**: Docker Desktop (Compose), [uv](https://docs.astral.sh/uv/), Python 3.14+. Ninguna
prueba necesita `mailySoft-pagos`, `mailySoft-usuarios` ni Clínicas reales: usan sus simulaciones
([contracts/e2e-stubs.md](contracts/e2e-stubs.md)).

## Nivel 1 — Suite automatizada (pytest, dos niveles — constitución v1.1.0)

```powershell
docker compose up -d db
uv sync
uv run pytest                 # rápida, por defecto (sin PostgreSQL real)
uv run pytest -m slow         # la que toca PostgreSQL real / contrato de la app completa
uv run alembic upgrade head
uv run alembic check
```

**Esperado**: ambos niveles en verde (incluidas las specs 001 a 009, sin regresiones);
`alembic check` responde «No new upgrade operations detected»; la migración `0008` sube y baja sin
error, también sobre una base con datos.

### Mapa historia → pruebas

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| 1 (cobrar) FR-001 a FR-012, SC-001, SC-002 | Cuerpo exacto a Pagos (centavos, `resource_type`/`resource_id`); `Idempotency-Key` determinista; Clínicas dice que no existe/otra organización → 404; Clínicas caída → 503; plan no Activo → 409; ya `approved` ese periodo → 409; `pending`/`rejected` sí reintenta; Pagos caído → 503; 401/403 de Pagos traducidos | `tests/contract/test_clinic_subscriptions_api.py`, `test_clinics_api_client.py`, `test_payments_api_client.py`; `tests/unit/test_clinic_subscription_service.py` |
| 2 (conocer el resultado) FR-013 a FR-015, SC-003 | Un cobro `pending` se sincroniza al consultarlo; uno resuelto no vuelve a llamar a Pagos; Pagos caído durante la sincronización → se devuelve el último estatus local | `tests/contract/test_clinic_subscriptions_api.py`; `tests/unit/test_clinic_subscription_service.py` |
| 3 (historial) FR-023, FR-027 | Paginado; filtra por `tenant_id`/`clinic_subscription_id`; inexistente → 404; sin permiso → 403 | `tests/contract/test_clinic_subscriptions_api.py` |
| Control de acceso (FR-009, FR-023, FR-026, FR-027) | Las 2 operaciones de lectura usan `check`; `charge_clinic_subscription` usa `me` (una sola llamada), compara `tenant_id`, `password_change_required` → 403 | `tests/contract/test_clinic_subscriptions_access_control.py`, `test_permission_coverage.py`; `tests/unit/test_authorization_service.py` |
| Integración con Clínicas y Pagos (FR-016 a FR-022, SC-004) | Asíncrona, sin reintentos, sin seguir redirecciones; variables de entorno; nunca filtra el cuerpo de las dependencias | `tests/contract/test_clinics_api_client.py`, `test_payments_api_client.py` |
| Esquema (Principio VI) | Migración `0008` sube/baja desde cero y con datos previos | `tests/integration/test_clinic_subscriptions_migration.py` |
| Capas (Principio I) | Los módulos nuevos no importan lo que no deben | `tests/unit/test_layering.py` |

## Nivel 2 — Prueba manual contra las simulaciones (opcional)

1. Registrar en el stub de Clínicas una suscripción de clínica (`POST /__test__/clinic-subscriptions`).
2. Registrar en el stub de Usuarios un token con `clinic_subscriptions:charge` y el `tenant_id` de
   esa suscripción.
3. `POST /api/v1/clinic-subscriptions/{id}/charges` con ese token → 201, `pending`, con
   `checkout_url`.
4. Mover el pago a `approved` en el stub de Pagos.
5. `GET .../charges/{charge_id}` → refleja `approved` sin ninguna acción manual aparte de
   consultarlo.

## Nivel 3 — Pila de punta a punta (Newman/Postman)

**Diferido**, igual que la versión anterior de este documento.

# Guía de validación (Fase 1): Periodo de prueba y siguiente pago de cada organización

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Cuatro niveles, de menor a mayor costo. Los comandos son de bash; en PowerShell cambian solo las rutas y los
saltos de línea.

## Prerrequisitos

- Docker con Compose 2.24 o superior, [uv](https://docs.astral.sh/uv/) y Python 3.14 o superior.
- Node.js con npm, solo para Newman (nivel 3).
- Un `.env` con `DATABASE_URL`, `TEST_DATABASE_URL` (la base debe terminar en `_test`), `USERS_API_BASE_URL`,
  `CLINICS_API_BASE_URL`, `PAYMENTS_API_BASE_URL` y `BILLING_CUTOFF_AT` (ver `.env.example`). Las pruebas
  automáticas **no** necesitan las direcciones ni la fecha de corte: usan simulaciones y las definen solas.

## Nivel 1 — rápido, sin base de datos (el ciclo de `/speckit-implement`)

```bash
uv run pytest
```

**Esperado**: todo en verde. Incluye las reglas puras con los 16 ejemplos de referencia
(`tests/unit/test_billing_rules.py`), la configuración nueva, los mensajes y los 22 códigos de error, los
DTOs, los clientes HTTP de Clínicas y Pagos contra sus simulaciones, el Service con dobles (consulta, inicio
del pago, conciliación, degradación) y las reglas de capas. No levanta PostgreSQL ni llama a ningún API real.

## Nivel 2 — completo, con PostgreSQL 17 real (la puerta antes de integrar en `main`)

```bash
docker compose up -d db
docker compose exec db psql -U postgres -c "CREATE DATABASE maily_system_test"   # una vez; ignora el error si ya existe
uv run pytest -m ""
```

**Esperado**: todo en verde, incluidas las pruebas marcadas `slow`:

- `tests/integration/test_subscription_period_repository.py`: creación única del periodo, reclamación de un
  cobro (`pending` → `applied` una sola vez), compare-and-swap de `paid_until`, unicidad de cobros y la
  restricción que liga el estado con sus columnas.
- `tests/integration/test_subscription_periods_migration.py`: `0008` sube y baja; los modelos coinciden con
  la migración (`test_models_match_migrations.py`).
- `tests/contract/test_subscription_periods_api.py` y `…_access_control.py` / `…_degradation.py`: las
  historias 1 a 6 por HTTP con reloj fijo, incluida la prueba de **20 consultas simultáneas** (SC-005).
- `tests/contract/test_permission_coverage.py`: las 15 operaciones protegidas declaran su permiso.

## Nivel 3 — punta a punta con Newman (la otra mitad de la puerta)

```bash
npm ci --prefix tests/postman
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --build --wait api
npm run e2e:periods --prefix tests/postman          # solo esta colección
npm run e2e:all --prefix tests/postman              # las cuatro colecciones, una tras otra
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

**Esperado**: código de salida `0`; `tests/postman/reports/junit-periods.xml` sin fallas. La pila aislada
levanta la API, su base de datos desechable y las simulaciones de Usuarios (`:8012`), Clínicas (`:8013`),
componentes (`:8014`) y **Pagos (`:8015`)**.

## Nivel 4 — recorrido manual contra la pila aislada

Con la pila del nivel 3 arriba (y sin desmontarla), este recorrido reproduce a mano la historia 1, la 2 y la
3. Usa `curl`; el token y el identificador son inventados para la simulación.

```bash
API=http://127.0.0.1:8011; USERS=http://127.0.0.1:8012; CLINICS=http://127.0.0.1:8013; PAGOS=http://127.0.0.1:8015
TOKEN=dueno-de-prueba; ORG=0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b

# 1. La persona de prueba (el Dueño) con los dos permisos nuevos
curl -s -X POST $USERS/__test__/tokens -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"permissions\":[\"subscription_periods:read\",\"subscription_periods:write\"]}"

# 2. Un plan en el catálogo (14 días de prueba, 499.00 al mes) y la organización en la simulación de Clínicas
#    (el plan se crea con la API de suscripciones y un token con subscriptions:write y modules:read)
curl -s -X POST $CLINICS/__test__/organizations -H 'Content-Type: application/json' \
  -d "{\"id\":\"$ORG\",\"subscription_id\":1,\"billing_period\":\"monthly\",\"created_at\":\"$(date -u -d '40 days ago' +%FT%TZ)\",\"owner_token\":\"$TOKEN\"}"

# 3. Consultar: la prueba (14 días) terminó hace unos 26 días → overdue, days_remaining ≈ -26
curl -s $API/api/v1/subscription-periods/$ORG -H "Authorization: Bearer $TOKEN"

# 4. Iniciar el pago → 201 con checkout_url; repetirlo → 200 con el mismo checkout
curl -s -i -X POST $API/api/v1/subscription-periods/$ORG/payments -H "Authorization: Bearer $TOKEN"
curl -s -i -X POST $API/api/v1/subscription-periods/$ORG/payments -H "Authorization: Bearer $TOKEN"

# 5. Aprobar el pago en la simulación de Pagos y consultar: la fecha del siguiente pago se mueve un mes, una vez
PAYMENT=$(curl -s $PAGOS/__test__/payments | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST $PAGOS/__test__/payments/$PAYMENT/status -H 'Content-Type: application/json' -d '{"status":"approved"}'
curl -s $API/api/v1/subscription-periods/$ORG -H "Authorization: Bearer $TOKEN"   # state: current
curl -s $API/api/v1/subscription-periods/$ORG -H "Authorization: Bearer $TOKEN"   # la misma payment_due_at
```

**Esperado**: el paso 3 trae `"state": "overdue"` y `days_remaining` negativo; el 4, `201` y luego `200` con
el mismo `checkout_url`; el 5, `"state": "current"`, `payment_due_at` un mes después de la aprobación y la
misma fecha en la segunda consulta. Para ver la degradación: `curl -X POST $PAGOS/__test__/faults` con
`{"mode":"unavailable","count":5,"operation":"any"}` y repetir la consulta (200 con `"payment_in_progress":
null` mientras haya un cobro pendiente) o el inicio del pago (503 `payments_unavailable`).

## Qué no se prueba contra los servicios reales

Hasta que Usuarios, Clínicas y Pagos entreguen lo pedido (`contracts/pedidos-*.md`), contra ellos las dos
operaciones responden 403 (permisos sin dar de alta) o 503 (`billing_period` ausente, `tenant_id` sin
publicar). Es lo esperado y lo que describe SC-010: nunca un dato inventado.

# Guía de validación (quickstart): Límite de clínicas por suscripción

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía es un **delta** sobre
[specs/006-add-subscription-type/quickstart.md](../006-add-subscription-type/quickstart.md): los
tres niveles (pytest, API real con simulaciones, Postman/Newman), sus comandos de arranque y los
puertos (API `8011`, stub de usuarios `8012`, stub de clínicas `8013`) no cambian. Aquí solo se fija
qué comprobar **de nuevo** (`clinics_limit` obligatorio al crear, su rango según el tipo, su
inmutabilidad en una suscripción Individual al actualizar). A diferencia de `006`, esta feature no
tiene ningún script de reconciliación que validar aparte (research R5): todo se ejercita a través
de las mismas tres operaciones de siempre (crear, consultar, actualizar).

**Enmienda v1.1.0 de la constitución (2026-10-27, posterior al resto de esta guía)**: los tres
niveles de abajo ya no se ejecutan todos como parte de `/speckit-implement`. El Nivel 1 ahora tiene
dos corridas (rápida por defecto, completa con `-m ""`); los Niveles 2 y 3 son la puerta de calidad
antes de integrar a `main` — hoy, mientras no exista un pipeline de CI, responsabilidad de quien
haga ese merge, no de la implementación de la feature.

## Nivel 1 — Suite automatizada (pytest)

Mismos comandos que 001/004/006, con una distinción nueva (Principio V, enmienda 2026-10-27):
`uv run pytest` (sin más) corre solo lo rápido, sin PostgreSQL — es lo que se corre durante la
implementación. Para la corrida completa (incluidas las pruebas marcadas `slow`, que necesitan la
base real), hace falta `docker compose up -d db && uv run pytest -m ""`; junto con
`uv run alembic upgrade head`, `uv run alembic check` y `uv run alembic downgrade base`, esa
corrida completa es la que debe pasar antes de integrar a `main`, no en cada tarea. La migración
`0006` (agrega `subscriptions.clinics_limit` con `DEFAULT 1` y su `CHECK` de dos columnas) se
aplica y se revierte junto con `0001` a `0005`.

### Mapa historia → pruebas (solo lo nuevo)

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| US1 (crear con el límite correcto) FR-002, FR-003 | Crear Individual con `clinics_limit: 1` guarda y devuelve 1; crear Individual con cualquier otro valor (0, 2, 100) → 422 «Individual debe tener límite de clínicas igual a 1»; crear no Individual con `clinics_limit` en 1–100 (incluidos los bordes 1 y 100) guarda ese valor; crear no Individual con 0 o 101 → 422 «debe ser un número entero de 1 a 100»; omitir el campo → 422 obligatorio | `tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_dtos.py` |
| US2 (consultar el límite) FR-004 | El listado y el detalle incluyen `clinics_limit` de cada suscripción, junto a los otros cuatro límites | `tests/contract/test_subscriptions_api.py` |
| US3 (comportamiento al actualizar) FR-005, FR-006 | Enviar `clinics_limit` en la actualización de una Individual —mismo valor (1) o distinto, sola o junto con otro campo válido— se rechaza por completo (422, mensaje propio de inmutabilidad) y no cambia ningún dato, incluido ese otro campo; la misma solicitud sobre una no Individual sí guarda el nuevo valor si está en 1–100, y se rechaza (sin cambiar nada) si no lo está; actualizar sin incluir `clinics_limit` deja el límite igual en cualquier tipo | `tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_service.py` |
| FR-007 (datos existentes) | Una fila insertada **antes** de aplicar `0006` en la prueba de migración queda con `clinics_limit = 1` después de subir (verifica el `DEFAULT`), sea Individual o no | `tests/integration/test_migrations.py` |
| FR-010 (techo informativo) | Crear o actualizar `clinics_limit` no dispara ninguna llamada a la API de clínicas ni se valida contra `clinics_count` | `tests/unit/test_subscription_service.py` (inspección de las llamadas al doble de la API de clínicas) |
| Restricción `CHECK` (research R6, defensivo) | La migración sube y baja sin error; una fila que intentara violar el `CHECK` directamente en la base (sin pasar por la API) lo rechaza con `23514` | `tests/integration/test_migrations.py`, `tests/integration/test_subscriptions_constraints.py` |

El resto de las tablas de 001/004/006 (control de acceso, degradación de clínicas, módulos, capas,
configuración, tipo de suscripción) no cambia: sigue aplicando igual.

## Nivel 2 — La API de verdad, con las simulaciones (manual)

**Puerta de calidad antes de integrar a `main` (Principio V, enmienda 2026-10-27), no parte de
`/speckit-implement`**: levanta la pila e2e completa, lo mismo que exige Newman en el Nivel 3; se
corre una sola vez, al terminar la feature, no en cada tarea.

Mismo arranque que 001/004/006 (pila aislada `tests/postman/docker-compose.e2e.yml`).

Crear una suscripción Individual con el único límite válido, y comprobar los rechazos:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Solo\",\"subscription_type_id\":1,\"monthly_price\":900,\"annual_price\":9000,\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":5000,\"clinics_limit\":1}'
# 201: clinics_limit: 1

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"SoloMal\",\"subscription_type_id\":1,\"monthly_price\":900,\"annual_price\":9000,\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":5000,\"clinics_limit\":5}'
# 422 validation_error: una suscripción Individual debe tener límite de clínicas igual a 1

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Corporativo\",\"subscription_type_id\":2,\"monthly_price\":5000,\"annual_price\":50000,\"consulting_rooms_limit\":20,\"doctors_limit\":30,\"assistants_limit\":20,\"new_patients_per_year_limit\":200000,\"clinics_limit\":25}'
# 201: clinics_limit: 25

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"CorporativoMal\",\"subscription_type_id\":2,\"monthly_price\":5000,\"annual_price\":50000,\"consulting_rooms_limit\":20,\"doctors_limit\":30,\"assistants_limit\":20,\"new_patients_per_year_limit\":200000,\"clinics_limit\":101}'
# 422 validation_error: el límite de clínicas debe ser un número entero de 1 a 100
```

Probar el comportamiento al actualizar (usar los `id` devueltos arriba; se asume `1` = Solo, `3` = Corporativo):

```powershell
curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"clinics_limit\":1,\"monthly_price\":950}'
# 422 validation_error: el límite de clínicas no puede modificarse en una suscripción Individual; monthly_price NO cambia

curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/3 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"clinics_limit\":50}'
# 200: clinics_limit: 50
```

**Esperado**: los códigos y cuerpos indicados en cada línea. Desmontar la pila igual que en 001.

## Nivel 3 — Postman con Newman (punta a punta)

**Puerta de calidad antes de integrar a `main` (Principio V, enmienda 2026-10-27), no parte de
`/speckit-implement`**: responsabilidad de un pipeline de CI o, mientras no exista, de quien
integre el cambio a `main` (ver `tasks.md`, T025).

Mismos comandos que 001/004/006. La carpeta «1. Catálogo» agrega `clinics_limit` a los cuerpos de
`create_subscription` existentes (para no romper el recorrido) y gana
`create_subscription: límite de clínicas inválido para Individual (422)`; la carpeta
«2. Consultar y actualizar» gana `update_subscription: el límite de clínicas no se puede modificar
en una Individual (422)` y `update_subscription: subir el límite de clínicas de una Empresarial`.

## Criterios de éxito → dónde se miden (solo lo nuevo)

| Criterio | Cómo se comprueba |
|---|---|
| SC-001 (100% de las creaciones Individual con límite ≠ 1 se rechazan) | `test_subscriptions_api.py`, `test_subscription_dtos.py` |
| SC-002 (100% de las creaciones no Individual fuera de 1–100 se rechazan) | `test_subscriptions_api.py`, `test_subscription_dtos.py` |
| SC-003 (100% de las respuestas incluye el límite) | `test_subscriptions_api.py` |
| SC-004 (100% de los intentos de modificarlo en Individual se rechaza sin cambiar nada) | `test_subscriptions_api.py`, `test_subscription_service.py` |
| SC-005 (100% de las no Individuales puede ajustarlo en 1–100) | `test_subscriptions_api.py` |
| SC-006 (100% de lo preexistente queda con un límite válido tras el despliegue) | `test_migrations.py` (el `DEFAULT`) |

El resto de los criterios de 001/004/006 no cambia de forma.

# Guía de validación (quickstart): corrección del modelo de datos de la API de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía es un **delta** sobre
[specs/001-subscriptions-api/quickstart.md](../001-subscriptions-api/quickstart.md): los tres niveles
(pytest, API real con simulaciones, Postman/Newman) y sus comandos de arranque no cambian. Aquí solo
se fija qué comprobar **de nuevo** (módulos, límites, precio anual, días de prueba, autoconsumo) y
cómo sembrar el stub ampliado de la API de usuarios. Se ejecuta cuando la feature esté implementada
(`/speckit-implement`).

**Requisito nuevo**: antes de ejercitar cualquier escenario con módulos además de `patients`, el stub
de la API de usuarios debe tener sembrados los 9 módulos de tipo Clínica (research R2); lo hace solo,
al arrancar (`POST /__test__/modules/reset` los repone si una prueba los modificó).

## Nivel 1 — Suite automatizada (pytest)

Mismos comandos que 001 (`uv run pytest`, `uv run alembic upgrade head`, `uv run alembic check`,
`uv run alembic downgrade base`). La migración `0003` se aplica y se revierte junto con `0001` y
`0002`.

### Mapa historia → pruebas (solo lo nuevo)

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| 1 (catálogo) FR-008, Clarifications P4 | El listado y el detalle devuelven los 7 campos nuevos; `module_keys` no dispara ninguna llamada a la API de usuarios (se comprueba contando las peticiones del stub); excluir un módulo no excluye a los que dependen de él | `tests/contract/test_subscriptions_api.py` |
| 3 (crear) FR-011 a FR-020 | `annual_price` y los 4 límites obligatorios (sin ellos, 422); `trial_days`/`self_service` omitidos → `0`/`false`; módulo sin prerrequisito → 409; módulo que la API de usuarios no reconoce → 422; `patients` siempre incluido aunque no se envíe; API de usuarios caída al validar módulos → 503 `module_check_unavailable`; sin módulos además de `patients`, la API de usuarios no se llama | `tests/contract/test_subscriptions_api.py`; `tests/unit/test_subscription_service.py`, `test_subscription_dtos.py`; `tests/unit/test_clinic_modules.py` |
| 5 (actualizar) FR-011 a FR-023 | Cambiar solo el precio anual conserva el resto; bajar un límite por debajo de lo que ya tiene una clínica se acepta igual (esta API no lo comprueba); actualizar módulos de una suscripción Eliminada → 404 **antes** de llamar a la API de usuarios | `tests/contract/test_subscriptions_api.py`; `tests/unit/test_subscription_service.py` |
| Migración | `0003` sube y baja sin error; `alembic check` no detecta diferencias; los `CHECK` nuevos rechazan límites fuera de rango, `trial_days` fuera de 0–3650 y `module_keys` sin `patients` | `tests/integration/test_migrations.py`, `test_subscriptions_constraints.py` |
| Integración de módulos | `list_clinic_module_keys` traduce `200`/`401`/`403`/`5xx`/cuerpo inesperado igual que `check_permission`; una sola llamada por escritura, nunca una por módulo | `tests/contract/test_users_api_client.py` |

El resto de la tabla de 001 (control de acceso, degradación de clínicas, capas, configuración) no
cambia: sigue aplicando igual.

## Nivel 2 — La API de verdad, con las simulaciones (manual)

Mismo arranque que 001. Antes de crear una suscripción con módulos, registra el permiso
`modules:read` además de los cuatro `subscriptions:*`:

```powershell
$h = @{ "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/tokens -Headers $h `
  -Body '{"token":"demo","permissions":["subscriptions:read","subscriptions:write","subscriptions:update","subscriptions:delete","modules:read"]}'
```

Crear el plan «Profesional» del mockup y comprobar los módulos:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Profesional\",\"monthly_price\":1299,\"annual_price\":12990,\"trial_days\":14,\"self_service\":true,\"module_keys\":[\"scheduling\",\"reminders\",\"clinical_records\",\"clinical_record_templates\",\"prescriptions\"],\"consulting_rooms_limit\":2,\"doctors_limit\":3,\"assistants_limit\":2,\"new_patients_per_year_limit\":15000}'
# 201: module_keys incluye "patients" aunque no se envió; clinics_count 0
```

Probar el rechazo por dependencia y por módulo no reconocido:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Avanzado\",\"monthly_price\":2499,\"annual_price\":24990,\"module_keys\":[\"billing\"],\"consulting_rooms_limit\":5,\"doctors_limit\":10,\"assistants_limit\":5,\"new_patients_per_year_limit\":50000}'
# 409 subscription_module_prerequisite_missing (billing exige finance)
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Inventado\",\"monthly_price\":100,\"annual_price\":1000,\"module_keys\":[\"no_existe\"],\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":100}'
# 422 subscription_module_not_found
```

Degradar la API de usuarios solo para módulos (el permiso sigue funcionando):

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8012/__test__/faults -Headers $h -Body '{"mode":"unavailable","count":1,"operation":"modules"}'
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Otro\",\"monthly_price\":100,\"annual_price\":1000,\"module_keys\":[\"scheduling\"],\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":100}'
# 503 module_check_unavailable (el permiso ya se verificó antes: no es authorization_unavailable)
curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo"
# 200: listar sigue funcionando, no llama a la API de usuarios por módulos
```

**Esperado**: los códigos y cuerpos indicados en cada línea. Desmontar la pila igual que en 001.

## Nivel 3 — Postman con Newman (punta a punta)

Mismos comandos que 001. La carpeta «2. Consultar y actualizar» gana dos peticiones (módulo sin
prerrequisito, módulo no reconocido); ver [contracts/e2e-stubs.md](contracts/e2e-stubs.md).

## Criterios de éxito → dónde se miden (solo lo nuevo)

| Criterio | Cómo se comprueba |
|---|---|
| SC-004 (todos los campos nuevos en cada respuesta) | `test_subscriptions_api.py` |
| SC-010 (0 suscripciones guardadas con módulos inconsistentes) | `test_subscription_service.py`, `test_clinic_modules.py` |
| SC-011 (los 4 límites siempre definidos) | `test_subscription_dtos.py` (rechaza la creación sin alguno) |

El resto de los criterios de 001 (SC-001, SC-002, SC-003, SC-005 a SC-009) no cambia de forma; SC-001
se vuelve a medir porque el listado ahora devuelve más campos, pero sigue sin llamar a la API de
usuarios por módulos (research R5), así que el presupuesto de tiempo no cambia.

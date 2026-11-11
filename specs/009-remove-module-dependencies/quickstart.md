# Guía de validación (quickstart): quitar dependencias entre módulos

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía es un **delta** sobre
[specs/008-subscription-modules-table/quickstart.md](../008-subscription-modules-table/quickstart.md):
los tres niveles (pytest, API real con simulaciones, Postman/Newman), sus comandos de arranque y
los puertos (API `8011`, stub de usuarios `8012`, stub de clínicas `8013`) no cambian.

## Nivel 1 — Suite automatizada (pytest)

Mismos comandos que `001`/`004`/`006`/`007`/`008` (dos niveles de ejecución, Principio V v1.1.0):
`uv run pytest` corre solo lo rápido; la corrida completa (`docker compose up -d db && uv run
pytest -m ""`) es la puerta de calidad antes de integrar a `main`. Sin migraciones nuevas que
aplicar ni revertir (ver [data-model.md](data-model.md)).

### Mapa historia → pruebas

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| US1 (FR-001, FR-003) | Crear o actualizar con cualquier combinación de módulos del catálogo activo —incluidas las que antes exigían un prerrequisito ausente— responde 201/200, sin exigir ningún otro módulo | `tests/contract/test_subscriptions_api.py` (casos invertidos, research R8), `tests/unit/test_subscription_service.py` |
| US1, Escenario 1 (Saturno, 18 módulos) | Crear con los 18 módulos reales del catálogo sembrado responde 201 con los 18 en `module_keys` | `tests/contract/test_subscriptions_api.py` (caso nuevo) y la colección de Postman ([e2e-stubs.md](contracts/e2e-stubs.md)) |
| US2 (FR-002) | Una clave que no está en el catálogo activo (`scheduling`, que ya no existe en ningún catálogo) se rechaza con `subscription_module_not_found`, indicando esa clave | `tests/unit/test_subscription_service.py`, `tests/contract/test_subscriptions_api.py` (sin cambios de aserciones) |
| US3 (FR-004) | Ningún código del servicio ni de sus pruebas unitarias referencia una clave de módulo concreta salvo `patients`; `src/clinic_modules.py` solo tiene `PATIENTS_KEY` | `tests/unit/test_clinic_modules.py` (reducido a `test_patients_key`), inspección del módulo |
| FR-005 (código 409 retirado) | `ErrorCode` ya no tiene `SUBSCRIPTION_MODULE_PREREQUISITE_MISSING`; el recuento de códigos del catálogo pasa de 18 a 17 | `tests/unit/test_error_messages.py` |
| FR-006, FR-007, FR-008, FR-009 (sin cambios de comportamiento) | Repetir, sin modificar sus aserciones, cada caso ya existente que no depende de la regla eliminada (`patients` siempre incluido, `module_check_unavailable`, sin llamada si solo se pide `patients`, sin revalidar al leer) | `tests/unit/test_subscription_service.py`, `tests/contract/test_subscriptions_api.py` |

El resto de las tablas de `001`/`004`/`006`/`007`/`008` (control de acceso, degradación de
clínicas, límites, tipo de suscripción, capas, configuración, almacenamiento de módulos) no
cambia: sigue aplicando igual.

## Nivel 2 — La API de verdad, con las simulaciones (manual)

**Puerta de calidad antes de integrar a `main`, no parte de `/speckit-implement`**: mismo arranque
que `001`/`004`/`006`/`007`/`008` (pila aislada `tests/postman/docker-compose.e2e.yml`).

Crear la suscripción «Saturno» con los 18 módulos del catálogo sembrado ([e2e-stubs.md](contracts/e2e-stubs.md))
y confirmar que una combinación que antes se rechazaba por dependencia ahora se acepta:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Saturno\",\"subscription_type_id\":2,\"monthly_price\":2000,\"annual_price\":20000,\"module_keys\":[\"appointments\",\"billing\",\"clinics\",\"consulting_rooms\",\"expenses\",\"finance\",\"incomes\",\"overview\",\"patient_diagnoses\",\"prescriptions\",\"reminders\",\"reports\",\"schedule\",\"services\",\"staff\",\"templates\",\"vital_signs\"],\"consulting_rooms_limit\":5,\"doctors_limit\":5,\"assistants_limit\":5,\"new_patients_per_year_limit\":10000,\"clinics_limit\":5}'
# 201: module_keys incluye los 18 (los 17 pedidos + patients), orden alfabético

curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"module_keys\":[\"reminders\"]}'
# 200: module_keys: ["patients", "reminders"] — antes se habría rechazado (409) por faltar "schedule"

curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"module_keys\":[\"scheduling\"]}'
# 422 subscription_module_not_found: "scheduling" ya no existe en ningún catálogo
```

Desmontar la pila igual que en `001`.

## Nivel 3 — Postman con Newman (punta a punta)

**Puerta de calidad antes de integrar a `main`, no parte de `/speckit-implement`**: mismos
comandos que `001`/`004`/`006`/`007`/`008`. Cambios de contenido en
`MailySoft-System-Suscripciones.postman_collection.json` (detalle completo en
[e2e-stubs.md](contracts/e2e-stubs.md)): se elimina el request del 409 de prerrequisito, se agrega
el de «Saturno» con los 18 módulos, y los cuerpos de ejemplo que usaban claves retiradas
(`scheduling` como válida, `clinical_records`, `clinical_record_templates`) se actualizan al
catálogo sembrado nuevo.

## Criterios de éxito → dónde se miden

| Criterio | Cómo se comprueba |
|---|---|
| SC-001 (los 18 módulos reales, en cualquier combinación, nunca se rechazan por dependencia) | `test_subscriptions_api.py` (caso Saturno), colección de Postman |
| SC-002 (un módulo nuevo se usa sin cambiar código) | Por diseño: `_resolve_modules` ya no conoce ninguna clave fija salvo `patients`; no hay prueba que lo contradiga (confirmado por `test_clinic_modules.py` reducido) |
| SC-003 (100% de las claves no reconocidas siguen rechazándose) | `test_subscription_service.py`, `test_subscriptions_api.py` |
| SC-004 (cero referencias a claves concretas salvo `patients`, en código y pruebas) | Inspección de `src/clinic_modules.py` y `tests/unit/test_clinic_modules.py` |
| SC-005 (cero menciones del error de prerrequisito) | `tests/unit/test_error_messages.py`, `contracts/error-catalog.md`, colección de Postman |

El resto de los criterios de `001`/`004`/`006`/`007`/`008` no cambia de forma.

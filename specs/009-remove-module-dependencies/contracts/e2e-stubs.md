# Contrato: simulación ampliada y colección de Postman (delta sobre `004-correct-subscriptions-api`)

La base (dos simulaciones FastAPI autocontenidas, montadas con `httpx.ASGITransport` en pytest y
como servicios de Docker Compose en la pila e2e) **no cambia**: ver
[specs/001-subscriptions-api/contracts/e2e-stubs.md](../../001-subscriptions-api/contracts/e2e-stubs.md)
y el delta de
[specs/004-correct-subscriptions-api/contracts/e2e-stubs.md](../../004-correct-subscriptions-api/contracts/e2e-stubs.md).
Este documento describe solo lo que cambia en `tests/stubs/users_api/app.py` y en la colección de
Postman; `tests/stubs/clinics_api/app.py` no cambia.

## 1. `tests/stubs/users_api/app.py`: catálogo sembrado realista, ya no los nueve de `src/clinic_modules.py`

La ruta `GET /api/v1/modules?type_id=&status_id=` no cambia de forma. Lo que cambia es **qué**
sembrado trae por defecto: `004` sembraba los 9 módulos que entonces proponía
`src/clinic_modules.py` (research R2 de esa feature) — `scheduling`, `clinical_records` y
`clinical_record_templates` entre ellos, que ya no existen en el catálogo real.

Como esta feature retira esa lista del código (FR-004: `src/clinic_modules.py` no vuelve a tener
ninguna clave fija salvo `patients`), el sembrado del stub deja de describirse como «un espejo de
`src/clinic_modules.py» y pasa a ser, igual que siempre debió ser, un catálogo de prueba propio e
independiente, elegido para parecerse al catálogo real de hoy (18 módulos de tipo Clínica):
`appointments`, `billing`, `clinics`, `consulting_rooms`, `expenses`, `finance`, `incomes`,
`overview`, `patient_diagnoses`, `patients`, `prescriptions`, `reminders`, `reports`, `schedule`,
`services`, `staff`, `templates`, `vital_signs` — las mismas 18 claves de los criterios de
aceptación de `spec.md`. `scheduling` deja de estar sembrada a propósito: es la clave que las
pruebas usan para demostrar «módulo no reconocido» (ya no existe en ningún catálogo, real o de
prueba).

El resto del sembrado (los 4 protegidos de tipo Sistema: `users`, `roles`, `permissions`,
`modules`, para probar que el filtro `type_id=2` los excluye) y la superficie `/__test__/…`
(`POST /__test__/faults`, `POST /__test__/modules/reset`, `GET /__test__/calls`) no cambian de
forma, solo el contenido de lo sembrado.

## 2. Pila de punta a punta — sin cambios

Sin cambios en los servicios de `docker-compose.e2e.yml`.

## 3. Colección de Postman

Se actualiza `tests/postman/collections/MailySoft-System-Suscripciones.postman_collection.json`:

| Carpeta | Cambio |
|---|---|
| 1. Catálogo | `create_subscription: crear «Pro»` pasa a incluir, en `module_keys`, una combinación realista del catálogo nuevo que antes se habría rechazado por dependencia (p. ej. `reminders` sin `schedule`), para demostrar FR-003 en el recorrido de punta a punta, no solo en pytest |
| 1. Catálogo | **Se agrega** `create_subscription: crear «Saturno» con los 18 módulos activos` (Historia 1, Escenario 1 de `spec.md`): los 18 `module_keys` del catálogo sembrado, responde 201 |
| 2. Consultar y actualizar | **Se elimina** `update_subscription: módulo sin prerrequisito se rechaza (409)` (el escenario que probaba ya no existe: ninguna combinación se rechaza por dependencia) |
| 2. Consultar y actualizar | `update_subscription: módulo no reconocido se rechaza (422)` sigue igual de forma; su cuerpo usa `scheduling` como la clave que ya no existe en ningún catálogo (antes era una clave inventada cualquiera) |
| 3 a 6 | Sin cambios de fondo; los cuerpos de ejemplo que usaban las claves retiradas (`scheduling`, `clinical_records`, `clinical_record_templates`) se actualizan a claves del catálogo sembrado nuevo, sin cambiar lo que cada caso demuestra |

La prueba `tests/contract/test_postman_collection.py` sigue sin cambios de fondo: sigue comparando
la colección contra las operaciones del OpenAPI (que no cambian de nombre ni de cantidad).

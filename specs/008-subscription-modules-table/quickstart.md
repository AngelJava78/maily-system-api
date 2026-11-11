# Guía de validación (quickstart): módulos de la suscripción en su propia tabla

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía es un **delta** sobre
[specs/007-add-clinics-limit/quickstart.md](../007-add-clinics-limit/quickstart.md): los tres
niveles (pytest, API real con simulaciones, Postman/Newman), sus comandos de arranque y los puertos
(API `8011`, stub de usuarios `8012`, stub de clínicas `8013`) no cambian. Como esta corrección no
modifica el contrato publicado (FR-004), lo que hay que comprobar aquí no es un caso nuevo de la
API, sino que **todo lo que ya pasaba antes sigue pasando igual**, más las dos garantías nuevas que
solo se ven a nivel de los datos (FR-002, FR-003).

## Nivel 1 — Suite automatizada (pytest)

Mismos comandos que 001/004/006/007 (dos niveles de ejecución, Principio V v1.1.0): `uv run pytest`
corre solo lo rápido; la corrida completa (`docker compose up -d db && uv run pytest -m ""`, junto
con `uv run alembic upgrade head`, `uv run alembic check` y `uv run alembic downgrade base`) es la
puerta de calidad antes de integrar a `main`. La migración `0007` (crea `subscription_modules`,
migra los datos y quita `module_keys` de `subscriptions`) se aplica y se revierte junto con `0001`
a `0006`.

### Mapa historia → pruebas (solo lo nuevo o lo que cambia de capa)

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| US1 (comportamiento sin cambios) FR-004 a FR-008 | Repetir, sin modificar sus aserciones, cada caso ya existente de módulos (válido, no reconocido por `users-api`, sin prerrequisito, `users-api` sin responder, `patients` implícito, reemplazo completo al actualizar): todos deben seguir pasando tal cual, ahora contra el almacenamiento nuevo | `tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_service.py` (sin cambios de aserciones; prueban una capa que no cambió, research R3/R8) |
| US2 (datos existentes) FR-003 | Insertar, **antes** de aplicar `0007` en la prueba de migración, suscripciones con distintos `module_keys` (incluida una con solo `patients`); tras subir, cada una tiene en `subscription_modules` exactamente esas mismas claves, ni una más ni una menos | `tests/integration/test_migrations.py` |
| US3 (sin duplicados, sin huérfanos) FR-002 | Insertar directamente dos filas iguales (`subscription_id`, `module_key`) en `subscription_modules` → la base lo rechaza (`23505`, la propia clave primaria); insertar una fila con un `subscription_id` que no existe → la base lo rechaza (`23503`, la `FOREIGN KEY`) | `tests/integration/test_subscriptions_constraints.py` |
| FR-001, FR-009 (una fila por módulo; reemplazo atómico) | Tras `create()`, `subscription_modules` tiene exactamente una fila por cada clave devuelta; tras `update()` con un nuevo conjunto completo, las filas que ya no están en el conjunto nuevo desaparecen y las nuevas aparecen, en una sola transacción | `tests/integration/test_subscription_repository.py` |
| FR-010 (baja lógica conserva los módulos) | Eliminar (baja lógica) una suscripción con varios módulos y comprobar que sus filas en `subscription_modules` siguen ahí, sin cambios | `tests/integration/test_subscription_repository.py` |
| Reversibilidad (research R6) | La migración `0007` sube y baja sin error; tras bajarla, `subscriptions.module_keys` queda con las mismas claves que tenía cada suscripción antes de subirla | `tests/integration/test_migrations.py` |

El resto de las tablas de 001/004/006/007 (control de acceso, degradación de clínicas, límites,
tipo de suscripción, capas, configuración) no cambia: sigue aplicando igual.

## Nivel 2 — La API de verdad, con las simulaciones (manual)

**Puerta de calidad antes de integrar a `main`, no parte de `/speckit-implement`**: mismo arranque
que 001/004/006/007 (pila aislada `tests/postman/docker-compose.e2e.yml`).

Crear una suscripción con módulos además de `patients`, confirmar que se devuelven igual que antes,
y comprobar que el reemplazo completo al actualizar deja exactamente el conjunto nuevo:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"ConModulos\",\"subscription_type_id\":2,\"monthly_price\":2000,\"annual_price\":20000,\"module_keys\":[\"scheduling\",\"reminders\"],\"consulting_rooms_limit\":5,\"doctors_limit\":5,\"assistants_limit\":5,\"new_patients_per_year_limit\":10000,\"clinics_limit\":5}'
# 201: module_keys: ["patients", "reminders", "scheduling"] (orden alfabético, igual que antes)

curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"module_keys\":[\"finance\",\"billing\"]}'
# 200: module_keys: ["billing", "finance", "patients"] — scheduling y reminders ya no aparecen
```

**Esperado**: los mismos códigos y cuerpos que daría la versión anterior a esta corrección para las
mismas solicitudes (FR-004). Desmontar la pila igual que en 001.

## Nivel 3 — Postman con Newman (punta a punta)

**Puerta de calidad antes de integrar a `main`, no parte de `/speckit-implement`**: mismos comandos
y mismas colecciones que 001/004/006/007. Ningún caso de
`MailySoft-System-Suscripciones.postman_collection.json` necesita cambiar: esta corrección no
modifica ninguna solicitud ni ninguna respuesta esperada (FR-004), así que la colección existente
sigue siendo la prueba de que el contrato no se rompió.

## Criterios de éxito → dónde se miden

| Criterio | Cómo se comprueba |
|---|---|
| SC-001 (100% de los escenarios de validación de módulos se resuelve igual que antes) | `test_subscriptions_api.py`, `test_subscription_service.py` (mismas aserciones, sin cambios) |
| SC-002 (0 casos de pérdida o de módulos de más al desplegar) | `test_migrations.py` |
| SC-003 (imposible, no solo improbable, un módulo duplicado o huérfano) | `test_subscriptions_constraints.py` (`23505`, `23503`) |
| SC-004 (reemplazo completo sigue funcionando sin pasos nuevos) | `test_subscriptions_api.py`, `test_subscription_repository.py` |

El resto de los criterios de 001/004/006/007 no cambia de forma.

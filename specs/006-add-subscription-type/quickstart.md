# Guía de validación (quickstart): Tipo de suscripción (Individual o Empresarial)

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Esta guía es un **delta** sobre
[specs/004-correct-subscriptions-api/quickstart.md](../004-correct-subscriptions-api/quickstart.md):
los tres niveles (pytest, API real con simulaciones, Postman/Newman), sus comandos de arranque y los
puertos (API `8011`, stub de usuarios `8012`, stub de clínicas `8013`) no cambian. Aquí solo se fija
qué comprobar **de nuevo** (`subscription_type_id` obligatorio al crear, el tipo —un catálogo, como
el estatus— visible como objeto `{id, name}` en toda lectura, inmutable) y cómo validar el script de
reconciliación (FR-009, FR-010), que no es una ruta de esta API. Se ejecuta cuando la feature esté
implementada (`/speckit-implement`).

## Nivel 1 — Suite automatizada (pytest)

Mismos comandos que 001/004 (`uv run pytest`, `uv run alembic upgrade head`, `uv run alembic check`,
`uv run alembic downgrade base`). La migración `0005` (crea `subscription_types`, la siembra, y
agrega `subscriptions.subscription_type_id`) se aplica y se revierte junto con `0001` a `0004`.

### Mapa historia → pruebas (solo lo nuevo)

| Historia / requisito | Qué se comprueba | Dónde |
|---|---|---|
| US1 (crear con tipo) FR-002 | Crear con `subscription_type_id: 1` y con `2` guarda y devuelve el tipo correcto (como objeto `{id, name}`); falta el campo, es `null`, no es entero o es `<= 0` → 422 «obligatorio y … positivo»; un entero positivo que no existe en `subscription_types` (p. ej. `99`) → 422 `subscription_type_not_found` | `tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_dtos.py`, `tests/unit/test_subscription_service.py` |
| US2 (consultar tipo) FR-003 | El listado y el detalle incluyen `subscription_type: {id, name}` de cada suscripción, sin mezclarse entre una Individual y una Empresarial | `tests/contract/test_subscriptions_api.py` |
| US3 (inmutable) FR-004 | Enviar `subscription_type_id` en la actualización —con el mismo valor que ya tiene o con otro, sola o junto con otro campo válido— se rechaza por completo (422, mensaje propio de inmutabilidad) y no cambia ningún dato, incluido el otro campo que traía la misma solicitud; actualizar sin incluirlo cambia los demás campos con normalidad | `tests/contract/test_subscriptions_api.py`, `tests/unit/test_subscription_service.py` |
| FR-005 | Eliminar una suscripción Individual o Empresarial sigue las reglas ya vigentes (clínicas asignadas); el tipo no las cambia | `tests/unit/test_subscription_service.py` (caso existente, solo se repite con los dos tipos) |
| FR-001 (catálogo) | `subscription_types` existe con exactamente `(1, 'Individual')` y `(2, 'Empresarial')` tras `0005`; esta API no publica ninguna ruta para administrarlo | `tests/integration/test_migrations.py` |
| Migración | `0005` sube y baja sin error; `alembic check` no detecta diferencias; la clave foránea rechaza un `subscription_type_id` que no exista en `subscription_types`; una fila insertada **antes** de aplicar `0005` en la prueba de migración queda con `subscription_type_id = 1` después de subir (verifica el `DEFAULT`, FR-001/FR-008) | `tests/integration/test_migrations.py`, `test_subscriptions_constraints.py` |
| Script de reconciliación FR-009 | Con `FakeClinicsApi(counts={1: 1, 2: 2, 3: 5})`, tras ejecutar la reconciliación la suscripción 1 sigue en `SubscriptionType.INDIVIDUAL` (1) y las 2 y 3 quedan en `SubscriptionType.ENTERPRISE` (2); una suscripción sin ninguna clínica (no aparece en `counts`) sigue en Individual | `tests/unit/test_subscription_service.py` (o un módulo nuevo dedicado al backfill) |
| Script de reconciliación FR-010 | Con `FakeClinicsApi(fail=True)` (o el stub con un fallo `unavailable` de `count: 2`), el bucle de reintento no marca nada como terminado hasta que una llamada tiene éxito; nunca asigna un tipo a partir de una respuesta fallida | `tests/unit/test_backfill_subscription_types.py`, con el bucle de reintento extraído a una función testable (sin `time.sleep` real: una función de espera inyectada) |

El resto de las tablas de 001/004 (control de acceso, degradación de clínicas, módulos, capas,
configuración) no cambia: sigue aplicando igual.

## Nivel 2 — La API de verdad, con las simulaciones (manual)

Mismo arranque que 001/004 (pila aislada `tests/postman/docker-compose.e2e.yml`).

Crear una suscripción Individual (`subscription_type_id: 1`) y una Empresarial (`2`), y comprobar el
rechazo sin tipo:

```powershell
curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Solo\",\"subscription_type_id\":1,\"monthly_price\":900,\"annual_price\":9000,\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":5000}'
# 201: subscription_type: {"id": 1, "name": "Individual"}

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"Corporativo\",\"subscription_type_id\":2,\"monthly_price\":5000,\"annual_price\":50000,\"consulting_rooms_limit\":20,\"doctors_limit\":30,\"assistants_limit\":20,\"new_patients_per_year_limit\":200000}'
# 201: subscription_type: {"id": 2, "name": "Empresarial"}

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"SinTipo\",\"monthly_price\":100,\"annual_price\":1000,\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":100}'
# 422 validation_error: subscription_type_id es obligatorio y debe ser un número entero positivo

curl.exe -s -X POST http://127.0.0.1:8011/api/v1/subscriptions -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"name\":\"TipoInventado\",\"subscription_type_id\":99,\"monthly_price\":100,\"annual_price\":1000,\"consulting_rooms_limit\":1,\"doctors_limit\":1,\"assistants_limit\":1,\"new_patients_per_year_limit\":100}'
# 422 subscription_type_not_found: no existe el tipo 99
```

Probar la inmutabilidad (usar el `id` devuelto por la primera creación, p. ej. `1`):

```powershell
curl.exe -s -X PATCH http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo" -H "Content-Type: application/json" `
  -d '{\"subscription_type_id\":2,\"monthly_price\":950}'
# 422 validation_error: el tipo de suscripción no puede modificarse una vez creada; monthly_price NO cambia (se rechaza la solicitud completa)
```

**Esperado**: los códigos y cuerpos indicados en cada línea. Desmontar la pila igual que en 001.

## Nivel 2b — El script de reconciliación (manual, contra la misma pila)

El script no es una ruta de la API: se ejecuta dentro del contenedor de la aplicación (misma imagen),
contra la misma base de datos y el mismo `clinics-api-stub` de la pila e2e.

1. Con la pila de Nivel 2 ya levantada y al menos tres suscripciones creadas (ids `1`, `2`, `3`),
   fija conteos de clínicas en el stub: la 1 con una sola clínica, la 2 y la 3 con varias.

   ```powershell
   curl.exe -s -X POST http://127.0.0.1:8013/__test__/counts -H "Content-Type: application/json" -d '{\"1\":1,\"2\":3,\"3\":2}'
   ```

2. Ejecuta el script con un token válido para esa pila (cualquiera que el stub de clínicas acepte: no
   comprueba permisos en la simulación, solo que haya un `Bearer`, research/`e2e-stubs.md` de 001):

   ```powershell
   docker compose -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml `
     -p maily-system-e2e run --rm -e BACKFILL_ACCESS_TOKEN=demo api `
     python -m src.scripts.backfill_subscription_types
   ```

3. Comprueba el resultado: la suscripción 1 sigue con `subscription_type: {"id": 1, "name":
   "Individual"}`; la 2 y la 3 quedan con `{"id": 2, "name": "Empresarial"}`.

   ```powershell
   curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions/1 -H "Authorization: Bearer demo"   # Individual
   curl.exe -s http://127.0.0.1:8011/api/v1/subscriptions/2 -H "Authorization: Bearer demo"   # Empresarial
   ```

4. Repetir el mismo comando del paso 2 una segunda vez: debe terminar sin error y sin cambiar nada
   (idempotente).

5. Para ver el reintento sin límite (FR-010): antes del paso 2, registra un fallo temporal en el stub
   de clínicas y confirma que el script no termina hasta que el stub vuelve a responder:

   ```powershell
   curl.exe -s -X POST http://127.0.0.1:8013/__test__/faults -H "Content-Type: application/json" -d '{\"mode\":\"unavailable\",\"count\":2}'
   ```

   El script debe reintentar (al menos 2 veces) y terminar con éxito en el tercer intento, sin haber
   marcado ninguna suscripción con un tipo adivinado mientras tanto.

## Nivel 3 — Postman con Newman (punta a punta)

Mismos comandos que 001/004. La carpeta «1. Catálogo» agrega `subscription_type_id` a los cuerpos
de `create_subscription` existentes (para no romper el recorrido) y gana
`create_subscription: sin tipo (422)`; la carpeta «2. Consultar y actualizar» gana
`update_subscription: el tipo no se puede modificar (422)`. El script de reconciliación **no** se
ejercita desde Postman (no es una ruta HTTP de esta API): se valida en el Nivel 2b.

## Criterios de éxito → dónde se miden (solo lo nuevo)

| Criterio | Cómo se comprueba |
|---|---|
| SC-001 (100% de las creaciones sin tipo válido se rechazan) | `test_subscriptions_api.py`, `test_subscription_dtos.py` |
| SC-002 (100% de las respuestas incluye el tipo) | `test_subscriptions_api.py` |
| SC-003 (100% de los intentos de modificar el tipo se rechaza sin cambiar nada) | `test_subscriptions_api.py`, `test_subscription_service.py` |
| SC-004 (100% de lo preexistente queda con un tipo tras el despliegue) | `test_migrations.py` (el `DEFAULT`) + la prueba del script de reconciliación (Nivel 1) |
| SC-005 (el sistema de clínicas conoce el tipo solo con esta API) | Cubierto por el contrato (`contracts/openapi-subscriptions.yaml`, `subscription_type` en `SubscriptionRead`); no hay una prueba automatizada de **otro** repositorio desde aquí |
| SC-006 (crear no toma más tiempo ni pasos) | Inspección manual del Nivel 2: un campo obligatorio más, sin pasos adicionales |

El resto de los criterios de 001/004 no cambia de forma.

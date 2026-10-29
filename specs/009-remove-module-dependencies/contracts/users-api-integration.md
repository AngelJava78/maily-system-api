# Contrato consumido: API de usuarios (FR-001 a FR-004; delta sobre `004-correct-subscriptions-api`)

Esta feature **recorta** la Operación 2 ya descrita en
[specs/004-correct-subscriptions-api/contracts/users-api-integration.md](../../004-correct-subscriptions-api/contracts/users-api-integration.md):
quita el paso local de dependencias entre módulos y la suposición de un catálogo mínimo fijo de
nueve módulos. La Operación 1 (comprobar el permiso) y el resto de la forma de la llamada (ruta,
parámetros, traducción de respuestas, «falla cerrada») **no cambian**: se repiten aquí solo los
puntos que esta feature modifica.

## Operación 2: catálogo de módulos de tipo Clínica — sin cambios de forma, cambia su uso

```http
GET {USERS_API_BASE_URL}/api/v1/modules?type_id=2&status_id=1
Authorization: Bearer <el token tal como llegó>
Accept: application/json
```

Sin cambios respecto a `004`: cuándo se llama (solo al crear o actualizar módulos, solo si la
solicitud pide algo además de `patients`), los parámetros (`type_id=2`, `status_id=1`), la
respuesta esperada (un arreglo de objetos de los que solo se usa `key`) y la traducción de fallas
(`UsersApiRejectedToken`, `UsersApiUnavailable` → `503 module_check_unavailable`).

### Cómo se usa la respuesta (Service, no el cliente HTTP) — reemplaza el paso 2 de `004`

1. `missing = module_keys_pedidos − {"patients"} − {claves recibidas}`; si `missing` no está
   vacío, `subscription_module_not_found` (422), reportando las claves de `missing`.
2. ~~Si todas las claves pedidas existen, se valida la dependencia local...~~ **Se retira
   (FR-003)**: ya no hay ningún paso de dependencias. Las claves pedidas que sí existen en el
   catálogo activo son válidas en cualquier combinación entre sí.
3. El conjunto final que se guarda es `module_keys_pedidos ∪ {"patients"}`, ordenado
   alfabéticamente (sin cambios).

## Reglas de la integración — sin cambios

Reenvío de `Authorization`, sin caché ni reintentos, sin redirecciones, mismo tiempo máximo: todo
igual que en `004`. Único cambio de capas: `SubscriptionService` ya no traduce a
`SubscriptionModulePrerequisiteMissingError` (se elimina esa excepción, FR-005); sigue traduciendo
a `SubscriptionModuleNotFoundError` o `ModuleCheckUnavailableError`.

## Qué debe estar listo en el API de usuarios — reemplaza el punto 3 de `004`

El punto 3 de `004` («los nueve módulos de tipo Clínica dados de alta, con estas claves
propuestas: `patients`, `scheduling`, `reminders`, `clinical_records`, `clinical_record_templates`,
`prescriptions`, `finance`, `reports`, `billing`») asumía un catálogo mínimo fijo para poder aplicar
la regla de dependencias (FR-016 de `004`). Esta feature elimina esa suposición (FR-010 de
`009`, reemplaza FR-016 de `004`): **no hay ningún catálogo mínimo que esta API necesite conocer de
antemano**. El único módulo que esta API sigue conociendo de antemano es `patients`
(`src/clinic_modules.py`, `PATIENTS_KEY`); cualquier otro módulo de tipo Clínica con estatus Activo
que la API de usuarios tenga en el momento de la operación es válido, sea cual sea su clave, se
haya dado de alta antes o después de esta entrega (FR-004, SC-002).

Los puntos 1 (`GET /api/v1/authorization/check`), 2 (`GET /api/v1/modules` publicada) y 4 (permiso
`modules:read`) de `004` no cambian.

Mientras no esté disponible la API de usuarios real, el desarrollo y las pruebas siguen usando la
simulación ([e2e-stubs.md](e2e-stubs.md)); sin ella, cualquier suscripción que pida un módulo
además de `patients` se sigue rechazando con `503 module_check_unavailable` (sin cambios).

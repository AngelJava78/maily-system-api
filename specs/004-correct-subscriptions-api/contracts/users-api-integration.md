# Contrato consumido: API de usuarios (FR-001 a FR-005, FR-015 a FR-020; Principios VIII y IX)

Esta feature **amplía** el contrato ya descrito en
[specs/001-subscriptions-api/contracts/users-api-integration.md](../../001-subscriptions-api/contracts/users-api-integration.md)
(la operación de permisos, sin cambios) con una segunda operación consumida: el catálogo de módulos de
tipo Clínica.

## Operación 1: comprobar el permiso — sin cambios

Ver el documento de `001-subscriptions-api`. Las 6 operaciones de esta API siguen exigiendo el mismo
permiso de siempre (`subscriptions:read|write|update|delete`), comprobado de la misma forma.

## Operación 2 (nueva): catálogo de módulos de tipo Clínica

**Fuente de verdad**: `mailySoft-usuarios`, feature `013-modules-permissions-catalogs`
(`specs/013-modules-permissions-catalogs/contracts/openapi-modules.yaml`, operación `list_modules`).
**Estado a la fecha de este contrato (2026-10-23): spec y la mayor parte del código escritos, pero
nada comprometido a git ni desplegado** (ver «Qué debe estar listo» más abajo).

```http
GET {USERS_API_BASE_URL}/api/v1/modules?type_id=2&status_id=1
Authorization: Bearer <el token tal como llegó>
Accept: application/json
```

- Se llama **solo** al crear una suscripción o al actualizar sus módulos, y **solo si la solicitud
  pide algún módulo además de `patients`** (research R5). Nunca al listar ni al consultar.
- `type_id=2` pide los módulos de tipo Clínica (el `1` es Sistema); `status_id=1` pide solo los
  Activos. Ambos se envían explícitos aunque `status_id=1` sea el valor por defecto de esa API.
- Respuesta `200` esperada: un arreglo de objetos `ModuleRead`, de los que esta API **solo usa el
  campo `key`** (ignora `id`, `name`, `description`, `sort_order`, `status`, `type`,
  `active_permissions_count`):

  ```json
  [
    { "id": 5, "key": "patients", "name": "Pacientes", "status": {"id": 1, "name": "Activo"}, "type": {"id": 2, "name": "Clínica"}, "...": "..." },
    { "id": 6, "key": "scheduling", "...": "..." }
  ]
  ```

### Traducción de las respuestas

| Respuesta del API de usuarios | Resultado aquí |
|---|---|
| `200` con un arreglo de objetos, cada uno con `key` (cadena no vacía) | Se usa el conjunto de `key` recibidos para validar el `module_keys` de la solicitud |
| `200` con un cuerpo que no es un arreglo, o un elemento sin `key` de cadena | `UsersApiUnavailable` (misma excepción que la operación 1) |
| `401` (token rechazado) | `UsersApiRejectedToken` (misma traducción que la operación 1: 401 con el código que corresponda) |
| `403` (el token no tiene `modules:read`) | `UsersApiUnavailable` → `503 module_check_unavailable` (ver nota de permisos abajo; **no** es lo mismo que «módulo no reconocido») |
| Cualquier otro `4xx`/`5xx`, `429`, cuerpo no JSON, redirección, tiempo agotado, error de red | `UsersApiUnavailable` → `503 module_check_unavailable` |

**Falla cerrada**: igual que la operación 1, cualquier caso no listado es «no disponible»; nunca se
crea ni se actualiza una suscripción por duda.

### Cómo se usa la respuesta (Service, no el cliente HTTP)

1. `missing = module_keys_pedidos − {"patients"} − {claves recibidas}`; si `missing` no está vacío,
   `subscription_module_not_found` (422), reportando las claves de `missing`.
2. Si todas las claves pedidas existen, se valida la dependencia local (`src/clinic_modules.py`, sin
   otra llamada): `subscription_module_prerequisite_missing` (409) si falta un prerrequisito.
3. El conjunto final que se guarda es `module_keys_pedidos ∪ {"patients"}`, ordenado alfabéticamente.

## Reglas de la integración (ambas operaciones)

- **Reenvío**: la cabecera `Authorization` se reenvía sin modificar; no se reenvía ninguna otra
  cabecera.
- **Sin caché ni reintentos**: cada escritura que toca módulos produce **como mucho una** llamada
  adicional (nunca una por módulo).
- **Sin redirecciones**, mismo tiempo máximo (`USERS_API_TIMEOUT_SECONDS`) y misma advertencia de
  `http://` no local que la operación 1 (son el mismo cliente, `UsersApiClient`).
- **Capas**: `src/integrations/users_api.py` (`UsersApiClient.list_clinic_module_keys`) solo habla
  HTTP y devuelve un `frozenset[str]` o lanza `UsersApiRejectedToken`/`UsersApiUnavailable` (las
  mismas excepciones que ya existen); `SubscriptionService` las traduce a
  `SubscriptionModuleNotFoundError`, `SubscriptionModulePrerequisiteMissingError` o
  `ModuleCheckUnavailableError`.

## Qué debe estar listo en el API de usuarios

1. La operación `GET /api/v1/authorization/check` (sin cambios respecto a 001).
2. La operación `GET /api/v1/modules` publicada (spec `013-modules-permissions-catalogs`), **terminada,
   comprometida a git y desplegada** — a la fecha de este contrato no lo está (research R2, plan.md
   «Puntos a confirmar»).
3. **Los nueve módulos de tipo Clínica dados de alta**, con estas claves propuestas (research R2):
   `patients`, `scheduling`, `reminders`, `clinical_records`, `clinical_record_templates`,
   `prescriptions`, `finance`, `reports`, `billing`. Si quien los crea usa otras claves,
   `src/clinic_modules.py` y este documento deben actualizarse juntos.
4. **El permiso `modules:read` asociado al mismo rol que ya tiene `subscriptions:write` y
   `subscriptions:update`.** Sin este permiso, toda creación o actualización que incluya módulos
   además de `patients` falla siempre con `503 module_check_unavailable`, aunque la API de usuarios
   esté sana — no es un error de esta API ni de la persona que la usa, sino de la asociación de roles
   y permisos en la API de usuarios.

Mientras no esté listo, el desarrollo y las pruebas usan la simulación ampliada
([e2e-stubs.md](e2e-stubs.md)); sin la API de usuarios real, cualquier suscripción que pida un módulo
además de `patients` se rechaza con `503 module_check_unavailable` (comportamiento especificado, no un
error).

# Contrato consumido: API de usuarios — ampliación (FR-012, FR-030, FR-031; research R1)

Amplía `specs/001-subscriptions-api/contracts/users-api-integration.md`, que sigue vigente sin
cambios para `clinic_subscriptions:read/write/delete` (usan `GET /api/v1/authorization/check`, igual
que siempre). Este documento cubre **solo** la operación nueva que consume
`charge_clinic_subscription`.

## Operación consumida

```http
GET {USERS_API_BASE_URL}/api/v1/authorization/me
Authorization: Bearer <el token tal como llegó>
Accept: application/json
```

Fuente de verdad: `mailySoft-usuarios` spec 009 (`contracts` de esa spec), ampliada por la spec 019
con `tenant_id`. Ya la consumen `mailySoft-agenda` y `mailySoft-pagos` con la misma forma.

- Respuesta `200` esperada (campos que este servicio usa; el resto se ignora, igual que hace Agenda):

  ```json
  {
    "user": { "id": "…", "status": { "id": 1, "name": "Activo" } },
    "tenant_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
    "roles": [
      { "id": 5, "name": "Owner", "permissions": ["clinic_subscriptions:charge", "…"] }
    ],
    "password_change_required": false
  }
  ```

- `tenant_id` es `null` cuando quien llama no tiene organización (p. ej. un rol de Sistema) o no
  tiene usuario en Usuarios.
- Los **permisos de quien llama** se calculan aquí como la unión de `permissions` de todos los
  elementos de `roles` (que ya son solo los roles Activos, por contrato de Usuarios); no hace falta
  una segunda llamada a `check` (sería una segunda consulta por la misma petición, que el Principio
  VIII prohíbe).

## Traducción de la respuesta (`AuthorizationService.require_as_caller`)

| Respuesta de Usuarios | Resultado aquí |
|---|---|
| `200`, `password_change_required: true` | `403 password_change_required` (no se ejecuta el cobro) |
| `200`, `password_change_required: false`, `clinic_subscriptions:charge` **no** está en la unión de permisos | `403 permission_denied` |
| `200`, con el permiso, pero `tenant_id` distinto del de la suscripción de clínica o `null` | `404 clinic_subscription_not_found` (FR-030: no se revela que existe) — lo decide el Service, no esta traducción, que solo entrega el `CallerAccess` |
| `401` con `code` = `unauthenticated` / `token_expired` / `invalid_token`, o cuerpo ilegible | Igual que el contrato de `check` (001): `401` con el código correspondiente |
| `200` con cuerpo que no es JSON, sin `tenant_id` (la clave debe estar siempre, aunque sea `null`), sin `roles` como lista o un elemento sin `permissions` como lista | `503 authorization_unavailable` |
| `503`, cualquier otro `5xx`, `429`, cualquier otro `4xx`, `3xx`, tiempo agotado, error de red/TLS | `503 authorization_unavailable` (igual que el contrato de `check`) |

**Falla cerrada**: igual que `check` — cualquier caso no listado es `503 authorization_unavailable`;
nunca se dispara un cobro por duda.

## Reglas (iguales a las del contrato de `check`, no se repiten aquí salvo diferencias)

- Una sola llamada a Usuarios por petición (ahora a `/me` en vez de a `/check`, nunca ambas).
- El token se reenvía sin modificar; ninguna otra cabecera de la petición original se reenvía.
- Sin caché ni reintentos; sin seguir redirecciones; mismo límite de 8 192 bytes del token.
- `USERS_API_TIMEOUT_SECONDS` (la misma variable que ya existe) también acota esta llamada.
- **Capas**: `UsersApiClient.get_current_access` solo habla HTTP y devuelve/lanza lo mismo que
  `check_permission` (mismas excepciones, `UsersApiRejectedToken`/`UsersApiUnavailable`) más el
  `CallerAccess` en el caso de éxito; `AuthorizationService.require_as_caller` hace la traducción de
  arriba; `src/security.py` la expone como una dependencia nueva
  (`require_caller(Permission.CLINIC_SUBSCRIPTIONS_CHARGE)`) que entrega el `CallerAccess` (con su
  `tenant_id`) al Router, igual que `SecuredRoute`/`CallerContext` de `mailySoft-pagos`.

## Qué debe estar listo en el API de usuarios

1. `GET /api/v1/authorization/me` con `tenant_id` (ya está: spec 009 ampliada por la 019).
2. El permiso `clinic_subscriptions:charge` en su catálogo, asociado a un rol de tipo **Clínica**
   (p. ej. Owner); y `clinic_subscriptions:read/write/delete` asociados a un rol de **Sistema**
   (p. ej. Administrator) — prerrequisito documentado (FR-025), no dado de alta por esta spec.

Mientras no esté listo, el desarrollo y las pruebas usan la simulación ampliada
(`contracts/e2e-stubs.md`); sin ese permiso en el Usuarios real, `charge_clinic_subscription`
responde `403 permission_denied` para cualquier token, que es el comportamiento especificado (nunca
se abre una operación por duda).

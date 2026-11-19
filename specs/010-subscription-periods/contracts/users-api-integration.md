# Contrato consumido: API de usuarios (FR-001, FR-002, FR-005, FR-047; Principio VIII)

> **Estado**: la operación de decisión **existe y no cambia**; lo que falta son **permisos del catálogo y un
> dato de identidad**, que se piden en [pedidos-usuarios.md](pedidos-usuarios.md). Hasta entonces, contra el
> servicio real toda petición a las dos operaciones recibe 403, y las pruebas usan la simulación
> (`tests/stubs/users_api`), que concede o niega cualquier permiso `recurso:acción`.

## Operación consumida (sin cambios)

```http
GET {USERS_API_BASE_URL}/api/v1/authorization/check?permission=subscription_periods:read
Authorization: Bearer <el token de la persona, tal como llegó>
```

La misma de las demás operaciones (contrato en
[users-api-integration.md de la feature 001](../../001-subscriptions-api/contracts/users-api-integration.md)):
`200 {"permission": "...", "allowed": true|false}`; `401` con `unauthenticated`, `token_expired` o
`invalid_token`; cualquier otra cosa → 503 `authorization_unavailable`. Una consulta por petición, por el
permiso exacto de la operación, sin caché y **antes** de validar nada (Principio VIII). Esta API **no**
consulta `GET /api/v1/authorization/me` y no necesita `tenant_id` para sí misma.

## Lo que esta feature necesita que exista en el API de usuarios

| Qué | Para qué | Quién lo usa | Estado |
|---|---|---|---|
| Módulo `subscription_periods` (tipo **Sistema**, ver abajo) con los permisos **`subscription_periods:read`** y **`subscription_periods:write`**, asignados al rol Owner | Que el Dueño consulte su estado y pague | Esta API (`/authorization/check`) | Falta |
| Permisos **`payments:read`** y **`payments:write`** asignados al rol Owner | El token del Dueño se reenvía a Pagos, que decide con ellos | Pagos (a través del token reenviado) | Falta (no existen en el catálogo) |
| **`tenant_id`** del Dueño en la respuesta de `GET /api/v1/authorization/me` (la organización a la que pertenece) | Pagos aísla sus pagos por ese identificador y lo exige | Pagos | Falta (no se publica) |

**Tipo del módulo**: de **Sistema**, igual que `organizations`, `subscriptions` y `clinic_members`. Razón
(evidencia: `mailySoft-clinicas/project-definition/RBAC.md`): un rol de **Clínica** (el Owner) puede recibir
permisos de módulos de tipo Sistema, pero un rol de Sistema no puede recibir los de módulos de tipo Clínica;
y el menú del frontend de clínicas se arma con los módulos de tipo **Clínica** que incluye el plan, y el cobro
de la suscripción no es un módulo de plan.

## Uso y degradación

Igual que el resto de las operaciones protegidas: `401` → 401 con su código; `allowed: false` → 403
`permission_denied` (nombra el permiso); sin respuesta, tiempo agotado o respuesta inesperada → 503
`authorization_unavailable`. Nunca se ejecuta la operación ante una duda.

## Reglas de la integración

- Sin credenciales de máquina ni comunicación con Auth0: todo lo que se pide a otro API se obtiene con el
  token de un Dueño (FR-005).
- Los permisos nuevos no cambian el contrato de las operaciones existentes ni las filas de la
  [matriz](permission-matrix.md).

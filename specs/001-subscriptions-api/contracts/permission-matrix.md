# Contrato: matriz operación → permiso (FR-001, FR-003, FR-023)

Cada operación declara el permiso que exige con la extensión de OpenAPI `x-required-permission` (que
además aparece en su descripción: «Permiso requerido: `…`»). Las **6 operaciones** de la API exigen
**token válido y su permiso**; las rutas de documentación no exigen nada.

El permiso se comprueba con los datos vigentes del API de usuarios, en cada petición, **después** de la
identidad y **antes** de validar la solicitud o buscar el recurso (FR-004; research R4).

## Suscripciones (`/api/v1/subscriptions`)

| Operación (`operationId`) | Método y ruta | Permiso |
|---|---|---|
| `list_subscriptions` | `GET /api/v1/subscriptions` | `subscriptions:read` |
| `get_subscription` | `GET /api/v1/subscriptions/{subscription_id}` | `subscriptions:read` |
| `create_subscription` | `POST /api/v1/subscriptions` | `subscriptions:write` |
| `update_subscription` | `PATCH /api/v1/subscriptions/{subscription_id}` | `subscriptions:update` |
| `change_subscription_status` | `PATCH /api/v1/subscriptions/{subscription_id}/status` | `subscriptions:update` |
| `delete_subscription` | `DELETE /api/v1/subscriptions/{subscription_id}` | `subscriptions:delete` |

## Rutas públicas (sin token)

| Ruta | Motivo |
|---|---|
| `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc` | Documentación publicada (FR-001) |

No hay comprobaciones de salud: la pila de punta a punta y los `healthcheck` usan `/openapi.json`.

## Reglas de la matriz

1. **Crear** usa `write` (como los nombres del catálogo del API de usuarios: `users:write`), no
   `create`.
2. **Cambiar el estatus** cuenta como **actualizar** la suscripción: `subscriptions:update`.
3. **Ampliar la lista** (requisito de la persona responsable): una operación nueva se añade con una
   fila en esta tabla, su declaración `protected("<permiso>")` en el Router y el alta del permiso en el
   catálogo del API de usuarios (que es su dueño). No exige enmendar la constitución.
4. La prueba `tests/contract/test_permission_coverage.py` falla si una ruta no tiene
   `x-required-permission` y no está en la tabla de rutas públicas, y si las rutas del Router no
   coinciden exactamente con esta matriz (ni sobra ni falta ninguna).
5. Los cuatro permisos `subscriptions:*` **deben existir en el catálogo del API de usuarios y estar
   asociados a algún rol Activo** antes de integrar; este servicio no los crea.

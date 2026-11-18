# Contrato: matriz operación → permiso (FR-001, FR-006, FR-053)

Esta feature **añade dos filas** a la matriz «operación → permiso» de la API. Las filas de las features 001,
003 y 005 **no se modifican**. La matriz **vigente** es la unión de todas: **15 operaciones protegidas** y las
8 rutas públicas de siempre (la documentación y las cuatro de salud).

El permiso se declara en la ruta con la extensión de OpenAPI `x-required-permission` (y en su descripción:
«Permiso requerido: `…`») y se comprueba con los datos vigentes del API de usuarios, en cada petición,
**después** de la identidad y **antes** de validar el identificador de la organización o consultar nada
(spec FR-001, FR-004).

## Filas nuevas (feature 010)

| Operación (`operationId`) | Método y ruta | Permiso |
|---|---|---|
| `get_subscription_period` | `GET /api/v1/subscription-periods/{organization_id}` | `subscription_periods:read` |
| `create_subscription_payment` | `POST /api/v1/subscription-periods/{organization_id}/payments` | `subscription_periods:write` |

## Matriz vigente (referencia)

| Operación (`operationId`) | Método y ruta | Permiso | Feature |
|---|---|---|---|
| `list_subscriptions` | `GET /api/v1/subscriptions` | `subscriptions:read` | 001 |
| `get_subscription` | `GET /api/v1/subscriptions/{subscription_id}` | `subscriptions:read` | 001 |
| `create_subscription` | `POST /api/v1/subscriptions` | `subscriptions:write` | 001 |
| `update_subscription` | `PATCH /api/v1/subscriptions/{subscription_id}` | `subscriptions:update` | 001 |
| `change_subscription_status` | `PATCH /api/v1/subscriptions/{subscription_id}/status` | `subscriptions:update` | 001 |
| `delete_subscription` | `DELETE /api/v1/subscriptions/{subscription_id}` | `subscriptions:delete` | 001 |
| `get_dashboard` | `GET /api/v1/dashboard` | `dashboard:read` | 003 |
| `get_health` | `GET /api/v1/health` | `health:read` | 005 |
| `list_monitored_components` | `GET /api/v1/monitored-components` | `health:read` | 005 |
| `get_monitored_component` | `GET /api/v1/monitored-components/{component_id}` | `health:read` | 005 |
| `create_monitored_component` | `POST /api/v1/monitored-components` | `health:write` | 005 |
| `update_monitored_component` | `PATCH /api/v1/monitored-components/{component_id}` | `health:update` | 005 |
| `delete_monitored_component` | `DELETE /api/v1/monitored-components/{component_id}` | `health:delete` | 005 |
| `get_subscription_period` | `GET /api/v1/subscription-periods/{organization_id}` | `subscription_periods:read` | **010** |
| `create_subscription_payment` | `POST /api/v1/subscription-periods/{organization_id}/payments` | `subscription_periods:write` | **010** |

## Rutas públicas (sin token)

Sin cambios: `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc`, `GET /health/live`,
`GET /health/ready`, `GET /info` y `GET /health/status`. Las operaciones de esta feature **no** son públicas.

## Reglas

1. **Un permiso por operación, exacto**: tener `subscription_periods:read` no autoriza iniciar el pago, ni
   `subscriptions:*` ni ningún otro permiso autoriza estas operaciones (historia 4, escenarios 3 y 4).
2. **Nombre**: `recurso:acción` en minúsculas con la acción del catálogo de Usuarios (`read` para consultar,
   `write` para crear el cobro), y el recurso en `snake_case` sin guiones (`^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$`,
   la regla de su catálogo; por eso `subscription_periods` y no `subscription-periods`).
3. **El permiso solo no basta**: además la persona debe ser el Dueño de la organización indicada; eso lo
   decide Clínicas (404 si no lo es; ver [clinics-api-integration.md](clinics-api-integration.md)). Los dos
   filtros juntos son el control de acceso.
4. **Ampliar la lista no enmienda la constitución**: basta la fila de esta tabla, la declaración
   `protected(...)` en el Router y el alta de los permisos en el catálogo del API de usuarios, que es su
   dueño ([pedidos-usuarios.md](pedidos-usuarios.md)).
5. **La prueba de cobertura** `tests/contract/test_permission_coverage.py` sigue siendo global: falla si una
   ruta no tiene `x-required-permission` y no es pública, y si el conjunto de rutas no coincide exactamente
   con la matriz vigente. Su ajuste para esta feature es solo ampliar sus tablas internas (`EXPECTED_PERMISSIONS`
   y `REQUESTS`) con las dos operaciones (ajuste A1 del [plan](../plan.md)); ninguna aserción cambia.
6. **Alta previa en el API de usuarios**: los dos permisos deben existir en su catálogo y estar asignados al
   rol Owner **antes** de usar la API contra servicios reales; esta API no los crea. Hasta entonces, la
   simulación del API de usuarios de las pruebas los concede y los niega a voluntad, y contra el API real
   toda petición recibe 403.

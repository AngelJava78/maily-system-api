# Contrato: matriz operación → permiso (FR-001, FR-004, FR-037)

Esta feature **añade una fila** a la matriz «operación → permiso» de la API. La matriz de la feature 001
([permission-matrix.md](../../001-subscriptions-api/contracts/permission-matrix.md)) **no se modifica**: sus
seis filas, sus reglas y su tabla de rutas públicas siguen valiendo tal cual. La matriz **vigente** de la API
es la unión de ambas: **7 operaciones**.

El permiso se declara en la ruta con la extensión de OpenAPI `x-required-permission` (que además aparece en su
descripción: «Permiso requerido: `…`») y se comprueba con los datos vigentes del API de usuarios, en cada
petición, **después** de la identidad y **antes** de validar `limit` (spec FR-003; [research R4](../research.md)).

## Fila nueva (feature 003)

| Operación (`operationId`) | Método y ruta | Permiso |
|---|---|---|
| `get_dashboard` | `GET /api/v1/dashboard` | `dashboard:read` |

## Matriz vigente (referencia; las seis primeras filas son las de la feature 001, sin cambios)

| Operación (`operationId`) | Método y ruta | Permiso | Feature |
|---|---|---|---|
| `list_subscriptions` | `GET /api/v1/subscriptions` | `subscriptions:read` | 001 |
| `get_subscription` | `GET /api/v1/subscriptions/{subscription_id}` | `subscriptions:read` | 001 |
| `create_subscription` | `POST /api/v1/subscriptions` | `subscriptions:write` | 001 |
| `update_subscription` | `PATCH /api/v1/subscriptions/{subscription_id}` | `subscriptions:update` | 001 |
| `change_subscription_status` | `PATCH /api/v1/subscriptions/{subscription_id}/status` | `subscriptions:update` | 001 |
| `delete_subscription` | `DELETE /api/v1/subscriptions/{subscription_id}` | `subscriptions:delete` | 001 |
| `get_dashboard` | `GET /api/v1/dashboard` | `dashboard:read` | **003** |

## Rutas públicas (sin token)

Sin cambios: `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect` y `GET /redoc`. La operación del
dashboard **no** es pública.

## Reglas

1. **Un permiso por operación, exacto**: tener `subscriptions:*` no autoriza el dashboard, ni al revés. La
   pregunta al API de usuarios es por `dashboard:read` y nada más (spec, historia 2, escenario 4).
2. **Nombre**: sigue la convención `recurso:acción` en minúsculas de la constitución (Principio VIII);
   `read` porque es una consulta, igual que `subscriptions:read`.
3. **Ampliar la lista no enmienda la constitución**: basta la fila de esta tabla, la declaración
   `protected("dashboard:read")` en el Router y el alta del permiso en el catálogo del API de usuarios (su
   dueño). Así se hizo aquí.
4. **La prueba de cobertura** `tests/contract/test_permission_coverage.py` sigue siendo **global**: falla si una
   ruta no tiene `x-required-permission` y no es pública, y si el conjunto de rutas del Router no coincide
   exactamente con la matriz vigente. Su ajuste para esta feature es solo ampliar sus dos tablas internas con
   `get_dashboard` (ajuste A1 del [plan](../plan.md)); ninguna aserción cambia.
5. **Alta previa en el API de usuarios**: `dashboard:read` debe existir en su catálogo y estar asociado al rol
   de administración de plataforma **antes** de integrar; este servicio no lo crea. Mientras tanto, la
   simulación del API de usuarios de las pruebas lo concede y lo niega a voluntad.

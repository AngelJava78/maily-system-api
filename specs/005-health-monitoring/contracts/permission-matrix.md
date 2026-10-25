# Contrato: matriz operación → permiso (FR-001, FR-002, FR-003, FR-042)

Esta feature **añade seis filas** a la matriz «operación → permiso» de la API y **cuatro rutas** a su tabla de
rutas públicas. Las siete filas vigentes (seis de suscripciones de la feature 001 y la del dashboard de la
003) **no cambian**. La matriz vigente de la API queda con **13 operaciones protegidas** y **8 rutas
públicas**. La matriz y la colección de Postman nueva se actualizan en el mismo cambio que añade las
operaciones (flujo de trabajo de la constitución).

El permiso se declara en cada ruta con `x-required-permission` y el esquema `BearerAuth` (con
`protected(...)`), y se comprueba con el API de usuarios en cada petición, sin caché, **antes** de validar la
solicitud, de buscar el componente y de consultar o servir un resultado de salud ([research R4](../research.md#r4-permiso-antes-de-validar-fr-003-fr-030-escenario-3-10)).

## Filas nuevas (feature 005)

| Operación (`operationId`) | Método y ruta | Permiso | Respuestas |
|---|---|---|---|
| `get_health` | `GET /api/v1/health` | `health:read` | 200, 401, 403, 503 |
| `list_monitored_components` | `GET /api/v1/monitored-components` | `health:read` | 200, 401, 403, 500, 503 |
| `get_monitored_component` | `GET /api/v1/monitored-components/{component_id}` | `health:read` | 200, 401, 403, 404, 422, 500, 503 |
| `create_monitored_component` | `POST /api/v1/monitored-components` | `health:write` | 201, 401, 403, 409, 422, 500, 503 |
| `update_monitored_component` | `PATCH /api/v1/monitored-components/{component_id}` | `health:update` | 200, 401, 403, 404, 409, 422, 500, 503 |
| `delete_monitored_component` | `DELETE /api/v1/monitored-components/{component_id}` | `health:delete` | 204, 401, 403, 404, 422, 500, 503 |

## Matriz vigente (13 operaciones protegidas)

| Operación (`operationId`) | Método y ruta | Permiso | Feature |
|---|---|---|---|
| `list_subscriptions` | `GET /api/v1/subscriptions` | `subscriptions:read` | 001 |
| `get_subscription` | `GET /api/v1/subscriptions/{subscription_id}` | `subscriptions:read` | 001 |
| `create_subscription` | `POST /api/v1/subscriptions` | `subscriptions:write` | 001 |
| `update_subscription` | `PATCH /api/v1/subscriptions/{subscription_id}` | `subscriptions:update` | 001 |
| `change_subscription_status` | `PATCH /api/v1/subscriptions/{subscription_id}/status` | `subscriptions:update` | 001 |
| `delete_subscription` | `DELETE /api/v1/subscriptions/{subscription_id}` | `subscriptions:delete` | 001 |
| `get_dashboard` | `GET /api/v1/dashboard` | `dashboard:read` | 003 |
| `get_health` | `GET /api/v1/health` | `health:read` | **005** |
| `list_monitored_components` | `GET /api/v1/monitored-components` | `health:read` | **005** |
| `get_monitored_component` | `GET /api/v1/monitored-components/{component_id}` | `health:read` | **005** |
| `create_monitored_component` | `POST /api/v1/monitored-components` | `health:write` | **005** |
| `update_monitored_component` | `PATCH /api/v1/monitored-components/{component_id}` | `health:update` | **005** |
| `delete_monitored_component` | `DELETE /api/v1/monitored-components/{component_id}` | `health:delete` | **005** |

## Rutas públicas (sin token): 8

| Ruta | Operación | Por qué es pública | Feature |
|---|---|---|---|
| `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc` | (documentación) | Excepción de documentación del Principio VIII | 001 |
| `GET /health/live` | `get_health_live` | Contrato de salud v1: la consultan Kubernetes, Docker y el agregador, sin token | **005** |
| `GET /health/ready` | `get_health_ready` | Ídem | **005** |
| `GET /info` | `get_info` | Ídem (identificación del build, parte del contrato v1) | **005** |
| `GET /health/status` | `get_health_status` | Estado público para quien no puede comprobar su acceso (historia 6); vista mínima sin datos sensibles (FR-047) | **005** |

Las cuatro de salud son la excepción «comprobaciones de salud, si la especificación las define» del
Principio VIII: la spec las define y son **solo** estas (FR-002). No declaran `security` ni
`x-required-permission`, no consultan el API de usuarios y `/health/status` ignora una cabecera
`Authorization` si llega (no la valida ni la reenvía). Cualquier otra ruta nueva exige token y permiso.

## Reglas

1. **Un permiso por operación, exacto**: `health:read` no autoriza registrar, ni `dashboard:read` consultar la
   salud. La pregunta al API de usuarios es por el permiso exacto de la operación.
2. **Nombre**: convención `recurso:acción` del Principio VIII: `read` (consultar), `write` (crear),
   `update` (modificar, habilitar o deshabilitar) y `delete` (baja lógica), como en las suscripciones.
3. **Ampliar la lista no enmienda la constitución**: bastan estas filas, `protected(HEALTH_*)` en los
   Routers (constantes en `src/security.py`) y el alta de los permisos en el API de usuarios, su dueño.
4. **Prueba de cobertura** (`tests/contract/test_permission_coverage.py`): sigue siendo global. Reconoce las
   cuatro rutas públicas de salud (ocho públicas en total), exige que las 13 operaciones protegidas
   coincidan exactamente con esta matriz y las recorre una por una contra la simulación del API de usuarios
   (ajuste A1 del [plan](../plan.md)).
5. **Alta previa en el API de usuarios**: los cuatro `health:*` y el módulo «Salud de servicios» (código
   `health`, tipo Sistema) los crea mailySoft-usuarios 016 y los asigna al rol de sistema `Administrator`.
   Hasta entonces, en un ambiente real las seis operaciones responden 403; las pruebas usan la simulación,
   que concede y niega los cuatro permisos.

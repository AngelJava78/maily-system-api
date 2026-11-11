# Contrato: matriz operación → permiso (FR-006, FR-012, FR-024)

Amplía la matriz de la spec 001 (`specs/001-subscriptions-api/contracts/permission-matrix.md`), que
no cambia. Las operaciones de esta spec viven bajo `/api/v1/clinic-subscriptions`.

## Suscripciones de clínica (`/api/v1/clinic-subscriptions`)

| Operación (`operationId`) | Método y ruta | Permiso | Quién lo tiene (FR-006/FR-012) |
|---|---|---|---|
| `list_clinic_subscriptions` | `GET /api/v1/clinic-subscriptions` | `clinic_subscriptions:read` | Rol de Sistema (quien administra la plataforma) |
| `get_clinic_subscription` | `GET /api/v1/clinic-subscriptions/{clinic_subscription_id}` | `clinic_subscriptions:read` | Rol de Sistema |
| `create_clinic_subscription` | `POST /api/v1/clinic-subscriptions` | `clinic_subscriptions:write` | Rol de Sistema |
| `cancel_clinic_subscription` | `DELETE /api/v1/clinic-subscriptions/{clinic_subscription_id}` | `clinic_subscriptions:delete` | Rol de Sistema |
| `charge_clinic_subscription` | `POST /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges` | `clinic_subscriptions:charge` | **Rol de Clínica** (p. ej. Owner), de la misma organización que la suscripción (FR-012, FR-030) |
| `list_clinic_subscription_charges` | `GET /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges` | `clinic_subscriptions:read` | Rol de Sistema |
| `get_clinic_subscription_charge` | `GET /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges/{charge_id}` | `clinic_subscriptions:read` | Rol de Sistema |

No hay `clinic_subscriptions:update`: modificar el ciclo o el plan de una suscripción de clínica
vigente no forma parte de esta especificación (Assumptions: «cambiar de plan es cancelar y crear una
nueva»); si se necesitara después, se añadiría con una fila nueva, sin tocar esta matriz existente
(regla 3 de la matriz de la spec 001).

## Dos formas de comprobar el acceso (FR-030, FR-031; research R1)

| Grupo de operaciones | Comprobación | Informa `tenant_id` |
|---|---|---|
| `list_clinic_subscriptions`, `get_clinic_subscription`, `create_clinic_subscription`, `cancel_clinic_subscription`, `list_clinic_subscription_charges`, `get_clinic_subscription_charge` | `GET /api/v1/authorization/check?permission=clinic_subscriptions:…` (igual que el resto de esta API) | No; no lo necesitan (reciben `tenant_id` explícito en el cuerpo o en la ruta). |
| `charge_clinic_subscription` | `GET /api/v1/authorization/me` (una sola llamada: resuelve el permiso localmente, con la unión de los permisos de los roles Activos de la respuesta, **y** el `tenant_id` de quien llama) | Sí; MUST coincidir con el `tenant_id` de la suscripción de clínica, o 404 (FR-030). |

## `payments:*` (catálogo de `mailySoft-usuarios`, exigido por `mailySoft-pagos`)

`charge_clinic_subscription` reenvía el token de quien llama a `POST /api/v1/payments` de Pagos
(FR-011); Pagos exige, a su vez, que ese token tenga `payments:write` en Usuarios (su propio
Principio VIII). Este servicio no lo comprueba: si falta, Pagos responde 401/403 y este servicio lo
traduce (`contracts/payments-api-integration.md`). `list_clinic_subscription_charges` y
`get_clinic_subscription_charge` leen datos ya guardados localmente (más la sincronización puntual de
un cobro `pending`, research R8): no exigen `payments:read` porque quien lee aquí es el rol de
Sistema (FR-006), no quien disparó el cobro.

## Rutas públicas (sin token)

Sin cambios respecto a la spec 001 (documentación de `/docs`, `/openapi.json`, etc.).

## Reglas de la matriz

1. Igual que la spec 001: **crear** usa `write`; las siete operaciones nuevas exigen token y su
   permiso; `test_permission_coverage` (ampliado) falla si una ruta de `clinic_subscriptions.py` no
   tiene `x-required-permission` o no coincide exactamente con esta tabla.
2. Los permisos `clinic_subscriptions:*` MUST existir en el catálogo del API de usuarios y estar
   asociados a algún rol Activo antes de integrar; `clinic_subscriptions:charge` MUST poder
   asociarse a un rol de **tipo Clínica** (no solo a uno de Sistema) — prerrequisito documentado
   (FR-025), no dado de alta en esta especificación.
3. `payments:write` (y `payments:read`, si Pagos lo exige para `GET /payments/{id}`) es un
   prerrequisito del catálogo de Usuarios que **Pagos** ya documentó como suyo (spec 001 de
   `mailySoft-pagos`); esta especificación solo lo hereda al reenviar el token, no lo declara de
   nuevo aquí.

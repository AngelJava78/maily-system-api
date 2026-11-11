# Contrato: matriz operación → permiso (FR-009, FR-023)

Amplía la matriz de la spec 001 (`specs/001-subscriptions-api/contracts/permission-matrix.md`), que
no cambia. Las operaciones de esta spec viven bajo `/api/v1/clinic-subscriptions`. Tras el rediseño
(2026-11-11) son **3**, no 7: no hay crear/cancelar/listar/consultar «la suscripción de clínica» (esa
entidad vive en Clínicas, fuera de este servicio).

## Cobros de suscripciones de clínica (`/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges`)

| Operación (`operationId`) | Método y ruta | Permiso | Quién lo tiene |
|---|---|---|---|
| `charge_clinic_subscription` | `POST /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges` | `clinic_subscriptions:charge` | **Rol de Clínica** (p. ej. Owner), de la misma organización que reporta Clínicas para ese `clinic_subscription_id` (FR-009, FR-026) |
| `list_clinic_subscription_charges` | `GET /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges` | `clinic_subscriptions:read` | Rol de Sistema (quien administra la plataforma) |
| `get_clinic_subscription_charge` | `GET /api/v1/clinic-subscriptions/{clinic_subscription_id}/charges/{charge_id}` | `clinic_subscriptions:read` | Rol de Sistema |

## Dos formas de comprobar el acceso (FR-026, FR-027; research R1)

| Operación | Comprobación | Informa `tenant_id` |
|---|---|---|
| `list_clinic_subscription_charges`, `get_clinic_subscription_charge` | `GET /api/v1/authorization/check?permission=clinic_subscriptions:read` (igual que el resto de esta API) | No; filtran por `tenant_id` como parámetro, no lo necesitan del token. |
| `charge_clinic_subscription` | `GET /api/v1/authorization/me` (una sola llamada: resuelve el permiso localmente, con la unión de los permisos de los roles Activos de la respuesta, **y** el `tenant_id` de quien llama) | Sí; MUST coincidir con el `tenant_id` que reporta Clínicas para ese `clinic_subscription_id`, o 404 (FR-026). |

## Dependencias externas que esta operación hereda (no las comprueba este servicio)

- **Clínicas**: `charge_clinic_subscription` consulta `GET /api/v1/clinics/clinic-subscriptions/{id}`
  (`contracts/clinics-api-integration.md`) antes de cualquier otra cosa; si Clínicas no responde,
  503; si dice que no existe/no es de esa organización, 404.
- **`payments:*`** (catálogo de `mailySoft-usuarios`, exigido por `mailySoft-pagos`):
  `charge_clinic_subscription` reenvía el token de quien llama a `POST /api/v1/payments` de Pagos
  (FR-008); Pagos exige `payments:write` en Usuarios. Este servicio no lo comprueba: si falta, Pagos
  responde 401/403 y este servicio lo traduce (`contracts/payments-api-integration.md`).

## Rutas públicas (sin token)

Sin cambios respecto a la spec 001.

## Reglas de la matriz

1. Las tres operaciones exigen token y su permiso; `test_permission_coverage` falla si una ruta de
   `clinic_subscriptions.py` no tiene `x-required-permission` o no coincide con esta tabla.
2. Los permisos `clinic_subscriptions:*` MUST existir en el catálogo del API de usuarios y estar
   asociados a algún rol Activo antes de integrar; `clinic_subscriptions:charge` MUST poder
   asociarse a un rol de **tipo Clínica** (no solo a uno de Sistema) — prerrequisito documentado
   (FR-024), no dado de alta en esta especificación.

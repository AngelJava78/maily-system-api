# Contrato: catálogo de errores (FR-001, FR-002, FR-004; delta sobre `004-correct-subscriptions-api`)

**Revisión tras Clarifications (2026-10-26)**: el tipo pasó de una columna con dos valores fijos a
un catálogo en tabla (`subscription_types`). Eso agrega **un código nuevo** (`subscription_type_not_found`);
la versión anterior de este documento decía "ningún código nuevo", lo cual dejó de ser correcto.

## Código nuevo

| Código | HTTP | Cuándo |
|---|---|---|
| `subscription_type_not_found` | 422 | `subscription_type_id` es un entero positivo, pero no existe ninguna fila con ese `id` en `subscription_types` (research R5: se descubre al intentar crear, por la clave foránea, no con una lectura previa) |

Ver el catálogo completo (sin cambios de los demás códigos) en
[specs/004-correct-subscriptions-api/contracts/error-catalog.md](../../004-correct-subscriptions-api/contracts/error-catalog.md).

## Mensaje del código nuevo

| Código | Mensaje |
|---|---|
| `subscription_type_not_found` | «No se encontró el tipo de suscripción con el identificador {subscription_type_id}.» |

## Mensajes de validación nuevos (`errors[]`)

| Situación | Operación | `field` | Mensaje |
|---|---|---|---|
| Falta, es `null`, no es un entero, o es `<= 0` | Crear | `subscription_type_id` | «El tipo de suscripción es obligatorio y debe ser un número entero positivo.» |
| Se envía en la actualización (con cualquier valor) | Actualizar | `subscription_type_id` | «El tipo de suscripción no puede modificarse una vez creada.» *(mensaje propio, no el genérico de campo no permitido — igual decisión que la versión anterior de este documento)* |

## Qué operaciones pueden devolver cada mensaje o código

| Mensaje / código | Operaciones |
|---|---|
| Tipo obligatorio / no es un entero positivo | `create_subscription` |
| `subscription_type_not_found` (422) | `create_subscription` (solo si `subscription_type_id` es un entero positivo que no existe en el catálogo) |
| Campo no permitido (`subscription_type_id`) | `update_subscription` (solo si la solicitud lo incluye) |

`get_subscription`, `list_subscriptions`, `change_subscription_status` y `delete_subscription` no
cambian: no validan ni devuelven ningún mensaje nuevo relacionado con el tipo.

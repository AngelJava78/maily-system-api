# Contrato: catálogo de errores (FR-002, FR-003, FR-005; delta sobre `006-add-subscription-type`)

**Ningún código nuevo** (research R4): a diferencia de `006` (que agregó
`subscription_type_not_found`), las dos reglas de esta feature se presentan con el código ya
existente `validation_error` (422) y un elemento más en `errors[]`. El catálogo completo de
códigos sigue siendo el mismo de
[specs/006-add-subscription-type/contracts/error-catalog.md](../../006-add-subscription-type/contracts/error-catalog.md)
(18 códigos, sin cambios).

## Mensajes de validación nuevos (`errors[]`)

| Situación | Operación | `field` | Mensaje |
|---|---|---|---|
| Falta, es `null`, no es un entero, o está fuera de 1 a 100 | Crear, Actualizar | `clinics_limit` | «El límite de clínicas debe ser un número entero de 1 a 100.» |
| El tipo de la suscripción es Individual y `clinics_limit` no es `1` | Crear | `clinics_limit` | «Una suscripción Individual debe tener límite de clínicas igual a 1.» *(validación cruzada de Pydantic, `model_validator`, research R2)* |
| Se envía en la actualización de una suscripción Individual (con cualquier valor, igual o distinto al que ya tiene) | Actualizar | `clinics_limit` | «El límite de clínicas no puede modificarse en una suscripción Individual.» *(decidida por el Service, no por el DTO — research R3; misma forma de respuesta que si la hubiera decidido Pydantic)* |

## Qué operaciones pueden devolver cada mensaje

| Mensaje | Operaciones |
|---|---|
| Límite obligatorio / fuera de 1 a 100 | `create_subscription`, `update_subscription` |
| Individual debe ser 1 (crear) | `create_subscription` (solo si `subscription_type_id` corresponde a Individual) |
| Inmutable en Individual (actualizar) | `update_subscription` (solo si la suscripción vigente es Individual y la solicitud incluye `clinics_limit`) |

`get_subscription`, `list_subscriptions`, `change_subscription_status` y `delete_subscription` no
cambian: no validan ni devuelven ningún mensaje nuevo relacionado con el límite de clínicas.

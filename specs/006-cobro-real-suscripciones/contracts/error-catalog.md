# Contrato: catálogo de errores (ampliación de la spec 001)

Mismo formato uniforme (`code`, `message`, `errors` solo en `validation_error`) que
`specs/001-subscriptions-api/contracts/error-catalog.md`, que sigue vigente para
`/api/v1/subscriptions`. Esto cubre solo los códigos nuevos de `/api/v1/clinic-subscriptions`.

## Códigos nuevos

| Código | HTTP | Cuándo | Cabecera extra |
|---|---|---|---|
| `password_change_required` | 403 | Solo en `charge_clinic_subscription`: Usuarios respondió `password_change_required: true` en `/me` (FR-030, research R1) | — |
| `clinic_subscription_not_found` | 404 | No existe, está Cancelada, o (solo en `charge_clinic_subscription`) el `tenant_id` de quien llama no coincide con el de la suscripción, o es `null` (FR-030: nunca revela cuál fue el motivo) | — |
| `clinic_subscription_charge_not_found` | 404 | El cobro no existe en esa suscripción de clínica | — |
| `clinic_subscription_plan_not_active` | 409 | Al crear: el plan indicado no existe o no está Activo (FR-003) | — |
| `clinic_subscription_already_active` | 409 | Al crear: la clínica ya tiene una suscripción Activa o con cobro pendiente de resolver (FR-004) | — |
| `clinic_subscription_charge_pending` | 409 | Al cancelar: el cobro vigente está `pending` (historia 5, escenario 2); al cobrar: la suscripción está Cancelada (research R7, corregido: un cobro `pending` o `rejected` del periodo vigente NO bloquea el disparo — un reintento llega a Pagos de nuevo con la misma `Idempotency-Key`, historia 2 escenario 2). El mensaje exacto distingue el caso (ver «Mensajes») aunque el código es el mismo. | — |
| `clinic_subscription_already_cancelled` | 409 | Al cancelar una suscripción ya Cancelada (historia 5, escenario 3) | — |
| `clinic_subscription_charge_requires_active_plan` | 409 | Al cobrar: el plan asignado ya no está Activo (Edge Cases) | — |
| `payment_not_authorized` | 403 | Pagos respondió 403 a `POST /api/v1/payments` (falta `payments:write`, sin organización, o cambio de contraseña pendiente **en Pagos**) | — |
| `clinic_subscription_charge_conflict` | 409 | Pagos respondió `idempotency_key_conflict` (409): el precio u otro dato cambió entre dos intentos del mismo periodo | — |
| `payments_unavailable` | 503 | `mailySoft-pagos` no respondió, agotó el tiempo de espera o respondió algo inesperado al crear o consultar un pago; no se creó ni cambió ningún cobro | — |

Los códigos ya existentes (`unauthenticated`, `token_expired`, `invalid_token`, `permission_denied`,
`authorization_unavailable`, `validation_error`, `internal_error`) se comportan igual que en el resto
de la API.

## Mensajes

| Código | Mensaje |
|---|---|
| `password_change_required` | «Debe cambiar su contraseña antes de usar esta operación.» |
| `clinic_subscription_not_found` | «No se encontró la suscripción de clínica con el identificador {clinic_subscription_id}.» |
| `clinic_subscription_charge_not_found` | «No se encontró el cobro con el identificador {charge_id} en esa suscripción de clínica.» |
| `clinic_subscription_plan_not_active` | «El plan con el identificador {subscription_id} no existe o no está Activo.» |
| `clinic_subscription_already_active` | «La clínica ya tiene una suscripción vigente. Cancélela antes de asignar una nueva.» |
| `clinic_subscription_charge_pending` | «La suscripción de clínica con el identificador {clinic_subscription_id} tiene un cobro pendiente de resolver.» |
| `clinic_subscription_already_cancelled` | «La suscripción de clínica con el identificador {clinic_subscription_id} ya está cancelada.» |
| `clinic_subscription_charge_requires_active_plan` | «El plan de esta suscripción de clínica ya no está Activo. Asígnele un plan vigente antes de cobrar.» |
| `payment_not_authorized` | «No se pudo autorizar el cobro con el proveedor de pagos.» |
| `clinic_subscription_charge_conflict` | «Ya existe un cobro distinto para este periodo. Revise el historial antes de reintentar.» |
| `payments_unavailable` | «No se pudo comunicar con el servicio de pagos por ahora. Inténtelo de nuevo más tarde.» |

## Mensajes de validación (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| Falta, es `null` o no es un UUID canónico | `tenant_id` | «El identificador de la clínica debe ser un UUID.» |
| Falta o no es un entero positivo | `subscription_id` | «El identificador del plan debe ser un número entero positivo.» |
| Falta o no es `monthly`/`annual` | `billing_cycle` | «El ciclo de cobro debe ser «monthly» o «annual».» |
| `started_at` en el futuro más allá de lo razonable, o con un formato no ISO 8601 | `started_at` | «La fecha de inicio no es válida.» |
| Identificador de la ruta que no es un entero positivo | `clinic_subscription_id` / `charge_id` | «El identificador debe ser un número entero positivo.» |
| Se envía un campo desconocido o no modificable | el campo | «El campo «{field}» no está permitido.» |

## Qué operaciones pueden devolver cada código

| Código | Operaciones |
|---|---|
| `unauthenticated`, `token_expired`, `invalid_token`, `permission_denied`, `authorization_unavailable` | Las 7 operaciones (en `charge_clinic_subscription`, resueltas con `/me` en vez de `/check`, research R1) |
| `password_change_required` | Solo `charge_clinic_subscription` |
| `clinic_subscription_not_found` | `get_clinic_subscription`, `cancel_clinic_subscription`, `charge_clinic_subscription`, `list_clinic_subscription_charges`, `get_clinic_subscription_charge` |
| `clinic_subscription_charge_not_found` | `get_clinic_subscription_charge` |
| `clinic_subscription_plan_not_active`, `clinic_subscription_already_active` | `create_clinic_subscription` |
| `clinic_subscription_charge_pending`, `clinic_subscription_already_cancelled` | `cancel_clinic_subscription` |
| `clinic_subscription_charge_pending`, `clinic_subscription_charge_requires_active_plan` | `charge_clinic_subscription` |
| `payment_not_authorized`, `clinic_subscription_charge_conflict`, `payments_unavailable` | `charge_clinic_subscription` |
| `validation_error` | Todas las que reciben datos de entrada (no `list_clinic_subscriptions` ni `list_clinic_subscription_charges` sin filtros inválidos) |

## Precedencia (igual que la spec 001, con un paso nuevo en `charge_clinic_subscription`)

1. Cuerpo que no es JSON sintácticamente válido → `validation_error` 422.
2. Identidad: `unauthenticated` → `invalid_token` / `token_expired`.
3. Permiso (`/check` o, en `charge_clinic_subscription`, `/me`): `permission_denied`;
   `password_change_required` (solo `/me`); si Usuarios no responde, `authorization_unavailable`.
4. Validación de ruta, consulta y cuerpo: `validation_error` 422.
5. Existencia: `clinic_subscription_not_found` 404 — en `charge_clinic_subscription`, incluye el
   `tenant_id` que no coincide (FR-030), comprobado **después** del permiso y **antes** de cualquier
   regla de negocio sobre el estatus.
6. Reglas de negocio propias: los 409 de la tabla de arriba.
7. Solo en `charge_clinic_subscription`, tras pasar 1 a 6: la llamada a Pagos y su traducción
   (`payment_not_authorized`, `clinic_subscription_charge_conflict`, `payments_unavailable`).

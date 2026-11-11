# Contrato: catálogo de errores (ampliación de la spec 001)

Mismo formato uniforme (`code`, `message`, `errors` solo en `validation_error`) que
`specs/001-subscriptions-api/contracts/error-catalog.md`. Esto cubre solo los códigos nuevos de
`/api/v1/clinic-subscriptions/{id}/charges`. Tras el rediseño (2026-11-11), más cortos que en la
primera versión: no hay crear/cancelar una «suscripción de clínica» (vive en Clínicas).

## Códigos nuevos

| Código | HTTP | Cuándo |
|---|---|---|
| `password_change_required` | 403 | Solo en `charge_clinic_subscription`: Usuarios respondió `password_change_required: true` en `/me` |
| `clinic_subscription_not_found` | 404 | Clínicas respondió que ese `clinic_subscription_id` no existe, está cancelado, o es de otra organización que la de quien llama (FR-003: nunca revela cuál) |
| `clinic_subscription_charge_not_found` | 404 | El cobro no existe |
| `clinic_subscription_plan_not_active` | 409 | El plan que reportó Clínicas para esa suscripción ya no existe o no está Activo en el catálogo (FR-005) |
| `clinic_subscription_charge_already_approved` | 409 | Ya existe un cobro `approved` para el mismo `clinic_subscription_id` y periodo (FR-011) |
| `payment_not_authorized` | 403 | Pagos respondió 403 a `POST /api/v1/payments` (falta `payments:write`, sin organización, o cambio de contraseña **en Pagos**) |
| `clinic_subscription_charge_conflict` | 409 | Pagos respondió `idempotency_key_conflict` (409) |
| `payments_unavailable` | 503 | `mailySoft-pagos` no respondió, agotó el tiempo de espera o respondió algo inesperado |

Si Clínicas agota el tiempo de espera o responde algo inesperado (nunca un 404 limpio), el código es
`clinics_check_unavailable` (503, ya existente en el catálogo desde la spec 001, donde lo usa
`delete_subscription`): es la misma situación («no se pudo comprobar algo de Clínicas»), reutilizada
en vez de inventar un código nuevo.

Los códigos ya existentes (`unauthenticated`, `token_expired`, `invalid_token`, `permission_denied`,
`authorization_unavailable`, `validation_error`, `internal_error`) se comportan igual que en el resto
de la API.

## Mensajes

| Código | Mensaje |
|---|---|
| `password_change_required` | «Debe cambiar su contraseña antes de usar esta operación.» |
| `clinic_subscription_not_found` | «No se encontró la suscripción de clínica con el identificador {clinic_subscription_id}.» |
| `clinic_subscription_charge_not_found` | «No se encontró el cobro con el identificador {charge_id}.» |
| `clinic_subscription_plan_not_active` | «El plan de esta suscripción de clínica no existe o no está Activo.» |
| `clinic_subscription_charge_already_approved` | «Ya existe un cobro aprobado para este periodo.» |
| `payment_not_authorized` | «No se pudo autorizar el cobro con el proveedor de pagos.» |
| `clinic_subscription_charge_conflict` | «Ya existe un cobro distinto para este periodo. Revise el historial antes de reintentar.» |
| `payments_unavailable` | «No se pudo comunicar con el servicio de pagos por ahora. Inténtelo de nuevo más tarde.» |

## Mensajes de validación (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| Falta, es `null` o no es una fecha ISO 8601 | `period` | «El periodo debe ser una fecha válida.» |
| Identificador de la ruta que no es un UUID canónico | `clinic_subscription_id` | «El identificador de la suscripción de clínica debe ser un UUID.» |
| Identificador de la ruta que no es un entero positivo | `charge_id` | «El identificador del cobro debe ser un número entero positivo.» |
| Se envía un campo desconocido | el campo | «El campo «{field}» no está permitido.» |

## Qué operaciones pueden devolver cada código

| Código | Operaciones |
|---|---|
| `unauthenticated`, `token_expired`, `invalid_token`, `permission_denied`, `authorization_unavailable` | Las 3 operaciones (en `charge_clinic_subscription`, resueltas con `/me`) |
| `password_change_required` | Solo `charge_clinic_subscription` |
| `clinic_subscription_not_found`, `clinics_check_unavailable` (503, ya existente) | `charge_clinic_subscription` |
| `clinic_subscription_charge_not_found` | `get_clinic_subscription_charge` |
| `clinic_subscription_plan_not_active`, `clinic_subscription_charge_already_approved`, `payment_not_authorized`, `clinic_subscription_charge_conflict`, `payments_unavailable` | `charge_clinic_subscription` |
| `validation_error` | `charge_clinic_subscription` (cuerpo), las tres (identificadores de ruta) |

## Precedencia

1. Cuerpo que no es JSON sintácticamente válido → `validation_error` 422.
2. Identidad: `unauthenticated` → `invalid_token` / `token_expired`.
3. Permiso (`/check` o, en `charge_clinic_subscription`, `/me`): `permission_denied`;
   `password_change_required` (solo `/me`); si Usuarios no responde, `authorization_unavailable`.
4. Validación de ruta y cuerpo: `validation_error` 422.
5. Solo en `charge_clinic_subscription`: consulta a Clínicas — `clinic_subscription_not_found` 404
   si dice que no existe; `clinics_check_unavailable` 503 si Clínicas no responde (FR-004).
6. Reglas de negocio propias: `clinic_subscription_plan_not_active`,
   `clinic_subscription_charge_already_approved`.
7. La llamada a Pagos y su traducción: `payment_not_authorized`,
   `clinic_subscription_charge_conflict`, `payments_unavailable`.
8. Existencia del cobro (solo `get_clinic_subscription_charge`): `clinic_subscription_charge_not_found` 404.

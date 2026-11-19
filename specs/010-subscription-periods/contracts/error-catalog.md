# Contrato: errores de los periodos de suscripción (FR-002, FR-004, FR-035 a FR-038, FR-045)

Las dos operaciones usan el mismo cuerpo de error de siempre (`code`, `message` y, en las validaciones,
`errors`) y **reutilizan** los códigos de acceso, validación e interno del catálogo vigente. Añaden
**cinco códigos nuevos** (17 → 22) para las situaciones nuevas; ninguno existente cambia.

## Códigos nuevos

| Código | HTTP | Cuándo | Mensaje (español) |
|---|---|---|---|
| `organization_not_found` | 404 | Clínicas respondió `404 not_found`: la organización no existe **o no es de la persona** (no se distingue) | «No se encontró la organización con el identificador {organization_id}.» |
| `organization_check_unavailable` | 503 | No se pudo comprobar la organización: Clínicas no respondió, agotó el tiempo, respondió 401, 403, 5xx, una redirección, un cuerpo ilegible o sin lo que el contrato exige (incluido `billing_period`) | «No se pudo comprobar la organización por ahora. No se hizo ningún cambio; inténtelo de nuevo más tarde.» |
| `payments_unavailable` | 503 | Solo al iniciar el pago: Pagos no pudo crear el pago (sin respuesta, tiempo agotado, error, cuerpo inesperado) o devolvió uno sin checkout | «No se pudo crear el pago por ahora. No se registró ningún cobro nuevo; inténtelo de nuevo más tarde.» |
| `nothing_to_charge` | 409 | Solo al iniciar el pago: el importe vigente es 0.00 | «La suscripción de la organización no tiene nada que cobrar: su importe vigente es 0.00.» |
| `organization_subscription_not_found` | 409 | El plan que informa Clínicas no existe en el catálogo | «El plan de la organización no existe en el catálogo de suscripciones.» |

Los mensajes no incluyen direcciones, cuerpos ni credenciales de otro API (FR-038); el 404 repite solo el
identificador que envió quien llama.

## Códigos existentes que usan las operaciones

| Código | HTTP | Cuándo | Cabecera extra |
|---|---|---|---|
| `unauthenticated` | 401 | Sin token o con un esquema distinto de Bearer | `WWW-Authenticate: Bearer` |
| `token_expired` | 401 | El API de usuarios respondió que el token venció | `WWW-Authenticate: Bearer error="invalid_token"` |
| `invalid_token` | 401 | El API de usuarios rechazó el token por otro motivo, o excede 8 192 bytes | `WWW-Authenticate: Bearer error="invalid_token"` |
| `permission_denied` | 403 | La persona no tiene el permiso de la operación (`subscription_periods:read` o `subscription_periods:write`) | — |
| `authorization_unavailable` | 503 | No se pudo verificar el permiso: Usuarios no respondió a tiempo, cayó o contestó algo inesperado | — |
| `validation_error` | 422 | `organization_id` no es un UUID (solo se evalúa con el acceso concedido) | — |
| `internal_error` | 500 | Fallo inesperado, con el mensaje genérico de siempre | — |

`permission_denied` nombra el permiso: «No tiene permiso para realizar esta operación. Permiso requerido:
subscription_periods:read.» (o `…:write`).

## Qué puede devolver cada operación

| Código | `get_subscription_period` | `create_subscription_payment` |
|---|---|---|
| 200 | El estado | El checkout de un cobro pendiente que ya existía |
| 201 | — | Un cobro nuevo y su checkout |
| 401 | `unauthenticated`, `token_expired`, `invalid_token` | ídem |
| 403 | `permission_denied` | ídem |
| 404 | `organization_not_found` | ídem |
| 409 | `organization_subscription_not_found` | `organization_subscription_not_found`, `nothing_to_charge` |
| 422 | `validation_error` | ídem |
| 503 | `authorization_unavailable`, `organization_check_unavailable` | además `payments_unavailable` |
| 500 | `internal_error` | ídem |

**Pagos nunca hace fallar la consulta**: una falla de Pagos al verificar un cobro llega como
`payment_in_progress: null` con 200 (FR-036), no como error.

## Mensaje de validación nuevo (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| `organization_id` no es un UUID | `organization_id` | «El identificador de la organización debe ser un UUID.» |

Cuerpo de ejemplo:

```json
{
  "code": "validation_error",
  "message": "Hay datos no válidos en la solicitud.",
  "errors": [
    { "field": "organization_id", "message": "El identificador de la organización debe ser un UUID." }
  ]
}
```

En el código: constantes en `src/messages.py` y el bloque `VALIDATION_MESSAGES["subscription-periods"]` (el
manejador de errores elige el bloque por el primer segmento de la ruta después de `/api/v1/`). `ErrorCode`
pasa de 17 a **22** códigos.

## Precedencia (cuál se devuelve si hay varias causas; FR-004)

1. Identidad: `unauthenticated` → `invalid_token` / `token_expired` (401).
2. Permiso: `permission_denied` (403); si el API de usuarios no responde, `authorization_unavailable` (503).
3. Validación de `organization_id`: `validation_error` (422).
4. Organización (Clínicas): `organization_not_found` (404) o `organization_check_unavailable` (503).
5. Reglas de negocio: `organization_subscription_not_found` (409) y, al iniciar el pago, `nothing_to_charge` (409).
6. Pagos, solo al iniciar el pago: `payments_unavailable` (503).

El permiso va antes que la validación **sin excepción**: ambas operaciones leen `organization_id` de la ruta
en una dependencia posterior a la de seguridad (research R12). Con el acceso denegado, un identificador
inválido responde 401, 403 o 503, nunca 422.

## Cabecera de caché

Solo las respuestas 200 y 201 llevan `Cache-Control: no-store`; las de error no contienen datos de cobro y
no la declaran.

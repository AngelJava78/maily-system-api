# Contrato: errores del dashboard (FR-002, FR-003, FR-013, FR-030)

El dashboard **no añade códigos de error** ni modifica el [catálogo de la feature 001](../../001-subscriptions-api/contracts/error-catalog.md):
usa el mismo cuerpo (`code`, `message` y, en las validaciones, `errors`) y los mismos 12 códigos. Este
documento fija cuáles de ellos puede devolver `get_dashboard`, el único mensaje de validación nuevo y el orden
en que se evalúan.

## Códigos que puede devolver `get_dashboard`

| Código | HTTP | Cuándo | Cabecera extra |
|---|---|---|---|
| `unauthenticated` | 401 | No se envió token, o la cabecera `Authorization` no usa el esquema `Bearer` | `WWW-Authenticate: Bearer` |
| `token_expired` | 401 | El API de usuarios respondió que el token venció | `WWW-Authenticate: Bearer error="invalid_token"` |
| `invalid_token` | 401 | El API de usuarios rechazó el token por otro motivo (o con un cuerpo ilegible), o excede 8 192 bytes | `WWW-Authenticate: Bearer error="invalid_token"` |
| `permission_denied` | 403 | La persona está autenticada pero el API de usuarios dice que no tiene `dashboard:read` | — |
| `authorization_unavailable` | 503 | No se pudo verificar el permiso: el API de usuarios no respondió a tiempo, cayó, respondió 5xx/429 o algo inesperado | — |
| `validation_error` | 422 | `limit` no es válido (solo se evalúa con el acceso concedido) | — |
| `internal_error` | 500 | Fallo inesperado, con el mensaje genérico de siempre (incluye un error de programación en una fuente de datos) | — |

No aplican a esta operación: `subscription_not_found`, `subscription_name_already_exists`,
`subscription_status_unchanged`, `subscription_has_clinics` ni `clinics_check_unavailable`. **Tampoco existe
un error "una fuente de datos falló"**: esa falla nunca se convierte en error HTTP; el valor afectado llega
como `null` con `200` ([data-sources.md](data-sources.md)). La única falla que impide responder es la del
control de acceso (503).

Mensajes de los cinco primeros códigos y de `internal_error`: los del catálogo de la feature 001, sin cambios
(`permission_denied` nombra el permiso: «No tiene permiso para realizar esta operación. Permiso requerido:
dashboard:read.»).

## Mensaje de validación nuevo (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| `limit` menor que 1 (`0`), que no es solo dígitos (`abc`, vacío, `5.5`, `5.0`, `1e1`, `+3`, `-1`, con espacios) o repetido | `limit` | «El parámetro «limit» debe ser un número entero mayor o igual que 1.» |

- Es el **único** mensaje: todos los casos de `limit` inválido producen el mismo texto, que **nunca repite el
  valor recibido**.
- Cuerpo de ejemplo:

```json
{
  "code": "validation_error",
  "message": "Hay datos no válidos en la solicitud.",
  "errors": [
    { "field": "limit", "message": "El parámetro «limit» debe ser un número entero mayor o igual que 1." }
  ]
}
```

- Un `limit` mayor que 10, por grande que sea, **no es un error**: devuelve 10 (FR-011).
- En el código: constante `DASHBOARD_LIMIT_INVALID_MESSAGE` y bloque `VALIDATION_MESSAGES["dashboard"]` en
  `src/messages.py` (el manejador de errores elige el bloque por el primer segmento de la ruta después de
  `/api/v1/`). `ErrorCode` no cambia: siguen siendo 12 códigos.

## Precedencia (cuál se devuelve si hay varias causas)

1. Identidad: `unauthenticated` → `invalid_token` / `token_expired` (401).
2. Permiso: `permission_denied` (403); si el API de usuarios no responde, `authorization_unavailable` (503).
3. Validación de `limit`: `validation_error` (422).
4. Datos: nada que decidir; una fuente que falla degrada el valor a `null` y no cambia el estado.

A diferencia de la feature 001, **no hay excepción** a que el permiso vaya antes que la validación: la
operación es un `GET` sin cuerpo y `limit` se lee en una dependencia posterior a la de seguridad
([research R4](../research.md)). Con permiso denegado, todo `limit` inválido (vacío, `0`, `abc`, `5.0`,
repetido, de miles de dígitos) responde 403, 401 o 503, nunca 422.

## Cabecera de caché

Solo la respuesta `200` lleva `Cache-Control: no-store` (spec, Aclaración 3). Las respuestas de error no
contienen datos del dashboard y no la declaran.

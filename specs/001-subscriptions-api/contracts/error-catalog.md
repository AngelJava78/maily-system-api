# Contrato: catálogo de errores (FR-005, FR-019, FR-021)

Todos los errores de la API tienen el mismo cuerpo:

```json
{
  "code": "permission_denied",
  "message": "No tiene permiso para realizar esta operación. Permiso requerido: subscriptions:write."
}
```

- `code`: código estable en inglés; quien consume la API debe basarse en él, no en el texto.
- `message`: texto en español para personas, sin detalles técnicos y **sin** tokens, secretos, cuerpos de
  error ni direcciones de otros servicios. Cuando menciona una suscripción lo hace por su identificador.
- `errors`: solo en `validation_error`; un elemento `{field, message}` por dato con problema. Los
  mensajes de validación nunca repiten el valor recibido.

## Códigos

| Código | HTTP | Cuándo | Cabecera extra |
|---|---|---|---|
| `unauthenticated` | 401 | No se envió token, o la cabecera `Authorization` no usa el esquema `Bearer` | `WWW-Authenticate: Bearer` |
| `token_expired` | 401 | El API de usuarios respondió que el token venció | `WWW-Authenticate: Bearer error="invalid_token"` |
| `invalid_token` | 401 | El API de usuarios rechazó el token por otro motivo (o con un cuerpo ilegible), o el token excede 8 192 bytes. **No se distingue cuál** | `WWW-Authenticate: Bearer error="invalid_token"` |
| `permission_denied` | 403 | La persona está autenticada pero el API de usuarios responde que no tiene el permiso (incluye no tener usuario, no estar Activa o no tener roles) | — |
| `authorization_unavailable` | 503 | No se pudo verificar el permiso: el API de usuarios no respondió a tiempo, cayó, respondió 5xx/429 o algo inesperado | — |
| `subscription_not_found` | 404 | La suscripción no existe o está Eliminada (incluye un identificador mayor que 2 147 483 647) | — |
| `subscription_name_already_exists` | 409 | Otra suscripción no eliminada ya usa el nombre (sin distinguir mayúsculas) | — |
| `subscription_status_unchanged` | 409 | Se pidió el estatus que la suscripción ya tiene | — |
| `subscription_has_clinics` | 409 | Se intentó eliminar una suscripción que tiene al menos una clínica asignada | — |
| `clinics_check_unavailable` | 503 | Se intentó eliminar y no pudo comprobarse si tiene clínicas (el API de clínicas no respondió, rechazó la consulta o respondió algo inesperado); no se eliminó nada | — |
| `validation_error` | 422 | Algún dato de la solicitud no es válido o no está permitido (incluye JSON mal formado) | — |
| `internal_error` | 500 | Fallo inesperado, con el mensaje genérico de siempre | — |

## Mensajes

| Código | Mensaje |
|---|---|
| `unauthenticated` | «Debe iniciar sesión para usar esta operación.» |
| `token_expired` | «Su sesión venció. Inicie sesión de nuevo.» |
| `invalid_token` | «El token de acceso no es válido.» |
| `permission_denied` | «No tiene permiso para realizar esta operación. Permiso requerido: {permission}.» |
| `authorization_unavailable` | «No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde.» |
| `subscription_not_found` | «No se encontró la suscripción con el identificador {subscription_id}.» |
| `subscription_name_already_exists` | «Ya existe una suscripción con el nombre «{name}».» |
| `subscription_status_unchanged` | «La suscripción con el identificador {subscription_id} ya tiene el estatus {status}.» |
| `subscription_has_clinics` | «No se puede eliminar la suscripción con el identificador {subscription_id} porque tiene clínicas asignadas.» |
| `clinics_check_unavailable` | «No se pudo comprobar si la suscripción con el identificador {subscription_id} tiene clínicas asignadas. No se eliminó; inténtelo de nuevo más tarde.» |
| `validation_error` | «Hay datos no válidos en la solicitud.» |
| `internal_error` | «Ocurrió un error inesperado. Inténtelo de nuevo más tarde.» |

## Mensajes de validación (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| Falta, es `null` o está vacío tras recortar | `name` | «El nombre de la suscripción es obligatorio.» |
| Más de 100 caracteres | `name` | «El nombre de la suscripción no puede tener más de 100 caracteres.» |
| No es un texto | `name` | «El nombre de la suscripción debe ser un texto.» |
| Más de 500 caracteres | `description` | «La descripción no puede tener más de 500 caracteres.» |
| Falta o es `null` | `monthly_price` | «El precio mensual es obligatorio.» |
| Negativo, con más de dos decimales, mayor que 99 999 999,99 o no numérico | `monthly_price` | «El precio mensual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales.» |
| No es una lista, o un elemento no es texto | `features` | «Lo que incluye la suscripción debe ser una lista de textos.» |
| Más de 20 elementos | `features` | «Lo que incluye la suscripción no puede tener más de 20 elementos.» |
| Un elemento vacío o de más de 150 caracteres | `features` | «Cada elemento de lo que incluye la suscripción debe tener de 1 a 150 caracteres.» |
| Falta o no es un entero | `status_id` | «El estatus es obligatorio y debe ser un número entero.» |
| Es 4 o un número que el catálogo no admite en esta operación | `status_id` | «El estatus debe ser uno de los que admite esta operación (1, 2 o 3).» |
| Se envía un campo desconocido o no modificable (`id`, `status`, `clinics_count`, fechas…) | el campo | «El campo «{field}» no está permitido.» |
| Cuerpo vacío (`{}`) al actualizar | `body` | «Hay que enviar al menos un dato para modificar.» |
| Cuerpo que no es un objeto JSON válido | `body` | «El cuerpo de la solicitud no es válido.» |
| Identificador de la ruta que no es un entero positivo | `subscription_id` | «El identificador de la suscripción debe ser un número entero positivo.» |

## Qué operaciones pueden devolver cada código

| Código | Operaciones |
|---|---|
| `unauthenticated`, `token_expired`, `invalid_token`, `permission_denied`, `authorization_unavailable` | Las 6 operaciones |
| `subscription_not_found` | `get_subscription`, `update_subscription`, `change_subscription_status`, `delete_subscription` |
| `subscription_name_already_exists` | `create_subscription`, `update_subscription` |
| `subscription_status_unchanged` | `change_subscription_status` |
| `subscription_has_clinics`, `clinics_check_unavailable` | `delete_subscription` |
| `validation_error` | `create_subscription`, `get_subscription`, `update_subscription`, `change_subscription_status`, `delete_subscription` (el listado no recibe datos) |

El API de clínicas **nunca** produce un error en las lecturas (`list_subscriptions`, `get_subscription`,
`create_subscription`, `update_subscription`, `change_subscription_status`): si falla, `clinics_count`
es `null` (FR-009). Solo `delete_subscription` lo convierte en `clinics_check_unavailable`.

## Precedencia (cuál se devuelve si hay varias causas)

1. Cuerpo que no es JSON sintácticamente válido → `validation_error` 422 (**limitación conocida**: se
   evalúa antes que la identidad porque Starlette lo decodifica antes de las dependencias; no revela
   datos; ver research R4).
2. Identidad: `unauthenticated` → `invalid_token` / `token_expired`.
3. Permiso: `permission_denied`; si el API de usuarios no responde, `authorization_unavailable`.
4. Validación de ruta, consulta y cuerpo: `validation_error` 422.
5. Existencia y reglas de negocio: `subscription_not_found` 404, conflictos 409.
6. Comprobación de clínicas (solo eliminar): `subscription_has_clinics` o `clinics_check_unavailable`.

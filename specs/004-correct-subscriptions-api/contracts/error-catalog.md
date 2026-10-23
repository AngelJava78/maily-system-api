# Contrato: catálogo de errores (FR-030, FR-032; delta sobre `001-subscriptions-api`)

El formato del cuerpo, `code` y `message` **no cambian** respecto a
[specs/001-subscriptions-api/contracts/error-catalog.md](../../001-subscriptions-api/contracts/error-catalog.md).
Este documento es el catálogo **completo** tras esta feature: reproduce los 12 códigos ya existentes
(sin cambios) y añade los 3 nuevos de módulos.

## Códigos

| Código | HTTP | Cuándo | Cabecera extra |
|---|---|---|---|
| `unauthenticated` | 401 | Sin cambios (001) | `WWW-Authenticate: Bearer` |
| `token_expired` | 401 | Sin cambios (001) | `WWW-Authenticate: Bearer error="invalid_token"` |
| `invalid_token` | 401 | Sin cambios (001) | `WWW-Authenticate: Bearer error="invalid_token"` |
| `permission_denied` | 403 | Sin cambios (001) | — |
| `authorization_unavailable` | 503 | Sin cambios (001): no se pudo verificar el **permiso** de la operación | — |
| `subscription_not_found` | 404 | Sin cambios (001) | — |
| `subscription_name_already_exists` | 409 | Sin cambios (001) | — |
| `subscription_status_unchanged` | 409 | Sin cambios (001) | — |
| `subscription_has_clinics` | 409 | Sin cambios (001) | — |
| `clinics_check_unavailable` | 503 | Sin cambios (001) | — |
| **`subscription_module_not_found`** | **422** | **Se pidió un módulo (en `module_keys`, distinto de `patients`) que la API de usuarios no reconoce como módulo de tipo Clínica vigente** | — |
| **`subscription_module_prerequisite_missing`** | **409** | **Se pidió un módulo sin su prerrequisito (Recordatorios sin Agenda y citas, Plantillas de expediente o Recetas sin Expediente clínico, Facturación sin Finanzas)** | — |
| **`module_check_unavailable`** | **503** | **Se pidieron módulos además de `patients` y la API de usuarios no respondió como se esperaba al validarlos; no se creó ni se actualizó nada** | — |
| `validation_error` | 422 | Sin cambios (001); ahora también cubre los 7 campos nuevos | — |
| `internal_error` | 500 | Sin cambios (001) | — |

## Mensajes nuevos

| Código | Mensaje |
|---|---|
| `subscription_module_not_found` | «La API de usuarios no reconoce el módulo «{module_key}» como un módulo de clínica vigente.» |
| `subscription_module_prerequisite_missing` | «El módulo «{module_key}» exige el módulo «{prerequisite_key}», que no está incluido.» |
| `module_check_unavailable` | «No se pudo comprobar los módulos de la suscripción por ahora. No se guardó ningún cambio; inténtelo de nuevo más tarde.» |

Los 12 mensajes ya existentes no cambian (ver el catálogo de `001-subscriptions-api`).

## Mensajes de validación nuevos (`errors[]`)

| Situación | `field` | Mensaje |
|---|---|---|
| Falta o es `null` | `annual_price` | «El precio anual es obligatorio.» |
| Negativo, con más de dos decimales, mayor que 99 999 999,99 o no numérico | `annual_price` | «El precio anual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales.» |
| No es un entero, o fuera de 0–3650 | `trial_days` | «Los días de prueba deben ser un número entero de 0 a 3650.» |
| No es verdadero/falso | `self_service` | «El autoconsumo debe ser verdadero o falso.» |
| No es una lista, o un elemento no sigue el patrón de clave | `module_keys` | «Cada módulo debe identificarse con una clave válida.» |
| Más de 50 elementos | `module_keys` | «No se pueden pedir más de 50 módulos.» |
| No es una lista, o un elemento no es texto | `other_features` | «Lo que incluye la suscripción debe ser una lista de textos.» *(mismo mensaje que `features` en 001, con el nuevo nombre de campo)* |
| Más de 20 elementos | `other_features` | «Lo que incluye la suscripción no puede tener más de 20 elementos.» |
| Un elemento vacío o de más de 150 caracteres | `other_features` | «Cada elemento de lo que incluye la suscripción debe tener de 1 a 150 caracteres.» |
| Falta, es `null` o fuera de 0–1 000 000 | `consulting_rooms_limit` | «El límite de consultorios debe ser un número entero de 0 a 1 000 000.» |
| Falta, es `null` o fuera de 0–1 000 000 | `doctors_limit` | «El límite de doctores debe ser un número entero de 0 a 1 000 000.» |
| Falta, es `null` o fuera de 0–1 000 000 | `assistants_limit` | «El límite de asistentes debe ser un número entero de 0 a 1 000 000.» |
| Falta, es `null` o fuera de 0–1 000 000 | `new_patients_per_year_limit` | «El límite de pacientes nuevos al año debe ser un número entero de 0 a 1 000 000.» |

El resto de los mensajes de validación de `001-subscriptions-api` (`name`, `description`,
`monthly_price`, `status_id`, campo no permitido, cuerpo vacío/ilegible,
`subscription_id`) no cambian.

## Qué operaciones pueden devolver cada código

| Código | Operaciones |
|---|---|
| Los 5 de control de acceso | Las 6 operaciones (sin cambios) |
| `subscription_not_found` | `get_subscription`, `update_subscription`, `change_subscription_status`, `delete_subscription` (sin cambios) |
| `subscription_name_already_exists` | `create_subscription`, `update_subscription` (sin cambios) |
| `subscription_status_unchanged` | `change_subscription_status` (sin cambios) |
| `subscription_has_clinics`, `clinics_check_unavailable` | `delete_subscription` (sin cambios) |
| `subscription_module_not_found`, `subscription_module_prerequisite_missing`, `module_check_unavailable` | **`create_subscription`, `update_subscription`** (solo si la solicitud trae `module_keys` con algo además de `patients`) |
| `validation_error` | `create_subscription`, `get_subscription`, `update_subscription`, `change_subscription_status`, `delete_subscription` (sin cambios) |

## Precedencia (cuál se devuelve si hay varias causas)

1. Cuerpo que no es JSON sintácticamente válido → `validation_error` 422 (sin cambios, única
   excepción aceptada).
2. Identidad: `unauthenticated` → `invalid_token` / `token_expired`.
3. Permiso de la operación: `permission_denied`; si el API de usuarios no responde,
   `authorization_unavailable`.
4. Validación de Pydantic de ruta, consulta y cuerpo (incluidos los 7 campos nuevos) → `validation_error` 422.
5. **(nuevo) Si la solicitud trae `module_keys` con algo además de `patients`**: existencia de la
   suscripción (solo en `update_subscription`, antes de llamar a la API de usuarios; research R6) →
   `subscription_module_not_found` 422 → `subscription_module_prerequisite_missing` 409 →
   `module_check_unavailable` 503 si la API de usuarios no respondió al intentar resolver el paso
   anterior.
6. Existencia de la suscripción (el resto de los casos) y demás reglas de negocio:
   `subscription_not_found` 404, `subscription_name_already_exists` /
   `subscription_status_unchanged` 409.
7. Comprobación de clínicas (solo eliminar): `subscription_has_clinics` o
   `clinics_check_unavailable` (sin cambios).

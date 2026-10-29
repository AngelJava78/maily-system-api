# Contrato: catálogo de errores (FR-003, FR-005; delta sobre `007-add-clinics-limit`)

**Se retira un código** (el único cambio de catálogo de esta feature): `subscription_module_prerequisite_missing`
(409) desaparece por completo porque la regla de negocio que lo producía (dependencias entre
módulos) ya no existe (FR-003). El catálogo completo de los demás códigos sigue siendo el mismo de
[specs/004-correct-subscriptions-api/contracts/error-catalog.md](../../004-correct-subscriptions-api/contracts/error-catalog.md)
(como lo dejó `006-add-subscription-type`, que le añadió `subscription_type_not_found`): de 18
códigos pasan a quedar **17**.

Esto no es un cambio incompatible que requiera versionar el contrato (ver `plan.md`, Constitution
Check): un código que el servidor ya no puede emitir no es un dato que un cliente necesite seguir
reconociendo.

## Código que se retira

| Código | HTTP | Por qué desaparece |
|---|---|---|
| ~~`subscription_module_prerequisite_missing`~~ | ~~409~~ | La dependencia entre módulos (Recordatorios exigía Agenda y citas; Plantillas de expediente y Recetas exigían Expediente clínico; Facturación exigía Finanzas) deja de ser una regla de esta API (FR-003). Ninguna combinación de módulos del catálogo activo se rechaza ya por este motivo. |

## Mensaje que se retira

| Código | Mensaje (ya no se usa) |
|---|---|
| `subscription_module_prerequisite_missing` | «El módulo «{module_key}» exige el módulo «{prerequisite_key}», que no está incluido.» |

Los demás mensajes (incluidos los otros dos de módulos, `subscription_module_not_found` y
`module_check_unavailable`) no cambian.

## Qué operaciones pueden devolver cada código (delta)

La fila de `004-correct-subscriptions-api` que listaba los tres códigos de módulos juntos
(`subscription_module_not_found`, `subscription_module_prerequisite_missing`,
`module_check_unavailable`) para `create_subscription`/`update_subscription` queda con solo los
dos que sobreviven. El resto de la tabla de operaciones por código no cambia.

## Precedencia (delta sobre el paso 5 de `004`)

El paso 5 de la tabla de precedencia de `004` (exclusivo de `create_subscription`/
`update_subscription` cuando la solicitud trae `module_keys` con algo además de `patients`) pierde
su sub-paso de dependencia local. Queda:

1. Existencia de la suscripción (solo en `update_subscription`, antes de llamar a la API de
   usuarios).
2. `subscription_module_not_found` (422) si algún módulo pedido no está en el catálogo activo de
   tipo Clínica.
3. `module_check_unavailable` (503) si la API de usuarios no respondió al intentar resolver el
   paso anterior.

El resto de la tabla de precedencia de `004` no cambia.

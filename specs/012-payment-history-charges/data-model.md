# Data Model: Historial paginado de cobros de la suscripción (012-payment-history-charges)

Esta feature **no cambia la base de datos**: ninguna tabla, columna, índice ni migración nueva (R4); el
modelo de persistencia (`SubscriptionCharge`, migración 0008) es exactamente el de la spec 010. Lo nuevo es
una lectura paginada y los DTOs que la publican.

## `SubscriptionChargeRead` (un cobro, tal como esta operación lo publica)

| Campo | Tipo | Presente cuando |
|---|---|---|
| `id` | UUID | siempre |
| `status` | `pending` \| `applied` \| `closed` | siempre |
| `closed_reason` | `rejected` \| `cancelled` \| `inconsistent` \| `refunded` \| `null` | **solo si** `status` es `closed`; `null` en cualquier otro caso (FR-003) |
| `amount` | texto, dos decimales | siempre |
| `currency` | `"MXN"` | siempre |
| `billing_period` | `monthly` \| `annual` | siempre |
| `period_starts_at` | fecha-hora ISO 8601 UTC \| `null` | **solo si** `status` es `applied`; `null` en cualquier otro caso (FR-004) |
| `period_ends_at` | fecha-hora ISO 8601 UTC \| `null` | igual que `period_starts_at` |
| `created_at` | fecha-hora ISO 8601 UTC | siempre |

**Nunca presentes** (FR-005): `payment_id`, `attempt`, `resolved_at`, `organization_id` — internos de la
reconciliación (spec 010) o redundantes (la organización ya está en la ruta).

Las restricciones `CheckConstraint` de la tabla `subscription_charges` (migración 0008,
`resolution_check`) ya garantizan a nivel de base de datos que ningún registro pueda violar las dos
reglas de presencia de arriba: el mapeo del Router (`_to_charge_read`) solo traslada lo que el Repository
devuelve, sin repetir esa validación.

## `SubscriptionChargesPageRead` (la página)

| Campo | Tipo | Significado |
|---|---|---|
| `items` | lista de `SubscriptionChargeRead` | los cobros de esta página, del más reciente al más antiguo |
| `total` | entero ≥ 0 | cuántos cobros tiene la organización en total |
| `page` | entero ≥ 1 | la página que se pidió (o 1 por omisión) |
| `page_size` | entero de 1 a 100 | cuántos cobros como máximo trae una página (10 por omisión, R6) |
| `total_pages` | entero ≥ 0 | `ceil(total / page_size)`; `0` cuando `total` es `0` |

La paginación va en el **cuerpo**, nunca en un encabezado (R1): es el único cambio deliberado frente al
patrón ya existente de `clinic-subscriptions`.

## Orden

`created_at` descendente; en empate (dos cobros creados en el mismo instante, dos intentos simultáneos),
`id` descendente — el mismo criterio de desempate que ya usa el listado de cobros de clínicas.

## Estados

Ninguno nuevo: los cobros siguen el ciclo ya definido en la spec 010 (`pending` → `applied` o `closed`).
Esta lectura no mueve ningún cobro de estado (R2, R3): es una fotografía de lo que ya está guardado.

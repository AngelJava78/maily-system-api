# Data Model: plan de cada cobro y filtro por estado

## Cambio de esquema (migración 0010, aditiva)

`subscription_charges` (spec 010, migración 0008/0009) gana una columna:

| Columna | Tipo | Nullable | Descripción |
|---|---|---|---|
| `plan` | `VARCHAR(100)` | sí | Nombre del plan de la organización al instante en que se creó el cobro (foto, nunca un join al catálogo). `NULL` en los cobros creados antes de esta migración y, en teoría, nunca en los creados después (siempre se resuelve un nombre antes de llamar `add_charge`). |

Sin cambios en ninguna restricción (`CheckConstraint`), índice ni disparador existente de la tabla. El
modelo `src/models/subscription_charge.py` (`SubscriptionCharge`) agrega el campo correspondiente.

## DTO (`src/dtos/subscription_period.py`)

`SubscriptionChargeRead` gana el campo `plan: str | None` (requerido en el JSON, su valor puede ser `null`
— mismo patrón que `closed_reason`). `SubscriptionChargesPageRead` no cambia: sigue siendo
`{items, total, page, page_size, total_pages}`, solo que ahora `total`/`total_pages` pueden reflejar un
subconjunto filtrado por `status`.

## Parámetro de consulta nuevo

`GET /api/v1/subscription-periods/{organization_id}/charges` gana `status` (opcional, query): uno de
`pending`/`applied`/`closed` (el mismo `ChargeStatusName` ya declarado). Ausente ⇒ sin filtrar (igual que
hoy). Cualquier otro valor ⇒ 422 `validation_error` (lo resuelve FastAPI/Pydantic contra el `Literal`, sin
código adicional de validación).

## Flujo de escritura

`SubscriptionPeriodService.start_payment` ya resuelve el plan vigente de la organización en `_prepare`
(`context.plan`, un `PlanTerms` con `.name`) antes de llamar a `SubscriptionPeriodRepository.add_charge`;
esta feature solo agrega `plan=context.plan.name` a esa llamada. Ningún otro punto de escritura de
`subscription_charges` existe (`close_charge`/`apply_charge` actualizan columnas de resolución, no `plan`).

## Flujo de lectura

`SubscriptionPeriodService.list_charges` gana el parámetro `status: str | None`, que pasa sin
transformación a `SubscriptionPeriodRepository.list_charges`. El Repository agrega, cuando `status` no es
`None`, una condición `SubscriptionCharge.status == status` tanto a la consulta de conteo como a la de
selección — la misma lista de condiciones para ambas, así que `total` siempre coincide con lo que `items`
representa a través de todas sus páginas.

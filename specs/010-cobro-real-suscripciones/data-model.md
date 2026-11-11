# Data Model: Cobro Real de Suscripciones de Clínicas

Una sola tabla nueva. `subscriptions`/`subscription_statuses`/`subscription_types`/
`subscription_modules` (specs 001-009) no cambian. **No hay tabla `clinic_subscriptions` ni su
catálogo de estatus en este servicio** (rediseño 2026-11-11): esa entidad vive en el futuro
microservicio Clínicas, consultada en el momento de cobrar (research R6) y nunca guardada aquí.

## `clinic_subscription_charges`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `INTEGER PK` | Autogenerado. |
| `clinic_subscription_id` | `UUID NOT NULL` | Identificador **opaco de Clínicas** (research R4); este servicio no lo valida contra ninguna tabla propia — ya se validó al consultar a Clínicas antes de llegar aquí (FR-002, FR-003). |
| `tenant_id` | `UUID NOT NULL` | Copiado de la respuesta de Clínicas al momento de cobrar (FR-010), para que quien administra la plataforma pueda filtrar el historial sin volver a preguntarle. |
| `period` | `DATE NOT NULL` | La fecha que envió quien disparó el cobro (FR-001; research R3). |
| `amount` | `INTEGER NOT NULL CHECK (amount > 0)` | Centavos (FR-006); nunca `NUMERIC`. |
| `currency` | `VARCHAR(3) NOT NULL DEFAULT 'MXN'` | Fija (Assumptions). |
| `payment_id` | `UUID NOT NULL` | El `id` que devolvió Pagos. |
| `payment_status` | `VARCHAR(20) NOT NULL` | Reflejo de `PaymentStatus` de Pagos: `pending`, `approved`, `rejected`, `cancelled`, `partially_refunded`, `refunded` (FR-015; `CHECK` con esos seis valores). |
| `checkout_url` | `TEXT NULL` | Mientras `payment_status = 'pending'`. |
| `idempotency_key` | `VARCHAR(100) NOT NULL` | La enviada a Pagos (research R3). |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `updated_at` cambia cuando se sincroniza el estatus (historia 2). |

Restricciones:

- Índice único en `(clinic_subscription_id, period)`: a lo sumo **un cobro por suscripción de
  clínica y periodo** (`clinic_subscription_charges_one_per_period_key`) — hace que la
  `Idempotency-Key` determinista (research R3) tenga siempre, de este lado, una sola fila que
  actualizar en vez de crear una nueva en un reintento del mismo periodo.
- Índice en `payment_id` (sincronización, historia 2), en `clinic_subscription_id` (historial de una
  suscripción) y en `tenant_id` (filtro de historia 3, FR-010).

No tiene estatus propio más allá de `payment_status`: no se «cancela» ni se «elimina» una fila; se
añade una fila nueva por cada `(clinic_subscription_id, period)` distinto, y la misma fila se
actualiza con reintentos del mismo par (misma `Idempotency-Key`), nunca se duplica.

**Elegibilidad para un nuevo cobro** (research R7): se rechaza (409) solo si ya existe una fila
`approved` para el mismo `(clinic_subscription_id, period)`. `pending`, `rejected` o `cancelled` no
bloquean un nuevo intento.

## Relación con entidades existentes y externas

- **Plan** (`subscriptions`, spec 001): referenciado por el `subscription_id` que reporta Clínicas
  (FR-002); su precio vigente (`monthly_price`/`annual_price`) se lee en el momento de cobrar
  (FR-006), nunca se copia. `maily-system-api` sigue siendo el dueño de este catálogo.
- **Suscripción de una clínica** (clínica + plan + ciclo + estatus): **entidad externa**, propiedad
  de Clínicas (no existe todavía como servicio real). `maily-system-api` solo guarda su
  identificador opaco (`clinic_subscription_id`) y, al cobrar, una copia puntual de `tenant_id` (no
  el resto de sus datos).

## Vista que expone la API (`ClinicSubscriptionChargeView`, no persistida)

Es la fila de `clinic_subscription_charges`, ya sincronizada con Pagos si estaba `pending`
(research R8), serializada directamente — no hay una entidad «suscripción de clínica» que combinar
con ella (a diferencia del diseño anterior a este rediseño).

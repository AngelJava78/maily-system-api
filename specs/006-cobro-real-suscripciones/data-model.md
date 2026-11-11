# Data Model: Cobro Real de Suscripciones de Clínicas

Tres piezas nuevas; `subscriptions` y `subscription_statuses` (spec 001/004) no cambian.

## `clinic_subscription_statuses` (catálogo, administrado a mano — Principio VI)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `INTEGER PK` | Se reconoce por `id`, nunca por `name` (igual que `subscription_statuses`). |
| `name` | `VARCHAR(50) UNIQUE NOT NULL` | En español. |
| `description` | `TEXT` | Opcional. |

Filas iniciales (migración, research R6):

| `id` | `name` |
|---|---|
| 1 | Activa |
| 2 | Con cobro pendiente de resolver |
| 3 | Cancelada |

## `clinic_subscriptions`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `INTEGER PK` | Autogenerado, igual que `subscriptions.id`. |
| `tenant_id` | `UUID NOT NULL` | La clínica (FR-006); no hay tabla de clínicas (fuera de alcance, igual que `mailySoft-usuarios` spec 019). |
| `subscription_id` | `INTEGER NOT NULL REFERENCES subscriptions(id)` | El plan asignado (FR-001); no se copian sus datos. |
| `billing_cycle` | `VARCHAR(10) NOT NULL` | `CHECK (billing_cycle IN ('monthly', 'annual'))` (FR-002). |
| `started_at` | `TIMESTAMPTZ NOT NULL` | Fecha de inicio. |
| `next_billing_at` | `TIMESTAMPTZ NOT NULL` | Próximo cobro (FR-005); avanza un ciclo tras un cobro `approved` (FR-015). |
| `status_id` | `INTEGER NOT NULL REFERENCES clinic_subscription_statuses(id) DEFAULT 1` | 1 Activa, 2 con cobro pendiente de resolver, 3 Cancelada. |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `updated_at` con disparador, igual que `subscriptions`. |

**Sin columna de «cobro vigente»**: una referencia a `clinic_subscription_charges` desde aquí sería
circular con la referencia de esa tabla hacia esta (`clinic_subscription_charges.
clinic_subscription_id`). El cobro vigente (historia 4, escenario 1: `null` hasta el primer
disparo) se lee como la fila más reciente de `clinic_subscription_charges` para esa suscripción de
clínica (por `period` descendente), sin guardar un puntero propio.

Restricciones:

- `CHECK (billing_cycle IN ('monthly', 'annual'))` (nombre: `clinic_subscriptions_billing_cycle_check`).
- Índice único parcial: a lo sumo una fila por `tenant_id` con `status_id IN (1, 2)` (FR-004):
  `CREATE UNIQUE INDEX clinic_subscriptions_one_active_per_tenant_key ON clinic_subscriptions
  (tenant_id) WHERE status_id IN (1, 2)`.
- Índice en `tenant_id` (filtro de FR-007) y en `status_id`.

**Transiciones de `status_id`** (FR-015, research R6 y R7):

```text
(crear) ──────────────────────────────► 1 Activa
1 Activa ── disparar cobro (pending) ──► 2 Con cobro pendiente de resolver
2 (pending) ── Pagos: approved ────────► 1 Activa (next_billing_at avanza un ciclo)
2 (pending) ── Pagos: rejected/cancelled ► 2 (se queda; disponible para reintentar, FR-015)
1 Activa ── cancelar ──────────────────► 3 Cancelada
2 (solo si el cobro vigente no es pending) ── cancelar ► 3 Cancelada
3 Cancelada ──────────────────────────► (sin salida; crear una nueva suscripción de clínica)
```

Cancelar con un cobro vigente `pending` se rechaza (409, historia 5 escenario 2): solo se cancela
desde 1 o desde 2 cuando el cobro vigente ya está resuelto en contra (`rejected`/`cancelled`).

## `clinic_subscription_charges`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `INTEGER PK` | Autogenerado. |
| `clinic_subscription_id` | `INTEGER NOT NULL REFERENCES clinic_subscriptions(id)` | A qué suscripción de clínica pertenece. |
| `period` | `DATE NOT NULL` | La fecha de `next_billing_at` (solo fecha) vigente cuando se disparó este cobro; identifica el periodo (research R3). |
| `amount` | `INTEGER NOT NULL CHECK (amount > 0)` | Centavos (FR-009); nunca `NUMERIC`: es lo que se envió a Pagos, no un precio propio. |
| `currency` | `VARCHAR(3) NOT NULL DEFAULT 'MXN'` | Fija (Assumptions). |
| `payment_id` | `UUID NOT NULL` | El `id` que devolvió Pagos. |
| `payment_status` | `VARCHAR(20) NOT NULL` | Reflejo de `PaymentStatus` de Pagos: `pending`, `approved`, `rejected`, `cancelled`, `partially_refunded`, `refunded` (FR-018; `CHECK` con esos seis valores). |
| `checkout_url` | `TEXT NULL` | Mientras `payment_status = 'pending'` (igual que Pagos). |
| `idempotency_key` | `VARCHAR(100) NOT NULL` | La enviada a Pagos (research R3). |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `updated_at` cambia cuando se sincroniza el estatus (historia 3). |

Restricciones:

- Índice único en `(clinic_subscription_id, period)`: **a lo sumo un cobro por suscripción de
  clínica y periodo** (`clinic_subscription_charges_one_per_period_key`) — es lo que hace que la
  `Idempotency-Key` determinista (research R3) tenga siempre, de este lado, una sola fila que
  actualizar en vez de crear una nueva en un reintento.
- Índice en `payment_id` (para la sincronización de la historia 3) y en `clinic_subscription_id`.

No tiene estatus propio más allá de `payment_status`: no se «cancela» ni se «elimina» una fila de
historial; se añade una fila nueva por cada periodo distinto que se cobra, y la misma fila se
actualiza con reintentos **del mismo periodo** (misma `Idempotency-Key`, mismo `(clinic_subscription_id,
period)`), nunca se duplica.

## Relación con entidades existentes

- **Plan** (`subscriptions`, spec 001): `clinic_subscriptions.subscription_id` la referencia; su
  precio vigente (`monthly_price`/`annual_price`) y su `trial_days` se leen en el momento de crear la
  suscripción de clínica (FR-005) y en el momento de cobrar (FR-009), nunca se copian.
- **Clínica**: solo un `tenant_id` (UUID), sin tabla propia en este servicio (Edge Cases de la spec).

## Vista que expone la API (`ClinicSubscriptionView`, no persistida)

Combina `ClinicSubscription` con su cobro vigente (el `ClinicSubscriptionCharge` más reciente de
esa suscripción, ya sincronizado si estaba `pending` — research R8) para la respuesta de
`GET`/`POST`/`PATCH` de `/api/v1/clinic-subscriptions`, igual que `SubscriptionView` combina
`Subscription` con `clinics_count` en la spec 001.

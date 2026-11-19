# Modelo de datos (Fase 1): Periodo de prueba y siguiente pago de cada organización

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Investigación**: [research.md](research.md)

La feature añade **dos tablas** (el periodo de cada organización y sus cobros), dos clases de
configuración y varias estructuras que viven solo en el código (registros de las integraciones y vistas
del Service). No guarda nada que sea de otro API (FR-042): la organización, su plan vigente, su periodo de
cobro y los pagos se piden en cada uso; de la organización solo se guarda su identificador, como llave.

## 1. Cambio de esquema respecto al vigente (Principio VI)

| | Antes (migraciones 0001–0007) | Después (0008) |
|---|---|---|
| Tablas | `subscription_statuses`, `subscriptions`, `subscription_types`, `subscription_modules`, `monitored_components` | + `subscription_periods`, + `subscription_charges` |
| Restricciones únicas con nombre de las que depende el código | `subscriptions_name_not_deleted_key`, `monitored_components_code_not_deleted_key` | + `subscription_charges_payment_id_key`, + `subscription_charges_terms_attempt_key`, + `subscription_charges_pending_terms_key` (índice único parcial) |
| Índices | los de las tablas anteriores | + `subscription_charges_pending_idx` (parcial), + `subscription_charges_pending_terms_key` (único parcial) |
| Funciones | `set_updated_at()` | Sin cambios (se reutiliza) |
| Disparadores | `subscriptions_set_updated_at`, `monitored_components_set_updated_at` | + `subscription_periods_set_updated_at`, + `subscription_charges_set_updated_at` |
| Datos iniciales | estatus y tipos de suscripción | Sin cambios: las dos tablas **empiezan vacías** |

Ninguna tabla existente cambia ni tiene columnas nuevas. La migración `0008_subscription_periods.py` revisa
`0007`, es reversible (su `downgrade` borra disparadores, índice y tablas, en ese orden, y **no** la función de
0001) y reproduce [contracts/database-schema.sql](contracts/database-schema.sql).
`project-definition/DATA_SCHEMA.md` añade las dos tablas con el comentario
`-- [spec 010-subscription-periods]` y amplía su tabla de nombres de restricciones.
`project-definition/create_database.sql` no cambia (crea hasta 0002; `alembic upgrade head` aplica el resto).

## 2. `subscription_periods` — el periodo de cada organización

Una fila por organización, creada en el primer contacto (FR-007). La fecha del siguiente pago, el estado y
los días que faltan **no se guardan**: se derivan (FR-012).

| Columna | Tipo | Nula | Por defecto | Reglas |
|---|---|---|---|---|
| `organization_id` | `uuid` | no | — | **Clave primaria.** Identificador de la organización en Clínicas; sin clave foránea (es de otro sistema) |
| `started_at` | `timestamptz` | no | — | Inicio del primer periodo: la más reciente entre el alta y la fecha de corte (FR-008) |
| `trial_ends_at` | `timestamptz` | sí | `NULL` | Fin de la prueba; `NULL` si el plan no tenía prueba (`trial_days` = 0). Se fija al crear la fila y no cambia (FR-009) |
| `paid_until` | `timestamptz` | sí | `NULL` | Hasta cuándo está pagada; `NULL` mientras no se aplique un pago. Solo la mueve la aplicación de un cobro (FR-032) |
| `created_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | — |
| `updated_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | Lo mueve el disparador en cada `UPDATE` |

Restricciones con nombre: `subscription_periods_pkey`; `subscription_periods_trial_ends_check`
(`trial_ends_at IS NULL OR trial_ends_at >= started_at`); `subscription_periods_paid_until_check`
(`paid_until IS NULL OR paid_until > started_at`).

**Derivados** (en `services/billing_rules.py`, no columnas): la fecha del siguiente pago
(`paid_until`, si no `trial_ends_at`, si no `started_at`), el estado y los días que faltan (research R3).

## 3. `subscription_charges` — los cobros que esta API inició

Una fila por pago creado en Pagos por esta API (FR-021). No guarda el estatus del pago ni su dirección de
checkout: se piden a Pagos (Principio IX); `status` es el **resultado propio** de la conciliación.

| Columna | Tipo | Nula | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | no | `gen_random_uuid()` | Clave primaria interna |
| `organization_id` | `uuid` | no | — | Clave foránea a `subscription_periods(organization_id)` |
| `payment_id` | `uuid` | no | — | Identificador del pago en Pagos. **Único**: un pago es un solo cobro |
| `amount` | `numeric(10,2)` | no | — | Importe en pesos, mayor que 0 (FR-016, FR-018); decimal exacto, nunca `float` |
| `currency` | `varchar(3)` | no | — | Solo `MXN` |
| `billing_period` | `varchar(10)` | no | — | `monthly` o `annual`: duración del periodo que cubrirá |
| `settles_due_at` | `timestamptz` | no | — | La fecha de pago que salda: la del siguiente pago vigente al iniciarlo |
| `attempt` | `integer` | no | — | 1 más el número de intentos previos con las mismas condiciones que ya terminaron, aplicados o cerrados (research R6) |
| `status` | `varchar(10)` | no | `'pending'` | `pending`, `applied` o `closed` |
| `closed_reason` | `varchar(20)` | sí | `NULL` | Solo si `closed`: `rejected`, `cancelled`, `inconsistent` o `refunded` |
| `period_starts_at` | `timestamptz` | sí | `NULL` | Solo si `applied`: inicio del periodo cubierto (FR-029) |
| `period_ends_at` | `timestamptz` | sí | `NULL` | Solo si `applied`: fin del periodo cubierto; es el nuevo `paid_until` |
| `resolved_at` | `timestamptz` | sí | `NULL` | Cuándo se aplicó o se cerró (el reloj de la API) |
| `created_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | Cuándo se inició |
| `updated_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | Disparador |

Restricciones con nombre (las usa el código o las pruebas): `subscription_charges_pkey`;
`subscription_charges_organization_id_fkey`; **`subscription_charges_payment_id_key`** (único); **`subscription_charges_terms_attempt_key`**
(único: `organization_id, settles_due_at, billing_period, amount, attempt`; decide la carrera de dos inicios
simultáneos); **`subscription_charges_pending_terms_key`** (índice único parcial `organization_id,
settles_due_at, billing_period, amount WHERE status = 'pending'`: a lo sumo un cobro sin resolver por
periodo e importe, cualquiera que sea el intento); `subscription_charges_amount_check`; `subscription_charges_currency_check`;
`subscription_charges_billing_period_check`; `subscription_charges_attempt_check`;
`subscription_charges_status_check`; `subscription_charges_closed_reason_check` y
**`subscription_charges_resolution_check`**, que liga el estado con sus columnas:

| `status` | `closed_reason` | `period_starts_at` / `period_ends_at` | `resolved_at` |
|---|---|---|---|
| `pending` | nulo | nulos | nulo |
| `applied` | nulo | ambos con valor y `period_ends_at > period_starts_at` | con valor |
| `closed` | con valor | nulos | con valor |

Índice parcial `subscription_charges_pending_idx` (`organization_id, created_at` donde `status = 'pending'`):
la conciliación y la búsqueda del cobro pendiente solo leen los pendientes de una organización.

### Ciclo de vida de un cobro

```text
  iniciar el pago ──► PENDING
                        │
   Pagos: approved + importe/moneda/referencia coinciden ──────────► APPLIED   (paid_until se mueve, una sola vez)
   Pagos: approved + no coinciden ─────────────────────────────────► CLOSED · inconsistent (y un WARNING)
   Pagos: rejected ────────────────────────────────────────────────► CLOSED · rejected
   Pagos: cancelled ───────────────────────────────────────────────► CLOSED · cancelled
   Pagos: partially_refunded / refunded (sin aplicar) ─────────────► CLOSED · refunded
   Pagos: pending, sin respuesta o respuesta inesperada ───────────► sigue PENDING
```

`APPLIED` y `CLOSED` son finales: un cobro aplicado no se vuelve a consultar, así que un reembolso posterior
no revoca su periodo (D3). El cambio de `pending` a otro estado es una sola sentencia condicionada
(`WHERE status = 'pending'`): con peticiones simultáneas solo una lo logra (research R5).

## 4. Modelos ORM (`src/models/`)

- `subscription_period.py`: `SubscriptionPeriod(Base)` con las columnas de la sección 2 (`Uuid` de
  SQLAlchemy, `DateTime(timezone=True)`, `server_default=text("CURRENT_TIMESTAMP")`) y sus `CheckConstraint`
  con los nombres cortos que completa la convención de `Base` (`trial_ends_check`, `paid_until_check`).
- `subscription_charge.py`: `SubscriptionCharge(Base)` con las columnas de la sección 3, `Numeric(10, 2)`
  para `amount`, `ForeignKey("subscription_periods.organization_id")`, los dos `UniqueConstraint` con nombre,
  los `CheckConstraint` (`amount_check`, `currency_check`, `billing_period_check`, `attempt_check`,
  `status_check`, `closed_reason_check`, `resolution_check`) y el `Index` parcial declarado como en
  `Subscription`. Constantes para los estados y los motivos (`ChargeStatus`, `ClosedReason`).
- Ambos se exportan en `src/models/__init__.py` para que `test_models_match_migrations.py` los compare con
  la migración (tipos y valores por defecto del servidor).

## 5. Registros internos (integraciones, Repository y Service)

Clases `dataclass(frozen=True, slots=True)` sin Pydantic ni FastAPI (como `dashboard_source.py`).

| Registro | Módulo | Campos | Para qué |
|---|---|---|---|
| `OrganizationRecord` | `integrations/clinics_api.py` | `id` (UUID), `subscription_id` (int), `billing_period` (`monthly`/`annual`), `created_at` (aware, UTC) | Lo único que esta API toma de Clínicas (R9) |
| `PaymentRecord` | `integrations/payments_api.py` | `id`, `status`, `amount` (int, unidad mínima), `currency`, `resource_type`, `resource_id`, `checkout_url` (o `None`), `updated_at` (aware, UTC) | Lo único que esta API toma de Pagos (R10) |
| `PlanTerms` | `repositories/subscription_repository.py` | `id`, `name`, `trial_days`, `monthly_price`, `annual_price` (`Decimal`) | El plan del catálogo en cualquier estatus (FR-034) |
| `ApplyOutcome` | `repositories/subscription_period_repository.py` | `APPLIED`, `ALREADY_RESOLVED`, `STALE` | Resultado de aplicar un cobro (R5) |
| `PeriodView` | `services/subscription_period_service.py` | `state`, `trial_ends_at`, `payment_due_at`, `days_remaining`, `plan` (`id`, `name`), `billing_period`, `amount`, `payment_in_progress` | Lo que sirve a `get_subscription_period` |
| `PaymentStart` | `services/subscription_period_service.py` | `checkout_url`, `amount`, `billing_period`, `created` (bool) | Lo que sirve a `create_subscription_payment` (201 si `created`, 200 si no) |

## 6. DTOs de respuesta (`src/dtos/subscription_period.py`)

Todos los campos están siempre presentes; los que pueden faltar valen `null`, nunca se omiten. Las fechas
son ISO 8601 en UTC con `Z`; los importes, texto con dos decimales (como `monthly_price` del catálogo).

| DTO | Operación | Campos |
|---|---|---|
| `PlanRead` | (anidado) | `id` (entero), `name` |
| `SubscriptionPeriodRead` | `get_subscription_period` | `state` (`trial`, `current`, `overdue`, `no_charge`), `trial_ends_at`, `payment_due_at`, `days_remaining`, `subscription` (`PlanRead`), `billing_period` (`monthly`, `annual`), `amount`, `currency` (`MXN`), `payment_in_progress` (`true`, `false`, `null`) |
| `SubscriptionPaymentRead` | `create_subscription_payment` | `checkout_url`, `amount`, `currency` (`MXN`), `billing_period` |

Ningún DTO tiene campos para el token, direcciones de otros APIs, identificadores de pago ni datos de las
organizaciones que no sean los de la tabla. Invariantes que prueban los DTOs: `state` = `no_charge` ⇒
`payment_due_at` y `days_remaining` nulos; `state` ∈ {`trial`, `current`} ⇒ `days_remaining` ≥ 1;
`state` = `overdue` ⇒ `days_remaining` ≤ 0 (FR-014).

## 7. Configuración (`src/config.py`)

| Variable | Clase | Obligatoria | Valor | Efecto |
|---|---|---|---|---|
| `PAYMENTS_API_BASE_URL` | `PaymentsSettings` | sí | `http(s)://host[:puerto]`, sin barra final | Dirección de Pagos; `http://` fuera de red local o Docker → advertencia que nombra la variable (nunca la dirección) |
| `PAYMENTS_API_TIMEOUT_SECONDS` | `PaymentsSettings` | no (5) | número > 0 y ≤ 30 | Tiempo máximo **total** de cada llamada a Pagos |
| `BILLING_CUTOFF_AT` | `BillingSettings` | sí | ISO 8601 con zona (`2026-11-18T00:00:00Z`) | Ningún primer periodo empieza antes (FR-008); normalizada a UTC |

Variables vacías cuentan como no definidas (`env_ignore_empty`). Se validan al arrancar junto a las demás y
un solo mensaje nombra todas las que falten o no sean válidas, nunca sus valores. Un cambio exige reiniciar.
`CORS_ALLOWED_ORIGINS` ya existe y no cambia.

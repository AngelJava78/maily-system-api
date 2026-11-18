-- Esquema de la spec 010-subscription-periods (migración 0008). Es lo que `alembic upgrade head` aplica
-- después de 0007; la migración y los modelos de `src/models/` MUST reproducirlo (Principio VI).
--
-- Cambio respecto al esquema vigente: dos tablas nuevas, un índice parcial y dos disparadores. Ninguna
-- tabla existente cambia. Las dos tablas empiezan vacías. `set_updated_at()` es la función de 0001.

-- =====================================================================================================
-- Migración 0008 — upgrade()
-- =====================================================================================================

-- [spec 010-subscription-periods FR-007 a FR-012, FR-042] El periodo de cada organización. La
-- organización es de otro API (Clínicas): su identificador es una referencia, sin clave foránea. La
-- fecha del siguiente pago, el estado y los días que faltan NO se guardan: se derivan al consultar.
CREATE TABLE subscription_periods (
    organization_id uuid        PRIMARY KEY,
    started_at      timestamptz NOT NULL,
    trial_ends_at   timestamptz,                       -- NULL = el plan no tenía prueba
    paid_until      timestamptz,                       -- NULL = ningún pago aplicado
    created_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT subscription_periods_trial_ends_check
        CHECK (trial_ends_at IS NULL OR trial_ends_at >= started_at),
    CONSTRAINT subscription_periods_paid_until_check
        CHECK (paid_until IS NULL OR paid_until > started_at)
);

-- [spec 010 FR-043] updated_at cambia con cualquier UPDATE (reutiliza set_updated_at de 0001).
CREATE TRIGGER subscription_periods_set_updated_at
    BEFORE UPDATE ON subscription_periods
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- [spec 010 FR-021, FR-022, FR-032] Los cobros que esta API inició. `payment_id` es el pago en Pagos
-- (único). `status` es el resultado PROPIO de la conciliación; el estatus del pago y su checkout no se
-- guardan. El importe es NUMERIC (Principio VI), nunca float.
CREATE TABLE subscription_charges (
    id               uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid          NOT NULL REFERENCES subscription_periods (organization_id),
    payment_id       uuid          NOT NULL,
    amount           numeric(10,2) NOT NULL,
    currency         varchar(3)    NOT NULL,
    billing_period   varchar(10)   NOT NULL,           -- duración del periodo que cubrirá
    settles_due_at   timestamptz   NOT NULL,           -- la fecha de pago que salda
    attempt          integer       NOT NULL,           -- 1 + intentos previos ya terminados con las mismas condiciones
    status           varchar(10)   NOT NULL DEFAULT 'pending',
    closed_reason    varchar(20),                      -- solo si status = 'closed'
    period_starts_at timestamptz,                      -- solo si status = 'applied'
    period_ends_at   timestamptz,                      -- solo si status = 'applied'
    resolved_at      timestamptz,                      -- cuándo se aplicó o se cerró
    created_at       timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Un pago de Pagos es un solo cobro.
    CONSTRAINT subscription_charges_payment_id_key UNIQUE (payment_id),
    -- Mismas condiciones e intento = el mismo cobro: decide la carrera de dos inicios simultáneos.
    CONSTRAINT subscription_charges_terms_attempt_key
        UNIQUE (organization_id, settles_due_at, billing_period, amount, attempt),
    CONSTRAINT subscription_charges_amount_check CHECK (amount > 0),
    CONSTRAINT subscription_charges_currency_check CHECK (currency = 'MXN'),
    CONSTRAINT subscription_charges_billing_period_check CHECK (billing_period IN ('monthly', 'annual')),
    CONSTRAINT subscription_charges_attempt_check CHECK (attempt >= 1),
    CONSTRAINT subscription_charges_status_check CHECK (status IN ('pending', 'applied', 'closed')),
    CONSTRAINT subscription_charges_closed_reason_check
        CHECK (closed_reason IS NULL OR closed_reason IN ('rejected', 'cancelled', 'inconsistent', 'refunded')),
    -- El estado fija qué columnas llevan valor.
    CONSTRAINT subscription_charges_resolution_check CHECK (
        (status = 'pending' AND closed_reason IS NULL AND period_starts_at IS NULL
            AND period_ends_at IS NULL AND resolved_at IS NULL)
        OR (status = 'applied' AND closed_reason IS NULL AND period_starts_at IS NOT NULL
            AND period_ends_at > period_starts_at AND resolved_at IS NOT NULL)
        OR (status = 'closed' AND closed_reason IS NOT NULL AND period_starts_at IS NULL
            AND period_ends_at IS NULL AND resolved_at IS NOT NULL)
    )
);

-- [spec 010 FR-026] La conciliación y la búsqueda del cobro pendiente solo leen los pendientes de una
-- organización.
CREATE INDEX subscription_charges_pending_idx
    ON subscription_charges (organization_id, created_at)
    WHERE status = 'pending';

-- [spec 010 FR-022] A lo sumo un cobro sin resolver por periodo e importe, cualquiera que sea el intento:
-- dos inicios simultáneos no pueden dejar dos cobros, así que solo se ofrece un checkout.
CREATE UNIQUE INDEX subscription_charges_pending_terms_key
    ON subscription_charges (organization_id, settles_due_at, billing_period, amount)
    WHERE status = 'pending';

CREATE TRIGGER subscription_charges_set_updated_at
    BEFORE UPDATE ON subscription_charges
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================================================
-- Migración 0008 — downgrade()
-- =====================================================================================================
-- DROP TRIGGER subscription_charges_set_updated_at ON subscription_charges;
-- DROP INDEX subscription_charges_pending_terms_key;
-- DROP INDEX subscription_charges_pending_idx;
-- DROP TABLE subscription_charges;
-- DROP TRIGGER subscription_periods_set_updated_at ON subscription_periods;
-- DROP TABLE subscription_periods;
-- (la función set_updated_at() es de 0001 y no se borra)

-- =====================================================================================================
-- Consultas que el Repository ejecuta (referencia; no es DDL)
-- =====================================================================================================
-- Crear el periodo una sola vez (research R4):
--   INSERT INTO subscription_periods (organization_id, started_at, trial_ends_at)
--   VALUES (:org, :started_at, :trial_ends_at) ON CONFLICT (organization_id) DO NOTHING;
--
-- Aplicar un cobro exactamente una vez (research R5), en una sola transacción:
--   UPDATE subscription_charges
--      SET status='applied', period_starts_at=:start, period_ends_at=:end, resolved_at=:now
--    WHERE id=:charge AND organization_id=:org AND status='pending' RETURNING id;      -- 0 filas: ya resuelto
--   UPDATE subscription_periods SET paid_until=:end
--    WHERE organization_id=:org AND paid_until IS NOT DISTINCT FROM :expected
--   RETURNING organization_id;                                                          -- 0 filas: obsoleto
--
-- Cerrar un cobro sin aplicarlo:
--   UPDATE subscription_charges SET status='closed', closed_reason=:reason, resolved_at=:now
--    WHERE id=:charge AND status='pending';

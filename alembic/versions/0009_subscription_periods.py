"""Periodo de suscripción de cada organización y los cobros que esta API inició.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18

Reproduce `specs/010-subscription-periods/contracts/database-schema.sql`: la tabla `subscription_periods`
(una fila por organización: inicio del primer periodo, fin de la prueba y hasta cuándo está pagada) y la
tabla `subscription_charges` (los pagos que esta API creó en Pagos, con su resultado propio), con sus
restricciones, el índice parcial de los cobros pendientes y los disparadores que mantienen `updated_at`.
La organización es de otro API (Clínicas): su identificador es solo una referencia, sin clave foránea. Las
dos tablas empiezan vacías: no hay datos iniciales. Los disparadores reutilizan la función
`set_updated_at()` de la migración 0001, así que el `downgrade` de esta migración no la borra.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # [spec 010-subscription-periods FR-007 a FR-012, FR-042] El periodo de cada organización.
    op.create_table(
        "subscription_periods",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column("paid_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # Como en 0001, la convención de nombres antepone `subscription_periods_` a cada CHECK.
        sa.CheckConstraint(
            "trial_ends_at IS NULL OR trial_ends_at >= started_at", name="trial_ends_check"
        ),
        sa.CheckConstraint("paid_until IS NULL OR paid_until > started_at", name="paid_until_check"),
    )

    # [spec 010 FR-043] updated_at cambia con cualquier UPDATE (reutiliza set_updated_at de 0001).
    op.execute(
        """
        CREATE TRIGGER subscription_periods_set_updated_at
            BEFORE UPDATE ON subscription_periods
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    # [spec 010 FR-021, FR-022, FR-032] Los cobros que esta API inició.
    op.create_table(
        "subscription_charges",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("subscription_periods.organization_id"),
            nullable=False,
        ),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("billing_period", sa.String(10), nullable=False),
        sa.Column("settles_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("closed_reason", sa.String(20)),
        sa.Column("period_starts_at", sa.DateTime(timezone=True)),
        sa.Column("period_ends_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # Un pago de Pagos es un solo cobro (nombre por convención: subscription_charges_payment_id_key).
        sa.UniqueConstraint("payment_id"),
        # Mismas condiciones e intento = el mismo cobro: decide la carrera de dos inicios simultáneos.
        sa.UniqueConstraint(
            "organization_id",
            "settles_due_at",
            "billing_period",
            "amount",
            "attempt",
            name="subscription_charges_terms_attempt_key",
        ),
        sa.CheckConstraint("amount > 0", name="amount_check"),
        sa.CheckConstraint("currency = 'MXN'", name="currency_check"),
        sa.CheckConstraint("billing_period IN ('monthly', 'annual')", name="billing_period_check"),
        sa.CheckConstraint("attempt >= 1", name="attempt_check"),
        sa.CheckConstraint("status IN ('pending', 'applied', 'closed')", name="status_check"),
        sa.CheckConstraint(
            "closed_reason IS NULL OR closed_reason IN "
            "('rejected', 'cancelled', 'inconsistent', 'refunded')",
            name="closed_reason_check",
        ),
        # El estado fija qué columnas llevan valor.
        sa.CheckConstraint(
            "(status = 'pending' AND closed_reason IS NULL AND period_starts_at IS NULL "
            "AND period_ends_at IS NULL AND resolved_at IS NULL) "
            "OR (status = 'applied' AND closed_reason IS NULL AND period_starts_at IS NOT NULL "
            "AND period_ends_at > period_starts_at AND resolved_at IS NOT NULL) "
            "OR (status = 'closed' AND closed_reason IS NOT NULL AND period_starts_at IS NULL "
            "AND period_ends_at IS NULL AND resolved_at IS NOT NULL)",
            name="resolution_check",
        ),
    )

    # [spec 010 FR-026] La conciliación y la búsqueda del cobro pendiente solo leen los pendientes.
    op.create_index(
        "subscription_charges_pending_idx",
        "subscription_charges",
        ["organization_id", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    # [spec 010 FR-022] A lo sumo un cobro sin resolver por periodo e importe, cualquiera que sea el
    # intento: dos inicios simultáneos no pueden dejar dos cobros (solo se ofrece un checkout).
    op.create_index(
        "subscription_charges_pending_terms_key",
        "subscription_charges",
        ["organization_id", "settles_due_at", "billing_period", "amount"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.execute(
        """
        CREATE TRIGGER subscription_charges_set_updated_at
            BEFORE UPDATE ON subscription_charges
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER subscription_charges_set_updated_at ON subscription_charges")
    op.drop_index("subscription_charges_pending_terms_key", table_name="subscription_charges")
    op.drop_index("subscription_charges_pending_idx", table_name="subscription_charges")
    op.drop_table("subscription_charges")
    op.execute("DROP TRIGGER subscription_periods_set_updated_at ON subscription_periods")
    op.drop_table("subscription_periods")

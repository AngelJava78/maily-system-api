"""Historial de cobros de suscripciones de clínica.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11

Reproduces `specs/010-cobro-real-suscripciones/contracts/database-schema.sql`: only
`clinic_subscription_charges`. The clinic/plan/cycle assignment (which clinic has which plan, on
which billing cycle) is NOT this service's table (rediseño 2026-11-11, Principle IX): it belongs to
the future Clinics microservice, consulted at charge time and never stored here.
`clinic_subscription_id` is an opaque UUID with no local foreign key. The trigger reuses the
`set_updated_at()` function of migration 0001.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "clinic_subscription_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'MXN'")),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_status", sa.String(20), nullable=False),
        sa.Column("checkout_url", sa.Text()),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
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
        sa.CheckConstraint("amount > 0", name="amount_check"),
        sa.CheckConstraint(
            "payment_status IN ('pending','approved','rejected','cancelled',"
            "'partially_refunded','refunded')",
            name="payment_status_check",
        ),
    )

    # A lo sumo un cobro por suscripción de clínica y periodo (research R3).
    op.create_index(
        "clinic_subscription_charges_one_per_period_key",
        "clinic_subscription_charges",
        ["clinic_subscription_id", "period"],
        unique=True,
    )
    op.create_index(
        "clinic_subscription_charges_payment_id_idx",
        "clinic_subscription_charges",
        ["payment_id"],
    )
    op.create_index(
        "clinic_subscription_charges_clinic_subscription_id_idx",
        "clinic_subscription_charges",
        ["clinic_subscription_id"],
    )
    op.create_index(
        "clinic_subscription_charges_tenant_id_idx",
        "clinic_subscription_charges",
        ["tenant_id"],
    )

    op.execute(
        """
        CREATE TRIGGER clinic_subscription_charges_set_updated_at
            BEFORE UPDATE ON clinic_subscription_charges
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER clinic_subscription_charges_set_updated_at ON clinic_subscription_charges"
    )
    op.drop_table("clinic_subscription_charges")

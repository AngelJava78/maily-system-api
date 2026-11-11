"""Suscripción de una clínica y su historial de cobros.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10

Reproduces `specs/006-cobro-real-suscripciones/contracts/database-schema.sql`: the status catalog
(`clinic_subscription_statuses`), the subscription of a clinic (`clinic_subscriptions`) and its
charge history (`clinic_subscription_charges`). `clinic_subscriptions` has no column pointing at
its current charge (that would make a foreign-key cycle with `clinic_subscription_charges`, which
already references `clinic_subscriptions`): the current charge is read as the most recent row of
`clinic_subscription_charges` for that subscription. The two triggers reuse the `set_updated_at()`
function of migration 0001.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Catálogo de estatus (se administra a mano). [spec 006-cobro-real-suscripciones research R6]
    op.create_table(
        "clinic_subscription_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
    )

    op.create_table(
        "clinic_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("billing_cycle", sa.String(10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_billing_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status_id", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
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
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.ForeignKeyConstraint(["status_id"], ["clinic_subscription_statuses.id"]),
        sa.CheckConstraint("billing_cycle IN ('monthly', 'annual')", name="billing_cycle_check"),
    )

    # [FR-004] a lo sumo una suscripción Activa (1) o con cobro pendiente de resolver (2) por clínica.
    op.create_index(
        "clinic_subscriptions_one_active_per_tenant_key",
        "clinic_subscriptions",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status_id IN (1, 2)"),
    )
    op.create_index(
        "clinic_subscriptions_tenant_id_idx", "clinic_subscriptions", ["tenant_id"]
    )
    op.create_index(
        "clinic_subscriptions_status_id_idx", "clinic_subscriptions", ["status_id"]
    )

    op.create_table(
        "clinic_subscription_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_subscription_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "currency", sa.String(3), nullable=False, server_default=sa.text("'MXN'")
        ),
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
        sa.ForeignKeyConstraint(["clinic_subscription_id"], ["clinic_subscriptions.id"]),
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

    op.execute(
        """
        CREATE TRIGGER clinic_subscriptions_set_updated_at
            BEFORE UPDATE ON clinic_subscriptions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_subscription_charges_set_updated_at
            BEFORE UPDATE ON clinic_subscription_charges
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.bulk_insert(
        sa.table(
            "clinic_subscription_statuses",
            sa.column("id", sa.Integer()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
        ),
        [
            {
                "id": 1,
                "name": "Activa",
                "description": "Al día; sin ningún cobro pendiente de resolver.",
            },
            {
                "id": 2,
                "name": "Con cobro pendiente de resolver",
                "description": (
                    "Tiene un cobro en curso (pending) o rechazado que admite un nuevo intento."
                ),
            },
            {
                "id": 3,
                "name": "Cancelada",
                "description": "Baja lógica: ya no admite nuevos cobros.",
            },
        ],
    )
    # Los estatus añadidos a mano empiezan en 4.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('clinic_subscription_statuses', 'id'), 3)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER clinic_subscription_charges_set_updated_at ON clinic_subscription_charges"
    )
    op.execute("DROP TRIGGER clinic_subscriptions_set_updated_at ON clinic_subscriptions")
    op.drop_table("clinic_subscription_charges")
    op.drop_index("clinic_subscriptions_status_id_idx", table_name="clinic_subscriptions")
    op.drop_index("clinic_subscriptions_tenant_id_idx", table_name="clinic_subscriptions")
    op.drop_index(
        "clinic_subscriptions_one_active_per_tenant_key", table_name="clinic_subscriptions"
    )
    op.drop_table("clinic_subscriptions")
    op.drop_table("clinic_subscription_statuses")

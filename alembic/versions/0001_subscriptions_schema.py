"""Esquema de suscripciones: catálogo de estatus y tabla de suscripciones.

Revision ID: 0001
Revises:
Create Date: 2026-10-18

Reproduce `specs/001-subscriptions-api/contracts/database-schema.sql`. Las restricciones resultan con
los nombres automáticos de PostgreSQL (subscriptions_pkey, subscriptions_name_check,
subscriptions_status_id_fkey...), de los que depende el código. Solo llevan nombre propio el índice
único del nombre y el disparador.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Catálogo de estatus (se administra a mano). [spec 001-subscriptions-api FR-022]
    op.create_table(
        "subscription_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("monthly_price", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "features",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "status_id",
            sa.Integer(),
            sa.ForeignKey("subscription_statuses.id"),
            nullable=False,
            server_default=sa.text("1"),
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
        # La convención de nombres de los modelos (que Alembic aplica) exige nombrar los CHECK; con
        # el prefijo de la tabla resultan los nombres automáticos de PostgreSQL.
        sa.CheckConstraint("btrim(name) <> ''", name="name_check"),
        sa.CheckConstraint("monthly_price >= 0", name="monthly_price_check"),
        sa.CheckConstraint("cardinality(features) <= 20", name="features_check"),
    )

    # [spec FR-014] único, sin distinguir mayúsculas, entre las no eliminadas (estatus 4).
    op.create_index(
        "subscriptions_name_not_deleted_key",
        "subscriptions",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("status_id <> 4"),
    )

    # [spec FR-015] la fecha de última modificación cambia con cualquier UPDATE.
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER subscriptions_set_updated_at
            BEFORE UPDATE ON subscriptions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER subscriptions_set_updated_at ON subscriptions")
    op.execute("DROP FUNCTION set_updated_at()")
    op.drop_index("subscriptions_name_not_deleted_key", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("subscription_statuses")

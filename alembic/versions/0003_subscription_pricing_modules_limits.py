"""Corrección del modelo de suscripciones: precio anual, prueba, autoconsumo, módulos y límites.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23

Reproduce `specs/004-correct-subscriptions-api/contracts/database-schema.sql` (sección «Migración
0003»). Renombra `features` a `other_features` (mismo contenido y CHECK, renombrado); añade siete
columnas nuevas a `subscriptions`. `annual_price` y los cuatro límites son NOT NULL sin DEFAULT: esta
migración asume que la tabla está vacía (spec 004, Assumptions); si algún entorno ya tiene filas,
fallará y necesitará un backfill antes de aplicarse.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("subscriptions", "features", new_column_name="other_features")
    op.execute(
        "ALTER TABLE subscriptions RENAME CONSTRAINT subscriptions_features_check "
        "TO subscriptions_other_features_check"
    )

    op.add_column(
        "subscriptions",
        sa.Column("annual_price", sa.Numeric(10, 2), nullable=False),
    )
    op.add_column(
        "subscriptions",
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "subscriptions",
        sa.Column("self_service", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "module_keys",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['patients']::text[]"),
        ),
    )
    op.add_column(
        "subscriptions", sa.Column("consulting_rooms_limit", sa.Integer(), nullable=False)
    )
    op.add_column("subscriptions", sa.Column("doctors_limit", sa.Integer(), nullable=False))
    op.add_column("subscriptions", sa.Column("assistants_limit", sa.Integer(), nullable=False))
    op.add_column(
        "subscriptions", sa.Column("new_patients_per_year_limit", sa.Integer(), nullable=False)
    )

    op.create_check_constraint(
        "annual_price_check", "subscriptions", "annual_price >= 0"
    )
    op.create_check_constraint(
        "trial_days_check", "subscriptions", "trial_days BETWEEN 0 AND 3650"
    )
    op.create_check_constraint(
        "module_keys_check", "subscriptions", "'patients' = ANY(module_keys)"
    )
    op.create_check_constraint(
        "consulting_rooms_limit_check",
        "subscriptions",
        "consulting_rooms_limit BETWEEN 0 AND 1000000",
    )
    op.create_check_constraint(
        "doctors_limit_check", "subscriptions", "doctors_limit BETWEEN 0 AND 1000000"
    )
    op.create_check_constraint(
        "assistants_limit_check", "subscriptions", "assistants_limit BETWEEN 0 AND 1000000"
    )
    op.create_check_constraint(
        "new_patients_per_year_limit_check",
        "subscriptions",
        "new_patients_per_year_limit BETWEEN 0 AND 1000000",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("subscriptions_new_patients_per_year_limit_check", "subscriptions")
    op.drop_constraint("subscriptions_assistants_limit_check", "subscriptions")
    op.drop_constraint("subscriptions_doctors_limit_check", "subscriptions")
    op.drop_constraint("subscriptions_consulting_rooms_limit_check", "subscriptions")
    op.drop_constraint("subscriptions_module_keys_check", "subscriptions")
    op.drop_constraint("subscriptions_trial_days_check", "subscriptions")
    op.drop_constraint("subscriptions_annual_price_check", "subscriptions")

    op.drop_column("subscriptions", "new_patients_per_year_limit")
    op.drop_column("subscriptions", "assistants_limit")
    op.drop_column("subscriptions", "doctors_limit")
    op.drop_column("subscriptions", "consulting_rooms_limit")
    op.drop_column("subscriptions", "module_keys")
    op.drop_column("subscriptions", "self_service")
    op.drop_column("subscriptions", "trial_days")
    op.drop_column("subscriptions", "annual_price")

    op.execute(
        "ALTER TABLE subscriptions RENAME CONSTRAINT subscriptions_other_features_check "
        "TO subscriptions_features_check"
    )
    op.alter_column("subscriptions", "other_features", new_column_name="features")

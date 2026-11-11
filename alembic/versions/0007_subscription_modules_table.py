"""Guarda los módulos de la suscripción en su propia tabla, en vez de en una columna `text[]`.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27

Reproduce `specs/008-subscription-modules-table/contracts/database-schema.sql` (secciones
«Migración 0007» y «downgrade() de 0007»). Los módulos ya guardados se migran con una sola
sentencia SQL (`unnest`), sin ningún script fuera de Alembic (research R5): el dato de origen ya
vive en esta misma base de datos, a diferencia de `0005`. La regla "patients siempre incluido" deja
de ser un `CHECK` de base de datos (un `CHECK` no ve otras filas de la misma tabla, research R2):
sigue siendo una garantía exclusiva de `SubscriptionService._resolve_modules`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_NAME = "module_keys_check"  # the naming convention prefixes it to subscriptions_module_keys_check


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "subscription_modules",
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), primary_key=True),
        sa.Column("module_key", sa.Text(), primary_key=True),
    )
    op.execute(
        "INSERT INTO subscription_modules (subscription_id, module_key) "
        "SELECT id, unnest(module_keys) FROM subscriptions"
    )
    op.drop_constraint(CHECK_NAME, "subscriptions", type_="check")
    op.drop_column("subscriptions", "module_keys")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "subscriptions",
        sa.Column(
            "module_keys",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['patients']::text[]"),
        ),
    )
    op.execute(
        "UPDATE subscriptions SET module_keys = ("
        "SELECT COALESCE(array_agg(module_key ORDER BY module_key), ARRAY['patients']::text[]) "
        "FROM subscription_modules WHERE subscription_id = subscriptions.id"
        ")"
    )
    op.create_check_constraint(CHECK_NAME, "subscriptions", "'patients' = ANY(module_keys)")
    op.drop_table("subscription_modules")

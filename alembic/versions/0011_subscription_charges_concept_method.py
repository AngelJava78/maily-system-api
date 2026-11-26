"""Agrega las columnas `concept` (texto libre) y `payment_method` (enum corto) a
`subscription_charges`.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25

[spec 014-charges-payment-method-concept] `concept` es una foto del texto amigable que ya se le manda
a Pagos como `description` al crear el cobro (igual que `plan`/`amount`/`billing_period`): nunca se
reescribe. `payment_method` (`card`/`oxxo`/`transfer`) solo se conoce cuando el cobro se resuelve
(aplicado o cerrado); mientras está pendiente, o si ya existía antes de esta migración, vale `NULL`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("subscription_charges", sa.Column("concept", sa.String(length=500), nullable=True))
    op.add_column(
        "subscription_charges", sa.Column("payment_method", sa.String(length=10), nullable=True)
    )
    op.create_check_constraint(
        "payment_method_check",
        "subscription_charges",
        "payment_method IS NULL OR payment_method IN ('card', 'oxxo', 'transfer')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("payment_method_check", "subscription_charges", type_="check")
    op.drop_column("subscription_charges", "payment_method")
    op.drop_column("subscription_charges", "concept")

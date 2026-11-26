"""Agrega la columna `plan` (nombre del plan, texto libre) a `subscription_charges`.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-25

[spec 013-charges-plan-and-status-filter] El nombre del plan vigente al momento del cobro, tomado
como una foto (igual que `amount`/`billing_period`): nunca se vuelve a consultar al catálogo, para
que un cambio de nombre del plan no reescriba el historial. Nullable porque los cobros que ya
existen no tienen de dónde sacarlo con certeza: se quedan en `NULL`, sin intentar adivinarlo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("subscription_charges", sa.Column("plan", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subscription_charges", "plan")

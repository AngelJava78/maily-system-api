"""Agrega el límite de clínicas: un quinto techo de la clínica, acotado por el tipo.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27

Reproduce `specs/007-add-clinics-limit/contracts/database-schema.sql` (sección «Migración 0006»).
`clinics_limit` se agrega con `DEFAULT 1`, válido para cualquier fila existente sin consultar nada
externo (research R5): es el único valor permitido si la suscripción es Individual, y el más bajo
del rango 1 a 100 si no lo es. Por eso, a diferencia de `0005`, esta migración no necesita ningún
script de reconciliación fuera de Alembic. El `CHECK` de dos columnas (research R6) es un respaldo
defensivo: Pydantic (al crear) y el Service (al actualizar) ya impiden que la API llegue a
violarlo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_NAME = "clinics_limit_check"  # the naming convention prefixes it to subscriptions_clinics_limit_check
CHECK_CONDITION = (
    "(subscription_type_id = 1 AND clinics_limit = 1) "
    "OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "subscriptions",
        sa.Column("clinics_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint(CHECK_NAME, "subscriptions", CHECK_CONDITION)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(CHECK_NAME, "subscriptions", type_="check")
    op.drop_column("subscriptions", "clinics_limit")

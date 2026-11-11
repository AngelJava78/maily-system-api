"""Agrega el tipo de suscripción: catálogo propio (Individual o Empresarial).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26

Reproduce `specs/006-add-subscription-type/contracts/database-schema.sql` (sección «Migración
0005»). Tras Clarifications (2026-10-26) el tipo es un catálogo propio (`subscription_types`),
igual que `subscription_statuses`, no una columna con `CHECK` fijo a dos valores: se reescribe en
el mismo archivo (nunca se usó fuera de este repositorio). Orden obligatorio: crear el catálogo,
sembrarlo, y SOLO ENTONCES agregar la columna que lo referencia, para que el `server_default`
tenga una fila 1 ('Individual') que referenciar al asignarla a cada fila existente (FR-001,
FR-008). Ascender a Empresarial las que ya tenían más de una clínica (FR-009) no es parte de esta
migración: lo hace `src/scripts/backfill_subscription_types.py`, que necesita el conteo de
clínicas de otro servicio (ver data-model.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

subscription_types = sa.table(
    "subscription_types",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "subscription_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
    )
    op.bulk_insert(
        subscription_types,
        [
            {
                "id": 1,
                "name": "Individual",
                "description": (
                    "Para médicos independientes; su consultorio se asocia a una sola clínica."
                ),
            },
            {
                "id": 2,
                "name": "Empresarial",
                "description": (
                    "Para empresas con varias clínicas y varios consultorios por clínica."
                ),
            },
        ],
    )
    op.execute("SELECT setval(pg_get_serial_sequence('subscription_types', 'id'), 2)")
    op.add_column(
        "subscriptions",
        sa.Column(
            "subscription_type_id",
            sa.Integer(),
            sa.ForeignKey("subscription_types.id"),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subscriptions", "subscription_type_id")
    op.drop_table("subscription_types")

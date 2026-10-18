"""Datos iniciales: catálogo de estatus de las suscripciones.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18

Los estatus del sistema se reconocen por su identificador (1 a 4), no por su nombre. Los que se
añadan a mano empezarán en 5: la secuencia se deja en 4.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = [
    {"id": 1, "name": "Activa", "description": "Disponible y ofrecida a clínicas nuevas."},
    {
        "id": 2,
        "name": "Inactiva",
        "description": "Retirada de la oferta; las clínicas que ya la tienen la conservan.",
    },
    {"id": 3, "name": "Bloqueada", "description": "Suspendida por la administración."},
    {
        "id": 4,
        "name": "Eliminada",
        "description": "Baja lógica: fuera de toda consulta y operación.",
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    statuses = sa.table(
        "subscription_statuses",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(statuses, STATUSES)
    op.execute("SELECT setval(pg_get_serial_sequence('subscription_statuses', 'id'), 4)")


def downgrade() -> None:
    """Downgrade schema.

    Falla por la clave foránea si hay suscripciones que usan estos estatus: solo para bases de
    desarrollo, igual que revertir `0001`.
    """
    op.execute("DELETE FROM subscription_statuses WHERE id IN (1, 2, 3, 4)")

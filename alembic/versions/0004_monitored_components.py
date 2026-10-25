"""Registro de componentes monitoreados (salud de servicios).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24

Reproduce `specs/005-health-monitoring/contracts/database-schema.sql`: la tabla
`monitored_components`, el índice único parcial del código (`monitored_components_code_not_deleted_key`,
del que depende el código para traducir un código repetido a un 409) y el disparador que mantiene
`updated_at`. El registro empieza vacío: no hay datos iniciales. El disparador reutiliza la función
`set_updated_at()` de la migración 0001, así que el `downgrade` de esta migración no la borra.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # [spec 005-health-monitoring FR-023 a FR-032]
    op.create_table(
        "monitored_components",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("live_path", sa.String(200), nullable=False),
        sa.Column("ready_path", sa.String(200)),
        sa.Column("info_path", sa.String(200)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        # Como en 0001, la convención de nombres antepone `monitored_components_` a cada CHECK.
        sa.CheckConstraint(
            "char_length(code) BETWEEN 2 AND 50 "
            "AND code ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$' "
            "AND code NOT IN ('maily-system-api', 'database')",
            name="code_check",
        ),
        sa.CheckConstraint("btrim(name) <> '' AND name = btrim(name)", name="name_check"),
        sa.CheckConstraint("kind IN ('service', 'frontend')", name="kind_check"),
        sa.CheckConstraint("sort_order BETWEEN 0 AND 9999", name="sort_order_check"),
        sa.CheckConstraint(
            "kind <> 'service' OR (ready_path IS NOT NULL AND info_path IS NOT NULL)",
            name="service_paths_check",
        ),
        sa.CheckConstraint(
            "kind <> 'frontend' OR ready_path IS NULL", name="frontend_ready_path_check"
        ),
    )

    # [spec 005 FR-024, FR-028, FR-029] código único entre los componentes no eliminados.
    op.create_index(
        "monitored_components_code_not_deleted_key",
        "monitored_components",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # [spec 005 FR-028] updated_at cambia con cualquier UPDATE (también con la baja lógica).
    op.execute(
        """
        CREATE TRIGGER monitored_components_set_updated_at
            BEFORE UPDATE ON monitored_components
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER monitored_components_set_updated_at ON monitored_components")
    op.drop_index("monitored_components_code_not_deleted_key", table_name="monitored_components")
    op.drop_table("monitored_components")

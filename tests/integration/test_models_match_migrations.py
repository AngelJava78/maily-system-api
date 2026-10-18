"""Los modelos de `src/models/` coinciden con lo que crean las migraciones (Principio VI)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import AsyncEngine

from src.models import Base


async def test_the_models_match_the_migrations(engine: AsyncEngine, migrated_db: None):
    def differences(connection):
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        return compare_metadata(context, Base.metadata)

    async with engine.connect() as connection:
        result = await connection.run_sync(differences)

    assert result == []

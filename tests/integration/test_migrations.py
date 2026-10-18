"""Las migraciones crean y deshacen el esquema (Principio VI)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import Migrator, fetch_all


@pytest.fixture
async def restore_head(migrator: Migrator):
    """Deja la base de datos en `head` al terminar, pase lo que pase."""
    yield
    await migrator.upgrade("head")


async def names(engine: AsyncEngine, sql: str) -> set[str]:
    return {name for (name,) in await fetch_all(engine, sql)}


async def tables(engine: AsyncEngine) -> set[str]:
    return await names(engine, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")


async def test_upgrade_creates_the_schema(migrator: Migrator, engine: AsyncEngine, restore_head):
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert {"subscription_statuses", "subscriptions"} <= await tables(engine)
    assert "subscriptions_name_not_deleted_key" in await names(
        engine, "SELECT indexname FROM pg_indexes WHERE tablename = 'subscriptions'"
    )
    assert "set_updated_at" in await names(engine, "SELECT proname FROM pg_proc")
    assert "subscriptions_set_updated_at" in await names(
        engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
    )


async def test_downgrade_to_base_removes_everything(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")

    assert not {"subscription_statuses", "subscriptions"} & await tables(engine)
    assert "set_updated_at" not in await names(engine, "SELECT proname FROM pg_proc")


async def test_the_migrations_are_reversible_and_repeatable(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert {"subscription_statuses", "subscriptions"} <= await tables(engine)


async def test_downgrading_only_the_seed_leaves_the_status_table_empty(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0001")

    assert {"subscription_statuses", "subscriptions"} <= await tables(engine)
    assert await fetch_all(engine, "SELECT id FROM subscription_statuses") == []

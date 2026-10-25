"""Migration 0004 creates and removes the registry of monitored components (spec 005, FR-032).

Reproduces `specs/005-health-monitoring/contracts/database-schema.sql`. The function
`set_updated_at()` belongs to migration 0001: 0004 reuses it and its downgrade must not drop it.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import Migrator, fetch_all

CONSTRAINTS = {
    "monitored_components_pkey",
    "monitored_components_code_check",
    "monitored_components_name_check",
    "monitored_components_kind_check",
    "monitored_components_sort_order_check",
    "monitored_components_service_paths_check",
    "monitored_components_frontend_ready_path_check",
}


@pytest.fixture
async def restore_head(migrator: Migrator):
    """Leaves the database at `head` whatever happens."""
    yield
    await migrator.upgrade("head")


async def names(engine: AsyncEngine, sql: str) -> set[str]:
    return {name for (name,) in await fetch_all(engine, sql)}


async def tables(engine: AsyncEngine) -> set[str]:
    return await names(engine, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")


async def triggers(engine: AsyncEngine) -> set[str]:
    return await names(engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")


async def test_upgrade_creates_the_table_its_index_its_constraints_and_its_trigger(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0003")
    await migrator.upgrade("head")

    assert "monitored_components" in await tables(engine)
    [(definition,)] = await fetch_all(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'monitored_components_code_not_deleted_key'",
    )
    assert "UNIQUE" in definition
    assert "WHERE (deleted_at IS NULL)" in definition
    assert CONSTRAINTS <= await names(
        engine,
        "SELECT conname FROM pg_constraint WHERE conrelid = 'monitored_components'::regclass",
    )
    assert "monitored_components_set_updated_at" in await triggers(engine)


async def test_downgrade_to_0003_removes_the_registry_and_keeps_the_function_of_0001(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0003")

    assert "monitored_components" not in await tables(engine)
    assert {"subscription_statuses", "subscriptions"} <= await tables(engine)
    assert "monitored_components_set_updated_at" not in await triggers(engine)
    assert "set_updated_at" in await names(engine, "SELECT proname FROM pg_proc")
    assert "subscriptions_set_updated_at" in await triggers(engine)


async def test_going_up_and_down_is_repeatable(migrator: Migrator, engine: AsyncEngine, restore_head):
    await migrator.upgrade("head")
    for _ in range(2):
        await migrator.downgrade("0003")
        await migrator.upgrade("head")

    assert "monitored_components" in await tables(engine)


async def test_the_identifier_is_a_random_uuid_by_default(engine: AsyncEngine, migrated_db: None):
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO monitored_components (code, name, kind, base_url, live_path, ready_path, info_path) "
                "VALUES ('migracion', 'Migración', 'service', 'http://h', '/health/live', '/health/ready', '/info') "
                "RETURNING id, enabled, sort_order, deleted_at"
            )
        )
        identifier, enabled, sort_order, deleted_at = result.one()
        await connection.execute(text("DELETE FROM monitored_components WHERE code = 'migracion'"))

    assert isinstance(identifier, uuid.UUID)
    assert (enabled, sort_order, deleted_at) == (True, 0, None)

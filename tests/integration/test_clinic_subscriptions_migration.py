"""The 0008 migration creates and undoes the charge history schema (Principle VI, spec 010)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import Migrator, fetch_all


@pytest.fixture
async def restore_head(migrator: Migrator):
    """Leave the database at `head` when done, whatever happens (same pattern as test_migrations.py)."""
    yield
    await migrator.upgrade("head")


async def names(engine: AsyncEngine, sql: str) -> set[str]:
    return {name for (name,) in await fetch_all(engine, sql)}


async def tables(engine: AsyncEngine) -> set[str]:
    return await names(engine, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")


NEW_TABLES = {"clinic_subscription_charges"}


async def test_upgrade_to_0008_creates_the_schema(migrator: Migrator, engine: AsyncEngine, restore_head):
    await migrator.downgrade("0007")
    await migrator.upgrade("0008")

    assert NEW_TABLES <= await tables(engine)
    assert "clinic_subscription_charges_one_per_period_key" in await names(
        engine, "SELECT indexname FROM pg_indexes WHERE tablename = 'clinic_subscription_charges'"
    )
    triggers = await names(engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    assert "clinic_subscription_charges_set_updated_at" in triggers


async def test_downgrade_to_0007_removes_the_table_and_its_trigger(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0007")

    assert not NEW_TABLES & await tables(engine)
    triggers = await names(engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    assert "clinic_subscription_charges_set_updated_at" not in triggers
    # set_updated_at() itself is reused from migration 0001: it must survive.
    assert "set_updated_at" in await names(engine, "SELECT proname FROM pg_proc")


async def test_the_migration_is_reversible_and_repeatable(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("0007")
    await migrator.upgrade("0008")
    await migrator.downgrade("0007")
    await migrator.upgrade("0008")

    assert NEW_TABLES <= await tables(engine)


async def test_downgrade_with_existing_rows_does_not_fail(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    """Uses real (committed) rows, not the rolled-back `db_session` savepoint: `engine`/`migrator`
    are session-scoped and alembic runs outside this test's transaction. `clinic_subscription_id`
    has no local foreign key (rediseño 2026-11-11), so downgrading only ever has to drop this one
    table — nothing else in the schema references it."""
    await migrator.upgrade("head")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO clinic_subscription_charges (clinic_subscription_id, tenant_id, "
                "period, amount, payment_id, payment_status, idempotency_key) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), now()::date, 100, "
                "gen_random_uuid(), 'pending', 'k1')"
            )
        )

    await migrator.downgrade("0007")

    assert not NEW_TABLES & await tables(engine)

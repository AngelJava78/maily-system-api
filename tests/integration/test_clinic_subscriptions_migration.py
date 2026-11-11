"""The 0005 migration creates and undoes the clinic subscriptions schema (Principle VI, spec 006)."""

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


NEW_TABLES = {"clinic_subscription_statuses", "clinic_subscriptions", "clinic_subscription_charges"}


async def test_upgrade_to_0005_creates_the_schema_and_seeds_the_three_statuses(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("0004")
    await migrator.upgrade("0005")

    assert NEW_TABLES <= await tables(engine)
    statuses = await fetch_all(engine, "SELECT id, name FROM clinic_subscription_statuses ORDER BY id")
    assert statuses == [(1, "Activa"), (2, "Con cobro pendiente de resolver"), (3, "Cancelada")]
    assert "clinic_subscriptions_one_active_per_tenant_key" in await names(
        engine, "SELECT indexname FROM pg_indexes WHERE tablename = 'clinic_subscriptions'"
    )
    assert "clinic_subscription_charges_one_per_period_key" in await names(
        engine, "SELECT indexname FROM pg_indexes WHERE tablename = 'clinic_subscription_charges'"
    )
    triggers = await names(engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    assert {"clinic_subscriptions_set_updated_at", "clinic_subscription_charges_set_updated_at"} <= triggers


async def test_downgrade_to_0004_removes_the_three_tables_and_their_triggers(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0004")

    assert not NEW_TABLES & await tables(engine)
    triggers = await names(engine, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    assert "clinic_subscriptions_set_updated_at" not in triggers
    assert "clinic_subscription_charges_set_updated_at" not in triggers
    # set_updated_at() itself is reused from migration 0001: it must survive.
    assert "set_updated_at" in await names(engine, "SELECT proname FROM pg_proc")


async def test_the_migration_is_reversible_and_repeatable(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("0004")
    await migrator.upgrade("0005")
    await migrator.downgrade("0004")
    await migrator.upgrade("0005")

    assert NEW_TABLES <= await tables(engine)


async def test_downgrade_with_existing_rows_does_not_fail(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    """Uses real (committed) rows, not the rolled-back `db_session` savepoint: `engine`/`migrator`
    are session-scoped and alembic runs outside this test's transaction. Downgrading to 0004 drops
    `clinic_subscriptions`/`clinic_subscription_charges` (and their rows) along with the tables,
    but `subscriptions` itself (from migration 0001) survives at 0004, so its row is deleted
    explicitly in `finally` — leaving it behind would corrupt the shared test database for every
    later test and session (as `migrated_db`'s own `downgrade("base")` would then fail trying to
    seed-delete statuses still referenced by this leftover row).
    """
    await migrator.upgrade("head")
    subscription_id: int | None = None
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "INSERT INTO subscriptions (name, monthly_price, annual_price, consulting_rooms_limit, "
                    "doctors_limit, assistants_limit, new_patients_per_year_limit) "
                    "VALUES ('Pro-migracion-006', 100, 1000, 1, 1, 1, 100) RETURNING id"
                )
            )
            [(subscription_id,)] = result.fetchall()
            result = await connection.execute(
                text(
                    "INSERT INTO clinic_subscriptions (tenant_id, subscription_id, billing_cycle, "
                    "started_at, next_billing_at) VALUES (gen_random_uuid(), :sid, 'monthly', now(), now()) "
                    "RETURNING id"
                ),
                {"sid": subscription_id},
            )
            [(clinic_subscription_id,)] = result.fetchall()
            await connection.execute(
                text(
                    "INSERT INTO clinic_subscription_charges (clinic_subscription_id, period, amount, "
                    "payment_id, payment_status, idempotency_key) "
                    "VALUES (:csid, now()::date, 100, gen_random_uuid(), 'pending', 'k1')"
                ),
                {"csid": clinic_subscription_id},
            )

        await migrator.downgrade("0004")

        assert not NEW_TABLES & await tables(engine)
    finally:
        # `clinic_subscriptions`/`clinic_subscription_charges` were dropped (and their rows with
        # them) by the downgrade above; only the `subscriptions` row survived it and needs
        # deleting by hand, after `restore_head` (below) brings that table back for the rest of
        # the session to use normally.
        if subscription_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM subscriptions WHERE id = :sid"), {"sid": subscription_id}
                )

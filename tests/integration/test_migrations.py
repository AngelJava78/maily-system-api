"""Las migraciones crean y deshacen el esquema (Principio VI)."""

import pytest
from sqlalchemy import text
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

    assert {"subscription_statuses", "subscription_types", "subscriptions"} <= await tables(engine)
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

    assert not {"subscription_statuses", "subscription_types", "subscriptions"} & await tables(engine)
    assert "set_updated_at" not in await names(engine, "SELECT proname FROM pg_proc")


async def test_the_migrations_are_reversible_and_repeatable(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert {"subscription_statuses", "subscription_types", "subscriptions"} <= await tables(engine)


async def test_downgrading_only_the_seed_leaves_the_status_table_empty(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0001")

    assert {"subscription_statuses", "subscriptions"} <= await tables(engine)
    assert await fetch_all(engine, "SELECT id FROM subscription_statuses") == []


async def columns(engine: AsyncEngine, table: str) -> set[str]:
    return await names(
        engine,
        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'",
    )


async def test_upgrade_to_0003_adds_the_new_subscription_columns(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    subscription_columns = await columns(engine, "subscriptions")
    assert subscription_columns >= {
        "annual_price",
        "trial_days",
        "self_service",
        "other_features",
        "consulting_rooms_limit",
        "doctors_limit",
        "assistants_limit",
        "new_patients_per_year_limit",
    }
    assert "features" not in subscription_columns
    # module_keys was one of 0003's columns too, but 0007 (spec 008) moves it out of this table
    # into subscription_modules: it is not expected at head any more, see test_upgrade_to_0007_*.


async def test_downgrade_to_0002_removes_the_new_subscription_columns(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0002")

    subscription_columns = await columns(engine, "subscriptions")
    assert "features" in subscription_columns
    assert not subscription_columns & {
        "annual_price",
        "trial_days",
        "self_service",
        "module_keys",
        "other_features",
        "consulting_rooms_limit",
        "doctors_limit",
        "assistants_limit",
        "new_patients_per_year_limit",
    }


async def test_upgrade_to_0005_creates_the_catalog_seeded_and_the_subscription_column(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert "subscription_type_id" in await columns(engine, "subscriptions")
    assert await fetch_all(
        engine, "SELECT id, name FROM subscription_types ORDER BY id"
    ) == [(1, "Individual"), (2, "Empresarial")]


async def test_downgrade_to_0004_removes_the_catalog_and_the_subscription_column(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0004")

    assert "subscription_type_id" not in await columns(engine, "subscriptions")
    assert "subscription_types" not in await tables(engine)


async def test_the_default_assigns_individual_to_rows_that_existed_before_0005(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    """FR-001/FR-008: no subscription ever goes without a type, not even one already on disk."""
    await migrator.downgrade("base")
    await migrator.upgrade("0004")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO subscriptions (name, monthly_price, annual_price, "
                    "consulting_rooms_limit, doctors_limit, assistants_limit, "
                    "new_patients_per_year_limit) VALUES ('Previa', 1, 1, 1, 1, 1, 100)"
                )
            )

        await migrator.upgrade("0005")

        assert await fetch_all(
            engine, "SELECT subscription_type_id FROM subscriptions WHERE name = 'Previa'"
        ) == [(1,)]
    finally:
        # The row survives `restore_head` (which only brings the schema back, not the data): other
        # tests in this session assume the table starts empty.
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM subscriptions WHERE name = 'Previa'"))


async def test_upgrade_to_0006_adds_the_clinics_limit_column(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert "clinics_limit" in await columns(engine, "subscriptions")


async def test_downgrade_to_0005_removes_the_clinics_limit_column(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0005")

    assert "clinics_limit" not in await columns(engine, "subscriptions")


async def test_upgrade_to_0007_moves_modules_into_their_own_table(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.downgrade("base")
    await migrator.upgrade("head")

    assert "module_keys" not in await columns(engine, "subscriptions")
    assert "subscription_modules" in await tables(engine)
    assert await columns(engine, "subscription_modules") == {"subscription_id", "module_key"}


async def test_downgrade_to_0006_restores_module_keys_and_drops_the_table(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0006")

    assert "module_keys" in await columns(engine, "subscriptions")
    assert "subscription_modules" not in await tables(engine)


async def test_0007_migrates_existing_modules_without_losing_or_adding_any(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    """FR-003/SC-002: no subscription gains or loses a module when this migration runs."""
    await migrator.downgrade("base")
    await migrator.upgrade("0006")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO subscriptions (name, monthly_price, annual_price, "
                    "consulting_rooms_limit, doctors_limit, assistants_limit, "
                    "new_patients_per_year_limit, module_keys) VALUES "
                    "('SoloPacientes', 1, 1, 1, 1, 1, 100, ARRAY['patients']), "
                    "('ConAgenda', 1, 1, 1, 1, 1, 100, ARRAY['patients', 'scheduling']), "
                    "('ConTresModulos', 1, 1, 1, 1, 1, 100, "
                    "ARRAY['billing', 'finance', 'patients'])"
                )
            )

        await migrator.upgrade("0007")

        rows = await fetch_all(
            engine,
            "SELECT s.name, m.module_key FROM subscriptions s "
            "JOIN subscription_modules m ON m.subscription_id = s.id "
            "WHERE s.name IN ('SoloPacientes', 'ConAgenda', 'ConTresModulos') "
            "ORDER BY s.name, m.module_key",
        )
        assert rows == [
            ("ConAgenda", "patients"),
            ("ConAgenda", "scheduling"),
            ("ConTresModulos", "billing"),
            ("ConTresModulos", "finance"),
            ("ConTresModulos", "patients"),
            ("SoloPacientes", "patients"),
        ]

        await migrator.downgrade("0006")

        reverted = await fetch_all(
            engine,
            "SELECT name, module_keys FROM subscriptions "
            "WHERE name IN ('SoloPacientes', 'ConAgenda', 'ConTresModulos') ORDER BY name",
        )
        assert reverted == [
            ("ConAgenda", ["patients", "scheduling"]),
            ("ConTresModulos", ["billing", "finance", "patients"]),
            ("SoloPacientes", ["patients"]),
        ]
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM subscriptions WHERE name IN "
                    "('SoloPacientes', 'ConAgenda', 'ConTresModulos')"
                )
            )


async def test_the_default_assigns_one_to_rows_that_existed_before_0006(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    """FR-007: 1 is valid for Individual (the only value it allows) and for Empresarial (the
    lowest of its 1-100 range), so no pre-existing row, of either type, needs a guess."""
    await migrator.downgrade("base")
    await migrator.upgrade("0005")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO subscriptions (name, subscription_type_id, monthly_price, "
                    "annual_price, consulting_rooms_limit, doctors_limit, assistants_limit, "
                    "new_patients_per_year_limit) VALUES "
                    "('PreviaIndividual', 1, 1, 1, 1, 1, 1, 100), "
                    "('PreviaEmpresarial', 2, 1, 1, 1, 1, 1, 100)"
                )
            )

        await migrator.upgrade("0006")

        assert await fetch_all(
            engine,
            "SELECT name, clinics_limit FROM subscriptions "
            "WHERE name IN ('PreviaIndividual', 'PreviaEmpresarial') ORDER BY name",
        ) == [("PreviaEmpresarial", 1), ("PreviaIndividual", 1)]
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM subscriptions WHERE name IN "
                    "('PreviaIndividual', 'PreviaEmpresarial')"
                )
            )

"""SubscriptionRepository against a real PostgreSQL 17 (Principle V)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.models.subscription import SUBSCRIPTION_NAME_INDEX
from src.repositories import INT4_MAX
from src.repositories.errors import UniqueViolationError
from src.repositories.subscription_repository import SubscriptionRepository
from tests.helpers import insert_subscription

MOMENT = datetime(2026, 1, 1, tzinfo=UTC)


async def add_hand_made_status(session: AsyncSession) -> None:
    await session.execute(
        text("INSERT INTO subscription_statuses (id, name) VALUES (5, 'Manual')")
    )
    await session.commit()


# --- US1: list_current ---


async def test_list_current_returns_statuses_1_2_3_and_the_ones_added_by_hand(
    db_session: AsyncSession,
):
    await add_hand_made_status(db_session)
    for status in (1, 2, 3, 5):
        await insert_subscription(db_session, name=f"S{status}", status_id=status)

    names = [s.name for s in await SubscriptionRepository(db_session).list_current()]

    assert sorted(names) == ["S1", "S2", "S3", "S5"]


async def test_list_current_excludes_the_deleted_ones(db_session: AsyncSession):
    await insert_subscription(db_session, name="Vigente")
    await insert_subscription(db_session, name="Eliminada", status_id=4)

    names = [s.name for s in await SubscriptionRepository(db_session).list_current()]

    assert names == ["Vigente"]


async def test_list_current_is_empty_when_all_are_deleted_or_there_are_none(
    db_session: AsyncSession,
):
    repository = SubscriptionRepository(db_session)
    assert await repository.list_current() == []

    await insert_subscription(db_session, name="Solo eliminada", status_id=4)

    assert await repository.list_current() == []


async def test_list_current_orders_by_creation_date_then_by_id(db_session: AsyncSession):
    later = await insert_subscription(db_session, name="Tarde", created_at=MOMENT + timedelta(days=1))
    first = await insert_subscription(db_session, name="B", created_at=MOMENT)
    second = await insert_subscription(db_session, name="A", created_at=MOMENT)
    third = await insert_subscription(db_session, name="C", created_at=MOMENT)

    ordered = [s.id for s in await SubscriptionRepository(db_session).list_current()]

    # Same creation date -> by id (not by name); the older creation date goes first.
    assert ordered == [first, second, third, later]


async def test_list_current_loads_the_status_together_with_each_subscription(
    db_session: AsyncSession,
):
    await insert_subscription(db_session, name="Con estatus", status_id=2)

    (subscription,) = await SubscriptionRepository(db_session).list_current()

    # `lazy="raise"`: this would fail if the status had not been loaded with the query.
    assert (subscription.status.id, subscription.status.name) == (2, "Inactiva")


# --- US3: create ---


async def test_create_inserts_an_active_subscription_and_returns_it_reloaded(
    db_session: AsyncSession,
):
    repository = SubscriptionRepository(db_session)

    created = await repository.create(
        "Pro", "Para clínicas", Decimal("4500"), ["Hasta 5 consultorios", "Usuarios ilimitados"]
    )

    assert created.id >= 1
    assert created.status_id == 1
    assert (created.status.id, created.status.name) == (1, "Activa")
    assert created.monthly_price == Decimal("4500.00")  # two decimals even if sent without them
    assert str(created.monthly_price) == "4500.00"
    assert created.features == ["Hasta 5 consultorios", "Usuarios ilimitados"]  # same order
    assert created.description == "Para clínicas"
    assert created.created_at == created.updated_at


async def test_create_without_description_stores_none(db_session: AsyncSession):
    created = await SubscriptionRepository(db_session).create("Legacy", None, Decimal("0"), [])

    assert created.description is None
    assert created.features == []
    assert created.monthly_price == Decimal("0.00")


async def test_a_repeated_name_with_other_capitals_is_a_unique_violation_of_the_name_index(
    db_session: AsyncSession,
):
    repository = SubscriptionRepository(db_session)
    await repository.create("Pro", None, Decimal("1"), [])

    with pytest.raises(UniqueViolationError) as error:
        await repository.create("pro", None, Decimal("1"), [])

    assert error.value.constraint_name == SUBSCRIPTION_NAME_INDEX


async def test_the_name_of_a_deleted_subscription_can_be_reused(db_session: AsyncSession):
    await insert_subscription(db_session, name="Solo", status_id=4)

    created = await SubscriptionRepository(db_session).create("Solo", None, Decimal("900"), [])

    assert created.name == "Solo"


async def test_fifty_simultaneous_creations_with_the_same_name_produce_exactly_one(
    engine: AsyncEngine, migrated_db: None
):
    async def attempt() -> bool:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                await SubscriptionRepository(session).create("Carrera", None, Decimal("1"), [])
            except UniqueViolationError:
                return False
            return True

    try:
        results = await asyncio.gather(*(attempt() for _ in range(50)))
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscriptions RESTART IDENTITY CASCADE"))

    assert results.count(True) == 1
    assert results.count(False) == 49


# --- US4: get_current_by_id ---


@pytest.mark.parametrize("status_id", [1, 2, 3, 5])
async def test_get_current_by_id_finds_a_current_subscription_with_its_status(
    db_session: AsyncSession, status_id: int
):
    await add_hand_made_status(db_session)
    subscription_id = await insert_subscription(db_session, name="Plan", status_id=status_id)

    found = await SubscriptionRepository(db_session).get_current_by_id(subscription_id)

    assert found is not None
    assert found.status.id == status_id  # `lazy="raise"`: it was loaded with the query


async def test_get_current_by_id_does_not_find_a_deleted_or_missing_subscription(
    db_session: AsyncSession,
):
    deleted = await insert_subscription(db_session, name="Eliminada", status_id=4)
    repository = SubscriptionRepository(db_session)

    assert await repository.get_current_by_id(deleted) is None
    assert await repository.get_current_by_id(deleted + 1000) is None


class ForbiddenSession:
    """A session that fails the test if anything is asked of it."""

    def __getattr__(self, name):
        raise AssertionError(f"the database must not be queried (session.{name})")


async def test_an_identifier_above_int4_is_not_found_without_querying_the_database():
    repository = SubscriptionRepository(ForbiddenSession())

    assert await repository.get_current_by_id(INT4_MAX + 1) is None


# --- US5: update ---


async def test_update_changes_only_the_given_columns_and_returns_the_reloaded_row(
    committing_session: AsyncSession,
):
    subscription_id = await insert_subscription(
        committing_session,
        name="Pro",
        monthly_price="4500",
        description="Para clínicas",
        features=["Uno", "Dos"],
    )
    repository = SubscriptionRepository(committing_session)

    updated = await repository.update(subscription_id, {"monthly_price": Decimal("4700")})

    assert updated is not None
    assert updated.monthly_price == Decimal("4700.00")
    assert (updated.name, updated.description, updated.features) == ("Pro", "Para clínicas", ["Uno", "Dos"])
    assert updated.status.name == "Activa"
    assert updated.updated_at > updated.created_at  # the trigger kept the modification date


async def test_update_can_clear_the_description_and_the_features(db_session: AsyncSession):
    subscription_id = await insert_subscription(
        db_session, name="Pro", description="Antes", features=["Uno"]
    )

    updated = await SubscriptionRepository(db_session).update(
        subscription_id, {"description": None, "features": []}
    )

    assert (updated.description, updated.features) == (None, [])


async def test_update_may_rename_a_subscription_with_other_capitals_of_its_own_name(
    db_session: AsyncSession,
):
    subscription_id = await insert_subscription(db_session, name="Pro")

    updated = await SubscriptionRepository(db_session).update(subscription_id, {"name": "PRO"})

    assert updated.name == "PRO"


async def test_update_to_the_name_of_another_current_subscription_is_a_unique_violation(
    db_session: AsyncSession,
):
    await insert_subscription(db_session, name="Pro")
    other = await insert_subscription(db_session, name="Básico")

    with pytest.raises(UniqueViolationError) as error:
        await SubscriptionRepository(db_session).update(other, {"name": "pro"})

    assert error.value.constraint_name == SUBSCRIPTION_NAME_INDEX


async def test_update_of_a_deleted_or_missing_subscription_changes_nothing(
    db_session: AsyncSession,
):
    deleted = await insert_subscription(db_session, name="Eliminada", status_id=4)
    repository = SubscriptionRepository(db_session)

    assert await repository.update(deleted, {"name": "Nueva"}) is None
    assert await repository.update(deleted + 1000, {"name": "Nueva"}) is None
    name = (await db_session.execute(text("SELECT name FROM subscriptions"))).scalar_one()
    assert name == "Eliminada"


async def test_update_of_an_identifier_above_int4_does_not_query_the_database():
    repository = SubscriptionRepository(ForbiddenSession())

    assert await repository.update(INT4_MAX + 1, {"name": "X"}) is None


# --- US6: change_status and get_status_id ---


MOVES = [(current, target) for current in (1, 2, 3, 5) for target in (1, 2, 3) if current != target]


@pytest.mark.parametrize(("current", "target"), MOVES)
async def test_change_status_moves_between_manageable_statuses(
    db_session: AsyncSession, current: int, target: int
):
    await add_hand_made_status(db_session)
    subscription_id = await insert_subscription(db_session, name="Plan", status_id=current)

    changed = await SubscriptionRepository(db_session).change_status(subscription_id, target)

    assert changed is not None
    assert (changed.status_id, changed.status.id) == (target, target)  # reloaded with its status


@pytest.mark.parametrize("status_id", [1, 2, 3])
async def test_change_status_to_the_same_status_changes_nothing(
    db_session: AsyncSession, status_id: int
):
    subscription_id = await insert_subscription(db_session, name="Plan", status_id=status_id)

    assert await SubscriptionRepository(db_session).change_status(subscription_id, status_id) is None


async def test_change_status_of_a_deleted_or_missing_subscription_returns_none(
    db_session: AsyncSession,
):
    deleted = await insert_subscription(db_session, name="Eliminada", status_id=4)
    repository = SubscriptionRepository(db_session)

    assert await repository.change_status(deleted, 1) is None
    assert await repository.change_status(deleted + 1000, 1) is None
    status = (await db_session.execute(text("SELECT status_id FROM subscriptions"))).scalar_one()
    assert status == 4


async def test_change_status_of_an_identifier_above_int4_does_not_query_the_database():
    assert await SubscriptionRepository(ForbiddenSession()).change_status(INT4_MAX + 1, 1) is None
    assert await SubscriptionRepository(ForbiddenSession()).get_status_id(INT4_MAX + 1) is None


async def test_get_status_id_sees_every_subscription_even_a_deleted_one(db_session: AsyncSession):
    active = await insert_subscription(db_session, name="Activa", status_id=1)
    deleted = await insert_subscription(db_session, name="Eliminada", status_id=4)
    repository = SubscriptionRepository(db_session)

    assert await repository.get_status_id(active) == 1
    assert await repository.get_status_id(deleted) == 4
    assert await repository.get_status_id(deleted + 1000) is None


async def test_change_status_moves_the_modification_date(committing_session: AsyncSession):
    subscription_id = await insert_subscription(committing_session, name="Plan")

    changed = await SubscriptionRepository(committing_session).change_status(subscription_id, 2)

    assert changed.updated_at > changed.created_at


async def test_two_simultaneous_changes_to_the_same_status_let_exactly_one_win(
    engine: AsyncEngine, migrated_db: None
):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        subscription_id = await insert_subscription(session, name="Carrera")

    async def attempt() -> bool:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            changed = await SubscriptionRepository(session).change_status(subscription_id, 2)
            return changed is not None

    try:
        results = await asyncio.gather(*(attempt() for _ in range(10)))
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscriptions RESTART IDENTITY CASCADE"))

    assert results.count(True) == 1


# --- US7: soft_delete ---


async def test_soft_delete_marks_the_subscription_deleted_and_keeps_the_row(
    committing_session: AsyncSession,
):
    subscription_id = await insert_subscription(
        committing_session, name="Pro", monthly_price="4500", features=["Uno"]
    )
    repository = SubscriptionRepository(committing_session)

    assert await repository.soft_delete(subscription_id) is True

    row = (
        await committing_session.execute(
            text("SELECT name, monthly_price, features, status_id, updated_at > created_at FROM subscriptions")
        )
    ).one()
    assert tuple(row) == ("Pro", Decimal("4500.00"), ["Uno"], 4, True)  # kept, modification date moved
    assert await repository.list_current() == []
    assert await repository.get_current_by_id(subscription_id) is None


async def test_soft_delete_of_a_deleted_or_missing_subscription_returns_false(
    db_session: AsyncSession,
):
    deleted = await insert_subscription(db_session, name="Eliminada", status_id=4)
    repository = SubscriptionRepository(db_session)

    assert await repository.soft_delete(deleted) is False
    assert await repository.soft_delete(deleted + 1000) is False


async def test_soft_delete_of_an_identifier_above_int4_does_not_query_the_database():
    assert await SubscriptionRepository(ForbiddenSession()).soft_delete(INT4_MAX + 1) is False


async def test_the_name_of_a_deleted_subscription_can_be_used_by_a_new_one(
    db_session: AsyncSession,
):
    subscription_id = await insert_subscription(db_session, name="Solo")
    repository = SubscriptionRepository(db_session)
    await repository.soft_delete(subscription_id)

    created = await repository.create("Solo", None, Decimal("900"), [])

    assert created.id != subscription_id


async def test_two_simultaneous_deletions_let_exactly_one_win(
    engine: AsyncEngine, migrated_db: None
):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        subscription_id = await insert_subscription(session, name="Carrera")

    async def attempt() -> bool:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await SubscriptionRepository(session).soft_delete(subscription_id)

    try:
        results = await asyncio.gather(*(attempt() for _ in range(10)))
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscriptions RESTART IDENTITY CASCADE"))

    assert results.count(True) == 1

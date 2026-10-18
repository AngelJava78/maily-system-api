"""Restricciones del esquema (data-model.md): CHECK, claves foráneas, unicidad y `updated_at`."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import assert_pg_error

INSERT = "INSERT INTO subscriptions (name, monthly_price, status_id) VALUES (:name, :price, :status)"


async def add(session: AsyncSession, name: str, price: str = "100", status: int = 1) -> None:
    await session.execute(
        text(INSERT), {"name": name, "price": Decimal(price), "status": status}
    )


async def add_and_commit(session: AsyncSession, name: str, price: str = "100", status: int = 1):
    await add(session, name, price, status)
    await session.commit()  # libera el SAVEPOINT: lo que falle después no deshace esto


@pytest.mark.parametrize(
    ("name", "price", "status", "sqlstate", "constraint"),
    [
        ("   ", "1", 1, "23514", "subscriptions_name_check"),
        ("Neg", "-1", 1, "23514", "subscriptions_monthly_price_check"),
        ("Huge", "100000000", 1, "22003", None),
        ("Status", "1", 99, "23503", "subscriptions_status_id_fkey"),
    ],
)
async def test_each_restriction_rejects_its_invalid_row(
    db_session: AsyncSession, name, price, status, sqlstate, constraint
):
    with pytest.raises(DBAPIError) as error:
        await add(db_session, name, price, status)

    assert_pg_error(error, sqlstate, constraint=constraint)


async def test_more_than_twenty_features_are_rejected(db_session: AsyncSession):
    features = [f"f{n}" for n in range(21)]

    with pytest.raises(DBAPIError) as error:
        await db_session.execute(
            text("INSERT INTO subscriptions (name, monthly_price, features) VALUES ('Muchas', 1, :f)"),
            {"f": features},
        )

    assert_pg_error(error, "23514", constraint="subscriptions_features_check")


async def test_twenty_features_are_accepted(db_session: AsyncSession):
    await db_session.execute(
        text("INSERT INTO subscriptions (name, monthly_price, features) VALUES ('Veinte', 1, :f)"),
        {"f": [f"f{n}" for n in range(20)]},
    )


@pytest.mark.parametrize(("first", "second"), [("Pro", "pro"), ("Básico", "BÁSICO"), ("Pro", "PRO")])
async def test_the_name_is_unique_ignoring_case_and_accents_in_capitals(
    db_session: AsyncSession, first: str, second: str
):
    await add_and_commit(db_session, first)

    with pytest.raises(DBAPIError) as error:
        await add(db_session, second)

    assert_pg_error(error, "23505", constraint="subscriptions_name_not_deleted_key")


async def test_the_name_of_a_deleted_subscription_is_free(db_session: AsyncSession):
    await add_and_commit(db_session, "Solo", status=4)
    await add_and_commit(db_session, "solo", status=4)  # varias eliminadas pueden compartir nombre

    await add(db_session, "SOLO")  # y una vigente puede usarlo

    count = (await db_session.execute(text("SELECT count(*) FROM subscriptions"))).scalar_one()
    assert count == 3


@pytest.mark.parametrize("status", [2, 3])
async def test_an_inactive_or_blocked_subscription_keeps_its_name_reserved(
    db_session: AsyncSession, status: int
):
    await add_and_commit(db_session, "Legacy", status=status)

    with pytest.raises(DBAPIError) as error:
        await add(db_session, "legacy")

    assert_pg_error(error, "23505", constraint="subscriptions_name_not_deleted_key")


async def test_a_subscription_can_be_renamed_with_other_capitals_of_its_own_name(
    db_session: AsyncSession,
):
    await add_and_commit(db_session, "Pro")

    await db_session.execute(text("UPDATE subscriptions SET name = 'PRO' WHERE name = 'Pro'"))


async def test_a_price_without_decimals_is_read_with_two(db_session: AsyncSession):
    await add_and_commit(db_session, "Precio", "4500")

    price = (await db_session.execute(text("SELECT monthly_price FROM subscriptions"))).scalar_one()

    assert price == Decimal("4500.00")
    assert str(price) == "4500.00"


async def read_dates(session: AsyncSession) -> tuple[datetime, datetime]:
    row = (await session.execute(text("SELECT created_at, updated_at FROM subscriptions"))).one()
    return row[0], row[1]


async def test_updated_at_changes_with_any_update(committing_session: AsyncSession):
    # Cada commit es real: `CURRENT_TIMESTAMP` es la hora de inicio de la transacción.
    await add_and_commit(committing_session, "Fechas")
    created, updated = await read_dates(committing_session)
    assert created == updated

    await committing_session.execute(text("UPDATE subscriptions SET monthly_price = 200"))
    await committing_session.commit()
    _, after_price_change = await read_dates(committing_session)
    assert after_price_change > updated

    await committing_session.execute(text("UPDATE subscriptions SET status_id = 2"))
    await committing_session.commit()
    _, after_status_change = await read_dates(committing_session)
    assert after_status_change > after_price_change

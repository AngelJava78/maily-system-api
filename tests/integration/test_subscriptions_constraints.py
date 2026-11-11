"""Restricciones del esquema (data-model.md): CHECK, claves foráneas, unicidad y `updated_at`."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import assert_pg_error

INSERT = """
INSERT INTO subscriptions (
    name, monthly_price, annual_price, consulting_rooms_limit, doctors_limit, assistants_limit,
    new_patients_per_year_limit, status_id
) VALUES (:name, :price, 1, 1, 1, 1, 100, :status)
"""


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


# Valores base que satisfacen todas las columnas obligatorias nuevas (sin DEFAULT); cada prueba
# sustituye solo la que quiere poner fuera de rango.
BASE_COLUMNS: dict[str, object] = {
    "monthly_price": Decimal("1"),
    "annual_price": Decimal("1"),
    "consulting_rooms_limit": 1,
    "doctors_limit": 1,
    "assistants_limit": 1,
    "new_patients_per_year_limit": 100,
}


async def insert_with(session: AsyncSession, name: str, **overrides: object) -> None:
    values = {**BASE_COLUMNS, **overrides, "name": name}
    columns = ", ".join(values)
    placeholders = ", ".join(f":{column}" for column in values)
    await session.execute(
        text(f"INSERT INTO subscriptions ({columns}) VALUES ({placeholders})"), values
    )


async def test_more_than_twenty_other_features_are_rejected(db_session: AsyncSession):
    with pytest.raises(DBAPIError) as error:
        await insert_with(db_session, "Muchas", other_features=[f"f{n}" for n in range(21)])

    assert_pg_error(error, "23514", constraint="subscriptions_other_features_check")


async def test_twenty_other_features_are_accepted(db_session: AsyncSession):
    await insert_with(db_session, "Veinte", other_features=[f"f{n}" for n in range(20)])


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("annual_price", Decimal("-1"), "subscriptions_annual_price_check"),
        ("trial_days", -1, "subscriptions_trial_days_check"),
        ("trial_days", 3651, "subscriptions_trial_days_check"),
        ("consulting_rooms_limit", -1, "subscriptions_consulting_rooms_limit_check"),
        ("consulting_rooms_limit", 1000001, "subscriptions_consulting_rooms_limit_check"),
        ("doctors_limit", -1, "subscriptions_doctors_limit_check"),
        ("doctors_limit", 1000001, "subscriptions_doctors_limit_check"),
        ("assistants_limit", -1, "subscriptions_assistants_limit_check"),
        ("assistants_limit", 1000001, "subscriptions_assistants_limit_check"),
        ("new_patients_per_year_limit", -1, "subscriptions_new_patients_per_year_limit_check"),
        ("new_patients_per_year_limit", 1000001, "subscriptions_new_patients_per_year_limit_check"),
    ],
)
async def test_each_new_column_rejects_a_value_outside_its_range(
    db_session: AsyncSession, column: str, value: object, constraint: str
):
    with pytest.raises(DBAPIError) as error:
        await insert_with(db_session, "Fuera de rango", **{column: value})

    assert_pg_error(error, "23514", constraint=constraint)


async def test_a_subscription_type_id_that_does_not_exist_in_the_catalog_is_rejected(
    db_session: AsyncSession,
):
    with pytest.raises(DBAPIError) as error:
        await insert_with(db_session, "Tipo invalido", subscription_type_id=99)

    assert_pg_error(error, "23503", constraint="subscriptions_subscription_type_id_fkey")


@pytest.mark.parametrize("value", [1, 2])
async def test_subscription_type_id_individual_and_enterprise_are_accepted(
    db_session: AsyncSession, value: int
):
    await insert_with(db_session, "Tipo valido", subscription_type_id=value)


async def test_subscription_type_id_defaults_to_individual_when_omitted(db_session: AsyncSession):
    await insert_with(db_session, "Sin tipo")

    value = (
        await db_session.execute(
            text("SELECT subscription_type_id FROM subscriptions WHERE name = 'Sin tipo'")
        )
    ).scalar_one()
    assert value == 1


@pytest.mark.parametrize(
    ("subscription_type_id", "clinics_limit"),
    [
        (1, 2),  # Individual MUST be exactly 1
        (1, 0),
        (1, 100),  # valid for a non-Individual, not for this one
        (2, 0),
        (2, 101),
    ],
)
async def test_clinics_limit_outside_its_rule_for_the_type_is_rejected(
    db_session: AsyncSession, subscription_type_id: int, clinics_limit: int
):
    with pytest.raises(DBAPIError) as error:
        await insert_with(
            db_session,
            "Limite invalido",
            subscription_type_id=subscription_type_id,
            clinics_limit=clinics_limit,
        )

    assert_pg_error(error, "23514", constraint="subscriptions_clinics_limit_check")


@pytest.mark.parametrize(
    ("subscription_type_id", "clinics_limit"),
    [(1, 1), (2, 1), (2, 50), (2, 100)],
)
async def test_clinics_limit_matching_its_rule_for_the_type_is_accepted(
    db_session: AsyncSession, subscription_type_id: int, clinics_limit: int
):
    await insert_with(
        db_session,
        "Limite valido",
        subscription_type_id=subscription_type_id,
        clinics_limit=clinics_limit,
    )


async def test_clinics_limit_defaults_to_one_when_omitted(db_session: AsyncSession):
    await insert_with(db_session, "Sin limite de clinicas")

    value = (
        await db_session.execute(
            text("SELECT clinics_limit FROM subscriptions WHERE name = 'Sin limite de clinicas'")
        )
    ).scalar_one()
    assert value == 1


async def test_trial_days_zero_and_the_default_are_accepted(db_session: AsyncSession):
    await insert_with(db_session, "Sin prueba", trial_days=0)
    await insert_with(db_session, "Por defecto")  # trial_days toma su DEFAULT (0)


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


async def test_a_duplicate_module_for_the_same_subscription_is_rejected(db_session: AsyncSession):
    await insert_with(db_session, "Con modulo")
    subscription_id = (
        await db_session.execute(text("SELECT id FROM subscriptions WHERE name = 'Con modulo'"))
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO subscription_modules (subscription_id, module_key) "
            "VALUES (:id, 'scheduling')"
        ),
        {"id": subscription_id},
    )
    await db_session.commit()  # libera el SAVEPOINT: lo que falle después no deshace esto

    with pytest.raises(DBAPIError) as error:
        await db_session.execute(
            text(
                "INSERT INTO subscription_modules (subscription_id, module_key) "
                "VALUES (:id, 'scheduling')"
            ),
            {"id": subscription_id},
        )

    assert_pg_error(error, "23505", constraint="subscription_modules_pkey")


async def test_a_module_for_a_subscription_that_does_not_exist_is_rejected(
    db_session: AsyncSession,
):
    with pytest.raises(DBAPIError) as error:
        await db_session.execute(
            text(
                "INSERT INTO subscription_modules (subscription_id, module_key) "
                "VALUES (999999, 'scheduling')"
            )
        )

    assert_pg_error(error, "23503", constraint="subscription_modules_subscription_id_fkey")


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

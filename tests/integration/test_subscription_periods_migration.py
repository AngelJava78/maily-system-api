"""Migration 0009 creates and removes the subscription periods and their charges (spec 010, FR-043).

Reproduces `specs/010-subscription-periods/contracts/database-schema.sql`. The function
`set_updated_at()` belongs to migration 0001: 0009 reuses it and its downgrade must not drop it. The
restrictions are tested with direct inserts: the service never writes an invalid row, but the database
must refuse it anyway (Principle VI).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.helpers import Migrator, assert_pg_error, fetch_all

PERIOD_CONSTRAINTS = {
    "subscription_periods_pkey",
    "subscription_periods_trial_ends_check",
    "subscription_periods_paid_until_check",
}
CHARGE_CONSTRAINTS = {
    "subscription_charges_pkey",
    "subscription_charges_organization_id_fkey",
    "subscription_charges_payment_id_key",
    "subscription_charges_terms_attempt_key",
    "subscription_charges_amount_check",
    "subscription_charges_currency_check",
    "subscription_charges_billing_period_check",
    "subscription_charges_attempt_check",
    "subscription_charges_status_check",
    "subscription_charges_closed_reason_check",
    "subscription_charges_resolution_check",
}

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
ORGANIZATION = uuid.UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")


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


def constraints_of(engine: AsyncEngine, table: str):
    return names(engine, f"SELECT conname FROM pg_constraint WHERE conrelid = '{table}'::regclass")


# --- upgrade and downgrade ---


async def test_upgrade_creates_the_tables_their_constraints_the_index_and_the_triggers(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0008")
    await migrator.upgrade("head")

    assert {"subscription_periods", "subscription_charges"} <= await tables(engine)
    assert PERIOD_CONSTRAINTS <= await constraints_of(engine, "subscription_periods")
    assert CHARGE_CONSTRAINTS <= await constraints_of(engine, "subscription_charges")
    [(definition,)] = await fetch_all(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'subscription_charges_pending_idx'",
    )
    assert "organization_id, created_at" in definition
    assert "WHERE ((status)::text = 'pending'::text)" in definition
    [(unique_definition,)] = await fetch_all(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'subscription_charges_pending_terms_key'",
    )
    assert unique_definition.startswith("CREATE UNIQUE INDEX")
    assert "organization_id, settles_due_at, billing_period, amount" in unique_definition
    assert "WHERE ((status)::text = 'pending'::text)" in unique_definition
    assert {"subscription_periods_set_updated_at", "subscription_charges_set_updated_at"} <= await triggers(
        engine
    )


async def test_downgrade_to_0008_removes_both_tables_and_keeps_the_function_of_0001(
    migrator: Migrator, engine: AsyncEngine, restore_head
):
    await migrator.upgrade("head")
    await migrator.downgrade("0008")

    assert not {"subscription_periods", "subscription_charges"} & await tables(engine)
    assert {"subscriptions", "subscription_modules", "monitored_components"} <= await tables(engine)
    assert not {"subscription_periods_set_updated_at", "subscription_charges_set_updated_at"} & await triggers(
        engine
    )
    assert "set_updated_at" in await names(engine, "SELECT proname FROM pg_proc")
    assert "subscriptions_set_updated_at" in await triggers(engine)


async def test_going_up_and_down_is_repeatable(migrator: Migrator, engine: AsyncEngine, restore_head):
    await migrator.upgrade("head")
    for _ in range(2):
        await migrator.downgrade("0008")
        await migrator.upgrade("head")

    assert {"subscription_periods", "subscription_charges"} <= await tables(engine)


async def test_both_tables_start_empty(engine: AsyncEngine, migrated_db: None):
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_periods") == [(0,)]
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges") == [(0,)]


# --- subscription_periods ---

INSERT_PERIOD = """
INSERT INTO subscription_periods (organization_id, started_at, trial_ends_at, paid_until)
VALUES (:organization_id, :started_at, :trial_ends_at, :paid_until)
"""


async def add_period(session: AsyncSession, **overrides: Any) -> None:
    values = {
        "organization_id": ORGANIZATION,
        "started_at": NOW,
        "trial_ends_at": NOW + timedelta(days=14),
        "paid_until": None,
        **overrides,
    }
    await session.execute(text(INSERT_PERIOD), values)


async def test_a_period_gets_its_defaults(db_session: AsyncSession):
    await add_period(db_session, trial_ends_at=None)

    row = (
        await db_session.execute(
            text("SELECT trial_ends_at, paid_until, created_at, updated_at FROM subscription_periods")
        )
    ).one()

    assert row.trial_ends_at is None and row.paid_until is None
    assert row.created_at is not None and row.updated_at is not None


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"trial_ends_at": NOW - timedelta(seconds=1)}, "subscription_periods_trial_ends_check"),
        ({"paid_until": NOW}, "subscription_periods_paid_until_check"),
        ({"paid_until": NOW - timedelta(days=1)}, "subscription_periods_paid_until_check"),
    ],
)
async def test_the_dates_of_a_period_are_kept_in_order(db_session: AsyncSession, overrides, constraint):
    with pytest.raises(DBAPIError) as error:
        await add_period(db_session, **overrides)

    assert_pg_error(error, "23514", constraint=constraint)


async def test_a_trial_that_ends_at_the_start_is_allowed(db_session: AsyncSession):
    await add_period(db_session, trial_ends_at=NOW)  # a zero-length trial is not forbidden


async def test_an_organization_has_one_period(db_session: AsyncSession):
    await add_period(db_session)
    await db_session.commit()

    with pytest.raises(DBAPIError) as error:
        await add_period(db_session)

    assert_pg_error(error, "23505", constraint="subscription_periods_pkey")


# --- subscription_charges ---

INSERT_CHARGE = """
INSERT INTO subscription_charges (
    organization_id, payment_id, amount, currency, billing_period, settles_due_at, attempt,
    status, closed_reason, period_starts_at, period_ends_at, resolved_at
) VALUES (
    :organization_id, :payment_id, :amount, :currency, :billing_period, :settles_due_at, :attempt,
    :status, :closed_reason, :period_starts_at, :period_ends_at, :resolved_at
)
"""


async def add_charge(session: AsyncSession, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "organization_id": ORGANIZATION,
        "payment_id": uuid.uuid4(),
        "amount": Decimal("499.00"),
        "currency": "MXN",
        "billing_period": "monthly",
        "settles_due_at": NOW + timedelta(days=14),
        "attempt": 1,
        "status": "pending",
        "closed_reason": None,
        "period_starts_at": None,
        "period_ends_at": None,
        "resolved_at": None,
        **overrides,
    }
    await session.execute(text(INSERT_CHARGE), values)


async def with_period(session: AsyncSession) -> AsyncSession:
    await add_period(session)
    return session


async def test_a_pending_charge_gets_its_defaults(db_session: AsyncSession):
    await with_period(db_session)
    await db_session.execute(
        text(
            "INSERT INTO subscription_charges (organization_id, payment_id, amount, currency, "
            "billing_period, settles_due_at, attempt) "
            "VALUES (:org, :payment, 499, 'MXN', 'monthly', :due, 1)"
        ),
        {"org": ORGANIZATION, "payment": uuid.uuid4(), "due": NOW},
    )

    row = (
        await db_session.execute(text("SELECT id, status, closed_reason, resolved_at FROM subscription_charges"))
    ).one()

    assert isinstance(row.id, uuid.UUID)
    assert (row.status, row.closed_reason, row.resolved_at) == ("pending", None, None)


@pytest.mark.parametrize(
    ("overrides", "sqlstate", "constraint"),
    [
        ({"amount": Decimal("0")}, "23514", "subscription_charges_amount_check"),
        ({"amount": Decimal("-1")}, "23514", "subscription_charges_amount_check"),
        ({"amount": Decimal("100000000")}, "22003", None),
        ({"currency": "USD"}, "23514", "subscription_charges_currency_check"),
        ({"billing_period": "weekly"}, "23514", "subscription_charges_billing_period_check"),
        ({"attempt": 0}, "23514", "subscription_charges_attempt_check"),
        # An unknown status breaks two checks; PostgreSQL evaluates them in name order, so the
        # resolution one (which lists the three valid statuses) is the one that reports it.
        ({"status": "paid"}, "23514", "subscription_charges_resolution_check"),
        (
            {"status": "closed", "closed_reason": "lost", "resolved_at": NOW},
            "23514",
            "subscription_charges_closed_reason_check",
        ),
        # The status decides which columns carry a value.
        (
            {"status": "applied", "resolved_at": NOW},
            "23514",
            "subscription_charges_resolution_check",
        ),
        (
            {
                "status": "applied",
                "period_starts_at": NOW,
                "period_ends_at": NOW,
                "resolved_at": NOW,
            },
            "23514",
            "subscription_charges_resolution_check",
        ),
        ({"status": "closed", "resolved_at": NOW}, "23514", "subscription_charges_resolution_check"),
        (
            {"status": "closed", "closed_reason": "rejected"},
            "23514",
            "subscription_charges_resolution_check",
        ),
        ({"status": "pending", "resolved_at": NOW}, "23514", "subscription_charges_resolution_check"),
        (
            {"status": "pending", "closed_reason": "rejected"},
            "23514",
            "subscription_charges_resolution_check",
        ),
        (
            {
                "status": "closed",
                "closed_reason": "rejected",
                "period_starts_at": NOW,
                "period_ends_at": NOW + timedelta(days=30),
                "resolved_at": NOW,
            },
            "23514",
            "subscription_charges_resolution_check",
        ),
    ],
)
async def test_each_restriction_rejects_its_invalid_charge(
    db_session: AsyncSession, overrides, sqlstate, constraint
):
    await with_period(db_session)
    await db_session.commit()

    with pytest.raises(DBAPIError) as error:
        await add_charge(db_session, **overrides)

    assert_pg_error(error, sqlstate, constraint=constraint)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {
            "status": "applied",
            "period_starts_at": NOW,
            "period_ends_at": NOW + timedelta(days=30),
            "resolved_at": NOW,
        },
        *[
            {"status": "closed", "closed_reason": reason, "resolved_at": NOW}
            for reason in ("rejected", "cancelled", "inconsistent", "refunded")
        ],
        {"billing_period": "annual", "amount": Decimal("4990.00")},
    ],
)
async def test_the_valid_charges_are_accepted(db_session: AsyncSession, overrides):
    await with_period(db_session)

    await add_charge(db_session, **overrides)


async def test_a_charge_needs_the_period_of_its_organization(db_session: AsyncSession):
    with pytest.raises(DBAPIError) as error:
        await add_charge(db_session)

    assert_pg_error(error, "23503", constraint="subscription_charges_organization_id_fkey")


async def test_a_payment_of_the_payments_api_is_one_single_charge(db_session: AsyncSession):
    await with_period(db_session)
    payment = uuid.uuid4()
    await add_charge(db_session, payment_id=payment)
    await db_session.commit()

    with pytest.raises(DBAPIError) as error:
        await add_charge(db_session, payment_id=payment, amount=Decimal("799.00"))  # other conditions

    assert_pg_error(error, "23505", constraint="subscription_charges_payment_id_key")


REJECTED = {"status": "closed", "closed_reason": "rejected", "resolved_at": NOW}


async def test_the_same_conditions_and_attempt_are_the_same_charge(db_session: AsyncSession):
    await with_period(db_session)
    await add_charge(db_session, **REJECTED)  # resolved: only the attempt can refuse the next one
    await db_session.commit()

    with pytest.raises(DBAPIError) as error:
        await add_charge(db_session)  # another payment, the same conditions and attempt

    assert_pg_error(error, "23505", constraint="subscription_charges_terms_attempt_key")


async def test_two_unresolved_charges_cannot_have_the_same_conditions_whatever_the_attempt(
    db_session: AsyncSession,
):
    await with_period(db_session)
    await add_charge(db_session)
    await db_session.commit()

    with pytest.raises(DBAPIError) as error:
        await add_charge(db_session, attempt=2)  # another payment and attempt, the same period and amount

    assert_pg_error(error, "23505", constraint="subscription_charges_pending_terms_key")


async def test_a_resolved_charge_does_not_stop_the_next_attempt(db_session: AsyncSession):
    await with_period(db_session)
    await add_charge(db_session, **REJECTED)

    await add_charge(db_session, attempt=2)  # the unresolved one that follows the rejected one
    await add_charge(
        db_session,
        attempt=3,
        status="applied",
        period_starts_at=NOW,
        period_ends_at=NOW + timedelta(days=31),
        resolved_at=NOW,
    )


async def test_other_conditions_are_other_charges(db_session: AsyncSession):
    await with_period(db_session)
    await add_charge(db_session)

    await add_charge(db_session, amount=Decimal("799.00"))
    await add_charge(db_session, billing_period="annual")
    await add_charge(db_session, settles_due_at=NOW + timedelta(days=45))


# --- updated_at ---


@pytest.mark.parametrize("table", ["subscription_periods", "subscription_charges"])
async def test_the_trigger_moves_updated_at_on_every_update(
    committing_session: AsyncSession, engine: AsyncEngine, table: str
):
    try:
        await add_period(committing_session)
        if table == "subscription_charges":
            await add_charge(committing_session)
        await committing_session.commit()
        key = "organization_id"
        [(before,)] = await fetch_all(engine, f"SELECT updated_at FROM {table}")

        # CURRENT_TIMESTAMP is the start of the transaction, so the update runs in another one.
        await committing_session.execute(text(f"UPDATE {table} SET created_at = created_at WHERE {key} IS NOT NULL"))
        await committing_session.commit()
        [(after,)] = await fetch_all(engine, f"SELECT updated_at FROM {table}")

        assert after > before
    finally:
        await committing_session.rollback()
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscription_charges, subscription_periods CASCADE"))

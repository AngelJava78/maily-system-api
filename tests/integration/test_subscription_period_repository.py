"""`SubscriptionPeriodRepository` against a real PostgreSQL (spec 010, research R4 and R5).

What must happen exactly once — creating the period of an organization and applying a charge — is
tested with simultaneous requests that use their own session each, as the requests of the service do.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.models.subscription_charge import (
    CHARGE_PAYMENT_ID_KEY,
    CHARGE_PENDING_TERMS_KEY,
    CHARGE_TERMS_ATTEMPT_KEY,
    ChargeStatus,
    ClosedReason,
)
from src.repositories.errors import ForeignKeyViolationError, UniqueViolationError
from src.repositories.subscription_period_repository import ApplyOutcome, SubscriptionPeriodRepository
from tests.helpers import fetch_all

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
TRIAL_END = NOW + timedelta(days=14)
NEXT_DUE = TRIAL_END + timedelta(days=31)  # the period that follows the first one
LAST_DUE = NEXT_DUE + timedelta(days=30)
ORGANIZATION = uuid.UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")
OTHER_ORGANIZATION = uuid.UUID("1f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")
PRICE = Decimal("499.00")


@pytest.fixture(autouse=True)
async def empty_tables(engine: AsyncEngine, migrated_db: None) -> AsyncIterator[None]:
    async def truncate() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscription_charges, subscription_periods CASCADE"))

    await truncate()
    yield
    await truncate()


@asynccontextmanager
async def repository(engine: AsyncEngine) -> AsyncIterator[SubscriptionPeriodRepository]:
    """A repository over a session of its own, like the one of a request."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield SubscriptionPeriodRepository(session)


async def create_period(engine: AsyncEngine, organization_id: uuid.UUID = ORGANIZATION):
    async with repository(engine) as repo:
        return await repo.create_if_absent(organization_id, NOW, TRIAL_END)


async def add_charge(engine: AsyncEngine, **overrides):
    values = {
        "organization_id": ORGANIZATION,
        "payment_id": uuid.uuid4(),
        "amount": PRICE,
        "billing_period": "monthly",
        "settles_due_at": TRIAL_END,
        "attempt": 1,
        **overrides,
    }
    async with repository(engine) as repo:
        return await repo.add_charge(**values)


async def charge_row(engine: AsyncEngine, charge_id: uuid.UUID):
    [row] = await fetch_all(
        engine,
        "SELECT status, closed_reason, period_starts_at, period_ends_at, resolved_at "
        "FROM subscription_charges WHERE id = :id",
        id=charge_id,
    )
    return row


async def paid_until(engine: AsyncEngine, organization_id: uuid.UUID = ORGANIZATION):
    [(value,)] = await fetch_all(
        engine,
        "SELECT paid_until FROM subscription_periods WHERE organization_id = :id",
        id=organization_id,
    )
    return value


async def apply(engine: AsyncEngine, charge_id: uuid.UUID, *, expected=None, start=None, end=None):
    async with repository(engine) as repo:
        return await repo.apply_charge(
            charge_id=charge_id,
            organization_id=ORGANIZATION,
            expected_paid_until=expected,
            period_starts_at=start or TRIAL_END,
            period_ends_at=end or TRIAL_END + timedelta(days=31),
            resolved_at=NOW + timedelta(days=1),
        )


# --- the period ---


async def test_there_is_no_period_until_one_is_created(engine: AsyncEngine):
    async with repository(engine) as repo:
        assert await repo.get(ORGANIZATION) is None


async def test_a_period_is_created_with_its_dates(engine: AsyncEngine):
    period = await create_period(engine)

    assert period.organization_id == ORGANIZATION
    assert (period.started_at, period.trial_ends_at, period.paid_until) == (NOW, TRIAL_END, None)
    assert period.created_at is not None


async def test_a_period_without_a_trial_keeps_its_trial_empty(engine: AsyncEngine):
    async with repository(engine) as repo:
        period = await repo.create_if_absent(ORGANIZATION, NOW, None)

    assert period.trial_ends_at is None


async def test_creating_the_period_again_returns_the_one_that_exists_without_changing_it(engine: AsyncEngine):
    first = await create_period(engine)

    async with repository(engine) as repo:
        again = await repo.create_if_absent(ORGANIZATION, NOW + timedelta(days=3), None)

    assert (again.started_at, again.trial_ends_at) == (first.started_at, first.trial_ends_at)
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_periods") == [(1,)]


async def test_ten_simultaneous_first_requests_create_one_period(engine: AsyncEngine):
    async def first_request(n: int):
        async with repository(engine) as repo:
            # Each one computed other dates: the ones of the winner are the ones that are kept.
            return await repo.create_if_absent(ORGANIZATION, NOW + timedelta(seconds=n), None)

    results = await asyncio.gather(*(first_request(n) for n in range(10)))

    assert await fetch_all(engine, "SELECT count(*) FROM subscription_periods") == [(1,)]
    assert len({(p.started_at, p.trial_ends_at) for p in results}) == 1


async def test_a_read_sees_what_another_session_stored(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    async with repository(engine) as reader:
        before = await reader.get(ORGANIZATION)
        assert before is not None and before.paid_until is None

        assert await apply(engine, charge.id) is ApplyOutcome.APPLIED

        after = await reader.get(ORGANIZATION)
        assert after is not None
        assert after.paid_until == TRIAL_END + timedelta(days=31)  # not the copy the session held


# --- registering a charge ---


async def test_a_charge_is_registered_as_pending_with_what_was_requested(engine: AsyncEngine):
    await create_period(engine)
    payment = uuid.uuid4()

    charge = await add_charge(
        engine, payment_id=payment, billing_period="annual", amount=Decimal("4990.00"), plan="Plan Titán"
    )

    assert charge.payment_id == payment
    assert charge.organization_id == ORGANIZATION
    assert charge.amount == Decimal("4990.00")
    assert (charge.currency, charge.billing_period, charge.attempt) == ("MXN", "annual", 1)
    assert charge.plan == "Plan Titán"
    assert charge.settles_due_at == TRIAL_END
    assert charge.status == ChargeStatus.PENDING
    assert charge.closed_reason is None and charge.resolved_at is None
    assert charge.period_starts_at is None and charge.period_ends_at is None
    assert isinstance(charge.id, uuid.UUID) and charge.created_at is not None


async def test_a_charge_registered_without_a_plan_keeps_it_null(engine: AsyncEngine):
    await create_period(engine)

    charge = await add_charge(engine)

    assert charge.plan is None


async def test_the_same_payment_cannot_be_registered_twice(engine: AsyncEngine):
    await create_period(engine)
    payment = uuid.uuid4()
    await add_charge(engine, payment_id=payment)

    with pytest.raises(UniqueViolationError) as error:
        await add_charge(engine, payment_id=payment, amount=Decimal("799.00"))  # other conditions

    assert error.value.constraint_name == CHARGE_PAYMENT_ID_KEY


async def test_the_same_conditions_and_attempt_cannot_be_registered_twice(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine)
    async with repository(engine) as repo:
        await repo.close_charge(first.id, ClosedReason.REJECTED, NOW)  # resolved: it is not unresolved any more

    with pytest.raises(UniqueViolationError) as error:
        await add_charge(engine)  # another payment with the same conditions and attempt

    assert error.value.constraint_name == CHARGE_TERMS_ATTEMPT_KEY


async def test_two_unresolved_charges_cannot_have_the_same_conditions_whatever_the_attempt(engine: AsyncEngine):
    await create_period(engine)
    await add_charge(engine, attempt=1)

    with pytest.raises(UniqueViolationError) as error:
        await add_charge(engine, attempt=2)  # another payment, another attempt: the period is the same

    assert error.value.constraint_name == CHARGE_PENDING_TERMS_KEY
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges") == [(1,)]


async def test_after_closing_the_unresolved_charge_a_new_attempt_can_be_registered(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine, attempt=1)
    async with repository(engine) as repo:
        await repo.close_charge(first.id, ClosedReason.REJECTED, NOW)

    second = await add_charge(engine, attempt=2)

    assert second.attempt == 2 and second.status == ChargeStatus.PENDING


@pytest.mark.parametrize(
    "other",
    [
        {"amount": Decimal("799.00")},
        {"billing_period": "annual"},
        {"settles_due_at": NEXT_DUE},
        {"organization_id": OTHER_ORGANIZATION},
    ],
)
async def test_unresolved_charges_with_other_conditions_or_organization_coexist(engine: AsyncEngine, other: dict):
    await create_period(engine)
    await create_period(engine, OTHER_ORGANIZATION)
    await add_charge(engine)

    second = await add_charge(engine, **other)

    assert second.status == ChargeStatus.PENDING


async def test_simultaneous_starts_that_computed_different_attempts_register_one_charge(engine: AsyncEngine):
    # What a stress test found: a request that counted the attempts after another one had registered its
    # charge computed the next attempt, which is another key and another payment for the same period.
    await create_period(engine)

    async def start(attempt: int):
        try:
            return await add_charge(engine, attempt=attempt)  # each with a payment of its own
        except UniqueViolationError as error:
            return error

    results = await asyncio.gather(*(start(attempt) for attempt in range(1, 7)))

    registered = [r for r in results if not isinstance(r, UniqueViolationError)]
    refused = [r for r in results if isinstance(r, UniqueViolationError)]
    assert len(registered) == 1 and len(refused) == 5
    assert {r.constraint_name for r in refused} <= {CHARGE_PENDING_TERMS_KEY, CHARGE_TERMS_ATTEMPT_KEY}
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges") == [(1,)]


async def test_a_charge_needs_the_period_of_its_organization(engine: AsyncEngine):
    with pytest.raises(ForeignKeyViolationError):
        await add_charge(engine)


async def test_two_simultaneous_starts_of_the_same_charge_register_one(engine: AsyncEngine):
    await create_period(engine)
    payment = uuid.uuid4()  # the payments API answers both with the same payment (same key)

    async def start():
        try:
            return await add_charge(engine, payment_id=payment)
        except UniqueViolationError as error:
            return error

    results = await asyncio.gather(*(start() for _ in range(8)))

    assert sum(not isinstance(r, UniqueViolationError) for r in results) == 1
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges") == [(1,)]


# --- reading the charges ---


async def test_the_pending_charges_are_the_unresolved_ones_of_that_organization_oldest_first(engine: AsyncEngine):
    await create_period(engine)
    await create_period(engine, OTHER_ORGANIZATION)
    first = await add_charge(engine)
    second = await add_charge(engine, settles_due_at=NEXT_DUE)
    closed = await add_charge(engine, settles_due_at=LAST_DUE)
    await add_charge(engine, organization_id=OTHER_ORGANIZATION)
    async with repository(engine) as repo:
        assert await repo.close_charge(closed.id, ClosedReason.REJECTED, NOW)
        pending = await repo.list_pending(ORGANIZATION)

    assert [charge.id for charge in pending] == [first.id, second.id]


async def test_the_pending_charges_stay_readable_when_the_session_gives_up_an_application(engine: AsyncEngine):
    # The Service keeps the list while it applies the charges one by one. When another request got there
    # first, `apply_charge` gives up with a rollback, which expires everything that the session holds:
    # reading an expired instance would need I/O that cannot happen outside of the session's greenlet.
    await create_period(engine)
    first = await add_charge(engine)
    second = await add_charge(engine, settles_due_at=NEXT_DUE)
    async with repository(engine) as repo:
        pending = await repo.list_pending(ORGANIZATION)

        stale = await repo.apply_charge(
            charge_id=first.id,
            organization_id=ORGANIZATION,
            expected_paid_until=NOW,  # the date is not what the caller read: nothing is applied
            period_starts_at=TRIAL_END,
            period_ends_at=TRIAL_END + timedelta(days=31),
            resolved_at=NOW,
        )

        assert stale is ApplyOutcome.STALE
        assert [(c.id, c.payment_id, c.organization_id, c.amount, c.currency, c.billing_period) for c in pending] == [
            (c.id, c.payment_id, ORGANIZATION, PRICE, "MXN", "monthly") for c in (first, second)
        ]


async def test_a_pending_charge_is_found_by_its_exact_conditions(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    async with repository(engine) as repo:
        found = await repo.find_pending(ORGANIZATION, TRIAL_END, "monthly", PRICE)

        assert found is not None and found.id == charge.id
        assert await repo.find_pending(ORGANIZATION, TRIAL_END, "annual", PRICE) is None
        assert await repo.find_pending(ORGANIZATION, TRIAL_END, "monthly", Decimal("799.00")) is None
        assert await repo.find_pending(ORGANIZATION, TRIAL_END + timedelta(days=1), "monthly", PRICE) is None
        assert await repo.find_pending(OTHER_ORGANIZATION, TRIAL_END, "monthly", PRICE) is None


async def test_a_closed_or_applied_charge_is_not_pending(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    async with repository(engine) as repo:
        assert await repo.close_charge(charge.id, ClosedReason.CANCELLED, NOW)

        assert await repo.find_pending(ORGANIZATION, TRIAL_END, "monthly", PRICE) is None
        assert await repo.list_pending(ORGANIZATION) == []


async def test_a_charge_is_found_by_its_payment(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    async with repository(engine) as repo:
        found = await repo.find_by_payment_id(charge.payment_id)

        assert found is not None and found.id == charge.id
        assert await repo.find_by_payment_id(uuid.uuid4()) is None


async def test_the_next_attempt_counts_only_the_attempts_that_ended(engine: AsyncEngine):
    await create_period(engine)
    async with repository(engine) as repo:
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", PRICE) == 0
    first = await add_charge(engine, attempt=1)
    async with repository(engine) as repo:
        # Unresolved: it is reused, not followed by another attempt, so it is not counted.
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", PRICE) == 0
        await repo.close_charge(first.id, ClosedReason.REJECTED, NOW)
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", PRICE) == 1
    second = await add_charge(engine, attempt=2)
    await add_charge(engine, amount=Decimal("799.00"))  # other conditions, unresolved
    async with repository(engine) as repo:
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", PRICE) == 1
        await apply_second(engine, second.id)
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", PRICE) == 2  # applied too
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "monthly", Decimal("799.00")) == 0
        assert await repo.count_resolved_with_terms(ORGANIZATION, TRIAL_END, "annual", PRICE) == 0


async def apply_second(engine: AsyncEngine, charge_id: uuid.UUID) -> None:
    assert await apply(engine, charge_id) is ApplyOutcome.APPLIED


# --- closing a charge ---


@pytest.mark.parametrize("reason", list(ClosedReason))
async def test_a_pending_charge_is_closed_with_its_reason_and_date(engine: AsyncEngine, reason: ClosedReason):
    await create_period(engine)
    charge = await add_charge(engine)

    async with repository(engine) as repo:
        assert await repo.close_charge(charge.id, reason, NOW + timedelta(hours=1)) is True

    status, closed_reason, starts, ends, resolved = await charge_row(engine, charge.id)
    assert (status, closed_reason, starts, ends) == ("closed", reason.value, None, None)
    assert resolved == NOW + timedelta(hours=1)
    assert await paid_until(engine) is None  # closing never moves the date


async def test_a_charge_is_closed_only_once(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)

    async with repository(engine) as repo:
        assert await repo.close_charge(charge.id, ClosedReason.REJECTED, NOW) is True
        assert await repo.close_charge(charge.id, ClosedReason.CANCELLED, NOW) is False

    assert (await charge_row(engine, charge.id))[1] == "rejected"


async def test_an_applied_charge_cannot_be_closed(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    assert await apply(engine, charge.id) is ApplyOutcome.APPLIED

    async with repository(engine) as repo:
        assert await repo.close_charge(charge.id, ClosedReason.REFUNDED, NOW) is False

    assert (await charge_row(engine, charge.id))[0] == "applied"


async def test_two_simultaneous_closings_close_it_once(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)

    async def close():
        async with repository(engine) as repo:
            return await repo.close_charge(charge.id, ClosedReason.REJECTED, NOW)

    assert sorted(await asyncio.gather(*(close() for _ in range(10)))) == [False] * 9 + [True]


# --- applying a charge (research R5) ---


async def test_applying_a_charge_marks_it_and_moves_the_date_in_one_step(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    start, end = TRIAL_END, TRIAL_END + timedelta(days=31)

    outcome = await apply(engine, charge.id, expected=None, start=start, end=end)

    assert outcome is ApplyOutcome.APPLIED
    assert await charge_row(engine, charge.id) == (
        "applied",
        None,
        start,
        end,
        NOW + timedelta(days=1),
    )
    assert await paid_until(engine) == end


async def test_a_charge_is_applied_once_the_second_time_changes_nothing(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    end = TRIAL_END + timedelta(days=31)
    assert await apply(engine, charge.id, end=end) is ApplyOutcome.APPLIED

    again = await apply(engine, charge.id, expected=end, start=end, end=end + timedelta(days=31))

    assert again is ApplyOutcome.ALREADY_RESOLVED
    assert await paid_until(engine) == end
    assert (await charge_row(engine, charge.id))[3] == end


async def test_a_closed_charge_is_not_applied(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    async with repository(engine) as repo:
        await repo.close_charge(charge.id, ClosedReason.REJECTED, NOW)

    assert await apply(engine, charge.id) is ApplyOutcome.ALREADY_RESOLVED
    assert await paid_until(engine) is None


async def test_a_charge_of_another_organization_is_not_applied(engine: AsyncEngine):
    await create_period(engine)
    await create_period(engine, OTHER_ORGANIZATION)
    charge = await add_charge(engine, organization_id=OTHER_ORGANIZATION)

    assert await apply(engine, charge.id) is ApplyOutcome.ALREADY_RESOLVED  # asked with ORGANIZATION
    assert (await charge_row(engine, charge.id))[0] == "pending"
    assert await paid_until(engine) is None and await paid_until(engine, OTHER_ORGANIZATION) is None


async def test_a_date_that_moved_since_it_was_read_is_stale_and_the_claim_is_undone(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine)
    second = await add_charge(engine, settles_due_at=NEXT_DUE)
    first_end = TRIAL_END + timedelta(days=31)
    assert await apply(engine, first.id, end=first_end) is ApplyOutcome.APPLIED

    # The caller of the second one read `paid_until` before the first one moved it.
    outcome = await apply(engine, second.id, expected=None, start=TRIAL_END, end=first_end + timedelta(days=30))

    assert outcome is ApplyOutcome.STALE
    assert (await charge_row(engine, second.id))[0] == "pending"  # still pending: nothing was claimed
    assert await paid_until(engine) == first_end


async def test_the_stale_charge_is_applied_after_reading_the_date_again(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine)
    second = await add_charge(engine, settles_due_at=NEXT_DUE)
    first_end = TRIAL_END + timedelta(days=31)
    second_end = first_end + timedelta(days=30)
    await apply(engine, first.id, end=first_end)

    outcome = await apply(engine, second.id, expected=first_end, start=first_end, end=second_end)

    assert outcome is ApplyOutcome.APPLIED
    assert await paid_until(engine) == second_end


async def test_twenty_simultaneous_applications_of_one_charge_move_the_date_once(engine: AsyncEngine):
    await create_period(engine)
    charge = await add_charge(engine)
    end = TRIAL_END + timedelta(days=31)

    outcomes = await asyncio.gather(*(apply(engine, charge.id, end=end) for _ in range(20)))

    assert sorted(outcomes) == [ApplyOutcome.ALREADY_RESOLVED] * 19 + [ApplyOutcome.APPLIED]
    assert await paid_until(engine) == end
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges WHERE status = 'applied'") == [(1,)]


# --- the history of charges (spec 012) ---


async def list_charges(
    engine: AsyncEngine,
    organization_id: uuid.UUID = ORGANIZATION,
    *,
    page=1,
    page_size=10,
    status=None,
):
    async with repository(engine) as repo:
        return await repo.list_charges(organization_id, page=page, page_size=page_size, status=status)


async def test_an_organization_without_charges_has_an_empty_history(engine: AsyncEngine):
    await create_period(engine)

    charges, total = await list_charges(engine)

    assert charges == [] and total == 0


async def test_the_history_lists_newest_first_and_only_of_its_own_organization(engine: AsyncEngine):
    await create_period(engine)
    await create_period(engine, OTHER_ORGANIZATION)
    first = await add_charge(engine, payment_id=uuid.uuid4())
    second = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=NEXT_DUE)
    await add_charge(engine, organization_id=OTHER_ORGANIZATION, payment_id=uuid.uuid4())

    charges, total = await list_charges(engine)

    assert total == 2
    assert [c.id for c in charges] == [second.id, first.id]


async def test_the_history_is_paginated(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine, payment_id=uuid.uuid4())
    second = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=NEXT_DUE)
    third = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=LAST_DUE)

    first_page, total = await list_charges(engine, page=1, page_size=2)
    second_page, _ = await list_charges(engine, page=2, page_size=2)

    assert total == 3
    assert [c.id for c in first_page] == [third.id, second.id]
    assert [c.id for c in second_page] == [first.id]


async def test_a_page_past_the_last_one_is_empty_but_the_total_is_still_reported(engine: AsyncEngine):
    await create_period(engine)
    await add_charge(engine, payment_id=uuid.uuid4())

    charges, total = await list_charges(engine, page=5, page_size=10)

    assert charges == [] and total == 1


async def test_the_history_shows_every_status_with_its_own_fields(engine: AsyncEngine):
    await create_period(engine)
    pending = await add_charge(engine, payment_id=uuid.uuid4())
    applied_charge = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=NEXT_DUE)
    closed = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=LAST_DUE)
    await apply(engine, applied_charge.id, start=TRIAL_END, end=NEXT_DUE)
    async with repository(engine) as repo:
        await repo.close_charge(closed.id, ClosedReason.REJECTED, NOW)

    charges, _ = await list_charges(engine)

    by_id = {c.id: c for c in charges}
    assert by_id[pending.id].status == ChargeStatus.PENDING
    assert by_id[pending.id].period_starts_at is None and by_id[pending.id].closed_reason is None
    assert by_id[applied_charge.id].status == ChargeStatus.APPLIED
    assert (by_id[applied_charge.id].period_starts_at, by_id[applied_charge.id].period_ends_at) == (
        TRIAL_END,
        NEXT_DUE,
    )
    assert by_id[closed.id].status == ChargeStatus.CLOSED
    assert by_id[closed.id].closed_reason == ClosedReason.REJECTED.value


async def test_the_history_can_be_filtered_by_status(engine: AsyncEngine):
    await create_period(engine)
    pending = await add_charge(engine, payment_id=uuid.uuid4())
    applied_charge = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=NEXT_DUE)
    closed = await add_charge(engine, payment_id=uuid.uuid4(), settles_due_at=LAST_DUE)
    await apply(engine, applied_charge.id, start=TRIAL_END, end=NEXT_DUE)
    async with repository(engine) as repo:
        await repo.close_charge(closed.id, ClosedReason.REJECTED, NOW)

    pending_only, pending_total = await list_charges(engine, status="pending")
    applied_only, applied_total = await list_charges(engine, status="applied")
    closed_only, closed_total = await list_charges(engine, status="closed")

    assert pending_total == 1 and [c.id for c in pending_only] == [pending.id]
    assert applied_total == 1 and [c.id for c in applied_only] == [applied_charge.id]
    assert closed_total == 1 and [c.id for c in closed_only] == [closed.id]


async def test_two_different_charges_applied_at_the_same_time_both_end_up_applied(engine: AsyncEngine):
    await create_period(engine)
    first = await add_charge(engine)
    second = await add_charge(engine, settles_due_at=NEXT_DUE)
    month = timedelta(days=31)

    async def apply_with_retries(charge_id: uuid.UUID) -> None:
        # What the Service does: read the date, compute the period from it, try; on «stale», again.
        for _ in range(5):
            current = await paid_until(engine)
            start = current or TRIAL_END
            outcome = await apply(engine, charge_id, expected=current, start=start, end=start + month)
            if outcome is not ApplyOutcome.STALE:
                return
        raise AssertionError("it never stopped being stale")

    await asyncio.gather(apply_with_retries(first.id), apply_with_retries(second.id))

    assert await paid_until(engine) == TRIAL_END + 2 * month  # the second continues where the first ends
    assert await fetch_all(engine, "SELECT count(*) FROM subscription_charges WHERE status = 'applied'") == [(2,)]

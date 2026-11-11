"""ClinicSubscriptionChargeRepository against a real PostgreSQL 17 (Principle V)."""

from datetime import date
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.clinic_subscription_charge_repository import ClinicSubscriptionChargeRepository

PERIOD = date(2026, 12, 1)


def charge_kwargs(**overrides) -> dict:
    values = {
        "clinic_subscription_id": uuid4(),
        "tenant_id": uuid4(),
        "period": PERIOD,
        "amount": 129900,
        "currency": "MXN",
        "payment_id": uuid4(),
        "payment_status": "pending",
        "checkout_url": "https://pagos.test/checkout/x",
        "idempotency_key": "k1",
    }
    values.update(overrides)
    return values


# --- save_charge: upsert by (clinic_subscription_id, period) ---


async def test_save_charge_returns_the_row_as_inserted(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)

    charge = await repository.save_charge(**charge_kwargs())

    assert charge.payment_status == "pending"
    assert charge.amount == 129900


async def test_save_charge_of_the_same_period_updates_the_same_row_not_a_duplicate(
    db_session: AsyncSession,
):
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()
    payment_id = uuid4()

    first = await repository.save_charge(
        **charge_kwargs(
            clinic_subscription_id=clinic_subscription_id, payment_id=payment_id, payment_status="pending"
        )
    )
    second = await repository.save_charge(
        **charge_kwargs(
            clinic_subscription_id=clinic_subscription_id,
            payment_id=payment_id,
            payment_status="approved",
            checkout_url=None,
        )
    )

    assert first.id == second.id
    assert second.payment_status == "approved"
    history, total = await repository.list(clinic_subscription_id, page=1, limit=20)
    assert total == 1  # the retry updated the row, it did not add a second one


async def test_save_charge_of_a_different_period_creates_a_new_row(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()

    await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id, period=date(2026, 11, 1))
    )
    await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id, period=date(2026, 12, 1))
    )

    _, total = await repository.list(clinic_subscription_id, page=1, limit=20)
    assert total == 2


async def test_a_second_subscription_does_not_conflict_with_the_same_period(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)

    first = await repository.save_charge(**charge_kwargs(clinic_subscription_id=uuid4()))
    second = await repository.save_charge(**charge_kwargs(clinic_subscription_id=uuid4()))

    assert first.id != second.id


# --- update_status: the sync-on-read ---


async def test_update_status_changes_only_the_status_and_checkout_url(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)
    charge = await repository.save_charge(**charge_kwargs())

    updated = await repository.update_status(charge.id, payment_status="approved", checkout_url=None)

    assert updated.payment_status == "approved"
    assert updated.checkout_url is None
    assert updated.amount == charge.amount  # unrelated columns untouched


# --- get_by_period / get / list ---


async def test_get_by_period_of_an_unknown_pair_is_none(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)

    assert await repository.get_by_period(uuid4(), PERIOD) is None


async def test_get_by_period_finds_the_matching_row(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()
    saved = await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id)
    )

    found = await repository.get_by_period(clinic_subscription_id, PERIOD)

    assert found is not None and found.id == saved.id


async def test_get_scopes_by_clinic_subscription_id(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()
    saved = await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id)
    )

    assert await repository.get(clinic_subscription_id, saved.id) is not None
    assert await repository.get(uuid4(), saved.id) is None  # wrong subscription
    assert await repository.get(clinic_subscription_id, 999999) is None  # unknown id


async def test_list_paginates_most_recent_period_first(db_session: AsyncSession):
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()
    await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id, period=date(2026, 11, 1))
    )
    await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id, period=date(2026, 12, 1))
    )

    page, total = await repository.list(clinic_subscription_id, page=1, limit=1)

    assert total == 2
    assert page[0].period == date(2026, 12, 1)


async def test_save_charge_never_duplicates_even_with_a_different_payment_id(
    db_session: AsyncSession,
):
    """The unique index on `(clinic_subscription_id, period)` is enforced via `ON CONFLICT DO
    UPDATE` (research R3): a second `save_charge` of the same pair, even with a different
    `payment_id` (e.g. a stale retry), still updates the one row instead of raising or duplicating."""
    repository = ClinicSubscriptionChargeRepository(db_session)
    clinic_subscription_id = uuid4()
    await repository.save_charge(**charge_kwargs(clinic_subscription_id=clinic_subscription_id))

    await repository.save_charge(
        **charge_kwargs(clinic_subscription_id=clinic_subscription_id, payment_id=uuid4())
    )

    _, total = await repository.list(clinic_subscription_id, page=1, limit=20)
    assert total == 1

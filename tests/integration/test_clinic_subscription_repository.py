"""ClinicSubscriptionRepository against a real PostgreSQL 17 (Principle V)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.clinic_subscription_status import ClinicSubscriptionStatus
from src.repositories.clinic_subscription_repository import ClinicSubscriptionRepository
from src.repositories.errors import UniqueViolationError
from tests.helpers import insert_subscription

MOMENT = datetime(2026, 11, 1, tzinfo=UTC)


async def active_plan(session: AsyncSession, **overrides) -> int:
    return await insert_subscription(session, status_id=1, **overrides)


# --- create / the unique index of FR-004 ---


async def test_create_returns_the_row_with_its_status_loaded(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)

    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    assert row.status.id == ClinicSubscriptionStatus.ACTIVE
    assert row.status.name == "Activa"


async def test_a_second_active_subscription_of_the_same_clinic_violates_the_unique_index(
    db_session: AsyncSession,
):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    tenant_id = uuid4()
    await repository.create(
        tenant_id=tenant_id, subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    with pytest.raises(UniqueViolationError) as error:
        await repository.create(
            tenant_id=tenant_id, subscription_id=plan_id, billing_cycle="annual",
            started_at=MOMENT, next_billing_at=MOMENT,
        )

    assert error.value.constraint_name == "clinic_subscriptions_one_active_per_tenant_key"


async def test_a_second_subscription_of_a_different_clinic_does_not_conflict(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)

    first = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    second = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    assert first.id != second.id


# --- get_by_id / list ---


async def test_get_by_id_of_an_unknown_id_is_none(db_session: AsyncSession):
    assert await ClinicSubscriptionRepository(db_session).get_by_id(999) is None


async def test_get_by_id_reflects_a_concurrent_update_populate_existing(db_session: AsyncSession):
    """Regression: `save_charge` updates `clinic_subscriptions` with a raw statement; `get_by_id`
    must not serve a stale, already-loaded ORM instance of the same row (the bug this guards
    against made the sync-on-read of historia 3 silently keep showing the old status)."""
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.get_by_id(row.id)  # loads it into the session's identity map once

    await repository.save_charge(
        row.id, period=MOMENT.date(), amount=100, currency="MXN", payment_id=uuid4(),
        payment_status="approved", checkout_url=None, idempotency_key="k1",
        subscription_status_id=ClinicSubscriptionStatus.ACTIVE,
        next_billing_at=MOMENT + timedelta(days=30),
    )

    refreshed = await repository.get_by_id(row.id)
    assert refreshed.next_billing_at == MOMENT + timedelta(days=30)


async def test_list_filters_by_tenant_and_status_and_paginates(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    tenant_a, tenant_b = uuid4(), uuid4()
    await repository.create(
        tenant_id=tenant_a, subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.create(
        tenant_id=tenant_b, subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT + timedelta(seconds=1), next_billing_at=MOMENT,
    )

    only_a, total_a = await repository.list(tenant_id=tenant_a, status_id=None, page=1, limit=20)
    all_rows, total_all = await repository.list(tenant_id=None, status_id=None, page=1, limit=1)

    assert total_a == 1 and [r.tenant_id for r in only_a] == [tenant_a]
    assert total_all == 2 and len(all_rows) == 1  # paginated to 1


# --- save_charge: upsert by (clinic_subscription_id, period) ---


async def test_save_charge_of_the_same_period_updates_the_same_row_not_a_duplicate(
    db_session: AsyncSession,
):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    period = MOMENT.date()
    payment_id = uuid4()

    first = await repository.save_charge(
        row.id, period=period, amount=100, currency="MXN", payment_id=payment_id,
        payment_status="pending", checkout_url="https://x", idempotency_key="k1",
        subscription_status_id=ClinicSubscriptionStatus.PENDING_RESOLUTION,
    )
    second = await repository.save_charge(
        row.id, period=period, amount=100, currency="MXN", payment_id=payment_id,
        payment_status="approved", checkout_url=None, idempotency_key="k1",
        subscription_status_id=ClinicSubscriptionStatus.ACTIVE,
        next_billing_at=MOMENT + timedelta(days=30),
    )

    assert first.id == second.id
    assert second.payment_status == "approved"
    history, total = await repository.list_charges(row.id, page=1, limit=20)
    assert total == 1  # the retry updated the row, it did not add a second one


async def test_save_charge_of_a_different_period_creates_a_new_row(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.save_charge(
        row.id, period=MOMENT.date(), amount=100, currency="MXN", payment_id=uuid4(),
        payment_status="approved", checkout_url=None, idempotency_key="k1",
        subscription_status_id=ClinicSubscriptionStatus.ACTIVE,
        next_billing_at=MOMENT + timedelta(days=30),
    )

    await repository.save_charge(
        row.id, period=(MOMENT + timedelta(days=30)).date(), amount=100, currency="MXN",
        payment_id=uuid4(), payment_status="pending", checkout_url="https://x",
        idempotency_key="k2", subscription_status_id=ClinicSubscriptionStatus.PENDING_RESOLUTION,
    )

    _, total = await repository.list_charges(row.id, page=1, limit=20)
    assert total == 2


async def test_latest_charges_for_picks_the_most_recent_period_per_subscription(
    db_session: AsyncSession,
):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.save_charge(
        row.id, period=MOMENT.date(), amount=100, currency="MXN", payment_id=uuid4(),
        payment_status="approved", checkout_url=None, idempotency_key="k1",
        subscription_status_id=ClinicSubscriptionStatus.ACTIVE,
        next_billing_at=MOMENT + timedelta(days=30),
    )
    await repository.save_charge(
        row.id, period=(MOMENT + timedelta(days=30)).date(), amount=100, currency="MXN",
        payment_id=uuid4(), payment_status="pending", checkout_url="https://x",
        idempotency_key="k2", subscription_status_id=ClinicSubscriptionStatus.PENDING_RESOLUTION,
    )

    latest = await repository.latest_charges_for([row.id])

    assert latest[row.id].period == (MOMENT + timedelta(days=30)).date()


async def test_latest_charge_of_a_subscription_without_any_is_none(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    assert await repository.latest_charge(row.id) is None


# --- cancel ---


async def test_cancel_moves_an_active_subscription_to_cancelled(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    cancelled = await repository.cancel(row.id)

    assert cancelled.status_id == ClinicSubscriptionStatus.CANCELLED


async def test_cancel_an_already_cancelled_subscription_returns_none(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    row = await repository.create(
        tenant_id=uuid4(), subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.cancel(row.id)

    assert await repository.cancel(row.id) is None


async def test_cancelling_frees_the_tenant_for_a_new_active_subscription(db_session: AsyncSession):
    plan_id = await active_plan(db_session, name="Pro")
    repository = ClinicSubscriptionRepository(db_session)
    tenant_id = uuid4()
    first = await repository.create(
        tenant_id=tenant_id, subscription_id=plan_id, billing_cycle="monthly",
        started_at=MOMENT, next_billing_at=MOMENT,
    )
    await repository.cancel(first.id)

    second = await repository.create(
        tenant_id=tenant_id, subscription_id=plan_id, billing_cycle="annual",
        started_at=MOMENT, next_billing_at=MOMENT,
    )

    assert second.id != first.id

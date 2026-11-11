"""Business rules of the clinic subscriptions, with the Repository and Pagos replaced by doubles."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.dtos.clinic_subscription import ClinicSubscriptionCreate
from src.exceptions import (
    ClinicSubscriptionAlreadyActiveError,
    ClinicSubscriptionAlreadyCancelledError,
    ClinicSubscriptionChargeConflictError,
    ClinicSubscriptionChargeNotFoundError,
    ClinicSubscriptionChargePendingError,
    ClinicSubscriptionChargeRequiresActivePlanError,
    ClinicSubscriptionNotChargeableError,
    ClinicSubscriptionNotFoundError,
    ClinicSubscriptionPlanNotActiveError,
    InvalidTokenError,
    PaymentNotAuthorizedError,
    PaymentsUnavailableError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.integrations.payments_api import PaymentView
from src.models.subscription_status import SubscriptionStatus
from src.services.clinic_subscription_service import ClinicSubscriptionService
from tests.unit.fakes import (
    FakeClinicSubscriptionRepository,
    FakePaymentsApi,
    FakeSubscriptionRepository,
    fake_caller_access,
)

TENANT = UUID("3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f")
TOKEN = "the-token"


def service(repository=None, subscriptions=None, payments=None) -> ClinicSubscriptionService:
    return ClinicSubscriptionService(
        repository or FakeClinicSubscriptionRepository(),
        subscriptions or FakeSubscriptionRepository(),
        payments or FakePaymentsApi(),
    )


def active_plan(subscriptions: FakeSubscriptionRepository, **overrides):
    return subscriptions.add(status_id=SubscriptionStatus.ACTIVE, **overrides)


# --- US1: assign a plan ---


async def test_create_without_trial_charges_immediately():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)

    view = await service(subscriptions=subscriptions).create(
        ClinicSubscriptionCreate(tenant_id=TENANT, subscription_id=1, billing_cycle="monthly")
    )

    row = view.clinic_subscription
    assert row.next_billing_at == row.started_at
    assert row.status_id == 1


async def test_create_with_trial_defers_the_first_charge():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions, trial_days=14)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)

    view = await service(subscriptions=subscriptions).create(
        ClinicSubscriptionCreate(
            tenant_id=TENANT, subscription_id=1, billing_cycle="monthly", started_at=started_at
        )
    )

    assert view.clinic_subscription.next_billing_at == started_at + timedelta(days=14)


@pytest.mark.parametrize("status_id", [SubscriptionStatus.INACTIVE, SubscriptionStatus.BLOCKED])
async def test_create_rejects_a_plan_that_is_not_active(status_id):
    subscriptions = FakeSubscriptionRepository()
    subscriptions.add(status_id=status_id)

    with pytest.raises(ClinicSubscriptionPlanNotActiveError):
        await service(subscriptions=subscriptions).create(
            ClinicSubscriptionCreate(tenant_id=TENANT, subscription_id=1, billing_cycle="monthly")
        )


async def test_create_rejects_an_unknown_plan():
    with pytest.raises(ClinicSubscriptionPlanNotActiveError):
        await service().create(
            ClinicSubscriptionCreate(tenant_id=TENANT, subscription_id=999, billing_cycle="monthly")
        )


async def test_create_rejects_a_second_active_subscription_of_the_same_clinic():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    repository.add(tenant_id=TENANT)

    with pytest.raises(ClinicSubscriptionAlreadyActiveError):
        await service(repository, subscriptions).create(
            ClinicSubscriptionCreate(tenant_id=TENANT, subscription_id=1, billing_cycle="monthly")
        )


# --- US2: charge ---


def caller_for(tenant: UUID):
    return fake_caller_access(tenant_id=str(tenant))


async def test_charge_sends_the_exact_body_and_advances_on_approval():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions, monthly_price="1299.00")
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, next_billing_at=datetime(2026, 12, 1, tzinfo=UTC))
    payment_id = uuid4()
    payments = FakePaymentsApi(
        payment=PaymentView(id=payment_id, status="approved", checkout_url=None, amount=129900, currency="MXN")
    )

    charge = await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    [call] = payments.create_calls
    assert call["amount"] == 129900
    assert call["currency"] == "MXN"
    assert call["resource_type"] == "system-api:clinic-subscription"
    assert call["resource_id"] == str(row.id)
    assert call["idempotency_key"] == f"clinic-subscription:{row.id}:2026-12-01"
    assert call["token"] == TOKEN
    assert charge.payment_status == "approved"
    assert row.status_id == 1
    assert row.next_billing_at == datetime(2027, 1, 1, tzinfo=UTC)


async def test_charge_of_an_annual_plan_uses_the_annual_price():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions, annual_price="12990.00")
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, billing_cycle="annual")
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="pending", checkout_url="https://x", amount=1299000, currency="MXN")
    )

    await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    assert payments.create_calls[0]["amount"] == 1299000


async def test_charge_pending_leaves_the_subscription_pending_without_advancing():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    next_billing_at = row.next_billing_at
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="pending", checkout_url="https://x", amount=129900, currency="MXN")
    )

    await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    assert row.status_id == 2
    assert row.next_billing_at == next_billing_at


async def test_charge_retries_a_period_whose_charge_was_rejected():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    repository.add_charge(
        clinic_subscription_id=row.id,
        period=row.next_billing_at.date(),
        payment_id=uuid4(),
        payment_status="rejected",
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="approved", checkout_url=None, amount=129900, currency="MXN")
    )

    charge = await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    assert charge.payment_status == "approved"
    assert row.status_id == 1


async def test_charge_is_rejected_for_another_organization_as_not_found():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)

    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service(repository).charge(row.id, caller_for(uuid4()), TOKEN)


async def test_charge_is_rejected_when_the_caller_has_no_organization():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)

    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service(repository).charge(row.id, fake_caller_access(tenant_id=None), TOKEN)


async def test_charge_is_rejected_for_a_cancelled_subscription():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=3)

    with pytest.raises(ClinicSubscriptionNotChargeableError):
        await service(repository).charge(row.id, caller_for(TENANT), TOKEN)


async def test_charge_retries_a_still_pending_charge_instead_of_blocking_it():
    # Historia 2, escenario 2: a retry (e.g. after a dropped connection) must reach Pagos again
    # with the same deterministic Idempotency-Key, never be rejected locally as a conflict.
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="pending"
    )
    payment_id = uuid4()
    payments = FakePaymentsApi(
        payment=PaymentView(id=payment_id, status="pending", checkout_url="https://x", amount=129900, currency="MXN")
    )

    charge = await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    assert charge.payment_id == payment_id
    assert len(payments.create_calls) == 1


async def test_charge_fails_closed_when_pagos_is_fully_down_even_with_a_pending_retry():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(unavailable=True)

    with pytest.raises(PaymentsUnavailableError):
        await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)


async def test_charge_requires_the_plan_to_still_be_active():
    subscriptions = FakeSubscriptionRepository()
    subscriptions.add(status_id=SubscriptionStatus.INACTIVE)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)

    with pytest.raises(ClinicSubscriptionChargeRequiresActivePlanError):
        await service(repository, subscriptions).charge(row.id, caller_for(TENANT), TOKEN)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("token_expired", TokenExpiredError),
        ("unauthenticated", UnauthenticatedError),
        ("invalid_token", InvalidTokenError),
    ],
)
async def test_charge_translates_a_payments_api_rejection(code, expected):
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    payments = FakePaymentsApi(rejected_code=code)

    with pytest.raises(expected):
        await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)


async def test_charge_translates_a_payments_api_permission_denial():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    payments = FakePaymentsApi(permission_denied=True)

    with pytest.raises(PaymentNotAuthorizedError):
        await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)


async def test_charge_translates_an_idempotency_conflict():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    payments = FakePaymentsApi(idempotency_conflict=True)

    with pytest.raises(ClinicSubscriptionChargeConflictError):
        await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)


async def test_charge_translates_payments_api_unavailable_and_changes_nothing():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    payments = FakePaymentsApi(unavailable=True)

    with pytest.raises(PaymentsUnavailableError):
        await service(repository, subscriptions, payments).charge(row.id, caller_for(TENANT), TOKEN)

    assert row.status_id == 1  # unchanged: nothing was saved


# --- US3: sync a pending charge on read ---


async def test_get_syncs_a_pending_charge_to_approved_and_advances():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2, next_billing_at=datetime(2026, 12, 1, tzinfo=UTC))
    repository.add_charge(
        clinic_subscription_id=row.id, period=date(2026, 12, 1), payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="approved", checkout_url=None, amount=129900, currency="MXN")
    )

    view = await service(repository, payments=payments).get(row.id)

    assert view.current_charge.payment_status == "approved"
    assert view.clinic_subscription.status_id == 1
    assert view.clinic_subscription.next_billing_at == datetime(2027, 1, 1, tzinfo=UTC)


async def test_get_syncs_a_pending_charge_to_rejected_without_advancing():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    next_billing_at = row.next_billing_at
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="rejected", checkout_url=None, amount=129900, currency="MXN")
    )

    view = await service(repository, payments=payments).get(row.id)

    assert view.current_charge.payment_status == "rejected"
    assert view.clinic_subscription.status_id == 2
    assert view.clinic_subscription.next_billing_at == next_billing_at


async def test_get_keeps_the_local_status_when_payments_api_is_down():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(unavailable=True)

    view = await service(repository, payments=payments).get(row.id)

    assert view.current_charge.payment_status == "pending"


async def test_get_never_calls_payments_api_for_a_resolved_charge():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="approved"
    )
    payments = FakePaymentsApi()

    await service(repository, payments=payments).get(row.id)

    assert payments.get_calls == []


# --- US4: consult / list ---


async def test_get_an_unknown_or_cancelled_subscription_is_not_found():
    repository = FakeClinicSubscriptionRepository()
    cancelled = repository.add(tenant_id=TENANT, status_id=3)

    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service(repository).get(999)
    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service(repository).get(cancelled.id)


async def test_list_is_paginated_and_filtered_by_tenant_and_status():
    repository = FakeClinicSubscriptionRepository()
    one = repository.add(tenant_id=TENANT)
    repository.add(tenant_id=uuid4(), status_id=3)

    views, total = await service(repository).list(tenant_id=TENANT, status_id=None, page=1, limit=20)

    assert total == 1
    assert [v.clinic_subscription.id for v in views] == [one.id]


async def test_get_charge_not_found():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)

    with pytest.raises(ClinicSubscriptionChargeNotFoundError):
        await service(repository).get_charge(row.id, 999)


async def test_list_charges_of_an_unknown_subscription_is_not_found():
    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service().list_charges(999, page=1, limit=20)


# --- US5: cancel ---


async def test_cancel_an_active_subscription_without_a_pending_charge():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT)

    await service(repository).cancel(row.id)

    assert row.status_id == 3


async def test_cancel_rejects_a_pending_charge():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=2)
    repository.add_charge(
        clinic_subscription_id=row.id, period=row.next_billing_at.date(), payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(unavailable=True)

    with pytest.raises(ClinicSubscriptionChargePendingError):
        await service(repository, payments=payments).cancel(row.id)
    assert row.status_id == 2


async def test_cancel_an_already_cancelled_subscription():
    repository = FakeClinicSubscriptionRepository()
    row = repository.add(tenant_id=TENANT, status_id=3)

    with pytest.raises(ClinicSubscriptionAlreadyCancelledError):
        await service(repository).cancel(row.id)


async def test_cancel_an_unknown_subscription():
    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service().cancel(999)

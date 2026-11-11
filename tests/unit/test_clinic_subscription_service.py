"""Business rules of charging a clinic subscription, with Clinics/Pagos/the Repository replaced by
doubles."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from src.integrations.clinics_api import ClinicSubscriptionInfo
from src.integrations.payments_api import PaymentView
from src.exceptions import (
    ClinicSubscriptionChargeAlreadyApprovedError,
    ClinicSubscriptionChargeConflictError,
    ClinicSubscriptionChargeNotFoundError,
    ClinicSubscriptionCheckUnavailableError,
    ClinicSubscriptionNotFoundError,
    ClinicSubscriptionPlanNotActiveError,
    InvalidTokenError,
    PaymentNotAuthorizedError,
    PaymentsUnavailableError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.models.subscription_status import SubscriptionStatus
from src.services.clinic_subscription_service import ClinicSubscriptionService
from tests.unit.fakes import (
    FakeClinicSubscriptionChargeRepository,
    FakeClinicsApi,
    FakePaymentsApi,
    FakeSubscriptionRepository,
    fake_caller_access,
)

TENANT = "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f"
CLINIC_SUBSCRIPTION_ID = UUID("6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70")
PERIOD = date(2026, 12, 1)
TOKEN = "the-token"


def service(repository=None, subscriptions=None, clinics=None, payments=None) -> ClinicSubscriptionService:
    return ClinicSubscriptionService(
        repository or FakeClinicSubscriptionChargeRepository(),
        subscriptions or FakeSubscriptionRepository(),
        clinics or FakeClinicsApi(clinic_subscription=ClinicSubscriptionInfo(
            tenant_id=TENANT, subscription_id=1, billing_cycle="monthly"
        )),
        payments or FakePaymentsApi(),
    )


def active_plan(subscriptions: FakeSubscriptionRepository, **overrides):
    return subscriptions.add(status_id=SubscriptionStatus.ACTIVE, **overrides)


def caller() -> object:
    return fake_caller_access(tenant_id=TENANT)


# --- historia 1: charge ---


async def test_charge_sends_the_exact_body_to_payments():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions, monthly_price="1299.00")
    clinics = FakeClinicsApi(
        clinic_subscription=ClinicSubscriptionInfo(tenant_id=TENANT, subscription_id=1, billing_cycle="monthly")
    )
    payment_id = uuid4()
    payments = FakePaymentsApi(
        payment=PaymentView(id=payment_id, status="pending", checkout_url="https://x", amount=129900, currency="MXN")
    )

    charge = await service(subscriptions=subscriptions, clinics=clinics, payments=payments).charge(
        CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
    )

    [call] = payments.create_calls
    assert call["amount"] == 129900
    assert call["currency"] == "MXN"
    assert call["resource_type"] == "system-api:clinic-subscription"
    assert call["resource_id"] == str(CLINIC_SUBSCRIPTION_ID)
    assert call["idempotency_key"] == f"clinic-subscription:{CLINIC_SUBSCRIPTION_ID}:2026-12-01"
    assert call["token"] == TOKEN
    assert charge.payment_status == "pending"
    assert charge.tenant_id == UUID(TENANT)


async def test_charge_of_an_annual_plan_uses_the_annual_price():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions, annual_price="12990.00")
    clinics = FakeClinicsApi(
        clinic_subscription=ClinicSubscriptionInfo(tenant_id=TENANT, subscription_id=1, billing_cycle="annual")
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=uuid4(), status="pending", checkout_url="https://x", amount=1299000, currency="MXN")
    )

    await service(subscriptions=subscriptions, clinics=clinics, payments=payments).charge(
        CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
    )

    assert payments.create_calls[0]["amount"] == 1299000


async def test_charge_is_idempotent_for_the_same_period():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    payment_id = uuid4()
    payments = FakePaymentsApi(
        payment=PaymentView(id=payment_id, status="pending", checkout_url="https://x", amount=129900, currency="MXN")
    )
    svc = service(subscriptions=subscriptions, payments=payments)

    first = await svc.charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)
    second = await svc.charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)

    assert first.payment_id == second.payment_id == payment_id
    assert len(payments.create_calls) == 2  # both reached Pagos, which kept it idempotent
    assert payments.create_calls[0]["idempotency_key"] == payments.create_calls[1]["idempotency_key"]


async def test_charge_is_rejected_when_clinics_reports_not_found():
    clinics = FakeClinicsApi(clinic_subscription_not_found=True)

    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service(clinics=clinics).charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)


async def test_charge_fails_closed_when_clinics_is_down():
    clinics = FakeClinicsApi(clinic_subscription_unavailable=True)

    with pytest.raises(ClinicSubscriptionCheckUnavailableError):
        await service(clinics=clinics).charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)


async def test_charge_from_another_organization_is_not_found():
    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service().charge(CLINIC_SUBSCRIPTION_ID, PERIOD, fake_caller_access(tenant_id=str(uuid4())), TOKEN)


async def test_charge_without_an_organization_is_not_found():
    with pytest.raises(ClinicSubscriptionNotFoundError):
        await service().charge(CLINIC_SUBSCRIPTION_ID, PERIOD, fake_caller_access(tenant_id=None), TOKEN)


async def test_charge_requires_the_plan_to_still_be_active():
    subscriptions = FakeSubscriptionRepository()
    subscriptions.add(status_id=SubscriptionStatus.INACTIVE)

    with pytest.raises(ClinicSubscriptionPlanNotActiveError):
        await service(subscriptions=subscriptions).charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)


async def test_charge_requires_a_known_plan():
    subscriptions = FakeSubscriptionRepository()  # no plan with id 1 at all

    with pytest.raises(ClinicSubscriptionPlanNotActiveError):
        await service(subscriptions=subscriptions).charge(CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN)


async def test_charge_already_approved_for_the_period_is_a_conflict_without_calling_pagos():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionChargeRepository()
    repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="approved"
    )
    payments = FakePaymentsApi()

    with pytest.raises(ClinicSubscriptionChargeAlreadyApprovedError):
        await service(repository, subscriptions, payments=payments).charge(
            CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
        )
    assert payments.create_calls == []


@pytest.mark.parametrize("status", ["pending", "rejected", "cancelled"])
async def test_charge_retries_a_period_that_is_not_yet_approved(status):
    # Historia 1, escenario 2: a retry (pending) or a new attempt after a rejection/cancellation
    # must reach Pagos again with the same deterministic Idempotency-Key, never be blocked locally.
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionChargeRepository()
    repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status=status
    )
    payment_id = uuid4()
    payments = FakePaymentsApi(
        payment=PaymentView(id=payment_id, status="approved", checkout_url=None, amount=129900, currency="MXN")
    )

    charge = await service(repository, subscriptions, payments=payments).charge(
        CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
    )

    assert charge.payment_id == payment_id
    assert charge.payment_status == "approved"
    assert len(payments.create_calls) == 1


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
    payments = FakePaymentsApi(rejected_code=code)

    with pytest.raises(expected):
        await service(subscriptions=subscriptions, payments=payments).charge(
            CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
        )


async def test_charge_translates_a_payments_api_permission_denial():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    payments = FakePaymentsApi(permission_denied=True)

    with pytest.raises(PaymentNotAuthorizedError):
        await service(subscriptions=subscriptions, payments=payments).charge(
            CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
        )


async def test_charge_translates_an_idempotency_conflict():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    payments = FakePaymentsApi(idempotency_conflict=True)

    with pytest.raises(ClinicSubscriptionChargeConflictError):
        await service(subscriptions=subscriptions, payments=payments).charge(
            CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
        )


async def test_charge_translates_payments_api_unavailable_and_saves_nothing():
    subscriptions = FakeSubscriptionRepository()
    active_plan(subscriptions)
    repository = FakeClinicSubscriptionChargeRepository()
    payments = FakePaymentsApi(unavailable=True)

    with pytest.raises(PaymentsUnavailableError):
        await service(repository, subscriptions, payments=payments).charge(
            CLINIC_SUBSCRIPTION_ID, PERIOD, caller(), TOKEN
        )

    assert await repository.get_by_period(CLINIC_SUBSCRIPTION_ID, PERIOD) is None


# --- historia 2: sync a pending charge on read ---


async def test_get_charge_syncs_a_pending_charge_to_approved():
    repository = FakeClinicSubscriptionChargeRepository()
    charge = repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=charge.payment_id, status="approved", checkout_url=None, amount=129900, currency="MXN")
    )

    result = await service(repository, payments=payments).get_charge(CLINIC_SUBSCRIPTION_ID, charge.id)

    assert result.payment_status == "approved"
    assert result.checkout_url is None


async def test_get_charge_syncs_a_pending_charge_to_rejected():
    repository = FakeClinicSubscriptionChargeRepository()
    charge = repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(
        payment=PaymentView(id=charge.payment_id, status="rejected", checkout_url=None, amount=129900, currency="MXN")
    )

    result = await service(repository, payments=payments).get_charge(CLINIC_SUBSCRIPTION_ID, charge.id)

    assert result.payment_status == "rejected"


async def test_get_charge_keeps_the_local_status_when_payments_api_is_down():
    repository = FakeClinicSubscriptionChargeRepository()
    charge = repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="pending"
    )
    payments = FakePaymentsApi(unavailable=True)

    result = await service(repository, payments=payments).get_charge(CLINIC_SUBSCRIPTION_ID, charge.id)

    assert result.payment_status == "pending"


async def test_get_charge_never_calls_payments_api_for_a_resolved_charge():
    repository = FakeClinicSubscriptionChargeRepository()
    charge = repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="approved"
    )
    payments = FakePaymentsApi()

    await service(repository, payments=payments).get_charge(CLINIC_SUBSCRIPTION_ID, charge.id)

    assert payments.get_calls == []


async def test_get_charge_not_found():
    with pytest.raises(ClinicSubscriptionChargeNotFoundError):
        await service().get_charge(CLINIC_SUBSCRIPTION_ID, 999)


async def test_get_charge_of_another_clinic_subscription_is_not_found():
    repository = FakeClinicSubscriptionChargeRepository()
    charge = repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=PERIOD, payment_id=uuid4(), payment_status="approved"
    )

    with pytest.raises(ClinicSubscriptionChargeNotFoundError):
        await service(repository).get_charge(uuid4(), charge.id)


# --- historia 3: list the history ---


async def test_list_charges_is_paginated_most_recent_first():
    repository = FakeClinicSubscriptionChargeRepository()
    repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=date(2026, 11, 1), payment_id=uuid4(),
        payment_status="approved",
    )
    repository.add_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, period=date(2026, 12, 1), payment_id=uuid4(),
        payment_status="approved",
    )

    charges, total = await service(repository).list_charges(CLINIC_SUBSCRIPTION_ID, page=1, limit=1)

    assert total == 2
    assert [c.period for c in charges] == [date(2026, 12, 1)]

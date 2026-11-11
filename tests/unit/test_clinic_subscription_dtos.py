"""DTOs of the clinic subscriptions: the rules of every field (spec 006, error-catalog.md)."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.dtos.clinic_subscription import (
    ClinicSubscriptionChargeRead,
    ClinicSubscriptionCreate,
    ClinicSubscriptionRead,
)
from src.error_handlers import translate_validation_errors

TENANT = UUID("3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f")


def create_body(**overrides) -> dict:
    return {
        "tenant_id": str(TENANT),
        "subscription_id": 1,
        "billing_cycle": "monthly",
        **overrides,
    }


# --- ClinicSubscriptionCreate ---


def test_a_minimal_valid_body_parses():
    data = ClinicSubscriptionCreate.model_validate(create_body())

    assert data.tenant_id == TENANT
    assert data.started_at is None


@pytest.mark.parametrize("field", ["tenant_id", "subscription_id", "billing_cycle"])
def test_the_required_fields_are_required(field):
    body = create_body()
    del body[field]

    with pytest.raises(ValidationError):
        ClinicSubscriptionCreate.model_validate(body)


def test_tenant_id_must_be_a_uuid():
    with pytest.raises(ValidationError) as error:
        ClinicSubscriptionCreate.model_validate(create_body(tenant_id="not-a-uuid"))

    message = translate_validation_errors(error.value.errors(), "clinic-subscriptions")
    assert message[0].field == "tenant_id"
    assert "UUID" in message[0].message


def test_subscription_id_must_be_a_positive_integer():
    with pytest.raises(ValidationError):
        ClinicSubscriptionCreate.model_validate(create_body(subscription_id=0))


@pytest.mark.parametrize("value", ["weekly", "", "MONTHLY", "annual "])
def test_billing_cycle_rejects_anything_other_than_monthly_or_annual(value):
    with pytest.raises(ValidationError) as error:
        ClinicSubscriptionCreate.model_validate(create_body(billing_cycle=value))

    message = translate_validation_errors(error.value.errors(), "clinic-subscriptions")
    assert message[0].field == "billing_cycle"


def test_billing_cycle_accepts_both_values():
    assert ClinicSubscriptionCreate.model_validate(create_body(billing_cycle="monthly")).billing_cycle == "monthly"
    assert ClinicSubscriptionCreate.model_validate(create_body(billing_cycle="annual")).billing_cycle == "annual"


def test_started_at_is_optional_and_accepts_an_explicit_datetime():
    moment = datetime(2026, 12, 1, tzinfo=UTC)

    data = ClinicSubscriptionCreate.model_validate(create_body(started_at=moment.isoformat()))

    assert data.started_at == moment


def test_an_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        ClinicSubscriptionCreate.model_validate(create_body(status="x"))


# --- ClinicSubscriptionRead / ClinicSubscriptionChargeRead: serialise ORM-shaped objects ---


def clinic_subscription_row(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        tenant_id=TENANT,
        subscription_id=2,
        billing_cycle="monthly",
        started_at=datetime(2026, 11, 10, tzinfo=UTC),
        next_billing_at=datetime(2026, 11, 10, tzinfo=UTC),
        status=SimpleNamespace(id=1, name="Activa"),
        created_at=datetime(2026, 11, 10, tzinfo=UTC),
        updated_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    return SimpleNamespace(**{**base, **overrides})


def charge_row(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        clinic_subscription_id=1,
        period=date(2026, 11, 10),
        amount=129900,
        currency="MXN",
        payment_id=uuid4(),
        payment_status="pending",
        checkout_url="https://pagos.test/checkout/x",
        created_at=datetime(2026, 11, 10, tzinfo=UTC),
        updated_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    return SimpleNamespace(**{**base, **overrides})


def test_clinic_subscription_read_serialises_the_status_object():
    read = ClinicSubscriptionRead.model_validate(clinic_subscription_row())

    assert read.status.id == 1
    assert read.status.name == "Activa"
    assert read.current_charge is None


def test_current_charge_can_be_set_explicitly_after_validation():
    read = ClinicSubscriptionRead.model_validate(clinic_subscription_row())
    read.current_charge = ClinicSubscriptionChargeRead.model_validate(charge_row())

    assert read.current_charge.payment_status == "pending"


def test_charge_read_amount_is_an_integer_of_cents_not_a_decimal_string():
    read = ClinicSubscriptionChargeRead.model_validate(charge_row(amount=129900))

    dumped = read.model_dump(mode="json")

    assert dumped["amount"] == 129900
    assert isinstance(dumped["amount"], int)


def test_charge_read_checkout_url_is_null_once_resolved():
    read = ClinicSubscriptionChargeRead.model_validate(charge_row(payment_status="approved", checkout_url=None))

    assert read.checkout_url is None

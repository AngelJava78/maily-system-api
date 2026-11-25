"""The response DTOs of the subscription periods (spec 010, data-model.md section 6; FR-011, FR-015).

The charge history DTOs (spec 012) are at the bottom of this file.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.dtos.subscription_period import (
    PlanRead,
    SubscriptionChargeRead,
    SubscriptionChargesPageRead,
    SubscriptionPaymentRead,
    SubscriptionPeriodRead,
)

KEYS = {
    "state",
    "trial_ends_at",
    "payment_due_at",
    "days_remaining",
    "subscription",
    "billing_period",
    "amount",
    "currency",
    "payment_in_progress",
}
DUE = datetime(2026, 12, 4, 15, 30, tzinfo=UTC)


def period(**changes) -> SubscriptionPeriodRead:
    values = {
        "state": "trial",
        "trial_ends_at": DUE,
        "payment_due_at": DUE,
        "days_remaining": 9,
        "subscription": PlanRead(id=3, name="Plan Individual"),
        "billing_period": "monthly",
        "amount": Decimal("499.00"),
        "currency": "MXN",
        "payment_in_progress": False,
        **changes,
    }
    return SubscriptionPeriodRead(**values)


def test_the_period_has_its_nine_keys_in_the_json():
    assert set(period().model_dump(mode="json")) == KEYS


def test_a_period_that_cannot_say_a_value_publishes_it_as_null_never_omitted():
    body = period(
        state="no_charge",
        trial_ends_at=None,
        payment_due_at=None,
        days_remaining=None,
        payment_in_progress=None,
        amount=Decimal("0.00"),
    ).model_dump(mode="json")

    assert set(body) == KEYS
    assert body["trial_ends_at"] is None
    assert body["payment_due_at"] is None
    assert body["days_remaining"] is None
    assert body["payment_in_progress"] is None


def test_the_dates_are_published_in_utc_with_z():
    body = period().model_dump(mode="json")

    assert body["trial_ends_at"] == "2026-12-04T15:30:00Z"
    assert body["payment_due_at"] == "2026-12-04T15:30:00Z"


def test_a_date_that_arrives_in_another_zone_is_published_in_utc():
    local = datetime(2026, 12, 4, 9, 30, tzinfo=timezone(timedelta(hours=-6)))

    body = period(trial_ends_at=local, payment_due_at=local).model_dump(mode="json")

    assert body["trial_ends_at"] == "2026-12-04T15:30:00Z"
    assert body["payment_due_at"] == "2026-12-04T15:30:00Z"


def test_a_date_without_a_zone_is_refused():
    with pytest.raises(ValidationError):
        period(trial_ends_at=datetime(2026, 12, 4, 15, 30))


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (Decimal("499.00"), "499.00"),
        (Decimal("499"), "499.00"),
        (Decimal("0.00"), "0.00"),
        (Decimal("4990.00"), "4990.00"),
        (Decimal("1234567.8"), "1234567.80"),
        (Decimal("0.1"), "0.10"),
    ],
)
def test_the_amount_is_published_as_text_with_two_decimals(amount, text):
    assert period(amount=amount).model_dump(mode="json")["amount"] == text
    assert SubscriptionPaymentRead(
        checkout_url="https://x.test/pay", amount=amount, currency="MXN", billing_period="monthly"
    ).model_dump(mode="json")["amount"] == text


def test_the_subscription_is_the_plan_with_its_id_and_name():
    body = period().model_dump(mode="json")

    assert body["subscription"] == {"id": 3, "name": "Plan Individual"}


@pytest.mark.parametrize("state", ["trial", "current", "overdue", "no_charge"])
def test_the_four_states_are_accepted(state):
    assert period(state=state).state == state


@pytest.mark.parametrize("value", ["TRIAL", "expired", "paid", "", None])
def test_another_state_is_refused(value):
    with pytest.raises(ValidationError):
        period(state=value)


@pytest.mark.parametrize("value", ["weekly", "MONTHLY", "", None])
def test_another_billing_period_is_refused(value):
    with pytest.raises(ValidationError):
        period(billing_period=value)


@pytest.mark.parametrize("value", ["USD", "mxn", "", None])
def test_only_mexican_pesos_are_accepted(value):
    with pytest.raises(ValidationError):
        period(currency=value)


@pytest.mark.parametrize("value", [True, False, None])
def test_the_charge_in_progress_is_true_false_or_unknown(value):
    assert period(payment_in_progress=value).payment_in_progress is value


@pytest.mark.parametrize("missing", sorted(KEYS))
def test_every_field_is_mandatory(missing):
    values = {
        "state": "trial",
        "trial_ends_at": DUE,
        "payment_due_at": DUE,
        "days_remaining": 9,
        "subscription": PlanRead(id=3, name="Plan"),
        "billing_period": "monthly",
        "amount": Decimal("499.00"),
        "currency": "MXN",
        "payment_in_progress": False,
    }
    del values[missing]

    with pytest.raises(ValidationError):
        SubscriptionPeriodRead(**values)


def test_the_published_schema_lists_the_nine_fields_as_required():
    schema = SubscriptionPeriodRead.model_json_schema(mode="serialization")

    assert set(schema["required"]) == KEYS
    assert schema["properties"]["amount"]["type"] == "string"
    assert schema["properties"]["state"]["enum"] == ["trial", "current", "overdue", "no_charge"]
    # A literal with one value is published as a constant.
    currency = schema["properties"]["currency"]
    assert currency.get("const") == "MXN" or currency.get("enum") == ["MXN"]


def test_the_payment_start_has_its_four_fields():
    body = SubscriptionPaymentRead(
        checkout_url="https://checkout.example.test/pay/1",
        amount=Decimal("4990.00"),
        currency="MXN",
        billing_period="annual",
    ).model_dump(mode="json")

    assert body == {
        "checkout_url": "https://checkout.example.test/pay/1",
        "amount": "4990.00",
        "currency": "MXN",
        "billing_period": "annual",
    }


ALL_DTOS = (
    SubscriptionPeriodRead,
    SubscriptionPaymentRead,
    PlanRead,
    SubscriptionChargeRead,
    SubscriptionChargesPageRead,
)


@pytest.mark.parametrize(
    "forbidden", ["token", "payment_id", "authorization", "organization_id", "base_url", "tenant_id", "attempt"]
)
def test_no_dto_has_a_field_for_a_token_a_payment_identifier_or_an_address(forbidden):
    for dto in ALL_DTOS:
        assert forbidden not in dto.model_fields


def test_the_descriptions_of_the_fields_are_in_spanish_and_exist():
    for dto in ALL_DTOS:
        for name, field in dto.model_fields.items():
            assert field.description, f"{dto.__name__}.{name} has no description"


# =============================== spec 012: the history of charges ===============================

CHARGE_KEYS = {
    "id",
    "status",
    "closed_reason",
    "amount",
    "currency",
    "billing_period",
    "period_starts_at",
    "period_ends_at",
    "created_at",
}
CHARGE_ID = uuid.UUID("6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70")
CREATED_AT = datetime(2026, 10, 19, 11, 58, 3, tzinfo=UTC)
PERIOD_START = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
PERIOD_END = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def charge(**changes) -> SubscriptionChargeRead:
    values = {
        "id": CHARGE_ID,
        "status": "applied",
        "closed_reason": None,
        "amount": Decimal("499.00"),
        "currency": "MXN",
        "billing_period": "monthly",
        "period_starts_at": PERIOD_START,
        "period_ends_at": PERIOD_END,
        "created_at": CREATED_AT,
        **changes,
    }
    return SubscriptionChargeRead(**values)


def test_an_applied_charge_has_its_nine_keys_and_both_period_dates():
    body = charge().model_dump(mode="json")

    assert set(body) == CHARGE_KEYS
    assert body["closed_reason"] is None
    assert body["period_starts_at"] == "2026-10-19T12:00:00Z"
    assert body["period_ends_at"] == "2026-11-19T12:00:00Z"
    assert body["created_at"] == "2026-10-19T11:58:03Z"


def test_a_pending_charge_has_no_period_dates_and_no_closed_reason():
    body = charge(status="pending", closed_reason=None, period_starts_at=None, period_ends_at=None).model_dump(
        mode="json"
    )

    assert (body["status"], body["closed_reason"]) == ("pending", None)
    assert body["period_starts_at"] is None and body["period_ends_at"] is None


@pytest.mark.parametrize("reason", ["rejected", "cancelled", "inconsistent", "refunded"])
def test_a_closed_charge_has_its_reason_and_no_period_dates(reason):
    body = charge(
        status="closed", closed_reason=reason, period_starts_at=None, period_ends_at=None
    ).model_dump(mode="json")

    assert (body["status"], body["closed_reason"]) == ("closed", reason)
    assert body["period_starts_at"] is None and body["period_ends_at"] is None


@pytest.mark.parametrize("value", ["approved", "PENDING", "", None])
def test_another_charge_status_is_refused(value):
    with pytest.raises(ValidationError):
        charge(status=value)


@pytest.mark.parametrize("value", ["expired", "REJECTED", ""])
def test_another_closed_reason_is_refused(value):
    with pytest.raises(ValidationError):
        charge(status="closed", closed_reason=value, period_starts_at=None, period_ends_at=None)


def test_the_amount_of_a_charge_is_published_as_text_with_two_decimals():
    assert charge(amount=Decimal("1234567.8")).model_dump(mode="json")["amount"] == "1234567.80"


def test_a_charge_date_without_a_zone_is_refused():
    with pytest.raises(ValidationError):
        charge(created_at=datetime(2026, 10, 19, 11, 58, 3))


def test_a_charge_date_in_another_zone_is_published_in_utc():
    local = datetime(2026, 10, 19, 5, 58, 3, tzinfo=timezone(timedelta(hours=-6)))

    assert charge(created_at=local).model_dump(mode="json")["created_at"] == "2026-10-19T11:58:03Z"


def test_the_id_of_a_charge_is_published_as_text():
    assert charge().model_dump(mode="json")["id"] == str(CHARGE_ID)


def page(**changes) -> SubscriptionChargesPageRead:
    values = {"items": [charge()], "total": 1, "page": 1, "page_size": 10, "total_pages": 1, **changes}
    return SubscriptionChargesPageRead(**values)


def test_a_page_has_its_five_keys():
    body = page().model_dump(mode="json")

    assert set(body) == {"items", "total", "page", "page_size", "total_pages"}
    assert len(body["items"]) == 1


def test_an_empty_page_publishes_an_empty_list_never_null():
    body = page(items=[], total=0, total_pages=0).model_dump(mode="json")

    assert body["items"] == []
    assert (body["total"], body["total_pages"]) == (0, 0)


@pytest.mark.parametrize(("field", "value"), [("total", -1), ("page", 0), ("page_size", 0), ("total_pages", -1)])
def test_the_pagination_numbers_cannot_be_negative_or_zero_where_it_does_not_apply(field, value):
    with pytest.raises(ValidationError):
        page(**{field: value})


def test_the_published_schema_of_the_page_lists_its_five_fields_as_required():
    schema = SubscriptionChargesPageRead.model_json_schema(mode="serialization")

    assert set(schema["required"]) == {"items", "total", "page", "page_size", "total_pages"}

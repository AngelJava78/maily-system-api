"""When another API fails, the subscription periods degrade without inventing anything (spec 010, story 6).

The table of FR-035 to FR-038 (Principle IX), cell by cell, against simulations that fail one at a time:

- the users API or the clinics API down: 503 in both operations, nothing created or changed (the access
  fails closed: without them the person cannot be proved to be the owner);
- the payments API down when consulting: what is stored, with the charge in progress marked as «could
  not be verified» (`null`), never a made-up `false`; nothing in Pagos to ask: a normal answer;
- the payments API down when starting the payment: 503 and no new charge.

No answer and no log of ours carries an address, a token or the body of another API.
"""

import logging
import uuid

import pytest
from sqlalchemy import text

from tests.billing_support import ORG_ID, TEST_TOKEN, BillingApi, at
from tests.helpers import CLINICS_BASE_URL, PAYMENTS_BASE_URL, USERS_BASE_URL

CREATED = "2026-11-20T15:30:00Z"
TRIAL_END = "2026-12-04T15:30:00Z"
INTERNAL_MARKER = "SECRETO-INTERNO"  # inside every error of the simulations
SECRETS = (INTERNAL_MARKER, TEST_TOKEN, USERS_BASE_URL, CLINICS_BASE_URL, PAYMENTS_BASE_URL, "evil.test")
# The ways in which the payments API can fail (its simulation understands all of them).
PAYMENTS_FAILURES = [
    "unavailable",
    "unauthorized",
    "forbidden",
    "organization_required",
    "malformed",
    "not_json",
    "redirect",
    "slow",
    "unknown_status",
]
USERS_FAILURES = [
    "unavailable",
    "rate_limited",
    "forbidden",
    "malformed",
    "wrong_permission",
    "not_json",
    "redirect",
    "slow",
]


@pytest.fixture
async def plan_id(billing_api: BillingApi) -> int:
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at=CREATED)
    return plan


async def fail_payments(api: BillingApi, mode: str, operation: str = "any", count: int = 99) -> None:
    if mode == "slow":
        api.timeouts["payments"] = 0.2
        await api.payments_fault("slow", count=count, operation=operation, delay=1)
    else:
        await api.payments_fault(mode, count=count, operation=operation)


def assert_clean(response, caplog: pytest.LogCaptureFixture) -> None:
    """Nothing of another API (its address, its error, a credential) reaches the person or our logs."""
    for secret in SECRETS:
        assert secret not in response.text, secret
        ours = [r for r in caplog.records if r.name.startswith("src")]
        assert all(secret not in r.getMessage() for r in ours), secret
        assert all(secret not in str(r.args) for r in ours), secret


async def pending_charge(api: BillingApi) -> None:
    """A charge that Pagos still has to decide, the way a person leaves it after opening the checkout."""
    assert (await api.start_payment()).status_code == 201


async def insert_charge_unknown_to_pagos(api: BillingApi, amount: str = "499.00") -> uuid.UUID:
    """A pending charge whose payment the payments API does not know (it answers 404 for it).

    There is one unresolved charge at most for each period and amount, so a second one needs another amount.
    """
    payment_id = uuid.uuid4()
    async with api.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO subscription_charges (organization_id, payment_id, amount, currency, "
                "billing_period, settles_due_at, attempt) "
                "VALUES (:organization_id, :payment_id, :amount, 'MXN', 'monthly', :due, 1)"
            ),
            {"organization_id": ORG_ID, "payment_id": payment_id, "amount": amount, "due": at(TRIAL_END)},
        )
    return payment_id


# =============================== the users API fails (access fails closed) ===============================


@pytest.mark.parametrize("operation", ["consult", "pay"])
@pytest.mark.parametrize("mode", USERS_FAILURES)
async def test_when_the_permission_cannot_be_verified_nothing_is_done(
    billing_api: BillingApi, plan_id: int, caplog, operation: str, mode: str
):
    caplog.set_level(logging.DEBUG)
    if mode == "slow":
        billing_api.timeouts["users"] = 0.2
        await billing_api.users_fault("slow", delay=1)
    else:
        await billing_api.users_fault(mode)

    response = await (billing_api.get_period() if operation == "consult" else billing_api.start_payment())

    assert response.status_code == 503
    assert response.json()["code"] == "authorization_unavailable"
    assert response.json()["message"].startswith("No se pudo")  # the message in Spanish, the code in English
    assert set(response.json()) == {"code", "message"}  # no date, no amount, no state
    assert_clean(response, caplog)
    assert await billing_api.snapshot() == []
    assert await billing_api.clinics_calls() == [] and await billing_api.payments_calls() == []


# =============================== the clinics API fails (nobody is the owner without it) ===============================


@pytest.mark.parametrize("operation", ["consult", "pay"])
async def test_when_the_organization_cannot_be_checked_nothing_is_created_and_nothing_is_invented(
    billing_api: BillingApi, plan_id: int, caplog, operation: str
):
    caplog.set_level(logging.DEBUG)
    await billing_api.clinics_fault("unavailable")

    response = await (billing_api.get_period() if operation == "consult" else billing_api.start_payment())

    assert response.status_code == 503
    assert response.json()["code"] == "organization_check_unavailable"
    assert set(response.json()) == {"code", "message"}  # no date, no amount, no state
    assert_clean(response, caplog)
    assert await billing_api.snapshot() == []
    assert await billing_api.payments_calls() == []  # without the organization there is nothing to charge


async def test_a_record_that_exists_is_not_served_when_the_organization_cannot_be_checked(
    billing_api: BillingApi, plan_id: int
):
    assert (await billing_api.get_period()).status_code == 200  # the record is stored now
    stored = await billing_api.snapshot()
    await billing_api.clinics_fault("unavailable")

    response = await billing_api.get_period()

    # Having the dates is not having the right to see them: the access fails closed.
    assert response.status_code == 503
    assert await billing_api.snapshot() == stored


# =============================== the payments API fails when consulting ===============================


@pytest.mark.parametrize("mode", PAYMENTS_FAILURES)
async def test_when_pagos_fails_the_consultation_answers_with_what_is_stored_and_says_it_could_not_verify(
    billing_api: BillingApi, plan_id: int, caplog, mode: str
):
    caplog.set_level(logging.DEBUG)
    await pending_charge(billing_api)
    healthy = (await billing_api.get_period()).json()
    stored = await billing_api.snapshot()
    await fail_payments(billing_api, mode, operation="get")

    response = await billing_api.get_period()

    assert response.status_code == 200
    body = response.json()
    assert body["payment_in_progress"] is None  # «could not be verified», never a made-up false
    assert body == {**healthy, "payment_in_progress": None}  # the dates, state and amount are the stored ones
    assert body["state"] == "trial" and body["payment_due_at"] == TRIAL_END
    assert_clean(response, caplog)
    assert await billing_api.snapshot() == stored  # the charge is still pending: nothing was decided


async def test_a_charge_that_pagos_does_not_know_is_not_decided_either(
    billing_api: BillingApi, plan_id: int, caplog
):
    caplog.set_level(logging.DEBUG)
    await billing_api.get_period()
    await insert_charge_unknown_to_pagos(billing_api)

    response = await billing_api.get_period()  # Pagos answers 404 for its payment

    assert response.status_code == 200
    assert response.json()["payment_in_progress"] is None
    assert_clean(response, caplog)
    assert (await billing_api.charges())[0][7] == "pending"


@pytest.mark.parametrize("mode", PAYMENTS_FAILURES)
async def test_when_there_is_nothing_to_verify_pagos_is_not_asked_and_its_failure_does_not_matter(
    billing_api: BillingApi, plan_id: int, mode: str
):
    await fail_payments(billing_api, mode)

    response = await billing_api.get_period()

    assert response.status_code == 200
    assert response.json()["payment_in_progress"] is False  # nothing is unresolved: a real false
    assert await billing_api.payments_calls() == []


async def test_a_charge_that_pagos_still_reports_as_pending_is_in_progress_even_if_another_could_not_be_verified(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await pending_charge(billing_api)  # monthly, 499.00: verifiable
    await insert_charge_unknown_to_pagos(billing_api, "799.00")  # the one that Pagos cannot answer for

    body = (await billing_api.get_period()).json()

    assert body["payment_in_progress"] is True  # one pending was verified: there is a charge in progress


async def test_a_charge_that_could_not_be_verified_is_decided_by_the_next_consultation(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await pending_charge(billing_api)
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, "approved", updated_at="2026-12-10T09:30:00Z")
    billing_api.clock.set(at("2026-12-10T09:45:00Z"))  # after the approval: it cannot be in the future (FR-031)
    await fail_payments(billing_api, "unavailable", operation="get", count=1)

    degraded = (await billing_api.get_period()).json()
    recovered = (await billing_api.get_period()).json()

    assert (degraded["state"], degraded["payment_in_progress"]) == ("overdue", None)  # the date has not moved
    assert (recovered["state"], recovered["payment_in_progress"]) == ("current", False)
    assert recovered["payment_due_at"] == "2027-01-10T09:30:00Z"  # Pagos came back: the payment counts, once


# =============================== the payments API fails when starting the payment ===============================


@pytest.mark.parametrize("mode", [m for m in PAYMENTS_FAILURES if m != "unknown_status"])
async def test_when_pagos_fails_the_payment_is_not_started_and_no_charge_is_registered(
    billing_api: BillingApi, plan_id: int, caplog, mode: str
):
    caplog.set_level(logging.DEBUG)
    await fail_payments(billing_api, mode, operation="create")

    response = await billing_api.start_payment()

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"
    assert response.json()["message"].startswith("No se pudo")
    assert set(response.json()) == {"code", "message"}  # no checkout, no amount
    assert_clean(response, caplog)
    assert await billing_api.charges() == []  # no charge without a payment
    assert (await billing_api.get_period()).json()["payment_in_progress"] is False


async def test_an_answer_that_is_lost_is_recovered_by_the_next_attempt_with_the_same_payment(
    billing_api: BillingApi, plan_id: int, caplog
):
    # Pagos created the payment, but its answer cannot be understood: nothing is registered, so the
    # person is told to try again; the same key then gives the same payment and it is registered once.
    caplog.set_level(logging.DEBUG)
    await billing_api.payments_fault("unknown_status", count=1, operation="create")

    lost = await billing_api.start_payment()
    assert lost.status_code == 503 and lost.json()["code"] == "payments_unavailable"
    assert_clean(lost, caplog)
    assert await billing_api.charges() == []
    assert len(await billing_api.payments()) == 1  # it exists in Pagos

    retry = await billing_api.start_payment()

    assert retry.status_code == 201
    assert len(await billing_api.payments()) == 1  # not a second payment
    [charge] = await billing_api.charges()
    assert str(charge[1]) == (await billing_api.payments())[0]["id"]


async def test_a_failure_of_pagos_does_not_outlive_it(billing_api: BillingApi, plan_id: int):
    await billing_api.payments_fault("unavailable", count=1, operation="create")
    assert (await billing_api.start_payment()).status_code == 503

    response = await billing_api.start_payment()

    assert response.status_code == 201


@pytest.mark.parametrize("mode", ["unavailable", "unknown_status"])
async def test_when_pagos_cannot_confirm_the_existing_charge_the_payment_is_not_offered(
    billing_api: BillingApi, plan_id: int, caplog, mode: str
):
    caplog.set_level(logging.DEBUG)
    await pending_charge(billing_api)
    await fail_payments(billing_api, mode, operation="get")

    response = await billing_api.start_payment()

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"
    assert_clean(response, caplog)
    assert len(await billing_api.charges()) == 1  # and no second charge for the same period
    assert len(await billing_api.payments()) == 1

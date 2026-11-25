"""The two operations of the subscription periods over HTTP (spec 010; stories 1 to 3 and 5).

The real application with the real PostgreSQL, the three simulated APIs and a clock that each test moves
(`billing_api`). The dates are the ones of «Ejemplos de referencia del cálculo de fechas» of the spec.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from src.config import get_billing_settings
from src.services.billing_rules import idempotency_key
from tests.billing_support import ORG_ID, TEST_TOKEN, BillingApi, at

CREATED = "2026-11-20T15:30:00Z"
TRIAL_END = "2026-12-04T15:30:00Z"
BODY_KEYS = {
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


@pytest.fixture
async def plan_id(billing_api: BillingApi) -> int:
    """A plan of 14 days of trial, 499.00 a month and 4990.00 a year; the organization is on it."""
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at=CREATED)
    return plan


def trial_body(plan_id: int, **changes) -> dict:
    return {
        "state": "trial",
        "trial_ends_at": TRIAL_END,
        "payment_due_at": TRIAL_END,
        "days_remaining": 9,
        "subscription": {"id": plan_id, "name": "Plan Individual"},
        "billing_period": "monthly",
        "amount": "499.00",
        "currency": "MXN",
        "payment_in_progress": False,
        **changes,
    }


# =============================== story 1: the consultation ===============================


async def test_scenario_1_an_organization_in_trial(billing_api: BillingApi, plan_id: int):
    response = await billing_api.get_period()

    assert response.status_code == 200
    assert response.json() == trial_body(plan_id)
    assert set(response.json()) == BODY_KEYS


async def test_scenario_9_the_answer_is_not_cached_and_the_dates_are_in_utc(billing_api: BillingApi, plan_id: int):
    response = await billing_api.get_period()

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["trial_ends_at"].endswith("Z")
    assert response.json()["payment_due_at"].endswith("Z")


async def test_scenario_2_the_same_organization_overdue(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))

    body = (await billing_api.get_period()).json()

    assert body == trial_body(plan_id, state="overdue", days_remaining=-5)


@pytest.mark.parametrize(
    ("now", "state", "days"),
    [
        ("2026-11-25T16:00:00Z", "trial", 9),
        ("2026-12-03T15:30:01Z", "trial", 1),
        ("2026-12-04T15:30:00Z", "overdue", 0),
    ],
)
async def test_the_state_and_the_days_follow_the_clock(billing_api: BillingApi, plan_id: int, now, state, days):
    billing_api.clock.set(at(now))

    body = (await billing_api.get_period()).json()

    assert (body["state"], body["days_remaining"]) == (state, days)


async def test_scenario_3_without_a_trial_the_first_payment_is_due_at_the_start(billing_api: BillingApi):
    plan = await billing_api.add_plan(name="Sin prueba", trial_days=0)
    await billing_api.register_organization(plan, created_at=CREATED)
    billing_api.clock.set(at("2026-11-21T09:00:00Z"))

    body = (await billing_api.get_period()).json()

    assert body["trial_ends_at"] is None
    assert body["payment_due_at"] == CREATED
    assert (body["state"], body["days_remaining"]) == ("overdue", 0)


async def test_scenario_4_a_free_plan_has_no_charge_and_no_payment_date(billing_api: BillingApi):
    plan = await billing_api.add_plan(name="Gratuito", monthly_price="0.00", annual_price="0.00")
    await billing_api.register_organization(plan, created_at=CREATED)

    body = (await billing_api.get_period()).json()

    assert body["state"] == "no_charge"
    assert (body["payment_due_at"], body["days_remaining"]) == (None, None)
    assert body["amount"] == "0.00"
    assert set(body) == BODY_KEYS  # the keys are there even when they are null


async def test_the_annual_billing_period_charges_the_annual_price(billing_api: BillingApi):
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, billing_period="annual", created_at=CREATED)

    body = (await billing_api.get_period()).json()

    assert (body["billing_period"], body["amount"]) == ("annual", "4990.00")


async def test_scenario_5_an_organization_older_than_the_cutoff_starts_at_the_cutoff(
    billing_api: BillingApi, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BILLING_CUTOFF_AT", "2026-11-18T00:00:00Z")
    get_billing_settings.cache_clear()
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at="2026-06-01T12:00:00Z")
    billing_api.clock.set(at("2026-11-25T00:00:00Z"))

    body = (await billing_api.get_period()).json()

    assert body["trial_ends_at"] == "2026-12-02T00:00:00Z"
    assert (body["state"], body["days_remaining"]) == ("trial", 7)
    [(_, started, *_)] = await billing_api.periods()
    assert started == at("2026-11-18T00:00:00Z")


async def test_the_record_is_created_once_and_the_second_consultation_does_not_change_it(
    billing_api: BillingApi, plan_id: int
):
    first = await billing_api.get_period()
    rows = await billing_api.periods()
    second = await billing_api.get_period()

    assert len(rows) == 1
    assert await billing_api.periods() == rows
    assert second.json() == first.json()


async def test_scenario_7_ten_simultaneous_first_consultations_create_one_record(
    billing_api: BillingApi, plan_id: int
):
    responses = await asyncio.gather(*(billing_api.get_period() for _ in range(10)))

    assert [r.status_code for r in responses] == [200] * 10
    assert len({r.text for r in responses}) == 1  # the same dates in all of them
    assert len(await billing_api.periods()) == 1


async def test_scenario_6_a_change_of_plan_and_of_its_trial_days_does_not_move_the_dates(
    billing_api: BillingApi, plan_id: int
):
    first = (await billing_api.get_period()).json()

    # The catalog changes the trial days of the plan and the organization moves to another plan.
    async with billing_api.engine.begin() as connection:
        await connection.execute(text("UPDATE subscriptions SET trial_days = 90 WHERE id = :id"), {"id": plan_id})
    other = await billing_api.add_plan(name="Plan Empresarial", trial_days=60, monthly_price="999.00")
    await billing_api.register_organization(other, created_at=CREATED)
    second = (await billing_api.get_period()).json()

    assert (second["trial_ends_at"], second["payment_due_at"]) == (first["trial_ends_at"], first["payment_due_at"])
    assert second["subscription"] == {"id": other, "name": "Plan Empresarial"}
    assert second["amount"] == "999.00"


async def test_a_consultation_writes_nothing_but_the_period(billing_api: BillingApi, plan_id: int):
    await billing_api.get_period()

    assert await billing_api.charges() == []
    assert await billing_api.payments_calls() == []  # Pagos is not asked when there is nothing to verify
    assert [c["path"] for c in await billing_api.clinics_calls()] == [f"/api/v1/organizations/{ORG_ID}"]
    assert [c["authorization"] for c in await billing_api.clinics_calls()] == [f"Bearer {TEST_TOKEN}"]


# ============================ story 2: starting the payment ============================


async def test_scenario_1_starting_the_payment_creates_the_charge_and_returns_the_checkout(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))

    response = await billing_api.start_payment()

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"checkout_url", "amount", "currency", "billing_period"}
    assert (body["amount"], body["currency"], body["billing_period"]) == ("499.00", "MXN", "monthly")
    # What Pagos received: one payment with the amount in the minimum unit and the reference.
    [payment] = await billing_api.payments()
    assert (payment["amount"], payment["currency"]) == (49900, "MXN")
    assert (payment["resource_type"], payment["resource_id"]) == ("system-api:subscription", str(ORG_ID))
    assert body["checkout_url"] == payment["checkout_url"]
    [call] = await billing_api.payments_calls()
    assert call["authorization"] == f"Bearer {TEST_TOKEN}"
    assert call["idempotency_key"] == idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 1, "Suscripción Plan Individual — mensual")
    # And the charge that this service registered.
    [charge] = await billing_api.charges()
    assert charge[0] == ORG_ID
    assert str(charge[1]) == payment["id"]
    assert (charge[2], charge[3], charge[4]) == (Decimal("499.00"), "MXN", "monthly")
    assert (charge[5], charge[6], charge[7]) == (at(TRIAL_END), 1, "pending")


async def test_scenario_9_the_answers_are_not_cached(billing_api: BillingApi, plan_id: int):
    created = await billing_api.start_payment()
    existing = await billing_api.start_payment()

    assert (created.status_code, existing.status_code) == (201, 200)
    assert created.headers["cache-control"] == existing.headers["cache-control"] == "no-store"


async def test_scenario_2_an_annual_organization_pays_the_annual_price(billing_api: BillingApi):
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, billing_period="annual", created_at=CREATED)

    response = await billing_api.start_payment()

    assert (response.json()["amount"], response.json()["billing_period"]) == ("4990.00", "annual")
    [payment] = await billing_api.payments()
    assert payment["amount"] == 499000


async def test_scenario_3_starting_twice_gives_the_same_checkout_and_one_charge(
    billing_api: BillingApi, plan_id: int
):
    first = await billing_api.start_payment()
    second = await billing_api.start_payment()

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    assert len(await billing_api.payments()) == 1
    assert len(await billing_api.charges()) == 1


async def test_scenario_4_what_the_request_says_about_the_amount_is_ignored(billing_api: BillingApi, plan_id: int):
    response = await billing_api.start_payment(
        json={"amount": 1, "currency": "USD", "billing_period": "annual", "organization_id": str(uuid.uuid4())}
    )

    assert response.status_code == 201
    assert (response.json()["amount"], response.json()["currency"], response.json()["billing_period"]) == (
        "499.00",
        "MXN",
        "monthly",
    )
    [payment] = await billing_api.payments()
    assert (payment["amount"], payment["currency"], payment["resource_id"]) == (49900, "MXN", str(ORG_ID))


async def test_scenario_5_an_amount_of_zero_has_nothing_to_charge(billing_api: BillingApi):
    plan = await billing_api.add_plan(name="Gratuito", monthly_price="0.00", annual_price="0.00")
    await billing_api.register_organization(plan, created_at=CREATED)

    response = await billing_api.start_payment()

    assert response.status_code == 409
    assert response.json()["code"] == "nothing_to_charge"
    assert await billing_api.payments_calls() == []  # Pagos was not called
    assert await billing_api.charges() == []


async def test_scenario_6_when_pagos_cannot_create_the_payment_nothing_is_registered(
    billing_api: BillingApi, plan_id: int
):
    await billing_api.payments_fault("unavailable", operation="create")

    response = await billing_api.start_payment()

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"
    assert await billing_api.charges() == []
    assert await billing_api.payments() == []
    assert "SECRETO-INTERNO" not in response.text


async def test_scenario_7_after_a_closed_charge_a_new_start_gives_a_new_checkout(
    billing_api: BillingApi, plan_id: int
):
    first = await billing_api.start_payment()
    async with billing_api.engine.begin() as connection:
        await connection.execute(
            text("UPDATE subscription_charges SET status = 'closed', closed_reason = 'rejected', resolved_at = now()")
        )

    second = await billing_api.start_payment()

    assert second.status_code == 201
    assert second.json()["checkout_url"] != first.json()["checkout_url"]
    assert [row[6] for row in await billing_api.charges()] == [1, 2]  # the attempts
    assert len(await billing_api.payments()) == 2


@pytest.mark.parametrize("now", ["2026-11-25T15:30:00Z", "2026-12-04T15:00:00Z", "2026-12-10T09:00:00Z"])
async def test_scenario_8_the_payment_can_be_started_in_trial_or_overdue(billing_api: BillingApi, plan_id: int, now):
    billing_api.clock.set(at(now))

    response = await billing_api.start_payment()

    assert response.status_code == 201
    assert (await billing_api.charges())[0][5] == at(TRIAL_END)  # the date that it settles


async def test_two_simultaneous_starts_of_the_same_period_create_one_charge(billing_api: BillingApi, plan_id: int):
    responses = await asyncio.gather(*(billing_api.start_payment() for _ in range(2)))

    assert sorted(r.status_code for r in responses) == [200, 201]
    assert len(await billing_api.charges()) == 1
    assert len(await billing_api.payments()) == 1  # the same key gave the same payment
    assert responses[0].json() == responses[1].json()


async def test_scenario_10_another_amount_after_a_change_of_plan_is_another_charge(
    billing_api: BillingApi, plan_id: int
):
    first = await billing_api.start_payment()
    async with billing_api.engine.begin() as connection:
        await connection.execute(
            text("UPDATE subscriptions SET monthly_price = 799.00 WHERE id = :id"), {"id": plan_id}
        )

    second = await billing_api.start_payment()

    assert (second.status_code, second.json()["amount"]) == (201, "799.00")
    assert second.json()["checkout_url"] != first.json()["checkout_url"]
    amounts = [row[2] for row in await billing_api.charges()]
    assert amounts == [Decimal("499.00"), Decimal("799.00")]


async def test_starting_the_payment_creates_the_record_when_it_is_the_first_contact(
    billing_api: BillingApi, plan_id: int
):
    await billing_api.start_payment()

    [(organization, started, trial_ends, paid_until)] = await billing_api.periods()
    assert organization == ORG_ID
    assert (started, trial_ends, paid_until) == (at(CREATED), at(TRIAL_END), None)


# ================== story 3: the date moves, once, when the payment is approved ==================


async def start_and_approve(billing_api: BillingApi, approved_at: str, **changes) -> str:
    """Start the payment and mark it as approved in Pagos at `approved_at`; return its identifier."""
    assert (await billing_api.start_payment()).status_code == 201
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, "approved", updated_at=approved_at, **changes)
    return payment_id


async def test_scenario_1_a_payment_approved_during_the_trial_moves_the_date_and_keeps_the_trial(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await start_and_approve(billing_api, "2026-12-01T10:00:00Z")
    billing_api.clock.set(at("2026-12-01T10:05:00Z"))

    body = (await billing_api.get_period()).json()

    assert body == trial_body(
        plan_id,
        state="trial",
        payment_due_at="2027-01-04T15:30:00Z",
        days_remaining=35,
        payment_in_progress=False,
    )
    [(_, _, trial_ends, paid_until)] = await billing_api.periods()
    assert (trial_ends, paid_until) == (at(TRIAL_END), at("2027-01-04T15:30:00Z"))
    [charge] = await billing_api.charges()
    assert (charge[7], charge[9], charge[10]) == ("applied", at(TRIAL_END), at("2027-01-04T15:30:00Z"))


async def test_scenario_2_a_payment_approved_when_overdue_starts_at_the_approval(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await start_and_approve(billing_api, "2026-12-10T09:30:00Z")
    billing_api.clock.set(at("2026-12-10T09:45:00Z"))

    body = (await billing_api.get_period()).json()

    assert (body["state"], body["payment_due_at"], body["days_remaining"]) == (
        "current",
        "2027-01-10T09:30:00Z",
        31,
    )


async def test_scenario_5_the_date_moves_once_however_many_times_it_is_consulted(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await start_and_approve(billing_api, "2026-12-01T10:00:00Z")

    first = (await billing_api.get_period()).json()
    second = (await billing_api.get_period()).json()
    third = (await billing_api.get_period()).json()

    assert first["payment_due_at"] == second["payment_due_at"] == third["payment_due_at"] == "2027-01-04T15:30:00Z"
    [(_, _, _, paid_until)] = await billing_api.periods()
    assert paid_until == at("2027-01-04T15:30:00Z")


async def test_scenario_6_a_payment_approved_before_the_date_and_noticed_after_it_was_on_time(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-03T09:00:00Z"))
    await start_and_approve(billing_api, "2026-12-03T10:00:00Z")
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))  # nobody consulted until six days after the trial ended

    body = (await billing_api.get_period()).json()

    assert (body["state"], body["payment_due_at"], body["days_remaining"]) == ("current", "2027-01-04T15:30:00Z", 26)


async def test_scenario_7_a_rejected_payment_closes_the_charge_and_a_new_start_makes_a_new_one(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    first = await billing_api.start_payment()
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, "rejected")

    body = (await billing_api.get_period()).json()

    assert (body["state"], body["payment_in_progress"]) == ("overdue", False)
    [charge] = await billing_api.charges()
    assert (charge[7], charge[8]) == ("closed", "rejected")
    assert (await billing_api.periods())[0][3] is None  # the date did not move
    second = await billing_api.start_payment()
    assert second.status_code == 201
    assert second.json()["checkout_url"] != first.json()["checkout_url"]


async def test_scenario_8_an_approved_payment_with_another_amount_is_not_applied(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await start_and_approve(billing_api, "2026-12-10T09:30:00Z", amount=100)

    body = (await billing_api.get_period()).json()

    assert body["state"] == "overdue"
    [charge] = await billing_api.charges()
    assert (charge[7], charge[8]) == ("closed", "inconsistent")
    assert (await billing_api.periods())[0][3] is None


async def test_scenario_9_a_payment_created_directly_in_pagos_moves_nothing(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await billing_api.get_period()
    await billing_api.create_foreign_payment(ORG_ID, status="approved", amount=49900)

    body = (await billing_api.get_period()).json()

    assert (body["state"], body["payment_due_at"]) == ("overdue", TRIAL_END)
    assert (await billing_api.periods())[0][3] is None
    assert await billing_api.payments_calls() == []  # no charge refers to it: Pagos was never asked


async def test_scenario_10_a_payment_that_is_still_pending_is_in_progress(billing_api: BillingApi, plan_id: int):
    await billing_api.start_payment()

    body = (await billing_api.get_period()).json()

    assert body["payment_in_progress"] is True
    assert (await billing_api.charges())[0][7] == "pending"
    # The charge was asked about with the token of the person.
    calls = [c for c in await billing_api.payments_calls() if c["method"] == "GET"]
    assert [c["authorization"] for c in calls] == [f"Bearer {TEST_TOKEN}"]


async def test_scenario_11_two_approved_charges_are_applied_in_order(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await billing_api.start_payment()
    async with billing_api.engine.begin() as connection:
        await connection.execute(
            text("UPDATE subscriptions SET monthly_price = 799.00 WHERE id = :id"), {"id": plan_id}
        )
    await billing_api.start_payment()
    first, second = (p["id"] for p in await billing_api.payments())
    await billing_api.set_payment_status(second, "approved", updated_at="2026-12-01T10:01:00Z")
    await billing_api.set_payment_status(first, "approved", updated_at="2026-12-01T10:00:00Z")

    body = (await billing_api.get_period()).json()

    assert body["payment_due_at"] == "2027-02-04T15:30:00Z"
    periods = [(c[9], c[10]) for c in await billing_api.charges()]
    assert periods == [
        (at(TRIAL_END), at("2027-01-04T15:30:00Z")),
        (at("2027-01-04T15:30:00Z"), at("2027-02-04T15:30:00Z")),
    ]


async def test_a_refund_after_the_application_does_not_revoke_the_period(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    payment_id = await start_and_approve(billing_api, "2026-12-01T10:00:00Z")
    await billing_api.get_period()
    await billing_api.set_payment_status(payment_id, "refunded")

    body = (await billing_api.get_period()).json()

    assert body["payment_due_at"] == "2027-01-04T15:30:00Z"
    assert (await billing_api.charges())[0][7] == "applied"


async def test_story_2_scenario_9_a_charge_approved_in_the_meantime_is_applied_before_starting_another(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await start_and_approve(billing_api, "2026-12-10T09:30:00Z")
    billing_api.clock.set(at("2026-12-10T09:45:00Z"))

    response = await billing_api.start_payment()

    assert response.status_code == 201
    first, second = await billing_api.charges()
    assert first[7] == "applied"
    assert second[5] == at("2027-01-10T09:30:00Z")  # the new charge settles the next period
    assert len(await billing_api.payments()) == 2


# ================== story 5: the changes of plan do not rewrite the past ==================


async def set_catalog(billing_api: BillingApi, plan_id: int, **columns) -> None:
    """Change a plan in the catalog: what the staff of MailySoft does, never the person."""
    assignments = ", ".join(f"{column} = :{column}" for column in columns)
    async with billing_api.engine.begin() as connection:
        await connection.execute(
            text(f"UPDATE subscriptions SET {assignments} WHERE id = :plan_id"), {"plan_id": plan_id, **columns}
        )


async def test_story_5_scenario_1_a_new_plan_with_other_trial_days_keeps_the_end_of_the_trial(
    billing_api: BillingApi, plan_id: int
):
    await billing_api.get_period()
    other = await billing_api.add_plan(name="Plan Consultorio", trial_days=30, monthly_price="799.00")
    await billing_api.register_organization(other, created_at=CREATED)  # Clínicas now reports the other plan

    body = (await billing_api.get_period()).json()

    assert body == trial_body(
        other,
        subscription={"id": other, "name": "Plan Consultorio"},
        amount="799.00",
    )  # the same dates as before, the new plan and its amount
    assert (await billing_api.periods())[0][2] == at(TRIAL_END)


async def test_story_5_the_trial_days_of_the_plan_changing_in_the_catalog_do_not_move_it(
    billing_api: BillingApi, plan_id: int
):
    await billing_api.get_period()
    await set_catalog(billing_api, plan_id, trial_days=30)

    body = (await billing_api.get_period()).json()

    assert (body["trial_ends_at"], body["payment_due_at"]) == (TRIAL_END, TRIAL_END)


async def test_story_5_scenario_2_monthly_to_annual_keeps_the_date_and_shows_the_annual_amount(
    billing_api: BillingApi, plan_id: int
):
    before = (await billing_api.get_period()).json()
    await billing_api.register_organization(plan_id, billing_period="annual", created_at=CREATED)

    body = (await billing_api.get_period()).json()

    assert body["payment_due_at"] == before["payment_due_at"] == TRIAL_END
    assert (body["billing_period"], body["amount"]) == ("annual", "4990.00")


async def test_story_5_scenario_3_a_monthly_charge_approved_after_the_change_to_annual_moves_one_month(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    payment_id = await start_and_approve(billing_api, "2026-12-10T09:30:00Z")
    await billing_api.register_organization(plan_id, billing_period="annual", created_at=CREATED)
    billing_api.clock.set(at("2026-12-10T09:45:00Z"))

    body = (await billing_api.get_period()).json()

    assert body["payment_due_at"] == "2027-01-10T09:30:00Z"  # one month, not twelve
    assert (body["billing_period"], body["amount"]) == ("annual", "4990.00")
    [charge] = await billing_api.charges()
    assert (charge[4], charge[7], charge[10]) == ("monthly", "applied", at("2027-01-10T09:30:00Z"))
    assert payment_id  # the payment that was approved is the one that was registered


async def test_story_5_the_next_payment_uses_the_plan_and_period_of_that_moment(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    assert (await billing_api.start_payment()).status_code == 201  # monthly, 499.00
    await billing_api.register_organization(plan_id, billing_period="annual", created_at=CREATED)

    second = await billing_api.start_payment()

    assert second.status_code == 201
    assert (second.json()["billing_period"], second.json()["amount"]) == ("annual", "4990.00")
    assert [c["amount"] for c in await billing_api.payments()] == [49900, 499000]
    assert [(c[2], c[4]) for c in await billing_api.charges()] == [
        (Decimal("499.00"), "monthly"),
        (Decimal("4990.00"), "annual"),
    ]


@pytest.mark.parametrize("status_id", [2, 3, 4], ids=["inactive", "blocked", "deleted"])
async def test_story_5_scenario_4_the_status_of_the_plan_does_not_affect_the_charge(
    billing_api: BillingApi, status_id: int
):
    plan = await billing_api.add_plan(name="Plan retirado", status_id=status_id, trial_days=10, monthly_price="650.00")
    await billing_api.register_organization(plan, created_at=CREATED)

    consult = await billing_api.get_period()
    pay = await billing_api.start_payment()

    assert consult.status_code == 200
    assert (consult.json()["subscription"], consult.json()["amount"]) == (
        {"id": plan, "name": "Plan retirado"},
        "650.00",
    )
    assert consult.json()["trial_ends_at"] == "2026-11-30T15:30:00Z"  # its own 10 days of trial
    assert pay.status_code == 201 and pay.json()["amount"] == "650.00"


@pytest.mark.parametrize("operation", ["consult", "pay"])
async def test_story_5_scenario_5_a_plan_that_is_not_in_the_catalog_is_a_conflict_that_creates_nothing(
    billing_api: BillingApi, operation: str
):
    await billing_api.register_organization(9999, created_at=CREATED)  # Clínicas reports a plan we do not have

    response = await (billing_api.get_period() if operation == "consult" else billing_api.start_payment())

    assert response.status_code == 409
    assert response.json()["code"] == "organization_subscription_not_found"
    assert await billing_api.snapshot() == []  # no record and no invented date or amount
    assert await billing_api.payments_calls() == []  # Pagos was never asked


async def test_story_5_a_plan_that_changes_to_a_free_one_has_nothing_to_charge_and_back_again_it_is_what_it_was(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))  # overdue since 2026-12-04
    await billing_api.get_period()
    free = await billing_api.add_plan(name="Plan Gratuito", monthly_price="0.00", annual_price="0.00")
    await billing_api.register_organization(free, created_at=CREATED)

    body = (await billing_api.get_period()).json()
    refused = await billing_api.start_payment()

    assert (body["state"], body["payment_due_at"], body["days_remaining"], body["amount"]) == (
        "no_charge",
        None,
        None,
        "0.00",
    )
    assert refused.status_code == 409 and refused.json()["code"] == "nothing_to_charge"
    assert await billing_api.payments_calls() == []

    await billing_api.register_organization(plan_id, created_at=CREATED)  # back to the paid plan
    back = (await billing_api.get_period()).json()

    assert (back["state"], back["payment_due_at"]) == ("overdue", TRIAL_END)  # the fixed date, now past


# ====================== spec 012: the history of charges ======================

CHARGE_KEYS = {
    "id", "status", "closed_reason", "amount", "currency", "billing_period",
    "period_starts_at", "period_ends_at", "created_at",
}


async def test_an_organization_without_charges_has_an_empty_history(billing_api: BillingApi, plan_id: int):
    response = await billing_api.list_charges()

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
    assert response.headers["cache-control"] == "no-store"


async def test_a_pending_charge_appears_with_both_period_dates_null(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await billing_api.start_payment()

    body = (await billing_api.list_charges()).json()

    assert body["total"] == 1
    [charge] = body["items"]
    assert set(charge) == CHARGE_KEYS
    assert (charge["status"], charge["closed_reason"]) == ("pending", None)
    assert charge["period_starts_at"] is None and charge["period_ends_at"] is None
    assert (charge["amount"], charge["currency"], charge["billing_period"]) == ("499.00", "MXN", "monthly")


async def test_an_applied_charge_shows_the_period_it_covered(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await start_and_approve(billing_api, "2026-12-01T10:00:00Z")
    await billing_api.get_period()  # the period read is what applies the charge

    body = (await billing_api.list_charges()).json()

    [charge] = body["items"]
    assert charge["status"] == "applied"
    assert (charge["period_starts_at"], charge["period_ends_at"]) == (TRIAL_END, "2027-01-04T15:30:00Z")


@pytest.mark.parametrize(("status", "reason"), [("rejected", "rejected"), ("cancelled", "cancelled")])
async def test_a_closed_charge_shows_its_reason_and_no_period_dates(
    billing_api: BillingApi, plan_id: int, status, reason
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await billing_api.start_payment()
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, status)
    await billing_api.get_period()  # the period read is what reconciles and closes the charge

    body = (await billing_api.list_charges()).json()

    [charge] = body["items"]
    assert (charge["status"], charge["closed_reason"]) == ("closed", reason)
    assert charge["period_starts_at"] is None and charge["period_ends_at"] is None


async def test_the_history_does_not_reconcile_an_approved_charge_by_itself(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    await start_and_approve(billing_api, "2026-12-10T09:30:00Z")

    body = (await billing_api.list_charges()).json()

    assert body["items"][0]["status"] == "pending"  # the period was never read: nothing applied it
    calls = [c for c in await billing_api.payments_calls() if c["method"] == "GET"]
    assert calls == []  # Pagos was never asked by this read


async def test_the_history_is_newest_first_and_paginated(billing_api: BillingApi, plan_id: int):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    first = await billing_api.start_payment()  # charge 1 (rejected right after, below)
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, "rejected")
    second = await billing_api.start_payment()  # a new attempt: charge 2, still pending

    assert (first.status_code, second.status_code) == (201, 201)
    first_page = (await billing_api.list_charges(params={"page": "1", "page_size": "1"})).json()
    second_page = (await billing_api.list_charges(params={"page": "2", "page_size": "1"})).json()

    assert (first_page["total"], first_page["total_pages"]) == (2, 2)
    assert first_page["items"][0]["status"] == "pending"  # the newer attempt comes first
    assert second_page["items"][0]["status"] == "closed"


async def test_the_history_rejects_a_page_size_outside_its_range(billing_api: BillingApi, plan_id: int):
    response = await billing_api.list_charges(params={"page_size": "0"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_only_the_owner_sees_the_history(billing_api: BillingApi, plan_id: int):
    await billing_api.set_permissions([])

    response = await billing_api.list_charges()

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


async def test_story_5_with_two_rates_only_the_free_one_has_nothing_to_charge(billing_api: BillingApi):
    plan = await billing_api.add_plan(monthly_price="0.00", annual_price="4990.00")
    await billing_api.register_organization(plan, billing_period="monthly", created_at=CREATED)
    monthly = (await billing_api.get_period()).json()
    await billing_api.register_organization(plan, billing_period="annual", created_at=CREATED)

    annual = (await billing_api.get_period()).json()

    assert (monthly["state"], monthly["amount"]) == ("no_charge", "0.00")
    assert (annual["state"], annual["amount"]) == ("trial", "4990.00")

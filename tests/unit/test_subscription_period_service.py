"""The Service of the subscription periods against doubles (spec 010).

No database and no network: the clinics API, the payments API, the Repository, the catalog and the clock
are doubles with the semantics of the real ones (`tests/billing_support.py`). The dates are the ones of
«Ejemplos de referencia del cálculo de fechas» of the spec.

Sections: the consultation (story 1), starting the payment (story 2), the reconciliation (story 3), the
changes of plan (story 5) and the degradation (story 6).
"""

import uuid
from dataclasses import replace
from decimal import Decimal

import pytest

from src.exceptions import (
    NothingToChargeError,
    OrganizationCheckUnavailableError,
    OrganizationNotFoundError,
    OrganizationSubscriptionNotFoundError,
    PaymentsUnavailableError,
)
from src.models.subscription_charge import ChargeStatus, ClosedReason
from src.services.billing_rules import CURRENCY, RESOURCE_TYPE, idempotency_key
from tests.billing_support import (
    ORG_ID,
    OTHER_ORG_ID,
    at,
    make_organization,
    make_payment,
    make_plan,
    make_world,
)

TOKEN = "token-de-la-persona"

# An organization created on 2026-11-20T15:30:00Z with a trial of 14 days (it ends on 2026-12-04T15:30:00Z),
# monthly billing and a price of 499.00; the cutoff is before its creation.
CREATED = "2026-11-20T15:30:00Z"
TRIAL_END = "2026-12-04T15:30:00Z"
CUTOFF_BEFORE = "2026-11-01T00:00:00Z"


def new_world(now: str = "2026-11-25T15:30:00Z", **kwargs):
    kwargs.setdefault("organization", make_organization(created_at=CREATED))
    kwargs.setdefault("cutoff", CUTOFF_BEFORE)
    return make_world(now=now, **kwargs)


# =============================== story 1: the consultation ===============================


async def test_scenario_1_an_organization_in_trial():  # example 2
    world = new_world()

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.state == "trial"
    assert view.trial_ends_at == at(TRIAL_END)
    assert view.payment_due_at == at(TRIAL_END)
    assert view.days_remaining == 9
    assert (view.plan_id, view.plan_name) == (1, "Plan Individual")
    assert view.billing_period == "monthly"
    assert view.amount == Decimal("499.00")
    assert view.payment_in_progress is False


async def test_scenario_2_the_same_organization_overdue():  # example 6
    world = new_world(now="2026-12-10T09:00:00Z")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.state == "overdue"
    assert view.payment_due_at == at(TRIAL_END)  # the date does not move
    assert view.days_remaining == -5


@pytest.mark.parametrize(
    ("now", "state", "days"),
    [
        ("2026-11-25T16:00:00Z", "trial", 9),  # example 3
        ("2026-12-03T15:30:01Z", "trial", 1),  # example 4
        ("2026-12-04T15:30:00Z", "overdue", 0),  # example 5: the exact instant
    ],
)
async def test_the_limits_of_the_trial(now, state, days):
    view = await new_world(now=now).service.get_status(TOKEN, ORG_ID)

    assert (view.state, view.days_remaining) == (state, days)


async def test_scenario_3_without_a_trial_the_first_payment_is_due_at_the_start():  # example 13
    world = new_world(now="2026-11-21T09:00:00Z", plan=make_plan(trial_days=0))

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.trial_ends_at is None
    assert view.payment_due_at == at(CREATED)
    assert (view.state, view.days_remaining) == ("overdue", 0)


async def test_scenario_4_a_free_amount_has_no_charge_and_no_payment_date():
    world = new_world(plan=make_plan(monthly_price="0.00", annual_price="0.00"))

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.state == "no_charge"
    assert view.payment_due_at is None and view.days_remaining is None
    assert view.amount == Decimal("0.00")
    assert view.trial_ends_at == at(TRIAL_END)  # what was fixed stays


async def test_a_free_amount_during_the_trial_or_overdue_is_always_no_charge():
    for now in ("2026-11-25T15:30:00Z", "2026-12-10T09:00:00Z"):
        world = new_world(now=now, plan=make_plan(monthly_price="0.00"))

        assert (await world.service.get_status(TOKEN, ORG_ID)).state == "no_charge"


async def test_only_one_of_the_two_prices_free_depends_on_the_billing_period():
    plan = make_plan(monthly_price="0.00", annual_price="4990.00")

    monthly = await new_world(plan=plan).service.get_status(TOKEN, ORG_ID)
    annual = await new_world(
        plan=plan, organization=make_organization(created_at=CREATED, billing_period="annual")
    ).service.get_status(TOKEN, ORG_ID)

    assert (monthly.state, monthly.amount) == ("no_charge", Decimal("0.00"))
    assert (annual.state, annual.amount) == ("trial", Decimal("4990.00"))


async def test_the_amount_follows_the_billing_period_of_the_organization():
    world = new_world(organization=make_organization(created_at=CREATED, billing_period="annual"))

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert (view.billing_period, view.amount) == ("annual", Decimal("4990.00"))


async def test_scenario_5_an_organization_older_than_the_cutoff_starts_at_the_cutoff():  # example 12
    world = make_world(
        now="2026-11-25T00:00:00Z",
        organization=make_organization(created_at="2026-06-01T12:00:00Z"),
        cutoff="2026-11-18T00:00:00Z",
    )

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.periods[ORG_ID].started_at == at("2026-11-18T00:00:00Z")
    assert view.trial_ends_at == at("2026-12-02T00:00:00Z")
    assert (view.state, view.days_remaining) == ("trial", 7)


async def test_an_old_organization_without_a_trial_falls_due_at_the_deployment():  # example 14
    world = make_world(
        now="2026-11-18T08:00:00Z",
        organization=make_organization(created_at="2026-06-01T12:00:00Z"),
        plan=make_plan(trial_days=0),
        cutoff="2026-11-18T00:00:00Z",
    )

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_due_at == at("2026-11-18T00:00:00Z")
    assert (view.state, view.days_remaining) == ("overdue", 0)


async def test_a_cutoff_in_the_future_leaves_the_organization_up_to_date():  # example 15
    world = make_world(
        now="2026-11-25T00:00:00Z",
        organization=make_organization(created_at="2026-06-01T12:00:00Z"),
        plan=make_plan(trial_days=0),
        cutoff="2026-12-18T00:00:00Z",
    )

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert (view.state, view.days_remaining) == ("current", 23)


async def test_the_first_consultation_creates_the_record_once():
    world = new_world()

    await world.service.get_status(TOKEN, ORG_ID)
    await world.service.get_status(TOKEN, ORG_ID)
    await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.calls["create_if_absent"] == 1
    assert list(world.periods.periods) == [ORG_ID]


async def test_scenario_6_the_fixed_dates_do_not_change_with_the_plan_nor_with_its_trial_days():
    world = new_world()
    first = await world.service.get_status(TOKEN, ORG_ID)

    # The organization moves to another plan and the catalog changes the trial days of both.
    world.plans.plans[1] = make_plan(1, trial_days=30)
    world.plans.plans[2] = make_plan(2, name="Plan Empresarial", trial_days=60, monthly_price="999.00")
    world.organizations.organization = make_organization(created_at=CREATED, subscription_id=2)
    second = await world.service.get_status(TOKEN, ORG_ID)

    assert second.trial_ends_at == first.trial_ends_at == at(TRIAL_END)
    assert second.payment_due_at == first.payment_due_at
    assert (second.plan_id, second.plan_name, second.amount) == (2, "Plan Empresarial", Decimal("999.00"))


async def test_the_trial_uses_the_days_of_the_plan_when_the_record_is_created():
    world = new_world()
    # The organization was created with the 14-day plan, but it is consulted for the first time on another.
    world.plans.plans[2] = make_plan(2, trial_days=30)
    world.organizations.organization = make_organization(created_at=CREATED, subscription_id=2)

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.trial_ends_at == at("2026-12-20T15:30:00Z")


async def test_the_state_is_computed_again_with_the_clock_on_every_consultation():
    world = new_world(now="2026-11-25T15:30:00Z")

    before = await world.service.get_status(TOKEN, ORG_ID)
    world.at("2026-12-10T09:00:00Z")
    after = await world.service.get_status(TOKEN, ORG_ID)

    assert (before.state, before.days_remaining) == ("trial", 9)
    assert (after.state, after.days_remaining) == ("overdue", -5)
    assert world.periods.calls["create_if_absent"] == 1  # nothing was stored for the state


async def test_the_clinics_api_gets_the_token_of_the_person_and_the_payments_api_nothing():
    world = new_world()

    await world.service.get_status(TOKEN, ORG_ID)

    assert world.organizations.calls == [(TOKEN, ORG_ID)]
    assert world.payments.get_calls == [] and world.payments.create_calls == []


async def test_scenario_1_an_organization_without_charges_has_no_charge_in_progress():
    view = await new_world().service.get_status(TOKEN, ORG_ID)

    assert view.payment_in_progress is False


async def test_the_catalog_is_read_for_the_plan_that_the_clinics_api_reports():
    world = new_world()

    await world.service.get_status(TOKEN, ORG_ID)

    assert world.plans.calls >= 1


async def test_an_organization_that_the_clinics_api_does_not_return_is_not_found():
    world = new_world()

    with pytest.raises(OrganizationNotFoundError) as error:
        await world.service.get_status(TOKEN, OTHER_ORG_ID)

    assert str(OTHER_ORG_ID) in error.value.message
    assert world.periods.periods == {}  # nothing was created


async def test_when_the_clinics_api_fails_the_check_is_unavailable_and_nothing_is_created():
    world = new_world()
    world.organizations.fail = True

    with pytest.raises(OrganizationCheckUnavailableError):
        await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.periods == {}
    assert world.plans.calls == 0  # it does not go on without knowing who the person is


async def test_a_plan_that_is_not_in_the_catalog_is_a_conflict_and_nothing_is_created():
    world = new_world()
    world.plans.plans.clear()

    with pytest.raises(OrganizationSubscriptionNotFoundError):
        await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.periods == {}
    assert world.payments.get_calls == [] and world.payments.create_calls == []


# ============================ story 2: starting the payment ============================

OVERDUE_NOW = "2026-12-10T09:00:00Z"  # the trial ended on 2026-12-04T15:30:00Z


async def test_scenario_1_starting_the_payment_creates_one_payment_and_registers_the_charge():
    world = new_world(now=OVERDUE_NOW)

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert start.checkout_url.startswith("https://checkout.example.test/pay/")
    assert (start.amount, start.billing_period) == (Decimal("499.00"), "monthly")
    [call] = world.payments.create_calls
    assert call["token"] == TOKEN  # the token of the person, forwarded
    assert (call["amount"], call["currency"]) == (49900, CURRENCY)
    assert (call["resource_type"], call["resource_id"]) == (RESOURCE_TYPE, str(ORG_ID))
    assert call["idempotency_key"] == idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 1, "Suscripción Plan Individual — mensual")
    assert call["description"] == "Suscripción Plan Individual — mensual"
    assert call["metadata"] == {"billing_period": "monthly", "settles_due_at": TRIAL_END}
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[0]
    assert charge.status == ChargeStatus.PENDING
    assert (charge.amount, charge.currency, charge.billing_period) == (Decimal("499.00"), "MXN", "monthly")
    assert (charge.settles_due_at, charge.attempt) == (at(TRIAL_END), 1)


async def test_scenario_2_an_annual_organization_pays_the_annual_price_for_twelve_months():
    world = new_world(
        now=OVERDUE_NOW, organization=make_organization(created_at=CREATED, billing_period="annual")
    )

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert (start.amount, start.billing_period) == (Decimal("4990.00"), "annual")
    [call] = world.payments.create_calls
    assert call["amount"] == 499000
    assert call["description"] == "Suscripción Plan Individual — anual"
    assert call["metadata"]["billing_period"] == "annual"
    assert world.periods.charges_of()[0].billing_period == "annual"


async def test_scenario_3_starting_twice_for_the_same_period_gives_the_same_checkout():
    world = new_world(now=OVERDUE_NOW)

    first = await world.service.start_payment(TOKEN, ORG_ID)
    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert (first.created, second.created) == (True, False)
    assert second.checkout_url == first.checkout_url
    assert len(world.payments.create_calls) == 1  # Pagos was not asked for a second payment
    assert len(world.periods.charges_of()) == 1


async def test_the_amount_and_the_period_never_come_from_the_person():
    # There is no argument for them: the Service takes only the token and the organization.
    import inspect

    assert list(inspect.signature(new_world().service.start_payment).parameters) == ["token", "organization_id"]


async def test_scenario_5_an_amount_of_zero_has_nothing_to_charge_and_pagos_is_not_asked():
    world = new_world(now=OVERDUE_NOW, plan=make_plan(monthly_price="0.00", annual_price="0.00"))

    with pytest.raises(NothingToChargeError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert world.payments.create_calls == [] and world.payments.get_calls == []
    assert world.periods.charges_of() == []


async def test_scenario_6_when_pagos_cannot_create_the_payment_no_charge_is_registered():
    world = new_world(now=OVERDUE_NOW)
    world.payments.fail_create = True

    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert world.periods.charges_of() == []


async def test_scenario_7_after_a_closed_charge_the_next_start_creates_a_new_one():
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)
    [charge] = world.periods.charges_of()
    await world.periods.close_charge(charge.id, ClosedReason.REJECTED, at(OVERDUE_NOW))

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert second.created is True
    assert second.checkout_url != first.checkout_url
    assert [c.attempt for c in world.periods.charges_of()] == [1, 2]
    keys = [call["idempotency_key"] for call in world.payments.create_calls]
    assert keys == [
        idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 1, "Suscripción Plan Individual — mensual"),
        idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 2, "Suscripción Plan Individual — mensual"),
    ]


@pytest.mark.parametrize("now", ["2026-11-25T15:30:00Z", "2026-12-04T15:00:00Z", OVERDUE_NOW])
async def test_scenario_8_the_payment_can_be_started_in_trial_close_to_the_date_or_overdue(now):
    world = new_world(now=now)

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert world.periods.charges_of()[0].settles_due_at == at(TRIAL_END)


async def test_scenario_10_another_amount_after_a_change_of_plan_is_another_charge():
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)
    world.plans.plans[1] = make_plan(monthly_price="799.00")  # the plan costs more now

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert (second.created, second.amount) == (True, Decimal("799.00"))
    assert second.checkout_url != first.checkout_url
    old, new = world.periods.charges_of()
    assert (old.amount, new.amount) == (Decimal("499.00"), Decimal("799.00"))
    assert (old.status, new.status) == (ChargeStatus.PENDING, ChargeStatus.PENDING)  # the old one is not cancelled
    assert (old.attempt, new.attempt) == (1, 1)  # other conditions, so the attempt starts again


async def test_starting_the_payment_creates_the_record_if_it_is_the_first_contact():
    world = new_world(now=OVERDUE_NOW)

    await world.service.start_payment(TOKEN, ORG_ID)

    assert world.periods.calls["create_if_absent"] == 1
    assert world.periods.periods[ORG_ID].trial_ends_at == at(TRIAL_END)


async def test_a_payment_without_checkout_is_registered_but_cannot_be_offered():
    world = new_world(now=OVERDUE_NOW)
    world.payments.create_without_checkout = True

    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    # It was created in Pagos, so it is registered: the next reconciliation will resolve it.
    assert len(world.periods.charges_of()) == 1


async def test_two_simultaneous_starts_that_computed_the_same_attempt_register_one_charge():
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)

    # The second request read the world before the first one registered its charge.
    real_find_pending, real_count = world.periods.find_pending, world.periods.count_resolved_with_terms
    stale = {"find_pending": True, "count": True}

    async def find_pending(*args, **kwargs):
        if stale.pop("find_pending", False):
            return None
        return await real_find_pending(*args, **kwargs)

    async def count_resolved_with_terms(*args, **kwargs):
        if stale.pop("count", False):
            return 0
        return await real_count(*args, **kwargs)

    world.periods.find_pending = find_pending
    world.periods.count_resolved_with_terms = count_resolved_with_terms

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert second.created is False  # the unique constraint decided: it is the same charge
    assert second.checkout_url == first.checkout_url
    assert len(world.periods.charges_of()) == 1
    assert len(world.payments.created()) == 1  # the same key gave the same payment


async def test_a_start_that_looked_for_the_pending_charge_before_it_was_registered_uses_the_same_key():
    # The race that a stress test found: the second request found no pending charge (the first had not
    # registered it yet) but counted the attempts after it had. Counting the pending charge as an
    # attempt gave attempt 2, so another key and another payment for the same period.
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)
    real_find_pending = world.periods.find_pending
    stale = {"find_pending": True}

    async def find_pending(*args, **kwargs):
        if stale.pop("find_pending", False):
            return None
        return await real_find_pending(*args, **kwargs)

    world.periods.find_pending = find_pending  # only the search is stale; the count sees the first charge

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert second.created is False
    assert second.checkout_url == first.checkout_url
    [charge] = world.periods.charges_of()
    assert charge.attempt == 1
    assert len(world.payments.created()) == 1  # no second payment was created in Pagos


async def test_a_conflict_with_another_payment_offers_the_registered_checkout_never_the_new_one():
    # Pagos should answer the same key with the same payment; if it ever answers with another one, the
    # payment that is not registered must not reach the person: nothing would apply its approval.
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)
    [registered] = world.periods.charges_of()
    real_find_pending = world.periods.find_pending
    stale = {"find_pending": True}

    async def find_pending(*args, **kwargs):
        if stale.pop("find_pending", False):
            return None
        return await real_find_pending(*args, **kwargs)

    world.periods.find_pending = find_pending
    world.payments.ignore_idempotency = True  # the second request gets a payment of its own

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert len(world.payments.created()) == 2  # Pagos did create another payment...
    assert second.checkout_url == first.checkout_url  # ...which is not the one that is offered
    assert second.created is False
    assert [c.payment_id for c in world.periods.charges_of()] == [registered.payment_id]


async def test_starting_the_payment_checks_the_organization_first():
    world = new_world(now=OVERDUE_NOW)

    with pytest.raises(OrganizationNotFoundError):
        await world.service.start_payment(TOKEN, OTHER_ORG_ID)
    world.organizations.fail = True
    with pytest.raises(OrganizationCheckUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert world.payments.create_calls == [] and world.periods.periods == {}


async def test_starting_the_payment_of_an_organization_whose_plan_is_missing_is_a_conflict():
    world = new_world(now=OVERDUE_NOW)
    world.plans.plans.clear()

    with pytest.raises(OrganizationSubscriptionNotFoundError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert world.payments.create_calls == []


# ================== story 3: the date moves, once, when the payment is approved ==================

import logging  # noqa: E402  (the sections are appended in the order of the stories)


async def start_and_get_ids(world):
    """Start the payment; return its identifier in Pagos and its charge."""
    await world.service.start_payment(TOKEN, ORG_ID)
    return world.payments.created()[-1], world.periods.charges_of()[-1]


def paid_until(world):
    return world.periods.periods[ORG_ID].paid_until


async def test_scenario_1_a_payment_approved_during_the_trial_does_not_shorten_it():  # example 7
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")
    world.at("2026-12-01T10:05:00Z")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-04T15:30:00Z")
    assert view.trial_ends_at == at(TRIAL_END)  # the trial is the same
    assert view.state == "trial"  # and it goes on until it ends
    assert (view.payment_due_at, view.days_remaining) == (at("2027-01-04T15:30:00Z"), 35)
    assert view.payment_in_progress is False
    [charge] = world.periods.charges_of()
    assert charge.status == ChargeStatus.APPLIED
    assert (charge.period_starts_at, charge.period_ends_at) == (at(TRIAL_END), at("2027-01-04T15:30:00Z"))


async def test_scenario_2_a_payment_approved_when_overdue_starts_at_the_approval():  # example 8
    world = new_world(now=OVERDUE_NOW)
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-10T09:30:00Z")
    world.at("2026-12-10T09:45:00Z")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-10T09:30:00Z")
    assert (view.state, view.days_remaining) == ("current", 31)
    charge = world.periods.charges_of()[0]
    assert (charge.period_starts_at, charge.period_ends_at) == (
        at("2026-12-10T09:30:00Z"),
        at("2027-01-10T09:30:00Z"),
    )


async def test_scenario_3_an_annual_payment_covers_twelve_months():  # example 9
    world = new_world(
        now="2026-12-01T10:00:00Z", organization=make_organization(created_at=CREATED, billing_period="annual")
    )
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")

    await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-12-04T15:30:00Z")


async def test_scenario_4_a_monthly_payment_at_the_end_of_a_month_ends_on_its_last_day():  # example 10
    # Created on 2027-01-17T10:00:00Z, the trial of 14 days ends on 2027-01-31T10:00:00Z.
    world = new_world(
        now="2027-01-20T08:00:00Z", organization=make_organization(created_at="2027-01-17T10:00:00Z")
    )
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2027-01-20T08:00:00Z")

    await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-02-28T10:00:00Z")


async def test_scenario_5_a_consultation_after_another_does_not_move_the_date_again():
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")

    first = await world.service.get_status(TOKEN, ORG_ID)
    second = await world.service.get_status(TOKEN, ORG_ID)
    third = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-04T15:30:00Z")
    assert world.periods.calls["apply_charge"] == 1
    assert (second.payment_due_at, third.payment_due_at) == (first.payment_due_at, first.payment_due_at)
    # An applied charge is not asked about again: only the first consultation went to Pagos.
    assert len(world.payments.get_calls) == 1


async def test_scenario_6_a_payment_approved_before_the_date_but_noticed_after_it_was_on_time():
    world = new_world(now="2026-12-03T09:00:00Z")
    payment_id, _ = await start_and_get_ids(world)
    # Approved the day before the trial ends; nobody consults until six days after it.
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-03T10:00:00Z")
    world.at("2026-12-10T09:00:00Z")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-04T15:30:00Z")  # from the date that was current, not from today
    assert (view.state, view.days_remaining) == ("current", 26)


async def test_an_approval_dated_in_the_future_of_this_service_counts_as_now():
    world = new_world(now=OVERDUE_NOW)
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-20T00:00:00Z")  # the clock says 12-10

    await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-10T09:00:00Z")  # from the clock, never from a future date


@pytest.mark.parametrize(("status", "reason"), [("rejected", "rejected"), ("cancelled", "cancelled")])
async def test_scenario_7_a_rejected_or_cancelled_payment_closes_the_charge_without_moving_the_date(status, reason):
    world = new_world(now=OVERDUE_NOW)
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, status)

    view = await world.service.get_status(TOKEN, ORG_ID)

    [charge] = world.periods.charges_of()
    assert (charge.status, charge.closed_reason) == (ChargeStatus.CLOSED, reason)
    assert charge.resolved_at == at(OVERDUE_NOW)
    assert paid_until(world) is None
    assert (view.state, view.payment_in_progress) == ("overdue", False)

    again = await world.service.start_payment(TOKEN, ORG_ID)  # and a new start creates a new charge
    assert again.created is True
    assert [c.attempt for c in world.periods.charges_of()] == [1, 2]


@pytest.mark.parametrize(
    "mismatch",
    [
        {"amount": 100},  # another amount
        {"currency": "USD"},  # another currency
        {"resource_id": str(OTHER_ORG_ID)},  # another organization
    ],
)
async def test_scenario_8_an_approved_payment_that_does_not_match_is_closed_as_inconsistent(mismatch, caplog):
    world = new_world(now=OVERDUE_NOW)
    payment_id, charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", **mismatch)

    with caplog.at_level(logging.WARNING, logger="src.services"):
        view = await world.service.get_status(TOKEN, ORG_ID)

    assert (charge.status, charge.closed_reason) == (ChargeStatus.CLOSED, ClosedReason.INCONSISTENT)
    assert paid_until(world) is None and view.state == "overdue"
    # It is left on record for its review, without personal data and without the token.
    assert str(charge.id) in caplog.text and "inconsistent" in caplog.text
    assert TOKEN not in caplog.text


async def test_scenario_9_a_payment_created_directly_in_pagos_moves_nothing():
    world = new_world(now=OVERDUE_NOW)
    await world.service.get_status(TOKEN, ORG_ID)
    foreign = world.payments.add_foreign_payment(status="approved", amount=49900)  # same reference, no charge

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) is None and view.state == "overdue"
    assert all(foreign != payment_id for _, payment_id in world.payments.get_calls)  # it is never asked about


async def test_scenario_10_a_payment_that_is_still_pending_changes_nothing_and_is_in_progress():
    world = new_world(now=OVERDUE_NOW)
    await start_and_get_ids(world)

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_in_progress is True
    assert world.periods.charges_of()[0].status == ChargeStatus.PENDING
    assert paid_until(world) is None


@pytest.mark.parametrize("status", ["partially_refunded", "refunded"])
async def test_a_refunded_payment_that_was_never_applied_is_closed_without_applying_it(status):
    world = new_world(now=OVERDUE_NOW)
    payment_id, charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, status)

    await world.service.get_status(TOKEN, ORG_ID)

    assert (charge.status, charge.closed_reason) == (ChargeStatus.CLOSED, ClosedReason.REFUNDED)
    assert paid_until(world) is None


async def test_a_refund_after_the_application_does_not_revoke_the_period():
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")
    await world.service.get_status(TOKEN, ORG_ID)
    world.payments.set_status(payment_id, "refunded")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert paid_until(world) == at("2027-01-04T15:30:00Z")
    assert charge.status == ChargeStatus.APPLIED
    assert view.payment_due_at == at("2027-01-04T15:30:00Z")


async def test_scenario_11_two_approved_charges_are_applied_in_order_and_the_second_continues_the_first():
    world = new_world(now="2026-12-01T10:00:00Z")
    first_payment, _ = await start_and_get_ids(world)
    world.plans.plans[1] = make_plan(monthly_price="799.00")  # another amount: another charge
    second_payment, _ = await start_and_get_ids(world)
    world.payments.set_status(second_payment, "approved", updated_at="2026-12-01T10:01:00Z")  # approved first
    world.payments.set_status(first_payment, "approved", updated_at="2026-12-01T10:00:00Z")

    await world.service.get_status(TOKEN, ORG_ID)

    first, second = world.periods.charges_of()  # in the order they were created
    assert (first.status, second.status) == (ChargeStatus.APPLIED, ChargeStatus.APPLIED)
    assert (first.period_starts_at, first.period_ends_at) == (at(TRIAL_END), at("2027-01-04T15:30:00Z"))
    assert (second.period_starts_at, second.period_ends_at) == (
        at("2027-01-04T15:30:00Z"),
        at("2027-02-04T15:30:00Z"),
    )
    assert paid_until(world) == at("2027-02-04T15:30:00Z")


async def test_all_the_unresolved_charges_are_asked_about_with_the_token_of_the_person():
    world = new_world(now=OVERDUE_NOW)
    await start_and_get_ids(world)
    world.plans.plans[1] = make_plan(monthly_price="799.00")
    await start_and_get_ids(world)
    world.payments.get_calls.clear()

    await world.service.get_status(TOKEN, ORG_ID)

    assert sorted(world.payments.get_calls) == sorted((TOKEN, payment_id) for payment_id in world.payments.created())


async def test_a_date_moved_by_another_request_in_between_is_read_again_and_the_period_recomputed():
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")

    def another_request_applied_a_payment():
        world.periods.periods[ORG_ID].paid_until = at("2027-01-04T15:30:00Z")

    world.periods.before_apply.append(another_request_applied_a_payment)

    await world.service.get_status(TOKEN, ORG_ID)

    # The first try was stale; it read the date again and the period now continues from it.
    assert world.periods.calls["apply_charge"] == 2
    assert paid_until(world) == at("2027-02-04T15:30:00Z")
    assert world.periods.charges_of()[0].status == ChargeStatus.APPLIED


async def test_a_charge_that_another_request_already_resolved_is_left_alone():
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")

    # The other request got in first and applied this same charge (the double hook is synchronous).
    world.periods.before_apply.append(
        lambda: setattr(charge, "status", ChargeStatus.APPLIED) or setattr(charge, "resolved_at", at(OVERDUE_NOW))
    )

    await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.calls["apply_charge"] == 1
    assert paid_until(world) is None  # this request moved nothing: the other one did the application


async def test_a_charge_that_keeps_being_stale_stays_pending_and_the_next_request_applies_it(caplog):
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")
    month = iter(["2027-01-04T15:30:00Z", "2027-02-04T15:30:00Z", "2027-03-04T15:30:00Z"])

    def moved_again():
        world.periods.periods[ORG_ID].paid_until = at(next(month))

    world.periods.before_apply.extend([moved_again, moved_again, moved_again])

    with caplog.at_level(logging.WARNING, logger="src.services"):
        view = await world.service.get_status(TOKEN, ORG_ID)  # it gives up after three tries, without failing

    assert world.periods.calls["apply_charge"] == 3
    assert charge.status == ChargeStatus.PENDING
    assert str(charge.id) in caplog.text
    # An approved payment that could not be applied is neither «no charge in progress» nor decided.
    assert view.payment_in_progress is None

    await world.service.get_status(TOKEN, ORG_ID)

    assert charge.status == ChargeStatus.APPLIED
    assert paid_until(world) == at("2027-04-04T15:30:00Z")


async def test_story_2_scenario_9_a_charge_approved_in_the_meantime_is_applied_before_starting_another():
    world = new_world(now=OVERDUE_NOW)
    payment_id, first_charge = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-10T09:30:00Z")
    world.at("2026-12-10T09:45:00Z")

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert first_charge.status == ChargeStatus.APPLIED  # the first payment was applied first
    assert paid_until(world) == at("2027-01-10T09:30:00Z")
    assert start.created is True
    second = world.periods.charges_of()[1]
    assert second.settles_due_at == at("2027-01-10T09:30:00Z")  # the new charge is for the next period
    assert len(world.payments.created()) == 2


async def test_starting_again_reuses_the_checkout_that_the_verification_already_read():
    world = new_world(now=OVERDUE_NOW)
    first = await world.service.start_payment(TOKEN, ORG_ID)
    world.payments.get_calls.clear()

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert second.checkout_url == first.checkout_url and second.created is False
    assert len(world.payments.get_calls) == 1  # one query for the pending charge, not two


# ================== story 5: the changes of plan do not rewrite the past ==================


def change_plan(world, plan_id: int, *, billing_period: str | None = None) -> None:
    """What Clínicas reports from now on: another plan and, if given, another billing period."""
    current = world.organizations.organization
    world.organizations.organization = make_organization(
        subscription_id=plan_id,
        billing_period=billing_period or current.billing_period,
        created_at=current.created_at,
    )


async def test_story_5_scenario_1_a_new_plan_with_other_trial_days_does_not_move_the_end_of_the_trial():
    world = new_world()
    await world.service.get_status(TOKEN, ORG_ID)  # the record, with its dates, exists now
    world.plans.plans[2] = make_plan(2, name="Plan Consultorio", trial_days=30, monthly_price="799.00")
    change_plan(world, 2)

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.trial_ends_at == at(TRIAL_END)  # the end of before, not 30 days after the start
    assert view.payment_due_at == at(TRIAL_END)
    assert view.state == "trial"
    assert (view.plan_id, view.plan_name, view.amount) == (2, "Plan Consultorio", Decimal("799.00"))
    assert world.periods.periods[ORG_ID].trial_ends_at == at(TRIAL_END)


async def test_story_5_the_trial_days_of_the_plan_changing_in_the_catalog_do_not_move_it_either():
    world = new_world()
    await world.service.get_status(TOKEN, ORG_ID)
    world.plans.plans[1] = make_plan(1, trial_days=30)  # the same plan, now with 30 days

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.trial_ends_at == at(TRIAL_END)


async def test_story_5_a_plan_with_a_longer_trial_does_not_reopen_an_expired_one():
    world = new_world(now="2026-12-10T09:00:00Z")  # six days after the trial ended
    await world.service.get_status(TOKEN, ORG_ID)
    world.plans.plans[2] = make_plan(2, trial_days=90)
    change_plan(world, 2)

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.state == "overdue"  # nobody gets days that the plan of before did not give
    assert view.payment_due_at == at(TRIAL_END)


async def test_story_5_scenario_2_monthly_to_annual_keeps_the_date_and_shows_the_annual_amount():
    world = new_world()
    before = await world.service.get_status(TOKEN, ORG_ID)
    change_plan(world, 1, billing_period="annual")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_due_at == before.payment_due_at == at(TRIAL_END)
    assert (view.billing_period, view.amount) == ("annual", Decimal("4990.00"))


async def test_story_5_a_change_never_moves_a_date_that_a_payment_had_set():
    world = new_world(now="2026-12-01T10:00:00Z")
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-01T10:00:00Z")
    before = await world.service.get_status(TOKEN, ORG_ID)
    world.plans.plans[2] = make_plan(2, trial_days=0, monthly_price="999.00")
    change_plan(world, 2, billing_period="annual")

    after = await world.service.get_status(TOKEN, ORG_ID)

    assert after.payment_due_at == before.payment_due_at == at("2027-01-04T15:30:00Z")  # no proration
    assert paid_until(world) == at("2027-01-04T15:30:00Z")


async def test_story_5_scenario_3_a_monthly_charge_approved_after_the_change_to_annual_moves_one_month():
    world = new_world(now=OVERDUE_NOW)
    payment_id, charge = await start_and_get_ids(world)  # monthly, 499.00
    change_plan(world, 1, billing_period="annual")
    world.payments.set_status(payment_id, "approved", updated_at="2026-12-10T09:30:00Z")
    world.at("2026-12-10T09:45:00Z")

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert charge.status == ChargeStatus.APPLIED
    assert (charge.period_starts_at, charge.period_ends_at) == (
        at("2026-12-10T09:30:00Z"),
        at("2027-01-10T09:30:00Z"),  # one month: the period that it was registered with, not twelve
    )
    assert view.payment_due_at == at("2027-01-10T09:30:00Z")
    assert (view.billing_period, view.amount) == ("annual", Decimal("4990.00"))  # what comes next is annual


async def test_story_5_the_next_charge_uses_the_plan_and_billing_period_of_that_moment():
    world = new_world(now=OVERDUE_NOW)
    await world.service.start_payment(TOKEN, ORG_ID)  # monthly, 499.00
    world.plans.plans[2] = make_plan(2, name="Plan Consultorio", monthly_price="799.00", annual_price="7990.00")
    change_plan(world, 2, billing_period="annual")

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert (second.created, second.amount, second.billing_period) == (True, Decimal("7990.00"), "annual")
    first_charge, second_charge = world.periods.charges_of()
    assert (first_charge.billing_period, first_charge.amount) == ("monthly", Decimal("499.00"))
    assert (second_charge.billing_period, second_charge.amount) == ("annual", Decimal("7990.00"))
    assert world.payments.create_calls[-1]["amount"] == 799000
    assert "anual" in world.payments.create_calls[-1]["description"]


async def test_story_5_a_plan_that_changes_to_a_free_one_has_nothing_to_charge_and_back_again_it_is_what_it_was():
    world = new_world(now="2026-12-10T09:00:00Z")  # overdue since 2026-12-04
    await world.service.get_status(TOKEN, ORG_ID)
    world.plans.plans[2] = make_plan(2, name="Plan Gratuito", monthly_price="0.00", annual_price="0.00")
    change_plan(world, 2)

    free = await world.service.get_status(TOKEN, ORG_ID)

    assert free.state == "no_charge"
    assert (free.payment_due_at, free.days_remaining) == (None, None)
    with pytest.raises(NothingToChargeError):
        await world.service.start_payment(TOKEN, ORG_ID)

    change_plan(world, 1)
    back = await world.service.get_status(TOKEN, ORG_ID)

    assert back.state == "overdue"  # the date that was fixed, which may have passed meanwhile
    assert back.payment_due_at == at(TRIAL_END)


async def test_story_5_with_two_rates_only_the_free_one_has_nothing_to_charge():
    plan = make_plan(1, monthly_price="0.00", annual_price="4990.00")
    world = make_world(
        now="2026-11-25T15:30:00Z",
        organization=make_organization(created_at=CREATED),
        plan=plan,
        cutoff=CUTOFF_BEFORE,
    )

    monthly = await world.service.get_status(TOKEN, ORG_ID)
    change_plan(world, 1, billing_period="annual")
    annual = await world.service.get_status(TOKEN, ORG_ID)

    assert (monthly.state, monthly.amount) == ("no_charge", Decimal("0.00"))
    assert (annual.state, annual.amount) == ("trial", Decimal("4990.00"))


@pytest.mark.parametrize("operation", ["get_status", "start_payment"])
async def test_story_5_scenario_5_a_plan_that_is_not_in_the_catalog_is_a_conflict_that_creates_nothing(operation):
    world = new_world(now=OVERDUE_NOW, organization=make_organization(subscription_id=99, created_at=CREATED))

    with pytest.raises(OrganizationSubscriptionNotFoundError):
        await getattr(world.service, operation)(TOKEN, ORG_ID)

    assert world.periods.periods == {} and world.periods.charges == {}  # no record, no invented date
    assert world.payments.create_calls == [] and world.payments.get_calls == []


async def test_story_5_a_plan_that_disappears_later_stops_the_answer_but_keeps_the_record():
    world = new_world()
    await world.service.get_status(TOKEN, ORG_ID)
    record = world.periods.periods[ORG_ID]
    change_plan(world, 99)

    with pytest.raises(OrganizationSubscriptionNotFoundError):
        await world.service.get_status(TOKEN, ORG_ID)

    assert world.periods.periods[ORG_ID] is record  # nothing was rewritten
    assert (record.trial_ends_at, record.paid_until) == (at(TRIAL_END), None)


# ================== story 6: when another API fails, nothing is invented ==================


async def two_pending_charges(world):
    """Two unresolved charges for the same period with different amounts; returns their payments."""
    first, _ = await start_and_get_ids(world)
    world.plans.plans[1] = make_plan(1, monthly_price="799.00")  # the plan costs more now
    second, _ = await start_and_get_ids(world)
    return first, second


async def test_story_6_a_payments_api_that_fails_on_a_consultation_is_never_an_error():
    world = new_world()
    await start_and_get_ids(world)
    healthy = await world.service.get_status(TOKEN, ORG_ID)
    world.payments.fail_get = True

    view = await world.service.get_status(TOKEN, ORG_ID)  # it does not raise

    assert view.payment_in_progress is None  # «could not be verified», not a made-up False
    assert view == replace(healthy, payment_in_progress=None)  # the rest is the stored data, as it was
    assert world.periods.charges_of()[0].status == ChargeStatus.PENDING  # nothing was decided


async def test_story_6_with_nothing_to_verify_the_payments_api_is_not_asked():
    world = new_world()
    world.payments.fail_get = True  # it would fail, if it were asked

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_in_progress is False  # a real False: there is no unresolved charge
    assert world.payments.get_calls == []


async def test_story_6_when_one_charge_is_verified_as_pending_there_is_one_in_progress():
    world = new_world(now=OVERDUE_NOW)
    first, _ = await two_pending_charges(world)
    world.payments.fail_get = {first}  # Pagos cannot answer for the first one only

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_in_progress is True


async def test_story_6_when_no_charge_can_be_verified_none_is_in_progress_for_sure():
    world = new_world(now=OVERDUE_NOW)
    first, second = await two_pending_charges(world)
    world.payments.fail_get = {first, second}

    view = await world.service.get_status(TOKEN, ORG_ID)

    assert view.payment_in_progress is None
    assert [c.status for c in world.periods.charges_of()] == [ChargeStatus.PENDING, ChargeStatus.PENDING]


async def test_story_6_a_charge_that_cannot_be_verified_does_not_hold_back_one_that_is_approved():
    world = new_world(now=OVERDUE_NOW)
    first, second = await two_pending_charges(world)
    world.payments.set_status(second, "approved", updated_at="2026-12-10T09:00:00Z")
    world.payments.fail_get = {first}

    view = await world.service.get_status(TOKEN, ORG_ID)

    old, new = world.periods.charges_of()
    assert (old.status, new.status) == (ChargeStatus.PENDING, ChargeStatus.APPLIED)
    assert view.payment_in_progress is None  # the first one is still unknown
    assert view.payment_due_at == at("2027-01-10T09:00:00Z")


async def test_story_6_a_programming_error_is_not_swallowed_as_if_it_were_an_unavailable_api():
    world = new_world()
    await start_and_get_ids(world)
    world.payments.crash_get = True

    with pytest.raises(RuntimeError):
        await world.service.get_status(TOKEN, ORG_ID)
    with pytest.raises(RuntimeError):
        await world.service.start_payment(TOKEN, ORG_ID)


async def test_story_6_the_organization_that_cannot_be_checked_stops_both_operations_before_anything_else():
    world = new_world()
    await start_and_get_ids(world)  # a record and a charge exist
    stored = (dict(world.periods.periods), dict(world.periods.charges))
    world.organizations.fail = True
    world.payments.get_calls.clear()

    for operation in (world.service.get_status, world.service.start_payment):
        with pytest.raises(OrganizationCheckUnavailableError):
            await operation(TOKEN, ORG_ID)

    assert (dict(world.periods.periods), dict(world.periods.charges)) == stored
    assert world.payments.get_calls == []  # Pagos was not asked about anything of an organization not checked


async def test_story_6_when_pagos_cannot_confirm_the_existing_charge_it_is_not_offered_nor_duplicated():
    world = new_world(now=OVERDUE_NOW)
    await start_and_get_ids(world)
    world.payments.fail_get = True
    created = len(world.payments.created())

    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert len(world.periods.charges_of()) == 1
    assert len(world.payments.created()) == created  # no second payment for the same period


async def test_story_6_when_pagos_fails_to_create_the_payment_nothing_is_registered():
    world = new_world(now=OVERDUE_NOW)
    world.payments.fail_create = True

    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    assert world.periods.charges == {}
    assert world.periods.periods[ORG_ID].paid_until is None  # and no date was touched


# ================== found by the review: conflicts, a stuck key and an application that gives up ==================


async def test_a_conflict_with_a_charge_that_is_already_resolved_is_a_503_never_a_500(caplog):
    world = new_world(now=OVERDUE_NOW)
    _, charge = await start_and_get_ids(world)
    await world.periods.close_charge(charge.id, ClosedReason.REJECTED, at(OVERDUE_NOW))  # resolved meanwhile
    # The second request read the world before: it found nothing pending and counted no attempt, and Pagos
    # (which should not) gave it a payment of its own. Its registration then meets the charge that closed.
    real_find_pending = world.periods.find_pending

    async def nothing_pending(*args, **kwargs):
        return None

    async def no_attempts(*args, **kwargs):
        return 0

    world.periods.find_pending = nothing_pending
    world.periods.count_resolved_with_terms = no_attempts
    world.payments.ignore_idempotency = True

    with caplog.at_level(logging.WARNING, logger="src.services"):
        with pytest.raises(PaymentsUnavailableError):  # «try again»: not an unmapped persistence error
            await world.service.start_payment(TOKEN, ORG_ID)

    assert str(world.payments.created()[-1]) in caplog.text  # the payment that was left out is on record
    assert [c.payment_id for c in world.periods.charges_of()] == [charge.payment_id]  # nothing new registered
    world.periods.find_pending = real_find_pending


async def test_a_plan_renamed_after_a_lost_answer_does_not_leave_the_payment_stuck():
    # Pagos created the payment but the answer was lost, so nothing was registered. Pagos refuses the same
    # key with another body (409), so a key that did not change with the description would fail for ever.
    world = new_world(now=OVERDUE_NOW)
    world.payments.lose_answer = True
    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)
    assert world.periods.charges_of() == []  # it was never registered nor offered
    world.plans.plans[1] = make_plan(1, name="Plan Consultorio")  # renamed in the catalog meanwhile

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert len(world.payments.created()) == 2  # another key, another payment: the first one is an orphan
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[-1]


async def test_a_lost_answer_is_recovered_with_the_same_payment_when_nothing_changed():
    world = new_world(now=OVERDUE_NOW)
    world.payments.lose_answer = True
    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert len(world.payments.created()) == 1  # the same key gave back the payment that already existed
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[0]


# ====================== spec 011: the return address of the payments ======================

RETURN_URL = "https://app.mailysoft.com/payment"
DESCRIPTION = "Suscripción Plan Individual — mensual"


def restarted(world, return_url: str | None):
    """The same doubles behind a new Service: the service restarted with another configuration."""
    from src.services.subscription_period_service import SubscriptionPeriodService

    return SubscriptionPeriodService(
        periods=world.periods,
        subscriptions=world.plans,
        clinics_api=world.organizations,
        payments_api=world.payments,
        clock=world.clock,
        cutoff=at(CUTOFF_BEFORE),
        return_url=return_url,
    )


async def test_with_a_return_address_the_payment_asks_pagos_to_return_there():  # FR-006, FR-008
    world = new_world(now=OVERDUE_NOW, return_url=RETURN_URL)

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    [call] = world.payments.create_calls
    assert call["return_url"] == RETURN_URL
    assert call["idempotency_key"] == idempotency_key(
        ORG_ID, at(TRIAL_END), "monthly", 49900, 1, DESCRIPTION, RETURN_URL
    )
    assert call["idempotency_key"] != idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 1, DESCRIPTION)
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[0]


async def test_with_a_return_address_starting_twice_gives_the_same_checkout():
    world = new_world(now=OVERDUE_NOW, return_url=RETURN_URL)
    first = await world.service.start_payment(TOKEN, ORG_ID)

    second = await world.service.start_payment(TOKEN, ORG_ID)

    assert (first.created, second.created) == (True, False)
    assert second.checkout_url == first.checkout_url
    assert len(world.payments.create_calls) == 1  # the pending charge is read, never created again


async def test_with_a_return_address_a_lost_answer_is_recovered_with_the_same_payment():
    world = new_world(now=OVERDUE_NOW, return_url=RETURN_URL)
    world.payments.lose_answer = True
    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)

    start = await world.service.start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert len(world.payments.created()) == 1
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[0]


@pytest.mark.parametrize("after", ["https://staging.mailysoft.com/payment", None], ids=["another", "removed"])
async def test_a_return_address_changed_after_a_lost_answer_does_not_leave_the_payment_stuck(after):
    # Pagos refuses the same key with another body (409) and the address is part of the body, so a key that
    # did not change with it would fail for ever (research R5 of spec 011).
    world = new_world(now=OVERDUE_NOW, return_url=RETURN_URL)
    world.payments.lose_answer = True
    with pytest.raises(PaymentsUnavailableError):
        await world.service.start_payment(TOKEN, ORG_ID)
    assert world.periods.charges_of() == []  # it was never registered nor offered

    start = await restarted(world, after).start_payment(TOKEN, ORG_ID)

    assert start.created is True
    assert len(world.payments.created()) == 2  # another key, another payment: the first one is an orphan
    [charge] = world.periods.charges_of()
    assert charge.payment_id == world.payments.created()[-1]
    assert world.payments.create_calls[-1]["return_url"] == after


async def test_without_a_return_address_the_payment_is_created_as_before():  # FR-007, FR-008 (story 2)
    world = new_world(now=OVERDUE_NOW)

    await world.service.start_payment(TOKEN, ORG_ID)

    [call] = world.payments.create_calls
    assert call["return_url"] is None
    assert call["idempotency_key"] == idempotency_key(ORG_ID, at(TRIAL_END), "monthly", 49900, 1, DESCRIPTION)


# ====================== spec 012: the history of charges ======================


async def test_an_organization_without_charges_has_an_empty_history():
    world = new_world()

    charges, total = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    assert charges == [] and total == 0


async def test_the_history_lists_the_charges_of_the_organization_newest_first():
    world = new_world(now=OVERDUE_NOW)
    await world.service.start_payment(TOKEN, ORG_ID)  # charge 1
    world.plans.plans[1] = make_plan(monthly_price="799.00")
    await world.service.start_payment(TOKEN, ORG_ID)  # charge 2, another attempt
    oldest, newest = world.periods.charges_of()

    charges, total = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    assert total == 2
    assert [c.id for c in charges] == [newest.id, oldest.id]


async def test_the_history_is_paginated():
    world = new_world(now=OVERDUE_NOW)
    await world.service.start_payment(TOKEN, ORG_ID)
    world.plans.plans[1] = make_plan(monthly_price="799.00")
    await world.service.start_payment(TOKEN, ORG_ID)

    first_page, total = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=1)
    second_page, _ = await world.service.list_charges(TOKEN, ORG_ID, page=2, page_size=1)

    assert total == 2
    assert len(first_page) == len(second_page) == 1
    assert first_page[0].id != second_page[0].id


async def test_the_history_never_resolves_a_pending_charge_by_itself():
    # Unlike get_status/start_payment, reading the history does not reconcile with the payments API:
    # a charge that is already approved there can still show as pending until the period is read.
    world = new_world(now=OVERDUE_NOW)
    payment_id, _ = await start_and_get_ids(world)
    world.payments.set_status(payment_id, "approved", updated_at=OVERDUE_NOW)

    charges, _ = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    assert charges[0].status == ChargeStatus.PENDING
    assert world.payments.get_calls == []  # the payments API was never asked


async def test_the_history_only_lists_charges_of_its_own_organization():
    world = new_world(now=OVERDUE_NOW)
    await world.service.start_payment(TOKEN, ORG_ID)
    other = make_organization(organization_id=OTHER_ORG_ID, created_at=CREATED)
    world.organizations.organization = other
    await world.service.start_payment(TOKEN, OTHER_ORG_ID)
    world.organizations.organization = make_organization(created_at=CREATED)  # back to ORG_ID, the owner

    charges, total = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    assert total == 1
    assert charges[0].organization_id == ORG_ID


async def test_the_history_snapshots_the_plan_name_at_the_time_of_the_charge():
    # Spec 013: a later rename of the plan in the catalog must not rewrite what an old charge says.
    world = new_world(now=OVERDUE_NOW, plan=make_plan(name="Plan Esencial"))
    await world.service.start_payment(TOKEN, ORG_ID)  # charge 1, while the plan was "Plan Esencial"
    world.plans.plans[1] = make_plan(name="Plan Titán", monthly_price="799.00")
    await world.service.start_payment(TOKEN, ORG_ID)  # charge 2, another attempt, now "Plan Titán"

    charges, _ = await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    newest, oldest = charges
    assert (newest.plan, oldest.plan) == ("Plan Titán", "Plan Esencial")


async def test_the_history_can_be_filtered_by_status():
    world = new_world(now=OVERDUE_NOW)
    first_payment_id, _ = await start_and_get_ids(world)  # charge 1, stays pending
    world.plans.plans[1] = make_plan(monthly_price="799.00")
    await world.service.start_payment(TOKEN, ORG_ID)  # charge 2, another attempt
    second_payment_id = world.payments.created()[-1]
    world.payments.set_status(second_payment_id, "rejected")
    await world.service.get_status(TOKEN, ORG_ID)  # reconciles: charge 2 closes as rejected

    pending_only, pending_total = await world.service.list_charges(
        TOKEN, ORG_ID, page=1, page_size=10, status="pending"
    )
    closed_only, closed_total = await world.service.list_charges(
        TOKEN, ORG_ID, page=1, page_size=10, status="closed"
    )

    assert pending_total == 1 and [c.payment_id for c in pending_only] == [first_payment_id]
    assert closed_total == 1 and [c.payment_id for c in closed_only] == [second_payment_id]


async def test_the_history_checks_the_organization_first():
    world = new_world(now=OVERDUE_NOW)

    with pytest.raises(OrganizationNotFoundError):
        await world.service.list_charges(TOKEN, OTHER_ORG_ID, page=1, page_size=10)
    world.organizations.fail = True
    with pytest.raises(OrganizationCheckUnavailableError):
        await world.service.list_charges(TOKEN, ORG_ID, page=1, page_size=10)

    assert world.payments.create_calls == []  # nothing else was attempted

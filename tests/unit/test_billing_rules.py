"""The pure rules of the subscription periods (spec 010, research R3).

Every row of «Ejemplos de referencia del cálculo de fechas» of `specs/010-subscription-periods/spec.md`
is reproduced here exactly (SC-004), with no database and no doubles: the rules are functions of dates
and amounts. All the dates are in UTC.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from src.services.billing_rules import (
    CURRENCY,
    MONTHS,
    RESOURCE_TYPE,
    add_months,
    covered_period,
    days_remaining,
    idempotency_key,
    payment_due_at,
    period_state,
    started_at_of,
    to_minor_units,
    trial_ends_at_of,
)

PRICE = Decimal("499.00")
ORGANIZATION = UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")


def at(text: str) -> datetime:
    """`2026-12-04T15:30:00Z` → an aware datetime in UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def view(now: str, trial_ends_at: datetime | None, due: datetime, amount: Decimal = PRICE):
    moment = at(now)
    return period_state(moment, amount, trial_ends_at, due), days_remaining(due, moment)


def test_the_constants_of_the_contract():
    assert CURRENCY == "MXN"
    assert RESOURCE_TYPE == "system-api:subscription"
    assert MONTHS == {"monthly": 1, "annual": 12}


# --- Examples 1 to 6: an organization created after the cutoff, a trial of 14 days, monthly 499.00 ---

CREATED = at("2026-11-20T15:30:00Z")
CUTOFF_BEFORE = at("2026-11-01T00:00:00Z")


def test_example_1_the_first_period_starts_at_the_creation_and_the_trial_lasts_fourteen_days():
    started = started_at_of(CREATED, CUTOFF_BEFORE)
    trial_ends = trial_ends_at_of(started, 14)

    assert started == at("2026-11-20T15:30:00Z")
    assert trial_ends == at("2026-12-04T15:30:00Z")
    assert payment_due_at(started, trial_ends, None) == at("2026-12-04T15:30:00Z")


@pytest.mark.parametrize(
    ("now", "state", "days"),
    [
        ("2026-11-25T15:30:00Z", "trial", 9),  # example 2
        ("2026-11-25T16:00:00Z", "trial", 9),  # example 3: 8 d 23 h 30 min, rounded up
        ("2026-12-03T15:30:01Z", "trial", 1),  # example 4
        ("2026-12-04T15:30:00Z", "overdue", 0),  # example 5: the exact instant the trial ends
        ("2026-12-04T15:30:01Z", "overdue", 0),
        ("2026-12-10T09:00:00Z", "overdue", -5),  # example 6: 5 d 17 h 30 min late
    ],
)
def test_examples_2_to_6_the_state_and_the_days_of_the_trial(now, state, days):
    trial_ends = at("2026-12-04T15:30:00Z")

    assert view(now, trial_ends, trial_ends) == (state, days)


# --- Example 7: a monthly payment approved during the trial ---


def test_example_7_a_payment_during_the_trial_does_not_shorten_it():
    trial_ends = at("2026-12-04T15:30:00Z")

    start, end = covered_period(trial_ends, at("2026-12-01T10:00:00Z"), "monthly")

    assert (start, end) == (at("2026-12-04T15:30:00Z"), at("2027-01-04T15:30:00Z"))
    # The trial goes on (state `trial`) and the next payment is the end of the paid month.
    assert view("2026-12-01T10:05:00Z", trial_ends, end) == ("trial", 35)
    assert view("2026-12-04T15:30:00Z", trial_ends, end) == ("current", 31)
    assert view("2027-01-04T15:29:59Z", trial_ends, end) == ("current", 1)
    assert view("2027-01-04T15:30:00Z", trial_ends, end) == ("overdue", 0)


# --- Example 8: a monthly payment approved when the organization was already overdue ---


def test_example_8_an_overdue_payment_starts_at_the_approval():
    trial_ends = at("2026-12-04T15:30:00Z")

    start, end = covered_period(trial_ends, at("2026-12-10T09:30:00Z"), "monthly")

    assert (start, end) == (at("2026-12-10T09:30:00Z"), at("2027-01-10T09:30:00Z"))
    assert view("2026-12-10T09:45:00Z", trial_ends, end) == ("current", 31)


# --- Examples 9 to 11: the length of the periods ---


def test_example_9_an_annual_period_is_twelve_months():
    start = at("2026-12-04T15:30:00Z")

    assert covered_period(start, at("2026-12-01T10:00:00Z"), "annual") == (start, at("2027-12-04T15:30:00Z"))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2027-01-31T10:00:00Z", "2027-02-28T10:00:00Z"),
        ("2028-01-31T10:00:00Z", "2028-02-29T10:00:00Z"),  # a leap year
        ("2027-02-28T10:00:00Z", "2027-03-28T10:00:00Z"),  # the day that got shorter is not recovered
        ("2027-08-31T10:00:00Z", "2027-09-30T10:00:00Z"),
        ("2026-12-04T15:30:00Z", "2027-01-04T15:30:00Z"),
        ("2026-12-31T23:59:59Z", "2027-01-31T23:59:59Z"),
    ],
)
def test_example_10_a_month_keeps_the_time_and_the_day_or_the_last_day(start, end):
    assert add_months(at(start), 1) == at(end)


def test_example_10_the_shortened_day_is_not_recovered_after_a_short_month():
    first = add_months(at("2027-01-31T10:00:00Z"), 1)

    assert add_months(first, 1) == at("2027-03-28T10:00:00Z")


def test_example_11_twelve_months_from_a_leap_day():
    assert add_months(at("2028-02-29T10:00:00Z"), 12) == at("2029-02-28T10:00:00Z")


def test_a_month_keeps_the_microseconds_and_the_zone():
    moment = datetime(2026, 12, 4, 15, 30, 12, 345678, tzinfo=UTC)

    assert add_months(moment, 1) == datetime(2027, 1, 4, 15, 30, 12, 345678, tzinfo=UTC)
    assert add_months(moment, 1).tzinfo is moment.tzinfo


def test_adding_zero_months_changes_nothing_and_more_than_a_year_rolls_the_year():
    moment = at("2026-12-04T15:30:00Z")

    assert add_months(moment, 0) == moment
    assert add_months(moment, 14) == at("2028-02-04T15:30:00Z")


# --- Example 12: an organization that existed before the cutoff ---


def test_example_12_the_first_period_never_starts_before_the_cutoff():
    created = at("2026-06-01T12:00:00Z")
    cutoff = at("2026-11-18T00:00:00Z")

    started = started_at_of(created, cutoff)
    trial_ends = trial_ends_at_of(started, 14)

    assert started == at("2026-11-18T00:00:00Z")
    assert trial_ends == at("2026-12-02T00:00:00Z")
    assert view("2026-11-25T00:00:00Z", trial_ends, trial_ends) == ("trial", 7)


# --- Examples 13 to 15: no trial ---


def test_example_13_without_a_trial_the_first_payment_is_due_at_the_start():
    started = started_at_of(CREATED, CUTOFF_BEFORE)

    trial_ends = trial_ends_at_of(started, 0)
    due = payment_due_at(started, trial_ends, None)

    assert trial_ends is None
    assert due == at("2026-11-20T15:30:00Z")
    assert view("2026-11-21T09:00:00Z", trial_ends, due) == ("overdue", 0)


def test_example_14_an_existing_organization_without_a_trial_is_overdue_at_the_deployment():
    started = started_at_of(at("2026-06-01T12:00:00Z"), at("2026-11-18T00:00:00Z"))
    due = payment_due_at(started, trial_ends_at_of(started, 0), None)

    assert due == at("2026-11-18T00:00:00Z")
    assert view("2026-11-18T08:00:00Z", None, due) == ("overdue", 0)


def test_example_15_a_cutoff_in_the_future_leaves_the_organization_up_to_date():
    started = started_at_of(at("2026-06-01T12:00:00Z"), at("2026-12-18T00:00:00Z"))
    due = payment_due_at(started, trial_ends_at_of(started, 0), None)

    assert started == at("2026-12-18T00:00:00Z")
    assert view("2026-11-25T00:00:00Z", None, due) == ("current", 23)


# --- Example 16: the rounding of the days ---


@pytest.mark.parametrize(
    ("hours_to_go", "days"),
    [
        (48, 2),
        (49, 3),
        (47.99, 2),
        (0.5, 1),
        (0, 0),
        (-0.5, 0),
        (-24, -1),
        (-24.5, -1),
        (-137.5, -5),
    ],
)
def test_example_16_the_days_are_rounded_up(hours_to_go, days):
    due = at("2026-12-04T15:30:00Z")

    assert days_remaining(due, due - timedelta(hours=hours_to_go)) == days


@pytest.mark.parametrize(
    ("delta", "days"),
    [
        (timedelta(days=1), 1),
        (timedelta(days=1, microseconds=1), 2),  # one microsecond above a whole day is the next day
        (timedelta(days=1) - timedelta(microseconds=1), 1),
        (timedelta(microseconds=1), 1),
        (timedelta(0), 0),
        (-timedelta(microseconds=1), 0),
        (-timedelta(days=1), -1),
        (-timedelta(days=1, microseconds=1), -1),
        (-timedelta(days=2) - timedelta(microseconds=1), -2),
        (timedelta(days=3650), 3650),
    ],
)
def test_the_days_are_exact_to_the_microsecond_and_are_an_integer(delta, days):
    now = at("2026-12-04T15:30:00Z")

    result = days_remaining(now + delta, now)

    assert result == days
    assert type(result) is int


def test_the_days_of_an_overdue_organization_are_zero_or_negative_and_the_others_one_or_more():
    trial_ends = at("2026-12-04T15:30:00Z")
    moment = at("2026-11-01T00:00:00Z")
    while moment < at("2026-12-12T00:00:00Z"):
        state, days = view(moment.isoformat(), trial_ends, trial_ends)
        if state == "overdue":
            assert days <= 0, moment
        else:
            assert days >= 1, moment
        moment += timedelta(hours=7, minutes=13)


# --- the state ---


def test_a_free_amount_is_never_charged_even_during_the_trial_or_when_overdue():
    trial_ends = at("2026-12-04T15:30:00Z")

    for now in ("2026-11-25T15:30:00Z", "2026-12-10T09:00:00Z", "2030-01-01T00:00:00Z"):
        assert period_state(at(now), Decimal("0.00"), trial_ends, trial_ends) == "no_charge"
    assert period_state(at("2026-12-10T09:00:00Z"), Decimal("0"), None, trial_ends) == "no_charge"


def test_without_a_trial_the_state_is_never_trial():
    due = at("2026-12-04T15:30:00Z")

    assert period_state(at("2026-12-01T00:00:00Z"), PRICE, None, due) == "current"
    assert period_state(at("2026-12-05T00:00:00Z"), PRICE, None, due) == "overdue"


def test_the_trial_wins_while_it_lasts_even_if_the_payment_date_is_later():
    trial_ends = at("2026-12-04T15:30:00Z")
    paid_until = at("2027-01-04T15:30:00Z")

    assert period_state(at("2026-12-03T00:00:00Z"), PRICE, trial_ends, paid_until) == "trial"
    assert period_state(at("2026-12-04T15:30:00Z"), PRICE, trial_ends, paid_until) == "current"


def test_the_state_is_a_pure_function_of_its_arguments():
    arguments = (at("2026-12-10T09:00:00Z"), PRICE, at("2026-12-04T15:30:00Z"), at("2026-12-04T15:30:00Z"))

    assert {period_state(*arguments) for _ in range(5)} == {"overdue"}


# --- the next payment date ---


def test_the_next_payment_date_is_the_paid_until_then_the_end_of_the_trial_then_the_start():
    started = at("2026-11-20T15:30:00Z")
    trial_ends = at("2026-12-04T15:30:00Z")
    paid_until = at("2027-01-04T15:30:00Z")

    assert payment_due_at(started, trial_ends, paid_until) == paid_until
    assert payment_due_at(started, trial_ends, None) == trial_ends
    assert payment_due_at(started, None, None) == started
    assert payment_due_at(started, None, paid_until) == paid_until


# --- the covered period ---


def test_a_payment_exactly_at_the_due_date_starts_at_that_same_instant():
    due = at("2026-12-04T15:30:00Z")

    assert covered_period(due, due, "monthly") == (due, at("2027-01-04T15:30:00Z"))


def test_a_payment_long_before_the_due_date_starts_at_the_due_date():
    due = at("2026-12-04T15:30:00Z")

    start, _ = covered_period(due, at("2026-01-01T00:00:00Z"), "monthly")

    assert start == due


def test_an_unknown_billing_period_is_refused():
    with pytest.raises(ValueError):
        covered_period(at("2026-12-04T15:30:00Z"), at("2026-12-01T00:00:00Z"), "weekly")


# --- the start and the trial ---


def test_the_start_is_the_latest_of_the_creation_and_the_cutoff_in_utc():
    local = timezone(timedelta(hours=-6))
    created = datetime(2026, 11, 19, 18, 0, tzinfo=local)  # 2026-11-20T00:00:00Z
    cutoff = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)

    assert started_at_of(created, cutoff) == cutoff
    assert started_at_of(created, cutoff).utcoffset() == timedelta(0)
    assert started_at_of(cutoff, created) == cutoff  # the order of the arguments does not matter for ties


def test_the_trial_has_whole_days_of_twenty_four_hours():
    started = at("2026-11-20T15:30:12Z")

    assert trial_ends_at_of(started, 1) == at("2026-11-21T15:30:12Z")
    assert trial_ends_at_of(started, 3650) == started + timedelta(days=3650)
    assert trial_ends_at_of(started, 0) is None


# --- the amount in the minimum unit ---


@pytest.mark.parametrize(
    ("amount", "minor"),
    [
        ("499.00", 49900),
        ("0.01", 1),
        ("1234567.89", 123456789),
        ("499", 49900),
        ("499.10", 49910),
        ("99999999.99", 9999999999),
    ],
)
def test_the_amount_is_converted_to_the_minimum_unit_exactly(amount, minor):
    result = to_minor_units(Decimal(amount))

    assert result == minor
    assert type(result) is int


@pytest.mark.parametrize("amount", ["499.001", "0.005", "1.2345"])
def test_an_amount_with_more_than_two_decimals_is_refused_never_rounded(amount):
    with pytest.raises(ValueError):
        to_minor_units(Decimal(amount))


# --- the idempotency key ---

SETTLES = at("2026-12-04T15:30:00Z")


def key(**changes):
    values = {
        "organization_id": ORGANIZATION,
        "settles_due_at": SETTLES,
        "billing_period": "monthly",
        "amount_minor": 49900,
        "attempt": 1,
        "description": "Suscripción Plan Individual — mensual",
        **changes,
    }
    return idempotency_key(**values)


def test_the_key_is_deterministic_and_has_the_shape_pagos_accepts():
    result = key()

    assert result == key()
    assert result.startswith(f"sub-{ORGANIZATION}-")
    assert len(result) == 65  # Pagos admits from 1 to 100 characters
    assert result.isascii()


@pytest.mark.parametrize(
    "changes",
    [
        {"organization_id": UUID("1f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")},
        {"settles_due_at": at("2026-12-04T15:30:01Z")},
        {"billing_period": "annual"},
        {"amount_minor": 49901},
        {"attempt": 2},
        {"description": "Suscripción Plan Consultorio — mensual"},  # a plan renamed: another body, another key
    ],
)
def test_the_key_changes_with_any_condition_of_the_charge(changes):
    assert key(**changes) != key()


def test_the_key_uses_the_instant_not_the_zone_it_arrives_in():
    local = datetime(2026, 12, 4, 9, 30, tzinfo=timezone(timedelta(hours=-6)))  # the same instant

    assert key(settles_due_at=local) == key()


def test_two_attempts_of_the_same_period_have_different_keys():
    assert len({key(attempt=attempt) for attempt in range(1, 20)}) == 19

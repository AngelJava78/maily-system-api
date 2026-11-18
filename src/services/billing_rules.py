"""The pure rules of the subscription periods (spec 010, research R3).

Functions of dates and amounts only: no I/O, no clock, no database. The Service reads the world and
hands the values to these functions, so the rules that the business will look at the most (when the
trial ends, what state an organization is in, how long a payment covers) can be tested with a table of
dates and no doubles.

Every date is an aware `datetime` in UTC. A day is 24 hours (UTC has no daylight saving time). The
amounts are `Decimal` in Mexican pesos, never `float` (Principle VI).
"""

import calendar
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

CURRENCY = "MXN"
# What a charge references in the payments API: «what is being paid» (an opaque, namespaced pair).
RESOURCE_TYPE = "system-api:subscription"
# The length of a billing period in calendar months (FR-029).
MONTHS = {"monthly": 1, "annual": 12}

PeriodState = Literal["trial", "current", "overdue", "no_charge"]

_ONE_DAY = timedelta(days=1)


def add_months(moment: datetime, months: int) -> datetime:
    """`moment` plus `months` calendar months, keeping the time of day and the zone (FR-030).

    The day of the month is kept; if it does not exist in the resulting month, the last day of that
    month is used (31 January + 1 month is 28 February, or 29 in a leap year). Each period starts at the
    end of the previous one, so a day that got shorter is not recovered afterwards.
    """
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def started_at_of(created_at: datetime, cutoff: datetime) -> datetime:
    """When the first period starts: the creation of the organization, never before the cutoff (FR-008)."""
    return max(created_at.astimezone(UTC), cutoff.astimezone(UTC))


def trial_ends_at_of(started_at: datetime, trial_days: int) -> datetime | None:
    """When the trial ends: whole days of 24 hours from the start; `None` without a trial (FR-009)."""
    if trial_days == 0:
        return None
    return started_at + timedelta(days=trial_days)


def payment_due_at(
    started_at: datetime, trial_ends_at: datetime | None, paid_until: datetime | None
) -> datetime:
    """The date of the next payment (FR-010).

    Until a payment is applied it is the end of the trial, or the start when there is no trial; every
    applied payment moves it to the end of the period that it covers (`paid_until`).
    """
    if paid_until is not None:
        return paid_until
    if trial_ends_at is not None:
        return trial_ends_at
    return started_at


def period_state(
    now: datetime, amount: Decimal, trial_ends_at: datetime | None, due: datetime
) -> PeriodState:
    """The state of an organization at `now`, evaluated in this order (FR-013).

    `no_charge` when the current amount is 0.00; `trial` while there is a trial and it has not ended;
    `overdue` from the instant of the next payment date on (no grace period); `current` otherwise.
    A payment made during the trial does not change the state: it stays `trial` until the trial ends.
    """
    if amount == 0:
        return "no_charge"
    if trial_ends_at is not None and now < trial_ends_at:
        return "trial"
    if now >= due:
        return "overdue"
    return "current"


def days_remaining(due: datetime, now: datetime) -> int:
    """The days between `now` and `due`, rounded up; zero or negative once it has fallen due (FR-014).

    Exact to the microsecond and without floating point: the ceiling of a division of two durations.
    `-5` are five whole days of delay; `0` is a delay of less than 24 hours (or the exact instant).
    """
    return -((now - due) // _ONE_DAY)


def covered_period(
    due: datetime, approved_at: datetime, billing_period: str
) -> tuple[datetime, datetime]:
    """The period that an approved payment covers: its start and its end (FR-029).

    It starts at the payment date that was current if the payment arrived on time (it was approved
    before that date) and at the approval if the organization was already overdue. A payment during the
    trial therefore starts when the trial ends and never shortens it. It lasts one calendar month if
    the billing period is monthly and twelve if it is annual.
    """
    months = MONTHS.get(billing_period)
    if months is None:
        raise ValueError("Unknown billing period")
    start = due if approved_at < due else approved_at
    return start, add_months(start, months)


def to_minor_units(amount: Decimal) -> int:
    """The amount in the minimum unit of the currency (centavos), as the payments API wants it (FR-017).

    Exact: 499.00 is 49900. An amount with more than two decimals is refused, never rounded.
    """
    minor = amount * 100
    if minor != minor.to_integral_value():
        raise ValueError("The amount has more than two decimals")
    return int(minor)


def idempotency_key(
    organization_id: UUID,
    settles_due_at: datetime,
    billing_period: str,
    amount_minor: int,
    attempt: int,
    description: str,
) -> str:
    """The `Idempotency-Key` of a charge: deterministic, 65 characters (research R6).

    The same organization, payment date that it settles, billing period, amount, attempt and description
    always give the same key, so asking twice for the same charge (also after a lost answer) gives the
    same payment in the payments API; a new attempt after a closed charge gives another key and so a new
    payment. The description is part of the key because the payments API refuses (409) the same key with
    another body: a plan renamed between a lost answer and its retry gets another key, and so another
    payment (the first one was never registered nor offered), instead of staying stuck on that refusal.
    """
    conditions = (
        f"{settles_due_at.astimezone(UTC).isoformat()}|{billing_period}|{amount_minor}|{attempt}|{description}"
    )
    digest = hashlib.sha256(conditions.encode()).hexdigest()[:24]
    return f"sub-{organization_id}-{digest}"

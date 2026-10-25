"""When the database is on (spec 005, FR-033 to FR-035, SC-013; research R12).

`in_window` and `next_start` are pure functions: the day and the time are those of the zone at that
instant, with its rules of summer time. The cases are the ones verified in research R12; Mexico City
has no summer time (UTC-6), Tijuana does (UTC-7 in summer, UTC-8 in winter).
"""

import dataclasses
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.config import DatabaseSchedule
from src.services.health_schedule import in_window, next_start
from tests.health_support import RUNBOOK_SCHEDULE

TIJUANA = ZoneInfo("America/Tijuana")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- in_window ---


@pytest.mark.parametrize(
    ("instant", "inside"),
    [
        ("2026-10-27T16:00:00Z", True),  # Tuesday 10:00
        ("2026-10-24T01:30:00Z", True),  # Friday 19:30, already Saturday in UTC
        ("2026-10-27T14:00:00Z", True),  # Tuesday 08:00 sharp: the window opens
        ("2026-10-28T02:00:00Z", False),  # Tuesday 20:00 sharp: the window is closed
        ("2026-10-28T03:00:00Z", False),  # Tuesday 21:00
        ("2026-10-27T13:59:59Z", False),  # Tuesday 07:59:59
        ("2026-10-24T16:00:00Z", False),  # Saturday 10:00
        ("2026-10-25T18:00:00Z", False),  # Sunday 12:00
    ],
)
def test_the_window_is_evaluated_with_the_day_and_the_time_of_the_zone(instant, inside):
    assert in_window(RUNBOOK_SCHEDULE, utc(instant)) is inside


# --- next_start ---


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        ("2026-10-28T03:00:00Z", "2026-10-28T14:00:00Z"),  # Tuesday 21:00 -> Wednesday 08:00
        ("2026-10-24T03:00:00Z", "2026-10-26T14:00:00Z"),  # Friday 21:00 -> Monday 08:00
        ("2026-10-24T03:15:00Z", "2026-10-26T14:00:00Z"),  # Friday 23 October 2026, 21:15
        ("2026-10-24T16:00:00Z", "2026-10-26T14:00:00Z"),  # Saturday 10:00 -> Monday 08:00
        ("2026-10-27T13:00:00Z", "2026-10-27T14:00:00Z"),  # Tuesday 07:00 -> that Tuesday 08:00
        ("2026-10-27T14:00:00Z", "2026-10-28T14:00:00Z"),  # at the opening -> the next one
    ],
)
def test_the_next_start_is_the_first_opening_after_the_instant(instant, expected):
    found = next_start(RUNBOOK_SCHEDULE, utc(instant))

    assert found == utc(expected)
    assert found.tzinfo is UTC
    assert found > utc(instant)


def test_a_schedule_of_one_day_waits_for_the_next_week():
    only_tuesday = dataclasses.replace(RUNBOOK_SCHEDULE, days=frozenset({1}))

    # Tuesday 21:00 -> Tuesday 3 November at 08:00.
    assert next_start(only_tuesday, utc("2026-10-28T03:00:00Z")) == utc("2026-11-03T14:00:00Z")


def test_the_next_start_follows_the_change_of_summer_time():
    in_tijuana = dataclasses.replace(RUNBOOK_SCHEDULE, zone=TIJUANA)

    # Friday 30 October 2026 at 21:00 (UTC-7) -> Monday 2 November at 08:00, already UTC-8.
    found = next_start(in_tijuana, utc("2026-10-31T04:00:00Z"))

    assert found == utc("2026-11-02T16:00:00Z")
    assert found.tzinfo is UTC


def test_a_start_that_does_not_exist_that_day_is_the_instant_of_the_jump():
    # On Sunday 14 March 2027 the clock of Tijuana jumps from 02:00 to 03:00: 02:30 does not exist.
    sunday_at_half_past_two = DatabaseSchedule(TIJUANA, frozenset({6}), time(2, 30), time(5, 0))

    found = next_start(sunday_at_half_past_two, utc("2027-03-13T20:00:00Z"))  # Saturday 12:00

    assert found == utc("2027-03-14T10:00:00Z")
    assert found.tzinfo is UTC


def test_a_start_that_happens_twice_that_day_is_the_first():
    # On Sunday 7 November 2027 the clock of Tijuana goes back from 02:00 to 01:00: 01:30 happens
    # twice (UTC-7 and then UTC-8).
    sunday_at_half_past_one = DatabaseSchedule(TIJUANA, frozenset({6}), time(1, 30), time(5, 0))

    found = next_start(sunday_at_half_past_one, utc("2027-11-06T19:00:00Z"))  # Saturday 12:00

    assert found == utc("2027-11-07T08:30:00Z")

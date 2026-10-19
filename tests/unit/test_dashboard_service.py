"""Business rules of the dashboard Service, with a fake data source (Principle V).

Sections: the summary (user story 1), the effective quantity (story 3) and the degradation of a
source that fails (story 6).
"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest

from src.integrations.dashboard_source import ClinicCounts
from src.services.dashboard_service import DashboardService
from tests.dashboard_support import (
    LEAK_MARKER,
    QUERIES,
    FakeDashboardSource,
    make_clinic,
    newest_first,
)


def at(day: int) -> datetime:
    return datetime(2026, 9, day, 12, 0, tzinfo=UTC)


def ids(clinics) -> list:
    return [clinic.id for clinic in clinics]


# --- the summary (user story 1) ---


async def test_it_builds_the_view_with_the_six_values_and_the_list():
    clinics = [make_clinic(n) for n in range(1, 4)]
    source = FakeDashboardSource(
        clinics=clinics, counts=ClinicCounts(20, 12, 5), doctors=7, patients=80, users=9
    )

    view = await DashboardService(source, 5).get("tok")

    assert (
        view.total_clinics,
        view.active_clinics,
        view.trial_clinics,
        view.total_doctors,
        view.total_patients,
        view.total_users,
    ) == (20, 12, 5, 7, 80, 9)
    assert ids(view.recent_clinics) == ids(newest_first(clinics))


async def test_every_query_is_asked_once_with_the_token_and_the_default_quantity():
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 4)])

    await DashboardService(source, 5).get("tok")

    assert source.called("recent_clinics") == [("tok", 5)]
    for name in QUERIES:
        if name != "recent_clinics":
            assert source.called(name) == [("tok",)], name


async def test_the_service_sorts_and_cuts_even_if_the_source_does_not():
    # ids 6 and 8 share the newest instant; 1, 2 and 3 the next one; 4 and 5 an older one
    instants = {1: at(10), 2: at(10), 3: at(10), 4: at(5), 5: at(5), 6: at(20), 7: at(1), 8: at(20)}
    stored = [make_clinic(n, created_at=instants[n]) for n in (3, 8, 5, 1, 7, 6, 4, 2)]
    source = FakeDashboardSource(clinics=stored, honor_order=False)

    view = await DashboardService(source, 5).get("tok")

    # newest first; ties by id ascending; only the five asked for
    assert ids(view.recent_clinics) == [make_clinic(n).id for n in (6, 8, 1, 2, 3)]


@pytest.mark.parametrize("default", [3, 5, 10])
async def test_the_default_quantity_is_the_one_of_the_configuration(default):
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 13)])

    view = await DashboardService(source, default).get("tok")

    assert len(view.recent_clinics) == default
    assert source.called("recent_clinics") == [("tok", default)]


async def test_the_five_queries_run_at_the_same_time():
    source = FakeDashboardSource(clinics=[make_clinic(1)], barrier=asyncio.Barrier(5))

    # In sequence the first query would wait forever for the other four.
    async with asyncio.timeout(1):
        view = await DashboardService(source, 5).get("tok")

    assert len(view.recent_clinics) == 1


async def test_nothing_is_kept_between_requests():
    source = FakeDashboardSource(clinics=[make_clinic(1)])
    service = DashboardService(source, 5)

    await service.get("tok")
    await service.get("tok")

    for name in QUERIES:
        assert len(source.called(name)) == 2, name


# --- the effective quantity (user story 3) ---


async def test_the_requested_quantity_is_what_is_asked_to_the_source_and_returned():
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 13)])

    view = await DashboardService(source, 5).get("tok", 3)

    assert source.called("recent_clinics") == [("tok", 3)]
    assert ids(view.recent_clinics) == ids(newest_first(source.clinics))[:3]


@pytest.mark.parametrize("requested", [11, 1000, 10**18])
async def test_more_than_ten_is_not_an_error_it_is_ten(requested):
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 13)])

    view = await DashboardService(source, 5).get("tok", requested)

    assert len(view.recent_clinics) == 10
    assert source.called("recent_clinics") == [("tok", 10)]


@pytest.mark.parametrize("default", [3, 5, 10])
async def test_without_a_requested_quantity_the_configured_default_rules(default):
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 13)])

    view = await DashboardService(source, default).get("tok", None)

    assert len(view.recent_clinics) == default


async def test_the_requested_quantity_wins_over_the_default():
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 13)])

    view = await DashboardService(source, 3).get("tok", 7)

    assert len(view.recent_clinics) == 7


async def test_one_is_the_most_recent_clinic():
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 6)])

    view = await DashboardService(source, 5).get("tok", 1)

    assert ids(view.recent_clinics) == [make_clinic(5).id]


async def test_with_fewer_clinics_than_requested_all_of_them_come_back_without_padding():
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 5)])

    view = await DashboardService(source, 5).get("tok", 10)

    assert len(view.recent_clinics) == 4
    assert view.total_clinics == 4


async def test_with_no_clinics_the_list_is_empty_and_the_six_values_are_zero_not_none():
    source = FakeDashboardSource(clinics=[], doctors=0, patients=0, users=0)

    view = await DashboardService(source, 5).get("tok", 10)

    assert view.recent_clinics == []
    assert (
        view.total_clinics,
        view.active_clinics,
        view.trial_clinics,
        view.total_doctors,
        view.total_patients,
        view.total_users,
    ) == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("requested", [0, -1])
async def test_a_quantity_below_one_is_a_programming_error(requested):
    service = DashboardService(FakeDashboardSource(), 5)

    with pytest.raises(ValueError):
        await service.get("tok", requested)


@pytest.mark.parametrize("honor_order", [True, False])
async def test_when_a_tie_is_cut_the_clinic_with_the_smaller_id_gets_in(honor_order):
    same = at(10)
    stored = [make_clinic(n, created_at=same) for n in (3, 1, 2)]
    source = FakeDashboardSource(clinics=stored, honor_order=honor_order)

    view = await DashboardService(source, 5).get("tok", 2)

    assert ids(view.recent_clinics) == [make_clinic(1).id, make_clinic(2).id]


# --- a source that fails (user story 6) ---

VALUES = ("total_clinics", "active_clinics", "trial_clinics", "total_doctors", "total_patients", "total_users")


def healthy_source(**changes) -> FakeDashboardSource:
    values = {"clinics": [make_clinic(n) for n in range(1, 4)], "doctors": 7, "patients": 80, "users": 9}
    return FakeDashboardSource(**{**values, **changes})


def values_of(view) -> dict:
    return {name: getattr(view, name) for name in VALUES}


async def intact() -> tuple[dict, list]:
    view = await DashboardService(healthy_source(), 5).get("tok")
    return values_of(view), view.recent_clinics


@pytest.mark.parametrize(
    ("failing", "lost"),
    [
        ("clinic_counts", {"total_clinics", "active_clinics", "trial_clinics"}),
        ("doctors_total", {"total_doctors"}),
        ("patients_total", {"total_patients"}),
        ("users_total", {"total_users"}),
    ],
)
async def test_a_failing_source_leaves_only_its_own_indicators_unavailable(failing, lost):
    expected, expected_list = await intact()

    view = await DashboardService(healthy_source(fail={failing}), 5).get("tok")

    for name, value in values_of(view).items():
        assert value is None if name in lost else value == expected[name], name
    assert ids(view.recent_clinics) == ids(expected_list)


async def test_when_the_recent_clinics_fail_the_list_is_none_not_empty():
    expected, _ = await intact()

    view = await DashboardService(healthy_source(fail={"recent_clinics"}), 5).get("tok")

    assert view.recent_clinics is None  # an empty list would claim "there are no clinics"
    assert values_of(view) == expected


async def test_when_every_source_fails_everything_is_none_and_nothing_is_raised():
    view = await DashboardService(healthy_source(fail=set(QUERIES)), 5).get("tok")

    assert values_of(view) == dict.fromkeys(VALUES)
    assert view.recent_clinics is None


async def test_a_source_that_answers_there_is_nothing_gives_zero_and_empty_not_none():
    view = await DashboardService(FakeDashboardSource(), 5).get("tok")

    assert values_of(view) == dict.fromkeys(VALUES, 0)
    assert view.recent_clinics == []


async def test_an_error_that_is_not_an_unavailable_source_is_not_hidden():
    service = DashboardService(healthy_source(crash={"users_total"}), 5)

    with pytest.raises(RuntimeError, match="boom"):
        await service.get("tok")


async def test_every_query_is_still_asked_when_one_fails():
    source = healthy_source(fail={"doctors_total"})

    await DashboardService(source, 5).get("tok")

    for name in QUERIES:
        assert len(source.called(name)) == 1, name


async def test_each_failure_is_logged_without_the_token_or_the_detail_of_the_source(caplog):
    source = healthy_source(fail={"doctors_total", "recent_clinics"})

    with caplog.at_level(logging.DEBUG):
        await DashboardService(source, 5).get("tok-secreto-1")

    warnings = sorted(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert warnings == [
        "Dashboard source unavailable: doctors_total",
        "Dashboard source unavailable: recent_clinics",
    ]
    assert "tok-secreto-1" not in caplog.text
    assert LEAK_MARKER not in caplog.text

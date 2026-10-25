"""Rules of the health aggregation (spec 005; research R8 to R10, R23).

`HealthService` with doubles: a scripted probe, a registry reader, a database pinger and a clock that
only moves when the test says so. No network and no database.
"""

import asyncio
import dataclasses
import logging
from datetime import UTC, datetime

import pytest

from src.config import AllowedHosts, BuildInfo, HealthConfig
from src.repositories.errors import DatabaseUnavailableError
from src.services.health_service import ComponentTarget, HealthService, global_status
from src.services.health_state import HealthState
from tests.health_support import (
    INFO_OK,
    RUNBOOK_SCHEDULE,
    TEST_HEALTH_CONFIG,
    TEST_NOW,
    FakeClock,
    FakeProbe,
    failed_answer,
    json_answer,
    make_component,
    service_answers,
    wait_until,
)

CONFIG = dataclasses.replace(
    TEST_HEALTH_CONFIG,
    check_timeout_seconds=0.2,
    allowed_hosts=AllowedHosts.parse("components.test,.components.test"),
)
BUILD = BuildInfo("maily-system-api", "2.0.0", "3c81089d", "2026-10-24T16:05:00Z", "staging")
NOT_READY = {
    "status": "unavailable",
    "checks": [{"name": "database", "status": "error", "latency_ms": 2001, "error": "timeout"}],
}


class Pinger:
    """The trivial query of the database: fine, failing with a given exception, or slow."""

    def __init__(self, error: BaseException | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error


class Reader:
    """The read of the registry: the components it holds, an exception, or a slow read."""

    def __init__(self, components=(), error: BaseException | None = None, delay: float = 0.0) -> None:
        self.components = list(components)
        self.error = error
        self.delay = delay
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return list(self.components)


def build_service(
    *,
    probe: FakeProbe | None = None,
    reader: Reader | None = None,
    pinger: Pinger | None = None,
    config: HealthConfig = CONFIG,
    clock: FakeClock | None = None,
    state: HealthState | None = None,
) -> HealthService:
    return HealthService(
        state=state or HealthState(),
        config=config,
        build=BUILD,
        clock=clock or FakeClock(),
        probe=probe or FakeProbe(),
        read_registry=reader or Reader(),
        ping_database=pinger or Pinger(),
    )


def by_code(result) -> dict:
    return {component.code: component for component in result.components}


def base(code: str) -> str:
    return f"http://{code}.components.test"


# --- (a) the rules of a service ---


async def test_a_service_whose_three_routes_answer_well_is_up_with_its_build_and_checks():
    probe = FakeProbe(service_answers(base("usuarios")))

    result = await build_service(probe=probe, reader=Reader([make_component("usuarios")])).health()

    component = by_code(result)["usuarios"]
    assert (component.status, component.error, component.latency_ms) == ("up", None, 11)
    assert (component.version, component.commit, component.environment) == ("1.4.2", "0123456789abcdef", "e2e")
    assert component.build_date == "2026-10-20T21:30:00Z"
    assert [check.name for check in component.checks] == ["database"]
    assert component.next_start_at is None
    assert component.kind == "service"


@pytest.mark.parametrize(
    ("ready", "error"),
    [
        (json_answer(503, NOT_READY), "not_ready"),
        (failed_answer("timeout"), "timeout"),
        (json_answer(200, {"status": "ok"}), "invalid_response"),
        (json_answer(500, {}), "unexpected_status"),
    ],
)
async def test_a_live_service_whose_readiness_fails_is_degraded(ready, error):
    probe = FakeProbe(service_answers(base("pacientes"), ready=ready))

    result = await build_service(probe=probe, reader=Reader([make_component("pacientes")])).health()

    component = by_code(result)["pacientes"]
    assert (component.status, component.error) == ("degraded", error)


async def test_a_not_ready_service_keeps_the_checks_it_reported():
    probe = FakeProbe(service_answers(base("pacientes"), ready=json_answer(503, NOT_READY)))

    result = await build_service(probe=probe, reader=Reader([make_component("pacientes")])).health()

    [check] = by_code(result)["pacientes"].checks
    assert (check.name, check.status, check.error) == ("database", "error", "timeout")


@pytest.mark.parametrize(
    ("live", "error"),
    [
        (failed_answer("dns_error"), "dns_error"),
        (failed_answer("timeout"), "timeout"),
        (json_answer(500, {}), "unexpected_status"),
        (json_answer(200, {"status": "fine"}), "invalid_response"),
    ],
)
async def test_a_service_whose_live_route_fails_is_down(live, error):
    probe = FakeProbe(service_answers(base("caido"), live=live))

    result = await build_service(probe=probe, reader=Reader([make_component("caido")])).health()

    component = by_code(result)["caido"]
    assert (component.status, component.error) == ("down", error)


async def test_a_failing_info_leaves_the_build_unknown_without_changing_the_status():
    probe = FakeProbe(service_answers(base("usuarios"), info=failed_answer("timeout")))

    result = await build_service(probe=probe, reader=Reader([make_component("usuarios")])).health()

    component = by_code(result)["usuarios"]
    assert component.status == "up"
    assert (component.version, component.commit, component.build_date, component.environment) == (
        "unknown",
        "unknown",
        "unknown",
        "unknown",
    )


# --- (b) the rules of a frontend ---


async def test_a_frontend_is_up_with_any_2xx_and_checked_by_its_status_only():
    url = f"{base('mailysoft')}/healthz/"
    probe = FakeProbe({url: json_answer(204, None)})
    component = make_component("mailysoft", kind="frontend")

    result = await build_service(probe=probe, reader=Reader([component])).health()

    frontend = by_code(result)["mailysoft"]
    assert (frontend.status, frontend.error, frontend.kind) == ("up", None, "frontend")
    assert frontend.version == "unknown"
    assert probe.calls == [("status", url)]


@pytest.mark.parametrize(("answer", "error"), [(json_answer(404, {}), "unexpected_status"), (json_answer(301, {}), "unexpected_status"), (failed_answer("connection_error"), "connection_error")])
async def test_a_frontend_with_another_answer_is_down(answer, error):
    probe = FakeProbe({f"{base('mailysoft')}/healthz/": answer})
    component = make_component("mailysoft", kind="frontend")

    result = await build_service(probe=probe, reader=Reader([component])).health()

    assert (by_code(result)["mailysoft"].status, by_code(result)["mailysoft"].error) == ("down", error)


async def test_a_frontend_with_an_info_route_reads_it():
    answers = {
        f"{base('web')}/healthz/": json_answer(200, None),
        f"{base('web')}/version.json": json_answer(200, INFO_OK),
    }
    component = make_component("web", kind="frontend", info_path="/version.json")

    result = await build_service(probe=FakeProbe(answers), reader=Reader([component])).health()

    assert by_code(result)["web"].version == "1.4.2"


# --- (c) the integrated components ---


async def test_with_the_database_answering_both_integrated_components_are_up():
    pinger = Pinger()
    probe = FakeProbe()

    result = await build_service(probe=probe, pinger=pinger).health()

    own, database = result.components[:2]
    assert (own.code, own.name, own.kind, own.status, own.error) == (
        "maily-system-api",
        "MailySoft System API",
        "service",
        "up",
        None,
    )
    assert (own.version, own.commit, own.build_date, own.environment) == (
        "2.0.0",
        "3c81089d",
        "2026-10-24T16:05:00Z",
        "staging",
    )
    [check] = own.checks
    assert (check.name, check.status, check.error) == ("database", "ok", None)
    assert own.latency_ms == check.latency_ms == database.latency_ms
    assert (database.code, database.name, database.kind, database.status) == ("database", "Base de datos", "database", "up")
    assert database.checks == ()
    assert database.version == "unknown"
    assert pinger.calls == 1  # one query per aggregation, reused by maily-system-api
    assert probe.calls == []  # the service never calls itself over HTTP


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (DatabaseUnavailableError("connection_error"), "connection_error"),
        (DatabaseUnavailableError("unexpected_error"), "unexpected_error"),
        (RuntimeError("SECRETO-INTERNO"), "unexpected_error"),
    ],
)
async def test_with_the_database_failing_it_is_down_and_this_service_degraded(error, code):
    result = await build_service(pinger=Pinger(error)).health()

    own, database = result.components[:2]
    assert (database.status, database.error, database.next_start_at) == ("down", code, None)
    assert (own.status, own.error) == ("degraded", "not_ready")
    assert own.checks[0].error == code
    assert result.status == "down"


async def test_a_database_that_does_not_answer_in_time_is_a_timeout():
    result = await build_service(pinger=Pinger(delay=5)).health()

    assert result.components[1].error == "timeout"


# --- (d) the allowed hosts are checked again on every aggregation ---


async def test_a_component_whose_host_is_no_longer_allowed_is_unknown_and_not_called():
    probe = FakeProbe(service_answers("http://otro.example"))
    component = make_component("fuera", base_url="http://otro.example")

    result = await build_service(probe=probe, reader=Reader([component])).health()

    fuera = by_code(result)["fuera"]
    assert (fuera.status, fuera.error, fuera.latency_ms, fuera.checks) == ("unknown", "host_not_allowed", None, ())
    assert probe.calls == []


async def test_without_a_list_every_registered_component_is_unknown():
    config = dataclasses.replace(CONFIG, allowed_hosts=AllowedHosts())
    probe = FakeProbe(service_answers(base("usuarios")))

    result = await build_service(probe=probe, reader=Reader([make_component("usuarios")]), config=config).health()

    assert by_code(result)["usuarios"].error == "host_not_allowed"
    assert probe.calls == []


# --- (e) a failure of the aggregator itself ---


async def test_an_unexpected_failure_while_checking_a_component_only_affects_that_one(caplog):
    async def boom():
        raise RuntimeError("http://usuarios.components.test SECRETO-INTERNO")

    answers = {**service_answers(base("roto"), live=boom), **service_answers(base("sano"))}
    reader = Reader([make_component("roto"), make_component("sano")])

    with caplog.at_level(logging.ERROR):
        result = await build_service(probe=FakeProbe(answers), reader=reader).health()

    assert (by_code(result)["roto"].status, by_code(result)["roto"].error) == ("unknown", "unexpected_error")
    assert by_code(result)["sano"].status == "up"
    assert "roto" in caplog.text
    assert "components.test" not in caplog.text
    assert "SECRETO-INTERNO" not in caplog.text


async def test_a_component_whose_calls_hang_does_not_delay_the_aggregation():
    async def hang():
        await asyncio.sleep(30)

    answers = service_answers(base("colgado"), live=hang, ready=hang, info=hang)
    loop = asyncio.get_running_loop()
    started = loop.time()

    result = await build_service(probe=FakeProbe(answers), reader=Reader([make_component("colgado")])).health()

    assert loop.time() - started < CONFIG.check_timeout_seconds + 1  # FR-019
    assert (by_code(result)["colgado"].status, by_code(result)["colgado"].error) == ("down", "timeout")


# --- (f) the global status ---


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["up", "up"], "ok"),
        (["up", "degraded"], "degraded"),
        (["up", "stopped"], "degraded"),
        (["up", "unknown"], "degraded"),
        (["degraded", "down"], "down"),
        (["stopped", "down", "unknown"], "down"),
    ],
)
def test_the_global_status_follows_the_worst_component(statuses, expected):
    components = [dataclasses.make_dataclass("C", ["status"])(status) for status in statuses]

    assert global_status(components) == expected


async def test_an_unavailable_registry_does_not_change_the_global_status_by_itself():
    result = await build_service(reader=Reader(error=RuntimeError("no hay base"))).health()

    assert (result.status, result.registry_available) == ("ok", False)


# --- (g) the order ---


async def test_the_integrated_components_go_first_and_then_by_sort_order_and_code():
    components = [
        make_component("zeta", sort_order=1),
        make_component("ab", sort_order=5),
        make_component("a-c", sort_order=5),  # a hyphen sorts before a letter (code point)
        make_component("beta", sort_order=1),
    ]
    probe = FakeProbe({url: answer for c in components for url, answer in service_answers(c.base_url).items()})

    result = await build_service(probe=probe, reader=Reader(components)).health()

    assert [c.code for c in result.components] == ["maily-system-api", "database", "beta", "zeta", "a-c", "ab"]


# --- (h) the registry ---


async def test_an_unreadable_registry_shows_only_the_integrated_components():
    result = await build_service(reader=Reader([make_component("x")], error=RuntimeError("caída"))).health()

    assert [c.code for c in result.components] == ["maily-system-api", "database"]
    assert result.registry_available is False


async def test_an_empty_registry_is_available():
    result = await build_service(reader=Reader([])).health()

    assert [c.code for c in result.components] == ["maily-system-api", "database"]
    assert result.registry_available is True


# --- (i) everything runs at the same time ---


async def test_the_database_and_the_registry_are_asked_at_the_same_time():
    ping_started = asyncio.Event()

    class SlowPinger(Pinger):
        async def __call__(self):
            ping_started.set()
            await asyncio.sleep(0.05)

    class WaitingReader(Reader):
        async def __call__(self):
            await asyncio.wait_for(ping_started.wait(), timeout=1)  # never set if they were in sequence
            return []

    result = await build_service(reader=WaitingReader(), pinger=SlowPinger()).health()

    assert result.registry_available is True


async def test_the_checks_start_when_the_list_is_known_without_waiting_for_the_database():
    probe = FakeProbe(service_answers(base("usuarios")))

    class WaitingPinger(Pinger):
        async def __call__(self):
            await wait_until(lambda: probe.calls, timeout=1)  # fails if the checks waited for it

    result = await build_service(probe=probe, reader=Reader([make_component("usuarios")]), pinger=WaitingPinger()).health()

    # In sequence, the query would time out (0.2 s) waiting for checks that had not started.
    assert by_code(result)["database"].status == "up"
    assert by_code(result)["usuarios"].status == "up"


async def test_the_three_calls_of_a_service_run_at_the_same_time():
    probe = FakeProbe(service_answers(base("usuarios")), delay=0.05)

    await build_service(probe=probe, reader=Reader([make_component("usuarios")])).health()

    assert probe.max_active == 3


# --- (j) the shared cache ---


async def test_within_the_cache_period_the_result_is_reused_with_its_original_dates():
    probe = FakeProbe(service_answers(base("usuarios")))
    clock = FakeClock()
    service = build_service(
        probe=probe,
        reader=Reader([make_component("usuarios")]),
        config=dataclasses.replace(CONFIG, cache_seconds=15),
        clock=clock,
    )

    first = await service.health()
    clock.advance(14.9)
    second = await service.health()

    assert second is first
    assert len(probe.calls) == 3


async def test_once_the_cache_period_ends_a_new_aggregation_runs():
    probe = FakeProbe(service_answers(base("usuarios")))
    clock = FakeClock()
    service = build_service(
        probe=probe,
        reader=Reader([make_component("usuarios")]),
        config=dataclasses.replace(CONFIG, cache_seconds=15),
        clock=clock,
    )

    first = await service.health()
    clock.advance(15)
    second = await service.health()

    assert second is not first
    assert second.checked_at > first.checked_at
    assert len(probe.calls) == 6


async def test_with_cache_zero_every_query_runs_a_new_aggregation():
    probe = FakeProbe(service_answers(base("usuarios")))
    service = build_service(probe=probe, reader=Reader([make_component("usuarios")]))

    await service.health()
    await service.health()

    assert len(probe.calls) == 6


async def test_fifty_simultaneous_queries_share_one_aggregation():
    probe = FakeProbe(service_answers(base("usuarios")), delay=0.05)
    reader = Reader([make_component("usuarios")])
    service = build_service(probe=probe, reader=reader)

    results = await asyncio.gather(*(service.health() for _ in range(50)))

    assert len({id(result) for result in results}) == 1
    assert len(probe.calls) == 3
    assert reader.calls == 1


async def test_cancelling_the_query_that_started_the_aggregation_does_not_cancel_it():
    probe = FakeProbe(service_answers(base("usuarios")), delay=0.1)
    service = build_service(probe=probe, reader=Reader([make_component("usuarios")]))

    first = asyncio.create_task(service.health())
    await wait_until(lambda: probe.calls)
    second = asyncio.create_task(service.health())
    await asyncio.sleep(0)
    first.cancel()

    result = await second
    assert by_code(result)["usuarios"].status == "up"
    assert first.cancelled()


# --- (k) a change of the registry ---


async def test_after_an_invalidation_the_finished_result_is_not_reused():
    state = HealthState()
    reader = Reader([])
    service = build_service(reader=reader, config=dataclasses.replace(CONFIG, cache_seconds=15), state=state)

    await service.health()
    reader.components = [make_component("nuevo")]
    state.invalidate()
    result = await service.health()

    assert "nuevo" in by_code(result)


async def test_an_aggregation_started_before_a_change_is_awaited_and_then_another_runs():
    state = HealthState()
    release = asyncio.Event()
    running = 0
    most_at_once = 0

    class SlowReader(Reader):
        """The first read takes what the registry had when it started and waits to be released."""

        async def __call__(self):
            nonlocal running, most_at_once
            self.calls += 1
            what_it_read = list(self.components)
            running += 1
            most_at_once = max(most_at_once, running)
            try:
                if self.calls == 1:
                    await release.wait()
                return what_it_read
            finally:
                running -= 1

    reader = SlowReader([])
    service = build_service(reader=reader, state=state, config=dataclasses.replace(CONFIG, check_timeout_seconds=2))

    before = asyncio.create_task(service.health())
    await wait_until(lambda: reader.calls == 1)
    reader.components = [make_component("nuevo")]
    state.invalidate()
    after = asyncio.create_task(service.health())
    await asyncio.sleep(0.02)
    release.set()

    assert "nuevo" not in by_code(await before)
    assert "nuevo" in by_code(await after)
    assert most_at_once == 1
    assert reader.calls == 2


# --- readiness and info (user story 2) ---


async def test_readiness_is_ok_when_the_database_answers():
    result = await build_service().readiness()

    assert result.ok is True
    assert (result.check.name, result.check.status, result.check.error) == ("database", "ok", None)
    assert result.check.latency_ms >= 0


@pytest.mark.parametrize(
    ("pinger", "error"),
    [
        (Pinger(delay=5), "timeout"),
        (Pinger(DatabaseUnavailableError("connection_error")), "connection_error"),
        (Pinger(DatabaseUnavailableError("unexpected_error")), "unexpected_error"),
        (Pinger(RuntimeError("SECRETO-INTERNO")), "unexpected_error"),
    ],
)
async def test_readiness_fails_with_the_kind_of_failure_and_its_latency(pinger, error):
    config = dataclasses.replace(CONFIG, ready_timeout_seconds=0.2)

    result = await build_service(pinger=pinger, config=config).readiness()

    assert result.ok is False
    assert (result.check.status, result.check.error) == ("error", error)
    assert isinstance(result.check.latency_ms, int)


async def test_simultaneous_readiness_checks_share_one_query_and_keep_nothing():
    pinger = Pinger(delay=0.05)
    state = HealthState()
    service = build_service(pinger=pinger, state=state)

    results = await asyncio.gather(*(service.readiness() for _ in range(20)))

    assert {result.ok for result in results} == {True}
    assert pinger.calls == 1
    assert state.readiness_task is None
    await service.readiness()
    assert pinger.calls == 2


async def test_readiness_logs_only_when_its_result_changes(caplog):
    pinger = Pinger(DatabaseUnavailableError("connection_error"))
    service = build_service(pinger=pinger)

    with caplog.at_level(logging.WARNING):
        await service.readiness()
        await service.readiness()
        pinger.error = None
        await service.readiness()

    assert [r.getMessage() for r in caplog.records] == [
        "Database readiness changed to error (connection_error)",
        "Database readiness changed to ok (none)",
    ]


def test_info_is_the_build_of_this_process():
    assert build_service().info() == BUILD


# --- (m) the logs only tell the changes ---


async def test_a_component_that_goes_down_is_logged_once_without_its_address(caplog):
    answers = service_answers(base("caido"), live=failed_answer("dns_error"))
    service = build_service(probe=FakeProbe(answers), reader=Reader([make_component("caido")]))

    with caplog.at_level(logging.WARNING):
        await service.health()
        await service.health()

    changes = [r.getMessage() for r in caplog.records if "caido" in r.getMessage()]
    assert changes == ["Health of component caido changed to down (dns_error)"]
    assert "components.test" not in caplog.text


async def test_components_that_are_up_from_the_start_are_not_logged(caplog):
    service = build_service(probe=FakeProbe(service_answers(base("sano"))), reader=Reader([make_component("sano")]))

    with caplog.at_level(logging.WARNING):
        await service.health()

    assert caplog.records == []


# --- (n) the schedule of the database (user story 4) ---

SCHEDULED = dataclasses.replace(CONFIG, schedule=RUNBOOK_SCHEDULE)
TUESDAY_AT_NIGHT = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)  # Tuesday 27 October, 21:00 in Mexico City
TUESDAY_MORNING = TEST_NOW  # Tuesday 27 October, 10:00 in Mexico City
SUNDAY_NOON = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)
WEDNESDAY_OPENING = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)  # Wednesday 08:00 in Mexico City


def failing_database() -> Pinger:
    return Pinger(DatabaseUnavailableError("connection_error"))


async def test_outside_its_window_a_failing_database_is_stopped_with_its_next_start():
    service = build_service(pinger=failing_database(), config=SCHEDULED, clock=FakeClock(TUESDAY_AT_NIGHT))

    result = await service.health()

    own, database = result.components[:2]
    assert (database.status, database.error, database.next_start_at) == (
        "stopped",
        "connection_error",
        WEDNESDAY_OPENING,
    )
    assert (own.status, own.error, own.next_start_at) == ("degraded", "not_ready", None)
    assert result.status == "degraded"  # nothing else is down


async def test_inside_its_window_a_failing_database_is_down_without_a_next_start():
    service = build_service(pinger=failing_database(), config=SCHEDULED, clock=FakeClock(TUESDAY_MORNING))

    result = await service.health()

    database = result.components[1]
    assert (database.status, database.error, database.next_start_at) == ("down", "connection_error", None)
    assert result.status == "down"


async def test_a_database_that_answers_outside_its_window_is_up():
    result = await build_service(config=SCHEDULED, clock=FakeClock(SUNDAY_NOON)).health()

    database = result.components[1]
    assert (database.status, database.error, database.next_start_at) == ("up", None, None)
    assert result.status == "ok"


@pytest.mark.parametrize("moment", [TUESDAY_AT_NIGHT, TUESDAY_MORNING, SUNDAY_NOON])
async def test_without_a_schedule_a_failing_database_is_down_at_any_time(moment):
    result = await build_service(pinger=failing_database(), clock=FakeClock(moment)).health()

    database = result.components[1]
    assert (database.status, database.next_start_at) == ("down", None)


async def test_only_the_database_carries_a_next_start():
    service = build_service(
        probe=FakeProbe(service_answers(base("usuarios"))),
        reader=Reader([make_component("usuarios")]),
        pinger=failing_database(),
        config=SCHEDULED,
        clock=FakeClock(TUESDAY_AT_NIGHT),
    )

    result = await service.health()

    assert [c.code for c in result.components if c.next_start_at is not None] == ["database"]
    assert by_code(result)["usuarios"].status == "up"


async def test_a_cached_result_keeps_its_next_start():
    clock = FakeClock(TUESDAY_AT_NIGHT)
    pinger = failing_database()
    service = build_service(pinger=pinger, config=dataclasses.replace(SCHEDULED, cache_seconds=15), clock=clock)

    first = await service.health()
    clock.advance(10)
    second = await service.health()

    assert second is first
    assert second.components[1].next_start_at == WEDNESDAY_OPENING
    assert pinger.calls == 1


async def test_the_schedule_does_not_change_the_readiness():
    service = build_service(pinger=failing_database(), config=SCHEDULED, clock=FakeClock(TUESDAY_AT_NIGHT))

    readiness = await service.readiness()

    assert (readiness.ok, readiness.check.error) == (False, "connection_error")


# --- (o) the public status (user story 6): at most one round every 15 seconds ---
# CONFIG has `cache_seconds=0`: the minimum period of the public status still applies (FR-048).


async def test_within_fifteen_seconds_the_public_status_reuses_one_round_and_at_fifteen_runs_another():
    clock = FakeClock()
    pinger = Pinger()
    service = build_service(pinger=pinger, clock=clock)

    first = await service.public_status()
    for _ in range(99):
        clock.advance(0.125)  # 99 more queries in 12.375 s
        assert await service.public_status() is first
    clock.advance(15 - 99 * 0.125)  # exactly 15 s after the first round
    later = await service.public_status()

    assert pinger.calls == 2
    assert later is not first
    assert later.checked_at > first.checked_at


async def test_the_public_status_reuses_the_result_of_the_health_query():
    pinger = Pinger()
    service = build_service(pinger=pinger)

    private = await service.health()

    assert await service.public_status() is private
    assert pinger.calls == 1


async def test_only_the_health_query_brings_the_next_round_forward():
    clock = FakeClock()
    pinger = Pinger()
    service = build_service(pinger=pinger, clock=clock)

    await service.public_status()  # first round
    clock.advance(5)
    newer = await service.health()  # with cache 0 the health query runs another round
    clock.advance(14)  # 19 s after the first round, 14 s after the second

    assert await service.public_status() is newer
    assert pinger.calls == 2


async def test_after_an_invalidation_the_public_status_runs_a_new_round():
    state = HealthState()
    pinger = Pinger()
    service = build_service(pinger=pinger, state=state)

    first = await service.public_status()
    state.invalidate()

    assert await service.public_status() is not first
    assert pinger.calls == 2


async def test_the_public_status_joins_an_older_aggregation_whose_result_is_not_kept():
    state = HealthState()
    pinger = Pinger(delay=0.05)
    service = build_service(pinger=pinger, state=state)

    running = asyncio.create_task(service.public_status())
    await wait_until(lambda: state.in_flight is not None)
    state.invalidate()  # the registry changes while the aggregation runs
    joined = await service.public_status()

    assert joined is await running
    assert pinger.calls == 1
    assert state.last is None  # a result of an older generation is not kept


async def test_a_thousand_public_queries_in_a_minute_make_at_most_four_rounds():
    clock = FakeClock()
    pinger = Pinger()
    service = build_service(pinger=pinger, clock=clock)

    for _ in range(1000):
        await service.public_status()
        clock.advance(0.06)  # 1 000 queries in 60 s

    assert pinger.calls == 4  # SC-016: one round every 15 s


async def test_the_public_status_answers_in_time_with_the_database_and_the_registry_hanging():
    async def hanging_registry():
        await asyncio.sleep(30)

    service = build_service(pinger=Pinger(delay=30), reader=hanging_registry)
    loop = asyncio.get_running_loop()
    started = loop.time()

    result = await service.public_status()

    assert loop.time() - started < 2 * CONFIG.check_timeout_seconds + 0.5  # SC-015
    assert (result.components[1].status, result.components[1].error) == ("down", "timeout")
    assert result.registry_available is False


# --- (p) the copy of the registry (user story 5) ---
# A registry that was never read shows only the integrated components: see (h).


def registered(*codes: str) -> tuple[Reader, FakeProbe]:
    """A registry with healthy services and the probe that answers for them."""
    answers = {}
    for code in codes:
        answers.update(service_answers(base(code)))
    return Reader([make_component(code) for code in codes]), FakeProbe(answers)


async def test_when_the_registry_cannot_be_read_its_last_copy_is_checked_for_real():
    reader, probe = registered("usuarios")
    service = build_service(probe=probe, reader=reader)
    await service.health()  # a good read
    reader.error = DatabaseUnavailableError("connection_error")

    result = await service.health()

    assert result.registry_available is False
    assert (by_code(result)["usuarios"].status, by_code(result)["database"].status) == ("up", "up")
    assert len(probe.calls) == 6  # three calls in each aggregation: the copy is checked again


async def test_an_empty_read_is_available_and_empties_the_copy():
    state = HealthState()
    reader, probe = registered("usuarios")
    service = build_service(probe=probe, reader=reader, state=state)
    await service.health()
    reader.components = []

    result = await service.health()

    assert (result.registry_available, state.registry_snapshot) == (True, ())
    reader.error = RuntimeError("caida")
    assert [c.code for c in (await service.health()).components] == ["maily-system-api", "database"]


async def test_when_the_registry_comes_back_the_copy_follows_its_changes():
    state = HealthState()
    reader, probe = registered("usuarios", "pacientes")
    reader.components = [make_component("usuarios")]
    service = build_service(probe=probe, reader=reader, state=state)
    await service.health()
    reader.error = RuntimeError("caida")
    await service.health()
    reader.error = None
    reader.components = [make_component("pacientes")]

    result = await service.health()

    assert result.registry_available is True
    assert [c.code for c in result.components] == ["maily-system-api", "database", "pacientes"]
    assert [target.code for target in state.registry_snapshot] == ["pacientes"]


async def test_a_read_that_never_ends_uses_the_copy_within_the_time_limit():
    reader, probe = registered("usuarios")
    service = build_service(probe=probe, reader=reader)
    await service.health()
    reader.delay = 30
    loop = asyncio.get_running_loop()
    started = loop.time()

    result = await service.health()

    assert loop.time() - started < 2 * CONFIG.check_timeout_seconds + 0.5
    assert (result.registry_available, by_code(result)["usuarios"].status) == (False, "up")


async def test_the_copy_holds_its_own_records_and_a_failed_read_is_logged_without_details(caplog):
    state = HealthState()
    reader, probe = registered("usuarios")
    service = build_service(probe=probe, reader=reader, state=state)
    await service.health()

    assert isinstance(state.registry_snapshot, tuple)
    assert all(isinstance(target, ComponentTarget) for target in state.registry_snapshot)

    reader.error = RuntimeError("SECRETO-INTERNO")
    with caplog.at_level(logging.WARNING):
        await service.health()

    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [
        "Registry of monitored components unavailable (RuntimeError)"
    ]
    assert "SECRETO-INTERNO" not in caplog.text

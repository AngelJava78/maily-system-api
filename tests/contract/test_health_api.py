"""`GET /api/v1/health` over HTTP (spec 005, user story 1; FR-010 to FR-019, SC-001, SC-005).

The real application with the real PostgreSQL (the registry and the trivial query), the simulated
users API and the simulated components (`tests/stubs/components`), with the configuration of
`TEST_HEALTH_CONFIG` (0.5 s per call).
"""

import asyncio
from datetime import UTC, datetime

from src.config import AllowedHosts
from src.dependencies import get_database_pinger, get_registry_reader
from src.repositories.errors import DatabaseUnavailableError
from tests.health_support import RUNBOOK_SCHEDULE, HealthApi, stub_url
from tests.helpers import TEST_TOKEN

FIELDS = {
    "code",
    "name",
    "kind",
    "status",
    "latency_ms",
    "checked_at",
    "version",
    "commit",
    "build_date",
    "environment",
    "checks",
    "error",
    "next_start_at",
}


def by_code(body: dict) -> dict[str, dict]:
    return {component["code"]: component for component in body["components"]}


async def test_the_health_of_the_platform_comes_in_one_answer_that_is_always_200(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"), sort_order=10)
    await health_api.insert_component(code="lento", base_url=stub_url("slow"), sort_order=20)

    response = await health_api.health()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["status"], body["registry_available"]) == ("down", True)
    assert body["checked_at"].endswith("Z")
    assert [c["code"] for c in body["components"]] == ["maily-system-api", "database", "sano", "lento"]
    for component in body["components"]:
        assert set(component) == FIELDS, component["code"]
    components = by_code(body)
    assert (components["sano"]["status"], components["sano"]["version"]) == ("up", "1.4.2")
    assert (components["lento"]["status"], components["lento"]["error"]) == ("down", "timeout")
    assert components["database"]["status"] == "up"


async def test_no_address_raw_body_or_token_reaches_the_answer(health_api: HealthApi):
    for prefix in ("healthy", "html", "error", "info-incomplete", "many-checks"):
        await health_api.insert_component(code=f"c-{prefix}", base_url=stub_url(prefix))

    text = (await health_api.health()).text

    for forbidden in ("components.test", "http://", "SECRETO-INTERNO", TEST_TOKEN, "<html"):
        assert forbidden not in text, forbidden


async def test_the_calls_to_the_components_never_carry_the_token(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))

    await health_api.health()

    calls = await health_api.component_calls()
    assert len(calls) == 3
    assert not any(call["has_authorization"] or call["has_cookie"] for call in calls)


async def test_disabled_and_deleted_components_are_neither_shown_nor_called(health_api: HealthApi):
    await health_api.insert_component(code="apagado", base_url=stub_url("healthy"), enabled=False)
    await health_api.insert_component(code="borrado", base_url=stub_url("healthy"), deleted_at=datetime.now(UTC))

    body = (await health_api.health()).json()

    assert [c["code"] for c in body["components"]] == ["maily-system-api", "database"]
    assert await health_api.component_calls() == []


async def test_an_empty_registry_shows_the_two_integrated_components_and_is_available(health_api: HealthApi):
    body = (await health_api.health()).json()

    assert [c["code"] for c in body["components"]] == ["maily-system-api", "database"]
    assert (body["registry_available"], body["status"]) == (True, "ok")


async def test_unknown_query_parameters_are_ignored(health_api: HealthApi):
    response = await health_api.get("/api/v1/health?refresh=true&x=1")

    assert response.status_code == 200


async def test_with_twenty_components_and_some_slow_the_answer_stays_within_the_limit(health_api: HealthApi):
    for n in range(20):
        prefix = "slow" if n % 4 == 0 else "healthy"
        await health_api.insert_component(code=f"c{n:02d}", base_url=stub_url(prefix), sort_order=n)
    loop = asyncio.get_running_loop()
    started = loop.time()

    response = await health_api.health()

    assert loop.time() - started < health_api.holder.config.check_timeout_seconds + 1  # SC-001
    assert len(response.json()["components"]) == 22


async def test_a_frontend_counts_its_status_and_a_service_needs_its_json(health_api: HealthApi):
    await health_api.insert_component(code="mailysoft", kind="frontend", base_url=stub_url("spa"), live_path="/healthz/")
    await health_api.insert_component(code="html-como-servicio", base_url=stub_url("html"))

    components = by_code((await health_api.health()).json())

    assert (components["mailysoft"]["status"], components["mailysoft"]["kind"]) == ("up", "frontend")
    assert (components["html-como-servicio"]["status"], components["html-como-servicio"]["error"]) == (
        "down",
        "invalid_response",
    )


async def test_a_host_that_left_the_list_is_unknown_and_never_called(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))
    health_api.set_config(allowed_hosts=AllowedHosts.parse("otro-host"))

    component = by_code((await health_api.health()).json())["sano"]

    assert (component["status"], component["error"], component["latency_ms"]) == ("unknown", "host_not_allowed", None)
    assert await health_api.component_calls() == []


# --- the schedule of the database (user story 4) ---


def make_the_database_fail(health_api: HealthApi) -> None:
    async def ping() -> None:
        raise DatabaseUnavailableError("connection_error")

    health_api.use_value(get_database_pinger, ping)


async def test_at_night_a_failing_database_is_stopped_until_its_next_start(health_api: HealthApi):
    health_api.set_config(schedule=RUNBOOK_SCHEDULE)
    health_api.clock.set(datetime(2026, 10, 24, 3, 0, tzinfo=UTC))  # Friday 23 October, 21:00 in Mexico City
    make_the_database_fail(health_api)

    body = (await health_api.health()).json()

    database = by_code(body)["database"]
    assert (database["status"], database["error"]) == ("stopped", "connection_error")
    assert database["next_start_at"] == "2026-10-26T14:00:00Z"  # Monday 08:00
    assert by_code(body)["maily-system-api"]["status"] == "degraded"
    assert body["status"] == "degraded"


async def test_during_its_hours_a_failing_database_is_down(health_api: HealthApi):
    health_api.set_config(schedule=RUNBOOK_SCHEDULE)  # the clock is on Tuesday at 10:00
    make_the_database_fail(health_api)

    body = (await health_api.health()).json()

    database = by_code(body)["database"]
    assert (database["status"], database["next_start_at"]) == ("down", None)
    assert body["status"] == "down"


# --- the copy of the registry (user story 5) ---


def make_the_registry_fail(health_api: HealthApi) -> None:
    async def read():
        raise DatabaseUnavailableError("connection_error")

    health_api.use_value(get_registry_reader, read)


async def test_after_a_good_read_an_unreadable_registry_is_replaced_by_its_copy(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))
    await health_api.health()  # a good read
    make_the_registry_fail(health_api)
    await health_api.reset_components()

    response = await health_api.health()

    body = response.json()
    assert (response.status_code, body["registry_available"]) == (200, False)
    assert [c["code"] for c in body["components"]] == ["maily-system-api", "database", "sano"]
    assert (by_code(body)["sano"]["status"], by_code(body)["database"]["status"]) == ("up", "up")
    assert len(await health_api.component_calls()) == 3  # the copy was checked for real


async def test_with_the_registry_unreadable_from_the_start_only_the_integrated_ones_appear(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))
    make_the_registry_fail(health_api)

    body = (await health_api.health()).json()

    assert [c["code"] for c in body["components"]] == ["maily-system-api", "database"]
    assert body["registry_available"] is False
    assert await health_api.component_calls() == []


async def test_the_public_status_also_uses_the_copy_without_telling_it(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))
    first = (await health_api.health()).json()
    make_the_registry_fail(health_api)
    health_api.clock.advance(15)  # the public status may not reuse the first result any more

    public = (await health_api.status()).json()

    assert public["checked_at"] != first["checked_at"]  # a new aggregation, with the copy
    assert [c["code"] for c in public["components"]] == ["maily-system-api", "database", "sano"]
    assert "registry_available" not in public

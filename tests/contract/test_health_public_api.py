"""The public routes of health (spec 005, user stories 2 and 6; FR-002, FR-004 to FR-008, FR-045 to
FR-050).

`/health/live`, `/health/ready` and `/info` are the health contract v1 of this service, and
`/health/status` the public status of the platform: without a token, in the root, with
`Cache-Control: no-store` and the CORS headers of the API.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from src.config import BuildInfo, get_cors_settings
from src.dependencies import get_build_info, get_database_pinger
from src.repositories.errors import DatabaseUnavailableError
from tests.health_support import (
    RUNBOOK_SCHEDULE,
    TEST_HEALTH_CONFIG,
    HealthApi,
    HealthConfigHolder,
    install_health_overrides,
    stub_url,
)

ALLOWED_ORIGIN = "http://localhost:5173"


def pinger_that(*, raises: BaseException | None = None, delay: float = 0.0):
    """A replacement of the trivial query of the database, with a counter of its calls."""
    calls = {"count": 0}

    async def ping() -> None:
        calls["count"] += 1
        if delay:
            await asyncio.sleep(delay)
        if raises is not None:
            raise raises

    async def provider():
        return ping

    return provider, calls


# --- /health/live ---


async def test_live_answers_ok_without_a_token_quickly_even_if_the_database_hangs(health_api: HealthApi):
    provider, calls = pinger_that(delay=30)
    health_api.use(get_database_pinger, provider)
    loop = asyncio.get_running_loop()
    await health_api.anonymous.get("/health/live")  # the first request builds the middleware stack

    durations = []
    for _ in range(20):
        started = loop.time()
        response = await health_api.anonymous.get("/health/live")
        durations.append(loop.time() - started)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["cache-control"] == "no-store"

    assert sum(duration < 0.1 for duration in durations) >= 19  # SC-007: 95 % under 100 ms
    assert calls["count"] == 0
    assert await health_api.users_calls() == []


# --- /health/ready ---


async def test_ready_checks_the_database_and_answers_200(health_api: HealthApi):
    response = await health_api.anonymous.get("/health/ready")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "ok"
    [check] = body["checks"]
    assert (check["name"], check["status"], check["error"]) == ("database", "ok", None)
    assert isinstance(check["latency_ms"], int)


@pytest.mark.parametrize(
    ("pinger", "error"),
    [
        ({"delay": 30}, "timeout"),
        ({"raises": DatabaseUnavailableError("connection_error")}, "connection_error"),
        ({"raises": RuntimeError("SECRETO-INTERNO host=db password=x")}, "unexpected_error"),
    ],
)
async def test_ready_answers_503_unavailable_when_the_database_fails(health_api: HealthApi, pinger, error):
    provider, _ = pinger_that(**pinger)
    health_api.use(get_database_pinger, provider)
    loop = asyncio.get_running_loop()
    started = loop.time()

    response = await health_api.anonymous.get("/health/ready")

    assert loop.time() - started < health_api.holder.config.ready_timeout_seconds + 1  # SC-007
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "unavailable"
    [check] = body["checks"]
    assert (check["name"], check["status"], check["error"]) == ("database", "error", error)
    assert isinstance(check["latency_ms"], int)
    for forbidden in ("SECRETO-INTERNO", "host=", "password"):
        assert forbidden not in response.text


async def test_ready_does_not_depend_on_the_users_api(health_api: HealthApi):
    await health_api.users_fault("unavailable", count=5)

    response = await health_api.anonymous.get("/health/ready")

    assert response.status_code == 200
    assert await health_api.users_calls() == []


async def test_simultaneous_readiness_checks_share_one_query_and_nothing_is_kept(health_api: HealthApi):
    provider, calls = pinger_that(delay=0.05)
    health_api.use(get_database_pinger, provider)

    responses = await asyncio.gather(*(health_api.anonymous.get("/health/ready") for _ in range(20)))

    assert {response.status_code for response in responses} == {200}
    assert calls["count"] == 1
    await health_api.anonymous.get("/health/ready")
    assert calls["count"] == 2  # not a cache: the next request asks again


# --- /info ---


async def test_info_without_build_variables_gives_unknown(health_api: HealthApi):
    health_api.use_value(get_build_info, BuildInfo("maily-system-api", "2.0.0", "unknown", "unknown", "unknown"))

    response = await health_api.anonymous.get("/info")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "service": "maily-system-api",
        "version": "2.0.0",
        "commit": "unknown",
        "build_date": "unknown",
        "environment": "unknown",
    }


async def test_info_publishes_the_build_that_was_injected(health_api: HealthApi):
    build = BuildInfo("maily-system-api", "2.0.0", "3c81089d", "2026-10-24T16:05:00Z", "staging")
    health_api.use_value(get_build_info, build)

    body = (await health_api.anonymous.get("/info")).json()

    assert (body["commit"], body["build_date"], body["environment"]) == (
        "3c81089d",
        "2026-10-24T16:05:00Z",
        "staging",
    )


@pytest.mark.parametrize("path", ["/health/live", "/info", "/health/status"])
@pytest.mark.parametrize("authorization", ["Bearer test-token", "Bearer no-registrado", "Basic abc"])
async def test_an_authorization_header_changes_nothing(health_api: HealthApi, path, authorization):
    plain = await health_api.anonymous.get(path)

    with_header = await health_api.anonymous.get(path, headers={"Authorization": authorization})

    assert plain.status_code == 200
    assert (with_header.status_code, with_header.json()) == (plain.status_code, plain.json())
    assert await health_api.users_calls() == []


async def test_an_authorization_header_does_not_change_the_readiness(health_api: HealthApi):
    response = await health_api.anonymous.get("/health/ready", headers={"Authorization": "Bearer no-registrado"})

    assert (response.status_code, response.json()["status"]) == (200, "ok")
    assert await health_api.users_calls() == []


# --- the integrated component has the build of /info and is never called over HTTP ---


async def test_the_aggregated_health_shows_this_service_with_the_build_of_info(health_api: HealthApi):
    build = BuildInfo("maily-system-api", "2.0.0", "3c81089d", "2026-10-24T16:05:00Z", "staging")
    health_api.use_value(get_build_info, build)

    info = (await health_api.anonymous.get("/info")).json()
    own = (await health_api.health()).json()["components"][0]

    assert own["code"] == "maily-system-api"
    assert (own["version"], own["commit"], own["build_date"], own["environment"]) == (
        info["version"],
        info["commit"],
        info["build_date"],
        info["environment"],
    )
    assert own["status"] == "up"
    assert await health_api.component_calls() == []


# --- /health/status: the public status of the platform (user story 6) ---


def codes_and_statuses(body: dict) -> list[tuple[str, str]]:
    return [(component["code"], component["status"]) for component in body["components"]]


async def test_the_public_status_needs_no_token_and_does_not_ask_the_users_api(health_api: HealthApi):
    await health_api.users_fault("unavailable")

    response = await health_api.status()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert await health_api.users_calls() == []
    # The failure of the users API is still waiting: the public status never consumed it.
    assert (await health_api.health()).status_code == 503


async def test_at_night_the_public_status_shows_the_database_stopped_until_its_next_start(health_api: HealthApi):
    provider, _ = pinger_that(raises=DatabaseUnavailableError("connection_error"))
    health_api.use(get_database_pinger, provider)
    health_api.set_config(schedule=RUNBOOK_SCHEDULE)
    health_api.clock.set(datetime(2026, 10, 24, 3, 15, tzinfo=UTC))  # Friday 23 October, 21:15 in Mexico City

    body = (await health_api.status()).json()

    assert body["status"] == "degraded"
    assert body["components"][:2] == [
        {
            "code": "maily-system-api",
            "name": "MailySoft System API",
            "kind": "service",
            "status": "degraded",
            "next_start_at": None,
        },
        {
            "code": "database",
            "name": "Base de datos",
            "kind": "database",
            "status": "stopped",
            "next_start_at": "2026-10-26T14:00:00Z",
        },
    ]


async def test_without_a_schedule_a_failing_database_is_down_in_the_public_status(health_api: HealthApi):
    provider, _ = pinger_that(raises=DatabaseUnavailableError("connection_error"))
    health_api.use(get_database_pinger, provider)

    database = (await health_api.status()).json()["components"][1]

    assert (database["status"], database["next_start_at"]) == ("down", None)


async def test_the_public_status_is_the_same_result_as_the_health_query(health_api: HealthApi):
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"), sort_order=10)
    await health_api.insert_component(code="con-error", base_url=stub_url("error"), sort_order=20)
    await health_api.insert_component(code="apagado", base_url=stub_url("healthy"), enabled=False)
    await health_api.insert_component(code="borrado", base_url=stub_url("healthy"), deleted_at=datetime.now(UTC))

    private = (await health_api.health()).json()
    public = (await health_api.status()).json()

    assert codes_and_statuses(public) == codes_and_statuses(private)
    assert [code for code, _ in codes_and_statuses(public)] == ["maily-system-api", "database", "sano", "con-error"]
    assert (public["status"], public["checked_at"]) == (private["status"], private["checked_at"])


async def test_unknown_query_parameters_of_the_public_status_are_ignored(health_api: HealthApi):
    response = await health_api.anonymous.get("/health/status?refresh=true")

    assert response.status_code == 200


# --- CORS (FR-050) ---


@pytest.fixture
async def cors_client(monkeypatch, components_stub_app):
    """An application with `CORS_ALLOWED_ORIGINS` (read when the application is built)."""
    from src.main import create_app

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    get_cors_settings.cache_clear()
    app = create_app()
    probe_client = install_health_overrides(app, components_stub_app, HealthConfigHolder(TEST_HEALTH_CONFIG))
    failing, _ = pinger_that(raises=DatabaseUnavailableError("connection_error"))
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api.test") as client,
        probe_client,
    ):
        yield app, client, failing
    get_cors_settings.cache_clear()


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/status"])
async def test_an_allowed_site_receives_the_cors_headers_without_credentials(cors_client, path):
    _, client, _ = cors_client

    response = await client.get(path, headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


async def test_the_503_of_readiness_also_carries_the_cors_headers(cors_client):
    app, client, failing = cors_client
    app.dependency_overrides[get_database_pinger] = failing

    response = await client.get("/health/ready", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/status"])
async def test_a_site_that_is_not_listed_receives_no_cors_headers(cors_client, path):
    _, client, _ = cors_client

    response = await client.get(path, headers={"Origin": "http://otro.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

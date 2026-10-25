"""Access control of `GET /api/v1/health` (spec 005, FR-003, FR-020, SC-006; Principle VIII).

The permission `health:read` is asked to the users API on every request, before any check is made or
any result is served; the cache keeps results, never decisions.
"""

import asyncio

import pytest

from tests.health_support import HealthApi, stub_url
from tests.helpers import TEST_TOKEN


async def assert_refused_without_checks(health_api: HealthApi, response, status: int, code: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert "components" not in body
    assert await health_api.component_calls() == []


@pytest.fixture
async def registered(health_api: HealthApi) -> HealthApi:
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"))
    return health_api


async def test_without_a_token_the_query_asks_to_log_in(registered: HealthApi):
    response = await registered.anonymous.get("/api/v1/health")

    await assert_refused_without_checks(registered, response, 401, "unauthenticated")
    assert response.headers["www-authenticate"] == "Bearer"
    assert await registered.users_calls() == []


async def test_an_invalid_token_is_rejected(registered: HealthApi):
    response = await registered.anonymous.get("/api/v1/health", headers={"Authorization": "Bearer no-registrado"})

    await assert_refused_without_checks(registered, response, 401, "invalid_token")


async def test_an_expired_token_is_rejected(registered: HealthApi):
    await registered.grant(["health:read"], expired=True)

    response = await registered.health()

    await assert_refused_without_checks(registered, response, 401, "token_expired")


@pytest.mark.parametrize(
    "permissions", [["dashboard:read"], ["health:write", "health:update", "health:delete"], []]
)
async def test_without_health_read_the_query_is_forbidden(registered: HealthApi, permissions):
    await registered.grant(permissions)

    response = await registered.health()

    await assert_refused_without_checks(registered, response, 403, "permission_denied")
    assert "health:read" in response.json()["message"]


async def test_with_the_users_api_down_the_query_is_refused(registered: HealthApi):
    await registered.users_fault("unavailable")

    response = await registered.health()

    await assert_refused_without_checks(registered, response, 503, "authorization_unavailable")


async def test_the_question_is_exactly_health_read_with_the_token_as_it_came(registered: HealthApi):
    response = await registered.health()

    assert response.status_code == 200
    calls = await registered.users_calls()
    assert [(c["permission"], c["authorization"]) for c in calls] == [("health:read", f"Bearer {TEST_TOKEN}")]


async def test_fifty_simultaneous_queries_ask_fifty_permissions_and_check_once(registered: HealthApi):
    registered.set_config(cache_seconds=15)

    responses = await asyncio.gather(*(registered.health() for _ in range(50)))

    assert {response.status_code for response in responses} == {200}
    assert len(await registered.users_calls()) == 50
    assert len(await registered.component_calls()) == 3  # one round: live, ready and info


async def test_a_cached_result_is_never_served_without_the_permission(registered: HealthApi):
    registered.set_config(cache_seconds=15)
    assert (await registered.health()).status_code == 200

    await registered.grant(["dashboard:read"])  # the role changed
    response = await registered.health()

    assert response.status_code == 403
    assert "components" not in response.json()

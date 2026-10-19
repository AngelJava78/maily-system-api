"""Only who has `dashboard:read` can read the dashboard (user story 2, spec 003).

The machinery (`require_permission`, `AuthorizationService`, `UsersApiClient`) is the one of spec 001;
what is fixed here is how the dashboard operation uses it: the permission is the exact one, it is
asked on every request, it fails closed, and it is checked BEFORE `limit`. The data source is a fake
so the tests can prove that nothing is asked of it when the access is denied.
"""

import logging

import httpx
import pytest

from tests.dashboard_support import DASHBOARD_URL, FakeDashboardSource, make_clinic
from tests.helpers import TEST_TOKEN

PERMISSION = "dashboard:read"
SUBSCRIPTIONS_PERMISSIONS = [
    "subscriptions:read",
    "subscriptions:write",
    "subscriptions:update",
    "subscriptions:delete",
]
DASHBOARD_KEYS = {
    "total_clinics",
    "active_clinics",
    "trial_clinics",
    "total_doctors",
    "total_patients",
    "total_users",
    "recent_clinics",
}
LEAK_MARKER = "SECRETO-INTERNO"


@pytest.fixture
def source(dashboard_api) -> FakeDashboardSource:
    fake = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 4)], doctors=1, users=2)
    dashboard_api.use_source(fake)
    return fake


def assert_error(response: httpx.Response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code
    assert not DASHBOARD_KEYS & set(body), "an error must not carry data of the dashboard"
    return body


# --- identity ---


async def test_without_a_token_it_asks_to_log_in_and_returns_nothing(dashboard_api, source):
    response = await dashboard_api.anonymous.get(DASHBOARD_URL)

    body = assert_error(response, 401, "unauthenticated")
    assert body == {
        "code": "unauthenticated",
        "message": "Debe iniciar sesión para usar esta operación.",
    }
    assert response.headers["www-authenticate"] == "Bearer"
    assert source.calls == []


async def test_another_authentication_scheme_is_the_same_as_no_token(dashboard_api, source):
    response = await dashboard_api.anonymous.get(
        DASHBOARD_URL, headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )

    assert_error(response, 401, "unauthenticated")
    assert source.calls == []


async def test_a_token_the_users_api_does_not_know_is_invalid(dashboard_api, source):
    response = await dashboard_api.anonymous.get(
        DASHBOARD_URL, headers={"Authorization": "Bearer not-a-registered-token"}
    )

    assert_error(response, 401, "invalid_token")
    assert source.calls == []


async def test_an_expired_token_asks_to_log_in_again(dashboard_api, source):
    await dashboard_api.grant_token("old-token", [PERMISSION], expired=True)

    response = await dashboard_api.anonymous.get(
        DASHBOARD_URL, headers={"Authorization": "Bearer old-token"}
    )

    body = assert_error(response, 401, "token_expired")
    assert body["message"] == "Su sesión venció. Inicie sesión de nuevo."
    assert source.calls == []


# --- permission ---


async def test_with_the_permission_the_dashboard_is_returned(dashboard_api, source):
    response = await dashboard_api.get()

    assert response.status_code == 200
    assert set(response.json()) == DASHBOARD_KEYS
    assert len(source.calls) == 5  # the five queries of the data source


async def test_a_person_without_the_permission_is_forbidden_and_gets_nothing(dashboard_api, source):
    await dashboard_api.set_permissions([])

    response = await dashboard_api.get()

    body = assert_error(response, 403, "permission_denied")
    assert body["message"] == (
        "No tiene permiso para realizar esta operación. Permiso requerido: dashboard:read."
    )
    assert source.calls == []


async def test_the_permissions_of_the_subscriptions_do_not_open_the_dashboard(dashboard_api, source):
    await dashboard_api.set_permissions(SUBSCRIPTIONS_PERMISSIONS)

    response = await dashboard_api.get()

    assert_error(response, 403, "permission_denied")
    assert source.calls == []


async def test_a_revoked_permission_takes_effect_on_the_very_next_request(dashboard_api, source):
    assert (await dashboard_api.get()).status_code == 200

    await dashboard_api.set_permissions([])

    assert_error(await dashboard_api.get(), 403, "permission_denied")


# --- fail closed ---


@pytest.mark.parametrize(
    "mode",
    ["unavailable", "rate_limited", "malformed", "not_json", "redirect", "forbidden", "wrong_permission"],
)
async def test_when_the_users_api_cannot_answer_the_request_is_refused(dashboard_api, source, mode):
    await dashboard_api.users_fault(mode)

    response = await dashboard_api.get()

    body = assert_error(response, 503, "authorization_unavailable")
    assert body["message"] == "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde."
    assert LEAK_MARKER not in response.text
    assert source.calls == []


# --- the access is decided BEFORE `limit` is looked at ---


async def prepare(api, scenario: str) -> tuple[httpx.AsyncClient, dict[str, str], int, str]:
    """A request that must be refused for `scenario`: client, headers, status and error code."""
    if scenario == "no_token":
        return api.anonymous, {}, 401, "unauthenticated"
    if scenario == "invalid_token":
        return api.anonymous, {"Authorization": "Bearer nope"}, 401, "invalid_token"
    if scenario == "expired_token":
        await api.grant_token("old-token", [PERMISSION], expired=True)
        return api.anonymous, {"Authorization": "Bearer old-token"}, 401, "token_expired"
    if scenario == "no_permission":
        await api.set_permissions([])
        return api.client, {}, 403, "permission_denied"
    assert scenario == "users_api_down"
    await api.users_fault("unavailable")
    return api.client, {}, 503, "authorization_unavailable"


@pytest.mark.parametrize("query", ["?limit=abc", "?limit=0", "?limit=", "?limit=3&limit=5"])
@pytest.mark.parametrize(
    "scenario", ["no_token", "invalid_token", "expired_token", "no_permission", "users_api_down"]
)
async def test_the_access_error_wins_over_an_invalid_limit(dashboard_api, source, scenario, query):
    client, headers, status, code = await prepare(dashboard_api, scenario)

    response = await client.get(DASHBOARD_URL + query, headers=headers)

    assert_error(response, status, code)
    assert source.calls == []


async def test_with_the_permission_an_invalid_limit_is_not_an_access_error(dashboard_api, source):
    response = await dashboard_api.get("?limit=abc")

    assert response.status_code not in (401, 403, 503)


# --- one decision per request, with the token forwarded as it came ---


async def test_each_request_asks_the_users_api_once_for_exactly_its_permission(dashboard_api, source):
    await dashboard_api.get()
    calls = await dashboard_api.users_calls()

    assert [(c["permission"], c["authorization"]) for c in calls] == [
        (PERMISSION, f"Bearer {TEST_TOKEN}")
    ]


async def test_decisions_are_not_cached(dashboard_api, source):
    await dashboard_api.get()
    await dashboard_api.get()

    assert len(await dashboard_api.users_calls()) == 2


async def test_the_token_never_appears_in_a_response_or_in_the_logs(dashboard_api, source, caplog):
    caplog.set_level(logging.DEBUG)

    ok = await dashboard_api.get()
    await dashboard_api.set_permissions([])
    denied = await dashboard_api.get()

    assert TEST_TOKEN not in ok.text
    assert TEST_TOKEN not in denied.text
    assert TEST_TOKEN not in caplog.text


# --- the published documentation needs no token and names the permission ---


async def test_the_documentation_is_public_and_declares_the_permission(dashboard_api):
    schema = await dashboard_api.anonymous.get("/openapi.json")
    docs = await dashboard_api.anonymous.get("/docs")

    assert schema.status_code == 200
    assert docs.status_code == 200
    operation = schema.json()["paths"][DASHBOARD_URL]["get"]
    assert operation["x-required-permission"] == PERMISSION
    assert operation["security"] == [{"BearerAuth": []}]

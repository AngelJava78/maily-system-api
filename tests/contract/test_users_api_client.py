"""UsersApiClient against the simulation of the users API (contracts/users-api-integration.md).

One case per row of the table «Traducción de las respuestas»: the real client code runs, only the
network is replaced by an in-memory transport.
"""

import logging
import time

import httpx
import pytest

from src.integrations.errors import UsersApiRejectedToken, UsersApiUnavailable
from src.integrations.users_api import UsersApiClient
from tests.helpers import USERS_BASE_URL, grant

TOKEN = "SECRET-TOKEN-123"
PERMISSION = "subscriptions:read"


async def add_fault(stub: httpx.AsyncClient, mode: str, count: int = 1, delay: float = 30) -> None:
    response = await stub.post(
        "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay}
    )
    assert response.status_code == 200


async def calls(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/calls")).json()


async def test_a_person_with_the_permission_is_allowed(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION])

    assert await users_api_client.check_permission(TOKEN, PERMISSION) is True


async def test_a_person_without_the_permission_is_not_allowed(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION])

    assert await users_api_client.check_permission(TOKEN, "subscriptions:write") is False


@pytest.mark.parametrize(
    ("token", "expired", "code"),
    [
        ("unknown-token", False, "invalid_token"),
        (TOKEN, True, "token_expired"),
        ("", False, "unauthenticated"),
    ],
)
async def test_a_401_becomes_a_rejection_with_the_code_of_the_users_api(
    users_stub, users_api_client, token, expired, code
):
    await grant(users_stub, TOKEN, [PERMISSION], expired=expired)

    with pytest.raises(UsersApiRejectedToken) as error:
        await users_api_client.check_permission(token, PERMISSION)

    assert error.value.code == code


@pytest.mark.parametrize("mode", ["unauthorized_unreadable", "unauthorized_unknown"])
async def test_an_unreadable_or_unknown_401_is_an_invalid_token(users_stub, users_api_client, mode):
    await add_fault(users_stub, mode)

    with pytest.raises(UsersApiRejectedToken) as error:
        await users_api_client.check_permission(TOKEN, PERMISSION)

    assert error.value.code == "invalid_token"


@pytest.mark.parametrize(
    "mode",
    [
        "malformed",
        "wrong_permission",
        "not_json",
        "redirect",
        "unavailable",
        "rate_limited",
        "forbidden",
        "not_found",
        "unprocessable",
    ],
)
async def test_everything_else_is_unavailable_never_a_decision(users_stub, users_api_client, mode):
    await grant(users_stub, TOKEN, [PERMISSION])
    await add_fault(users_stub, mode)

    with pytest.raises(UsersApiUnavailable):
        await users_api_client.check_permission(TOKEN, PERMISSION)


async def test_a_redirection_is_not_followed(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION])
    await add_fault(users_stub, "redirect")

    with pytest.raises(UsersApiUnavailable):
        await users_api_client.check_permission(TOKEN, PERMISSION)

    recorded = await calls(users_stub)
    assert len(recorded) == 1
    assert all(call["path"] != "/steal" for call in recorded)


async def test_a_refused_connection_is_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(UsersApiUnavailable):
            await UsersApiClient(client, USERS_BASE_URL, 5.0).check_permission(TOKEN, PERMISSION)


async def test_the_time_limit_covers_the_whole_call(users_stub):
    await grant(users_stub, TOKEN, [PERMISSION])
    await add_fault(users_stub, "slow", delay=1)
    client = UsersApiClient(users_stub, USERS_BASE_URL, 0.2)

    started = time.perf_counter()
    with pytest.raises(UsersApiUnavailable):
        await client.check_permission(TOKEN, PERMISSION)

    assert time.perf_counter() - started < 1


async def test_one_call_with_the_exact_permission_and_the_token_untouched(
    users_stub, users_api_client
):
    await grant(users_stub, TOKEN, [PERMISSION])

    await users_api_client.check_permission(TOKEN, PERMISSION)

    recorded = await calls(users_stub)
    assert len(recorded) == 1
    assert recorded[0]["path"] == "/api/v1/authorization/check"
    assert recorded[0]["permission"] == PERMISSION
    assert recorded[0]["authorization"] == f"Bearer {TOKEN}"


async def test_no_header_of_the_original_request_is_forwarded(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION])

    await users_api_client.check_permission(TOKEN, PERMISSION)

    names = set((await calls(users_stub))[0]["header_names"])
    transport_defaults = {"host", "accept-encoding", "connection", "user-agent"}
    assert names - transport_defaults == {"authorization", "accept"}


async def test_the_token_never_appears_in_an_exception_or_in_the_logs(
    users_stub, users_api_client, caplog
):
    caplog.set_level(logging.DEBUG)
    messages = []
    for mode in ("unavailable", "not_json", "forbidden", "redirect"):
        await add_fault(users_stub, mode)
        with pytest.raises(UsersApiUnavailable) as error:
            await users_api_client.check_permission(TOKEN, PERMISSION)
        messages.append(str(error.value))
    with pytest.raises(UsersApiRejectedToken) as rejected:
        await users_api_client.check_permission("another-secret-token", PERMISSION)
    messages.append(str(rejected.value))

    assert all(TOKEN not in message for message in messages)
    assert "another-secret-token" not in str(rejected.value)
    assert TOKEN not in caplog.text
    assert "another-secret-token" not in caplog.text

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


async def add_fault(
    stub: httpx.AsyncClient,
    mode: str,
    count: int = 1,
    delay: float = 30,
    operation: str = "check",
) -> None:
    response = await stub.post(
        "/__test__/faults",
        json={"mode": mode, "count": count, "delay_seconds": delay, "operation": operation},
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


# --- list_clinic_module_keys (contracts/users-api-integration.md, operación 2) ---


async def test_it_returns_exactly_the_nine_clinic_module_keys(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])

    keys = await users_api_client.list_clinic_module_keys(TOKEN)

    assert keys == {
        "patients",
        "scheduling",
        "reminders",
        "clinical_records",
        "clinical_record_templates",
        "prescriptions",
        "finance",
        "reports",
        "billing",
    }


async def test_the_system_type_modules_are_never_included(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])

    keys = await users_api_client.list_clinic_module_keys(TOKEN)

    assert not keys & {"users", "roles", "permissions", "modules"}


async def test_an_unrecognised_token_is_a_rejection(users_stub, users_api_client):
    with pytest.raises(UsersApiRejectedToken):
        await users_api_client.list_clinic_module_keys("unknown-token")


async def test_a_token_without_modules_read_is_unavailable_not_a_silent_empty_catalog(
    users_stub, users_api_client
):
    # Documented risk (contracts/permission-matrix.md): a role with subscriptions:write/update but
    # not modules:read gets a 403 here, which this client reports as "unavailable", never as an
    # empty (and therefore misleadingly "valid") module catalog.
    await grant(users_stub, TOKEN, [PERMISSION])  # no "modules:read"

    with pytest.raises(UsersApiUnavailable):
        await users_api_client.list_clinic_module_keys(TOKEN)


@pytest.mark.parametrize("mode", ["unavailable", "not_json", "malformed", "redirect", "forbidden"])
async def test_a_modules_fault_makes_it_unavailable(users_stub, users_api_client, mode):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])
    await add_fault(users_stub, mode, operation="modules")

    with pytest.raises(UsersApiUnavailable):
        await users_api_client.list_clinic_module_keys(TOKEN)


async def test_a_fault_registered_for_check_does_not_affect_modules(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])
    await add_fault(users_stub, "unavailable", operation="check")

    # No se consume el fallo de "check": list_clinic_module_keys sigue funcionando.
    keys = await users_api_client.list_clinic_module_keys(TOKEN)
    assert "patients" in keys

    # El fallo de "check" sigue pendiente para check_permission.
    with pytest.raises(UsersApiUnavailable):
        await users_api_client.check_permission(TOKEN, PERMISSION)


async def test_a_fault_registered_for_modules_does_not_affect_check(users_stub, users_api_client):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])
    await add_fault(users_stub, "unavailable", operation="modules")

    assert await users_api_client.check_permission(TOKEN, PERMISSION) is True


async def test_list_clinic_module_keys_asks_for_type_clinic_and_active_status(
    users_stub, users_api_client
):
    await grant(users_stub, TOKEN, [PERMISSION, "modules:read"])

    await users_api_client.list_clinic_module_keys(TOKEN)

    recorded = await calls(users_stub)
    modules_calls = [call for call in recorded if call["path"] == "/api/v1/modules"]
    assert len(modules_calls) == 1
    assert modules_calls[0]["authorization"] == f"Bearer {TOKEN}"

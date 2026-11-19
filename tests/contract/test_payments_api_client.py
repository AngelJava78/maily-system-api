"""PaymentsApiClient against the simulation of mailySoft-pagos (contracts/payments-api-integration.md).

One case per row of the two translation tables (create and get): the real client code runs, only
the network is replaced by an in-memory transport.
"""

import logging
import time
import uuid

import httpx
import pytest

from src.integrations.errors import (
    PaymentsApiIdempotencyConflict,
    PaymentsApiPermissionDenied,
    PaymentsApiRejectedToken,
    PaymentsApiUnavailable,
)
from src.integrations.payments_api import PaymentsApiClient
from tests.helpers import PAGOS_BASE_URL

TOKEN = "SECRET-PAGOS-TOKEN-123"
SERVICE_TOKEN = "SECRET-SERVICE-TOKEN-456"


def create_kwargs(**overrides) -> dict:
    return {
        "idempotency_key": "clinic-subscription:1:2026-12-01",
        "amount": 129900,
        "currency": "MXN",
        "resource_type": "system-api:clinic-subscription",
        "resource_id": "1",
        "description": "Suscripción de clínica 1 — periodo 2026-12-01",
        **overrides,
    }


async def grant_payments(stub: httpx.AsyncClient, token: str = TOKEN, permissions=("payments:write", "payments:read")) -> None:
    response = await stub.post("/__test__/tokens", json={"token": token, "permissions": list(permissions)})
    assert response.status_code == 200


async def add_fault(stub: httpx.AsyncClient, mode: str, count: int = 1, delay: float = 30, operation: str = "create") -> None:
    response = await stub.post(
        "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay, "operation": operation}
    )
    assert response.status_code == 200


async def calls(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/calls")).json()


def client_with_service_token(payments_stub: httpx.AsyncClient) -> PaymentsApiClient:
    return PaymentsApiClient(payments_stub, PAGOS_BASE_URL, 5.0, SERVICE_TOKEN)


# --- create_payment ---


async def test_create_payment_sends_the_exact_body_and_returns_pending(payments_stub, payments_api_client):
    await grant_payments(payments_stub)

    payment = await payments_api_client.create_payment(TOKEN, **create_kwargs())

    assert payment.status == "pending"
    assert payment.amount == 129900
    assert payment.currency == "MXN"
    assert payment.checkout_url is not None

    [call] = await calls(payments_stub)
    assert call["path"] == "/api/v1/payments"
    assert call["authorization"] == f"Bearer {TOKEN}"
    assert call["idempotency_key"] == "clinic-subscription:1:2026-12-01"


async def test_a_retry_with_the_same_key_and_body_returns_the_same_payment(payments_stub, payments_api_client):
    await grant_payments(payments_stub)

    first = await payments_api_client.create_payment(TOKEN, **create_kwargs())
    second = await payments_api_client.create_payment(TOKEN, **create_kwargs())

    assert first.id == second.id


async def test_the_same_key_with_a_different_body_is_an_idempotency_conflict(payments_stub, payments_api_client):
    await grant_payments(payments_stub)
    await payments_api_client.create_payment(TOKEN, **create_kwargs())

    with pytest.raises(PaymentsApiIdempotencyConflict):
        await payments_api_client.create_payment(TOKEN, **create_kwargs(amount=1))


async def test_create_payment_with_no_token_is_unauthenticated(payments_stub, payments_api_client):
    with pytest.raises(PaymentsApiRejectedToken) as error:
        await payments_api_client.create_payment("", **create_kwargs())

    assert error.value.code == "unauthenticated"


async def test_create_payment_with_an_unrecognized_rejection_code_is_an_invalid_token(
    payments_stub, payments_api_client
):
    # A token that is not registered in this stub is authenticated (subscription periods, which
    # shares this simulation, never registers one): only an explicit 401 fault reproduces Pagos
    # rejecting the token outright, with a code this client does not recognize.
    await add_fault(payments_stub, "unauthorized_unknown", operation="create")

    with pytest.raises(PaymentsApiRejectedToken) as error:
        await payments_api_client.create_payment(TOKEN, **create_kwargs())

    assert error.value.code == "invalid_token"


async def test_create_payment_without_permission_is_a_permission_denial(payments_stub, payments_api_client):
    await grant_payments(payments_stub, permissions=())

    with pytest.raises(PaymentsApiPermissionDenied):
        await payments_api_client.create_payment(TOKEN, **create_kwargs())


@pytest.mark.parametrize("mode", ["unavailable", "malformed", "not_json", "redirect", "unauthorized_unreadable", "unauthorized_unknown"])
async def test_create_payment_everything_else_is_unavailable(payments_stub, payments_api_client, mode):
    await grant_payments(payments_stub)
    await add_fault(payments_stub, mode, operation="create")

    if mode in ("unauthorized_unreadable", "unauthorized_unknown"):
        with pytest.raises(PaymentsApiRejectedToken):
            await payments_api_client.create_payment(TOKEN, **create_kwargs())
    else:
        with pytest.raises(PaymentsApiUnavailable):
            await payments_api_client.create_payment(TOKEN, **create_kwargs())


async def test_create_payment_does_not_follow_a_redirection(payments_stub, payments_api_client):
    await add_fault(payments_stub, "redirect", operation="create")

    with pytest.raises(PaymentsApiUnavailable):
        await payments_api_client.create_payment(TOKEN, **create_kwargs())

    recorded = await calls(payments_stub)
    assert all(call["path"] != "/steal" for call in recorded)


async def test_create_payment_time_limit_covers_the_whole_call(payments_stub):
    await grant_payments(payments_stub)
    await add_fault(payments_stub, "slow", delay=1, operation="create")
    client = PaymentsApiClient(payments_stub, PAGOS_BASE_URL, 0.2)

    started = time.perf_counter()
    with pytest.raises(PaymentsApiUnavailable):
        await client.create_payment(TOKEN, **create_kwargs())

    assert time.perf_counter() - started < 1


async def test_a_refused_connection_is_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await PaymentsApiClient(client, PAGOS_BASE_URL, 5.0).create_payment(TOKEN, **create_kwargs())


async def test_the_token_never_appears_in_an_exception_or_in_the_logs(payments_stub, payments_api_client, caplog):
    caplog.set_level(logging.DEBUG)
    await add_fault(payments_stub, "unavailable", operation="create")
    with pytest.raises(PaymentsApiUnavailable) as error:
        await payments_api_client.create_payment(TOKEN, **create_kwargs())

    assert TOKEN not in str(error.value)
    assert TOKEN not in caplog.text


# --- get_payment (sync-on-read, research R8) ---


async def test_get_payment_without_a_service_token_is_skipped_without_a_call(payments_stub, payments_api_client):
    # `payments_api_client` (conftest fixture) has no service token configured.
    with pytest.raises(PaymentsApiUnavailable):
        await payments_api_client.get_payment_as_service(uuid.uuid4())

    assert await calls(payments_stub) == []


async def test_get_payment_returns_the_current_status(payments_stub):
    await grant_payments(payments_stub, token=TOKEN, permissions=("payments:write",))
    await grant_payments(payments_stub, token=SERVICE_TOKEN, permissions=("payments:read",))
    client = client_with_service_token(payments_stub)
    created = await client.create_payment(TOKEN, **create_kwargs())
    await payments_stub.post(f"/__test__/payments/{created.id}/status", json={"status": "approved"})

    payment = await client.get_payment_as_service(created.id)

    assert payment.status == "approved"
    assert payment.checkout_url is None


async def test_get_payment_uses_the_service_token_not_the_callers(payments_stub):
    await grant_payments(payments_stub, token=TOKEN, permissions=("payments:write",))
    await grant_payments(payments_stub, token=SERVICE_TOKEN, permissions=("payments:read",))
    client = client_with_service_token(payments_stub)
    created = await client.create_payment(TOKEN, **create_kwargs())

    await client.get_payment_as_service(created.id)

    get_calls = [c for c in await calls(payments_stub) if c["path"] == f"/api/v1/payments/{created.id}"]
    assert get_calls[0]["authorization"] == f"Bearer {SERVICE_TOKEN}"


async def test_get_payment_of_an_unknown_id_is_unavailable(payments_stub):
    await grant_payments(payments_stub, token=SERVICE_TOKEN, permissions=("payments:read",))
    client = client_with_service_token(payments_stub)

    with pytest.raises(PaymentsApiUnavailable):
        await client.get_payment_as_service(uuid.uuid4())


@pytest.mark.parametrize("mode", ["unavailable", "forbidden", "not_found", "malformed", "not_json", "redirect"])
async def test_get_payment_everything_else_is_unavailable(payments_stub, mode):
    await grant_payments(payments_stub, token=SERVICE_TOKEN, permissions=("payments:read",))
    client = client_with_service_token(payments_stub)
    await add_fault(payments_stub, mode, operation="get")

    with pytest.raises(PaymentsApiUnavailable):
        await client.get_payment_as_service(uuid.uuid4())

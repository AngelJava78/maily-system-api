"""`PaymentsApiClient` against the simulation of the payments API (spec 010, research R10).

Contract: `specs/010-subscription-periods/contracts/payments-api-integration.md`. The real client code runs;
only the network is replaced by an in-memory transport. Anything that is not exactly the expected answer is
«unavailable»: the state of a payment is never guessed.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from src.integrations.errors import PaymentsApiUnavailable
from src.integrations.payments_api import PAYMENT_PROVIDER, PaymentRecord, PaymentsApiClient
from tests.helpers import PAYMENTS_BASE_URL

TOKEN = "SECRET-TOKEN-789"
ORGANIZATION = "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b"
KEY = "sub-0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b-3a9c1d7e5b2f4a6c8e0d1b3f"

CREATE_ARGUMENTS: dict[str, Any] = {
    "idempotency_key": KEY,
    "amount": 49900,
    "currency": "MXN",
    "resource_type": "system-api:subscription",
    "resource_id": ORGANIZATION,
    "description": "Suscripción Plan Individual — mensual",
    "metadata": {"billing_period": "monthly", "settles_due_at": "2026-12-04T15:30:00Z"},
}

PAYMENT_ID = "6b0a0b1e-2d3c-4e5f-8a9b-0c1d2e3f4a5b"
VALID_BODY: dict[str, Any] = {
    "id": PAYMENT_ID,
    "status": "pending",
    "amount": 49900,
    "currency": "MXN",
    "resource_type": "system-api:subscription",
    "resource_id": ORGANIZATION,
    "checkout_url": "https://checkout.example.test/pay/1",
    "updated_at": "2026-12-01T10:00:00Z",
}


async def create(client: PaymentsApiClient, **overrides: Any) -> PaymentRecord:
    return await client.create_payment(TOKEN, **{**CREATE_ARGUMENTS, **overrides})


async def add_fault(stub: httpx.AsyncClient, mode: str, operation: str = "any", delay: float = 30) -> None:
    response = await stub.post(
        "/__test__/faults",
        json={"mode": mode, "count": 1, "delay_seconds": delay, "operation": operation},
    )
    assert response.status_code == 200


async def calls(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/calls")).json()


async def stored(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/payments")).json()


@asynccontextmanager
async def client_answering(status: int = 200, **response: Any) -> AsyncIterator[PaymentsApiClient]:
    """A client whose «payments API» answers exactly what the test says (`json=` or `content=`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, **response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        yield PaymentsApiClient(http, PAYMENTS_BASE_URL, 5.0)


# --- creating a payment ---


async def test_a_payment_is_created_and_returned_as_a_record(payments_stub, payments_api_client):
    record = await create(payments_api_client)

    assert isinstance(record, PaymentRecord)
    assert isinstance(record.id, uuid.UUID)
    assert record.status == "pending"
    assert (record.amount, record.currency) == (49900, "MXN")
    assert (record.resource_type, record.resource_id) == ("system-api:subscription", ORGANIZATION)
    assert record.checkout_url and record.checkout_url.startswith("https://")
    assert record.updated_at.utcoffset() == timedelta(0)


async def test_the_body_sent_to_the_payments_api_is_the_one_of_the_contract(payments_stub, payments_api_client):
    await create(payments_api_client)

    [payment] = await stored(payments_stub)
    assert (payment["amount"], payment["currency"]) == (49900, "MXN")
    assert (payment["resource_type"], payment["resource_id"]) == ("system-api:subscription", ORGANIZATION)
    assert payment["description"] == "Suscripción Plan Individual — mensual"
    assert payment["metadata"] == CREATE_ARGUMENTS["metadata"]
    assert payment["provider"] == PAYMENT_PROVIDER == "mercado_pago"
    assert payment["idempotency_key"] == KEY


async def test_the_exact_request_has_the_token_the_key_and_the_json_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=VALID_BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await PaymentsApiClient(http, PAYMENTS_BASE_URL, 5.0).create_payment(TOKEN, **CREATE_ARGUMENTS)

    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/api/v1/payments")
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["idempotency-key"] == KEY
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "provider": "mercado_pago",
        "amount": 49900,
        "currency": "MXN",
        "resource_type": "system-api:subscription",
        "resource_id": ORGANIZATION,
        "description": "Suscripción Plan Individual — mensual",
        "metadata": {"billing_period": "monthly", "settles_due_at": "2026-12-04T15:30:00Z"},
    }


async def test_no_header_of_the_original_request_is_forwarded(payments_stub, payments_api_client):
    await create(payments_api_client)

    names = set((await calls(payments_stub))[0]["header_names"])
    transport_defaults = {"host", "accept-encoding", "connection", "user-agent", "content-length"}
    assert names - transport_defaults == {"authorization", "accept", "content-type", "idempotency-key"}


async def test_the_same_key_and_the_same_body_give_the_same_payment(payments_stub, payments_api_client):
    first = await create(payments_api_client)
    second = await create(payments_api_client)

    assert first.id == second.id
    assert len(await stored(payments_stub)) == 1


async def test_a_new_key_gives_a_new_payment(payments_stub, payments_api_client):
    first = await create(payments_api_client)
    second = await create(payments_api_client, idempotency_key=KEY + "2")

    assert first.id != second.id


async def test_the_same_key_with_another_body_is_unavailable_never_the_old_payment(payments_api_client):
    await create(payments_api_client)

    with pytest.raises(PaymentsApiUnavailable):
        await create(payments_api_client, amount=79900)


async def test_the_description_and_the_metadata_are_optional():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json=VALID_BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await PaymentsApiClient(http, PAYMENTS_BASE_URL, 5.0).create_payment(
            TOKEN, **{**CREATE_ARGUMENTS, "description": None, "metadata": None}
        )

    assert "description" not in seen[0] and "metadata" not in seen[0]


@pytest.mark.parametrize("status", [200, 201])
async def test_a_creation_may_be_answered_with_200_or_201(status):
    async with client_answering(status, json=VALID_BODY) as client:
        assert (await create(client)).id == uuid.UUID(PAYMENT_ID)


async def test_a_payment_without_checkout_is_a_valid_record(payments_stub, payments_api_client):
    await add_fault(payments_stub, "no_checkout", "create")

    assert (await create(payments_api_client)).checkout_url is None


# --- reading a payment ---


async def test_a_payment_is_read_with_its_status_and_the_date_of_its_last_update(
    payments_stub, payments_api_client
):
    created = await create(payments_api_client)

    await payments_stub.post(
        f"/__test__/payments/{created.id}/status",
        json={"status": "approved", "updated_at": "2026-12-01T10:00:00Z"},
    )
    record = await payments_api_client.get_payment(TOKEN, created.id)

    assert record.id == created.id
    assert record.status == "approved"
    assert record.checkout_url is None  # «present while the payment has not been notified»
    assert record.updated_at == datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("status", ["pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"])
async def test_the_six_statuses_of_the_contract_are_read(payments_stub, payments_api_client, status):
    created = await create(payments_api_client)
    await payments_stub.post(f"/__test__/payments/{created.id}/status", json={"status": status})

    assert (await payments_api_client.get_payment(TOKEN, created.id)).status == status


async def test_the_amount_and_the_currency_that_the_payments_api_reports_are_the_ones_returned(
    payments_stub, payments_api_client
):
    created = await create(payments_api_client)
    await payments_stub.post(
        f"/__test__/payments/{created.id}/status", json={"status": "approved", "amount": 1, "currency": "USD"}
    )

    record = await payments_api_client.get_payment(TOKEN, created.id)

    assert (record.amount, record.currency) == (1, "USD")  # the Service decides what to do with it


async def test_the_request_of_a_read_has_the_token_and_nothing_else(payments_stub, payments_api_client):
    created = await create(payments_api_client)

    await payments_api_client.get_payment(TOKEN, created.id)

    call = (await calls(payments_stub))[-1]
    assert (call["method"], call["path"]) == ("GET", f"/api/v1/payments/{created.id}")
    assert call["authorization"] == f"Bearer {TOKEN}"
    assert call["idempotency_key"] is None


async def test_a_payment_that_does_not_exist_is_unavailable(payments_api_client):
    with pytest.raises(PaymentsApiUnavailable):
        await payments_api_client.get_payment(TOKEN, uuid.uuid4())


async def test_the_answer_must_be_about_the_payment_that_was_asked_for():
    async with client_answering(200, json=VALID_BODY) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.uuid4())  # the body says another identifier


# --- failures and unexpected answers, in both operations ---


@pytest.mark.parametrize(
    "mode",
    [
        "unavailable",
        "unauthorized",
        "forbidden",
        "organization_required",  # the person has no tenant in the users API yet
        "malformed",
        "not_json",
        "redirect",  # 307: it is not followed
        "unknown_status",  # a status that is not in the contract
    ],
)
async def test_a_failure_or_an_unexpected_answer_is_unavailable(payments_stub, payments_api_client, mode):
    created = await create(payments_api_client)

    await add_fault(payments_stub, mode, "create")
    with pytest.raises(PaymentsApiUnavailable):
        await create(payments_api_client, idempotency_key=KEY + "-other")

    await add_fault(payments_stub, mode, "get")
    with pytest.raises(PaymentsApiUnavailable):
        await payments_api_client.get_payment(TOKEN, created.id)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 502, 503])
async def test_any_other_status_is_unavailable(status):
    async with client_answering(status, json=VALID_BODY) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await create(client)
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))


@pytest.mark.parametrize("body", [[], "texto", 7, None, [VALID_BODY]])
async def test_a_body_that_is_not_an_object_is_unavailable(body):
    async with client_answering(200, json=body) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))


async def test_a_body_that_is_not_json_is_unavailable():
    async with client_answering(200, content=b"<html>hola</html>") as client:
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))


@pytest.mark.parametrize("missing", [key for key in VALID_BODY if key != "checkout_url"])
async def test_a_body_without_one_of_the_fields_is_unavailable(missing):
    body = {key: value for key, value in VALID_BODY.items() if key != missing}

    async with client_answering(200, json=body) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))


async def test_a_body_without_the_checkout_field_is_valid():
    body = {key: value for key, value in VALID_BODY.items() if key != "checkout_url"}

    async with client_answering(200, json=body) as client:
        record = await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))

    assert record.checkout_url is None


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "no-es-un-uuid"},
        {"id": None},
        {"status": "mystery"},
        {"status": "APPROVED"},
        {"status": None},
        {"status": ["approved"]},  # unhashable: it must not break the check of the set of statuses
        {"status": {"value": "approved"}},
        {"amount": True},
        {"amount": 499.0},
        {"amount": "49900"},
        {"amount": None},
        {"currency": "MX"},
        {"currency": "MXNN"},
        {"currency": None},
        {"currency": 484},
        {"resource_type": None},
        {"resource_id": 7},
        {"checkout_url": 123},
        {"updated_at": "2026-12-01T10:00:00"},  # no zone
        {"updated_at": "ayer"},
        {"updated_at": None},
        {"updated_at": 1700000000},
    ],
)
async def test_an_invalid_value_is_unavailable(changes):
    async with client_answering(200, json={**VALID_BODY, **changes}) as client:
        with pytest.raises(PaymentsApiUnavailable):
            await client.get_payment(TOKEN, uuid.UUID(PAYMENT_ID))


# --- no retries, time limit and secrets ---


async def test_each_operation_makes_one_call_and_never_retries(payments_stub, payments_api_client):
    await add_fault(payments_stub, "unavailable", "create")

    with pytest.raises(PaymentsApiUnavailable):
        await create(payments_api_client)

    assert len(await calls(payments_stub)) == 1


async def test_a_slow_answer_is_cut_by_the_total_time_limit(payments_stub):
    await add_fault(payments_stub, "slow", "create", delay=5)
    client = PaymentsApiClient(payments_stub, PAYMENTS_BASE_URL, 0.2)

    started = time.monotonic()
    with pytest.raises(PaymentsApiUnavailable):
        await create(client)

    assert time.monotonic() - started < 2


@pytest.mark.parametrize("mode", ["unavailable", "unauthorized", "malformed", "not_json", "redirect", "organization_required"])
async def test_the_logs_never_contain_the_token_the_address_or_the_body(
    payments_stub, payments_api_client, caplog, mode
):
    created = await create(payments_api_client)
    await add_fault(payments_stub, mode, "get")

    # Only the loggers of this service: `create_app` silences the `httpx` logger, which writes the URL.
    with caplog.at_level(logging.DEBUG, logger="src"), pytest.raises(PaymentsApiUnavailable):
        await payments_api_client.get_payment(TOKEN, created.id)

    assert TOKEN not in caplog.text
    assert "payments-api.test" not in caplog.text
    assert "SECRETO-INTERNO" not in caplog.text


async def test_the_error_never_carries_the_body_of_the_other_api(payments_stub, payments_api_client):
    await add_fault(payments_stub, "unavailable", "create")

    with pytest.raises(PaymentsApiUnavailable) as error:
        await create(payments_api_client)

    assert "SECRETO-INTERNO" not in str(error.value)
    assert TOKEN not in str(error.value)

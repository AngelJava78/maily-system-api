"""`ClinicsApiClient.get_organization` against the simulation of the clinics API (spec 010, research R9).

Contract: `specs/010-subscription-periods/contracts/clinics-api-integration.md`. The real client code runs;
only the network is replaced by an in-memory transport. Anything that is not exactly the expected answer
is «unavailable», and only a 404 with the code `not_found` means that the organization is not there.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from src.integrations.clinics_api import ClinicsApiClient, OrganizationRecord
from src.integrations.errors import ClinicsApiUnavailable, OrganizationNotFound
from tests.helpers import CLINICS_BASE_URL

TOKEN = "SECRET-TOKEN-456"
ORGANIZATION = uuid.UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")
CREATED = "2026-11-20T15:30:00Z"
VALID_BODY = {
    "id": str(ORGANIZATION),
    "subscription_id": 3,
    "billing_period": "monthly",
    "created_at": CREATED,
}


async def register(stub: httpx.AsyncClient, **overrides) -> None:
    body = {**VALID_BODY, "owner_token": TOKEN, **overrides}
    response = await stub.post("/__test__/organizations", json=body)
    assert response.status_code == 200


async def add_fault(stub: httpx.AsyncClient, mode: str, delay: float = 30) -> None:
    response = await stub.post(
        "/__test__/faults",
        json={"mode": mode, "count": 1, "delay_seconds": delay, "operation": "organizations"},
    )
    assert response.status_code == 200


async def calls(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/calls")).json()


@asynccontextmanager
async def client_answering(status: int = 200, **response: Any) -> AsyncIterator[ClinicsApiClient]:
    """A client whose «clinics API» answers exactly what the test says (`json=` or `content=`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, **response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        yield ClinicsApiClient(http, CLINICS_BASE_URL, 5.0)


# --- the answer that the service expects ---


async def test_it_returns_the_four_fields_that_the_service_uses(clinics_stub, clinics_api_client):
    await register(clinics_stub)

    organization = await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    assert organization == OrganizationRecord(
        id=ORGANIZATION,
        subscription_id=3,
        billing_period="monthly",
        created_at=datetime(2026, 11, 20, 15, 30, tzinfo=UTC),
    )


@pytest.mark.parametrize("billing_period", ["monthly", "annual"])
async def test_both_billing_periods_are_valid(clinics_stub, clinics_api_client, billing_period):
    await register(clinics_stub, billing_period=billing_period)

    assert (await clinics_api_client.get_organization(TOKEN, ORGANIZATION)).billing_period == billing_period


async def test_the_creation_is_normalized_to_utc(clinics_stub, clinics_api_client):
    await register(clinics_stub, created_at="2026-11-20T09:30:00-06:00")

    created_at = (await clinics_api_client.get_organization(TOKEN, ORGANIZATION)).created_at

    assert created_at == datetime(2026, 11, 20, 15, 30, tzinfo=UTC)
    assert created_at.utcoffset() == timedelta(0)


async def test_the_extra_fields_of_the_answer_are_ignored(clinics_stub, clinics_api_client):
    await register(clinics_stub)  # the simulation adds a `name` that the service does not use

    organization = await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    assert not hasattr(organization, "name")


async def test_the_token_of_the_person_is_forwarded_untouched_to_the_organization(
    clinics_stub, clinics_api_client
):
    await register(clinics_stub)

    await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    [call] = await calls(clinics_stub)
    assert call["path"] == f"/api/v1/organizations/{ORGANIZATION}"
    assert call["authorization"] == f"Bearer {TOKEN}"


async def test_no_header_of_the_original_request_is_forwarded(clinics_stub, clinics_api_client):
    await register(clinics_stub)

    await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    names = set((await calls(clinics_stub))[0]["header_names"])
    transport_defaults = {"host", "accept-encoding", "connection", "user-agent"}
    assert names - transport_defaults == {"authorization", "accept"}


async def test_it_makes_one_call_and_never_retries(clinics_stub, clinics_api_client):
    await add_fault(clinics_stub, "unavailable")

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    assert len(await calls(clinics_stub)) == 1


# --- the organization is not there ---


async def test_an_organization_that_is_not_registered_is_not_found(clinics_stub, clinics_api_client):
    with pytest.raises(OrganizationNotFound):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)


async def test_an_organization_of_another_person_is_not_found_like_one_that_does_not_exist(
    clinics_stub, clinics_api_client
):
    await register(clinics_stub, owner_token="another-person")

    with pytest.raises(OrganizationNotFound):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)


async def test_a_404_with_the_code_not_found_is_the_only_one_that_means_it_is_not_there():
    async with client_answering(404, json={"code": "not_found", "message": "La organización no existe."}) as client:
        with pytest.raises(OrganizationNotFound):
            await client.get_organization(TOKEN, ORGANIZATION)


@pytest.mark.parametrize(
    "response",
    [
        {"content": b""},
        {"content": b"<html>no existe</html>"},
        {"json": {"code": "route_not_found"}},  # a route that its version does not have
        {"json": {"code": 404}},
        {"json": {"detail": "Not Found"}},
        {"json": ["not_found"]},
    ],
)
async def test_a_404_without_the_code_not_found_is_unavailable(response):
    async with client_answering(404, **response) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


# --- anything else is «unavailable», never a data ---


@pytest.mark.parametrize(
    "mode",
    [
        "unavailable",  # 503
        "unauthorized",  # 401
        "forbidden",  # 403
        "malformed",  # 200 without the fields
        "not_json",
        "redirect",  # 307, which is not followed
        "not_found_other_code",  # a 404 that is not «the organization is not there»
        "missing_billing_period",  # the field that the real API does not publish yet
        "invalid_billing_period",
    ],
)
async def test_a_failure_or_an_unexpected_answer_is_unavailable(clinics_stub, clinics_api_client, mode):
    await register(clinics_stub)
    await add_fault(clinics_stub, mode)

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)


async def test_without_the_billing_period_it_does_not_assume_monthly(clinics_stub, clinics_api_client):
    await register(clinics_stub)
    await add_fault(clinics_stub, "missing_billing_period")

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)
    # The next answer, with the field, is fine: the failure was the answer, not the organization.
    assert (await clinics_api_client.get_organization(TOKEN, ORGANIZATION)).billing_period == "monthly"


@pytest.mark.parametrize("status", [400, 401, 403, 409, 422, 429, 500, 502, 503])
async def test_any_other_status_is_unavailable(status):
    async with client_answering(status, json={"code": "not_found"}) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


@pytest.mark.parametrize("body", [[], "texto", 7, None, [VALID_BODY]])
async def test_a_body_that_is_not_an_object_is_unavailable(body):
    async with client_answering(200, json=body) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


async def test_a_body_that_is_not_json_is_unavailable():
    async with client_answering(200, content=b"<html>hola</html>") as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


@pytest.mark.parametrize("missing", list(VALID_BODY))
async def test_a_body_without_one_of_the_four_fields_is_unavailable(missing):
    body = {key: value for key, value in VALID_BODY.items() if key != missing}

    async with client_answering(200, json=body) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


@pytest.mark.parametrize(
    "changes",
    [
        {"subscription_id": 0},
        {"subscription_id": -3},
        {"subscription_id": True},
        {"subscription_id": "3"},
        {"subscription_id": 3.0},
        {"subscription_id": None},
        {"created_at": "2026-11-20T15:30:00"},  # no zone: the instant would be ambiguous
        {"created_at": "ayer"},
        {"created_at": None},
        {"created_at": 1700000000},
        {"billing_period": "weekly"},
        {"billing_period": "MONTHLY"},
        {"billing_period": None},
        {"billing_period": 1},
        {"id": "no-es-un-uuid"},
        {"id": str(uuid.uuid4())},  # the answer is about another organization
        {"id": None},
    ],
)
async def test_an_invalid_value_is_unavailable(changes):
    async with client_answering(200, json={**VALID_BODY, **changes}) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await client.get_organization(TOKEN, ORGANIZATION)


# --- time and secrets ---


async def test_a_slow_answer_is_cut_by_the_total_time_limit(clinics_stub):
    await register(clinics_stub)
    await add_fault(clinics_stub, "slow", delay=5)
    client = ClinicsApiClient(clinics_stub, CLINICS_BASE_URL, 0.2)

    started = time.monotonic()
    with pytest.raises(ClinicsApiUnavailable):
        await client.get_organization(TOKEN, ORGANIZATION)

    assert time.monotonic() - started < 2


@pytest.mark.parametrize("mode", ["unavailable", "unauthorized", "malformed", "not_json", "redirect"])
async def test_the_logs_never_contain_the_token_the_address_or_the_body(
    clinics_stub, clinics_api_client, caplog, mode
):
    await register(clinics_stub)
    await add_fault(clinics_stub, mode)

    # Only the loggers of this service: `create_app` silences the `httpx` logger, which writes the URL.
    with caplog.at_level(logging.DEBUG, logger="src"), pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    assert TOKEN not in caplog.text
    assert "clinics-api.test" not in caplog.text
    assert "SECRETO-INTERNO" not in caplog.text


async def test_the_error_never_carries_the_body_of_the_other_api(clinics_stub, clinics_api_client):
    await register(clinics_stub)
    await add_fault(clinics_stub, "unavailable")

    with pytest.raises(ClinicsApiUnavailable) as error:
        await clinics_api_client.get_organization(TOKEN, ORGANIZATION)

    assert "SECRETO-INTERNO" not in str(error.value)
    assert TOKEN not in str(error.value)

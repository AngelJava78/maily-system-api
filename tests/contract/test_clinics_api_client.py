"""ClinicsApiClient against the simulation of the clinics API (contracts/clinics-api-integration.md).

The real client code runs; only the network is replaced by an in-memory transport.
"""

import logging
import time

import httpx
import pytest

from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.errors import ClinicsApiUnavailable
from tests.helpers import CLINICS_BASE_URL

TOKEN = "SECRET-TOKEN-456"


async def set_counts(stub: httpx.AsyncClient, counts: dict[int, int]) -> None:
    response = await stub.post("/__test__/counts", json={str(k): v for k, v in counts.items()})
    assert response.status_code == 200


async def add_fault(stub: httpx.AsyncClient, mode: str, delay: float = 30) -> None:
    response = await stub.post(
        "/__test__/faults", json={"mode": mode, "count": 1, "delay_seconds": delay}
    )
    assert response.status_code == 200


async def calls(stub: httpx.AsyncClient) -> list[dict]:
    return (await stub.get("/__test__/calls")).json()


async def test_without_a_filter_it_returns_every_subscription_with_clinics(
    clinics_stub, clinics_api_client
):
    await set_counts(clinics_stub, {1: 2, 6: 14})

    assert await clinics_api_client.get_counts(TOKEN) == {1: 2, 6: 14}


async def test_with_a_filter_it_returns_only_the_requested_ones(clinics_stub, clinics_api_client):
    await set_counts(clinics_stub, {1: 2, 6: 14})

    assert await clinics_api_client.get_counts(TOKEN, [1]) == {1: 2}
    assert await clinics_api_client.get_counts(TOKEN, [1, 6]) == {1: 2, 6: 14}


async def test_a_subscription_without_clinics_does_not_appear(clinics_stub, clinics_api_client):
    await set_counts(clinics_stub, {1: 2, 2: 0})

    assert await clinics_api_client.get_counts(TOKEN, [2]) == {}


async def test_the_identifiers_are_repeated_in_the_query(clinics_stub, clinics_api_client):
    await set_counts(clinics_stub, {1: 2, 6: 14})

    await clinics_api_client.get_counts(TOKEN, [1, 6])

    recorded = await calls(clinics_stub)
    assert recorded[0]["path"] == "/api/v1/clinics/subscription-counts"
    assert recorded[0]["subscription_ids"] == [1, 6]


async def test_the_token_of_the_person_is_forwarded_untouched(clinics_stub, clinics_api_client):
    await clinics_api_client.get_counts(TOKEN)

    assert (await calls(clinics_stub))[0]["authorization"] == f"Bearer {TOKEN}"


async def test_no_header_of_the_original_request_is_forwarded(clinics_stub, clinics_api_client):
    await clinics_api_client.get_counts(TOKEN)

    names = set((await calls(clinics_stub))[0]["header_names"])
    transport_defaults = {"host", "accept-encoding", "connection", "user-agent"}
    assert names - transport_defaults == {"authorization", "accept"}


async def test_an_empty_filter_asks_nothing(clinics_stub, clinics_api_client):
    assert await clinics_api_client.get_counts(TOKEN, []) == {}
    assert await calls(clinics_stub) == []


@pytest.mark.parametrize(
    "mode",
    ["unavailable", "unauthorized", "forbidden", "malformed", "not_json", "redirect"],
)
async def test_a_failure_is_unavailable_never_a_zero(clinics_stub, clinics_api_client, mode):
    await set_counts(clinics_stub, {1: 2})
    await add_fault(clinics_stub, mode)

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_counts(TOKEN, [1])


@pytest.mark.parametrize("ids", [None, [1]], ids=["unfiltered", "filtered"])
@pytest.mark.parametrize("mode", ["negative_count", "unrequested_id", "duplicate_id"])
async def test_an_unexpected_body_is_unavailable_never_a_partial_dictionary(
    clinics_stub, clinics_api_client, mode, ids
):
    await set_counts(clinics_stub, {1: 2})
    await add_fault(clinics_stub, mode)

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_counts(TOKEN, ids)


async def test_a_redirection_is_not_followed(clinics_stub, clinics_api_client):
    await add_fault(clinics_stub, "redirect")

    with pytest.raises(ClinicsApiUnavailable):
        await clinics_api_client.get_counts(TOKEN)

    recorded = await calls(clinics_stub)
    assert len(recorded) == 1
    assert all(call["path"] != "/steal" for call in recorded)


async def test_a_refused_connection_is_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(ClinicsApiUnavailable):
            await ClinicsApiClient(client, CLINICS_BASE_URL, 5.0).get_counts(TOKEN)


async def test_the_time_limit_covers_the_whole_call(clinics_stub):
    await add_fault(clinics_stub, "slow", delay=1)
    client = ClinicsApiClient(clinics_stub, CLINICS_BASE_URL, 0.2)

    started = time.perf_counter()
    with pytest.raises(ClinicsApiUnavailable):
        await client.get_counts(TOKEN)

    assert time.perf_counter() - started < 1


async def test_the_token_never_appears_in_an_exception_or_in_the_logs(
    clinics_stub, clinics_api_client, caplog
):
    caplog.set_level(logging.DEBUG)
    messages = []
    for mode in ("unavailable", "not_json", "forbidden", "redirect"):
        await add_fault(clinics_stub, mode)
        with pytest.raises(ClinicsApiUnavailable) as error:
            await clinics_api_client.get_counts(TOKEN)
        messages.append(str(error.value))

    assert all(TOKEN not in message for message in messages)
    assert TOKEN not in caplog.text

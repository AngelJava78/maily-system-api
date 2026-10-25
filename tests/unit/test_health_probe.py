"""HTTP calls to the monitored components (spec 005, FR-019, FR-021; research R6).

Against the simulation of components in memory and the transport that produces network failures:
the real client of the checks is exercised, with its time limit over the whole call, no redirections,
no more than 64 KiB, no compression, no cookies and no credentials.
"""

import logging

import httpx
import pytest

from src.integrations.health_probe import (
    MAX_RESPONSE_BYTES,
    HealthProbeClient,
    create_health_http_client,
    same_origin_url,
)
from tests.health_support import FaultTransport, stub_url
from tests.stubs.components.app import create_stub_app


@pytest.fixture
def stub():
    return create_stub_app()


@pytest.fixture
async def probe(stub):
    client = create_health_http_client(
        timeout_seconds=0.3,
        user_agent="ua-pruebas",
        transport=FaultTransport(httpx.ASGITransport(app=stub)),
    )
    async with client:
        yield HealthProbeClient(client, timeout_seconds=0.3)


async def calls_of(stub) -> list[dict]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stub), base_url="http://s") as client:
        return (await client.get("/__test__/calls")).json()


async def test_a_healthy_answer_comes_with_its_status_body_and_latency(probe):
    response = await probe.get_json(stub_url("healthy") + "/health/live")

    assert response.status_code == 200
    assert response.failure is None
    assert response.body == b'{"status":"ok"}'
    assert isinstance(response.latency_ms, int) and response.latency_ms >= 0


@pytest.mark.parametrize("prefix", ["too-large", "too-large-chunked"])
async def test_an_answer_above_64_kib_is_too_large(probe, prefix):
    response = await probe.get_json(stub_url(prefix) + "/health/live")

    assert (response.failure, response.body) == ("response_too_large", None)


async def test_an_answer_of_exactly_64_kib_is_accepted():
    body = b"x" * MAX_RESPONSE_BYTES
    # `stream=`: a `content=` answer would be read in advance, unlike a real one.
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=httpx.ByteStream(body)))
    async with create_health_http_client(timeout_seconds=1, user_agent="ua", transport=transport) as client:
        response = await HealthProbeClient(client, timeout_seconds=1).get_json("http://h/x")

    assert (response.failure, len(response.body)) == (None, MAX_RESPONSE_BYTES)


async def test_a_compressed_answer_is_an_invalid_response(probe):
    response = await probe.get_json(stub_url("gzip") + "/health/live")

    assert response.failure == "invalid_response"


async def test_a_redirection_is_returned_and_never_followed(probe, stub):
    response = await probe.get_json(stub_url("redirect") + "/health/live")

    assert response.status_code == 307
    assert [call["path"] for call in await calls_of(stub)] == ["/redirect/health/live"]


async def test_a_component_that_does_not_answer_in_time_is_a_timeout(probe):
    response = await probe.get_json(stub_url("slow") + "/health/live")

    assert response.failure == "timeout"
    assert 250 <= response.latency_ms <= 1500


@pytest.mark.parametrize(
    ("host", "code"),
    [
        ("dns-error.test", "dns_error"),
        ("refused.test", "connection_error"),
        ("tls-error.test", "connection_error"),
        ("reset.test", "connection_error"),
    ],
)
async def test_the_network_failures_are_translated(probe, host, code):
    response = await probe.get_json(stub_url("healthy", host=host) + "/health/live")

    assert (response.status_code, response.body, response.failure) == (None, None, code)


async def test_no_call_carries_a_token_or_a_cookie_and_all_are_get_with_the_agent(probe, stub):
    await probe.get_json(stub_url("healthy") + "/health/live")  # it answers with a cookie
    await probe.get_json(stub_url("healthy") + "/health/ready")

    calls = await calls_of(stub)
    assert len(calls) == 2
    assert not any(call["has_authorization"] or call["has_cookie"] for call in calls)
    assert {call["method"] for call in calls} == {"GET"}
    assert all("user-agent" in call["header_names"] for call in calls)


@pytest.mark.parametrize("prefix", ["spa", "html"])
async def test_the_status_of_a_frontend_comes_without_its_body(probe, prefix):
    response = await probe.get_status(stub_url(prefix) + "/healthz/")

    assert (response.status_code, response.body, response.failure) == (200, None, None)


async def test_an_unexpected_failure_of_the_transport_is_an_unexpected_error():
    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("SECRETO-INTERNO")

    transport = httpx.MockTransport(boom)
    async with create_health_http_client(timeout_seconds=1, user_agent="ua", transport=transport) as client:
        response = await HealthProbeClient(client, timeout_seconds=1).get_json("http://h/x")

    assert response.failure == "unexpected_error"


async def test_the_logs_never_carry_the_address(probe, caplog):
    with caplog.at_level(logging.DEBUG):
        await probe.get_json(stub_url("healthy", host="dns-error.test") + "/health/live")
        await probe.get_json(stub_url("slow") + "/health/live")

    assert "dns-error.test" not in caplog.text
    assert "components.test" not in caplog.text


@pytest.mark.parametrize(
    ("base_url", "path", "expected"),
    [
        ("http://components.test/healthy", "/health/live", "http://components.test/healthy/health/live"),
        ("https://h.test:8443", "/info", "https://h.test:8443/info"),
        ("http://h.test", "@otro.test/x", None),  # would change the host
        ("http://h.test:8000", ":9000/x", None),  # would change the port
        ("http://h.test", ".otro.test/x", None),  # would change the host too
        ("http://h.test/app", "@otro.test", "http://h.test/app@otro.test"),  # "@" in the path: same host
    ],
)
def test_the_address_of_a_call_always_has_the_host_of_the_base_url(base_url, path, expected):
    assert same_origin_url(base_url, path) == expected

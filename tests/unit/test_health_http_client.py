"""The HTTP client of the health checks (spec 005, FR-019, FR-021; research R6).

Its settings are part of the protection against SSRF and of the promise that no call carries the
token, the headers of the request or any credential: it never follows redirections, ignores the
environment (proxies, `.netrc`), rejects every cookie, keeps no connection alive and asks for the body
without compression.
"""

import httpx
import pytest

from src.integrations.health_probe import (
    MAX_RESPONSE_BYTES,
    PROBE_MAX_CONNECTIONS,
    create_health_http_client,
)


class Recorder:
    """A transport that answers what each test needs and remembers every request."""

    def __init__(self, handler) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def client_with(handler) -> tuple[httpx.AsyncClient, Recorder]:
    recorder = Recorder(handler)
    client = create_health_http_client(
        timeout_seconds=0.5, user_agent="agente-prueba", transport=httpx.MockTransport(recorder)
    )
    return client, recorder


def test_the_limits_are_the_documented_ones():
    assert MAX_RESPONSE_BYTES == 65_536
    assert PROBE_MAX_CONNECTIONS == 200


async def test_a_redirection_is_returned_and_never_followed():
    client, recorder = client_with(
        lambda request: httpx.Response(307, headers={"Location": "http://otro-host/robar"})
    )
    async with client:
        response = await client.get("http://componente.test/health/live")

    assert response.status_code == 307
    assert [str(r.url) for r in recorder.requests] == ["http://componente.test/health/live"]


async def test_the_environment_is_not_trusted():
    async with create_health_http_client(timeout_seconds=0.5, user_agent="ua") as client:
        assert client.trust_env is False


async def test_a_cookie_of_one_answer_never_travels_in_the_next_call():
    client, recorder = client_with(
        lambda request: httpx.Response(
            200, json={"status": "ok"}, headers={"Set-Cookie": "session=SECRETO-INTERNO; Path=/"}
        )
    )
    async with client:
        await client.get("http://componente.test/health/live")
        await client.get("http://componente.test/health/live")

    assert all("cookie" not in r.headers for r in recorder.requests)


async def test_it_sends_its_user_agent_asks_for_no_compression_and_no_credentials():
    client, recorder = client_with(lambda request: httpx.Response(200, json={"status": "ok"}))
    async with client:
        await client.get("http://componente.test/health/live")

    [request] = recorder.requests
    assert request.headers["user-agent"] == "agente-prueba"
    assert request.headers["accept-encoding"] == "identity"
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers


async def test_the_timeout_is_the_one_received():
    async with create_health_http_client(timeout_seconds=0.5, user_agent="ua") as client:
        assert client.timeout == httpx.Timeout(0.5)


@pytest.mark.parametrize("attribute", ["_max_connections", "_max_keepalive_connections"])
async def test_no_connection_is_kept_alive_and_up_to_200_are_opened(attribute):
    async with create_health_http_client(timeout_seconds=0.5, user_agent="ua") as client:
        pool = client._transport._pool  # the real transport (no MockTransport here)

        expected = {"_max_connections": 200, "_max_keepalive_connections": 0}[attribute]
        assert getattr(pool, attribute) == expected

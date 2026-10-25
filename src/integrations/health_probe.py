"""HTTP calls to the monitored components (spec 005, FR-019, FR-021; research R6).

`create_health_http_client` builds the only client that calls components. Every setting is part of
the protection against SSRF and of the promise that no call carries the token of the person, the
headers of the request or any credential:

- it never follows a redirection (a 3xx is an answer, `unexpected_status`);
- it ignores the environment (`trust_env=False`): no proxies and no `.netrc` credentials;
- it rejects every cookie, so no cookie of an answer travels in another call;
- it keeps no connection alive: an old connection that the component closed would look like a
  failure of the component, and checks are seconds apart anyway;
- it asks for the body without compression (`Accept-Encoding: identity`), so a compressed "bomb"
  cannot grow in memory.

This module knows neither FastAPI, the DTOs nor the database.
"""

import asyncio
import http.cookiejar
import logging
import socket
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# The most a check reads of an answer (FR-019): one byte more is `response_too_large`.
MAX_RESPONSE_BYTES = 65_536
# Enough for 50 components with three calls each at the same time, without waiting for the pool.
PROBE_MAX_CONNECTIONS = 200
# How deep the chain of causes of an exception is searched for a DNS failure.
_MAX_CAUSES = 10


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """What one call answered, bounded: it never leaves the process.

    `failure` is a code of FR-018 when there was no usable answer (`timeout`, `dns_error`,
    `connection_error`, `response_too_large`, `invalid_response` or `unexpected_error`); `body` is at
    most 64 KiB and `None` for a frontend, whose body is not read. `latency_ms` is measured also when
    the call fails.
    """

    status_code: int | None
    body: bytes | None
    failure: str | None
    latency_ms: int


def same_origin_url(base_url: str, path: str) -> str | None:
    """`base_url` + `path`, only if the result keeps the scheme, host and port of `base_url`.

    The paths are validated when a component is registered, so this never fails for them; it covers
    rows changed by hand in the database (FR-026: the host of every call is the one of `base_url`).
    """
    url = base_url + path
    try:
        base, full = httpx.URL(base_url), httpx.URL(url)
        same = (full.scheme, full.host, full.port) == (base.scheme, base.host, base.port)
    except (httpx.InvalidURL, ValueError):
        return None
    return url if same else None


def _milliseconds_since(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _caused_by_dns(error: BaseException) -> bool:
    current: BaseException | None = error
    for _ in range(_MAX_CAUSES):
        if current is None:
            return False
        if isinstance(current, socket.gaierror):
            return True
        current = current.__cause__ or current.__context__
    return False


def _failure_of(error: Exception) -> str:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "dns_error" if _caused_by_dns(error) else "connection_error"
    if isinstance(error, (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError, httpx.CloseError)):
        return "connection_error"
    return "unexpected_error"


class HealthProbeClient:
    """`GET` calls to the components with a time limit over the **whole** call (DNS, connection,
    headers and body), without retries and reading at most 64 KiB (FR-019, FR-021).
    """

    def __init__(self, http_client: httpx.AsyncClient, timeout_seconds: float) -> None:
        self._http = http_client
        self._timeout = timeout_seconds

    async def get_json(self, url: str) -> ProbeResponse:
        """The status and the raw body (at most 64 KiB) of a route of the contract."""
        return await self._get(url, accept="application/json", read_body=True)

    async def get_status(self, url: str) -> ProbeResponse:
        """Only the status: the health route of a frontend (its body is not read)."""
        return await self._get(url, accept="*/*", read_body=False)

    async def _get(self, url: str, *, accept: str, read_body: bool) -> ProbeResponse:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                async with self._http.stream(
                    "GET", url, headers={"Accept": accept}, follow_redirects=False
                ) as response:
                    return await self._read(response, started, read_body)
        except Exception as error:
            failure = _failure_of(error)
            # Only the kind of failure: never the address, the body or the text of the error.
            logger.debug("Health check call failed (%s, %s)", failure, type(error).__name__)
            return ProbeResponse(None, None, failure, _milliseconds_since(started))

    @staticmethod
    async def _read(response: httpx.Response, started: float, read_body: bool) -> ProbeResponse:
        status = response.status_code
        if not read_body:
            return ProbeResponse(status, None, None, _milliseconds_since(started))
        length = response.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
            return ProbeResponse(status, None, "response_too_large", _milliseconds_since(started))
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        if encoding not in ("", "identity"):
            # `identity` was asked: reading a compressed body could make it grow in memory.
            return ProbeResponse(status, None, "invalid_response", _milliseconds_since(started))
        body = bytearray()
        async for chunk in response.aiter_raw():
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                return ProbeResponse(status, None, "response_too_large", _milliseconds_since(started))
        return ProbeResponse(status, bytes(body), None, _milliseconds_since(started))


def create_health_http_client(
    *,
    timeout_seconds: float,
    user_agent: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The client of the health checks; `transport` is only for the tests."""
    no_cookies = http.cookiejar.CookieJar(
        policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[])
    )
    return httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(timeout_seconds),
        limits=httpx.Limits(max_connections=PROBE_MAX_CONNECTIONS, max_keepalive_connections=0),
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
        # The jar itself: `httpx.Cookies(jar)` would copy it into a new jar with the default policy.
        cookies=no_cookies,
    )

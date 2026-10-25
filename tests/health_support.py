"""Helpers of the health tests (spec 005); the fixtures live in `tests/conftest.py`.

- `FakeClock`: a clock that only moves when the test says so (schedule, `next_start_at`, cache).
- `FaultTransport`: produces the network failures that an in-memory transport cannot (DNS, refused
  connection, TLS, cut connection) and passes everything else to the simulation of components.
- `HealthConfigHolder`: the configuration that the application receives, changeable by each test
  (the tests use fractions of a second, which the environment variables do not allow).
- `insert_component`: a component written directly in the database.
- `install_health_overrides` and `HealthApi`: the application under test with all of the above.
"""

import asyncio
import dataclasses
import itertools
import json
import socket
import ssl
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from src.config import AllowedHosts, DatabaseSchedule, HealthConfig
from tests.helpers import TEST_TOKEN, grant

# Tuesday, 27 October 2026, 10:00 in Mexico City: inside the default schedule of the database.
TEST_NOW = datetime(2026, 10, 27, 16, 0, tzinfo=UTC)
# The schedule of the runbook `Deploy-PgAutoShutdown.ps1`: Monday to Friday, 08:00 to 20:00 in
# Mexico City (UTC-6 all the year), so the window opens at 14:00 UTC.
RUNBOOK_SCHEDULE = DatabaseSchedule(
    zone=ZoneInfo("America/Mexico_City"),
    days=frozenset({0, 1, 2, 3, 4}),
    start=time(8, 0),
    end=time(20, 0),
)

COMPONENTS_HOST = "components.test"
TEST_ALLOWED_HOSTS = "components.test,dns-error.test,refused.test,reset.test,tls-error.test"
HEALTH_PERMISSIONS = ("health:read", "health:write", "health:update", "health:delete")
TEST_HEALTH_CONFIG = HealthConfig(
    check_timeout_seconds=0.5,
    ready_timeout_seconds=0.3,
    cache_seconds=0.0,
    allowed_hosts=AllowedHosts.parse(TEST_ALLOWED_HOSTS),
)

_codes = itertools.count(1)
_DEFAULT = object()


def stub_url(prefix: str, host: str = COMPONENTS_HOST) -> str:
    """The `base_url` of a component of the simulation (`prefix` is its behaviour)."""
    return f"http://{host}/{prefix}"


class FakeClock:
    """A clock for the Services: `advance` moves the wall time and the monotonic clock together."""

    def __init__(self, now: datetime = TEST_NOW, monotonic: float = 1000.0) -> None:
        self._now = now
        self._monotonic = monotonic

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds

    def set(self, now: datetime) -> None:
        """Move the wall time only (the monotonic clock never goes back)."""
        self._now = now


def _connect_error(request: httpx.Request, message: str, cause: BaseException) -> httpx.ConnectError:
    error = httpx.ConnectError(message, request=request)
    error.__cause__ = cause
    return error


class FaultTransport(httpx.AsyncBaseTransport):
    """Network failures by host, like the ones httpx raises; any other host goes to `inner`."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "dns-error.test":
            raise _connect_error(request, "getaddrinfo failed", socket.gaierror(11001, "getaddrinfo failed"))
        if host == "refused.test":
            raise _connect_error(request, "refused", ConnectionRefusedError(111, "Connection refused"))
        if host == "tls-error.test":
            raise _connect_error(request, "tls", ssl.SSLCertVerificationError(1, "certificate verify failed"))
        if host == "reset.test":
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=request)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


class HealthConfigHolder:
    """The `HealthConfig` that the application receives; a test may replace any of its values."""

    def __init__(self, config: HealthConfig = TEST_HEALTH_CONFIG) -> None:
        self.config = config

    def replace(self, **changes: Any) -> None:
        self.config = dataclasses.replace(self.config, **changes)


async def insert_component(
    engine: AsyncEngine,
    *,
    code: str | None = None,
    name: str | None = None,
    kind: str = "service",
    base_url: str | None = None,
    live_path: Any = _DEFAULT,
    ready_path: Any = _DEFAULT,
    info_path: Any = _DEFAULT,
    enabled: bool = True,
    sort_order: int = 0,
    deleted_at: datetime | None = None,
    id: UUID | None = None,
) -> UUID:
    """Write a component directly in the database (committed) and return its identifier.

    Without paths, a service gets the three routes of the contract and a frontend `/healthz/`.
    """
    from sqlalchemy import insert

    from src.models.monitored_component import MonitoredComponent

    code = code or f"componente-{next(_codes)}"
    service = kind == "service"
    values: dict[str, Any] = {
        "code": code,
        "name": name or code.replace("-", " ").title(),
        "kind": kind,
        "base_url": base_url or stub_url("healthy"),
        "live_path": ("/health/live" if service else "/healthz/") if live_path is _DEFAULT else live_path,
        "ready_path": ("/health/ready" if service else None) if ready_path is _DEFAULT else ready_path,
        "info_path": ("/info" if service else None) if info_path is _DEFAULT else info_path,
        "enabled": enabled,
        "sort_order": sort_order,
        "deleted_at": deleted_at,
    }
    if id is not None:
        values["id"] = id
    async with engine.begin() as connection:
        result = await connection.execute(
            insert(MonitoredComponent).values(**values).returning(MonitoredComponent.id)
        )
        return result.scalar_one()


def json_answer(status: int, body: Any, latency_ms: int = 5) -> Any:
    """What the probe returns for an answer with a JSON body."""
    from src.integrations.health_probe import ProbeResponse

    return ProbeResponse(status, json.dumps(body).encode(), None, latency_ms)


def failed_answer(code: str, latency_ms: int = 500) -> Any:
    """What the probe returns for a call that failed (`timeout`, `dns_error`…)."""
    from src.integrations.health_probe import ProbeResponse

    return ProbeResponse(None, None, code, latency_ms)


LIVE_OK = {"status": "ok"}
READY_OK = {"status": "ok", "checks": [{"name": "database", "status": "ok", "latency_ms": 3, "error": None}]}
INFO_OK = {
    "service": "otro",
    "version": "1.4.2",
    "commit": "0123456789abcdef",
    "build_date": "2026-10-20T15:30:00-06:00",
    "environment": "e2e",
}


def service_answers(base_url: str, *, live: Any = None, ready: Any = None, info: Any = None) -> dict[str, Any]:
    """The three answers of a service with the routes of the contract (healthy by default)."""
    return {
        f"{base_url}/health/live": live or json_answer(200, LIVE_OK, latency_ms=11),
        f"{base_url}/health/ready": ready or json_answer(200, READY_OK),
        f"{base_url}/info": info or json_answer(200, INFO_OK),
    }


class FakeProbe:
    """Scripted answers by address, for the tests of the Service (no network, no time limits).

    An answer is a `ProbeResponse` or an async function that returns one (or raises). An address
    without an answer gets a 404. Every call is recorded with its kind (`json` or `status`).
    """

    def __init__(self, answers: dict[str, Any] | None = None, *, delay: float = 0.0) -> None:
        self.answers: dict[str, Any] = dict(answers or {})
        self.calls: list[tuple[str, str]] = []
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def get_json(self, url: str) -> Any:
        return await self._answer("json", url)

    async def get_status(self, url: str) -> Any:
        return await self._answer("status", url)

    async def _answer(self, kind: str, url: str) -> Any:
        from src.integrations.health_probe import ProbeResponse

        self.calls.append((kind, url))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            answer = self.answers.get(url)
            if answer is None:
                return ProbeResponse(404, b"{}", None, 1)
            if callable(answer):
                return await answer()
            return answer
        finally:
            self.active -= 1


def make_component(code: str, **values: Any) -> Any:
    """A transient `MonitoredComponent` (not in a database), as the registry reader returns it.

    Its `base_url` is `http://<code>.components.test` unless another is given.
    """
    from src.models.monitored_component import MonitoredComponent

    kind = values.pop("kind", "service")
    service = kind == "service"
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "name": code.replace("-", " ").title(),
        "base_url": f"http://{code}.components.test",
        "live_path": "/health/live" if service else "/healthz/",
        "ready_path": "/health/ready" if service else None,
        "info_path": "/info" if service else None,
        "enabled": True,
        "sort_order": 0,
        "deleted_at": None,
    }
    return MonitoredComponent(code=code, kind=kind, **{**defaults, **values})


async def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Let the event loop run until `condition()` holds (fails after `timeout` seconds)."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


def install_health_overrides(
    app: Any,
    components_app: Any,
    holder: HealthConfigHolder,
    clock: FakeClock | None = None,
) -> httpx.AsyncClient:
    """Point the application at the simulation of components; return the client to close it."""
    from src.dependencies import get_clock, get_health_config, get_health_http_client
    from src.integrations.health_probe import create_health_http_client

    probe_client = create_health_http_client(
        timeout_seconds=holder.config.check_timeout_seconds,
        user_agent="maily-system-api-health/test",
        transport=FaultTransport(httpx.ASGITransport(app=components_app)),
    )

    async def http_client() -> httpx.AsyncClient:
        return probe_client

    async def config() -> HealthConfig:
        return holder.config

    app.dependency_overrides[get_health_http_client] = http_client
    app.dependency_overrides[get_health_config] = config
    if clock is not None:

        async def fake_clock() -> FakeClock:
            return clock

        app.dependency_overrides[get_clock] = fake_clock
    return probe_client


class HealthApi:
    """The application under test with the simulations of the users API and of the components.

    `client` sends `TEST_TOKEN` (registered with the four `health:*`); `anonymous` sends none.
    """

    def __init__(
        self,
        app: Any,
        client: httpx.AsyncClient,
        anonymous: httpx.AsyncClient,
        users_stub: httpx.AsyncClient,
        components_stub: httpx.AsyncClient,
        engine: AsyncEngine,
        clock: FakeClock,
        holder: HealthConfigHolder,
    ) -> None:
        self.app = app
        self.client = client
        self.anonymous = anonymous
        self.users_stub = users_stub
        self.components_stub = components_stub
        self.engine = engine
        self.clock = clock
        self.holder = holder

    async def insert_component(self, **values: Any) -> UUID:
        return await insert_component(self.engine, **values)

    async def component_calls(self) -> list[dict[str, Any]]:
        return (await self.components_stub.get("/__test__/calls")).json()

    async def reset_components(self) -> None:
        response = await self.components_stub.post("/__test__/reset")
        assert response.status_code == 200

    async def set_component_mode(self, prefix: str, mode: str) -> None:
        response = await self.components_stub.post("/__test__/modes", json={"prefix": prefix, "mode": mode})
        assert response.status_code == 200, response.text

    async def grant(self, permissions, token: str = TEST_TOKEN, *, expired: bool = False) -> None:
        await grant(self.users_stub, token, permissions, expired=expired)

    async def users_fault(self, mode: str, count: int = 1, delay: float = 30) -> None:
        response = await self.users_stub.post(
            "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay}
        )
        assert response.status_code == 200

    async def users_calls(self) -> list[dict[str, Any]]:
        return (await self.users_stub.get("/__test__/calls")).json()

    def use(self, dependency: Callable[..., Any], provider: Callable[..., Any]) -> None:
        """Replace a dependency of the application by `provider` (an async function)."""
        self.app.dependency_overrides[dependency] = provider

    def use_value(self, dependency: Callable[..., Any], value: Any) -> None:
        """Replace a dependency of the application by a fixed value."""

        async def provider() -> Any:
            return value

        self.app.dependency_overrides[dependency] = provider

    def set_config(self, **changes: Any) -> None:
        self.holder.replace(**changes)

    async def health(self, **kwargs: Any) -> httpx.Response:
        return await self.client.get("/api/v1/health", **kwargs)

    async def status(self, **kwargs: Any) -> httpx.Response:
        return await self.anonymous.get("/health/status", **kwargs)

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.get(path, **kwargs)

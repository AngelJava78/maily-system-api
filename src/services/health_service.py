"""Business rules of the health of the services (spec 005; research R8 to R10).

One aggregation checks, at the same time, the database, the registry of components and every
registered component that is enabled, and puts the result together: the two integrated components
first (`maily-system-api` and `database`), then the registered ones by `sort_order` and `code`, and
the global status. Several requests of the process share the aggregation in progress and its cached
result (`HealthState`); the cache keeps results, never decisions of permission (the security
dependency runs before this Service on every request).
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from src.config import BuildInfo, HealthConfig
from src.integrations.health_contract import (
    UNKNOWN,
    UNKNOWN_BUILD,
    BuildData,
    CheckResult,
    parse_frontend,
    parse_info,
    parse_live,
    parse_ready,
)
from src.integrations.health_probe import HealthProbeClient, same_origin_url
from src.models.monitored_component import MonitoredComponent
from src.repositories.errors import DatabaseUnavailableError
from src.services.clock import Clock
from src.services.health_schedule import in_window, next_start
from src.services.health_state import CachedResult, HealthState, InFlight

logger = logging.getLogger(__name__)

SELF_CODE = "maily-system-api"
SELF_NAME = "MailySoft System API"
DATABASE_CODE = "database"
DATABASE_NAME = "Base de datos"
# The codes of the integrated components: they cannot be registered (FR-024).
RESERVED_CODES = frozenset({SELF_CODE, DATABASE_CODE})
# What a component that hangs may take beyond the time limit of its calls before it counts as down.
_GUARD_MARGIN_SECONDS = 0.5
# The public status reuses a result for at least this long, also with `HEALTH_CACHE_SECONDS=0`, so
# no number of anonymous requests makes more than one round of checks per period (FR-048).
PUBLIC_MIN_CACHE_SECONDS = 15
# Key of the result of `/health/ready` among the last statuses (no component can have this code).
_READINESS_KEY = "__readiness__"


@dataclass(frozen=True, slots=True)
class ComponentTarget:
    """What is checked of a registered component; also the shape of the copy of the registry."""

    id: UUID
    code: str
    name: str
    kind: str
    base_url: str
    live_path: str
    ready_path: str | None
    info_path: str | None
    sort_order: int

    @classmethod
    def from_model(cls, model: MonitoredComponent) -> ComponentTarget:
        return cls(
            id=model.id,
            code=model.code,
            name=model.name,
            kind=model.kind,
            base_url=model.base_url,
            live_path=model.live_path,
            ready_path=model.ready_path,
            info_path=model.info_path,
            sort_order=model.sort_order,
        )


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """One component of the result, with the thirteen fields of FR-012."""

    code: str
    name: str
    kind: str
    status: str
    latency_ms: int | None
    checked_at: datetime
    version: str
    commit: str
    build_date: str
    environment: str
    checks: tuple[CheckResult, ...]
    error: str | None
    next_start_at: datetime | None


@dataclass(frozen=True, slots=True)
class HealthResult:
    """What an aggregation produces: it is cached and serves both health routes."""

    status: str
    checked_at: datetime
    registry_available: bool
    components: tuple[ComponentHealth, ...]


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    """`/health/ready` of this service: whether the database answered, and its check."""

    ok: bool
    check: CheckResult


@dataclass(frozen=True, slots=True)
class _DatabaseCheck:
    ok: bool
    error: str | None
    latency_ms: int
    checked_at: datetime


class _HasStatus(Protocol):
    status: str


def global_status(components: Iterable[_HasStatus]) -> str:
    """`down` if any is down; otherwise `degraded` if any is degraded, stopped or unknown (FR-017)."""
    statuses = {component.status for component in components}
    if "down" in statuses:
        return "down"
    if statuses & {"degraded", "stopped", "unknown"}:
        return "degraded"
    return "ok"


def _milliseconds_since(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


class HealthService:
    """The health of the platform. The time limits come from `HealthConfig`."""

    def __init__(
        self,
        *,
        state: HealthState,
        config: HealthConfig,
        build: BuildInfo,
        clock: Clock,
        probe: HealthProbeClient,
        read_registry: Callable[[], Awaitable[Sequence[MonitoredComponent]]],
        ping_database: Callable[[], Awaitable[None]],
    ) -> None:
        self._state = state
        self._config = config
        self._build = build
        self._clock = clock
        self._probe = probe
        self._read_registry = read_registry
        self._ping_database = ping_database

    # --- the contract v1 of this service (user story 2) ---

    async def readiness(self) -> ReadinessResult:
        """`/health/ready`: only the database, with `HEALTH_READY_TIMEOUT_SECONDS` (FR-005).

        Simultaneous requests share the query in progress, so a burst on this public route cannot
        take the pool of connections of the other operations; nothing is kept once it finishes. The
        schedule of the database does not count here: without a database the service cannot attend.
        """
        task = self._state.readiness_task
        if task is None:
            task = asyncio.create_task(self._check_readiness())
            self._state.readiness_task = task
        return await asyncio.shield(task)

    async def _check_readiness(self) -> ReadinessResult:
        try:
            database = await self._check_database(self._config.ready_timeout_seconds)
            check = CheckResult("database", "ok" if database.ok else "error", database.latency_ms, database.error)
            self._log_readiness(database)
            return ReadinessResult(database.ok, check)
        finally:
            if self._state.readiness_task is asyncio.current_task():
                self._state.readiness_task = None

    def info(self) -> BuildInfo:
        """`/info`: the build of this process."""
        return self._build

    # --- the shared result ---

    async def health(self) -> HealthResult:
        """`GET /api/v1/health`: reused during `HEALTH_CACHE_SECONDS` (with 0, never finished ones)."""
        return await self.current_result(max_age=self._config.cache_seconds)

    async def public_status(self) -> HealthResult:
        """`GET /health/status`: the same result, reused during `max(HEALTH_CACHE_SECONDS, 15)`.

        It joins any aggregation in progress, also one that started before a change of the registry
        (its result is not kept), so the public route only bounds the checks and never adds rounds.
        """
        max_age = max(self._config.cache_seconds, PUBLIC_MIN_CACHE_SECONDS)
        return await self.current_result(max_age=max_age, accept_stale_in_flight=True)

    async def current_result(self, max_age: float, *, accept_stale_in_flight: bool = False) -> HealthResult:
        """The cached result if it is younger than `max_age`; otherwise the aggregation in progress
        or a new one. There is never more than one aggregation at a time in the process (FR-020).

        An aggregation that started before a change of the registry (another generation) is awaited
        and then another one runs, unless `accept_stale_in_flight` (the public status only bounds the
        checks). The waits are shielded: if the request that started the aggregation goes away, the
        aggregation goes on for the others.
        """
        state = self._state
        while True:
            last = state.last
            if (
                last is not None
                and last.generation == state.generation
                and self._clock.monotonic() - last.completed_at < max_age
            ):
                return last.result
            flight = state.in_flight
            if flight is None:
                generation = state.generation
                flight = InFlight(generation, asyncio.create_task(self._run_aggregation(generation)))
                state.in_flight = flight
            if flight.generation != state.generation and not accept_stale_in_flight:
                await asyncio.shield(flight.task)
                continue
            return await asyncio.shield(flight.task)

    async def _run_aggregation(self, generation: int) -> HealthResult:
        try:
            result = await self._aggregate()
            if generation == self._state.generation:
                self._state.last = CachedResult(result, self._clock.monotonic(), generation)
            return result
        finally:
            flight = self._state.in_flight
            if flight is not None and flight.task is asyncio.current_task():
                self._state.in_flight = None

    # --- one aggregation ---

    async def _aggregate(self) -> HealthResult:
        timeout = self._config.check_timeout_seconds
        database_task = asyncio.create_task(self._check_database(timeout))
        targets, registry_available = await self._registry(timeout)
        ordered = sorted(targets, key=lambda target: (target.sort_order, target.code))
        checks = [asyncio.create_task(self._check_target(target)) for target in ordered]
        database = await database_task
        registered = await asyncio.gather(*checks)
        components = (self._self_component(database), self._database_component(database), *registered)
        self._log_changes(components)
        return HealthResult(
            status=global_status(components),
            checked_at=self._clock.now(),
            registry_available=registry_available,
            components=components,
        )

    async def _registry(self, timeout: float) -> tuple[tuple[ComponentTarget, ...], bool]:
        """The enabled components and whether the registry could be read in this aggregation.

        A good read (also an empty one) replaces the copy of the process; a failed or late one uses
        that copy, or only the integrated components if the registry was never read (research R11).
        The copy keeps its own records, never ORM objects (they would be detached from a session).
        """
        try:
            async with asyncio.timeout(timeout):
                models = await self._read_registry()
            targets = tuple(ComponentTarget.from_model(model) for model in models)
        except Exception as error:
            logger.warning("Registry of monitored components unavailable (%s)", type(error).__name__)
            return self._state.registry_snapshot or (), False
        self._state.registry_snapshot = targets
        return targets, True

    async def _check_database(self, timeout: float) -> _DatabaseCheck:
        started = time.perf_counter()
        error: str | None = None
        try:
            async with asyncio.timeout(timeout):
                await self._ping_database()
        except TimeoutError:
            error = "timeout"
        except DatabaseUnavailableError as failure:
            error = failure.kind
        except Exception:
            error = "unexpected_error"
        return _DatabaseCheck(error is None, error, _milliseconds_since(started), self._clock.now())

    def _self_component(self, database: _DatabaseCheck) -> ComponentHealth:
        """This service, computed inside the process: it never calls itself over HTTP (FR-016)."""
        check = CheckResult("database", "ok" if database.ok else "error", database.latency_ms, database.error)
        return ComponentHealth(
            code=SELF_CODE,
            name=SELF_NAME,
            kind="service",
            status="up" if database.ok else "degraded",
            latency_ms=database.latency_ms,
            checked_at=database.checked_at,
            version=self._build.version,
            commit=self._build.commit,
            build_date=self._build.build_date,
            environment=self._build.environment,
            checks=(check,),
            error=None if database.ok else "not_ready",
            next_start_at=None,
        )

    def _database_component(self, database: _DatabaseCheck) -> ComponentHealth:
        """The database: a failure outside its schedule is `stopped`, with when it starts (FR-033).

        The window is evaluated when the query finished (`checked_at`); a cached result keeps its
        `next_start_at`. Without a schedule, or inside the window, a failure is `down`.
        """
        status = "up" if database.ok else "down"
        next_start_at = None
        schedule = self._config.schedule
        if not database.ok and schedule is not None and not in_window(schedule, database.checked_at):
            status, next_start_at = "stopped", next_start(schedule, database.checked_at)
        return ComponentHealth(
            code=DATABASE_CODE,
            name=DATABASE_NAME,
            kind="database",
            status=status,
            latency_ms=database.latency_ms,
            checked_at=database.checked_at,
            version=UNKNOWN,
            commit=UNKNOWN,
            build_date=UNKNOWN,
            environment=UNKNOWN,
            checks=(),
            error=database.error,
            next_start_at=next_start_at,
        )

    async def _check_target(self, target: ComponentTarget) -> ComponentHealth:
        """One registered component, isolated from the failures of the others (FR-018)."""
        try:
            async with asyncio.timeout(self._config.check_timeout_seconds + _GUARD_MARGIN_SECONDS):
                return await self._evaluate(target)
        except TimeoutError:
            return self._without_answer(target, "down", "timeout")
        except Exception as error:
            # Only the code of the component and the kind of failure: never its address or text.
            logger.error("Health check of component %s failed unexpectedly (%s)", target.code, type(error).__name__)
            return self._without_answer(target, "unknown", "unexpected_error")

    async def _evaluate(self, target: ComponentTarget) -> ComponentHealth:
        host = urlsplit(target.base_url).hostname or ""
        if not self._config.allowed_hosts.allows(host):
            return self._without_answer(target, "unknown", "host_not_allowed", latency=None)
        paths = (target.live_path, target.ready_path, target.info_path)
        urls = [None if path is None else same_origin_url(target.base_url, path) for path in paths]
        if any(url is None for url, path in zip(urls, paths, strict=True) if path is not None):
            return self._without_answer(target, "unknown", "host_not_allowed", latency=None)
        live_url, ready_url, info_url = urls

        if target.kind == "frontend":
            async with asyncio.TaskGroup() as group:
                live = group.create_task(self._probe.get_status(live_url))
                info = group.create_task(self._build_data(info_url))
            outcome = parse_frontend(live.result())
            status = "up" if outcome.ok else "down"
            return self._answered(target, status, outcome.error, live.result().latency_ms, (), info.result())

        async with asyncio.TaskGroup() as group:
            live = group.create_task(self._probe.get_json(live_url))
            ready = group.create_task(self._probe.get_json(ready_url))
            info = group.create_task(self._build_data(info_url))
        live_outcome, ready_outcome = parse_live(live.result()), parse_ready(ready.result())
        if not live_outcome.ok:
            status, error = "down", live_outcome.error
        elif ready_outcome.ok:
            status, error = "up", None
        else:
            status, error = "degraded", ready_outcome.error
        return self._answered(target, status, error, live_outcome.latency_ms, ready_outcome.checks, info.result())

    async def _build_data(self, url: str | None) -> BuildData:
        if url is None:
            return UNKNOWN_BUILD
        return parse_info(await self._probe.get_json(url))

    def _answered(
        self,
        target: ComponentTarget,
        status: str,
        error: str | None,
        latency_ms: int | None,
        checks: tuple[CheckResult, ...],
        build: BuildData,
    ) -> ComponentHealth:
        return ComponentHealth(
            code=target.code,
            name=target.name,
            kind=target.kind,
            status=status,
            latency_ms=latency_ms,
            checked_at=self._clock.now(),
            version=build.version,
            commit=build.commit,
            build_date=build.build_date,
            environment=build.environment,
            checks=checks,
            error=error,
            next_start_at=None,
        )

    def _without_answer(
        self, target: ComponentTarget, status: str, error: str, latency: int | None = None
    ) -> ComponentHealth:
        return self._answered(target, status, error, latency, (), UNKNOWN_BUILD)

    def _log_readiness(self, database: _DatabaseCheck) -> None:
        current = "ok" if database.ok else "error"
        before = self._state.last_statuses.get(_READINESS_KEY)
        if current != before and (before is not None or not database.ok):
            logger.warning("Database readiness changed to %s (%s)", current, database.error or "none")
        self._state.last_statuses[_READINESS_KEY] = current

    def _log_changes(self, components: Iterable[ComponentHealth]) -> None:
        """A warning only when a component changes its status (and the first time, if not up)."""
        previous = self._state.last_statuses
        for component in components:
            before = previous.get(component.code)
            if component.status != before and (before is not None or component.status != "up"):
                logger.warning(
                    "Health of component %s changed to %s (%s)",
                    component.code,
                    component.status,
                    component.error or "none",
                )
            previous[component.code] = component.status

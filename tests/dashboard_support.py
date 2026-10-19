"""Support for the dashboard tests (spec 003): a configurable fake data source and an HTTP helper.

No fixtures here (they live in `conftest.py`, like `tests/helpers.py`). The fake fulfils the port of
`src/integrations/dashboard_source.py`, so the Service and the whole HTTP path are the real ones and
only the data comes from the test.
"""

import asyncio
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from src.integrations.dashboard_source import ClinicCounts, ClinicRecord, ClinicStatusRecord
from src.integrations.errors import DashboardSourceUnavailable
from tests.helpers import TEST_TOKEN, grant

DASHBOARD_URL = "/api/v1/dashboard"

# The five queries of the port (also the names that `fail` and `crash` accept).
QUERIES = ("clinic_counts", "recent_clinics", "doctors_total", "patients_total", "users_total")

# Internal detail that a failing source carries as the cause of its error; it must never reach a
# client or a log.
LEAK_MARKER = "SECRETO-INTERNO http://interno:9000"

_STATUS_NAMES = {1: "Activa", 2: "En prueba", 3: "Suspendida"}


def make_clinic(
    n: int,
    *,
    created_at: datetime | None = None,
    status_id: int = 1,
    name: str | None = None,
) -> ClinicRecord:
    """A clinic whose id is derived from `n`; by default the higher `n`, the newer the clinic."""
    return ClinicRecord(
        id=UUID(f"00000000-0000-4000-8000-{n:012x}"),
        name=name or f"Clínica {n}",
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=n),
        status=ClinicStatusRecord(status_id, _STATUS_NAMES.get(status_id, "Otro")),
    )


def newest_first(clinics: Iterable[ClinicRecord]) -> list[ClinicRecord]:
    """The order of the contract: newest first and, for the same instant, `id` ascending."""
    return sorted(sorted(clinics, key=lambda c: c.id), key=lambda c: c.created_at, reverse=True)


class FakeDashboardSource:
    """Double of a `DashboardSource`: answers what the test configures and records every call.

    - `counts` defaults to the totals derived from `clinics` (statuses 1 and 2 are the active and
      the trial ones).
    - Queries named in `fail` raise `DashboardSourceUnavailable` (chained to an error that carries
      `LEAK_MARKER`); the ones in `crash` raise a `RuntimeError`, which is a programming error.
    - With `honor_order=False`, `recent_clinics` returns the list as it was given, neither sorted nor
      cut, to prove that the Service does both itself.
    - With a `barrier`, every query waits for it before answering: they only finish if they run at
      the same time.
    """

    def __init__(
        self,
        *,
        clinics: Sequence[ClinicRecord] = (),
        counts: ClinicCounts | None = None,
        doctors: int = 0,
        patients: int = 0,
        users: int = 0,
        fail: Iterable[str] = (),
        crash: Iterable[str] = (),
        honor_order: bool = True,
        is_dummy: bool = False,
        barrier: asyncio.Barrier | None = None,
    ) -> None:
        self.clinics = list(clinics)
        self.doctors = doctors
        self.patients = patients
        self.users = users
        self.fail = set(fail)
        self.crash = set(crash)
        self.honor_order = honor_order
        self.is_dummy = is_dummy
        self.barrier = barrier
        self._counts = counts
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def _enter(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self.barrier is not None:
            await self.barrier.wait()
        if name in self.crash:
            raise RuntimeError("boom")
        if name in self.fail:
            raise DashboardSourceUnavailable() from RuntimeError(LEAK_MARKER)

    def called(self, name: str) -> list[tuple[Any, ...]]:
        """The arguments of every call to the query `name`."""
        return [args for called_name, args in self.calls if called_name == name]

    async def clinic_counts(self, token: str) -> ClinicCounts:
        await self._enter("clinic_counts", token)
        if self._counts is not None:
            return self._counts
        return ClinicCounts(
            total=len(self.clinics),
            active=sum(1 for c in self.clinics if c.status.id == 1),
            trial=sum(1 for c in self.clinics if c.status.id == 2),
        )

    async def recent_clinics(self, token: str, limit: int) -> list[ClinicRecord]:
        await self._enter("recent_clinics", token, limit)
        if not self.honor_order:
            return list(self.clinics)
        return newest_first(self.clinics)[:limit]

    async def doctors_total(self, token: str) -> int:
        await self._enter("doctors_total", token)
        return self.doctors

    async def patients_total(self, token: str) -> int:
        await self._enter("patients_total", token)
        return self.patients

    async def users_total(self, token: str) -> int:
        await self._enter("users_total", token)
        return self.users


class DashboardApi:
    """The application under test with the users API simulated, ready to be called over HTTP.

    `client` sends `TEST_TOKEN`; `anonymous` sends no token. The data source is the real dummy one
    until a test replaces it with `use_source`. There is no database: the dashboard does not use it.
    """

    def __init__(
        self,
        app: Any,
        client: httpx.AsyncClient,
        anonymous: httpx.AsyncClient,
        users_stub: httpx.AsyncClient,
    ) -> None:
        self.app = app
        self.client = client
        self.anonymous = anonymous
        self.users_stub = users_stub

    def use_source(self, source: Any) -> None:
        from src.dependencies import get_dashboard_source

        async def provider() -> Any:
            return source

        self.app.dependency_overrides[get_dashboard_source] = provider

    async def get(self, query: str = "", **kwargs: Any) -> httpx.Response:
        return await self.client.get(DASHBOARD_URL + query, **kwargs)

    async def set_permissions(self, permissions: Iterable[str]) -> None:
        await grant(self.users_stub, TEST_TOKEN, permissions)

    async def grant_token(
        self, token: str, permissions: Iterable[str], *, expired: bool = False
    ) -> None:
        await grant(self.users_stub, token, permissions, expired=expired)

    async def users_fault(self, mode: str, count: int = 1, delay: float = 30) -> None:
        response = await self.users_stub.post(
            "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay}
        )
        assert response.status_code == 200

    async def users_calls(self) -> list[dict[str, Any]]:
        return (await self.users_stub.get("/__test__/calls")).json()

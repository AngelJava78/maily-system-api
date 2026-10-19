"""Port of the data sources of the platform dashboard (spec 003, contracts/data-sources.md).

The dashboard owns no data: the clinics, doctors, patients and users belong to other MailySoft APIs.
`DashboardService` talks to whatever fulfils `DashboardSource`; today that is the dummy source of
phase 1, and when the real APIs exist only the object that fulfils the port changes.

This module only uses the standard library (an integration must not know FastAPI, the DTOs or the
database). The records carry exactly the fields of the published contract and no personal data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClinicStatusRecord:
    """Status of a clinic, taken from the (foreign) catalog of clinic statuses."""

    id: int
    name: str


@dataclass(frozen=True, slots=True)
class ClinicRecord:
    """Basic data of a clinic. `created_at` MUST carry a time zone: the Service sorts by it."""

    id: UUID
    name: str
    created_at: datetime
    status: ClinicStatusRecord


@dataclass(frozen=True, slots=True)
class ClinicCounts:
    """Clinics of the whole platform. `active` and `trial` do not overlap: `active + trial <= total`."""

    total: int
    active: int
    trial: int


class DashboardSource(Protocol):
    """Where the dashboard gets its data. Every query is independent of the others.

    Contract of the implementations:

    - `recent_clinics` returns AT MOST `limit` clinics (the Service asks for 1 to 10), newest first
      by `created_at` and, for the same instant, by `id` ascending. The source does the cut, so
      the tie-break decides which clinic gets in.
    - `users_total >= doctors_total`: every doctor is a user, patients are not.
    - A query that cannot be answered (no response, time out, anything unexpected) raises
      `DashboardSourceUnavailable`, with a generic message that never includes addresses, error
      bodies or credentials. Any other exception is a programming error.
    - "There is nothing" is an answer (`0` or `[]`), not a failure.
    - `token` is the token of the person as it arrived. A real source forwards it and never logs it.
    """

    is_dummy: bool  # True only for the fictitious source of phase 1 (it triggers the start-up notice)

    async def clinic_counts(self, token: str) -> ClinicCounts: ...

    async def recent_clinics(self, token: str, limit: int) -> list[ClinicRecord]: ...

    async def doctors_total(self, token: str) -> int: ...

    async def patients_total(self, token: str) -> int: ...

    async def users_total(self, token: str) -> int: ...

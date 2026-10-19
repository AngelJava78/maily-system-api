"""Business rules of the platform dashboard (spec 003).

The dashboard owns no data: it asks five independent queries to a `DashboardSource` and puts the
answers together. This Service decides how many recent clinics are shown and in which order, and
what happens when a source fails: only its own values become `None` (`null` in the response), never
a made-up zero, and the rest of the dashboard is still returned (principle IX).
"""

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass

from src.integrations.dashboard_source import ClinicRecord, DashboardSource
from src.integrations.errors import DashboardSourceUnavailable

logger = logging.getLogger(__name__)

# The most recent clinics the dashboard ever shows. Fixed on purpose: it is not configurable.
MAX_RECENT_CLINICS = 10


@dataclass(frozen=True, slots=True)
class DashboardView:
    """The summary of the platform, as the Service builds it.

    Each field is `None` when its data source failed (never a made-up zero or empty list); a `0`
    or an empty list only means that the source answered there is nothing.
    """

    total_clinics: int | None
    active_clinics: int | None
    trial_clinics: int | None
    total_doctors: int | None
    total_patients: int | None
    total_users: int | None
    recent_clinics: list[ClinicRecord] | None


def _newest_first(clinics: list[ClinicRecord]) -> list[ClinicRecord]:
    """Newest first by `created_at` and, for the same instant, by `id` ascending (FR-015).

    The sort is stable and `reverse=True` keeps the order of equal elements, so the order by id of
    the first pass survives the second one.
    """
    by_id = sorted(clinics, key=lambda clinic: clinic.id)
    return sorted(by_id, key=lambda clinic: clinic.created_at, reverse=True)


class DashboardService:
    """Builds the dashboard from the data source; the default quantity comes from the configuration."""

    def __init__(self, source: DashboardSource, default_limit: int) -> None:
        self._source = source
        self._default_limit = default_limit

    def _effective_limit(self, requested_limit: int | None) -> int:
        """How many recent clinics to show: the request, never above the maximum, or the default."""
        if requested_limit is None:
            return self._default_limit
        if requested_limit < 1:
            # The Router rejects it with a 422 before it gets here.
            raise ValueError("requested_limit must be at least 1")
        return min(requested_limit, MAX_RECENT_CLINICS)

    @staticmethod
    async def _guarded[T](name: str, query: Awaitable[T]) -> T | None:
        """The answer of a query, or `None` if its source is unavailable.

        Only `DashboardSourceUnavailable` is a failure of the source; any other exception is a
        programming error and is not hidden. The log names the query and nothing else: no token,
        no address and no detail of the source (principles VIII and IX).
        """
        try:
            return await query
        except DashboardSourceUnavailable:
            logger.warning("Dashboard source unavailable: %s", name)
            return None

    async def get(self, token: str, requested_limit: int | None = None) -> DashboardView:
        """The summary of the platform. The five queries run at the same time.

        `requested_limit` is the `limit` of the person, already known to be an integer of at
        least 1 (`None` when none was sent): more than `MAX_RECENT_CLINICS` is not an error, it is
        capped. The Service sorts and cuts the recent clinics itself, so the rule does not depend on
        every source getting the order right. A source that fails leaves only its own values as
        `None`. Nothing is kept between requests.
        """
        limit = self._effective_limit(requested_limit)
        counts, recent, doctors, patients, users = await asyncio.gather(
            self._guarded("clinic_counts", self._source.clinic_counts(token)),
            self._guarded("recent_clinics", self._source.recent_clinics(token, limit)),
            self._guarded("doctors_total", self._source.doctors_total(token)),
            self._guarded("patients_total", self._source.patients_total(token)),
            self._guarded("users_total", self._source.users_total(token)),
        )
        return DashboardView(
            total_clinics=None if counts is None else counts.total,
            active_clinics=None if counts is None else counts.active,
            trial_clinics=None if counts is None else counts.trial,
            total_doctors=doctors,
            total_patients=patients,
            total_users=users,
            recent_clinics=None if recent is None else _newest_first(recent)[:limit],
        )

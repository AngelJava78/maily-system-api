"""Client of the clinics API: how many clinics have each subscription, and (ampliación,
spec 010-cobro-real-suscripciones) which clinic/plan/cycle a clinic subscription is.

Contracts (proposals of this repository, Clinics does not exist yet as a real service):
`specs/001-subscriptions-api/contracts/clinics-api-integration.md` (counts) and
`specs/010-cobro-real-suscripciones/contracts/clinics-api-integration.md` (clinic subscriptions).
Both kinds of data belong to another system: read on every use, never stored. Anything that is not
exactly the expected answer is "unavailable" (or, for a clinic subscription, "not found") and never
invented; the caller decides how to degrade or react.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from src.integrations.errors import ClinicsApiNotFound, ClinicsApiUnavailable

logger = logging.getLogger(__name__)

COUNTS_PATH = "/api/v1/clinics/subscription-counts"
CLINIC_SUBSCRIPTIONS_PATH = "/api/v1/clinics/clinic-subscriptions"
_BILLING_CYCLES = ("monthly", "annual")


@dataclass(frozen=True, slots=True)
class ClinicSubscriptionInfo:
    """What Clinics reports about one clinic subscription (research R6): only what this service
    needs to charge it. Never persisted; read fresh on every charge (Principle IX)."""

    tenant_id: str
    subscription_id: int
    billing_cycle: str


class ClinicsApiClient:
    def __init__(
        self, http_client: httpx.AsyncClient, base_url: str, timeout_seconds: float
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def get_counts(
        self, token: str, subscription_ids: Sequence[int] | None = None
    ) -> dict[int, int]:
        """Clinics per subscription, only for the ones that have at least one.

        Without `subscription_ids` it answers for every subscription; with them, only for those. A
        subscription that does not appear has no clinics (the API answered, so the zero is true).
        Raises `ClinicsApiUnavailable` for any failure or unexpected answer.
        """
        requested = None if subscription_ids is None else list(subscription_ids)
        if requested is not None and not requested:
            return {}
        params = [("subscription_id", i) for i in requested] if requested else None

        try:
            # The time limit covers the whole call; `httpx` only limits each phase separately.
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    f"{self._base_url}{COUNTS_PATH}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.HTTPError, TimeoutError) as error:
            # Only the kind of failure is logged: never the token, the address or the body.
            logger.warning("Clinics API request failed (%s)", type(error).__name__)
            raise ClinicsApiUnavailable from None

        if response.status_code != 200:
            logger.warning("Clinics API unavailable (status %s)", response.status_code)
            raise ClinicsApiUnavailable

        try:
            data = response.json()
        except ValueError:
            logger.warning("Clinics API answered a body that is not JSON")
            raise ClinicsApiUnavailable from None
        return self._parse(data, requested)

    @staticmethod
    def _parse(data: object, requested: list[int] | None) -> dict[int, int]:
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            logger.warning("Clinics API answered an unexpected body")
            raise ClinicsApiUnavailable

        counts: dict[int, int] = {}
        for item in items:
            if not isinstance(item, dict):
                raise ClinicsApiUnavailable
            subscription_id = item.get("subscription_id")
            count = item.get("clinics_count")
            # `bool` is an `int` in Python: exclude it explicitly.
            valid = (
                type(subscription_id) is int
                and subscription_id >= 1
                and type(count) is int
                and count >= 1
                and subscription_id not in counts
                and (requested is None or subscription_id in requested)
            )
            if not valid:
                logger.warning("Clinics API answered an unexpected item")
                raise ClinicsApiUnavailable
            counts[subscription_id] = count
        return counts

    async def get_clinic_subscription(
        self, token: str, clinic_subscription_id: str
    ) -> ClinicSubscriptionInfo:
        """The clinic/plan/cycle of one clinic subscription (research R6), as reported by Clinics.

        Raises `ClinicsApiNotFound` when it does not exist, is cancelled, or belongs to another
        organization than `token`'s (indistinguishable, FR-003), and `ClinicsApiUnavailable` for
        any other failure or unexpected answer (fail closed, this is the core of a write).
        """
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    f"{self._base_url}{CLINIC_SUBSCRIPTIONS_PATH}/{clinic_subscription_id}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("Clinics API clinic-subscription request failed (%s)", type(error).__name__)
            raise ClinicsApiUnavailable from None

        if response.status_code == 404:
            raise ClinicsApiNotFound
        if response.status_code != 200:
            logger.warning(
                "Clinics API unavailable for clinic-subscription (status %s)", response.status_code
            )
            raise ClinicsApiUnavailable

        try:
            data = response.json()
        except ValueError:
            logger.warning("Clinics API answered a body that is not JSON for clinic-subscription")
            raise ClinicsApiUnavailable from None
        return self._parse_clinic_subscription(data)

    @staticmethod
    def _parse_clinic_subscription(data: object) -> ClinicSubscriptionInfo:
        if not isinstance(data, dict):
            raise ClinicsApiUnavailable
        tenant_id, subscription_id, billing_cycle = (
            data.get("tenant_id"),
            data.get("subscription_id"),
            data.get("billing_cycle"),
        )
        valid = (
            isinstance(tenant_id, str)
            and type(subscription_id) is int
            and subscription_id >= 1
            and billing_cycle in _BILLING_CYCLES
        )
        if not valid:
            logger.warning("Clinics API answered an unexpected clinic-subscription body")
            raise ClinicsApiUnavailable
        return ClinicSubscriptionInfo(
            tenant_id=tenant_id, subscription_id=subscription_id, billing_cycle=billing_cycle
        )

"""Client of the clinics API: how many clinics have each subscription, and the organization of a person.

Contracts: `specs/001-subscriptions-api/contracts/clinics-api-integration.md` (the count, a proposal of
this repository) and `specs/010-subscription-periods/contracts/clinics-api-integration.md` (the
organization: its plan, its billing period and its creation). What the clinics API owns is read on every
use and never stored. Anything that is not exactly the expected answer is "unavailable" and never a
made-up value; the caller decides how to degrade.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx

from src.integrations.errors import ClinicsApiUnavailable, OrganizationNotFound

logger = logging.getLogger(__name__)

COUNTS_PATH = "/api/v1/clinics/subscription-counts"
ORGANIZATIONS_PATH = "/api/v1/organizations"
BILLING_PERIODS = ("monthly", "annual")


@dataclass(frozen=True, slots=True)
class OrganizationRecord:
    """The four things that the subscription periods take from an organization (spec 010, FR-003).

    `created_at` is aware and in UTC. `billing_period` is `monthly` or `annual`: the clinics API stores
    it but does not publish it yet, so an answer without it is "unavailable" (never a default).
    """

    id: UUID
    subscription_id: int
    billing_period: str
    created_at: datetime


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

    async def get_organization(self, token: str, organization_id: UUID) -> OrganizationRecord:
        """The organization that the person of `token` is the owner of (spec 010, research R9).

        The clinics API only lets the owner of an organization read it, so a valid answer proves that the
        person is its owner. Raises `OrganizationNotFound` only for a 404 with the code `not_found` (the
        organization does not exist or is not the person's own: the API does not tell them apart) and
        `ClinicsApiUnavailable` for anything else that is not exactly the expected answer.
        """
        try:
            # The time limit covers the whole call; `httpx` only limits each phase separately.
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    f"{self._base_url}{ORGANIZATIONS_PATH}/{organization_id}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.HTTPError, TimeoutError) as error:
            # Only the kind of failure is logged: never the token, the address or the body.
            logger.warning("Clinics API request failed (%s)", type(error).__name__)
            raise ClinicsApiUnavailable from None

        if response.status_code == 404 and self._says_not_found(response):
            raise OrganizationNotFound
        if response.status_code != 200:
            logger.warning("Clinics API unavailable (status %s)", response.status_code)
            raise ClinicsApiUnavailable

        try:
            data = response.json()
        except ValueError:
            logger.warning("Clinics API answered a body that is not JSON")
            raise ClinicsApiUnavailable from None
        return self._parse_organization(data, organization_id)

    @staticmethod
    def _says_not_found(response: httpx.Response) -> bool:
        """Whether a 404 is «that organization is not there»: only the code `not_found` says so."""
        try:
            body = response.json()
        except ValueError:
            return False
        return isinstance(body, dict) and body.get("code") == "not_found"

    @staticmethod
    def _parse_organization(data: object, organization_id: UUID) -> OrganizationRecord:
        unavailable = ClinicsApiUnavailable()
        if not isinstance(data, dict):
            logger.warning("Clinics API answered an unexpected body")
            raise unavailable

        identifier = data.get("id")
        subscription_id = data.get("subscription_id")
        billing_period = data.get("billing_period")
        created_at_text = data.get("created_at")
        try:
            answered_id = UUID(identifier) if isinstance(identifier, str) else None
            created_at = (
                datetime.fromisoformat(created_at_text) if isinstance(created_at_text, str) else None
            )
        except ValueError:
            answered_id = created_at = None

        # `bool` is an `int` in Python: exclude it explicitly.
        valid = (
            answered_id == organization_id
            and type(subscription_id) is int
            and subscription_id >= 1
            and billing_period in BILLING_PERIODS
            and created_at is not None
            and created_at.utcoffset() is not None
        )
        if not valid:
            logger.warning("Clinics API answered an unexpected organization")
            raise unavailable
        return OrganizationRecord(
            id=organization_id,
            subscription_id=subscription_id,
            billing_period=billing_period,
            created_at=created_at.astimezone(UTC),
        )

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

import asyncio
import logging
from dataclasses import dataclass

from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.exceptions import (
    ClinicsCheckUnavailableError,
    SubscriptionHasClinicsError,
    SubscriptionNameAlreadyExistsError,
    SubscriptionNotFoundError,
    SubscriptionStatusUnchangedError,
)
from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.errors import ClinicsApiUnavailable
from src.models.subscription import SUBSCRIPTION_NAME_INDEX, Subscription
from src.repositories.errors import UniqueViolationError
from src.repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    """A subscription together with the clinics count that belongs to another system.

    `clinics_count` is `None` when it is not available (never a made-up zero).
    """

    subscription: Subscription
    clinics_count: int | None


class SubscriptionService:
    """Business rules of the subscriptions. Receives validated DTOs and returns views."""

    def __init__(
        self, repository: SubscriptionRepository, clinics_api: ClinicsApiClient
    ) -> None:
        self._repository = repository
        self._clinics_api = clinics_api

    async def _fetch_counts(self, token: str, ids: list[int] | None) -> dict[int, int] | None:
        """The clinics per subscription, or `None` when the clinics API cannot answer.

        Reads never depend on the clinics API (principle IX): the caller shows the count as not
        available instead of failing.
        """
        try:
            return await self._clinics_api.get_counts(token, ids)
        except ClinicsApiUnavailable:
            logger.warning("Clinics count unavailable")
            return None

    async def list(self, token: str) -> list[SubscriptionView]:
        """Every current subscription with its clinics count.

        The database and the clinics API are asked at the same time: the question to the clinics
        API has no filter, so it does not depend on the ids that the database returns.
        """
        subscriptions, counts = await asyncio.gather(
            self._repository.list_current(), self._fetch_counts(token, None)
        )
        return [
            SubscriptionView(s, None if counts is None else counts.get(s.id, 0))
            for s in subscriptions
        ]

    async def create(self, data: SubscriptionCreate) -> SubscriptionView:
        """Create an active subscription. The name is not checked beforehand: the database decides.

        Checking first would leave a race between two requests with the same name (research R11).
        The clinics count is a true zero without asking the clinics API: a subscription that was
        just created cannot have clinics yet (research R6).
        """
        try:
            subscription = await self._repository.create(
                data.name, data.description, data.monthly_price, data.features
            )
        except UniqueViolationError as error:
            if error.constraint_name == SUBSCRIPTION_NAME_INDEX:
                raise SubscriptionNameAlreadyExistsError(data.name) from error
            raise
        return SubscriptionView(subscription, 0)

    async def get(self, subscription_id: int, token: str) -> SubscriptionView:
        """A current subscription with its clinics count.

        The database is read first so a missing or deleted subscription is answered without
        bothering the clinics API.
        """
        subscription = await self._repository.get_current_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        counts = await self._fetch_counts(token, [subscription_id])
        return SubscriptionView(
            subscription, None if counts is None else counts.get(subscription_id, 0)
        )

    async def update(
        self, subscription_id: int, data: SubscriptionUpdate, token: str
    ) -> SubscriptionView:
        """Apply only the fields that were sent; the database decides the name conflicts."""
        changes = data.model_dump(exclude_unset=True)  # a description sent as null is kept
        try:
            subscription = await self._repository.update(subscription_id, changes)
        except UniqueViolationError as error:
            if error.constraint_name == SUBSCRIPTION_NAME_INDEX:
                raise SubscriptionNameAlreadyExistsError(changes["name"]) from error
            raise
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        counts = await self._fetch_counts(token, [subscription_id])
        return SubscriptionView(
            subscription, None if counts is None else counts.get(subscription_id, 0)
        )

    async def change_status(
        self, subscription_id: int, data: SubscriptionStatusChange, token: str
    ) -> SubscriptionView:
        """Move a current subscription to Active, Inactive or Blocked, with or without clinics.

        There is no read beforehand: one atomic write decides, so with simultaneous requests only
        one wins. If it did not apply, one read tells why: missing or deleted (not found) or it
        already had that status (conflict). The clinics API is never asked to decide; it is only
        asked afterwards to fill the answer.
        """
        target = data.status_id
        current = None
        for _ in range(2):  # repeated once if another request changed the status in between
            subscription = await self._repository.change_status(subscription_id, target)
            if subscription is not None:
                counts = await self._fetch_counts(token, [subscription_id])
                return SubscriptionView(
                    subscription, None if counts is None else counts.get(subscription_id, 0)
                )
            current = await self._repository.get_current_by_id(subscription_id)
            if current is None:
                raise SubscriptionNotFoundError(subscription_id)
            if current.status_id == target:
                break
        raise SubscriptionStatusUnchangedError(subscription_id, current.status.name)

    async def delete(self, subscription_id: int, token: str) -> None:
        """Soft delete a current subscription that has no clinics.

        Unlike the reads, this does not degrade: deleting is destructive, so if the clinics API
        cannot confirm that the subscription has no clinics, nothing is deleted (principle IX). No
        transaction stays open while the clinics API is asked.
        """
        if await self._repository.get_current_by_id(subscription_id) is None:
            raise SubscriptionNotFoundError(subscription_id)
        try:
            counts = await self._clinics_api.get_counts(token, [subscription_id])
        except ClinicsApiUnavailable:
            raise ClinicsCheckUnavailableError(subscription_id) from None
        if counts.get(subscription_id, 0) >= 1:
            raise SubscriptionHasClinicsError(subscription_id)
        if not await self._repository.soft_delete(subscription_id):
            raise SubscriptionNotFoundError(subscription_id)  # another request deleted it first

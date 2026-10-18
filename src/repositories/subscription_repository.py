from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.subscription import Subscription
from src.models.subscription_status import SubscriptionStatus
from src.repositories import INT4_MAX
from src.repositories.transactions import execute_and_commit


class SubscriptionRepository:
    """All the persistence of the subscriptions: the only layer that builds queries over them.

    Every read loads the status together with the subscription (`SubscriptionRead` always includes
    it and the relationship is `lazy="raise"`). A subscription is "current" when its status is
    not Deleted: a status added by hand counts as current.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _select_with_status() -> Select[tuple[Subscription]]:
        return select(Subscription).options(joinedload(Subscription.status))

    async def list_current(self) -> list[Subscription]:
        """Every current subscription, oldest first (creation date, then id)."""
        statement = (
            self._select_with_status()
            .where(Subscription.status_id != SubscriptionStatus.DELETED)
            .order_by(Subscription.created_at, Subscription.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def create(
        self, name: str, description: str | None, monthly_price: Decimal, features: list[str]
    ) -> Subscription:
        """Insert an active subscription and commit (the unique index decides name conflicts).

        A repeated name raises `UniqueViolationError`; any other failure is re-raised as it is.
        """
        statement = (
            insert(Subscription)
            .values(
                name=name,
                description=description,
                monthly_price=monthly_price,
                features=features,
            )
            .returning(Subscription.id)
        )
        subscription_id = await execute_and_commit(self._session, statement)
        if subscription_id is None:  # an INSERT always returns its row
            raise RuntimeError("The INSERT of the subscription returned no row")
        return await self._reload(subscription_id)

    async def _reload(self, subscription_id: int) -> Subscription:
        """Read a subscription with its status, refreshing any instance the session already holds.

        What a client sees is what the database stored (for instance the price with two decimals).
        """
        statement = (
            self._select_with_status()
            .where(Subscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def get_current_by_id(self, subscription_id: int) -> Subscription | None:
        """The current subscription with that identifier, or `None` (also for one that cannot exist)."""
        if subscription_id > INT4_MAX:
            return None
        statement = self._select_with_status().where(
            Subscription.id == subscription_id,
            Subscription.status_id != SubscriptionStatus.DELETED,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def update(
        self, subscription_id: int, changes: Mapping[str, Any]
    ) -> Subscription | None:
        """Apply `changes` to a current subscription and commit.

        Returns the updated subscription, or `None` if there is no current subscription with that
        identifier. Renaming to the subscription's own name does not clash: the index compares with
        other rows. The trigger of the table moves `updated_at`.
        """
        if subscription_id > INT4_MAX:
            return None
        statement = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.status_id != SubscriptionStatus.DELETED,
            )
            .values(**changes)
            .returning(Subscription.id)
        )
        if await execute_and_commit(self._session, statement) is None:
            return None
        return await self._reload(subscription_id)

    async def change_status(self, subscription_id: int, to_status_id: int) -> Subscription | None:
        """Move a current subscription to `to_status_id` with one atomic statement.

        Returns the subscription with its new status, or `None` when there is no current
        subscription with that identifier or it already has that status (nothing changes). With
        simultaneous requests only one finds the row in the old status.
        """
        if subscription_id > INT4_MAX:
            return None
        statement = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.status_id != SubscriptionStatus.DELETED,
                Subscription.status_id != to_status_id,
            )
            .values(status_id=to_status_id)
            .returning(Subscription.id)
        )
        if await execute_and_commit(self._session, statement) is None:
            return None
        return await self._reload(subscription_id)

    async def get_status_id(self, subscription_id: int) -> int | None:
        """The status of any subscription, deleted or not, or `None` if it does not exist."""
        if subscription_id > INT4_MAX:
            return None
        statement = select(Subscription.status_id).where(Subscription.id == subscription_id)
        return (await self._session.scalars(statement)).one_or_none()

    async def soft_delete(self, subscription_id: int) -> bool:
        """Mark a current subscription as deleted (status 4); no row is removed.

        Returns `False` when there is no current subscription with that identifier. The condition on
        the status makes the change atomic: with simultaneous requests only one finds it.
        """
        if subscription_id > INT4_MAX:
            return False
        statement = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.status_id != SubscriptionStatus.DELETED,
            )
            .values(status_id=SubscriptionStatus.DELETED)
            .returning(Subscription.id)
        )
        return await execute_and_commit(self._session, statement) is not None

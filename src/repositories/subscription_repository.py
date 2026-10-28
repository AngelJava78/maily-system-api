from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.models.subscription import Subscription
from src.models.subscription_module import SubscriptionModule
from src.models.subscription_status import SubscriptionStatus
from src.models.subscription_type import SubscriptionType
from src.repositories import INT4_MAX
from src.repositories.transactions import execute_and_commit

# Sentinel distinguishing "module_keys was not in changes" from an explicit `[]` (update()).
_UNSET = object()


class SubscriptionRepository:
    """All the persistence of the subscriptions: the only layer that builds queries over them.

    Every read loads the status and the type together with the subscription (`SubscriptionRead`
    always includes both and the relationships are `lazy="raise"`). A subscription is "current"
    when its status is not Deleted: a status added by hand counts as current.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _select_with_relations() -> Select[tuple[Subscription]]:
        return select(Subscription).options(
            joinedload(Subscription.status),
            joinedload(Subscription.subscription_type),
            selectinload(Subscription.modules),
        )

    async def list_current(self) -> list[Subscription]:
        """Every current subscription, oldest first (creation date, then id)."""
        statement = (
            self._select_with_relations()
            .where(Subscription.status_id != SubscriptionStatus.DELETED)
            .order_by(Subscription.created_at, Subscription.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def create(
        self,
        name: str,
        description: str | None,
        monthly_price: Decimal,
        *,
        subscription_type_id: int,
        annual_price: Decimal,
        trial_days: int,
        self_service: bool,
        module_keys: list[str],
        other_features: list[str],
        consulting_rooms_limit: int,
        doctors_limit: int,
        assistants_limit: int,
        new_patients_per_year_limit: int,
        clinics_limit: int,
    ) -> Subscription:
        """Insert an active subscription and commit (the unique index decides name conflicts).

        `module_keys` MUST already be the final, validated set (including 'patients'); this layer
        does not know about modules, only persists what the Service already resolved.
        A repeated name raises `UniqueViolationError`; a `subscription_type_id` that does not
        exist in `subscription_types` raises `ForeignKeyViolationError`; any other failure is
        re-raised as it is.
        """
        statement = (
            insert(Subscription)
            .values(
                name=name,
                description=description,
                subscription_type_id=subscription_type_id,
                monthly_price=monthly_price,
                annual_price=annual_price,
                trial_days=trial_days,
                self_service=self_service,
                other_features=other_features,
                consulting_rooms_limit=consulting_rooms_limit,
                doctors_limit=doctors_limit,
                assistants_limit=assistants_limit,
                new_patients_per_year_limit=new_patients_per_year_limit,
                clinics_limit=clinics_limit,
            )
            .returning(Subscription.id)
        )
        subscription_id = await execute_and_commit(
            self._session,
            statement,
            then=lambda new_id: [
                insert(SubscriptionModule).values(
                    [{"subscription_id": new_id, "module_key": key} for key in module_keys]
                )
            ],
        )
        if subscription_id is None:  # an INSERT always returns its row
            raise RuntimeError("The INSERT of the subscription returned no row")
        return await self._reload(subscription_id)

    async def _reload(self, subscription_id: int) -> Subscription:
        """Read a subscription with its status, refreshing any instance the session already holds.

        What a client sees is what the database stored (for instance the price with two decimals).
        """
        statement = (
            self._select_with_relations()
            .where(Subscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def get_current_by_id(self, subscription_id: int) -> Subscription | None:
        """The current subscription with that identifier, or `None` (also for one that cannot exist)."""
        if subscription_id > INT4_MAX:
            return None
        statement = self._select_with_relations().where(
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
        changes = dict(changes)
        module_keys = changes.pop("module_keys", _UNSET)
        statement = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.status_id != SubscriptionStatus.DELETED,
            )
            # `.values()` cannot build a SET-less UPDATE: if module_keys was the only change, fall
            # back to a no-op self-assignment so the existence/status check and the updated_at
            # trigger still run (spec 008 research R8).
            .values(**changes if changes else {"id": Subscription.id})
            .returning(Subscription.id)
        )

        def replace_modules(new_id: int) -> list[Any]:
            return [
                delete(SubscriptionModule).where(SubscriptionModule.subscription_id == new_id),
                insert(SubscriptionModule).values(
                    [{"subscription_id": new_id, "module_key": key} for key in module_keys]
                ),
            ]

        then = replace_modules if module_keys is not _UNSET else None
        if await execute_and_commit(self._session, statement, then=then) is None:
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

    async def mark_enterprise(self, ids: Sequence[int]) -> int:
        """Set `subscription_type_id = SubscriptionType.ENTERPRISE` for exactly these ids (FR-009,
        research R7).

        No status condition: a deleted subscription is reached too (defensive; by construction it
        should already have no clinics). Returns how many rows changed; an empty `ids` is a no-op
        (not even a statement is sent).
        """
        if not ids:
            return 0
        statement = (
            update(Subscription)
            .where(Subscription.id.in_(ids))
            .values(subscription_type_id=SubscriptionType.ENTERPRISE)
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return result.rowcount

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

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.monitored_component import MonitoredComponent
from src.repositories.transactions import execute_and_commit


class MonitoredComponentRepository:
    """All the persistence of the registry of monitored components (spec 005).

    The only layer that builds queries over `monitored_components`. A component is "current" when
    its `deleted_at` is NULL. The order is `sort_order` and then `code` by code point
    (`COLLATE "C"`), the same order that the aggregation uses in Python: with the collation of the
    server a hyphen could be ignored and `a-c` and `ab` could swap.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _current() -> Select[tuple[MonitoredComponent]]:
        return (
            select(MonitoredComponent)
            .where(MonitoredComponent.deleted_at.is_(None))
            .order_by(MonitoredComponent.sort_order, MonitoredComponent.code.collate("C"))
        )

    async def list_enabled(self) -> list[MonitoredComponent]:
        """The current and enabled components, the ones that the aggregation checks."""
        statement = self._current().where(MonitoredComponent.enabled.is_(True))
        return list((await self._session.scalars(statement)).all())

    async def list_current(self) -> list[MonitoredComponent]:
        """Every current component, enabled or not, in its order."""
        return list((await self._session.scalars(self._current())).all())

    async def get_current(self, component_id: UUID) -> MonitoredComponent | None:
        """The current component with that identifier, or `None`."""
        statement = self._current().where(MonitoredComponent.id == component_id)
        return (await self._session.scalars(statement)).one_or_none()

    async def create(self, values: Mapping[str, Any]) -> MonitoredComponent:
        """Insert a component and commit; the table gives the identifier and the dates.

        A code in use by another current component raises `UniqueViolationError` (the unique index
        also decides simultaneous creations); any other failure is re-raised as it is.
        """
        statement = insert(MonitoredComponent).values(**values).returning(MonitoredComponent.id)
        component_id = await execute_and_commit(self._session, statement)
        if component_id is None:  # an INSERT always returns its row
            raise RuntimeError("The INSERT of the component returned no row")
        return await self._reload(component_id)

    async def lock_current(self, component_id: UUID) -> MonitoredComponent | None:
        """The current component with that identifier, locked until the transaction ends.

        It does not commit: the caller ends the transaction with `update` (which commits) or with
        `rollback`. Two simultaneous modifications wait for each other on the row.
        """
        statement = (
            self._current()
            .where(MonitoredComponent.id == component_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def update(
        self, component_id: UUID, changes: Mapping[str, Any]
    ) -> MonitoredComponent | None:
        """Apply `changes` to a current component and commit.

        Returns the updated component, or `None` if there is no current component with that
        identifier. The trigger of the table moves `updated_at`; a code in use by another current
        component raises `UniqueViolationError`.
        """
        statement = (
            update(MonitoredComponent)
            .where(MonitoredComponent.id == component_id, MonitoredComponent.deleted_at.is_(None))
            .values(**changes)
            .returning(MonitoredComponent.id)
        )
        if await execute_and_commit(self._session, statement) is None:
            return None
        return await self._reload(component_id)

    async def soft_delete(self, component_id: UUID) -> bool:
        """Mark a current component as deleted with the date; no row is removed.

        Returns `False` when there is no current component with that identifier. The condition on
        `deleted_at` makes it atomic: with simultaneous requests only one finds it.
        """
        statement = (
            update(MonitoredComponent)
            .where(MonitoredComponent.id == component_id, MonitoredComponent.deleted_at.is_(None))
            .values(deleted_at=func.current_timestamp())
            .returning(MonitoredComponent.id)
        )
        return await execute_and_commit(self._session, statement) is not None

    async def rollback(self) -> None:
        """End the transaction that `lock_current` opened without changing anything."""
        await self._session.rollback()

    async def _reload(self, component_id: UUID) -> MonitoredComponent:
        """Read a component, refreshing any instance the session already holds."""
        statement = (
            select(MonitoredComponent)
            .where(MonitoredComponent.id == component_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

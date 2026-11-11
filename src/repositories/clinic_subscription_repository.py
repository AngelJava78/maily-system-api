from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Select, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.clinic_subscription import ClinicSubscription
from src.models.clinic_subscription_charge import ClinicSubscriptionCharge
from src.models.clinic_subscription_status import ClinicSubscriptionStatus
from src.repositories import INT4_MAX
from src.repositories.transactions import execute_and_commit


class ClinicSubscriptionRepository:
    """All the persistence of the clinic subscriptions and their charge history.

    The current charge is never a column of `clinic_subscriptions` (it would make a foreign-key
    cycle, research R6/data-model.md): it is read as the most recent row of
    `clinic_subscription_charges` for that subscription (`latest_charge`/`latest_charges_for`).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _select_with_status() -> Select[tuple[ClinicSubscription]]:
        return select(ClinicSubscription).options(joinedload(ClinicSubscription.status))

    async def _reload(self, clinic_subscription_id: int) -> ClinicSubscription:
        statement = (
            self._select_with_status()
            .where(ClinicSubscription.id == clinic_subscription_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def create(
        self,
        *,
        tenant_id: UUID,
        subscription_id: int,
        billing_cycle: str,
        started_at: datetime,
        next_billing_at: datetime,
    ) -> ClinicSubscription:
        """Insert an Active clinic subscription and commit.

        The unique partial index (`clinic_subscriptions_one_active_per_tenant_key`) decides
        whether the clinic already has an Active or pending-resolution one; a violation raises
        `UniqueViolationError` (FR-004), which the Service translates.
        """
        statement = (
            insert(ClinicSubscription)
            .values(
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                billing_cycle=billing_cycle,
                started_at=started_at,
                next_billing_at=next_billing_at,
            )
            .returning(ClinicSubscription.id)
        )
        clinic_subscription_id = await execute_and_commit(self._session, statement)
        if clinic_subscription_id is None:  # an INSERT always returns its row
            raise RuntimeError("The INSERT of the clinic subscription returned no row")
        return await self._reload(clinic_subscription_id)

    async def get_by_id(self, clinic_subscription_id: int) -> ClinicSubscription | None:
        """Any clinic subscription with that id, whatever its status (callers decide what a
        Cancelled one means for their operation: FR-030, research R7).

        Always re-reads from the database (`populate_existing`), even if this session already
        holds the row: the Service may call this again right after a raw `UPDATE` elsewhere in
        the same request (`save_charge`'s subscription update) and must see that change.
        """
        if clinic_subscription_id > INT4_MAX:
            return None
        statement = (
            self._select_with_status()
            .where(ClinicSubscription.id == clinic_subscription_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def list(
        self, *, tenant_id: UUID | None, status_id: int | None, page: int, limit: int
    ) -> tuple[list[ClinicSubscription], int]:
        """A page of clinic subscriptions (FR-007), oldest first, and the total count of matches."""
        conditions = []
        if tenant_id is not None:
            conditions.append(ClinicSubscription.tenant_id == tenant_id)
        if status_id is not None:
            conditions.append(ClinicSubscription.status_id == status_id)

        count_statement = select(func.count()).select_from(ClinicSubscription).where(*conditions)
        total = (await self._session.scalars(count_statement)).one()

        statement = (
            self._select_with_status()
            .where(*conditions)
            .order_by(ClinicSubscription.created_at, ClinicSubscription.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list((await self._session.scalars(statement)).all())
        return rows, total

    async def latest_charge(self, clinic_subscription_id: int) -> ClinicSubscriptionCharge | None:
        charges = await self.latest_charges_for([clinic_subscription_id])
        return charges.get(clinic_subscription_id)

    async def latest_charges_for(
        self, clinic_subscription_ids: Sequence[int]
    ) -> dict[int, ClinicSubscriptionCharge]:
        """The most recent charge of each of these subscriptions (one query, `DISTINCT ON`)."""
        ids = list(clinic_subscription_ids)
        if not ids:
            return {}
        statement = (
            select(ClinicSubscriptionCharge)
            .distinct(ClinicSubscriptionCharge.clinic_subscription_id)
            .where(ClinicSubscriptionCharge.clinic_subscription_id.in_(ids))
            .order_by(
                ClinicSubscriptionCharge.clinic_subscription_id,
                ClinicSubscriptionCharge.period.desc(),
                ClinicSubscriptionCharge.id.desc(),
            )
        )
        rows = (await self._session.scalars(statement)).all()
        return {row.clinic_subscription_id: row for row in rows}

    async def list_charges(
        self, clinic_subscription_id: int, *, page: int, limit: int
    ) -> tuple[list[ClinicSubscriptionCharge], int]:
        """A page of the charge history of one clinic subscription, most recent period first."""
        condition = ClinicSubscriptionCharge.clinic_subscription_id == clinic_subscription_id
        count_statement = select(func.count()).select_from(ClinicSubscriptionCharge).where(condition)
        total = (await self._session.scalars(count_statement)).one()

        statement = (
            select(ClinicSubscriptionCharge)
            .where(condition)
            .order_by(ClinicSubscriptionCharge.period.desc(), ClinicSubscriptionCharge.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list((await self._session.scalars(statement)).all())
        return rows, total

    async def get_charge(
        self, clinic_subscription_id: int, charge_id: int
    ) -> ClinicSubscriptionCharge | None:
        if charge_id > INT4_MAX:
            return None
        statement = select(ClinicSubscriptionCharge).where(
            ClinicSubscriptionCharge.id == charge_id,
            ClinicSubscriptionCharge.clinic_subscription_id == clinic_subscription_id,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def cancel(self, clinic_subscription_id: int) -> ClinicSubscription | None:
        """Move a clinic subscription to Cancelled with one atomic statement.

        Returns `None` when there is no clinic subscription with that id or it is already
        Cancelled (nothing changes); the Service tells the two apart with `get_by_id`.
        """
        if clinic_subscription_id > INT4_MAX:
            return None
        statement = (
            update(ClinicSubscription)
            .where(
                ClinicSubscription.id == clinic_subscription_id,
                ClinicSubscription.status_id != ClinicSubscriptionStatus.CANCELLED,
            )
            .values(status_id=ClinicSubscriptionStatus.CANCELLED)
            .returning(ClinicSubscription.id)
        )
        if await execute_and_commit(self._session, statement) is None:
            return None
        return await self._reload(clinic_subscription_id)

    async def save_charge(
        self,
        clinic_subscription_id: int,
        *,
        period: date,
        amount: int,
        currency: str,
        payment_id: UUID,
        payment_status: str,
        checkout_url: str | None,
        idempotency_key: str,
        subscription_status_id: int,
        next_billing_at: datetime | None = None,
    ) -> ClinicSubscriptionCharge:
        """Upsert the charge of one period and update the subscription's own status in one commit.

        The same call serves both a brand-new charge (research R3: the unique index on
        `(clinic_subscription_id, period)` means a retry of the same period updates this same row)
        and the sync-on-read of a `pending` one (historia 3): the caller always passes the full,
        already-resolved row. `next_billing_at` is only set when the charge moves to `approved`
        (FR-015); otherwise the subscription's own date is left untouched.
        """
        charge_statement = (
            pg_insert(ClinicSubscriptionCharge)
            .values(
                clinic_subscription_id=clinic_subscription_id,
                period=period,
                amount=amount,
                currency=currency,
                payment_id=payment_id,
                payment_status=payment_status,
                checkout_url=checkout_url,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_update(
                index_elements=["clinic_subscription_id", "period"],
                set_={
                    "amount": amount,
                    "currency": currency,
                    "payment_id": payment_id,
                    "payment_status": payment_status,
                    "checkout_url": checkout_url,
                    "idempotency_key": idempotency_key,
                },
            )
            .returning(ClinicSubscriptionCharge.id)
        )
        subscription_values: dict[str, object] = {"status_id": subscription_status_id}
        if next_billing_at is not None:
            subscription_values["next_billing_at"] = next_billing_at
        subscription_statement = (
            update(ClinicSubscription)
            .where(ClinicSubscription.id == clinic_subscription_id)
            .values(**subscription_values)
        )
        try:
            charge_id = (await self._session.execute(charge_statement)).scalar_one()
            await self._session.execute(subscription_statement)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        # populate_existing: the row may already be in this session's identity map (it is always
        # read once before this call, to decide whether to insert or update), which would
        # otherwise make SQLAlchemy keep serving the stale in-memory attributes instead of the
        # ones the UPDATE/INSERT just wrote.
        statement = (
            select(ClinicSubscriptionCharge)
            .where(ClinicSubscriptionCharge.id == charge_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

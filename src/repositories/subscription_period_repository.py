from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.subscription_charge import ChargeStatus, SubscriptionCharge
from src.models.subscription_period import SubscriptionPeriod
from src.repositories.transactions import execute_and_commit


class ApplyOutcome(StrEnum):
    """What `apply_charge` did (research R5)."""

    APPLIED = "applied"
    # Another request already applied or closed the charge: nothing changed.
    ALREADY_RESOLVED = "already_resolved"
    # The date `paid_until` moved after the caller read it: nothing changed, read it again.
    STALE = "stale"


class SubscriptionPeriodRepository:
    """All the persistence of the subscription periods and their charges (spec 010).

    The only layer that builds queries over `subscription_periods` and `subscription_charges`. It holds
    no business rule: the Service computes the dates and the Repository writes them, in a way that makes
    the two things that must happen once — creating the period and applying a charge — happen once even
    with simultaneous requests. Every read refreshes the instances that the session already holds, so
    what the Service sees is what the database has stored.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID) -> SubscriptionPeriod | None:
        """The period of the organization, or `None` if it has not been consulted yet."""
        statement = (
            select(SubscriptionPeriod)
            .where(SubscriptionPeriod.organization_id == organization_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def create_if_absent(
        self, organization_id: UUID, started_at: datetime, trial_ends_at: datetime | None
    ) -> SubscriptionPeriod:
        """Create the period of an organization once and return the one that exists (FR-007).

        The primary key decides simultaneous first requests: one inserts, the others read the row that
        the winner wrote (the dates they computed are the same, but the winner's are the ones kept).
        """
        statement = (
            postgresql_insert(SubscriptionPeriod)
            .values(
                organization_id=organization_id,
                started_at=started_at,
                trial_ends_at=trial_ends_at,
            )
            .on_conflict_do_nothing(index_elements=[SubscriptionPeriod.organization_id])
        )
        try:
            await self._session.execute(statement)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        period = await self.get(organization_id)
        if period is None:  # the row was inserted by this call or by the one that won
            raise RuntimeError("The period of the organization does not exist after creating it")
        return period

    async def list_pending(self, organization_id: UUID) -> list[SubscriptionCharge]:
        """The charges of the organization that are still unresolved, oldest first.

        They are returned detached from the session, as read-only snapshots. The Service keeps the list
        while it applies or closes the charges one by one, and when another request got there first
        `apply_charge` gives up with a rollback, which expires every instance that the session holds:
        reading an expired one needs I/O that cannot happen outside the session's greenlet. Nothing is
        ever written through these instances (every write is a statement of this Repository).
        """
        statement = (
            select(SubscriptionCharge)
            .where(
                SubscriptionCharge.organization_id == organization_id,
                SubscriptionCharge.status == ChargeStatus.PENDING,
            )
            .order_by(SubscriptionCharge.created_at, SubscriptionCharge.id)
            .execution_options(populate_existing=True)
        )
        charges = list((await self._session.scalars(statement)).all())
        for charge in charges:
            self._session.expunge(charge)
        return charges

    async def list_charges(
        self, organization_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[SubscriptionCharge], int]:
        """A page of the charge history of the organization, most recent first (spec 012).

        Unlike `list_pending`, this is a plain read with no business meaning attached: it does not
        trigger a reconciliation with the payments API (the full period read already does that
        whenever the person visits the payment screen), so a charge can legitimately still show as
        `pending` here.
        """
        condition = SubscriptionCharge.organization_id == organization_id
        total = (
            await self._session.scalars(select(func.count()).select_from(SubscriptionCharge).where(condition))
        ).one()
        statement = (
            select(SubscriptionCharge)
            .where(condition)
            .order_by(SubscriptionCharge.created_at.desc(), SubscriptionCharge.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(populate_existing=True)
        )
        charges = list((await self._session.scalars(statement)).all())
        for charge in charges:
            self._session.expunge(charge)
        return charges, total

    async def find_pending(
        self,
        organization_id: UUID,
        settles_due_at: datetime,
        billing_period: str,
        amount: Decimal,
    ) -> SubscriptionCharge | None:
        """The unresolved charge with those conditions, if any (research R6)."""
        statement = (
            select(SubscriptionCharge)
            .where(
                SubscriptionCharge.organization_id == organization_id,
                SubscriptionCharge.settles_due_at == settles_due_at,
                SubscriptionCharge.billing_period == billing_period,
                SubscriptionCharge.amount == amount,
                SubscriptionCharge.status == ChargeStatus.PENDING,
            )
            .order_by(SubscriptionCharge.created_at, SubscriptionCharge.id)
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def find_by_payment_id(self, payment_id: UUID) -> SubscriptionCharge | None:
        """The charge that registered that payment of the payments API, if any."""
        statement = (
            select(SubscriptionCharge)
            .where(SubscriptionCharge.payment_id == payment_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def count_resolved_with_terms(
        self,
        organization_id: UUID,
        settles_due_at: datetime,
        billing_period: str,
        amount: Decimal,
    ) -> int:
        """How many attempts with those conditions already ended: the next attempt is this + 1.

        Only the resolved ones (applied or closed) count, never the pending one. A pending charge is
        reused, not followed by another attempt, and counting it would let a request that read just
        before it was registered and counted just after it compute the next attempt: another key, so
        another payment in the payments API for the same period (research R6).
        """
        statement = select(func.count()).where(
            SubscriptionCharge.organization_id == organization_id,
            SubscriptionCharge.settles_due_at == settles_due_at,
            SubscriptionCharge.billing_period == billing_period,
            SubscriptionCharge.amount == amount,
            SubscriptionCharge.status != ChargeStatus.PENDING,
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def add_charge(
        self,
        *,
        organization_id: UUID,
        payment_id: UUID,
        amount: Decimal,
        billing_period: str,
        settles_due_at: datetime,
        attempt: int,
        currency: str = "MXN",
    ) -> SubscriptionCharge:
        """Register a payment that the payments API created, as a pending charge, and commit.

        A payment that is already registered, or conditions and attempt that already exist, raise
        `UniqueViolationError` (with the name of the constraint); the organization must have a period
        (`ForeignKeyViolationError` otherwise). Any other failure is re-raised as it is.
        """
        statement = (
            insert(SubscriptionCharge)
            .values(
                organization_id=organization_id,
                payment_id=payment_id,
                amount=amount,
                currency=currency,
                billing_period=billing_period,
                settles_due_at=settles_due_at,
                attempt=attempt,
            )
            .returning(SubscriptionCharge.id)
        )
        charge_id = await execute_and_commit(self._session, statement)
        if charge_id is None:  # an INSERT always returns its row
            raise RuntimeError("The INSERT of the charge returned no row")
        statement_reload = (
            select(SubscriptionCharge)
            .where(SubscriptionCharge.id == charge_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement_reload)).one()

    async def close_charge(self, charge_id: UUID, reason: str, resolved_at: datetime) -> bool:
        """Close an unresolved charge without applying it and commit.

        Returns `False` when the charge is no longer pending (nothing changes): with simultaneous
        requests only one closes it.
        """
        statement = (
            update(SubscriptionCharge)
            .where(
                SubscriptionCharge.id == charge_id,
                SubscriptionCharge.status == ChargeStatus.PENDING,
            )
            .values(status=ChargeStatus.CLOSED, closed_reason=reason, resolved_at=resolved_at)
            .returning(SubscriptionCharge.id)
        )
        return await execute_and_commit(self._session, statement) is not None

    async def apply_charge(
        self,
        *,
        charge_id: UUID,
        organization_id: UUID,
        expected_paid_until: datetime | None,
        period_starts_at: datetime,
        period_ends_at: datetime,
        resolved_at: datetime,
    ) -> ApplyOutcome:
        """Apply a charge: mark it applied and move `paid_until`, in one transaction (research R5).

        Two statements, both conditioned, nothing locked while the caller talked to the payments API:

        1. Claim the charge (`WHERE status = 'pending'`): only one of the requests that compete for it
           finds it pending, so a charge moves the date exactly once. Otherwise `ALREADY_RESOLVED`.
        2. Move `paid_until` to the end of the period, only if it still is what the caller read
           (compare-and-swap): the caller computed the period from that date. Otherwise `STALE`, and the
           claim of step 1 is undone too: the caller reads again and computes again.
        """
        claim = (
            update(SubscriptionCharge)
            .where(
                SubscriptionCharge.id == charge_id,
                SubscriptionCharge.organization_id == organization_id,
                SubscriptionCharge.status == ChargeStatus.PENDING,
            )
            .values(
                status=ChargeStatus.APPLIED,
                period_starts_at=period_starts_at,
                period_ends_at=period_ends_at,
                resolved_at=resolved_at,
            )
            .returning(SubscriptionCharge.id)
        )
        move = (
            update(SubscriptionPeriod)
            .where(
                SubscriptionPeriod.organization_id == organization_id,
                SubscriptionPeriod.paid_until.is_not_distinct_from(expected_paid_until),
            )
            .values(paid_until=period_ends_at)
            .returning(SubscriptionPeriod.organization_id)
        )
        try:
            if (await self._session.execute(claim)).scalar_one_or_none() is None:
                await self._session.rollback()
                return ApplyOutcome.ALREADY_RESOLVED
            if (await self._session.execute(move)).scalar_one_or_none() is None:
                await self._session.rollback()
                return ApplyOutcome.STALE
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return ApplyOutcome.APPLIED

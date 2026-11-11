from datetime import date
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.clinic_subscription_charge import ClinicSubscriptionCharge
from src.repositories import INT4_MAX


class ClinicSubscriptionChargeRepository:
    """All the persistence of the charge history (Principle I).

    `clinic_subscription_id` is an opaque identifier owned by Clinics (rediseño 2026-11-11): this
    repository never validates it against a local table, only against its own history.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_charge(
        self,
        *,
        clinic_subscription_id: UUID,
        tenant_id: UUID,
        period: date,
        amount: int,
        currency: str,
        payment_id: UUID,
        payment_status: str,
        checkout_url: str | None,
        idempotency_key: str,
    ) -> ClinicSubscriptionCharge:
        """Upsert the charge of one period and commit.

        The unique index on `(clinic_subscription_id, period)` means a retry of the same period
        (research R3) updates this same row instead of creating a duplicate.
        """
        statement = (
            pg_insert(ClinicSubscriptionCharge)
            .values(
                clinic_subscription_id=clinic_subscription_id,
                tenant_id=tenant_id,
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
                    "tenant_id": tenant_id,
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
        charge_id = (await self._session.execute(statement)).scalar_one()
        await self._session.commit()
        return await self._reload(charge_id)

    async def update_status(
        self, charge_id: int, *, payment_status: str, checkout_url: str | None
    ) -> ClinicSubscriptionCharge:
        """Apply the sync-on-read of a `pending` charge (historia 2, research R8): only its own
        status and checkout URL change, nothing else about the charge."""
        statement = (
            update(ClinicSubscriptionCharge)
            .where(ClinicSubscriptionCharge.id == charge_id)
            .values(payment_status=payment_status, checkout_url=checkout_url)
        )
        await self._session.execute(statement)
        await self._session.commit()
        return await self._reload(charge_id)

    async def _reload(self, charge_id: int) -> ClinicSubscriptionCharge:
        statement = (
            select(ClinicSubscriptionCharge)
            .where(ClinicSubscriptionCharge.id == charge_id)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def get_by_period(
        self, clinic_subscription_id: UUID, period: date
    ) -> ClinicSubscriptionCharge | None:
        """The charge of this subscription and period, if any (FR-011 eligibility check)."""
        statement = select(ClinicSubscriptionCharge).where(
            ClinicSubscriptionCharge.clinic_subscription_id == clinic_subscription_id,
            ClinicSubscriptionCharge.period == period,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get(
        self, clinic_subscription_id: UUID, charge_id: int
    ) -> ClinicSubscriptionCharge | None:
        """A charge of this subscription by its own id, or `None` (wrong subscription included)."""
        if charge_id > INT4_MAX:
            return None
        statement = select(ClinicSubscriptionCharge).where(
            ClinicSubscriptionCharge.id == charge_id,
            ClinicSubscriptionCharge.clinic_subscription_id == clinic_subscription_id,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def list(
        self, clinic_subscription_id: UUID, *, page: int, limit: int
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

"""Business rules of the clinic subscriptions and their charges (spec 006).

Receives validated DTOs (and, for the charge operation, the caller's own `CallerAccess`) and
returns ORM rows wrapped in a small view, same pattern as `SubscriptionService`.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.dtos.clinic_subscription import ClinicSubscriptionCreate
from src.exceptions import (
    ClinicSubscriptionAlreadyActiveError,
    ClinicSubscriptionAlreadyCancelledError,
    ClinicSubscriptionChargeConflictError,
    ClinicSubscriptionChargeNotFoundError,
    ClinicSubscriptionChargePendingError,
    ClinicSubscriptionChargeRequiresActivePlanError,
    ClinicSubscriptionNotChargeableError,
    ClinicSubscriptionNotFoundError,
    ClinicSubscriptionPlanNotActiveError,
    InvalidTokenError,
    PaymentNotAuthorizedError,
    PaymentsUnavailableError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.integrations.errors import (
    PaymentsApiIdempotencyConflict,
    PaymentsApiPermissionDenied,
    PaymentsApiRejectedToken,
    PaymentsApiUnavailable,
)
from src.integrations.payments_api import PaymentsApiClient
from src.integrations.users_api import CallerAccess
from src.models.clinic_subscription import ClinicSubscription
from src.models.clinic_subscription_charge import ClinicSubscriptionCharge
from src.models.clinic_subscription_status import ClinicSubscriptionStatus
from src.models.subscription_status import SubscriptionStatus
from src.repositories.clinic_subscription_repository import ClinicSubscriptionRepository
from src.repositories.errors import UniqueViolationError
from src.repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

# Namespaced reference to this resource (Pagos' Principle X; research R4). Never changes: Pagos
# never validates it, but other integrations may come to rely on its exact spelling.
PAYMENTS_RESOURCE_TYPE = "system-api:clinic-subscription"
CURRENCY = "MXN"
_PENDING = "pending"
_APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class ClinicSubscriptionView:
    """A clinic subscription together with its current (most recent) charge, if any."""

    clinic_subscription: ClinicSubscription
    current_charge: ClinicSubscriptionCharge | None


def _idempotency_key(clinic_subscription_id: int, period: datetime) -> str:
    """Deterministic per period (research R3): the same period always yields the same key."""
    return f"clinic-subscription:{clinic_subscription_id}:{period.date().isoformat()}"


def _advance(moment: datetime, cycle: str) -> datetime:
    """`moment` one billing cycle later, clamping to the last valid day of the target month."""
    if cycle == "annual":
        try:
            return moment.replace(year=moment.year + 1)
        except ValueError:  # 29 February on a non-leap year
            return moment.replace(year=moment.year + 1, month=2, day=28)
    year = moment.year + (1 if moment.month == 12 else 0)
    month = 1 if moment.month == 12 else moment.month + 1
    day = moment.day
    while True:
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1


def _to_cents(price: Decimal) -> int:
    """`price` (pesos, at most two decimals) as an exact integer of centavos (research R2)."""
    cents = price * 100
    if cents != cents.to_integral_value():
        raise RuntimeError("Price has more than two decimal places")
    return int(cents)


class ClinicSubscriptionService:
    def __init__(
        self,
        repository: ClinicSubscriptionRepository,
        subscription_repository: SubscriptionRepository,
        payments_api: PaymentsApiClient,
    ) -> None:
        self._repository = repository
        self._subscriptions = subscription_repository
        self._payments_api = payments_api

    async def _sync_if_pending(
        self, clinic_subscription: ClinicSubscription, charge: ClinicSubscriptionCharge | None
    ) -> tuple[ClinicSubscription, ClinicSubscriptionCharge | None]:
        """Resolve a `pending` charge against Pagos before answering (historia 3, research R8).

        Degrades to the last known local state if Pagos cannot be reached (FR-017): never fails
        the read that triggered it. Returns the subscription too, re-read from the database when
        syncing changed it (its status and `next_billing_at`), since `save_charge` updates it with
        a raw statement that does not refresh an ORM instance already held in memory.
        """
        if charge is None or charge.payment_status != _PENDING:
            return clinic_subscription, charge
        try:
            payment = await self._payments_api.get_payment(charge.payment_id)
        except PaymentsApiUnavailable:
            logger.warning("Could not sync pending charge %s with the payments API", charge.id)
            return clinic_subscription, charge
        if payment.status == charge.payment_status:
            return clinic_subscription, charge

        if payment.status == _APPROVED:
            status_id = ClinicSubscriptionStatus.ACTIVE
            next_billing_at = _advance(clinic_subscription.next_billing_at, clinic_subscription.billing_cycle)
        else:
            status_id = ClinicSubscriptionStatus.PENDING_RESOLUTION
            next_billing_at = None
        updated_charge = await self._repository.save_charge(
            clinic_subscription.id,
            period=charge.period,
            amount=charge.amount,
            currency=charge.currency,
            payment_id=charge.payment_id,
            payment_status=payment.status,
            checkout_url=payment.checkout_url if payment.status == _PENDING else None,
            idempotency_key=charge.idempotency_key,
            subscription_status_id=status_id,
            next_billing_at=next_billing_at,
        )
        refreshed = await self._repository.get_by_id(clinic_subscription.id)
        assert refreshed is not None  # it existed a moment ago and this service never deletes rows
        return refreshed, updated_charge

    async def create(self, data: ClinicSubscriptionCreate) -> ClinicSubscriptionView:
        """Assign a catalog plan to a clinic (FR-001 to FR-006)."""
        plan = await self._subscriptions.get_current_by_id(data.subscription_id)
        if plan is None or plan.status_id != SubscriptionStatus.ACTIVE:
            raise ClinicSubscriptionPlanNotActiveError(data.subscription_id)

        started_at = data.started_at or datetime.now(UTC)
        next_billing_at = (
            started_at + timedelta(days=plan.trial_days) if plan.trial_days else started_at
        )
        try:
            row = await self._repository.create(
                tenant_id=data.tenant_id,
                subscription_id=data.subscription_id,
                billing_cycle=data.billing_cycle,
                started_at=started_at,
                next_billing_at=next_billing_at,
            )
        except UniqueViolationError:
            raise ClinicSubscriptionAlreadyActiveError from None
        return ClinicSubscriptionView(row, None)

    async def get(self, clinic_subscription_id: int) -> ClinicSubscriptionView:
        row = await self._repository.get_by_id(clinic_subscription_id)
        if row is None or row.status_id == ClinicSubscriptionStatus.CANCELLED:
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id)
        row, charge = await self._sync_if_pending(row, await self._repository.latest_charge(row.id))
        return ClinicSubscriptionView(row, charge)

    async def list(
        self, *, tenant_id, status_id: int | None, page: int, limit: int
    ) -> tuple[list[ClinicSubscriptionView], int]:
        rows, total = await self._repository.list(
            tenant_id=tenant_id, status_id=status_id, page=page, limit=limit
        )
        charges = await self._repository.latest_charges_for([row.id for row in rows])
        views = []
        for row in rows:
            row, charge = await self._sync_if_pending(row, charges.get(row.id))
            views.append(ClinicSubscriptionView(row, charge))
        return views, total

    async def _current_or_404(self, clinic_subscription_id: int) -> ClinicSubscription:
        row = await self._repository.get_by_id(clinic_subscription_id)
        if row is None or row.status_id == ClinicSubscriptionStatus.CANCELLED:
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id)
        return row

    async def list_charges(
        self, clinic_subscription_id: int, *, page: int, limit: int
    ) -> tuple[list[ClinicSubscriptionCharge], int]:
        await self._current_or_404(clinic_subscription_id)
        return await self._repository.list_charges(clinic_subscription_id, page=page, limit=limit)

    async def get_charge(
        self, clinic_subscription_id: int, charge_id: int
    ) -> ClinicSubscriptionCharge:
        row = await self._current_or_404(clinic_subscription_id)
        charge = await self._repository.get_charge(clinic_subscription_id, charge_id)
        if charge is None:
            raise ClinicSubscriptionChargeNotFoundError(charge_id)
        _, synced = await self._sync_if_pending(row, charge)
        assert synced is not None  # a found charge is never None after syncing
        return synced

    async def cancel(self, clinic_subscription_id: int) -> None:
        """Cancel a clinic subscription (historia 5): rejects a `pending` current charge."""
        row = await self._repository.get_by_id(clinic_subscription_id)
        if row is None:
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id)
        if row.status_id == ClinicSubscriptionStatus.CANCELLED:
            raise ClinicSubscriptionAlreadyCancelledError(clinic_subscription_id)
        _, charge = await self._sync_if_pending(row, await self._repository.latest_charge(row.id))
        if charge is not None and charge.payment_status == _PENDING:
            raise ClinicSubscriptionChargePendingError(clinic_subscription_id)
        if await self._repository.cancel(clinic_subscription_id) is None:
            # Another request resolved this in between (cancelled it, or left a pending charge).
            raise ClinicSubscriptionAlreadyCancelledError(clinic_subscription_id)

    async def charge(
        self, clinic_subscription_id: int, caller: CallerAccess, token: str
    ) -> ClinicSubscriptionCharge:
        """Trigger the charge of a clinic subscription (historia 2; FR-008 to FR-015, FR-030).

        `caller` MUST belong to the same organization as the subscription (FR-030: checked by the
        Router before this is even called, via `tenant_id`); `token` is forwarded to Pagos
        untouched so it resolves the correct `tenant_id` itself (FR-011).
        """
        row = await self._repository.get_by_id(clinic_subscription_id)
        if (
            row is None
            or caller.tenant_id is None
            or str(row.tenant_id) != caller.tenant_id.lower()
        ):
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id)

        # Syncing first (rather than trusting a stale local status) means a charge that was
        # resolved asynchronously advances the period before it is retried, and a retry of a
        # charge that is still genuinely pending reaches Pagos again with the same deterministic
        # Idempotency-Key (research R3, historia 2 escenario 2): it is never blocked here, only
        # Pagos decides (it returns the same payment, never a duplicate charge).
        row, _ = await self._sync_if_pending(row, await self._repository.latest_charge(row.id))
        if row.status_id == ClinicSubscriptionStatus.CANCELLED:
            raise ClinicSubscriptionNotChargeableError(clinic_subscription_id)

        plan = await self._subscriptions.get_current_by_id(row.subscription_id)
        if plan is None or plan.status_id != SubscriptionStatus.ACTIVE:
            raise ClinicSubscriptionChargeRequiresActivePlanError

        price = plan.monthly_price if row.billing_cycle == "monthly" else plan.annual_price
        amount = _to_cents(price)
        period = row.next_billing_at
        idempotency_key = _idempotency_key(row.id, period)

        try:
            payment = await self._payments_api.create_payment(
                token,
                idempotency_key=idempotency_key,
                amount=amount,
                currency=CURRENCY,
                resource_type=PAYMENTS_RESOURCE_TYPE,
                resource_id=str(row.id),
                description=f"Suscripción de clínica {row.id} — periodo {period.date().isoformat()}",
            )
        except PaymentsApiRejectedToken as rejection:
            if rejection.code == "token_expired":
                raise TokenExpiredError from None
            if rejection.code == "unauthenticated":
                raise UnauthenticatedError from None
            raise InvalidTokenError from None
        except PaymentsApiPermissionDenied:
            raise PaymentNotAuthorizedError from None
        except PaymentsApiIdempotencyConflict:
            raise ClinicSubscriptionChargeConflictError from None
        except PaymentsApiUnavailable:
            raise PaymentsUnavailableError from None

        if payment.status == _APPROVED:
            status_id = ClinicSubscriptionStatus.ACTIVE
            next_billing_at = _advance(row.next_billing_at, row.billing_cycle)
        else:
            status_id = ClinicSubscriptionStatus.PENDING_RESOLUTION
            next_billing_at = None
        return await self._repository.save_charge(
            row.id,
            period=period.date(),
            amount=amount,
            currency=CURRENCY,
            payment_id=payment.id,
            payment_status=payment.status,
            checkout_url=payment.checkout_url,
            idempotency_key=idempotency_key,
            subscription_status_id=status_id,
            next_billing_at=next_billing_at,
        )

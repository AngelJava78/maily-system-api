"""Business rules of charging a clinic subscription and its history (spec 010).

Receives validated input (and the caller's own `CallerAccess`, for the charge operation) and
returns ORM rows, same pattern as `SubscriptionService`. The clinic/plan/cycle assignment is NOT
owned here (rediseño 2026-11-11, Principle IX): it is consulted from Clinics (an opaque
`clinic_subscription_id`) on every charge, never stored.
"""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.exceptions import (
    ClinicSubscriptionChargeAlreadyApprovedError,
    ClinicSubscriptionChargeConflictError,
    ClinicSubscriptionChargeNotFoundError,
    ClinicSubscriptionCheckUnavailableError,
    ClinicSubscriptionNotFoundError,
    ClinicSubscriptionPlanNotActiveError,
    InvalidTokenError,
    PaymentNotAuthorizedError,
    PaymentsUnavailableError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.errors import (
    ClinicsApiNotFound,
    ClinicsApiUnavailable,
    PaymentsApiIdempotencyConflict,
    PaymentsApiPermissionDenied,
    PaymentsApiRejectedToken,
    PaymentsApiUnavailable,
)
from src.integrations.payments_api import PaymentsApiClient
from src.integrations.users_api import CallerAccess
from src.models.clinic_subscription_charge import ClinicSubscriptionCharge
from src.models.subscription_status import SubscriptionStatus
from src.repositories.clinic_subscription_charge_repository import ClinicSubscriptionChargeRepository
from src.repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

# Namespaced reference to this resource (Pagos' Principle X; research R4). Never changes: Pagos
# never validates it, but other integrations may come to rely on its exact spelling.
PAYMENTS_RESOURCE_TYPE = "system-api:clinic-subscription"
CURRENCY = "MXN"
_PENDING = "pending"
_APPROVED = "approved"


def _idempotency_key(clinic_subscription_id: UUID, period: date) -> str:
    """Deterministic per period (research R3): the same period always yields the same key."""
    return f"clinic-subscription:{clinic_subscription_id}:{period.isoformat()}"


def _to_cents(price: Decimal) -> int:
    """`price` (pesos, at most two decimals) as an exact integer of centavos (research R2)."""
    cents = price * 100
    if cents != cents.to_integral_value():
        raise RuntimeError("Price has more than two decimal places")
    return int(cents)


class ClinicSubscriptionService:
    def __init__(
        self,
        repository: ClinicSubscriptionChargeRepository,
        subscription_repository: SubscriptionRepository,
        clinics_api: ClinicsApiClient,
        payments_api: PaymentsApiClient,
    ) -> None:
        self._repository = repository
        self._subscriptions = subscription_repository
        self._clinics_api = clinics_api
        self._payments_api = payments_api

    async def _sync_if_pending(self, charge: ClinicSubscriptionCharge) -> ClinicSubscriptionCharge:
        """Resolve a `pending` charge against Pagos before answering (historia 2, research R8).

        Degrades to the last known local state if Pagos cannot be reached: never fails the read
        that triggered it.
        """
        if charge.payment_status != _PENDING:
            return charge
        try:
            payment = await self._payments_api.get_payment_as_service(charge.payment_id)
        except PaymentsApiUnavailable:
            logger.warning("Could not sync pending charge %s with the payments API", charge.id)
            return charge
        if payment.status == charge.payment_status:
            return charge
        checkout_url = payment.checkout_url if payment.status == _PENDING else None
        return await self._repository.update_status(
            charge.id, payment_status=payment.status, checkout_url=checkout_url
        )

    async def charge(
        self, clinic_subscription_id: UUID, period: date, caller: CallerAccess, token: str
    ) -> ClinicSubscriptionCharge:
        """Trigger the charge of a clinic subscription (historia 1; FR-001 to FR-012, FR-026).

        `clinic_subscription_id` is resolved against Clinics on every call (Principle IX): this
        service never stores the clinic/plan/cycle assignment. `caller` MUST belong to the same
        organization Clinics reports (FR-026); `token` is forwarded to Pagos untouched so it
        resolves the correct `tenant_id` itself (FR-008).
        """
        try:
            info = await self._clinics_api.get_clinic_subscription(token, str(clinic_subscription_id))
        except ClinicsApiNotFound:
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id) from None
        except ClinicsApiUnavailable:
            raise ClinicSubscriptionCheckUnavailableError from None

        if caller.tenant_id is None or caller.tenant_id.lower() != info.tenant_id.lower():
            raise ClinicSubscriptionNotFoundError(clinic_subscription_id)

        plan = await self._subscriptions.get_current_by_id(info.subscription_id)
        if plan is None or plan.status_id != SubscriptionStatus.ACTIVE:
            raise ClinicSubscriptionPlanNotActiveError

        existing = await self._repository.get_by_period(clinic_subscription_id, period)
        if existing is not None and existing.payment_status == _APPROVED:
            raise ClinicSubscriptionChargeAlreadyApprovedError

        price = plan.monthly_price if info.billing_cycle == "monthly" else plan.annual_price
        amount = _to_cents(price)
        idempotency_key = _idempotency_key(clinic_subscription_id, period)

        try:
            payment = await self._payments_api.create_payment(
                token,
                idempotency_key=idempotency_key,
                amount=amount,
                currency=CURRENCY,
                resource_type=PAYMENTS_RESOURCE_TYPE,
                resource_id=str(clinic_subscription_id),
                description=f"Suscripción de clínica {clinic_subscription_id} — periodo {period.isoformat()}",
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

        return await self._repository.save_charge(
            clinic_subscription_id=clinic_subscription_id,
            tenant_id=UUID(info.tenant_id),
            period=period,
            amount=amount,
            currency=CURRENCY,
            payment_id=payment.id,
            payment_status=payment.status,
            checkout_url=payment.checkout_url,
            idempotency_key=idempotency_key,
        )

    async def get_charge(
        self, clinic_subscription_id: UUID, charge_id: int
    ) -> ClinicSubscriptionCharge:
        """Consult one charge of the history (historia 3), synced if still `pending`."""
        charge = await self._repository.get(clinic_subscription_id, charge_id)
        if charge is None:
            raise ClinicSubscriptionChargeNotFoundError(charge_id)
        return await self._sync_if_pending(charge)

    async def list_charges(
        self, clinic_subscription_id: UUID, *, page: int, limit: int
    ) -> tuple[list[ClinicSubscriptionCharge], int]:
        """A page of the charge history of one clinic subscription (historia 3)."""
        rows, total = await self._repository.list(clinic_subscription_id, page=page, limit=limit)
        return [await self._sync_if_pending(row) for row in rows], total

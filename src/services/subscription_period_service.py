"""The subscription periods: the trial and the next payment of each organization (spec 010).

The Service orchestrates what the business rules need — the organization, its plan and billing period
(clinics API), the price of the plan (catalog), the record of this service and the payments (payments API)
— and leaves the arithmetic to `billing_rules`. Nothing of another API is stored (Principle IX): the
organization and its plan are read on every use. Every date comes from the injected clock.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.exceptions import (
    NothingToChargeError,
    OrganizationCheckUnavailableError,
    OrganizationNotFoundError,
    OrganizationSubscriptionNotFoundError,
    PaymentsUnavailableError,
)
from src.integrations.clinics_api import ClinicsApiClient, OrganizationRecord
from src.integrations.errors import ClinicsApiUnavailable, OrganizationNotFound, PaymentsApiUnavailable
from src.integrations.payments_api import PaymentRecord, PaymentsApiClient
from src.models.subscription_charge import ClosedReason, SubscriptionCharge
from src.models.subscription_period import SubscriptionPeriod
from src.repositories.errors import UniqueViolationError
from src.repositories.subscription_period_repository import (
    ApplyOutcome,
    SubscriptionPeriodRepository,
)
from src.repositories.subscription_repository import PlanTerms, SubscriptionRepository
from src.services import billing_rules
from src.services.clock import Clock

logger = logging.getLogger(__name__)

# How many times an application is tried again when another request moved the date in between.
MAX_APPLY_ATTEMPTS = 3

_PERIOD_LABELS = {"monthly": "mensual", "annual": "anual"}


@dataclass(frozen=True, slots=True)
class PeriodView:
    """The state of the period of an organization, as the Router publishes it."""

    state: str
    trial_ends_at: datetime | None
    payment_due_at: datetime | None
    days_remaining: int | None
    plan_id: int
    plan_name: str
    billing_period: str
    amount: Decimal
    payment_in_progress: bool | None


@dataclass(frozen=True, slots=True)
class PaymentStart:
    """The payment that was started: where to take the person, and whether it is a new charge."""

    checkout_url: str
    amount: Decimal
    billing_period: str
    # True if a new charge was created (201); False if the pending one of the period was returned (200).
    created: bool


@dataclass(frozen=True, slots=True)
class _Reconciliation:
    """What the verification of the unresolved charges found out."""

    # The payments that Pagos reports as still pending, by payment id (with their checkout address).
    pending: dict[UUID, PaymentRecord]
    # Whether some unresolved charge could not be verified (the payments API did not answer).
    unverified: bool


@dataclass(frozen=True, slots=True)
class _Context:
    """What an operation knows after the steps that both share."""

    organization: OrganizationRecord
    plan: PlanTerms
    period: SubscriptionPeriod
    amount: Decimal
    reconciliation: _Reconciliation


class SubscriptionPeriodService:
    def __init__(
        self,
        periods: SubscriptionPeriodRepository,
        subscriptions: SubscriptionRepository,
        clinics_api: ClinicsApiClient,
        payments_api: PaymentsApiClient,
        clock: Clock,
        cutoff: datetime,
        return_url: str | None = None,
    ) -> None:
        """`return_url` is the configured return address of the payments (spec 011, `PAYMENTS_RETURN_URL`):
        `None` when it is not configured, and then the charges are created exactly as before."""
        self._periods = periods
        self._subscriptions = subscriptions
        self._clinics = clinics_api
        self._payments = payments_api
        self._clock = clock
        self._cutoff = cutoff
        self._return_url = return_url

    # --- story 1: the consultation ---

    async def get_status(self, token: str, organization_id: UUID) -> PeriodView:
        """The state of the period of an organization of which the person is the owner (FR-012 to FR-015)."""
        context = await self._prepare(token, organization_id)
        return self._view(context)

    # --- spec 012: the history of charges ---

    async def list_charges(
        self,
        token: str,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[SubscriptionCharge], int]:
        """A page of the charge history of an organization of which the person is the owner.

        Only the ownership check is done (the same as `get_status`): this is a read-only history, so
        it does not create the period record nor reconcile with the payments API — a charge can show
        as `pending` here even when the full period read would have resolved it by now.

        `status` (spec 013) filters server-side; see `SubscriptionPeriodRepository.list_charges`.
        """
        await self._read_organization(token, organization_id)
        return await self._periods.list_charges(
            organization_id, page=page, page_size=page_size, status=status
        )

    # --- story 2: starting the payment ---

    async def start_payment(self, token: str, organization_id: UUID) -> PaymentStart:
        """Create the charge of the next period in the payments API and return its checkout (FR-020).

        The amount is the one of the catalog for the plan and billing period of the organization now; the
        person never sends it. Asking twice for the same period (the same payment date it settles, billing
        period and amount) gives the same pending charge and checkout; after a charge that was closed
        without being applied, or with another amount, a new charge is created (FR-022 to FR-024).

        With a return address configured (spec 011), the payment carries it and it is part of the key of
        the charge (FR-006, FR-008); without one, the payment and its key are exactly the ones of before.
        """
        context = await self._prepare(token, organization_id)
        if context.amount == 0:
            raise NothingToChargeError()

        period = context.period
        due = billing_rules.payment_due_at(period.started_at, period.trial_ends_at, period.paid_until)
        billing_period = context.organization.billing_period
        amount = context.amount

        pending = await self._periods.find_pending(organization_id, due, billing_period, amount)
        if pending is not None:
            return await self._existing(token, pending, context)

        amount_minor = billing_rules.to_minor_units(amount)
        attempt = await self._periods.count_resolved_with_terms(organization_id, due, billing_period, amount) + 1
        description = f"Suscripción {context.plan.name} — {_PERIOD_LABELS[billing_period]}"
        key = billing_rules.idempotency_key(
            organization_id, due, billing_period, amount_minor, attempt, description, self._return_url
        )
        try:
            payment = await self._payments.create_payment(
                token,
                idempotency_key=key,
                amount=amount_minor,
                currency=billing_rules.CURRENCY,
                resource_type=billing_rules.RESOURCE_TYPE,
                resource_id=str(organization_id),
                description=description,
                metadata={
                    "billing_period": billing_period,
                    "settles_due_at": due.isoformat().replace("+00:00", "Z"),
                },
                return_url=self._return_url,
            )
        except PaymentsApiUnavailable:
            raise PaymentsUnavailableError() from None

        created = True
        try:
            await self._periods.add_charge(
                organization_id=organization_id,
                payment_id=payment.id,
                amount=amount,
                billing_period=billing_period,
                settles_due_at=due,
                attempt=attempt,
                plan=context.plan.name,
            )
        except UniqueViolationError:
            # A simultaneous request registered a charge for this period first. Normally it is the very
            # same one (the same key gave the same payment); if it is another payment, the one that was
            # just created is not registered, so its checkout is never offered: the registered one is.
            if await self._periods.find_by_payment_id(payment.id) is None:
                registered = await self._periods.find_pending(organization_id, due, billing_period, amount)
                if registered is None:
                    # The charge that got there first is already resolved: nothing to offer and nothing
                    # to reuse. Trying again computes the next attempt, so it is a 503, never a 500.
                    logger.warning(
                        "Payment %s of organization %s could not be registered: a charge for the same "
                        "period was already resolved",
                        payment.id,
                        organization_id,
                    )
                    raise PaymentsUnavailableError() from None
                return await self._existing(token, registered, context)
            created = False

        if payment.status != "pending" or not payment.checkout_url:
            # It was registered, so the next reconciliation resolves it, but there is nothing to offer.
            raise PaymentsUnavailableError()
        return PaymentStart(payment.checkout_url, amount, billing_period, created)

    async def _existing(
        self, token: str, charge: SubscriptionCharge, context: _Context
    ) -> PaymentStart:
        """The checkout of the pending charge that already exists for the period."""
        payment = context.reconciliation.pending.get(charge.payment_id)
        if payment is None:  # the reconciliation did not verify it: ask now
            try:
                payment = await self._payments.get_payment(token, charge.payment_id)
            except PaymentsApiUnavailable:
                raise PaymentsUnavailableError() from None
        if payment.status != "pending" or not payment.checkout_url:
            raise PaymentsUnavailableError()
        return PaymentStart(
            payment.checkout_url, context.amount, context.organization.billing_period, False
        )

    # --- the steps that the operations share ---

    async def _prepare(self, token: str, organization_id: UUID) -> _Context:
        organization = await self._read_organization(token, organization_id)
        plan = await self._subscriptions.get_plan_terms(organization.subscription_id)
        if plan is None:
            raise OrganizationSubscriptionNotFoundError()
        await self._period_of(organization, plan)  # the first consultation creates the record (FR-007)
        reconciliation = await self._reconcile(token, organization_id)
        # Read after the reconciliation, never before: it may have moved the date, and a rollback of the
        # session expires whatever was read earlier.
        period = await self._periods.get(organization_id)
        if period is None:  # nothing deletes a period, and `_period_of` has just created it if it was absent
            raise RuntimeError("The period of the organization does not exist after creating it")
        return _Context(organization, plan, period, self._amount_of(organization, plan), reconciliation)

    async def _read_organization(self, token: str, organization_id: UUID) -> OrganizationRecord:
        """The organization, which proves that the person is its owner (FR-003): the access fails closed."""
        try:
            return await self._clinics.get_organization(token, organization_id)
        except OrganizationNotFound:
            raise OrganizationNotFoundError(organization_id) from None
        except ClinicsApiUnavailable:
            raise OrganizationCheckUnavailableError() from None

    async def _period_of(self, organization: OrganizationRecord, plan: PlanTerms) -> SubscriptionPeriod:
        """The record of the organization; the first time, it is created with the dates that apply now.

        The trial lasts the days of the plan at this moment and, once fixed, nothing changes it (FR-009).
        """
        period = await self._periods.get(organization.id)
        if period is not None:
            return period
        started_at = billing_rules.started_at_of(organization.created_at, self._cutoff)
        trial_ends_at = billing_rules.trial_ends_at_of(started_at, plan.trial_days)
        logger.info("Creating the subscription period of organization %s", organization.id)
        return await self._periods.create_if_absent(organization.id, started_at, trial_ends_at)

    @staticmethod
    def _amount_of(organization: OrganizationRecord, plan: PlanTerms) -> Decimal:
        """The price of the plan for the billing period of the organization (FR-016)."""
        return plan.monthly_price if organization.billing_period == "monthly" else plan.annual_price

    # --- story 3: the reconciliation of the charges ---

    async def _reconcile(self, token: str, organization_id: UUID) -> _Reconciliation:
        """Verify the unresolved charges with the payments API and settle the ones that are decided (FR-026).

        Pagos does not announce when a payment changes, and nothing runs in the background (FR-012), so
        this is where an approved payment is found. All the charges are asked about at once; each answer
        applies or closes its charge (`_settle`); an answer that cannot be had leaves the charge unresolved
        and the person is told that it could not be verified (`unverified`).
        """
        charges = await self._periods.list_pending(organization_id)
        if not charges:
            return _Reconciliation(pending={}, unverified=False)
        answers = await asyncio.gather(
            *(self._payments.get_payment(token, charge.payment_id) for charge in charges),
            return_exceptions=True,
        )
        pending: dict[UUID, PaymentRecord] = {}
        unverified = False
        # Oldest first: the order in which the approved charges are applied (the second continues the first).
        for charge, answer in zip(charges, answers, strict=True):
            if isinstance(answer, PaymentsApiUnavailable):
                unverified = True
                continue
            if isinstance(answer, BaseException):
                raise answer  # a bug, not a failure of the other API: it must not be swallowed
            decided = await self._settle(charge, answer)
            if decided is None:
                unverified = True  # approved, but it could not be applied now: the next request tries again
            elif decided:
                pending[charge.payment_id] = answer
        return _Reconciliation(pending, unverified)

    async def _settle(self, charge: SubscriptionCharge, payment: PaymentRecord) -> bool | None:
        """Apply or close the charge according to what Pagos reports (FR-028).

        `True` if it is still pending, `False` if it is resolved and `None` if it is approved but could not
        be applied this time (it stays pending and the next request tries again).
        """
        status = payment.status
        if status == "pending":
            return True
        if status == "approved":
            if self._matches(charge, payment):
                return False if await self._apply(charge, payment) else None
            else:
                # Left on record for its review: the ids only, never the token nor personal data.
                logger.warning(
                    "Charge %s of organization %s closed as inconsistent: "
                    "the approved payment does not match what was requested",
                    charge.id,
                    charge.organization_id,
                )
                await self._close(charge, ClosedReason.INCONSISTENT)
        elif status == "rejected":
            await self._close(charge, ClosedReason.REJECTED)
        elif status == "cancelled":
            await self._close(charge, ClosedReason.CANCELLED)
        else:  # partially_refunded, refunded: Pagos no longer reports it as approved (decision D3)
            await self._close(charge, ClosedReason.REFUNDED)
        return False

    @staticmethod
    def _matches(charge: SubscriptionCharge, payment: PaymentRecord) -> bool:
        """Whether the payment is what this service asked for: the amount, the currency and the reference (FR-027)."""
        return (
            payment.id == charge.payment_id
            and payment.amount == billing_rules.to_minor_units(charge.amount)
            and payment.currency == charge.currency
            and payment.resource_type == billing_rules.RESOURCE_TYPE
            and payment.resource_id == str(charge.organization_id)
        )

    async def _close(self, charge: SubscriptionCharge, reason: ClosedReason) -> None:
        await self._periods.close_charge(charge.id, reason, self._clock.now())

    async def _apply(self, charge: SubscriptionCharge, payment: PaymentRecord) -> bool:
        """Move the payment date by the period that the approved payment covers, exactly once (FR-032).

        The approval is the date that Pagos reports, never later than this service's clock (FR-031). The
        period is computed from the date that was current when the period was read; if another request
        moved that date in between, the Repository says so (`STALE`) and the period is computed again
        from the new date. An application that keeps losing that race stays pending: the next request
        tries again. Returns whether the charge is resolved (by this request or by another one).
        """
        approved_at = min(payment.updated_at, self._clock.now())
        for _ in range(MAX_APPLY_ATTEMPTS):
            period = await self._periods.get(charge.organization_id)
            if period is None:  # a charge cannot exist without the period of its organization
                return False
            due = billing_rules.payment_due_at(period.started_at, period.trial_ends_at, period.paid_until)
            start, end = billing_rules.covered_period(due, approved_at, charge.billing_period)
            outcome = await self._periods.apply_charge(
                charge_id=charge.id,
                organization_id=charge.organization_id,
                expected_paid_until=period.paid_until,
                period_starts_at=start,
                period_ends_at=end,
                resolved_at=self._clock.now(),
            )
            if outcome is not ApplyOutcome.STALE:
                return True
        logger.warning(
            "Charge %s of organization %s could not be applied after %s attempts: "
            "another request kept moving the date; the next request will try again",
            charge.id,
            charge.organization_id,
            MAX_APPLY_ATTEMPTS,
        )
        return False

    def _view(self, context: _Context) -> PeriodView:
        now = self._clock.now()
        period = context.period
        due = billing_rules.payment_due_at(period.started_at, period.trial_ends_at, period.paid_until)
        state = billing_rules.period_state(now, context.amount, period.trial_ends_at, due)
        no_charge = state == "no_charge"
        reconciliation = context.reconciliation
        if reconciliation.pending:
            in_progress: bool | None = True
        else:
            in_progress = None if reconciliation.unverified else False
        return PeriodView(
            state=state,
            trial_ends_at=period.trial_ends_at,
            payment_due_at=None if no_charge else due,
            days_remaining=None if no_charge else billing_rules.days_remaining(due, now),
            plan_id=context.plan.id,
            plan_name=context.plan.name,
            billing_period=context.organization.billing_period,
            amount=context.amount,
            payment_in_progress=in_progress,
        )

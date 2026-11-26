"""Support for the tests of the subscription periods (spec 010): doubles, builders and an HTTP helper.

No fixtures here (they live in `conftest.py`, like `tests/helpers.py`). The doubles replace what the
Service talks to — the clinics API, the payments API, the Repository of the periods and the catalog of
plans — and keep the semantics of the real ones (the Repository double applies a charge with the same
claim and compare-and-swap), so the Service tests exercise the real rules with no database and no
network. `BillingApi` is the real application over HTTP with the real database and the three simulated
APIs, for the contract tests.
"""

import itertools
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.integrations.clinics_api import OrganizationRecord
from src.integrations.errors import ClinicsApiUnavailable, OrganizationNotFound, PaymentsApiUnavailable
from src.integrations.payments_api import PaymentRecord
from src.models.subscription_charge import (
    CHARGE_PAYMENT_ID_KEY,
    CHARGE_PENDING_TERMS_KEY,
    CHARGE_TERMS_ATTEMPT_KEY,
    ChargeStatus,
    SubscriptionCharge,
)
from src.models.subscription_period import SubscriptionPeriod
from src.repositories.errors import ForeignKeyViolationError, UniqueViolationError
from src.repositories.subscription_period_repository import ApplyOutcome
from src.repositories.subscription_repository import PlanTerms
from src.services.billing_rules import RESOURCE_TYPE
from tests.health_support import FakeClock
from tests.helpers import TEST_TOKEN, fetch_all, grant, insert_subscription

ORG_ID = uuid.UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")
OTHER_ORG_ID = uuid.UUID("1f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")
PERIODS_URL = "/api/v1/subscription-periods"
PERMISSIONS = ("subscription_periods:read", "subscription_periods:write")
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def at(text: str) -> datetime:
    """`2026-12-04T15:30:00Z` → an aware datetime in UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def make_organization(
    *,
    organization_id: uuid.UUID = ORG_ID,
    subscription_id: int = 1,
    billing_period: str = "monthly",
    created_at: datetime | str = "2026-11-20T15:30:00Z",
) -> OrganizationRecord:
    return OrganizationRecord(
        id=organization_id,
        subscription_id=subscription_id,
        billing_period=billing_period,
        created_at=at(created_at) if isinstance(created_at, str) else created_at,
    )


def make_plan(
    plan_id: int = 1,
    *,
    name: str = "Plan Individual",
    trial_days: int = 14,
    monthly_price: str = "499.00",
    annual_price: str = "4990.00",
) -> PlanTerms:
    return PlanTerms(
        id=plan_id,
        name=name,
        trial_days=trial_days,
        monthly_price=Decimal(monthly_price),
        annual_price=Decimal(annual_price),
    )


def make_payment(
    payment_id: uuid.UUID,
    *,
    status: str = "pending",
    amount: int = 49900,
    currency: str = "MXN",
    resource_type: str = RESOURCE_TYPE,
    resource_id: str | None = None,
    updated_at: datetime | str = "2026-12-01T10:00:00Z",
) -> PaymentRecord:
    return PaymentRecord(
        id=payment_id,
        status=status,
        amount=amount,
        currency=currency,
        resource_type=resource_type,
        resource_id=resource_id if resource_id is not None else str(ORG_ID),
        checkout_url=f"https://checkout.example.test/pay/{payment_id}" if status == "pending" else None,
        updated_at=at(updated_at) if isinstance(updated_at, str) else updated_at,
    )


# --- doubles of what the Service talks to ---


class FakeOrganizationsApi:
    """Double of `ClinicsApiClient.get_organization`: answers what the test configures."""

    def __init__(self, organization: OrganizationRecord | None = None, *, fail: bool = False) -> None:
        self.organization = organization
        self.fail = fail
        self.calls: list[tuple[str, uuid.UUID]] = []

    async def get_organization(self, token: str, organization_id: uuid.UUID) -> OrganizationRecord:
        self.calls.append((token, organization_id))
        if self.fail:
            raise ClinicsApiUnavailable()
        if self.organization is None or self.organization.id != organization_id:
            raise OrganizationNotFound()
        return self.organization


class FakePaymentsApi:
    """Double of `PaymentsApiClient`: idempotent creation, payments whose status the test changes."""

    def __init__(self) -> None:
        self.payments: dict[uuid.UUID, PaymentRecord] = {}
        self.keys: dict[str, tuple[str, uuid.UUID]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.get_calls: list[tuple[str, uuid.UUID]] = []
        self.fail_create = False
        self.fail_get: bool | set[uuid.UUID] = False
        self.crash_get = False  # a programming error, not a failure of the other API
        self.create_without_checkout = False
        # A payments API that gives a new payment for a key that it already knows: it must not happen,
        # and the Service must still never offer a payment that it did not register.
        self.ignore_idempotency = False
        # The payment is created but the answer never arrives (once): the person is told to try again.
        self.lose_answer = False
        self._ids = itertools.count(1)

    def _new_id(self) -> uuid.UUID:
        return uuid.UUID(f"00000000-0000-4000-8000-{next(self._ids):012x}")

    async def create_payment(
        self,
        token: str,
        *,
        idempotency_key: str,
        amount: int,
        currency: str,
        resource_type: str,
        resource_id: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        return_url: str | None = None,
    ) -> PaymentRecord:
        self.create_calls.append(
            {
                "token": token,
                "idempotency_key": idempotency_key,
                "amount": amount,
                "currency": currency,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "description": description,
                "metadata": metadata,
                "return_url": return_url,
            }
        )
        if self.fail_create:
            raise PaymentsApiUnavailable()
        # The return address is part of the body, so of the fingerprint too, as in Pagos (spec 011).
        fingerprint = repr((amount, currency, resource_type, resource_id, description, metadata, return_url))
        known = None if self.ignore_idempotency else self.keys.get(idempotency_key)
        if known is not None:
            if known[0] != fingerprint:
                raise PaymentsApiUnavailable()  # a 409 is never taken for the old payment
            return self._read(known[1])
        payment_id = self._new_id()
        self.payments[payment_id] = make_payment(
            payment_id,
            amount=amount,
            currency=currency,
            resource_type=resource_type,
            resource_id=resource_id,
            updated_at=_EPOCH,
        )
        stored_as = idempotency_key if idempotency_key not in self.keys else f"{idempotency_key}#{len(self.keys)}"
        self.keys[stored_as] = (fingerprint, payment_id)
        if self.lose_answer:
            self.lose_answer = False
            raise PaymentsApiUnavailable()
        return self._read(payment_id)

    async def get_payment(self, token: str, payment_id: uuid.UUID) -> PaymentRecord:
        self.get_calls.append((token, payment_id))
        if self.crash_get:
            raise RuntimeError("a bug, not an unavailable payments API")
        if self.fail_get is True or (isinstance(self.fail_get, set) and payment_id in self.fail_get):
            raise PaymentsApiUnavailable()
        if payment_id not in self.payments:
            raise PaymentsApiUnavailable()  # a 404
        return self._read(payment_id)

    def _read(self, payment_id: uuid.UUID) -> PaymentRecord:
        payment = self.payments[payment_id]
        if self.create_without_checkout and payment.status == "pending":
            return replace(payment, checkout_url=None)
        return payment

    # --- helpers for the tests ---

    def set_status(
        self,
        payment_id: uuid.UUID,
        status: str,
        *,
        amount: int | None = None,
        currency: str | None = None,
        resource_id: str | None = None,
        updated_at: datetime | str | None = None,
    ) -> None:
        payment = self.payments[payment_id]
        moment = at(updated_at) if isinstance(updated_at, str) else updated_at
        self.payments[payment_id] = make_payment(
            payment_id,
            status=status,
            amount=payment.amount if amount is None else amount,
            currency=payment.currency if currency is None else currency,
            resource_type=payment.resource_type,
            resource_id=payment.resource_id if resource_id is None else resource_id,
            updated_at=moment or payment.updated_at,
        )

    def add_foreign_payment(self, *, status: str = "approved", amount: int = 49900) -> uuid.UUID:
        """A payment created in the payments API by another route: no charge refers to it."""
        payment_id = self._new_id()
        self.payments[payment_id] = make_payment(payment_id, status=status, amount=amount)
        return payment_id

    def created(self) -> list[uuid.UUID]:
        return [payment_id for _, payment_id in self.keys.values()]


class FakePlanCatalog:
    """Double of the part of `SubscriptionRepository` that the Service uses: `get_plan_terms`."""

    def __init__(self, *plans: PlanTerms) -> None:
        self.plans = {plan.id: plan for plan in plans}
        self.calls = 0

    async def get_plan_terms(self, subscription_id: int) -> PlanTerms | None:
        self.calls += 1
        return self.plans.get(subscription_id)


class FakePeriodRepository:
    """Double of `SubscriptionPeriodRepository` that keeps real model objects in memory.

    It keeps the semantics that the Service relies on: `create_if_absent` is idempotent, a payment and the
    conditions with their attempt are unique (and so are the conditions of an unresolved charge), a charge
    is claimed once and the date moves only if it is still what the caller read. `before_apply` lets a
    test change the world just before an application, as a simultaneous request would.
    """

    def __init__(self, now: datetime = _EPOCH) -> None:
        self.periods: dict[uuid.UUID, SubscriptionPeriod] = {}
        self.charges: dict[uuid.UUID, SubscriptionCharge] = {}
        self.calls: Counter[str] = Counter()
        self.before_apply: list[Callable[[], None]] = []
        self._now = now
        self._sequence = itertools.count(1)

    # --- reads ---

    async def get(self, organization_id: uuid.UUID) -> SubscriptionPeriod | None:
        self.calls["get"] += 1
        return self.periods.get(organization_id)

    async def list_pending(self, organization_id: uuid.UUID) -> list[SubscriptionCharge]:
        self.calls["list_pending"] += 1
        return sorted(
            (
                charge
                for charge in self.charges.values()
                if charge.organization_id == organization_id and charge.status == ChargeStatus.PENDING
            ),
            key=lambda charge: (charge.created_at, str(charge.id)),
        )

    async def find_pending(
        self, organization_id: uuid.UUID, settles_due_at: datetime, billing_period: str, amount: Decimal
    ) -> SubscriptionCharge | None:
        self.calls["find_pending"] += 1
        for charge in await self.list_pending(organization_id):
            if (charge.settles_due_at, charge.billing_period, charge.amount) == (
                settles_due_at,
                billing_period,
                amount,
            ):
                return charge
        return None

    async def find_by_payment_id(self, payment_id: uuid.UUID) -> SubscriptionCharge | None:
        self.calls["find_by_payment_id"] += 1
        return next((c for c in self.charges.values() if c.payment_id == payment_id), None)

    async def count_resolved_with_terms(
        self, organization_id: uuid.UUID, settles_due_at: datetime, billing_period: str, amount: Decimal
    ) -> int:
        self.calls["count_resolved_with_terms"] += 1
        return sum(
            1
            for charge in self.charges.values()
            if charge.organization_id == organization_id
            and charge.status != ChargeStatus.PENDING
            and (charge.settles_due_at, charge.billing_period, charge.amount)
            == (settles_due_at, billing_period, amount)
        )

    # --- writes ---

    async def create_if_absent(
        self, organization_id: uuid.UUID, started_at: datetime, trial_ends_at: datetime | None
    ) -> SubscriptionPeriod:
        self.calls["create_if_absent"] += 1
        if organization_id not in self.periods:
            self.periods[organization_id] = SubscriptionPeriod(
                organization_id=organization_id,
                started_at=started_at,
                trial_ends_at=trial_ends_at,
                paid_until=None,
                created_at=self._now,
                updated_at=self._now,
            )
        return self.periods[organization_id]

    async def add_charge(
        self,
        *,
        organization_id: uuid.UUID,
        payment_id: uuid.UUID,
        amount: Decimal,
        billing_period: str,
        settles_due_at: datetime,
        attempt: int,
        currency: str = "MXN",
        plan: str | None = None,
    ) -> SubscriptionCharge:
        self.calls["add_charge"] += 1
        if organization_id not in self.periods:
            raise ForeignKeyViolationError("subscription_charges_organization_id_fkey")
        if any(c.payment_id == payment_id for c in self.charges.values()):
            raise UniqueViolationError(CHARGE_PAYMENT_ID_KEY)
        if any(
            (c.organization_id, c.settles_due_at, c.billing_period, c.amount, c.attempt)
            == (organization_id, settles_due_at, billing_period, amount, attempt)
            for c in self.charges.values()
        ):
            raise UniqueViolationError(CHARGE_TERMS_ATTEMPT_KEY)
        if any(
            (c.organization_id, c.settles_due_at, c.billing_period, c.amount, c.status)
            == (organization_id, settles_due_at, billing_period, amount, ChargeStatus.PENDING)
            for c in self.charges.values()
        ):
            raise UniqueViolationError(CHARGE_PENDING_TERMS_KEY)
        number = next(self._sequence)
        charge = SubscriptionCharge(
            id=uuid.UUID(f"00000000-0000-4000-9000-{number:012x}"),
            organization_id=organization_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            billing_period=billing_period,
            settles_due_at=settles_due_at,
            attempt=attempt,
            plan=plan,
            status=ChargeStatus.PENDING,
            closed_reason=None,
            period_starts_at=None,
            period_ends_at=None,
            resolved_at=None,
            created_at=_EPOCH + timedelta(seconds=number),
            updated_at=_EPOCH + timedelta(seconds=number),
        )
        self.charges[charge.id] = charge
        return charge

    async def close_charge(self, charge_id: uuid.UUID, reason: str, resolved_at: datetime) -> bool:
        self.calls["close_charge"] += 1
        charge = self.charges.get(charge_id)
        if charge is None or charge.status != ChargeStatus.PENDING:
            return False
        charge.status = ChargeStatus.CLOSED
        charge.closed_reason = str(reason)
        charge.resolved_at = resolved_at
        return True

    async def apply_charge(
        self,
        *,
        charge_id: uuid.UUID,
        organization_id: uuid.UUID,
        expected_paid_until: datetime | None,
        period_starts_at: datetime,
        period_ends_at: datetime,
        resolved_at: datetime,
    ) -> ApplyOutcome:
        self.calls["apply_charge"] += 1
        if self.before_apply:
            self.before_apply.pop(0)()  # a simultaneous request got in first
        charge = self.charges.get(charge_id)
        if charge is None or charge.organization_id != organization_id or charge.status != ChargeStatus.PENDING:
            return ApplyOutcome.ALREADY_RESOLVED
        period = self.periods[organization_id]
        if period.paid_until != expected_paid_until:
            return ApplyOutcome.STALE  # nothing was claimed
        charge.status = ChargeStatus.APPLIED
        charge.period_starts_at = period_starts_at
        charge.period_ends_at = period_ends_at
        charge.resolved_at = resolved_at
        period.paid_until = period_ends_at
        return ApplyOutcome.APPLIED

    async def list_charges(
        self, organization_id: uuid.UUID, *, page: int, page_size: int, status: str | None = None
    ) -> tuple[list[SubscriptionCharge], int]:
        self.calls["list_charges"] += 1
        charges = self.charges_of(organization_id)
        if status is not None:
            charges = [c for c in charges if c.status == status]
        charges.reverse()  # most recent first, as the real Repository orders them
        total = len(charges)
        start = (page - 1) * page_size
        return charges[start : start + page_size], total

    # --- helpers for the tests ---

    def charges_of(self, organization_id: uuid.UUID = ORG_ID) -> list[SubscriptionCharge]:
        return sorted(
            (c for c in self.charges.values() if c.organization_id == organization_id),
            key=lambda charge: charge.created_at,
        )


@dataclass
class World:
    """Everything a Service test needs, wired together."""

    service: Any
    organizations: FakeOrganizationsApi
    payments: FakePaymentsApi
    periods: FakePeriodRepository
    plans: FakePlanCatalog
    clock: FakeClock

    def at(self, text: str) -> None:
        self.clock.set(at(text))


def make_world(
    *,
    now: str = "2026-11-25T15:30:00Z",
    organization: OrganizationRecord | None = None,
    plan: PlanTerms | None = None,
    cutoff: str = "2020-01-01T00:00:00Z",
    return_url: str | None = None,
) -> World:
    """A Service with doubles: the organization of `make_organization()` on the plan of `make_plan()`.

    `return_url` is the configured return address of the payments (spec 011); by default there is none.
    """
    from src.services.subscription_period_service import SubscriptionPeriodService

    organizations = FakeOrganizationsApi(organization or make_organization())
    payments = FakePaymentsApi()
    periods = FakePeriodRepository()
    plans = FakePlanCatalog(plan or make_plan())
    clock = FakeClock(at(now))
    service = SubscriptionPeriodService(
        periods=periods,
        subscriptions=plans,
        clinics_api=organizations,
        payments_api=payments,
        clock=clock,
        cutoff=at(cutoff),
        return_url=return_url,
    )
    return World(service, organizations, payments, periods, plans, clock)


# --- the application over HTTP (contract tests) ---


class BillingApi:
    """The real application with the real database and the three simulated APIs, ready to be called.

    `client` sends the token of `TEST_TOKEN` (registered with the two permissions of the subscription
    periods); `anonymous` sends none. The clock is a `FakeClock` that each test moves. The simulations
    and the database are reachable to prepare scenarios and to see what happened.
    """

    def __init__(
        self,
        app: Any,
        client: httpx.AsyncClient,
        anonymous: httpx.AsyncClient,
        users_stub: httpx.AsyncClient,
        clinics_stub: httpx.AsyncClient,
        payments_stub: httpx.AsyncClient,
        engine: AsyncEngine,
        clock: FakeClock,
        timeouts: dict[str, float] | None = None,
    ) -> None:
        self.app = app
        self.client = client
        self.anonymous = anonymous
        self.users_stub = users_stub
        self.clinics_stub = clinics_stub
        self.payments_stub = payments_stub
        self.engine = engine
        self.clock = clock
        self.timeouts = timeouts if timeouts is not None else {}

    # --- the two operations ---

    async def get_period(self, organization_id: uuid.UUID | str = ORG_ID, **kwargs: Any) -> httpx.Response:
        return await self.client.get(f"{PERIODS_URL}/{organization_id}", **kwargs)

    async def start_payment(self, organization_id: uuid.UUID | str = ORG_ID, **kwargs: Any) -> httpx.Response:
        return await self.client.post(f"{PERIODS_URL}/{organization_id}/payments", **kwargs)

    async def list_charges(self, organization_id: uuid.UUID | str = ORG_ID, **kwargs: Any) -> httpx.Response:
        return await self.client.get(f"{PERIODS_URL}/{organization_id}/charges", **kwargs)

    # --- preparing scenarios ---

    async def add_plan(self, **values: Any) -> int:
        """A plan in the catalog (see `insert_subscription`); the defaults are the ones of `make_plan`."""
        defaults = {"name": "Plan Individual", "trial_days": 14, "monthly_price": "499.00", "annual_price": "4990.00"}
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await insert_subscription(session, **{**defaults, **values})

    async def register_organization(
        self,
        subscription_id: int,
        *,
        organization_id: uuid.UUID = ORG_ID,
        billing_period: str = "monthly",
        created_at: datetime | str | None = None,
        owner_token: str = TEST_TOKEN,
    ) -> None:
        created = created_at or self.clock.now() - timedelta(days=5)
        response = await self.clinics_stub.post(
            "/__test__/organizations",
            json={
                "id": str(organization_id),
                "subscription_id": subscription_id,
                "billing_period": billing_period,
                "created_at": created if isinstance(created, str) else iso(created),
                "owner_token": owner_token,
            },
        )
        assert response.status_code == 200

    async def set_payment_status(
        self,
        payment_id: str | uuid.UUID,
        status: str,
        *,
        amount: int | None = None,
        currency: str | None = None,
        updated_at: datetime | str | None = None,
    ) -> None:
        body: dict[str, Any] = {"status": status}
        if amount is not None:
            body["amount"] = amount
        if currency is not None:
            body["currency"] = currency
        if updated_at is not None:
            body["updated_at"] = updated_at if isinstance(updated_at, str) else iso(updated_at)
        response = await self.payments_stub.post(f"/__test__/payments/{payment_id}/status", json=body)
        assert response.status_code == 200, response.text

    async def create_foreign_payment(
        self, resource_id: uuid.UUID | str = ORG_ID, *, status: str = "approved", amount: int = 49900
    ) -> str:
        response = await self.payments_stub.post(
            "/__test__/payments", json={"resource_id": str(resource_id), "status": status, "amount": amount}
        )
        assert response.status_code == 200
        return response.json()["id"]

    async def set_permissions(self, permissions: Sequence[str]) -> None:
        await grant(self.users_stub, TEST_TOKEN, permissions)

    async def payments_fault(
        self, mode: str, count: int = 1, operation: str = "any", delay: float = 30
    ) -> None:
        response = await self.payments_stub.post(
            "/__test__/faults",
            json={"mode": mode, "count": count, "delay_seconds": delay, "operation": operation},
        )
        assert response.status_code == 200

    async def clinics_fault(
        self, mode: str, count: int = 1, operation: str = "organizations", delay: float = 30
    ) -> None:
        response = await self.clinics_stub.post(
            "/__test__/faults",
            json={"mode": mode, "count": count, "delay_seconds": delay, "operation": operation},
        )
        assert response.status_code == 200

    async def users_fault(self, mode: str, count: int = 1, delay: float = 30) -> None:
        response = await self.users_stub.post(
            "/__test__/faults",
            json={"mode": mode, "count": count, "delay_seconds": delay, "operation": "check"},
        )
        assert response.status_code == 200

    # --- seeing what happened ---

    async def payments(self) -> list[dict[str, Any]]:
        return (await self.payments_stub.get("/__test__/payments")).json()

    async def payments_calls(self) -> list[dict[str, Any]]:
        return (await self.payments_stub.get("/__test__/calls")).json()

    async def clinics_calls(self) -> list[dict[str, Any]]:
        return (await self.clinics_stub.get("/__test__/calls")).json()

    async def users_calls(self) -> list[dict[str, Any]]:
        return (await self.users_stub.get("/__test__/calls")).json()

    async def periods(self) -> list[tuple[Any, ...]]:
        return await fetch_all(
            self.engine,
            "SELECT organization_id, started_at, trial_ends_at, paid_until FROM subscription_periods "
            "ORDER BY organization_id",
        )

    async def charges(self) -> list[tuple[Any, ...]]:
        return await fetch_all(
            self.engine,
            "SELECT organization_id, payment_id, amount, currency, billing_period, settles_due_at, attempt, "
            "status, closed_reason, period_starts_at, period_ends_at FROM subscription_charges "
            "ORDER BY created_at, id",
        )

    async def snapshot(self) -> list[tuple[Any, ...]]:
        """Both tables, to prove that a request changed nothing."""
        return [
            *await fetch_all(
                self.engine, "SELECT * FROM subscription_periods ORDER BY organization_id"
            ),
            *await fetch_all(self.engine, "SELECT * FROM subscription_charges ORDER BY created_at, id"),
        ]

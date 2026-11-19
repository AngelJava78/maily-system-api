"""In-memory doubles of the collaborators of the Services (Principle V).

Each user story extends this module: the Repository double implements every operation of
`SubscriptionRepository` so the Service tests never touch the database.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from src.clinic_modules import PATIENTS_KEY
from src.integrations.clinics_api import ClinicSubscriptionInfo
from src.integrations.errors import (
    ClinicsApiNotFound,
    ClinicsApiUnavailable,
    PaymentsApiIdempotencyConflict,
    PaymentsApiPermissionDenied,
    PaymentsApiRejectedToken,
    PaymentsApiUnavailable,
    UsersApiRejectedToken,
    UsersApiUnavailable,
)
from src.integrations.payments_api import PaymentRecord
from src.integrations.users_api import CallerAccess
from src.models.clinic_subscription_charge import ClinicSubscriptionCharge
from src.models.subscription import SUBSCRIPTION_NAME_INDEX, Subscription
from src.models.subscription_module import SubscriptionModule
from src.models.subscription_status import SubscriptionStatus
from src.models.subscription_type import SubscriptionType
from src.repositories.errors import UniqueViolationError

STATUS_NAMES = {1: "Activa", 2: "Inactiva", 3: "Bloqueada", 4: "Eliminada", 5: "Manual"}
TYPE_NAMES = {1: "Individual", 2: "Empresarial"}
DELETED = 4
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FakeUsersApi:
    """Double of `UsersApiClient`: records the calls and answers what the test configures."""

    def __init__(
        self,
        *,
        allowed: bool = True,
        rejected_code: str | None = None,
        unavailable: bool = False,
        clinic_module_keys: frozenset[str] = frozenset({PATIENTS_KEY}),
        modules_unavailable: bool = False,
        access: CallerAccess | None = None,
    ) -> None:
        self.allowed = allowed
        self.rejected_code = rejected_code
        self.unavailable = unavailable
        self.clinic_module_keys = clinic_module_keys
        self.modules_unavailable = modules_unavailable
        # spec 006: what get_current_access (GET /me) answers.
        self.access = access
        self.calls: list[tuple[str, str]] = []
        # Separate from `calls`: list_clinic_module_keys is a different operation of the same API
        # (research R4), and tests need to tell the two apart (e.g. "no call was made for modules").
        self.module_calls: list[str] = []
        self.access_calls: list[str] = []

    async def check_permission(self, token: str, permission: str) -> bool:
        self.calls.append((token, permission))
        if self.unavailable:
            raise UsersApiUnavailable()
        if self.rejected_code is not None:
            raise UsersApiRejectedToken(self.rejected_code)
        return self.allowed

    async def get_current_access(self, token: str) -> CallerAccess:
        self.access_calls.append(token)
        if self.unavailable:
            raise UsersApiUnavailable()
        if self.rejected_code is not None:
            raise UsersApiRejectedToken(self.rejected_code)
        assert self.access is not None, "configure `access` for a successful get_current_access"
        return self.access

    async def list_clinic_module_keys(self, token: str) -> frozenset[str]:
        self.module_calls.append(token)
        if self.modules_unavailable:
            raise UsersApiUnavailable()
        if self.rejected_code is not None:
            raise UsersApiRejectedToken(self.rejected_code)
        return self.clinic_module_keys


class FakeClinicsApi:
    """Double of `ClinicsApiClient`: `counts` only holds subscriptions with at least one clinic.

    `clinic_subscription` configures what `get_clinic_subscription` (spec 010, research R6)
    answers: a `ClinicSubscriptionInfo` for success, or one of the two failure flags.
    """

    def __init__(
        self,
        counts: Mapping[int, int] | None = None,
        *,
        fail: bool = False,
        clinic_subscription: ClinicSubscriptionInfo | None = None,
        clinic_subscription_not_found: bool = False,
        clinic_subscription_unavailable: bool = False,
    ) -> None:
        self.counts = dict(counts or {})
        self.fail = fail
        self.clinic_subscription = clinic_subscription
        self.clinic_subscription_not_found = clinic_subscription_not_found
        self.clinic_subscription_unavailable = clinic_subscription_unavailable
        self.calls: list[tuple[str, Sequence[int] | None]] = []
        self.clinic_subscription_calls: list[tuple[str, str]] = []

    async def get_counts(
        self, token: str, subscription_ids: Sequence[int] | None = None
    ) -> dict[int, int]:
        self.calls.append((token, subscription_ids))
        if self.fail:
            raise ClinicsApiUnavailable()
        return {
            subscription_id: count
            for subscription_id, count in self.counts.items()
            if count >= 1 and (subscription_ids is None or subscription_id in subscription_ids)
        }

    async def get_clinic_subscription(
        self, token: str, clinic_subscription_id: str
    ) -> ClinicSubscriptionInfo:
        self.clinic_subscription_calls.append((token, clinic_subscription_id))
        if self.clinic_subscription_unavailable:
            raise ClinicsApiUnavailable()
        if self.clinic_subscription_not_found:
            raise ClinicsApiNotFound()
        assert self.clinic_subscription is not None, "configure `clinic_subscription` for success"
        return self.clinic_subscription


class FakeSubscriptionRepository:
    """Double of `SubscriptionRepository` that keeps real `Subscription` objects in memory."""

    def __init__(self) -> None:
        self.items: dict[int, Subscription] = {}
        self.calls: Counter[str] = Counter()
        self._next_id = 1

    # --- helpers for the tests ---

    def add(
        self,
        *,
        name: str = "Plan",
        status_id: int = 1,
        subscription_type_id: int = 1,
        monthly_price: str | Decimal = "100.00",
        annual_price: str | Decimal = "1000.00",
        trial_days: int = 0,
        self_service: bool = False,
        module_keys: Iterable[str] = (PATIENTS_KEY,),
        description: str | None = None,
        other_features: Iterable[str] = (),
        consulting_rooms_limit: int = 1,
        doctors_limit: int = 1,
        assistants_limit: int = 1,
        new_patients_per_year_limit: int = 100,
        clinics_limit: int = 1,
        created_at: datetime | None = None,
    ) -> Subscription:
        subscription_id = self._next_id
        self._next_id += 1
        moment = created_at or _EPOCH + timedelta(seconds=subscription_id)
        subscription = Subscription(
            id=subscription_id,
            name=name,
            description=description,
            subscription_type_id=subscription_type_id,
            monthly_price=Decimal(str(monthly_price)).quantize(Decimal("0.01")),
            annual_price=Decimal(str(annual_price)).quantize(Decimal("0.01")),
            trial_days=trial_days,
            self_service=self_service,
            other_features=list(other_features),
            consulting_rooms_limit=consulting_rooms_limit,
            doctors_limit=doctors_limit,
            assistants_limit=assistants_limit,
            new_patients_per_year_limit=new_patients_per_year_limit,
            clinics_limit=clinics_limit,
            status_id=status_id,
            created_at=moment,
            updated_at=moment,
        )
        subscription.status = SubscriptionStatus(id=status_id, name=STATUS_NAMES[status_id])
        subscription.subscription_type = SubscriptionType(
            id=subscription_type_id, name=TYPE_NAMES[subscription_type_id]
        )
        subscription.modules = [SubscriptionModule(module_key=key) for key in sorted(module_keys)]
        self.items[subscription_id] = subscription
        return subscription

    def _is_name_taken(self, name: str, *, excluding: int | None = None) -> bool:
        return any(
            s.name.lower() == name.lower() and s.status_id != DELETED and s.id != excluding
            for s in self.items.values()
        )

    def _current(self, subscription_id: int) -> Subscription | None:
        subscription = self.items.get(subscription_id)
        if subscription is None or subscription.status_id == DELETED:
            return None
        return subscription

    def _set_status(self, subscription: Subscription, status_id: int) -> None:
        subscription.status_id = status_id
        subscription.status = SubscriptionStatus(id=status_id, name=STATUS_NAMES[status_id])
        subscription.updated_at = datetime.now(UTC)

    # --- the interface of SubscriptionRepository ---

    async def list_current(self) -> list[Subscription]:
        self.calls["list_current"] += 1
        current = [s for s in self.items.values() if s.status_id != DELETED]
        return sorted(current, key=lambda s: (s.created_at, s.id))

    async def get_current_by_id(self, subscription_id: int) -> Subscription | None:
        self.calls["get_current_by_id"] += 1
        return self._current(subscription_id)

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
        self.calls["create"] += 1
        if self._is_name_taken(name):
            raise UniqueViolationError(SUBSCRIPTION_NAME_INDEX)
        return self.add(
            name=name,
            description=description,
            subscription_type_id=subscription_type_id,
            monthly_price=monthly_price,
            annual_price=annual_price,
            trial_days=trial_days,
            self_service=self_service,
            module_keys=module_keys,
            other_features=other_features,
            consulting_rooms_limit=consulting_rooms_limit,
            doctors_limit=doctors_limit,
            assistants_limit=assistants_limit,
            new_patients_per_year_limit=new_patients_per_year_limit,
            clinics_limit=clinics_limit,
        )

    async def update(
        self, subscription_id: int, changes: Mapping[str, Any]
    ) -> Subscription | None:
        self.calls["update"] += 1
        subscription = self._current(subscription_id)
        if subscription is None:
            return None
        if "name" in changes and self._is_name_taken(changes["name"], excluding=subscription_id):
            raise UniqueViolationError(SUBSCRIPTION_NAME_INDEX)
        changes = dict(changes)
        module_keys = changes.pop("module_keys", None)
        for key, value in changes.items():
            setattr(subscription, key, value)
        if module_keys is not None:
            subscription.modules = [SubscriptionModule(module_key=key) for key in sorted(module_keys)]
        subscription.updated_at = datetime.now(UTC)
        return subscription

    async def change_status(
        self, subscription_id: int, to_status_id: int
    ) -> Subscription | None:
        self.calls["change_status"] += 1
        subscription = self._current(subscription_id)
        if subscription is None or subscription.status_id == to_status_id:
            return None
        self._set_status(subscription, to_status_id)
        return subscription

    async def get_status_id(self, subscription_id: int) -> int | None:
        self.calls["get_status_id"] += 1
        subscription = self.items.get(subscription_id)
        return None if subscription is None else subscription.status_id

    async def mark_enterprise(self, ids: Sequence[int]) -> int:
        self.calls["mark_enterprise"] += 1
        changed = 0
        for subscription_id in ids:
            subscription = self.items.get(subscription_id)
            if subscription is not None:
                subscription.subscription_type_id = SubscriptionType.ENTERPRISE
                subscription.subscription_type = SubscriptionType(
                    id=SubscriptionType.ENTERPRISE, name=TYPE_NAMES[SubscriptionType.ENTERPRISE]
                )
                changed += 1
        return changed

    async def soft_delete(self, subscription_id: int) -> bool:
        self.calls["soft_delete"] += 1
        subscription = self._current(subscription_id)
        if subscription is None:
            return False
        self._set_status(subscription, DELETED)
        return True


# --- spec 006: clinic subscriptions and their charges ---


class FakePaymentsApi:
    """Double of `PaymentsApiClient`: records the calls and answers what the test configures."""

    def __init__(
        self,
        *,
        rejected_code: str | None = None,
        permission_denied: bool = False,
        idempotency_conflict: bool = False,
        unavailable: bool = False,
        payment: PaymentRecord | None = None,
    ) -> None:
        self.rejected_code = rejected_code
        self.permission_denied = permission_denied
        self.idempotency_conflict = idempotency_conflict
        self.unavailable = unavailable
        self.payment = payment
        self.create_calls: list[dict[str, Any]] = []
        self.get_calls: list[Any] = []

    async def create_payment(
        self,
        token: str,
        *,
        idempotency_key: str,
        amount: int,
        currency: str,
        resource_type: str,
        resource_id: str,
        description: str,
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
            }
        )
        if self.rejected_code is not None:
            raise PaymentsApiRejectedToken(self.rejected_code)
        if self.permission_denied:
            raise PaymentsApiPermissionDenied()
        if self.idempotency_conflict:
            raise PaymentsApiIdempotencyConflict()
        if self.unavailable:
            raise PaymentsApiUnavailable()
        assert self.payment is not None, "configure `payment` for a successful create_payment"
        return self.payment

    async def get_payment_as_service(self, payment_id: Any) -> PaymentRecord:
        self.get_calls.append(payment_id)
        if self.unavailable:
            raise PaymentsApiUnavailable()
        assert self.payment is not None, "configure `payment` for a successful get_payment_as_service"
        return self.payment


def fake_caller_access(
    *, tenant_id: str | None, permissions: Iterable[str] = (), password_change_required: bool = False
) -> CallerAccess:
    return CallerAccess(
        tenant_id=tenant_id,
        permissions=frozenset(permissions),
        password_change_required=password_change_required,
    )


class FakeClinicSubscriptionChargeRepository:
    """Double of `ClinicSubscriptionChargeRepository` that keeps real ORM objects in memory.

    `clinic_subscription_id` is an opaque id (no local table of its own, rediseño 2026-11-11):
    this double only ever tracks charges, keyed by their own `id`.
    """

    def __init__(self) -> None:
        self.charges: dict[int, ClinicSubscriptionCharge] = {}
        self._next_charge_id = 1

    # --- helpers for the tests ---

    def add_charge(
        self,
        *,
        clinic_subscription_id,
        tenant_id=None,
        period,
        amount: int = 129900,
        currency: str = "MXN",
        payment_id,
        payment_status: str = "pending",
        checkout_url: str | None = None,
        idempotency_key: str = "key",
    ) -> ClinicSubscriptionCharge:
        charge_id = self._next_charge_id
        self._next_charge_id += 1
        charge = ClinicSubscriptionCharge(
            id=charge_id,
            clinic_subscription_id=clinic_subscription_id,
            tenant_id=tenant_id if tenant_id is not None else clinic_subscription_id,
            period=period,
            amount=amount,
            currency=currency,
            payment_id=payment_id,
            payment_status=payment_status,
            checkout_url=checkout_url,
            idempotency_key=idempotency_key,
            created_at=_EPOCH,
            updated_at=_EPOCH,
        )
        self.charges[charge_id] = charge
        return charge

    def _charges_of(self, clinic_subscription_id) -> list[ClinicSubscriptionCharge]:
        return sorted(
            (c for c in self.charges.values() if c.clinic_subscription_id == clinic_subscription_id),
            key=lambda c: (c.period, c.id),
        )

    # --- the interface of ClinicSubscriptionChargeRepository ---

    async def save_charge(
        self,
        *,
        clinic_subscription_id,
        tenant_id,
        period,
        amount: int,
        currency: str,
        payment_id,
        payment_status: str,
        checkout_url: str | None,
        idempotency_key: str,
    ) -> ClinicSubscriptionCharge:
        existing = next(
            (
                c
                for c in self.charges.values()
                if c.clinic_subscription_id == clinic_subscription_id and c.period == period
            ),
            None,
        )
        if existing is not None:
            existing.tenant_id = tenant_id
            existing.amount = amount
            existing.currency = currency
            existing.payment_id = payment_id
            existing.payment_status = payment_status
            existing.checkout_url = checkout_url
            existing.idempotency_key = idempotency_key
            return existing
        return self.add_charge(
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

    async def update_status(
        self, charge_id: int, *, payment_status: str, checkout_url: str | None
    ) -> ClinicSubscriptionCharge:
        charge = self.charges[charge_id]
        charge.payment_status = payment_status
        charge.checkout_url = checkout_url
        return charge

    async def get_by_period(self, clinic_subscription_id, period) -> ClinicSubscriptionCharge | None:
        return next(
            (
                c
                for c in self.charges.values()
                if c.clinic_subscription_id == clinic_subscription_id and c.period == period
            ),
            None,
        )

    async def get(self, clinic_subscription_id, charge_id: int) -> ClinicSubscriptionCharge | None:
        charge = self.charges.get(charge_id)
        if charge is None or charge.clinic_subscription_id != clinic_subscription_id:
            return None
        return charge

    async def list(self, clinic_subscription_id, *, page: int, limit: int):
        charges = list(reversed(self._charges_of(clinic_subscription_id)))
        total = len(charges)
        start = (page - 1) * limit
        return charges[start : start + limit], total

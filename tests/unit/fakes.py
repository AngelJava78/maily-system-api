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
from src.integrations.errors import (
    ClinicsApiUnavailable,
    UsersApiRejectedToken,
    UsersApiUnavailable,
)
from src.models.subscription import SUBSCRIPTION_NAME_INDEX, Subscription
from src.models.subscription_status import SubscriptionStatus
from src.repositories.errors import UniqueViolationError

STATUS_NAMES = {1: "Activa", 2: "Inactiva", 3: "Bloqueada", 4: "Eliminada", 5: "Manual"}
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
    ) -> None:
        self.allowed = allowed
        self.rejected_code = rejected_code
        self.unavailable = unavailable
        self.clinic_module_keys = clinic_module_keys
        self.modules_unavailable = modules_unavailable
        self.calls: list[tuple[str, str]] = []
        # Separate from `calls`: list_clinic_module_keys is a different operation of the same API
        # (research R4), and tests need to tell the two apart (e.g. "no call was made for modules").
        self.module_calls: list[str] = []

    async def check_permission(self, token: str, permission: str) -> bool:
        self.calls.append((token, permission))
        if self.unavailable:
            raise UsersApiUnavailable()
        if self.rejected_code is not None:
            raise UsersApiRejectedToken(self.rejected_code)
        return self.allowed

    async def list_clinic_module_keys(self, token: str) -> frozenset[str]:
        self.module_calls.append(token)
        if self.modules_unavailable:
            raise UsersApiUnavailable()
        if self.rejected_code is not None:
            raise UsersApiRejectedToken(self.rejected_code)
        return self.clinic_module_keys


class FakeClinicsApi:
    """Double of `ClinicsApiClient`: `counts` only holds subscriptions with at least one clinic."""

    def __init__(self, counts: Mapping[int, int] | None = None, *, fail: bool = False) -> None:
        self.counts = dict(counts or {})
        self.fail = fail
        self.calls: list[tuple[str, Sequence[int] | None]] = []

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
        created_at: datetime | None = None,
    ) -> Subscription:
        subscription_id = self._next_id
        self._next_id += 1
        moment = created_at or _EPOCH + timedelta(seconds=subscription_id)
        subscription = Subscription(
            id=subscription_id,
            name=name,
            description=description,
            monthly_price=Decimal(str(monthly_price)).quantize(Decimal("0.01")),
            annual_price=Decimal(str(annual_price)).quantize(Decimal("0.01")),
            trial_days=trial_days,
            self_service=self_service,
            module_keys=sorted(module_keys),
            other_features=list(other_features),
            consulting_rooms_limit=consulting_rooms_limit,
            doctors_limit=doctors_limit,
            assistants_limit=assistants_limit,
            new_patients_per_year_limit=new_patients_per_year_limit,
            status_id=status_id,
            created_at=moment,
            updated_at=moment,
        )
        subscription.status = SubscriptionStatus(id=status_id, name=STATUS_NAMES[status_id])
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
        annual_price: Decimal,
        trial_days: int,
        self_service: bool,
        module_keys: list[str],
        other_features: list[str],
        consulting_rooms_limit: int,
        doctors_limit: int,
        assistants_limit: int,
        new_patients_per_year_limit: int,
    ) -> Subscription:
        self.calls["create"] += 1
        if self._is_name_taken(name):
            raise UniqueViolationError(SUBSCRIPTION_NAME_INDEX)
        return self.add(
            name=name,
            description=description,
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
        for key, value in changes.items():
            setattr(subscription, key, value)
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

    async def soft_delete(self, subscription_id: int) -> bool:
        self.calls["soft_delete"] += 1
        subscription = self._current(subscription_id)
        if subscription is None:
            return False
        self._set_status(subscription, DELETED)
        return True

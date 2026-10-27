from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

# Name of the unique index on the subscription name; the Service recognises it in
# `UniqueViolationError`.
SUBSCRIPTION_NAME_INDEX = "subscriptions_name_not_deleted_key"

# Name of the foreign key of `subscription_type_id`; the Service recognises it in
# `ForeignKeyViolationError` to translate a nonexistent type into `SubscriptionTypeNotFoundError`.
SUBSCRIPTION_TYPE_FK_NAME = "subscriptions_subscription_type_id_fkey"

if TYPE_CHECKING:
    from src.models.subscription_status import SubscriptionStatus
    from src.models.subscription_type import SubscriptionType


class Subscription(Base):
    """Subscription (plan) assigned to clinics: price, modules, limits and its status.

    The clinic module catalog itself is not stored here (Principle IX): `module_keys` only holds
    the keys this service already validated against the users API (spec 004).
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_check"),
        CheckConstraint("monthly_price >= 0", name="monthly_price_check"),
        CheckConstraint("annual_price >= 0", name="annual_price_check"),
        CheckConstraint("trial_days BETWEEN 0 AND 3650", name="trial_days_check"),
        CheckConstraint("'patients' = ANY(module_keys)", name="module_keys_check"),
        CheckConstraint("cardinality(other_features) <= 20", name="other_features_check"),
        CheckConstraint(
            "consulting_rooms_limit BETWEEN 0 AND 1000000", name="consulting_rooms_limit_check"
        ),
        CheckConstraint("doctors_limit BETWEEN 0 AND 1000000", name="doctors_limit_check"),
        CheckConstraint("assistants_limit BETWEEN 0 AND 1000000", name="assistants_limit_check"),
        CheckConstraint(
            "new_patients_per_year_limit BETWEEN 0 AND 1000000",
            name="new_patients_per_year_limit_check",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    # Who the subscription is for; fixed forever once created (spec 006). A hand-administered
    # catalog like the status (today Individual=1, Enterprise=2); the application never writes it
    # outside `create()`.
    subscription_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_types.id"), server_default=text("1")
    )
    # Mexican pesos, never float (Principle VI); independent of each other (no enforced ratio).
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    annual_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # 0 = no trial period.
    trial_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Whether the plan is self-service in the MailySoft portal; born off (fail closed).
    self_service: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Keys of a clinic-module catalog owned by the users API (src/clinic_modules.py); always
    # includes 'patients'.
    module_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("ARRAY['patients']::text[]")
    )
    # Ordered list of free texts that are not modules; at most 20 (each of 1 to 150 characters in
    # the DTO). Renamed from `features` (spec 004).
    other_features: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    # Clinic growth ceilings; informational only, never validated against actual clinic usage.
    consulting_rooms_limit: Mapped[int] = mapped_column(Integer)
    doctors_limit: Mapped[int] = mapped_column(Integer)
    assistants_limit: Mapped[int] = mapped_column(Integer)
    new_patients_per_year_limit: Mapped[int] = mapped_column(Integer)
    # 1 = Active, 2 = Inactive, 3 = Blocked, 4 = Deleted (see SubscriptionStatus); new ones are Active.
    status_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_statuses.id"), server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `subscriptions_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

    # lazy="raise": an AsyncSession has no implicit loads; the Repository loads the relationship
    # explicitly (joinedload).
    status: Mapped["SubscriptionStatus"] = relationship(lazy="raise")
    subscription_type: Mapped["SubscriptionType"] = relationship(lazy="raise")


# The only uniqueness rule of the name (FR-014): unique among the subscriptions that are not deleted
# (status 4), ignoring case. The name of a deleted subscription is free; the name of an inactive or
# blocked one (or one with a status added by hand) stays reserved. It must match migration 0001.
Index(
    SUBSCRIPTION_NAME_INDEX,
    func.lower(Subscription.name),
    unique=True,
    postgresql_where=text("status_id <> 4"),
)

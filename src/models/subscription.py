from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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

if TYPE_CHECKING:
    from src.models.subscription_status import SubscriptionStatus


class Subscription(Base):
    """Subscription (plan) that is assigned to clinics: price, what it includes and its status."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_check"),
        CheckConstraint("monthly_price >= 0", name="monthly_price_check"),
        CheckConstraint("cardinality(features) <= 20", name="features_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    # Mexican pesos; exact decimal type, never float (Principle VI).
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Ordered list of free texts shown to people; at most 20 (each of 1 to 150 characters in the DTO).
    features: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
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


# The only uniqueness rule of the name (FR-014): unique among the subscriptions that are not deleted
# (status 4), ignoring case. The name of a deleted subscription is free; the name of an inactive or
# blocked one (or one with a status added by hand) stays reserved. It must match migration 0001.
Index(
    SUBSCRIPTION_NAME_INDEX,
    func.lower(Subscription.name),
    unique=True,
    postgresql_where=text("status_id <> 4"),
)

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

# Name of the unique partial index that keeps at most one Active or Pending-resolution subscription
# per clinic (FR-004); the Repository recognises it in `UniqueViolationError`.
CLINIC_SUBSCRIPTIONS_ONE_ACTIVE_INDEX = "clinic_subscriptions_one_active_per_tenant_key"
BILLING_CYCLES = ("monthly", "annual")

if TYPE_CHECKING:
    from src.models.clinic_subscription_status import ClinicSubscriptionStatus


class ClinicSubscription(Base):
    """A clinic's subscription to a catalog plan: its billing cycle, status and next charge date.

    References `subscriptions` (spec 001) by id only: it never copies its price or limits. There is
    no table of clinics (`tenant_id` is just a UUID, see spec Edge Cases). The current charge is not
    a column here (it would make a foreign-key cycle with `clinic_subscription_charges`, which
    already references this table): the Repository reads it as the most recent row of
    `clinic_subscription_charges` for this subscription (research R6).
    """

    __tablename__ = "clinic_subscriptions"
    __table_args__ = (
        CheckConstraint("billing_cycle IN ('monthly', 'annual')", name="billing_cycle_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscriptions.id"))
    billing_cycle: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_billing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 1 = Active, 2 = Pending resolution, 3 = Cancelled; new ones are Active.
    status_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clinic_subscription_statuses.id"), server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `clinic_subscriptions_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

    # lazy="raise": an AsyncSession has no implicit loads; the Repository loads explicitly.
    status: Mapped["ClinicSubscriptionStatus"] = relationship(lazy="raise")


# At most one Active (1) or Pending-resolution (2) subscription per clinic (FR-004).
Index(
    CLINIC_SUBSCRIPTIONS_ONE_ACTIVE_INDEX,
    ClinicSubscription.tenant_id,
    unique=True,
    postgresql_where=text("status_id IN (1, 2)"),
)
Index("clinic_subscriptions_tenant_id_idx", ClinicSubscription.tenant_id)
Index("clinic_subscriptions_status_id_idx", ClinicSubscription.status_id)

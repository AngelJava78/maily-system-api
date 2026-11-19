from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SubscriptionPeriod(Base):
    """The control of one organization: when its first period started, when its trial ends and until
    when it is paid (spec 010, FR-007 to FR-012). It must match migration 0008.

    One row per organization, created the first time the organization is consulted. The organization
    belongs to the clinics API (Principle IX): its identifier is only the key of this service's own
    data, there is no foreign key and nothing else about it is stored. The date of the next payment,
    the state and the days that are left are derived when asked, never stored (FR-012).
    """

    __tablename__ = "subscription_periods"
    __table_args__ = (
        CheckConstraint(
            "trial_ends_at IS NULL OR trial_ends_at >= started_at", name="trial_ends_check"
        ),
        CheckConstraint("paid_until IS NULL OR paid_until > started_at", name="paid_until_check"),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # The latest of the creation of the organization and the cutoff date (FR-008).
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL = the plan had no trial. Fixed when the row is created, never changed (FR-009).
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL = no payment applied yet. Only the application of a charge moves it (FR-032).
    paid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `subscription_periods_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

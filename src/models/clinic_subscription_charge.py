from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

# Name of the unique index on (clinic_subscription_id, period); the Repository recognises it in
# `UniqueViolationError` (research R3: one row per subscription and billing period).
CLINIC_SUBSCRIPTION_CHARGES_ONE_PER_PERIOD_INDEX = "clinic_subscription_charges_one_per_period_key"

# The six values of Pagos' own `PaymentStatus` (contracts/payments-api-integration.md); this
# service only ever stores a translation of what Pagos answered, never an invented status.
PAYMENT_STATUSES = ("pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded")


class ClinicSubscriptionCharge(Base):
    """One charge attempt against Pagos for a clinic subscription (full history, research R3).

    `clinic_subscription_id` is an opaque identifier owned by the future Clinics microservice
    (Principle IX, rediseño 2026-11-11): this service never stores the clinic/plan/cycle
    assignment itself, only references it by this id, with no local foreign key. `tenant_id` is a
    copy of what Clinics reported at charge time, kept only so the history can be filtered by
    organization without asking Clinics again (FR-010).
    """

    __tablename__ = "clinic_subscription_charges"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_check"),
        CheckConstraint(
            "payment_status IN ('pending','approved','rejected','cancelled',"
            "'partially_refunded','refunded')",
            name="payment_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_subscription_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    period: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(Integer)  # cents (research R2); never NUMERIC
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'MXN'"))
    payment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    payment_status: Mapped[str] = mapped_column(String(20))
    checkout_url: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `clinic_subscription_charges_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )


Index(
    CLINIC_SUBSCRIPTION_CHARGES_ONE_PER_PERIOD_INDEX,
    ClinicSubscriptionCharge.clinic_subscription_id,
    ClinicSubscriptionCharge.period,
    unique=True,
)
Index("clinic_subscription_charges_payment_id_idx", ClinicSubscriptionCharge.payment_id)
Index(
    "clinic_subscription_charges_clinic_subscription_id_idx",
    ClinicSubscriptionCharge.clinic_subscription_id,
)
Index("clinic_subscription_charges_tenant_id_idx", ClinicSubscriptionCharge.tenant_id)

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

# Names of the unique constraints and indexes, as PostgreSQL reports them in
# `UniqueViolationError.constraint_name`. The Service treats them all alike (somebody registered a charge
# for the same period first); the tests and the doubles tell them apart.
CHARGE_PAYMENT_ID_KEY = "subscription_charges_payment_id_key"
CHARGE_TERMS_ATTEMPT_KEY = "subscription_charges_terms_attempt_key"
CHARGE_PENDING_TERMS_KEY = "subscription_charges_pending_terms_key"
CHARGE_PENDING_INDEX = "subscription_charges_pending_idx"


class ChargeStatus(StrEnum):
    """The result of the reconciliation of a charge, not the status of its payment (that is Pagos')."""

    PENDING = "pending"
    APPLIED = "applied"
    CLOSED = "closed"


class ClosedReason(StrEnum):
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    INCONSISTENT = "inconsistent"
    REFUNDED = "refunded"


class SubscriptionCharge(Base):
    """A payment that this service asked the payments API to create (spec 010, FR-021).

    It only keeps what this service itself requested (amount, currency, period) and its own result:
    the status of the payment and its checkout address belong to the payments API and are asked for on
    every use (Principle IX). It must match migration 0008.
    """

    __tablename__ = "subscription_charges"
    __table_args__ = (
        # A payment of the payments API is one single charge: named subscription_charges_payment_id_key.
        UniqueConstraint("payment_id"),
        # The same conditions and attempt are the same charge: it decides two simultaneous starts.
        UniqueConstraint(
            "organization_id",
            "settles_due_at",
            "billing_period",
            "amount",
            "attempt",
            name=CHARGE_TERMS_ATTEMPT_KEY,
        ),
        CheckConstraint("amount > 0", name="amount_check"),
        CheckConstraint("currency = 'MXN'", name="currency_check"),
        CheckConstraint("billing_period IN ('monthly', 'annual')", name="billing_period_check"),
        CheckConstraint("attempt >= 1", name="attempt_check"),
        CheckConstraint("status IN ('pending', 'applied', 'closed')", name="status_check"),
        CheckConstraint(
            "closed_reason IS NULL OR closed_reason IN "
            "('rejected', 'cancelled', 'inconsistent', 'refunded')",
            name="closed_reason_check",
        ),
        # The status decides which columns carry a value.
        CheckConstraint(
            "(status = 'pending' AND closed_reason IS NULL AND period_starts_at IS NULL "
            "AND period_ends_at IS NULL AND resolved_at IS NULL) "
            "OR (status = 'applied' AND closed_reason IS NULL AND period_starts_at IS NOT NULL "
            "AND period_ends_at > period_starts_at AND resolved_at IS NOT NULL) "
            "OR (status = 'closed' AND closed_reason IS NOT NULL AND period_starts_at IS NULL "
            "AND period_ends_at IS NULL AND resolved_at IS NOT NULL)",
            name="resolution_check",
        ),
        # The reconciliation and the search of the pending charge only read the pending ones.
        Index(
            CHARGE_PENDING_INDEX,
            "organization_id",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        # There is at most one unresolved charge for a period and amount (FR-022): whatever the attempt,
        # two simultaneous starts cannot leave two of them, so only one checkout is ever offered.
        Index(
            CHARGE_PENDING_TERMS_KEY,
            "organization_id",
            "settles_due_at",
            "billing_period",
            "amount",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("subscription_periods.organization_id")
    )
    # The identifier of the payment in the payments API.
    payment_id: Mapped[UUID] = mapped_column(Uuid)
    # Mexican pesos, never float (Principle VI).
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))
    # The length of the period that it will cover: 'monthly' or 'annual'.
    billing_period: Mapped[str] = mapped_column(String(10))
    # The payment date that this charge settles: the one that was current when it was started.
    settles_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 1 + the charges that already had the same conditions (research R6).
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), server_default=text("'pending'"))
    # Only when closed: rejected, cancelled, inconsistent or refunded.
    closed_reason: Mapped[str | None] = mapped_column(String(20))
    # Only when applied: the period that the payment covers (FR-029).
    period_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When it was applied or closed (the clock of the service).
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `subscription_charges_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

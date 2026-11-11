from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.dtos.status import StatusRead
from src.messages import CLINIC_SUBSCRIPTION_BILLING_CYCLE_INVALID_MESSAGE

BillingCycle = Literal["monthly", "annual"]
PaymentStatus = Literal["pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"]
_BILLING_CYCLES = ("monthly", "annual")


class ClinicSubscriptionChargeRead(BaseModel):
    """One charge attempt of a clinic subscription (full history, research R3/R6)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": (
                "Un intento de cobro de una suscripción de clínica (historial completo, "
                "rechazados incluidos)."
            )
        },
    )

    id: int = Field(ge=1, description="Identificador del cobro.", examples=[1])
    clinic_subscription_id: int = Field(
        ge=1, description="Identificador de la suscripción de clínica."
    )
    period: date = Field(description="El periodo que cubre este cobro.")
    amount: int = Field(
        ge=1, description="Monto cobrado, en centavos (nunca pesos).", examples=[129900]
    )
    currency: str = Field(description="Moneda del cobro.", examples=["MXN"])
    payment_id: UUID = Field(description="Identificador del pago en mailySoft-pagos.")
    payment_status: PaymentStatus = Field(
        description="Estatus del pago, reflejo del de mailySoft-pagos.", examples=["pending"]
    )
    checkout_url: str | None = Field(
        default=None,
        description="URL de checkout de Mercado Pago, mientras el pago no se resuelva.",
    )
    created_at: datetime = Field(description="Fecha y hora en que se disparó el cobro.")
    updated_at: datetime = Field(
        description="Fecha y hora de la última sincronización de su estatus."
    )


class ClinicSubscriptionCreate(BaseModel):
    """Data to assign a catalog plan to a clinic (FR-001 a FR-006)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": (
                "Datos para asignar un plan del catálogo a una clínica. No se admiten campos "
                "desconocidos."
            )
        },
    )

    tenant_id: UUID = Field(
        description="Identificador (UUID) de la clínica. No se valida contra ningún catálogo.",
        examples=["3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f"],
    )
    subscription_id: int = Field(
        ge=1, description="Identificador del plan del catálogo (`subscriptions`).", examples=[2]
    )
    billing_cycle: str = Field(
        description='Ciclo de cobro: "monthly" o "annual".', examples=["monthly"]
    )
    started_at: datetime | None = Field(
        default=None,
        description="Fecha de inicio. Si se omite, es el momento de crear la suscripción.",
    )

    @field_validator("billing_cycle")
    @classmethod
    def billing_cycle_must_be_known(cls, value: str) -> str:
        if value not in _BILLING_CYCLES:
            raise ValueError(CLINIC_SUBSCRIPTION_BILLING_CYCLE_INVALID_MESSAGE)
        return value


class ClinicSubscriptionRead(BaseModel):
    """A clinic's subscription, with its current charge (FR-002, FR-013)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": (
                "Suscripción de una clínica: su plan, su ciclo de cobro, su estatus y su cobro "
                "vigente."
            )
        },
    )

    id: int = Field(ge=1, description="Identificador de la suscripción de clínica.", examples=[1])
    tenant_id: UUID = Field(description="Identificador de la clínica.")
    subscription_id: int = Field(ge=1, description="Identificador del plan asignado.")
    billing_cycle: BillingCycle = Field(description="Ciclo de cobro.")
    started_at: datetime = Field(description="Fecha de inicio.")
    next_billing_at: datetime = Field(description="Fecha del próximo cobro.")
    status: StatusRead = Field(
        description="Estatus de la suscripción de clínica (1 Activa, 2 con cobro pendiente de "
        "resolver, 3 Cancelada)."
    )
    current_charge: ClinicSubscriptionChargeRead | None = Field(
        default=None, description="El cobro vigente (el más reciente), o `null` si aún no se ha "
        "disparado ninguno."
    )
    created_at: datetime = Field(description="Fecha y hora de creación.")
    updated_at: datetime = Field(description="Fecha y hora de la última modificación.")

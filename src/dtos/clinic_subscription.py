from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PaymentStatus = Literal["pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"]


class ClinicSubscriptionChargeCreate(BaseModel):
    """Data to trigger the charge of a clinic subscription (FR-001).

    `clinic_subscription_id` comes from the path, not the body: Clinics owns that identifier. The
    period being charged is decided by whoever triggers the charge (Assumptions of the spec).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": (
                "Datos para disparar el cobro de una suscripción de clínica. No se admiten "
                "campos desconocidos."
            )
        },
    )

    period: date = Field(
        description="El periodo que se cobra (lo decide quien dispara el cobro).",
        examples=["2026-12-01"],
    )


class ClinicSubscriptionChargeRead(BaseModel):
    """One charge attempt of a clinic subscription (full history, research R3)."""

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
    clinic_subscription_id: UUID = Field(
        description="Identificador (opaco) de la suscripción de clínica, propiedad de Clínicas."
    )
    tenant_id: UUID = Field(
        description="Identificador de la clínica, copiado de Clínicas al momento de cobrar."
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

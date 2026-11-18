"""Responses of the subscription periods (spec 010, data-model.md section 6).

The nine fields of `SubscriptionPeriodRead` are mandatory: the key is always in the JSON, with its value
or with `null` when there is no such value (no trial, no payment date, no days, a charge that could not
be verified). The dates are ISO 8601 in UTC with `Z`; the amounts are text with two decimals, like the
prices of the catalog. No field here can carry a token, the identifier of a payment or anything that
belongs to another API (FR-042).
"""

from datetime import UTC
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer, field_validator

PeriodStateName = Literal["trial", "current", "overdue", "no_charge"]
BillingPeriodName = Literal["monthly", "annual"]


def _two_decimals(value: Decimal) -> str:
    """The amount as the catalog publishes its prices: text with exactly two decimals."""
    return format(value.quantize(Decimal("0.01")), "f")


class PlanRead(BaseModel):
    """The plan (subscription of the catalog) that the organization is billed on."""

    model_config = ConfigDict(
        json_schema_extra={"description": "El plan del catálogo con el que se cobra a la organización."}
    )

    id: int = Field(description="Identificador del plan en el catálogo de suscripciones.", examples=[3])
    name: str = Field(description="Nombre del plan.", examples=["Plan Individual"])


class SubscriptionPeriodRead(BaseModel):
    """The state of the subscription period of an organization."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "Estado del periodo de una organización: en qué punto está su prueba, cuándo toca "
                "pagar y cuánto. Los nueve campos siempre están presentes; los que no aplican valen "
                "`null`."
            )
        }
    )

    state: PeriodStateName = Field(
        description=(
            "`trial` (en prueba), `current` (al corriente), `overdue` (vencida) o `no_charge` "
            "(sin cobro: el importe vigente es 0.00)."
        ),
        examples=["trial"],
    )
    trial_ends_at: AwareDatetime | None = Field(
        description=(
            "Cuándo termina la prueba, en ISO 8601 con zona horaria UTC. `null` si el plan no "
            "tenía prueba."
        ),
        examples=["2026-12-04T15:30:00Z"],
    )
    payment_due_at: AwareDatetime | None = Field(
        description=(
            "Fecha del siguiente pago, en ISO 8601 con zona horaria UTC. `null` en `no_charge`: "
            "no hay fecha de pago."
        ),
        examples=["2026-12-04T15:30:00Z"],
    )
    days_remaining: int | None = Field(
        description=(
            "Días que faltan para `payment_due_at`, redondeados hacia arriba: con `trial` y "
            "`current` vale 1 o más; con `overdue`, 0 o menos (`-5` son cinco días completos de "
            "atraso). `null` en `no_charge`."
        ),
        examples=[9],
    )
    subscription: PlanRead = Field(description="El plan vigente de la organización.")
    billing_period: BillingPeriodName = Field(
        description="Periodo de cobro que eligió la organización: `monthly` o `annual`.",
        examples=["monthly"],
    )
    amount: Decimal = Field(
        description=(
            "Importe del siguiente pago, en pesos mexicanos, como texto con dos decimales: el "
            "precio del catálogo para el plan y el periodo de cobro vigentes."
        ),
        examples=["499.00"],
    )
    currency: Literal["MXN"] = Field(description="Moneda del importe: siempre `MXN`.", examples=["MXN"])
    payment_in_progress: bool | None = Field(
        description=(
            "`true` si hay un cobro pendiente verificado en Pagos; `false` si no hay ninguno; "
            "`null` si hay cobros sin resolver que no se pudieron verificar porque Pagos no "
            "respondió."
        ),
        examples=[False],
    )

    @field_validator("trial_ends_at", "payment_due_at")
    @classmethod
    def _in_utc(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        return None if value is None else value.astimezone(UTC)

    @field_serializer("amount")
    def _amount_with_two_decimals(self, value: Decimal) -> str:
        return _two_decimals(value)


class SubscriptionPaymentRead(BaseModel):
    """The payment that was started: where to take the person to pay it."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": "El pago que se inició: la dirección del checkout y lo que se va a pagar."
        }
    )

    checkout_url: str = Field(
        description="Dirección del checkout de Pagos a la que la aplicación lleva a la persona.",
        examples=["https://www.mercadopago.com.mx/checkout/v1/redirect?pref_id=123456789-abc"],
    )
    amount: Decimal = Field(
        description="Importe del cobro, en pesos mexicanos, como texto con dos decimales.",
        examples=["499.00"],
    )
    currency: Literal["MXN"] = Field(description="Moneda del importe: siempre `MXN`.", examples=["MXN"])
    billing_period: BillingPeriodName = Field(
        description="Duración del periodo que cubrirá el pago: `monthly` o `annual`.",
        examples=["monthly"],
    )

    @field_serializer("amount")
    def _amount_with_two_decimals(self, value: Decimal) -> str:
        return _two_decimals(value)

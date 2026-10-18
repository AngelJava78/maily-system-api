from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from src.dtos.status import StatusRead
from src.messages import (
    SUBSCRIPTION_EMPTY_UPDATE_MESSAGE,
    SUBSCRIPTION_FEATURES_NOT_LIST_MESSAGE,
    SUBSCRIPTION_NAME_REQUIRED_MESSAGE,
    SUBSCRIPTION_PRICE_REQUIRED_MESSAGE,
    SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE,
)


class SubscriptionRead(BaseModel):
    """A subscription as the API shows it (FR-008): with its status and its clinics count."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Una suscripción (plan) con su estatus."},
    )

    id: int = Field(ge=1, description="Identificador de la suscripción.", examples=[1])
    name: str = Field(description="Nombre de la suscripción.", examples=["Pro"])
    description: str | None = Field(
        description="Descripción de la suscripción, o `null` si no tiene.",
        examples=["Para clínicas en crecimiento."],
    )
    monthly_price: Decimal = Field(
        description=(
            "Precio mensual en pesos mexicanos, con dos decimales (cadena para no perder "
            "precisión)."
        ),
        examples=["4500.00"],
    )
    features: list[str] = Field(
        description=(
            "Lo que incluye el plan, en el orden en que se guardó. Es texto informativo."
        ),
        examples=[["Hasta 5 consultorios", "Usuarios ilimitados"]],
    )
    status: StatusRead = Field(
        description=(
            "Estatus de la suscripción, tomado del catálogo de estatus (se edita a mano): quien "
            "consume la API debe basarse en su `id`."
        )
    )
    clinics_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Número de clínicas con esta suscripción (dato del API de clínicas, consultado en "
            "cada lectura). `null` = no disponible."
        ),
        examples=[2],
    )
    created_at: datetime = Field(description="Fecha y hora de creación (con zona horaria).")
    updated_at: datetime = Field(
        description="Fecha y hora de la última modificación (con zona horaria)."
    )

    @field_serializer("monthly_price")
    def _two_decimals(self, value: Decimal) -> str:
        # What was accepted without zeros ("4500") is always shown with two decimals ("4500.00").
        return format(value.quantize(Decimal("0.01")), "f")


# One item of what a subscription includes: 1 to 150 characters once trimmed.
FeatureText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class SubscriptionCreate(BaseModel):
    """Data to create a subscription (FR-011 to FR-013); unknown fields are rejected (FR-019)."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "description": "Datos para crear una suscripción. No se admiten campos desconocidos."
        },
    )

    name: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "Nombre de la suscripción (1 a 100 caracteres, sin contar espacios al inicio y al "
            "final). No puede repetirse (sin distinguir mayúsculas) entre las no eliminadas."
        ),
        examples=["Pro"],
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Descripción opcional (hasta 500 caracteres). La cadena vacía equivale a no tener "
            "descripción."
        ),
        examples=["Para clínicas en crecimiento."],
    )
    monthly_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description=(
            "Precio mensual en pesos mexicanos, de 0 a 99999999.99, con hasta dos decimales "
            "(número o cadena)."
        ),
        examples=["4500.00"],
    )
    features: list[FeatureText] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Lo que incluye el plan: hasta 20 textos de 1 a 150 caracteres. Puede estar vacía."
        ),
        examples=[["Hasta 5 consultorios", "Usuarios ilimitados"]],
    )

    @field_validator("description")
    @classmethod
    def empty_description_means_none(cls, value: str | None) -> str | None:
        return value or None


class SubscriptionUpdate(BaseModel):
    """Changes to a subscription (FR-015): only the fields that are sent are modified."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "description": (
                "Datos a modificar de una suscripción. Hay que enviar al menos uno. No se admiten "
                "campos desconocidos (tampoco el estatus: tiene su propia operación)."
            )
        },
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Nuevo nombre. No puede ser nulo ni vacío.",
        examples=["Pro Plus"],
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Nueva descripción. La cadena vacía o `null` la borran.",
        examples=["Para clínicas con varias sedes."],
    )
    monthly_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Nuevo precio mensual (mismo formato que al crear). No puede ser nulo.",
        examples=["4700.00"],
    )
    features: list[FeatureText] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Nueva lista completa de lo que incluye (sustituye a la anterior). `[]` la vacía. No "
            "puede ser nula."
        ),
        examples=[["Hasta 5 consultorios"]],
    )

    # The validators below only run for a field that is in the body, so a `null` that was sent on
    # purpose is reported on the field itself instead of reaching the database.

    @field_validator("name")
    @classmethod
    def name_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError(SUBSCRIPTION_NAME_REQUIRED_MESSAGE)
        return value

    @field_validator("monthly_price")
    @classmethod
    def price_cannot_be_null(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise ValueError(SUBSCRIPTION_PRICE_REQUIRED_MESSAGE)
        return value

    @field_validator("features")
    @classmethod
    def features_cannot_be_null(cls, value: list[str] | None) -> list[str]:
        if value is None:  # the column is NOT NULL: an empty list is how the features are cleared
            raise ValueError(SUBSCRIPTION_FEATURES_NOT_LIST_MESSAGE)
        return value

    @field_validator("description")
    @classmethod
    def empty_description_means_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "SubscriptionUpdate":
        # `model_fields_set` tells "not sent" apart from an explicit `null`.
        if not self.model_fields_set:
            raise ValueError(SUBSCRIPTION_EMPTY_UPDATE_MESSAGE)
        return self


class SubscriptionStatusChange(BaseModel):
    """The status a subscription moves to (FR-016); deleting has its own operation."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"description": "Estatus al que pasa la suscripción."},
    )

    # A strict integer: `Literal[1, 2, 3]` would also accept `true` as 1.
    status_id: Annotated[int, Field(strict=True)] = Field(
        json_schema_extra={"enum": [1, 2, 3]},
        description="1 Activa, 2 Inactiva o 3 Bloqueada. Eliminar tiene su propia operación.",
        examples=[2],
    )

    @field_validator("status_id")
    @classmethod
    def only_the_manageable_statuses(cls, value: int) -> int:
        if value not in (1, 2, 3):
            raise ValueError(SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE)
        return value

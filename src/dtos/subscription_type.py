from pydantic import BaseModel, ConfigDict, Field


class SubscriptionTypeRead(BaseModel):
    """Who a subscription is for, taken from its type catalog."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": (
                "A quién va dirigida la suscripción, tomado de su catálogo (se edita a mano)."
            )
        },
    )

    id: int = Field(
        ge=1,
        description=(
            "Identificador del tipo en el catálogo (hoy, 1 Individual, 2 Empresarial). Es el "
            "valor estable en el que debe basarse quien consume la API."
        ),
        examples=[1],
    )
    name: str = Field(
        description=(
            "Nombre del tipo (en español). Es un dato del catálogo y puede cambiar si se edita "
            "a mano."
        ),
        examples=["Individual"],
    )

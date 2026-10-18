from pydantic import BaseModel, ConfigDict, Field


class StatusRead(BaseModel):
    """Status of a subscription, taken from its status catalog."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": (
                "Estatus de una suscripción, tomado de su catálogo de estatus (se edita a mano)."
            )
        },
    )

    id: int = Field(
        ge=1,
        description=(
            "Identificador del estatus en el catálogo (1 Activa, 2 Inactiva, 3 Bloqueada, "
            "4 Eliminada). Es el valor estable en el que debe basarse quien consume la API."
        ),
        examples=[1],
    )
    name: str = Field(
        description=(
            "Nombre del estatus (en español). Es un dato del catálogo y puede cambiar si se "
            "edita a mano."
        ),
        examples=["Activa"],
    )

from pydantic import BaseModel, ConfigDict, Field

from src.messages import ErrorCode


class FieldError(BaseModel):
    """One piece of the request that is not valid."""

    model_config = ConfigDict(
        json_schema_extra={"description": "Un dato de la solicitud que no es válido."}
    )

    field: str = Field(
        description="Campo con el problema (el nombre del campo de la API, o `body`).",
        examples=["name"],
    )
    message: str = Field(
        description="Explicación en español.",
        examples=["El nombre de la suscripción es obligatorio."],
    )


class ErrorResponse(BaseModel):
    """Uniform body of every error of the API (FR-021)."""

    model_config = ConfigDict(
        json_schema_extra={"description": "Formato uniforme de todos los errores."}
    )

    code: ErrorCode = Field(description="Código estable del error (en inglés).")
    message: str = Field(description="Mensaje en español, sin detalles técnicos.")
    errors: list[FieldError] | None = Field(
        default=None,
        description="Solo en `validation_error`: un elemento por dato con problema.",
    )

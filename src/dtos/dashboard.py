"""Response of the platform dashboard (spec 003, data-model.md section 3).

The seven fields of `DashboardRead` are mandatory: the key is always in the JSON, with its value or
with `null` when its data source failed (FR-026). A `0` or an empty list only means that the source
answered there is nothing. No field here can carry personal data (FR-008).
"""

from datetime import timezone
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

# A count of the platform; `null` is only allowed as "not available" (never as a made-up zero).
Count = Annotated[int, Field(ge=0)]


class ClinicStatusRead(BaseModel):
    """Status of a clinic, taken from the catalog of clinic statuses."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Estatus de una clínica, tomado del catálogo de estatus de clínicas."
        },
    )

    id: int = Field(
        description=(
            "Identificador del estatus en el catálogo de clínicas. Es el valor estable en el que "
            "debe basarse quien consume la API."
        ),
        examples=[1],
    )
    name: str = Field(
        description="Nombre del estatus (en español). Puede cambiar si se edita el catálogo.",
        examples=["Activa"],
    )


class RecentClinicRead(BaseModel):
    """Basic data of a recent clinic."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Datos básicos de una clínica reciente."},
    )

    id: UUID = Field(description="Identificador de la clínica.")
    name: str = Field(description="Nombre de la clínica.", examples=["Clínica Santa Aurora"])
    created_at: AwareDatetime = Field(
        description="Fecha y hora de creación, en ISO 8601 con zona horaria UTC.",
        examples=["2026-10-15T16:20:00Z"],
    )
    status: ClinicStatusRead = Field(description="Estatus de la clínica.")

    @field_validator("created_at")
    @classmethod
    def _in_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(timezone.utc)


class DashboardRead(BaseModel):
    """General summary of the platform («Panel de Maily»)."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "Resumen general de la plataforma. Los siete campos siempre están presentes; cada "
                "uno vale `null` si su fuente de datos falló."
            )
        }
    )

    total_clinics: Count | None = Field(
        description="Total de clínicas de la plataforma, en cualquier estatus.", examples=[12]
    )
    active_clinics: Count | None = Field(description="Clínicas activas.", examples=[8])
    trial_clinics: Count | None = Field(description="Clínicas con periodo de prueba.", examples=[3])
    total_doctors: Count | None = Field(
        description="Total de doctores de toda la plataforma.", examples=[37]
    )
    total_patients: Count | None = Field(
        description="Total de pacientes de toda la plataforma.", examples=[1284]
    )
    total_users: Count | None = Field(
        description="Total de usuarios de toda la plataforma (incluye a los doctores).",
        examples=[52],
    )
    recent_clinics: Annotated[list[RecentClinicRead], Field(max_length=10)] | None = Field(
        description=(
            "Las clínicas más recientes, de la más nueva a la más antigua. Lista vacía si no hay "
            "clínicas; `null` solo si su fuente falló."
        )
    )

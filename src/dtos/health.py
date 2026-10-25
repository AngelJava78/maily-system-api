"""Responses of the health of the services (spec 005, data-model.md section 5).

Field names are part of the agreement with maily-backoffice 016 (and, the ones of the contract v1,
with mailySoft-usuarios 016 and mailySoft-pacientes 008). No DTO here has a field for an address, a
host, an IP, a raw body or the text of an exception. The dates are published in UTC with `Z`.
"""

from datetime import UTC
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Latency = Annotated[int, Field(ge=0)]
GlobalStatus = Literal["ok", "degraded", "down"]
ComponentKind = Literal["service", "database", "frontend"]
ComponentStatus = Literal["up", "degraded", "down", "stopped", "unknown"]
CheckError = Literal["timeout", "connection_error", "not_configured", "unexpected_error"]
ComponentError = Literal[
    "timeout",
    "connection_error",
    "dns_error",
    "host_not_allowed",
    "unexpected_status",
    "invalid_response",
    "response_too_large",
    "not_ready",
    "unexpected_error",
]


def _in_utc(value: AwareDatetime | None) -> AwareDatetime | None:
    return None if value is None else value.astimezone(UTC)


class CheckRead(BaseModel):
    """One check, in the shape of `/health/ready` of the contract v1."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Un chequeo de disponibilidad (forma del contrato v1)."},
    )

    name: str = Field(description="Nombre del chequeo (hasta 64 caracteres).", examples=["database"])
    status: Literal["ok", "error"] = Field(description="`ok` o `error`.")
    latency_ms: Latency | None = Field(
        description="Duración del chequeo en milisegundos, también si falló.", examples=[12]
    )
    error: CheckError | None = Field(description="`null` si está `ok`; si no, el código de la falla.")


class ComponentHealthRead(BaseModel):
    """The health of one component. It never carries its address."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Salud de un componente. Nunca incluye su dirección."},
    )

    code: str = Field(description="Código del componente.", examples=["mailysoft-usuarios"])
    name: str = Field(description="Nombre del componente.", examples=["MailySoft Usuarios"])
    kind: ComponentKind = Field(description="`service`, `database` o `frontend`.")
    status: ComponentStatus = Field(
        description=(
            "`up` sano; `degraded` vivo pero no disponible; `down` caído; `stopped` la base de datos "
            "detenida por horario; `unknown` no se pudo saber (por ejemplo, su host ya no está "
            "permitido)."
        )
    )
    latency_ms: Latency | None = Field(
        description="Duración del chequeo principal, también si falló; `null` si no se intentó.",
        examples=[11],
    )
    checked_at: AwareDatetime = Field(
        description="Cuándo terminó su chequeo, en ISO 8601 UTC.", examples=["2026-10-24T17:40:03Z"]
    )
    version: str = Field(description="Versión (hasta 64 caracteres) o `unknown`.", examples=["2.0.0"])
    commit: str = Field(description="Commit (hasta 64 caracteres) o `unknown`.")
    build_date: str = Field(description="Fecha de build en ISO 8601 UTC o `unknown`.")
    environment: str = Field(description="Entorno (hasta 64 caracteres) o `unknown`.", examples=["staging"])
    checks: list[CheckRead] = Field(
        max_length=20, description="Chequeos que reportó (forma de `/health/ready`); vacía si no aplica."
    )
    error: ComponentError | None = Field(
        description="`null` si está `up`; si no, un código de la lista cerrada del catálogo."
    )
    next_start_at: AwareDatetime | None = Field(
        description=(
            "Próximo encendido programado (ISO 8601 UTC). Solo tiene valor en `database` cuando está "
            "`stopped` y el horario está configurado; `null` en cualquier otro caso."
        ),
        examples=[None],
    )

    @field_validator("checked_at", "next_start_at")
    @classmethod
    def _utc(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        return _in_utc(value)


class LiveRead(BaseModel):
    """`/health/live` of the contract v1: the process attends HTTP."""

    model_config = ConfigDict(json_schema_extra={"description": "El proceso está vivo."})

    status: Literal["ok"] = Field(description="Siempre `ok` mientras el proceso atienda HTTP.")


class ReadyRead(BaseModel):
    """`/health/ready` of the contract v1: the same shape with 200 and with 503."""

    model_config = ConfigDict(
        json_schema_extra={
            "description": "Disponibilidad del servicio (contrato v1); el mismo esquema en 200 y en 503."
        }
    )

    status: Literal["ok", "unavailable"] = Field(description="`ok` si la base de datos respondió.")
    checks: list[CheckRead] = Field(description="En este servicio, solo el chequeo `database`.")


class InfoRead(BaseModel):
    """`/info` of the contract v1: which build is running."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Identificación del build (contrato v1)."},
    )

    service: str = Field(description="Nombre del servicio.", examples=["maily-system-api"])
    version: str = Field(description="Versión; la misma del documento OpenAPI.", examples=["2.0.0"])
    commit: str = Field(description="SHA del commit o `unknown`.", examples=["3c81089d"])
    build_date: str = Field(
        description="Fecha y hora del build en ISO 8601 UTC o `unknown`.", examples=["2026-10-24T16:05:00Z"]
    )
    environment: str = Field(description="Entorno del despliegue o `unknown`.", examples=["staging"])


class HealthRead(BaseModel):
    """The health of the platform (`GET /api/v1/health`)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"description": "Resultado de salud de la plataforma."},
    )

    status: GlobalStatus = Field(
        description=(
            "`down` si algún componente está `down`; si no, `degraded` si alguno está `degraded`, "
            "`stopped` o `unknown`; si no, `ok`."
        )
    )
    checked_at: AwareDatetime = Field(
        description="Cuándo terminó la agregación, en ISO 8601 UTC.", examples=["2026-10-24T17:40:03Z"]
    )
    registry_available: bool = Field(
        description=(
            "`false` si el registro no pudo leerse en esta agregación (se usa la última copia leída, "
            "o solo los componentes integrados). Vacío no es lo mismo que no disponible."
        )
    )
    components: list[ComponentHealthRead] = Field(
        description=(
            "Los dos integrados (`maily-system-api` y `database`) y después los registrados "
            "habilitados, por `sort_order` y `code`."
        )
    )

    @field_validator("checked_at")
    @classmethod
    def _utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)


# --- The public status (`GET /health/status`, FR-045 to FR-047) ---
# A closed list of fields: a field that the result of health gains is not published here unless the
# spec adds it to this list (FR-047). `extra="forbid"` keeps anything else out.


class PublicComponentRead(BaseModel):
    """One component of the public status: who it is, its status and, stopped, when it starts."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Un componente en el estado público. Lista cerrada de campos (FR-047)."
        },
    )

    code: str = Field(description="Código del componente.", examples=["database"])
    name: str = Field(description="Nombre del componente.", examples=["Base de datos"])
    kind: ComponentKind = Field(description="`service`, `database` o `frontend`.")
    status: ComponentStatus = Field(description="`up`, `degraded`, `down`, `stopped` o `unknown`.")
    next_start_at: AwareDatetime | None = Field(
        description=(
            "Próximo encendido programado (ISO 8601 UTC) de la base de datos detenida por horario; "
            "`null` en cualquier otro caso."
        ),
        examples=["2026-10-26T14:00:00Z"],
    )

    @field_validator("next_start_at")
    @classmethod
    def _utc(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        return _in_utc(value)


class PublicStatusRead(BaseModel):
    """The public status of the platform: the same result as the health query, without details."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Estado público de la plataforma. Lista cerrada de campos (FR-047)."
        },
    )

    status: GlobalStatus = Field(description="Estado global: `ok`, `degraded` o `down`.")
    checked_at: AwareDatetime = Field(
        description="Cuándo terminó la agregación, en ISO 8601 UTC.", examples=["2026-10-24T03:15:00Z"]
    )
    components: list[PublicComponentRead] = Field(
        description="Los mismos componentes que la consulta de salud, en el mismo orden."
    )

    @field_validator("checked_at")
    @classmethod
    def _utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)

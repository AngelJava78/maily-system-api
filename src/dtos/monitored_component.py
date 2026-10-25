"""Data of the registry of monitored components (spec 005, data-model.md section 3; research R14).

The DTOs check each field on its own: format, length, type and unknown fields. The rules that depend
on `kind` and the list of allowed hosts belong to the Service, which knows the stored row and the
configuration. The messages are the exact ones of `contracts/error-catalog.md` and never repeat the
value that was received (a `base_url` could carry credentials).
"""

import re
from datetime import UTC
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from src.config import valid_host
from src.messages import (
    MONITORED_COMPONENT_BASE_URL_INVALID_MESSAGE,
    MONITORED_COMPONENT_BASE_URL_REQUIRED_MESSAGE,
    MONITORED_COMPONENT_CODE_INVALID_MESSAGE,
    MONITORED_COMPONENT_CODE_REQUIRED_MESSAGE,
    MONITORED_COMPONENT_EMPTY_UPDATE_MESSAGE,
    MONITORED_COMPONENT_ENABLED_INVALID_MESSAGE,
    MONITORED_COMPONENT_KIND_INVALID_MESSAGE,
    MONITORED_COMPONENT_KIND_REQUIRED_MESSAGE,
    MONITORED_COMPONENT_NAME_REQUIRED_MESSAGE,
    MONITORED_COMPONENT_PATH_INVALID_MESSAGE,
    MONITORED_COMPONENT_SORT_ORDER_INVALID_MESSAGE,
)

RegisteredKind = Literal["service", "frontend"]
KINDS = ("service", "frontend")

CODE_PATTERN = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
# The characters of a segment of RFC 3986 without `%`: no encoding can hide `..` or `/`.
PATH_PATTERN = r"^/[A-Za-z0-9\-._~!$&'()*+,;=:@/]*$"
_CODE = re.compile(CODE_PATTERN)
_PATH = re.compile(PATH_PATTERN)
# Host (an IPv6 between brackets, or anything without `:` that `valid_host` checks) and port.
_NETLOC = re.compile(r"(?P<host>\[[^\[\]]*\]|[^:\[\]]*)(?::(?P<port>[0-9]{1,5}))?")
# Never in a `base_url`: `\`, `?` and `#` anywhere (`urlsplit` cannot tell an empty `?` or `#` apart),
# and `%`, which neither a host nor a path may carry.
_FORBIDDEN_IN_BASE_URL = frozenset("\\?#%")

MAX_CODE_LENGTH = 50
MAX_BASE_URL_LENGTH = 255
MAX_PATH_LENGTH = 200


def _is_printable_ascii(text: str) -> bool:
    """Printable ASCII without spaces (from `!` to `~`)."""
    return all("!" <= character <= "~" for character in text)


def _is_valid_path(path: str) -> bool:
    segments = path.split("/")
    return (
        _PATH.fullmatch(path) is not None
        and "//" not in path
        and not any(segment in (".", "..") for segment in segments)
    )


def validate_path(value: object) -> str:
    """A route of a component (`live_path`, `ready_path`, `info_path`), trimmed.

    It starts with a single `/`, has up to 200 characters of `PATH_PATTERN`, no `//` and no `.` or
    `..` segment; a final slash is allowed (`/healthz/`). Raises `ValueError` with the message of
    the catalog.
    """
    if not isinstance(value, str):
        raise ValueError(MONITORED_COMPONENT_PATH_INVALID_MESSAGE)
    path = value.strip()
    if len(path) > MAX_PATH_LENGTH or not _is_valid_path(path):
        raise ValueError(MONITORED_COMPONENT_PATH_INVALID_MESSAGE)
    return path


def _valid_netloc(netloc: str) -> bool:
    match = _NETLOC.fullmatch(netloc)
    if match is None:
        return False
    host, port = match["host"], match["port"]
    if port is not None and not 1 <= int(port) <= 65_535:
        return False
    if host.startswith("["):  # only an IPv6 goes between brackets
        inner = host[1:-1]
        return ":" in inner and valid_host(inner) is not None
    return valid_host(host) is not None


def validate_base_url(value: object) -> str:
    """The address of a component, normalised (research R14).

    `http` or `https`, a valid host (an IP literal or an ASCII name; see `valid_host`), an optional
    port from 1 to 65 535 and an optional path with the rules of the routes; no user or password,
    query or fragment, up to 255 characters. It is stored with the scheme and the host in lower case
    and without a final slash. Raises `ValueError` with the message of the catalog, which never
    repeats the address.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(MONITORED_COMPONENT_BASE_URL_REQUIRED_MESSAGE)
    if not isinstance(value, str):
        raise ValueError(MONITORED_COMPONENT_BASE_URL_INVALID_MESSAGE)
    text = value.strip()
    if (
        len(text) > MAX_BASE_URL_LENGTH
        or not _is_printable_ascii(text)
        or not _FORBIDDEN_IN_BASE_URL.isdisjoint(text)
    ):
        raise ValueError(MONITORED_COMPONENT_BASE_URL_INVALID_MESSAGE)
    parts = urlsplit(text)  # the scheme comes in lower case
    if (
        parts.scheme not in ("http", "https")
        or "@" in parts.netloc
        or not _valid_netloc(parts.netloc)
        or (parts.path and not _is_valid_path(parts.path))
    ):
        raise ValueError(MONITORED_COMPONENT_BASE_URL_INVALID_MESSAGE)
    return f"{parts.scheme}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def _validate_code(value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(MONITORED_COMPONENT_CODE_REQUIRED_MESSAGE)
    if not isinstance(value, str):
        raise ValueError(MONITORED_COMPONENT_CODE_INVALID_MESSAGE)
    code = value.strip()
    if not 2 <= len(code) <= MAX_CODE_LENGTH or _CODE.fullmatch(code) is None:
        raise ValueError(MONITORED_COMPONENT_CODE_INVALID_MESSAGE)
    return code


def _validate_kind(value: object) -> object:
    if value is None:
        raise ValueError(MONITORED_COMPONENT_KIND_REQUIRED_MESSAGE)
    kind = value.strip() if isinstance(value, str) else value
    if kind not in KINDS:
        raise ValueError(MONITORED_COMPONENT_KIND_INVALID_MESSAGE)
    return kind


ComponentCode = Annotated[str, BeforeValidator(_validate_code)]
ComponentKind = Annotated[RegisteredKind, BeforeValidator(_validate_kind)]
BaseUrl = Annotated[str, BeforeValidator(validate_base_url)]
ComponentPath = Annotated[str, BeforeValidator(validate_path)]

_CODE_DESCRIPTION = (
    "Código estable del componente: de 2 a 50 caracteres entre minúsculas sin acentos, dígitos y "
    "guiones. Único entre los no eliminados; `maily-system-api` y `database` están reservados."
)
_BASE_URL_DESCRIPTION = (
    "Dirección base `http` o `https`, sin usuario, contraseña, consulta ni fragmento. Su host debe "
    "estar en la lista permitida del servicio. Se guarda en minúsculas y sin barra final."
)


class MonitoredComponentRead(BaseModel):
    """A registered component: the only answer of the API that publishes its address (FR-023)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": (
                "Un componente registrado. Es el único lugar de la API donde se ve `base_url`."
            )
        },
    )

    id: UUID = Field(
        description="Identificador del componente.",
        examples=["7d3c2f0e-9a1b-4c5d-8e6f-0a1b2c3d4e5f"],
    )
    code: str = Field(description="Código estable del componente.", examples=["mailysoft-usuarios"])
    name: str = Field(description="Nombre que se muestra.", examples=["MailySoft Usuarios"])
    kind: RegisteredKind = Field(description="`service` o `frontend`.")
    base_url: str = Field(
        description="Dirección base que se consulta.", examples=["http://mailysoft-usuarios:8000"]
    )
    live_path: str = Field(
        description="Ruta de vida (servicio) o de salud (frontend).", examples=["/health/live"]
    )
    ready_path: str | None = Field(
        description="Ruta de disponibilidad de un servicio; `null` en un frontend.",
        examples=["/health/ready"],
    )
    info_path: str | None = Field(
        description="Ruta de identificación del build; en un frontend puede ser `null`.",
        examples=["/info"],
    )
    enabled: bool = Field(description="Si se consulta y aparece en la salud.", examples=[True])
    sort_order: int = Field(description="Orden en la salud (y luego por `code`).", examples=[10])
    created_at: AwareDatetime = Field(
        description="Fecha y hora del registro, en ISO 8601 UTC.", examples=["2026-10-24T17:00:00Z"]
    )
    updated_at: AwareDatetime = Field(
        description="Fecha y hora de la última modificación, en ISO 8601 UTC.",
        examples=["2026-10-24T17:00:00Z"],
    )

    @field_validator("created_at", "updated_at")
    @classmethod
    def _utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)


class MonitoredComponentCreate(BaseModel):
    """Data to register a component (FR-024 to FR-027); unknown fields are rejected (FR-030)."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "description": "Datos para registrar un componente. No se admiten campos desconocidos."
        },
    )

    code: ComponentCode = Field(
        min_length=2,
        max_length=MAX_CODE_LENGTH,
        pattern=CODE_PATTERN,
        description=_CODE_DESCRIPTION,
        examples=["mailysoft-usuarios"],
    )
    name: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "Nombre que se muestra (1 a 100 caracteres, sin contar espacios en los extremos)."
        ),
        examples=["MailySoft Usuarios"],
    )
    kind: ComponentKind = Field(
        description="`service` (contrato v1) o `frontend` (solo su ruta de salud)."
    )
    base_url: BaseUrl = Field(
        max_length=MAX_BASE_URL_LENGTH,
        description=_BASE_URL_DESCRIPTION,
        examples=["http://mailysoft-usuarios:8000"],
    )
    live_path: ComponentPath | None = Field(
        default=None,
        max_length=MAX_PATH_LENGTH,
        description="Servicio: `/health/live` por defecto. Frontend: obligatoria (su ruta de salud).",
        examples=["/healthz/"],
    )
    ready_path: ComponentPath | None = Field(
        default=None,
        max_length=MAX_PATH_LENGTH,
        description="Servicio: `/health/ready` por defecto. Frontend: debe ser nula.",
        examples=["/health/ready"],
    )
    info_path: ComponentPath | None = Field(
        default=None,
        max_length=MAX_PATH_LENGTH,
        description="Servicio: `/info` por defecto. Frontend: opcional.",
        examples=["/info"],
    )
    enabled: bool = Field(
        default=True, strict=True, description="Si se consulta. Por defecto, sí.", examples=[True]
    )
    sort_order: int = Field(
        default=0,
        strict=True,
        ge=0,
        le=9999,
        description="Orden en la salud (0 a 9999). Por defecto, 0.",
        examples=[10],
    )


class MonitoredComponentUpdate(BaseModel):
    """Changes to a component (FR-028): only the fields that are sent change, at least one."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "description": (
                "Campos a modificar (al menos uno). El componente resultante se valida como un "
                "alta. No se pueden cambiar el identificador ni las fechas."
            )
        },
    )

    code: ComponentCode | None = Field(
        default=None,
        max_length=MAX_CODE_LENGTH,
        description="Nuevo código. No puede ser nulo.",
        examples=["mailysoft-pacientes"],
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Nuevo nombre. No puede ser nulo.",
        examples=["MailySoft Pacientes"],
    )
    kind: ComponentKind | None = Field(
        default=None,
        description=(
            "Nuevo tipo. Pasar a `frontend` exige enviar `ready_path` nula. No puede ser nulo."
        ),
    )
    base_url: BaseUrl | None = Field(
        default=None,
        max_length=MAX_BASE_URL_LENGTH,
        description=(
            "Nueva dirección base; se vuelve a comprobar la lista permitida. No puede ser nula."
        ),
        examples=["http://mailysoft-pacientes:8000"],
    )
    live_path: ComponentPath | None = Field(
        default=None, max_length=MAX_PATH_LENGTH, description="Nueva ruta de vida o de salud."
    )
    ready_path: ComponentPath | None = Field(
        default=None,
        max_length=MAX_PATH_LENGTH,
        description="Nueva ruta de disponibilidad; nula en un frontend.",
    )
    info_path: ComponentPath | None = Field(
        default=None, max_length=MAX_PATH_LENGTH, description="Nueva ruta de identificación."
    )
    enabled: bool | None = Field(
        default=None,
        strict=True,
        description="`false` deja de consultarlo; `true` lo vuelve a consultar.",
        examples=[False],
    )
    sort_order: int | None = Field(
        default=None,
        strict=True,
        ge=0,
        le=9999,
        description="Nuevo orden (0 a 9999). No puede ser nulo.",
        examples=[5],
    )

    # The validators below only run for a field that is in the body, so a `null` that was sent on
    # purpose is reported on the field itself (the paths may be null: the Service decides by kind).

    @field_validator("code", "name", "kind", "base_url", "enabled", "sort_order")
    @classmethod
    def _cannot_be_null(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            raise ValueError(_NULL_MESSAGES[info.field_name])
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "MonitoredComponentUpdate":
        # `model_fields_set` tells "not sent" apart from an explicit `null`.
        if not self.model_fields_set:
            raise ValueError(MONITORED_COMPONENT_EMPTY_UPDATE_MESSAGE)
        return self


_NULL_MESSAGES = {
    "code": MONITORED_COMPONENT_CODE_REQUIRED_MESSAGE,
    "name": MONITORED_COMPONENT_NAME_REQUIRED_MESSAGE,
    "kind": MONITORED_COMPONENT_KIND_REQUIRED_MESSAGE,
    "base_url": MONITORED_COMPONENT_BASE_URL_REQUIRED_MESSAGE,
    "enabled": MONITORED_COMPONENT_ENABLED_INVALID_MESSAGE,
    "sort_order": MONITORED_COMPONENT_SORT_ORDER_INVALID_MESSAGE,
}

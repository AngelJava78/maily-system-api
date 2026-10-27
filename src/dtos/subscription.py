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
from src.dtos.subscription_type import SubscriptionTypeRead
from src.messages import (
    SUBSCRIPTION_ANNUAL_PRICE_REQUIRED_MESSAGE,
    SUBSCRIPTION_ASSISTANTS_LIMIT_INVALID_MESSAGE,
    SUBSCRIPTION_CONSULTING_ROOMS_LIMIT_INVALID_MESSAGE,
    SUBSCRIPTION_DOCTORS_LIMIT_INVALID_MESSAGE,
    SUBSCRIPTION_EMPTY_UPDATE_MESSAGE,
    SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE,
    SUBSCRIPTION_NAME_REQUIRED_MESSAGE,
    SUBSCRIPTION_NEW_PATIENTS_PER_YEAR_LIMIT_INVALID_MESSAGE,
    SUBSCRIPTION_OTHER_FEATURES_NOT_LIST_MESSAGE,
    SUBSCRIPTION_PRICE_REQUIRED_MESSAGE,
    SUBSCRIPTION_SELF_SERVICE_INVALID_MESSAGE,
    SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE,
    SUBSCRIPTION_TRIAL_DAYS_INVALID_MESSAGE,
)

# One item of what a subscription includes beyond its modules: 1 to 150 characters once trimmed.
FeatureText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]

# A key of the clinic-module catalog the users API owns (src/clinic_modules.py); never the module's
# display name. Same pattern that API itself requires of a module `key` (contracts/users-api-integration.md).
ModuleKeyText = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=50)
]


class SubscriptionRead(BaseModel):
    """A subscription as the API shows it (FR-008): status, modules, limits and clinics count."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Una suscripción (plan) con su estatus, sus módulos y sus límites."
        },
    )

    id: int = Field(ge=1, description="Identificador de la suscripción.", examples=[1])
    name: str = Field(description="Nombre de la suscripción.", examples=["Profesional"])
    description: str | None = Field(
        description="Descripción de la suscripción, o `null` si no tiene.",
        examples=["Para clínicas en crecimiento."],
    )
    subscription_type: SubscriptionTypeRead = Field(
        description=(
            "A quién va dirigida la suscripción, tomado de su catálogo (se edita a mano): quien "
            "consume la API debe basarse en su `id`. Obligatorio desde la creación y fijo para "
            "siempre."
        )
    )
    monthly_price: Decimal = Field(
        description=(
            "Precio mensual en pesos mexicanos sin IVA, con dos decimales (cadena para no perder "
            "precisión)."
        ),
        examples=["1299.00"],
    )
    annual_price: Decimal = Field(
        description=(
            "Precio anual en pesos mexicanos sin IVA, con dos decimales. Independiente del precio "
            "mensual (sin proporción obligatoria)."
        ),
        examples=["12990.00"],
    )
    trial_days: int = Field(
        ge=0,
        le=3650,
        description="Días de prueba del plan. `0` = sin periodo de prueba.",
        examples=[14],
    )
    self_service: bool = Field(
        description=(
            "Si la suscripción está en autoconsumo (visible y contratable por su cuenta en el "
            "portal de MailySoft)."
        ),
        examples=[True],
    )
    module_keys: list[str] = Field(
        description=(
            "Claves de los módulos de clínica que incluye, ordenadas alfabéticamente. Siempre "
            "incluye «patients». El nombre de cada módulo se consulta directamente en la API de "
            "usuarios."
        ),
        examples=[["clinical_records", "patients", "scheduling"]],
    )
    other_features: list[str] = Field(
        description=(
            "Otras funcionalidades del plan que no son módulos (soporte, capacitación…), en el "
            "orden en que se guardaron."
        ),
        examples=[["Soporte por correo y WhatsApp"]],
    )  
    consulting_rooms_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de consultorios que puede dar de alta la clínica."
    )
    doctors_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de doctores que puede dar de alta la clínica."
    )
    assistants_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de asistentes que puede dar de alta la clínica."
    )
    new_patients_per_year_limit: int = Field(
        ge=0,
        le=1_000_000,
        description="Techo de pacientes nuevos que puede registrar la clínica cada año.",
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

    @field_serializer("monthly_price", "annual_price")
    def _two_decimals(self, value: Decimal) -> str:
        # What was accepted without zeros ("4500") is always shown with two decimals ("4500.00").
        return format(value.quantize(Decimal("0.01")), "f")


class SubscriptionCreate(BaseModel):
    """Data to create a subscription (FR-011 to FR-024); unknown fields are rejected (FR-030)."""

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
        examples=["Profesional"],
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
    subscription_type_id: Annotated[int, Field(strict=True, gt=0)] = Field(
        description=(
            "Identificador de un tipo del catálogo `subscription_types` (hoy, 1 Individual o 2 "
            "Empresarial). Obligatorio. Fijo para siempre una vez creada la suscripción: ninguna "
            "operación posterior lo modifica. Un identificador que no exista en el catálogo se "
            "rechaza con `subscription_type_not_found`."
        ),
        examples=[1],
    )
    monthly_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description=(
            "Precio mensual en pesos mexicanos, de 0 a 99999999.99, con hasta dos decimales "
            "(número o cadena)."
        ),
        examples=["1299.00"],
    )
    annual_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description=(
            "Precio anual en pesos mexicanos, de 0 a 99999999.99, con hasta dos decimales "
            "(número o cadena). Obligatorio e independiente del precio mensual."
        ),
        examples=["12990.00"],
    )
    trial_days: int = Field(
        default=0,
        ge=0,
        le=3650,
        description="Días de prueba. `0` = sin periodo de prueba (valor por defecto si se omite).",
        examples=[14],
    )
    self_service: bool = Field(
        default=False,
        description=(
            "Si queda en autoconsumo en el portal de MailySoft. Por defecto, en falso (no aparece "
            "hasta que se active a propósito)."
        ),
        examples=[True],
    )
    module_keys: list[ModuleKeyText] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Claves de los módulos de clínica, además de «patients» (que siempre se incluye "
            "aunque no se envíe). Se validan contra la API de usuarios y contra sus dependencias."
        ),
        examples=[["scheduling", "reminders"]],
    )
    other_features: list[FeatureText] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Otras funcionalidades del plan que no son módulos: hasta 20 textos de 1 a 150 "
            "caracteres. Puede estar vacía."
        ),
        examples=[["Soporte por correo y WhatsApp"]],
    )
    consulting_rooms_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de consultorios. Obligatorio."
    )
    doctors_limit: int = Field(ge=0, le=1_000_000, description="Techo de doctores. Obligatorio.")
    assistants_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de asistentes. Obligatorio."
    )
    new_patients_per_year_limit: int = Field(
        ge=0, le=1_000_000, description="Techo de pacientes nuevos al año. Obligatorio."
    )

    @field_validator("description")
    @classmethod
    def empty_description_means_none(cls, value: str | None) -> str | None:
        return value or None


class SubscriptionUpdate(BaseModel):
    """Changes to a subscription (FR-026): only the fields that are sent are modified."""

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
        examples=["1399.00"],
    )
    annual_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Nuevo precio anual (mismo formato que al crear). No puede ser nulo.",
        examples=["13990.00"],
    )
    trial_days: int | None = Field(
        default=None,
        ge=0,
        le=3650,
        description="Nuevos días de prueba. No puede ser nulo.",
        examples=[30],
    )
    self_service: bool | None = Field(
        default=None, description="Nuevo autoconsumo. No puede ser nulo.", examples=[True]
    )
    module_keys: list[ModuleKeyText] | None = Field(
        default=None,
        max_length=50,
        description=(
            "Nuevo conjunto completo de módulos (sustituye al anterior; «patients» se conserva "
            "aunque no se envíe). No puede ser nulo."
        ),
        examples=[["scheduling", "reminders"]],
    )
    other_features: list[FeatureText] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Nueva lista completa de otras funcionalidades (sustituye a la anterior). `[]` la "
            "vacía. No puede ser nula."
        ),
        examples=[["Soporte por correo y WhatsApp"]],
    )
    consulting_rooms_limit: int | None = Field(
        default=None, ge=0, le=1_000_000, description="Nuevo techo de consultorios. No puede ser nulo."
    )
    doctors_limit: int | None = Field(
        default=None, ge=0, le=1_000_000, description="Nuevo techo de doctores. No puede ser nulo."
    )
    assistants_limit: int | None = Field(
        default=None, ge=0, le=1_000_000, description="Nuevo techo de asistentes. No puede ser nulo."
    )
    new_patients_per_year_limit: int | None = Field(
        default=None,
        ge=0,
        le=1_000_000,
        description="Nuevo techo de pacientes nuevos al año. No puede ser nulo.",
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

    @field_validator("annual_price")
    @classmethod
    def annual_price_cannot_be_null(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise ValueError(SUBSCRIPTION_ANNUAL_PRICE_REQUIRED_MESSAGE)
        return value

    @field_validator("trial_days")
    @classmethod
    def trial_days_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError(SUBSCRIPTION_TRIAL_DAYS_INVALID_MESSAGE)
        return value

    @field_validator("self_service")
    @classmethod
    def self_service_cannot_be_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError(SUBSCRIPTION_SELF_SERVICE_INVALID_MESSAGE)
        return value

    @field_validator("module_keys")
    @classmethod
    def module_keys_cannot_be_null(cls, value: list[str] | None) -> list[str]:
        if value is None:  # the column is NOT NULL: [] is how the extra modules are cleared
            raise ValueError(SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE)
        return value

    @field_validator("other_features")
    @classmethod
    def other_features_cannot_be_null(cls, value: list[str] | None) -> list[str]:
        if value is None:  # the column is NOT NULL: [] is how other_features is cleared
            raise ValueError(SUBSCRIPTION_OTHER_FEATURES_NOT_LIST_MESSAGE)
        return value

    @field_validator("consulting_rooms_limit")
    @classmethod
    def consulting_rooms_limit_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError(SUBSCRIPTION_CONSULTING_ROOMS_LIMIT_INVALID_MESSAGE)
        return value

    @field_validator("doctors_limit")
    @classmethod
    def doctors_limit_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError(SUBSCRIPTION_DOCTORS_LIMIT_INVALID_MESSAGE)
        return value

    @field_validator("assistants_limit")
    @classmethod
    def assistants_limit_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError(SUBSCRIPTION_ASSISTANTS_LIMIT_INVALID_MESSAGE)
        return value

    @field_validator("new_patients_per_year_limit")
    @classmethod
    def new_patients_per_year_limit_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError(SUBSCRIPTION_NEW_PATIENTS_PER_YEAR_LIMIT_INVALID_MESSAGE)
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
    """The status a subscription moves to (FR-027); deleting has its own operation."""

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

"""Vocabulario de la API: códigos de error, mensajes en español y mensajes de validación (FR-021)."""

from decimal import Decimal
from typing import Annotated, Any

import pytest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from src import messages
from src.error_handlers import translate_validation_errors
from src.exceptions import (
    AuthorizationUnavailableError,
    ClinicsCheckUnavailableError,
    InvalidTokenError,
    PermissionDeniedError,
    SubscriptionHasClinicsError,
    SubscriptionNameAlreadyExistsError,
    SubscriptionNotFoundError,
    SubscriptionStatusUnchangedError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.messages import ErrorCode

EXPECTED_MESSAGES = {
    ErrorCode.UNAUTHENTICATED: "Debe iniciar sesión para usar esta operación.",
    ErrorCode.TOKEN_EXPIRED: "Su sesión venció. Inicie sesión de nuevo.",
    ErrorCode.INVALID_TOKEN: "El token de acceso no es válido.",
    ErrorCode.PERMISSION_DENIED: (
        "No tiene permiso para realizar esta operación. Permiso requerido: {permission}."
    ),
    ErrorCode.AUTHORIZATION_UNAVAILABLE: (
        "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde."
    ),
    ErrorCode.SUBSCRIPTION_NOT_FOUND: (
        "No se encontró la suscripción con el identificador {subscription_id}."
    ),
    ErrorCode.SUBSCRIPTION_NAME_ALREADY_EXISTS: "Ya existe una suscripción con el nombre «{name}».",
    ErrorCode.SUBSCRIPTION_STATUS_UNCHANGED: (
        "La suscripción con el identificador {subscription_id} ya tiene el estatus {status}."
    ),
    ErrorCode.SUBSCRIPTION_HAS_CLINICS: (
        "No se puede eliminar la suscripción con el identificador {subscription_id} porque tiene "
        "clínicas asignadas."
    ),
    ErrorCode.CLINICS_CHECK_UNAVAILABLE: (
        "No se pudo comprobar si la suscripción con el identificador {subscription_id} tiene "
        "clínicas asignadas. No se eliminó; inténtelo de nuevo más tarde."
    ),
    ErrorCode.VALIDATION_ERROR: "Hay datos no válidos en la solicitud.",
    ErrorCode.INTERNAL_ERROR: "Ocurrió un error inesperado. Inténtelo de nuevo más tarde.",
}

BEARER = {"WWW-Authenticate": "Bearer"}
BEARER_INVALID = {"WWW-Authenticate": 'Bearer error="invalid_token"'}


def test_the_error_codes_are_exactly_the_twelve_of_the_catalog():
    assert {code.value for code in ErrorCode} == {
        "unauthenticated",
        "token_expired",
        "invalid_token",
        "permission_denied",
        "authorization_unavailable",
        "subscription_not_found",
        "subscription_name_already_exists",
        "subscription_status_unchanged",
        "subscription_has_clinics",
        "clinics_check_unavailable",
        "validation_error",
        "internal_error",
    }


@pytest.mark.parametrize("code", list(EXPECTED_MESSAGES), ids=lambda code: code.value)
def test_every_code_has_the_exact_message_of_the_catalog(code: ErrorCode):
    assert getattr(messages, f"{code.name}_MESSAGE") == EXPECTED_MESSAGES[code]


@pytest.mark.parametrize(
    ("error", "code", "status_code", "headers", "message"),
    [
        (UnauthenticatedError(), ErrorCode.UNAUTHENTICATED, 401, BEARER, None),
        (TokenExpiredError(), ErrorCode.TOKEN_EXPIRED, 401, BEARER_INVALID, None),
        (InvalidTokenError(), ErrorCode.INVALID_TOKEN, 401, BEARER_INVALID, None),
        (
            PermissionDeniedError("subscriptions:write"),
            ErrorCode.PERMISSION_DENIED,
            403,
            None,
            "No tiene permiso para realizar esta operación. Permiso requerido: subscriptions:write.",
        ),
        (AuthorizationUnavailableError(), ErrorCode.AUTHORIZATION_UNAVAILABLE, 503, None, None),
        (
            SubscriptionNotFoundError(42),
            ErrorCode.SUBSCRIPTION_NOT_FOUND,
            404,
            None,
            "No se encontró la suscripción con el identificador 42.",
        ),
        (
            SubscriptionNameAlreadyExistsError("pro"),
            ErrorCode.SUBSCRIPTION_NAME_ALREADY_EXISTS,
            409,
            None,
            "Ya existe una suscripción con el nombre «pro».",
        ),
        (
            SubscriptionStatusUnchangedError(1, "Inactiva"),
            ErrorCode.SUBSCRIPTION_STATUS_UNCHANGED,
            409,
            None,
            "La suscripción con el identificador 1 ya tiene el estatus Inactiva.",
        ),
        (
            SubscriptionHasClinicsError(1),
            ErrorCode.SUBSCRIPTION_HAS_CLINICS,
            409,
            None,
            "No se puede eliminar la suscripción con el identificador 1 porque tiene clínicas "
            "asignadas.",
        ),
        (
            ClinicsCheckUnavailableError(1),
            ErrorCode.CLINICS_CHECK_UNAVAILABLE,
            503,
            None,
            "No se pudo comprobar si la suscripción con el identificador 1 tiene clínicas "
            "asignadas. No se eliminó; inténtelo de nuevo más tarde.",
        ),
    ],
    ids=lambda value: value.__class__.__name__ if isinstance(value, Exception) else None,
)
def test_every_error_has_its_code_status_headers_and_message(
    error, code, status_code, headers, message
):
    assert error.code == code
    assert error.status_code == status_code
    assert error.headers == headers
    assert error.message == (message or EXPECTED_MESSAGES[code])


def test_the_headers_of_an_error_are_a_copy_that_cannot_leak_between_errors():
    first = UnauthenticatedError()
    first.headers["X-Other"] = "changed"

    assert UnauthenticatedError().headers == BEARER


# --- Mensajes de validación (traducción de los errores de Pydantic) ---


class _Create(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    monthly_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    features: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    ] = Field(default_factory=list, max_length=20)


class _Status(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_id: Annotated[int, Field(strict=True)]

    @field_validator("status_id")
    @classmethod
    def allowed(cls, value: int) -> int:
        if value not in (1, 2, 3):
            raise ValueError(messages.SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE)
        return value


class _Update(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError(messages.SUBSCRIPTION_EMPTY_UPDATE_MESSAGE)
        return self


VALID = {"name": "Pro", "monthly_price": 100}


def translated(model: type[BaseModel], payload: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as info:
        model.model_validate(payload)
    errors = [{**error, "loc": ("body", *error["loc"])} for error in info.value.errors()]
    return [(e.field, e.message) for e in translate_validation_errors(errors, "subscriptions")]


NAME_REQUIRED = "El nombre de la suscripción es obligatorio."
PRICE_INVALID = (
    "El precio mensual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales."
)
NOT_LIST = "Lo que incluye la suscripción debe ser una lista de textos."
ELEMENT = "Cada elemento de lo que incluye la suscripción debe tener de 1 a 150 caracteres."
STATUS_REQUIRED = "El estatus es obligatorio y debe ser un número entero."
STATUS_NOT_ALLOWED = "El estatus debe ser uno de los que admite esta operación (1, 2 o 3)."


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"monthly_price": 1}, "name", NAME_REQUIRED),
        ({"name": None, "monthly_price": 1}, "name", NAME_REQUIRED),
        ({"name": "   ", "monthly_price": 1}, "name", NAME_REQUIRED),
        (
            {"name": "x" * 101, "monthly_price": 1},
            "name",
            "El nombre de la suscripción no puede tener más de 100 caracteres.",
        ),
        (
            {"name": 5, "monthly_price": 1},
            "name",
            "El nombre de la suscripción debe ser un texto.",
        ),
        (
            {**VALID, "description": "d" * 501},
            "description",
            "La descripción no puede tener más de 500 caracteres.",
        ),
        ({"name": "Pro"}, "monthly_price", "El precio mensual es obligatorio."),
        ({"name": "Pro", "monthly_price": None}, "monthly_price", "El precio mensual es obligatorio."),
        ({"name": "Pro", "monthly_price": -1}, "monthly_price", PRICE_INVALID),
        ({"name": "Pro", "monthly_price": "4500.555"}, "monthly_price", PRICE_INVALID),
        ({"name": "Pro", "monthly_price": "abc"}, "monthly_price", PRICE_INVALID),
        ({"name": "Pro", "monthly_price": 100000000}, "monthly_price", PRICE_INVALID),
        ({**VALID, "features": "abc"}, "features", NOT_LIST),
        ({**VALID, "features": None}, "features", NOT_LIST),
        ({**VALID, "features": [1]}, "features", NOT_LIST),
        (
            {**VALID, "features": [f"f{n}" for n in range(21)]},
            "features",
            "Lo que incluye la suscripción no puede tener más de 20 elementos.",
        ),
        ({**VALID, "features": [""]}, "features", ELEMENT),
        ({**VALID, "features": ["  "]}, "features", ELEMENT),
        ({**VALID, "features": ["e" * 151]}, "features", ELEMENT),
        ({**VALID, "status": 1}, "status", "El campo «status» no está permitido."),
        ({**VALID, "clinics_count": 2}, "clinics_count", "El campo «clinics_count» no está permitido."),
    ],
)
def test_the_validation_errors_of_a_subscription_have_the_catalog_messages(payload, field, message):
    assert (field, message) in translated(_Create, payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, STATUS_REQUIRED),
        ({"status_id": None}, STATUS_REQUIRED),
        ({"status_id": "2"}, STATUS_REQUIRED),
        ({"status_id": 2.5}, STATUS_REQUIRED),
        ({"status_id": True}, STATUS_REQUIRED),
        ({"status_id": 4}, STATUS_NOT_ALLOWED),
        ({"status_id": 99}, STATUS_NOT_ALLOWED),
    ],
)
def test_the_status_errors_have_the_catalog_messages(payload, message):
    assert translated(_Status, payload) == [("status_id", message)]


def test_an_empty_update_is_reported_on_the_body():
    assert translated(_Update, {}) == [
        ("body", "Hay que enviar al menos un dato para modificar.")
    ]


def test_an_unreadable_body_is_reported_on_the_body():
    errors = translate_validation_errors(
        [{"type": "json_invalid", "loc": ("body", 0), "msg": "bad", "input": "{oops"}],
        "subscriptions",
    )

    assert [(e.field, e.message) for e in errors] == [
        ("body", "El cuerpo de la solicitud no es válido.")
    ]


@pytest.mark.parametrize("error_type", ["int_parsing", "greater_than"])
def test_a_bad_subscription_id_in_the_path_is_reported(error_type):
    errors = translate_validation_errors(
        [{"type": error_type, "loc": ("path", "subscription_id"), "msg": "bad", "input": "abc"}],
        "subscriptions",
    )

    assert [(e.field, e.message) for e in errors] == [
        ("subscription_id", "El identificador de la suscripción debe ser un número entero positivo.")
    ]


def test_the_validation_messages_never_repeat_the_value_that_was_received():
    secret = "valor-secreto-123"

    found = translated(_Create, {**VALID, "password": secret, "name": "x" * 101})

    assert all(secret not in message for _, message in found)
    assert all("x" * 20 not in message for _, message in found)


def test_no_message_of_the_api_mentions_a_token_value():
    texts = [value for name, value in vars(messages).items() if name.endswith("_MESSAGE")]

    assert texts
    assert all("Bearer" not in text for text in texts)

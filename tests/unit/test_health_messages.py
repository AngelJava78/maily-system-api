"""Vocabulary of the registry of components (spec 005, FR-030; contracts/error-catalog.md).

Two new error codes (the catalog goes from 15 to 17) and the Spanish messages of the validation of
`/api/v1/monitored-components`, which never repeat the value that was received.
"""

from uuid import UUID

import pytest

from src import messages
from src.error_handlers import translate_validation_errors
from src.exceptions import (
    MonitoredComponentCodeAlreadyExistsError,
    MonitoredComponentDataError,
    MonitoredComponentNotFoundError,
)
from src.messages import ErrorCode

RESOURCE = "monitored-components"
COMPONENT_ID = UUID("7d3c2f0e-9a1b-4c5d-8e6f-0a1b2c3d4e5f")


def test_the_two_new_messages_are_the_exact_texts_of_the_catalog():
    assert messages.MONITORED_COMPONENT_NOT_FOUND_MESSAGE == (
        "No se encontró el componente monitoreado con el identificador {component_id}."
    )
    assert messages.MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE == (
        "Ya existe un componente monitoreado con el código «{code}»."
    )


def test_the_catalog_has_eighteen_codes_with_the_two_new_ones():
    assert len(ErrorCode) == 18
    assert ErrorCode.MONITORED_COMPONENT_NOT_FOUND.value == "monitored_component_not_found"
    assert ErrorCode.MONITORED_COMPONENT_CODE_ALREADY_EXISTS.value == "monitored_component_code_already_exists"


def test_the_new_errors_have_their_status_code_and_message():
    not_found = MonitoredComponentNotFoundError(COMPONENT_ID)
    conflict = MonitoredComponentCodeAlreadyExistsError("database")
    invalid = MonitoredComponentDataError([MonitoredComponentDataError.field_error("base_url", "x")])

    assert (not_found.status_code, not_found.code) == (404, ErrorCode.MONITORED_COMPONENT_NOT_FOUND)
    assert not_found.message == (
        "No se encontró el componente monitoreado con el identificador 7d3c2f0e-9a1b-4c5d-8e6f-0a1b2c3d4e5f."
    )
    assert (conflict.status_code, conflict.code) == (409, ErrorCode.MONITORED_COMPONENT_CODE_ALREADY_EXISTS)
    assert conflict.message == "Ya existe un componente monitoreado con el código «database»."
    assert (invalid.status_code, invalid.code) == (422, ErrorCode.VALIDATION_ERROR)
    assert invalid.message == "Hay datos no válidos en la solicitud."


def error(error_type: str, field: str, input_value: object = "valor-secreto-123") -> dict:
    return {"type": error_type, "loc": ("body", field), "msg": "x", "input": input_value}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (error("missing", "code"), ("code", "El código del componente es obligatorio.")),
        (error("missing", "name"), ("name", "El nombre del componente es obligatorio.")),
        (error("string_too_short", "name"), ("name", "El nombre del componente es obligatorio.")),
        (error("string_too_long", "name"), ("name", "El nombre del componente no puede tener más de 100 caracteres.")),
        (error("string_type", "name", 7), ("name", "El nombre del componente debe ser un texto.")),
        (error("missing", "kind"), ("kind", "El tipo del componente es obligatorio.")),
        (error("missing", "base_url"), ("base_url", "La dirección base del componente es obligatoria.")),
        (error("bool_type", "enabled", "si"), ("enabled", "«enabled» debe ser verdadero o falso.")),
        (error("bool_type", "enabled", None), ("enabled", "«enabled» debe ser verdadero o falso.")),
        (error("int_type", "sort_order", "5"), ("sort_order", "El orden debe ser un número entero de 0 a 9999.")),
        (error("less_than_equal", "sort_order", 10000), ("sort_order", "El orden debe ser un número entero de 0 a 9999.")),
        (error("int_type", "sort_order", None), ("sort_order", "El orden debe ser un número entero de 0 a 9999.")),
        (
            {"type": "uuid_parsing", "loc": ("path", "component_id"), "msg": "x", "input": "no-es-uuid"},
            ("component_id", "El identificador del componente debe ser un UUID."),
        ),
        (error("extra_forbidden", "deleted_at"), ("deleted_at", "El campo «deleted_at» no está permitido.")),
    ],
)
def test_each_validation_of_the_registry_has_its_message_on_its_field(raw, expected):
    [found] = translate_validation_errors([raw], RESOURCE)

    assert (found.field, found.message) == expected
    assert "valor-secreto-123" not in found.message


def test_an_error_decided_by_the_service_keeps_its_field_and_its_message():
    raw = MonitoredComponentDataError.field_error("base_url", messages.MONITORED_COMPONENT_HOST_NOT_ALLOWED_MESSAGE)

    [found] = translate_validation_errors([raw], RESOURCE)

    assert (found.field, found.message) == (
        "base_url",
        "El host de la dirección base no está entre los hosts permitidos por el servicio.",
    )


def test_the_messages_of_the_subscriptions_do_not_change():
    [found] = translate_validation_errors([error("missing", "name")], "subscriptions")

    assert found.message == "El nombre de la suscripción es obligatorio."

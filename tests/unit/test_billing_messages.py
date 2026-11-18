"""The error codes, messages and errors of the subscription periods (spec 010, FR-045).

The texts come from `specs/010-subscription-periods/contracts/error-catalog.md` and must not be
paraphrased: consumers rely on the codes and people read the messages.
"""

from uuid import UUID

import pytest

from src import messages
from src.error_handlers import translate_validation_errors
from src.exceptions import (
    AppError,
    NothingToChargeError,
    OrganizationCheckUnavailableError,
    OrganizationNotFoundError,
    OrganizationSubscriptionNotFoundError,
    PaymentsUnavailableError,
)
from src.messages import VALIDATION_MESSAGES, ErrorCode

ORGANIZATION_ID = UUID("0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")

NEW_CODES = {
    "ORGANIZATION_NOT_FOUND": "organization_not_found",
    "ORGANIZATION_CHECK_UNAVAILABLE": "organization_check_unavailable",
    "PAYMENTS_UNAVAILABLE": "payments_unavailable",
    "NOTHING_TO_CHARGE": "nothing_to_charge",
    "ORGANIZATION_SUBSCRIPTION_NOT_FOUND": "organization_subscription_not_found",
}


def test_the_five_new_codes_exist_with_their_exact_values():
    for name, value in NEW_CODES.items():
        assert ErrorCode[name].value == value


def test_the_catalog_has_twenty_two_codes():
    # 17 of the specs 001 to 009 plus the 5 of the subscription periods (spec 010).
    assert len(ErrorCode) == 22


@pytest.mark.parametrize(
    ("error", "code", "status_code", "message"),
    [
        (
            OrganizationNotFoundError(ORGANIZATION_ID),
            ErrorCode.ORGANIZATION_NOT_FOUND,
            404,
            f"No se encontró la organización con el identificador {ORGANIZATION_ID}.",
        ),
        (
            OrganizationCheckUnavailableError(),
            ErrorCode.ORGANIZATION_CHECK_UNAVAILABLE,
            503,
            "No se pudo comprobar la organización por ahora. No se hizo ningún cambio; "
            "inténtelo de nuevo más tarde.",
        ),
        (
            PaymentsUnavailableError(),
            ErrorCode.PAYMENTS_UNAVAILABLE,
            503,
            "No se pudo crear el pago por ahora. No se registró ningún cobro nuevo; "
            "inténtelo de nuevo más tarde.",
        ),
        (
            NothingToChargeError(),
            ErrorCode.NOTHING_TO_CHARGE,
            409,
            "La suscripción de la organización no tiene nada que cobrar: su importe vigente es 0.00.",
        ),
        (
            OrganizationSubscriptionNotFoundError(),
            ErrorCode.ORGANIZATION_SUBSCRIPTION_NOT_FOUND,
            409,
            "El plan de la organización no existe en el catálogo de suscripciones.",
        ),
    ],
    ids=lambda value: value.value if isinstance(value, ErrorCode) else None,
)
def test_each_new_error_has_its_code_status_and_exact_message(error, code, status_code, message):
    assert isinstance(error, AppError)
    assert (error.code, error.status_code, error.message) == (code, status_code, message)
    assert error.headers is None


def test_the_constants_follow_the_naming_of_the_other_codes():
    # `test_error_messages` finds the text of a code as `<CODE_NAME>_MESSAGE`.
    for name in NEW_CODES:
        assert isinstance(getattr(messages, f"{name}_MESSAGE"), str), name


def test_the_not_found_message_only_repeats_the_identifier_that_was_sent():
    message = OrganizationNotFoundError(ORGANIZATION_ID).message

    assert str(ORGANIZATION_ID) in message
    # Neither the organization's owner nor any detail of the clinics API can appear in it.
    assert "http" not in message and "Bearer" not in message


def test_no_message_carries_an_address_a_token_or_an_internal_marker():
    texts = [
        messages.ORGANIZATION_CHECK_UNAVAILABLE_MESSAGE,
        messages.PAYMENTS_UNAVAILABLE_MESSAGE,
        messages.NOTHING_TO_CHARGE_MESSAGE,
        messages.ORGANIZATION_SUBSCRIPTION_NOT_FOUND_MESSAGE,
    ]

    for text in texts:
        assert "http" not in text
        assert "Bearer" not in text
        assert "SECRETO" not in text


def test_the_validation_message_of_the_organization_identifier():
    block = VALIDATION_MESSAGES["subscription-periods"]

    assert block[("organization_id", "invalid")] == (
        "El identificador de la organización debe ser un UUID."
    )


def test_an_identifier_that_is_not_a_uuid_gets_its_message_and_is_not_repeated():
    error = {
        "type": "uuid_parsing",
        "loc": ("path", "organization_id"),
        "msg": "Input should be a valid UUID",
        "input": "valor-secreto-123",
    }

    found = translate_validation_errors([error], "subscription-periods")

    assert [(e.field, e.message) for e in found] == [
        ("organization_id", "El identificador de la organización debe ser un UUID.")
    ]
    assert "valor-secreto-123" not in found[0].message


def test_the_other_resources_do_not_get_this_message():
    error = {
        "type": "uuid_parsing",
        "loc": ("path", "organization_id"),
        "msg": "Input should be a valid UUID",
        "input": "x",
    }

    found = translate_validation_errors([error], "subscriptions")

    assert found[0].message != "El identificador de la organización debe ser un UUID."

"""The only new message of the dashboard: the validation of `limit` (spec 003, error-catalog.md)."""

import pytest

from src import messages
from src.error_handlers import translate_validation_errors
from src.messages import ErrorCode

LIMIT_MESSAGE = "El parámetro «limit» debe ser un número entero mayor o igual que 1."


def error_of(error_type: str) -> dict:
    return {"type": error_type, "loc": ("query", "limit"), "msg": "invalid", "input": None}


def test_the_message_is_the_exact_text_of_the_catalog():
    assert messages.DASHBOARD_LIMIT_INVALID_MESSAGE == LIMIT_MESSAGE


# The Router raises `int_parsing`; `greater_than_equal` is what a declared `ge=1` would raise.
@pytest.mark.parametrize("error_type", ["int_parsing", "greater_than_equal"])
def test_an_invalid_limit_is_reported_on_the_limit_field_with_that_message(error_type):
    found = translate_validation_errors([error_of(error_type)], "dashboard")

    assert [(e.field, e.message) for e in found] == [("limit", LIMIT_MESSAGE)]


def test_each_resource_keeps_its_own_messages():
    found = translate_validation_errors([error_of("int_parsing")], "subscriptions")

    assert [e.message for e in found] != [LIMIT_MESSAGE]


def test_no_error_code_was_added():
    assert len(ErrorCode) == 15  # spec 004 added 3 module-related codes; reviewed, no dashboard impact
    assert ErrorCode.VALIDATION_ERROR.value == "validation_error"


def test_the_message_never_repeats_a_received_value():
    error = {**error_of("int_parsing"), "input": "valor-secreto-123"}

    found = translate_validation_errors([error], "dashboard")

    assert "valor-secreto-123" not in found[0].message

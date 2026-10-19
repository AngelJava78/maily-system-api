"""Default number of recent clinics of the dashboard: `DASHBOARD_RECENT_CLINICS_LIMIT` (FR-017 to FR-019)."""

import pytest
from pydantic import ValidationError

from src.config import (
    DashboardSettings,
    IntegrationSettings,
    configuration_error_message,
)

VARIABLE = "DASHBOARD_RECENT_CLINICS_LIMIT"
FIELD = "dashboard_recent_clinics_limit"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (VARIABLE, "USERS_API_BASE_URL", "CLINICS_API_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def loaded() -> int:
    return DashboardSettings(_env_file=None).dashboard_recent_clinics_limit


def error_of_variable(value: str) -> ValidationError:
    with pytest.raises(ValidationError) as info:
        DashboardSettings(_env_file=None)
    return info.value


def test_without_the_variable_the_default_is_five():
    assert loaded() == 5


def test_an_empty_variable_counts_as_not_defined(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(VARIABLE, "")

    assert loaded() == 5


@pytest.mark.parametrize(("text", "expected"), [("3", 3), ("5", 5), ("10", 10), (" 5 ", 5)])
def test_only_three_five_and_ten_are_allowed(monkeypatch: pytest.MonkeyPatch, text, expected):
    monkeypatch.setenv(VARIABLE, text)

    assert loaded() == expected


@pytest.mark.parametrize(
    "text",
    ["4", "0", "1", "11", "-5", "abc", "5.5", "5.0", "05", "+5", "1e1", " "],
)
def test_any_other_value_is_invalid(monkeypatch: pytest.MonkeyPatch, text):
    monkeypatch.setenv(VARIABLE, text)

    error = error_of_variable(text)

    assert [item["loc"][0] for item in error.errors()] == [FIELD]


def test_a_value_given_in_code_follows_the_same_rule():
    assert DashboardSettings(_env_file=None, dashboard_recent_clinics_limit=3).dashboard_recent_clinics_limit == 3
    for value in (4, True, 5.0):
        with pytest.raises(ValidationError):
            DashboardSettings(_env_file=None, dashboard_recent_clinics_limit=value)


def test_the_start_up_message_names_the_variable_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(VARIABLE, "valor-secreto-9")

    message = configuration_error_message(error_of_variable("valor-secreto-9"))

    assert VARIABLE in message
    assert "valor-secreto-9" not in message


def test_the_message_of_a_single_error_is_the_one_it_always_was(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")
    with pytest.raises(ValidationError) as info:
        IntegrationSettings(_env_file=None)

    assert configuration_error_message(info.value) == (
        "Configuración incompleta o no válida. Falta la variable de entorno USERS_API_BASE_URL."
    )


def test_several_errors_are_reported_together_under_one_heading(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(VARIABLE, "4")
    with pytest.raises(ValidationError) as integration:
        IntegrationSettings(_env_file=None)

    message = configuration_error_message(integration.value, error_of_variable("4"))

    assert "USERS_API_BASE_URL" in message
    assert "CLINICS_API_BASE_URL" in message
    assert VARIABLE in message
    assert message.count("Configuración incompleta o no válida.") == 1

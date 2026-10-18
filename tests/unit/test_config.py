"""Configuración del servicio: validación al arrancar, valores por defecto y advertencias (FR-024)."""

import pytest
from pydantic import ValidationError

from src.config import (
    CorsSettings,
    IntegrationSettings,
    configuration_error_message,
    insecure_url_warnings,
)

ENV_NAMES = (
    "USERS_API_BASE_URL",
    "USERS_API_TIMEOUT_SECONDS",
    "CLINICS_API_BASE_URL",
    "CLINICS_API_TIMEOUT_SECONDS",
    "CORS_ALLOWED_ORIGINS",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def settings(**values: object) -> IntegrationSettings:
    defaults = {
        "users_api_base_url": "http://users-api:8000",
        "clinics_api_base_url": "http://clinics-api:8000",
    }
    return IntegrationSettings(_env_file=None, **{**defaults, **values})


def test_both_api_addresses_are_required():
    with pytest.raises(ValidationError) as error:
        IntegrationSettings(_env_file=None)

    assert {e["loc"][0] for e in error.value.errors()} == {
        "users_api_base_url",
        "clinics_api_base_url",
    }


def test_the_timeouts_default_to_five_seconds():
    loaded = settings()

    assert loaded.users_api_timeout_seconds == 5.0
    assert loaded.clinics_api_timeout_seconds == 5.0


@pytest.mark.parametrize("value", [0, -1, 31, 30.01])
def test_a_timeout_must_be_above_zero_and_at_most_thirty(value):
    with pytest.raises(ValidationError):
        settings(users_api_timeout_seconds=value)
    with pytest.raises(ValidationError):
        settings(clinics_api_timeout_seconds=value)


def test_the_limits_of_the_timeouts_are_valid():
    assert settings(users_api_timeout_seconds=30).users_api_timeout_seconds == 30
    assert settings(clinics_api_timeout_seconds=0.1).clinics_api_timeout_seconds == 0.1


def test_an_empty_variable_counts_as_not_defined(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("USERS_API_BASE_URL", "")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")

    with pytest.raises(ValidationError) as error:
        IntegrationSettings(_env_file=None)

    assert [e["loc"][0] for e in error.value.errors()] == ["users_api_base_url"]


def test_the_variables_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("USERS_API_BASE_URL", "https://users.example.com")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "https://clinics.example.com")
    monkeypatch.setenv("CLINICS_API_TIMEOUT_SECONDS", "2.5")

    loaded = IntegrationSettings(_env_file=None)

    assert loaded.users_api_base_url == "https://users.example.com"
    assert loaded.clinics_api_timeout_seconds == 2.5


def test_the_addresses_are_stored_without_a_trailing_slash():
    assert settings(users_api_base_url="http://x:8000/").users_api_base_url == "http://x:8000"
    assert settings(clinics_api_base_url="https://y/").clinics_api_base_url == "https://y"


@pytest.mark.parametrize("value", ["ftp://secreto", "users-api:8000", "", "//host"])
def test_an_address_must_start_with_http_or_https(value):
    with pytest.raises(ValidationError):
        settings(users_api_base_url=value)


def test_cors_has_no_origins_by_default():
    assert CorsSettings(_env_file=None).origins == []


def test_cors_origins_are_split_trimmed_and_cleaned(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.com, http://b.com,")

    assert CorsSettings(_env_file=None).origins == ["http://a.com", "http://b.com"]


def test_the_configuration_error_names_the_variables_that_are_missing():
    with pytest.raises(ValidationError) as error:
        IntegrationSettings(_env_file=None)

    message = configuration_error_message(error.value)

    assert "USERS_API_BASE_URL" in message
    assert "CLINICS_API_BASE_URL" in message


def test_the_configuration_error_never_contains_the_value_received():
    with pytest.raises(ValidationError) as error:
        settings(users_api_base_url="ftp://secreto")

    message = configuration_error_message(error.value)

    assert "USERS_API_BASE_URL" in message
    assert "secreto" not in message


# --- FR-024: advertencia por direcciones http no locales ---


@pytest.mark.parametrize(
    "url",
    [
        "https://users.empresa.com",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://[::1]:8000",
        "http://users-api-stub:8080",
    ],
)
def test_no_warning_for_https_or_for_local_and_docker_addresses(url):
    assert insecure_url_warnings(settings(users_api_base_url=url, clinics_api_base_url=url)) == []


def test_there_is_one_warning_per_insecure_address_naming_the_variable():
    warnings = insecure_url_warnings(
        settings(
            users_api_base_url="http://users.empresa.com",
            clinics_api_base_url="http://clinicas.internal:8000",
        )
    )

    assert len(warnings) == 2
    assert "USERS_API_BASE_URL" in warnings[0]
    assert "CLINICS_API_BASE_URL" in warnings[1]


def test_a_warning_never_contains_the_address_nor_the_credentials():
    warnings = insecure_url_warnings(
        settings(users_api_base_url="http://usuario:clave@host.com", clinics_api_base_url="https://ok.com")
    )

    assert len(warnings) == 1
    assert "clave" not in warnings[0]
    assert "usuario" not in warnings[0]
    assert "host.com" not in warnings[0]

"""Start-up of the service with the configuration of the subscription periods (spec 010, story 7).

The service refuses to start without the address of the payments API and the cutoff date, names every
wrong variable in one message and never repeats a value. A plain-http address of Pagos warns, because the
token of the person is forwarded to it. No PostgreSQL is needed.
"""

import logging
from pathlib import Path

import pytest

from src.config import (
    BillingSettings,
    CorsSettings,
    IntegrationSettings,
    PaymentsSettings,
    get_billing_settings,
    get_cors_settings,
    get_integration_settings,
    get_payments_settings,
)
from src.main import create_app, lifespan

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
ENV_NAMES = (
    "USERS_API_BASE_URL",
    "USERS_API_TIMEOUT_SECONDS",
    "CLINICS_API_BASE_URL",
    "CLINICS_API_TIMEOUT_SECONDS",
    # Not of this feature (spec 010-cobro-real-suscripciones), but part of the same
    # `IntegrationSettings` as the two above: must be valid too, or `start()` refuses for a reason
    # unrelated to what each test here means to check.
    "PAGOS_API_BASE_URL",
    "PAYMENTS_API_BASE_URL",
    "PAYMENTS_API_TIMEOUT_SECONDS",
    "BILLING_CUTOFF_AT",
    "CORS_ALLOWED_ORIGINS",
)
CACHED = (get_integration_settings, get_payments_settings, get_billing_settings, get_cors_settings)
VALID = {
    "USERS_API_BASE_URL": "http://users-api:8000",
    "CLINICS_API_BASE_URL": "http://clinics-api:8000",
    "PAGOS_API_BASE_URL": "http://pagos-api:8000",
    "PAYMENTS_API_BASE_URL": "http://payments-api:8080",
    "BILLING_CUTOFF_AT": "2026-11-18T00:00:00Z",
}


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch):
    """No variable and no `.env` file: each test sets exactly what it needs."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for settings in (IntegrationSettings, PaymentsSettings, BillingSettings, CorsSettings):
        monkeypatch.setitem(settings.model_config, "env_file", None)
    for cached in CACHED:
        cached.cache_clear()
    yield
    for cached in CACHED:
        cached.cache_clear()


def define(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    """The complete valid configuration; a value of `None` leaves that variable undefined."""
    for name, value in {**VALID, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    for cached in CACHED:
        cached.cache_clear()


async def start() -> None:
    async with lifespan(create_app()):
        pass


async def refusal(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> str:
    define(monkeypatch, **overrides)
    with pytest.raises(RuntimeError) as error:
        await start()
    return str(error.value)


# --- scenario 1: the complete configuration starts ---


async def test_with_the_complete_configuration_the_service_starts(monkeypatch):
    define(monkeypatch)

    await start()


# --- the cutoff date ---


@pytest.mark.parametrize(
    "value",
    [None, "", "2026-11-18T00:00:00", "2026-11-18", "pronto-secreto", "2026-13-45T00:00:00Z", "18/11/2026"],
    ids=["absent", "empty", "no-zone", "date-only", "text", "impossible-date", "other-format"],
)
async def test_without_a_valid_cutoff_the_service_does_not_start_and_names_the_variable(monkeypatch, value):
    message = await refusal(monkeypatch, BILLING_CUTOFF_AT=value)

    assert "BILLING_CUTOFF_AT" in message
    for forbidden in ("pronto-secreto", "2026-13-45", "18/11/2026", "2026-11-18T00:00:00"):
        assert forbidden not in message  # the message names the variable, never its value
    assert "USERS_API_BASE_URL" not in message and "PAYMENTS_API_BASE_URL" not in message


# --- the address and the timeout of Pagos ---


@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
async def test_without_the_address_of_pagos_the_service_does_not_start_and_names_the_variable(monkeypatch, value):
    message = await refusal(monkeypatch, PAYMENTS_API_BASE_URL=value)

    assert "PAYMENTS_API_BASE_URL" in message
    assert "BILLING_CUTOFF_AT" not in message


async def test_an_invalid_address_of_pagos_is_refused_without_repeating_it(monkeypatch):
    message = await refusal(monkeypatch, PAYMENTS_API_BASE_URL="ftp://secreto-de-pagos")

    assert "PAYMENTS_API_BASE_URL" in message
    assert "secreto" not in message


@pytest.mark.parametrize("value", ["0", "-1", "31", "abc", "5s"])
async def test_an_invalid_timeout_of_pagos_is_refused_naming_the_variable_and_not_its_value(monkeypatch, value):
    define(monkeypatch)
    monkeypatch.setenv("PAYMENTS_API_TIMEOUT_SECONDS", value)
    get_payments_settings.cache_clear()

    with pytest.raises(RuntimeError) as error:
        await start()

    assert "PAYMENTS_API_TIMEOUT_SECONDS" in str(error.value)
    assert f"={value}" not in str(error.value)


async def test_the_timeout_of_pagos_is_optional(monkeypatch):
    define(monkeypatch)
    monkeypatch.setenv("PAYMENTS_API_TIMEOUT_SECONDS", "")  # an empty variable counts as undefined
    get_payments_settings.cache_clear()

    await start()

    assert get_payments_settings().payments_api_timeout_seconds == 5.0


# --- scenario 3: several wrong variables, one message ---


async def test_with_several_variables_missing_one_message_names_them_all(monkeypatch):
    message = await refusal(
        monkeypatch, USERS_API_BASE_URL=None, PAYMENTS_API_BASE_URL=None, BILLING_CUTOFF_AT=None
    )

    for name in ("USERS_API_BASE_URL", "PAYMENTS_API_BASE_URL", "BILLING_CUTOFF_AT"):
        assert name in message
    assert "CLINICS_API_BASE_URL" not in message  # the one that is right is not named


async def test_a_refusal_is_logged_once_in_spanish_without_values(monkeypatch, caplog):
    define(monkeypatch, BILLING_CUTOFF_AT="pronto-secreto")

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        await start()

    assert "BILLING_CUTOFF_AT" in caplog.text
    assert "pronto-secreto" not in caplog.text
    assert "Configuración incompleta o no válida" in caplog.text


# --- the plain-http warning for Pagos ---


async def test_a_plain_http_address_of_pagos_outside_a_local_network_warns_without_repeating_it(
    monkeypatch, caplog
):
    define(monkeypatch, PAYMENTS_API_BASE_URL="http://pagos.empresa.com")

    with caplog.at_level(logging.WARNING):
        await start()

    assert "PAYMENTS_API_BASE_URL" in caplog.text
    assert "pagos.empresa.com" not in caplog.text
    assert "USERS_API_BASE_URL" not in caplog.text and "CLINICS_API_BASE_URL" not in caplog.text


@pytest.mark.parametrize(
    "address",
    ["http://payments-api:8080", "http://localhost:8080", "http://127.0.0.1:8080", "https://pagos.empresa.com"],
)
async def test_docker_local_and_https_addresses_of_pagos_do_not_warn(monkeypatch, caplog, address):
    define(monkeypatch, PAYMENTS_API_BASE_URL=address)

    with caplog.at_level(logging.WARNING):
        await start()

    assert "PAYMENTS_API_BASE_URL" not in caplog.text


# --- scenario 7: the configuration is read once ---


def test_a_change_of_the_cutoff_while_the_service_runs_takes_effect_after_a_restart(monkeypatch):
    define(monkeypatch, BILLING_CUTOFF_AT="2026-11-18T00:00:00Z")
    first = get_billing_settings().billing_cutoff_at

    monkeypatch.setenv("BILLING_CUTOFF_AT", "2027-01-01T00:00:00Z")  # the operator edits it
    still = get_billing_settings().billing_cutoff_at

    assert still == first  # the service keeps what it read when it started
    get_billing_settings.cache_clear()  # a restart
    assert get_billing_settings().billing_cutoff_at != first


# --- the documentation of the operator ---


@pytest.mark.parametrize("name", ["PAYMENTS_API_BASE_URL", "PAYMENTS_API_TIMEOUT_SECONDS", "BILLING_CUTOFF_AT"])
def test_the_variables_are_documented_in_the_example_of_the_environment(name):
    assert name in ENV_EXAMPLE.read_text(encoding="utf-8")


def test_the_example_explains_what_the_cutoff_is_for():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    block = text[text.index("# --- Periodos de suscripción") :].split("# --- Salud de servicios", 1)[0]

    for fragment in ("OBLIGATORIA", "ISO 8601", "zona horaria", "despliegue", "trial_days = 0", "reiniciar"):
        assert fragment in block, fragment


def test_the_origin_of_the_front_goes_in_the_existing_variable_and_no_new_one_exists():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "CORS_ALLOWED_ORIGINS" in text
    assert text.count("CORS_") == text.count("CORS_ALLOWED_ORIGINS")  # the only CORS variable
    assert set(CorsSettings.model_fields) == {"cors_allowed_origins"}

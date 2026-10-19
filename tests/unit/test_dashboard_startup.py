"""Start-up of the service with the dashboard (spec 003): its configuration and its notice.

Sections: the configuration at start-up (user story 4) and the notice about dummy data (story 5).
Same isolation as `test_main.py`, plus the settings of the dashboard.
"""

import logging

import pytest

from src.config import (
    CorsSettings,
    DashboardSettings,
    IntegrationSettings,
    get_cors_settings,
    get_dashboard_settings,
    get_integration_settings,
)
from src.main import create_app, lifespan

VARIABLE = "DASHBOARD_RECENT_CLINICS_LIMIT"
ENV_NAMES = (
    "USERS_API_BASE_URL",
    "USERS_API_TIMEOUT_SECONDS",
    "CLINICS_API_BASE_URL",
    "CLINICS_API_TIMEOUT_SECONDS",
    "CORS_ALLOWED_ORIGINS",
    VARIABLE,
)


def clear_caches() -> None:
    for cached in (get_integration_settings, get_cors_settings, get_dashboard_settings):
        cached.cache_clear()


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch):
    """No variable and no `.env` file: each test sets exactly what it needs."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for settings in (IntegrationSettings, CorsSettings, DashboardSettings):
        monkeypatch.setitem(settings.model_config, "env_file", None)
    clear_caches()
    yield
    clear_caches()


def define_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERS_API_BASE_URL", "http://users-api:8000")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")


async def start_and_stop() -> None:
    app = create_app()
    async with lifespan(app):
        assert not app.state.http_client.is_closed
    assert app.state.http_client.is_closed


# --- the configuration at start-up (user story 4) ---


async def test_without_the_variable_the_service_starts(monkeypatch):
    define_apis(monkeypatch)

    await start_and_stop()

    assert get_dashboard_settings().dashboard_recent_clinics_limit == 5


@pytest.mark.parametrize("value", ["", "3", "5", "10"])
async def test_an_empty_or_allowed_value_lets_the_service_start(monkeypatch, value):
    define_apis(monkeypatch)
    monkeypatch.setenv(VARIABLE, value)

    await start_and_stop()

    assert get_dashboard_settings().dashboard_recent_clinics_limit == (int(value) if value else 5)


@pytest.mark.parametrize("value", ["4", "0", "11", "-5", "abc", "5.5", "05"])
async def test_any_other_value_stops_the_service_and_the_message_names_the_variable(
    monkeypatch, caplog, value
):
    define_apis(monkeypatch)
    monkeypatch.setenv(VARIABLE, value)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            async with lifespan(create_app()):
                pass  # pragma: no cover

    text = str(error.value)
    assert text.startswith("Configuración incompleta o no válida.")
    assert VARIABLE in text
    assert f"{VARIABLE} no es válida" in text
    # The log carries the same text, once.
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [text]


async def test_the_message_never_shows_the_value_that_was_configured(monkeypatch, caplog):
    define_apis(monkeypatch)
    monkeypatch.setenv(VARIABLE, "valor-secreto-9")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as error:
            async with lifespan(create_app()):
                pass  # pragma: no cover

    assert "valor-secreto-9" not in str(error.value)
    assert "valor-secreto-9" not in caplog.text


async def test_every_wrong_variable_is_named_in_one_message(monkeypatch):
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")  # the users address is missing
    monkeypatch.setenv(VARIABLE, "4")

    with pytest.raises(RuntimeError) as error:
        async with lifespan(create_app()):
            pass  # pragma: no cover

    text = str(error.value)
    assert "USERS_API_BASE_URL" in text
    assert VARIABLE in text
    assert "CLINICS_API_BASE_URL" not in text
    assert text.count("Configuración incompleta o no válida.") == 1


async def test_the_value_is_read_once_so_a_change_needs_a_restart(monkeypatch):
    define_apis(monkeypatch)
    monkeypatch.setenv(VARIABLE, "3")
    await start_and_stop()

    monkeypatch.setenv(VARIABLE, "10")  # changed while the service is running

    assert get_dashboard_settings().dashboard_recent_clinics_limit == 3
    clear_caches()  # what a restart does
    assert get_dashboard_settings().dashboard_recent_clinics_limit == 10


# --- the notice about dummy data (user story 5) ---


def dummy_notices(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "DUMMY" in r.getMessage()]


async def test_starting_with_dummy_data_logs_one_warning_that_says_so(monkeypatch, caplog):
    define_apis(monkeypatch)

    with caplog.at_level(logging.WARNING):
        await start_and_stop()

    [notice] = dummy_notices(caplog)
    assert "phase 1" in notice
    assert [r.levelno for r in caplog.records if "DUMMY" in r.getMessage()] == [logging.WARNING]


async def test_the_notice_carries_no_address_token_or_secret(monkeypatch, caplog):
    monkeypatch.setenv("USERS_API_BASE_URL", "http://usuario:clave-secreta@users.empresa.com")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")

    with caplog.at_level(logging.WARNING):
        await start_and_stop()

    [notice] = dummy_notices(caplog)
    assert "BASE_URL" not in notice
    for forbidden in ("http", "Bearer", "clave-secreta", "users.empresa.com"):
        assert forbidden not in notice, forbidden


async def test_the_notice_does_not_stop_the_service(monkeypatch):
    define_apis(monkeypatch)

    await start_and_stop()  # the HTTP client is created and closed as usual


async def test_a_real_data_source_starts_without_the_notice(monkeypatch, caplog):
    from tests.dashboard_support import FakeDashboardSource

    define_apis(monkeypatch)
    monkeypatch.setattr("src.main.build_dashboard_source", lambda: FakeDashboardSource(is_dummy=False))

    with caplog.at_level(logging.WARNING):
        await start_and_stop()

    assert dummy_notices(caplog) == []


async def test_a_service_that_does_not_start_gives_no_notice(monkeypatch, caplog):
    define_apis(monkeypatch)
    monkeypatch.setenv(VARIABLE, "4")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            async with lifespan(create_app()):
                pass  # pragma: no cover

    assert dummy_notices(caplog) == []

"""Start-up of the service with the health feature (spec 005, FR-038, SC-010; research R16).

The new variables are validated together with the existing ones: one message names every wrong
variable and never its value, also the four of the schedule of the database (all of them or none).
`DATABASE_URL` is now validated at start-up too (approved decision). Same isolation as
`test_dashboard_startup.py`, extended to the new settings.
"""

import logging

import pytest

from src.config import (
    BuildSettings,
    CorsSettings,
    DashboardSettings,
    DatabaseScheduleSettings,
    HealthSettings,
    IntegrationSettings,
    Settings,
    get_build_settings,
    get_cors_settings,
    get_dashboard_settings,
    get_database_schedule_settings,
    get_health_settings,
    get_integration_settings,
    get_settings,
)
from src.main import create_app, lifespan
from src.services.health_state import HealthState

ENV_NAMES = (
    "USERS_API_BASE_URL",
    "USERS_API_TIMEOUT_SECONDS",
    "CLINICS_API_BASE_URL",
    "CLINICS_API_TIMEOUT_SECONDS",
    "CORS_ALLOWED_ORIGINS",
    "DASHBOARD_RECENT_CLINICS_LIMIT",
    "HEALTH_CHECK_TIMEOUT_SECONDS",
    "HEALTH_CACHE_SECONDS",
    "HEALTH_READY_TIMEOUT_SECONDS",
    "HEALTH_ALLOWED_HOSTS",
    "APP_COMMIT_SHA",
    "APP_BUILD_DATE",
    "APP_ENVIRONMENT",
    "DATABASE_SCHEDULE_TIMEZONE",
    "DATABASE_SCHEDULE_DAYS",
    "DATABASE_SCHEDULE_START",
    "DATABASE_SCHEDULE_END",
)
CACHED = (
    get_settings,
    get_integration_settings,
    get_cors_settings,
    get_dashboard_settings,
    get_health_settings,
    get_database_schedule_settings,
    get_build_settings,
)
# The schedule of the runbook `Deploy-PgAutoShutdown.ps1`.
SCHEDULE = {
    "DATABASE_SCHEDULE_TIMEZONE": "America/Mexico_City",
    "DATABASE_SCHEDULE_DAYS": "Monday,Tuesday,Wednesday,Thursday,Friday",
    "DATABASE_SCHEDULE_START": "08:00",
    "DATABASE_SCHEDULE_END": "20:00",
}

# One wrong value per new variable (the full lists are in test_health_settings.py).
INVALID_VALUES = [
    ("HEALTH_CHECK_TIMEOUT_SECONDS", "0"),
    ("HEALTH_CACHE_SECONDS", "301"),
    ("HEALTH_READY_TIMEOUT_SECONDS", "11"),
    ("HEALTH_ALLOWED_HOSTS", "*.maily.internal"),
    ("APP_COMMIT_SHA", "xyz1234"),
    ("APP_BUILD_DATE", "2026-10-24T16:05:00"),
    ("APP_ENVIRONMENT", "con espacio"),
]


def clear_caches() -> None:
    for cached in CACHED:
        cached.cache_clear()


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch):
    """No variable and no `.env` file except `DATABASE_URL`, which the session already defines."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for settings in (
        Settings,
        IntegrationSettings,
        CorsSettings,
        DashboardSettings,
        HealthSettings,
        DatabaseScheduleSettings,
        BuildSettings,
    ):
        monkeypatch.setitem(settings.model_config, "env_file", None)
    monkeypatch.setenv("USERS_API_BASE_URL", "http://users-api:8000")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")
    clear_caches()
    yield
    clear_caches()


async def start_and_fail() -> str:
    with pytest.raises(RuntimeError) as error:
        async with lifespan(create_app()):
            pass  # pragma: no cover
    return str(error.value)


def test_the_application_is_built_without_any_variable_and_owns_its_health_state(monkeypatch):
    for name in ("USERS_API_BASE_URL", "CLINICS_API_BASE_URL"):
        monkeypatch.delenv(name)

    app = create_app()

    assert isinstance(app.state.health, HealthState)


async def test_with_the_defaults_the_service_starts_and_closes_both_http_clients():
    app = create_app()

    async with lifespan(app):
        assert not app.state.http_client.is_closed
        assert not app.state.health_http_client.is_closed

    assert app.state.http_client.is_closed
    assert app.state.health_http_client.is_closed


@pytest.mark.parametrize(("name", "value"), INVALID_VALUES)
async def test_a_wrong_new_variable_stops_the_service_naming_it_without_its_value(
    monkeypatch, caplog, name, value
):
    monkeypatch.setenv(name, value)

    with caplog.at_level(logging.ERROR):
        text = await start_and_fail()

    assert text.startswith("Configuración incompleta o no válida.")
    assert f"La variable de entorno {name} no es válida." in text
    assert value not in text
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [text]


async def test_every_wrong_variable_is_named_in_one_message(monkeypatch):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", "301")
    monkeypatch.setenv("APP_ENVIRONMENT", "con espacio")

    text = await start_and_fail()

    assert "HEALTH_CACHE_SECONDS" in text
    assert "APP_ENVIRONMENT" in text
    assert text.count("Configuración incompleta o no válida.") == 1


async def test_without_database_url_the_service_does_not_start(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    text = await start_and_fail()

    assert "Falta la variable de entorno DATABASE_URL." in text


async def test_an_empty_new_variable_lets_the_service_start(monkeypatch):
    for name in [*dict(INVALID_VALUES), *SCHEDULE]:
        monkeypatch.setenv(name, "")
    app = create_app()

    async with lifespan(app):
        pass

    assert app.state.health_http_client.is_closed


# --- the schedule of the database ---


async def test_an_incomplete_schedule_stops_the_service_naming_what_is_missing(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_SCHEDULE_TIMEZONE", "America/Mexico_City")

    with caplog.at_level(logging.ERROR):
        text = await start_and_fail()

    for name in ("DATABASE_SCHEDULE_DAYS", "DATABASE_SCHEDULE_START", "DATABASE_SCHEDULE_END"):
        assert f"Falta la variable de entorno {name}." in text
    assert "DATABASE_SCHEDULE_TIMEZONE" not in text
    assert "America/Mexico_City" not in text
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [text]


async def test_an_invalid_schedule_stops_the_service_naming_the_variable(monkeypatch):
    for name, value in {**SCHEDULE, "DATABASE_SCHEDULE_TIMEZONE": "Mars/Olympus"}.items():
        monkeypatch.setenv(name, value)

    text = await start_and_fail()

    assert "La variable de entorno DATABASE_SCHEDULE_TIMEZONE no es válida." in text
    assert "Mars" not in text


async def test_with_the_whole_schedule_the_service_starts(monkeypatch):
    for name, value in SCHEDULE.items():
        monkeypatch.setenv(name, value)
    app = create_app()

    async with lifespan(app):
        assert not app.state.health_http_client.is_closed

    assert app.state.health_http_client.is_closed


async def test_a_wrong_cache_and_an_incomplete_schedule_are_named_in_one_message(monkeypatch):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", "301")
    monkeypatch.setenv("DATABASE_SCHEDULE_DAYS", "Monday")

    text = await start_and_fail()

    assert text.count("Configuración incompleta o no válida.") == 1
    assert "La variable de entorno HEALTH_CACHE_SECONDS no es válida." in text
    for name in ("DATABASE_SCHEDULE_TIMEZONE", "DATABASE_SCHEDULE_START", "DATABASE_SCHEDULE_END"):
        assert f"Falta la variable de entorno {name}." in text
    assert "Monday" not in text

"""Configuration of the health feature (spec 005, FR-038; data-model.md section 7).

`HealthSettings` holds the time limits, the cache, the allowed hosts and the schedule of the database
(its four variables, all of them or none); `BuildSettings` the build identification of `/info`. Every
invalid value stops the service; the messages name the variable and never its value.
"""

from datetime import time
from itertools import combinations
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src import VERSION
from src.config import (
    AllowedHosts,
    BuildInfo,
    BuildSettings,
    DatabaseSchedule,
    HealthConfig,
    HealthSettings,
    InvalidSettingsError,
    build_info_from,
    configuration_error_message,
    database_schedule_from,
    health_config_from,
)

HEALTH_VARIABLES = (
    "HEALTH_CHECK_TIMEOUT_SECONDS",
    "HEALTH_CACHE_SECONDS",
    "HEALTH_READY_TIMEOUT_SECONDS",
    "HEALTH_ALLOWED_HOSTS",
)
BUILD_VARIABLES = ("APP_COMMIT_SHA", "APP_BUILD_DATE", "APP_ENVIRONMENT")
TIMEOUTS = ("HEALTH_CHECK_TIMEOUT_SECONDS", "HEALTH_READY_TIMEOUT_SECONDS")
# The schedule of the runbook `Deploy-PgAutoShutdown.ps1`, written as the operator writes it.
RUNBOOK = {
    "DATABASE_SCHEDULE_TIMEZONE": "America/Mexico_City",
    "DATABASE_SCHEDULE_DAYS": "Monday,Tuesday,Wednesday,Thursday,Friday",
    "DATABASE_SCHEDULE_START": "08:00",
    "DATABASE_SCHEDULE_END": "20:00",
}
SCHEDULE_VARIABLES = tuple(RUNBOOK)


@pytest.fixture(autouse=True)
def no_variables(monkeypatch: pytest.MonkeyPatch):
    for name in HEALTH_VARIABLES + BUILD_VARIABLES + SCHEDULE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def set_schedule(monkeypatch: pytest.MonkeyPatch, **changes: str) -> None:
    """The four variables of the runbook, with `changes` (by variable name) on top."""
    for name, value in {**RUNBOOK, **changes}.items():
        monkeypatch.setenv(name, value)


def only_error_location(error: pytest.ExceptionInfo[ValidationError]) -> tuple:
    [item] = error.value.errors()
    return item["loc"]


# --- HealthSettings ---


def test_without_variables_the_defaults_apply():
    settings = HealthSettings(_env_file=None)

    assert settings.health_check_timeout_seconds == 3
    assert settings.health_cache_seconds == 15
    assert settings.health_ready_timeout_seconds == 2
    assert settings.allowed_hosts.is_empty


@pytest.mark.parametrize("name", HEALTH_VARIABLES)
def test_an_empty_variable_counts_as_not_defined(monkeypatch, name):
    monkeypatch.setenv(name, "")

    settings = HealthSettings(_env_file=None)

    assert (settings.health_check_timeout_seconds, settings.health_cache_seconds) == (3, 15)
    assert settings.health_ready_timeout_seconds == 2
    assert settings.allowed_hosts.is_empty


@pytest.mark.parametrize("name", TIMEOUTS)
@pytest.mark.parametrize(("value", "expected"), [("1", 1), ("10", 10), (" 5 ", 5)])
def test_a_timeout_from_1_to_10_is_valid(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)

    settings = HealthSettings(_env_file=None)

    assert getattr(settings, name.lower()) == expected


@pytest.mark.parametrize(("value", "expected"), [("0", 0), ("300", 300)])
def test_the_cache_goes_from_0_to_300(monkeypatch, value, expected):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", value)

    assert HealthSettings(_env_file=None).health_cache_seconds == expected


@pytest.mark.parametrize("name", TIMEOUTS)
@pytest.mark.parametrize("value", ["0", "11", "3.5", "+3", "03", "-1", "abc", "1e1", " "])
def test_a_timeout_outside_the_rules_is_invalid(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError) as error:
        HealthSettings(_env_file=None)

    assert only_error_location(error) == (name.lower(),)


@pytest.mark.parametrize("value", ["301", "-1", "15.0", "x"])
def test_a_cache_outside_the_rules_is_invalid(monkeypatch, value):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", value)

    with pytest.raises(ValidationError) as error:
        HealthSettings(_env_file=None)

    assert only_error_location(error) == ("health_cache_seconds",)


@pytest.mark.parametrize("value", [True, 5.0])
def test_only_integers_are_accepted_by_code_too(value):
    with pytest.raises(ValidationError):
        HealthSettings(_env_file=None, health_cache_seconds=value)


def test_the_allowed_hosts_are_parsed(monkeypatch):
    monkeypatch.setenv("HEALTH_ALLOWED_HOSTS", "mailysoft-usuarios,.maily.internal")

    hosts = HealthSettings(_env_file=None).allowed_hosts

    assert hosts == AllowedHosts(frozenset({"mailysoft-usuarios"}), (".maily.internal",))


@pytest.mark.parametrize("value", ["*.maily.internal", "a,,b", "http://a", "a:8000", "."])
def test_an_invalid_list_of_hosts_is_invalid(monkeypatch, value):
    monkeypatch.setenv("HEALTH_ALLOWED_HOSTS", value)

    with pytest.raises(ValidationError) as error:
        HealthSettings(_env_file=None)

    assert only_error_location(error) == ("health_allowed_hosts",)


def test_the_health_config_carries_the_values_as_seconds_and_no_schedule(monkeypatch):
    monkeypatch.setenv("HEALTH_ALLOWED_HOSTS", "a")

    config = health_config_from(HealthSettings(_env_file=None))

    assert config == HealthConfig(
        check_timeout_seconds=3.0,
        ready_timeout_seconds=2.0,
        cache_seconds=15.0,
        allowed_hosts=AllowedHosts(frozenset({"a"}), ()),
    )
    assert isinstance(config.check_timeout_seconds, float)
    assert config.schedule is None


# --- the schedule of the database (DATABASE_SCHEDULE_*) ---


def test_the_four_schedule_variables_make_the_schedule(monkeypatch):
    set_schedule(monkeypatch, DATABASE_SCHEDULE_DAYS=" monday , TUESDAY,Wednesday, thursday ,Friday ")

    schedule = database_schedule_from(HealthSettings(_env_file=None))

    assert schedule == DatabaseSchedule(
        zone=ZoneInfo("America/Mexico_City"),
        days=frozenset({0, 1, 2, 3, 4}),
        start=time(8, 0),
        end=time(20, 0),
    )


def test_without_any_schedule_variable_there_is_no_schedule():
    assert database_schedule_from(HealthSettings(_env_file=None)) is None


@pytest.mark.parametrize("name", SCHEDULE_VARIABLES)
def test_an_empty_schedule_variable_counts_as_not_defined(monkeypatch, name):
    monkeypatch.setenv(name, "")

    assert database_schedule_from(HealthSettings(_env_file=None)) is None


@pytest.mark.parametrize(
    "given",
    [subset for size in (1, 2, 3) for subset in combinations(SCHEDULE_VARIABLES, size)],
)
def test_some_schedule_variables_without_the_others_name_the_missing_ones(monkeypatch, given):
    for name in given:
        monkeypatch.setenv(name, RUNBOOK[name])

    with pytest.raises(InvalidSettingsError) as error:
        database_schedule_from(HealthSettings(_env_file=None))

    assert error.value.variables == tuple(name for name in SCHEDULE_VARIABLES if name not in given)
    assert error.value.missing is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_SCHEDULE_TIMEZONE", "Mars/Olympus"),
        ("DATABASE_SCHEDULE_TIMEZONE", "../x"),
        ("DATABASE_SCHEDULE_TIMEZONE", "America"),
        ("DATABASE_SCHEDULE_DAYS", "Lunes"),
        ("DATABASE_SCHEDULE_DAYS", "Monday,Monday"),
        ("DATABASE_SCHEDULE_DAYS", "Monday,,Friday"),
        ("DATABASE_SCHEDULE_DAYS", "Mon,Tue"),
        ("DATABASE_SCHEDULE_START", "8:00"),
        ("DATABASE_SCHEDULE_START", "24:00"),
        ("DATABASE_SCHEDULE_START", "2000"),
        ("DATABASE_SCHEDULE_END", "20:5"),
        ("DATABASE_SCHEDULE_END", "20:60"),
        ("DATABASE_SCHEDULE_END", "20:00:00"),
    ],
)
def test_an_invalid_schedule_variable_is_named_without_its_value(monkeypatch, name, value):
    set_schedule(monkeypatch, **{name: value})

    with pytest.raises(InvalidSettingsError) as error:
        database_schedule_from(HealthSettings(_env_file=None))

    assert error.value.variables == (name,)
    assert error.value.missing is False
    assert value not in str(error.value)


@pytest.mark.parametrize(("start", "end"), [("20:00", "20:00"), ("21:00", "08:00")])
def test_the_start_must_come_before_the_end(monkeypatch, start, end):
    set_schedule(monkeypatch, DATABASE_SCHEDULE_START=start, DATABASE_SCHEDULE_END=end)

    with pytest.raises(InvalidSettingsError) as error:
        database_schedule_from(HealthSettings(_env_file=None))

    assert error.value.variables == ("DATABASE_SCHEDULE_END",)


def test_every_invalid_schedule_variable_is_named_at_once(monkeypatch):
    set_schedule(monkeypatch, DATABASE_SCHEDULE_TIMEZONE="Mars/Olympus", DATABASE_SCHEDULE_START="8:00")

    with pytest.raises(InvalidSettingsError) as error:
        database_schedule_from(HealthSettings(_env_file=None))

    assert error.value.variables == ("DATABASE_SCHEDULE_TIMEZONE", "DATABASE_SCHEDULE_START")


def test_the_health_config_carries_the_schedule(monkeypatch):
    set_schedule(monkeypatch)

    config = health_config_from(HealthSettings(_env_file=None))

    assert config.schedule == database_schedule_from(HealthSettings(_env_file=None))
    assert config.schedule.days == frozenset({0, 1, 2, 3, 4})


# --- BuildSettings ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [("abc1234", "abc1234"), ("ABCDEF1", "abcdef1"), ("a" * 64, "a" * 64)],
)
def test_a_commit_of_7_to_64_hexadecimal_characters_is_valid(monkeypatch, value, expected):
    monkeypatch.setenv("APP_COMMIT_SHA", value)

    assert BuildSettings(_env_file=None).app_commit_sha == expected


@pytest.mark.parametrize("value", ["abc12", "a" * 65, "xyz1234", "abc 1234"])
def test_an_invalid_commit_is_invalid(monkeypatch, value):
    monkeypatch.setenv("APP_COMMIT_SHA", value)

    with pytest.raises(ValidationError) as error:
        BuildSettings(_env_file=None)

    assert only_error_location(error) == ("app_commit_sha",)


@pytest.mark.parametrize(
    "value", ["2026-10-24T16:05:00Z", "2026-10-24T10:05:00-06:00", "2026-10-24T16:05:00+00:00"]
)
def test_a_build_date_with_a_zone_is_published_in_utc(monkeypatch, value):
    monkeypatch.setenv("APP_BUILD_DATE", value)

    assert BuildSettings(_env_file=None).app_build_date == "2026-10-24T16:05:00Z"


@pytest.mark.parametrize("value", ["ayer", "2026-10-24T16:05:00", "1700000000", "2026-13-01T00:00:00Z"])
def test_a_build_date_without_a_zone_or_invalid_is_invalid(monkeypatch, value):
    monkeypatch.setenv("APP_BUILD_DATE", value)

    with pytest.raises(ValidationError) as error:
        BuildSettings(_env_file=None)

    assert only_error_location(error) == ("app_build_date",)


@pytest.mark.parametrize("value", ["staging", "prod-1.mx_a", "e2e"])
def test_an_environment_of_letters_digits_dots_underscores_and_hyphens_is_valid(monkeypatch, value):
    monkeypatch.setenv("APP_ENVIRONMENT", value)

    assert BuildSettings(_env_file=None).app_environment == value


@pytest.mark.parametrize("value", ["con espacio", "a" * 51, "ñ", "staging!"])
def test_an_invalid_environment_is_invalid(monkeypatch, value):
    monkeypatch.setenv("APP_ENVIRONMENT", value)

    with pytest.raises(ValidationError) as error:
        BuildSettings(_env_file=None)

    assert only_error_location(error) == ("app_environment",)


def test_without_build_variables_the_build_is_unknown_with_the_version_of_the_code():
    info = build_info_from(BuildSettings(_env_file=None))

    assert info == BuildInfo("maily-system-api", "2.0.0", "unknown", "unknown", "unknown")
    assert info.version == VERSION


def test_the_build_variables_reach_the_build_info(monkeypatch):
    monkeypatch.setenv("APP_COMMIT_SHA", "3C81089D")
    monkeypatch.setenv("APP_BUILD_DATE", "2026-10-24T10:05:00-06:00")
    monkeypatch.setenv("APP_ENVIRONMENT", "staging")

    info = build_info_from(BuildSettings(_env_file=None))

    assert (info.commit, info.build_date, info.environment) == (
        "3c81089d",
        "2026-10-24T16:05:00Z",
        "staging",
    )


# --- the message for the operator ---


def test_the_message_names_the_variable_and_never_the_value(monkeypatch):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", "valor-secreto-9")

    with pytest.raises(ValidationError) as error:
        HealthSettings(_env_file=None)
    message = configuration_error_message(error.value)

    assert "HEALTH_CACHE_SECONDS" in message
    assert "valor-secreto-9" not in message


def test_one_message_names_the_invalid_settings_and_the_schedule(monkeypatch):
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", "valor-secreto-9")
    with pytest.raises(ValidationError) as error:
        HealthSettings(_env_file=None)

    message = configuration_error_message(
        error.value,
        invalid_variables=("DATABASE_SCHEDULE_DAYS",),
        missing_variables=("DATABASE_SCHEDULE_END",),
    )

    assert message == (
        "Configuración incompleta o no válida. "
        "La variable de entorno HEALTH_CACHE_SECONDS no es válida. "
        "Falta la variable de entorno DATABASE_SCHEDULE_END. "
        "La variable de entorno DATABASE_SCHEDULE_DAYS no es válida."
    )
    assert "valor-secreto-9" not in message


def test_the_message_can_name_only_the_schedule():
    assert configuration_error_message(invalid_variables=("DATABASE_SCHEDULE_TIMEZONE",)) == (
        "Configuración incompleta o no válida. "
        "La variable de entorno DATABASE_SCHEDULE_TIMEZONE no es válida."
    )

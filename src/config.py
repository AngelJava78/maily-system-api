"""Configuration of the service, validated at start-up from environment variables or `.env`.

`Settings` holds the database; `IntegrationSettings` the addresses and time limits of the APIs this
service depends on (FR-002, FR-009); `CorsSettings` the sites allowed to call the API from a browser
(FR-025); `DashboardSettings` the default number of recent clinics of the dashboard (spec 003);
`HealthSettings` and `BuildSettings` the health checks and the build identification (spec 005), and
`DatabaseScheduleSettings` the schedule of the database (part of `HealthSettings`). The messages
about a bad configuration name the variables, never their values.
"""

import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from functools import lru_cache
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src import VERSION

# Hosts that are never reached through an untrusted network: no warning when they use plain http.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# The only values of DASHBOARD_RECENT_CLINICS_LIMIT (the default is 5).
ALLOWED_RECENT_CLINICS_LIMITS = (3, 5, 10)

# The `service` of `/info` (health contract v1) and the value of what is not known.
SERVICE_NAME = "maily-system-api"
_UNKNOWN = "unknown"  # the same value as `src.integrations.health_contract.UNKNOWN`

# One label of a host name: letters, digits and hyphens, not at its ends (research R14).
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_MAX_HOST_NAME = 253
_COMMIT = re.compile(r"[0-9A-Fa-f]{7,64}")
_ENVIRONMENT = re.compile(r"[A-Za-z0-9._-]{1,50}")

# The four variables of the schedule of the database: all of them or none (research R12, R16).
SCHEDULE_VARIABLES = (
    "DATABASE_SCHEDULE_TIMEZONE",
    "DATABASE_SCHEDULE_DAYS",
    "DATABASE_SCHEDULE_START",
    "DATABASE_SCHEDULE_END",
)
# The days as the runbook `Deploy-PgAutoShutdown.ps1` writes them (0 = Monday, like `weekday()`).
_WEEKDAYS = {
    name: number
    for number, name in enumerate(
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    )
}
_CLOCK_TIME = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


class Settings(BaseSettings):
    """Database configuration."""

    database_url: str
    test_database_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class IntegrationSettings(BaseSettings):
    """Addresses and total time limits of the users API and the clinics API."""

    users_api_base_url: str
    users_api_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    clinics_api_base_url: str
    clinics_api_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    # An empty variable (docker-compose passes empty values when `.env` has none) counts as unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @field_validator("users_api_base_url", "clinics_api_base_url")
    @classmethod
    def _normalize_address(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            # The message never includes the value: it could carry credentials.
            raise ValueError("The address must start with http:// or https:// and name a host")
        return value.rstrip("/")


class CorsSettings(BaseSettings):
    """Sites allowed to call the API from a browser. Empty means no web site is allowed."""

    cors_allowed_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


class DashboardSettings(BaseSettings):
    """Default number of recent clinics that the dashboard returns when no `limit` is sent."""

    dashboard_recent_clinics_limit: int = 5

    # An empty variable (docker-compose passes empty values when `.env` has none) counts as unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @field_validator("dashboard_recent_clinics_limit", mode="before")
    @classmethod
    def _only_the_allowed_values(cls, value: object) -> int:
        # The exact text "3", "5" or "10": no decimals, signs, zero padding or booleans. A value
        # that comes from the environment is a string, so it cannot be a `Literal[3, 5, 10]`.
        text = str(value).strip()
        if text not in {str(allowed) for allowed in ALLOWED_RECENT_CLINICS_LIMITS}:
            # The message never includes the value, like the other settings.
            raise ValueError("Only 3, 5 or 10 are allowed")
        return int(text)


# --- Health of the services (spec 005, data-model.md section 7) ---


def _ip_literal(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def valid_host(text: str) -> str | None:
    """The host in lower case if it is an IP literal or an ASCII host name; otherwise `None`.

    A name is made of labels of letters, digits and hyphens (not at their ends), up to 253
    characters and without a final dot. A name whose last label only has digits must be an IP:
    `2130706433` or `0x7f.1` would otherwise reach an address that no list of hosts names.
    """
    if not text or not text.isascii():
        return None
    candidate = text.lower()
    ip = _ip_literal(candidate)
    if ip is not None:
        return ip
    labels = candidate.split(".")
    if len(candidate) > _MAX_HOST_NAME or not all(_HOST_LABEL.fullmatch(label) for label in labels):
        return None
    if labels[-1].isdigit():
        return None
    return candidate


@dataclass(frozen=True, slots=True)
class AllowedHosts:
    """Hosts that the health checks may call (HEALTH_ALLOWED_HOSTS, FR-027).

    An exact host admits only itself; a suffix (with a leading dot) admits the subdomains of that
    domain, but not the domain alone nor the names that only end the same way.
    """

    exact: frozenset[str] = frozenset()
    suffixes: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> AllowedHosts:
        """Read the comma separated list. An empty text is an empty list.

        Raises `ValueError` for an empty entry, a lone dot, a wildcard, a scheme, a path or a port;
        its message never repeats the entry.
        """
        if not text.strip():
            return cls()
        exact: set[str] = set()
        suffixes: list[str] = []
        for raw in text.split(","):
            entry = raw.strip().lower()
            if entry.startswith("."):
                host = valid_host(entry[1:])
                if host is None or _ip_literal(host) is not None:
                    raise ValueError("Invalid allowed host entry")
                if f".{host}" not in suffixes:
                    suffixes.append(f".{host}")
            else:
                host = valid_host(entry)
                if host is None:
                    raise ValueError("Invalid allowed host entry")
                exact.add(host)
        return cls(frozenset(exact), tuple(suffixes))

    @property
    def is_empty(self) -> bool:
        return not self.exact and not self.suffixes

    def allows(self, host: str) -> bool:
        normalized = valid_host(host)
        if normalized is None:
            return False
        return normalized in self.exact or any(normalized.endswith(s) for s in self.suffixes)


@dataclass(frozen=True, slots=True)
class DatabaseSchedule:
    """When the Azure database is on (DATABASE_SCHEDULE_*): days (0 = Monday) and [start, end)."""

    zone: ZoneInfo
    days: frozenset[int]
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class HealthConfig:
    """What the health Services receive: plain values, so the tests can use fractions of a second."""

    check_timeout_seconds: float
    ready_timeout_seconds: float
    cache_seconds: float
    allowed_hosts: AllowedHosts
    schedule: DatabaseSchedule | None = None


def _strict_integer(value: object, low: int, high: int) -> int:
    # Only plain ASCII digits, without signs, decimals or zero padding (a value from the environment
    # is a string, so a declared `int` would accept "3.0" or "+3").
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()) or text != str(int(text)):
        raise ValueError("Only a plain integer is allowed")
    number = int(text)
    if not low <= number <= high:
        raise ValueError("The integer is out of range")
    return number


class InvalidSettingsError(Exception):
    """Variables that are only valid together are missing or invalid (the schedule of the database).

    Pydantic cannot place an error between fields, so this error names the variables itself:
    `variables` are the ones that are missing (`missing` is true: the others were defined) or the
    ones that are not valid. It never carries their values.
    """

    def __init__(self, variables: tuple[str, ...], *, missing: bool = False) -> None:
        super().__init__(f"{'Missing' if missing else 'Invalid'} variables: {', '.join(variables)}")
        self.variables = variables
        self.missing = missing


class DatabaseScheduleSettings(BaseSettings):
    """When the Azure database is on (FR-033): its four variables, all of them or none.

    They are only valid together, so `database_schedule_from` checks them. `HealthSettings` carries
    them too; at start-up they are also read on their own, so a wrong schedule is named even when
    another health variable is wrong.
    """

    database_schedule_timezone: str | None = None
    database_schedule_days: str | None = None
    database_schedule_start: str | None = None
    database_schedule_end: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)


class HealthSettings(DatabaseScheduleSettings):
    """Time limits, cache, allowed hosts and database schedule of the health checks (FR-038)."""

    health_check_timeout_seconds: int = 3
    health_cache_seconds: int = 15
    health_ready_timeout_seconds: int = 2
    health_allowed_hosts: str = ""

    # An empty variable (docker-compose passes empty values when `.env` has none) counts as unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @field_validator("health_check_timeout_seconds", "health_ready_timeout_seconds", mode="before")
    @classmethod
    def _timeout(cls, value: object) -> int:
        return _strict_integer(value, 1, 10)

    @field_validator("health_cache_seconds", mode="before")
    @classmethod
    def _cache(cls, value: object) -> int:
        return _strict_integer(value, 0, 300)

    @field_validator("health_allowed_hosts")
    @classmethod
    def _allowed_hosts(cls, value: str) -> str:
        AllowedHosts.parse(value)  # an invalid entry stops the service at start-up
        return value

    @property
    def allowed_hosts(self) -> AllowedHosts:
        return AllowedHosts.parse(self.health_allowed_hosts)


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class BuildSettings(BaseSettings):
    """Build identification of `/info` (FR-006): injected when building the image or deploying."""

    app_commit_sha: str | None = None
    app_build_date: str | None = None
    app_environment: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @field_validator("app_commit_sha")
    @classmethod
    def _commit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _COMMIT.fullmatch(value.strip()):
            raise ValueError("A commit has 7 to 64 hexadecimal characters")
        return value.strip().lower()

    @field_validator("app_build_date")
    @classmethod
    def _build_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            raise ValueError("A build date is an ISO 8601 date and time with its zone") from None
        if moment.utcoffset() is None:
            raise ValueError("A build date is an ISO 8601 date and time with its zone")
        return _utc_text(moment)

    @field_validator("app_environment")
    @classmethod
    def _environment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ENVIRONMENT.fullmatch(value):
            raise ValueError("An environment has 1 to 50 letters, digits, dots, underscores or hyphens")
        return value


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """What `/info` publishes and what the integrated component `maily-system-api` carries."""

    service: str
    version: str
    commit: str
    build_date: str
    environment: str


def _zone_of(text: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(text.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):  # unknown, not a key, or no zone data
        return None


def _days_of(text: str) -> frozenset[int] | None:
    names = [name.strip().lower() for name in text.split(",")]
    if any(name not in _WEEKDAYS for name in names) or len(set(names)) != len(names):
        return None
    return frozenset(_WEEKDAYS[name] for name in names)


def _clock_time_of(text: str) -> time | None:
    match = _CLOCK_TIME.fullmatch(text.strip())
    return None if match is None else time(int(match[1]), int(match[2]))


def database_schedule_from(settings: DatabaseScheduleSettings) -> DatabaseSchedule | None:
    """The schedule of the database (research R12), or `None` when none of its variables is set.

    An IANA zone, the days in English separated by commas (any case, no repetitions), and the start
    and the end as `HH:MM` of 24 hours, the start before the end. Raises `InvalidSettingsError` with
    the variables that are missing (when only some are defined) or every one that is not valid.
    """
    texts = {name: getattr(settings, name.lower()) for name in SCHEDULE_VARIABLES}
    missing = tuple(name for name, text in texts.items() if text is None)
    if len(missing) == len(texts):
        return None
    if missing:
        raise InvalidSettingsError(missing, missing=True)
    zone = _zone_of(texts["DATABASE_SCHEDULE_TIMEZONE"])
    days = _days_of(texts["DATABASE_SCHEDULE_DAYS"])
    start = _clock_time_of(texts["DATABASE_SCHEDULE_START"])
    end = _clock_time_of(texts["DATABASE_SCHEDULE_END"])
    parsed = dict(zip(SCHEDULE_VARIABLES, (zone, days, start, end), strict=True))
    invalid = [name for name, value in parsed.items() if value is None]
    if start is not None and end is not None and start >= end:
        invalid.append("DATABASE_SCHEDULE_END")  # the end must come after the start
    if invalid:
        raise InvalidSettingsError(tuple(invalid))
    return DatabaseSchedule(zone=zone, days=days, start=start, end=end)


def health_config_from(settings: HealthSettings) -> HealthConfig:
    return HealthConfig(
        check_timeout_seconds=float(settings.health_check_timeout_seconds),
        ready_timeout_seconds=float(settings.health_ready_timeout_seconds),
        cache_seconds=float(settings.health_cache_seconds),
        allowed_hosts=settings.allowed_hosts,
        schedule=database_schedule_from(settings),
    )


def build_info_from(settings: BuildSettings) -> BuildInfo:
    """The build of this process; what is not configured is `unknown` (the version is never)."""
    return BuildInfo(
        service=SERVICE_NAME,
        version=VERSION,
        commit=settings.app_commit_sha or _UNKNOWN,
        build_date=settings.app_build_date or _UNKNOWN,
        environment=settings.app_environment or _UNKNOWN,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_integration_settings() -> IntegrationSettings:
    return IntegrationSettings()


@lru_cache
def get_cors_settings() -> CorsSettings:
    return CorsSettings()


@lru_cache
def get_dashboard_settings() -> DashboardSettings:
    # Read once: changing the variable needs a restart of the service (FR-019).
    return DashboardSettings()


@lru_cache
def get_health_settings() -> HealthSettings:
    # Read once: changing a variable needs a restart of the service (spec 005, FR-038).
    return HealthSettings()


@lru_cache
def get_database_schedule_settings() -> DatabaseScheduleSettings:
    # Only the schedule, read on its own at start-up (it does not depend on the other variables).
    return DatabaseScheduleSettings()


@lru_cache
def get_build_settings() -> BuildSettings:
    return BuildSettings()


def configuration_error_message(
    *errors: ValidationError,
    invalid_variables: Iterable[str] = (),
    missing_variables: Iterable[str] = (),
) -> str:
    """Spanish text for the operator: which variables are missing or invalid, never their values.

    Receives the errors of every configuration class that failed and the names of the variables
    that are checked together (`InvalidSettingsError`), so one message names them all.
    """
    problems = []
    for error in errors:
        for item in error.errors():
            variable = str(item["loc"][0]).upper() if item["loc"] else "?"
            if item["type"] == "missing":
                problems.append(f"Falta la variable de entorno {variable}.")
            else:
                problems.append(f"La variable de entorno {variable} no es válida.")
    problems.extend(f"Falta la variable de entorno {name}." for name in missing_variables)
    problems.extend(f"La variable de entorno {name} no es válida." for name in invalid_variables)
    return "Configuración incompleta o no válida. " + " ".join(problems)


def _is_local_or_internal(host: str) -> bool:
    # A name without dots is a Docker Compose service (or another internal name).
    return host in _LOCAL_HOSTS or "." not in host


def insecure_url_warnings(settings: IntegrationSettings) -> list[str]:
    """One warning per address that uses plain http outside a local or Docker network (FR-024).

    The texts name the variable and never the address, so no credentials can leak into the log.
    """
    warnings = []
    addresses = (
        ("USERS_API_BASE_URL", settings.users_api_base_url),
        ("CLINICS_API_BASE_URL", settings.clinics_api_base_url),
    )
    for variable, address in addresses:
        parts = urlsplit(address)
        if parts.scheme == "http" and not _is_local_or_internal(parts.hostname or ""):
            warnings.append(
                f"{variable} uses plain http outside a local or Docker network: "
                "the access token will travel unencrypted"
            )
    return warnings

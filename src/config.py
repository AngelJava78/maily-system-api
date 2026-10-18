"""Configuration of the service, validated at start-up from environment variables or `.env`.

`Settings` holds the database; `IntegrationSettings` the addresses and time limits of the APIs this
service depends on (FR-002, FR-009); `CorsSettings` the sites allowed to call the API from a browser
(FR-025). The messages about a bad configuration name the variables, never their values.
"""

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hosts that are never reached through an untrusted network: no warning when they use plain http.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


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


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_integration_settings() -> IntegrationSettings:
    return IntegrationSettings()


@lru_cache
def get_cors_settings() -> CorsSettings:
    return CorsSettings()


def configuration_error_message(error: ValidationError) -> str:
    """Spanish text for the operator: which variables are missing or invalid, never their values."""
    problems = []
    for item in error.errors():
        variable = str(item["loc"][0]).upper() if item["loc"] else "?"
        if item["type"] == "missing":
            problems.append(f"Falta la variable de entorno {variable}.")
        else:
            problems.append(f"La variable de entorno {variable} no es válida.")
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

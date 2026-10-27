"""Application factory and life cycle: start-up validation, warnings (FR-024) and CORS (FR-025)."""

import logging

import httpx
import pytest

from src.config import IntegrationSettings, CorsSettings, get_cors_settings, get_integration_settings
from src.main import create_app, lifespan

ENV_NAMES = (
    "USERS_API_BASE_URL",
    "USERS_API_TIMEOUT_SECONDS",
    "CLINICS_API_BASE_URL",
    "CLINICS_API_TIMEOUT_SECONDS",
    "CORS_ALLOWED_ORIGINS",
)


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch):
    """No variable and no `.env` file: each test sets exactly what it needs."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(IntegrationSettings.model_config, "env_file", None)
    monkeypatch.setitem(CorsSettings.model_config, "env_file", None)
    get_integration_settings.cache_clear()
    get_cors_settings.cache_clear()
    yield
    get_integration_settings.cache_clear()
    get_cors_settings.cache_clear()


def define_apis(monkeypatch, users="http://users-api:8000", clinics="http://clinics-api:8000"):
    monkeypatch.setenv("USERS_API_BASE_URL", users)
    monkeypatch.setenv("CLINICS_API_BASE_URL", clinics)


def test_the_application_can_be_built_without_any_variable():
    app = create_app()

    assert app.title == "MailySoft System API"
    assert app.version == "4.0.0"


async def test_the_service_does_not_start_without_the_address_of_the_users_api(
    monkeypatch, caplog
):
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")
    app = create_app()

    with pytest.raises(RuntimeError) as error:
        async with lifespan(app):
            pass  # pragma: no cover

    assert "USERS_API_BASE_URL" in str(error.value)
    assert "CLINICS_API_BASE_URL" not in str(error.value)


async def test_the_start_up_error_never_contains_the_values(monkeypatch):
    define_apis(monkeypatch, users="ftp://secreto-del-usuario")
    app = create_app()

    with pytest.raises(RuntimeError) as error:
        async with lifespan(app):
            pass  # pragma: no cover

    assert "USERS_API_BASE_URL" in str(error.value)
    assert "secreto" not in str(error.value)


async def test_with_both_addresses_the_service_starts_and_closes_its_http_client(monkeypatch):
    define_apis(monkeypatch)
    app = create_app()

    async with lifespan(app):
        client = app.state.http_client
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
        assert client.follow_redirects is False

    assert client.is_closed


async def test_a_plain_http_address_outside_a_local_network_warns_but_starts(monkeypatch, caplog):
    define_apis(monkeypatch, users="http://users.empresa.com", clinics="http://clinics-api:8000")
    app = create_app()

    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            pass

    assert "USERS_API_BASE_URL" in caplog.text
    assert "users.empresa.com" not in caplog.text
    assert "CLINICS_API_BASE_URL" not in caplog.text


async def test_docker_and_https_addresses_do_not_warn(monkeypatch, caplog):
    define_apis(monkeypatch, users="http://users-api-stub:8080", clinics="https://clinics.empresa.com")
    app = create_app()

    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            pass

    # Only the plain-http address warnings are meant to be absent; the start-up notice about the
    # dummy data of the dashboard (spec 003, FR-024) is expected.
    assert "BASE_URL" not in caplog.text


# --- CORS (FR-025) ---

FRONT = "http://front.test"


async def request(monkeypatch, origins: str | None, method: str = "GET", **kwargs) -> httpx.Response:
    if origins is not None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
    get_cors_settings.cache_clear()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as client:
        return await client.request(method, "/openapi.json", **kwargs)


async def test_without_a_list_no_web_site_is_allowed(monkeypatch):
    response = await request(monkeypatch, None, headers={"Origin": FRONT})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_a_listed_site_is_allowed_without_credentials(monkeypatch):
    response = await request(monkeypatch, FRONT, headers={"Origin": FRONT})

    assert response.headers["access-control-allow-origin"] == FRONT
    assert "access-control-allow-credentials" not in response.headers


async def test_a_site_that_is_not_listed_receives_no_authorization(monkeypatch):
    response = await request(monkeypatch, FRONT, headers={"Origin": "http://other.test"})

    assert "access-control-allow-origin" not in response.headers


async def test_the_preflight_of_a_listed_site_allows_authorization_and_content_type(monkeypatch):
    response = await request(
        monkeypatch,
        FRONT,
        method="OPTIONS",
        headers={
            "Origin": FRONT,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONT
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed
    assert "access-control-allow-credentials" not in response.headers


async def test_the_preflight_does_not_authorize_other_headers(monkeypatch):
    response = await request(
        monkeypatch,
        FRONT,
        method="OPTIONS",
        headers={
            "Origin": FRONT,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-otra",
        },
    )

    assert response.status_code == 400

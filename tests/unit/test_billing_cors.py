"""The Front can call the two operations of the subscription periods from the browser (spec 010, story 7).

It is the existing `CORS_ALLOWED_ORIGINS` variable and nothing else: the preflights of the two routes
are answered for the listed site, without credentials, and never for another one. The application starts
through its `lifespan` (it needs the three addresses and the cutoff, nothing else) and no database.
"""

import httpx
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

FRONT = "http://front.test"
ORGANIZATION = "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b"
CONSULT = f"/api/v1/subscription-periods/{ORGANIZATION}"
PAY = f"/api/v1/subscription-periods/{ORGANIZATION}/payments"
CACHED = (get_integration_settings, get_payments_settings, get_billing_settings, get_cors_settings)


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch):
    for name in ("CORS_ALLOWED_ORIGINS",):
        monkeypatch.delenv(name, raising=False)
    for settings in (IntegrationSettings, PaymentsSettings, BillingSettings, CorsSettings):
        monkeypatch.setitem(settings.model_config, "env_file", None)
    monkeypatch.setenv("USERS_API_BASE_URL", "http://users-api:8000")
    monkeypatch.setenv("CLINICS_API_BASE_URL", "http://clinics-api:8000")
    for cached in CACHED:
        cached.cache_clear()
    yield
    for cached in CACHED:
        cached.cache_clear()


async def request(monkeypatch, origins: str | None, method: str, path: str, **kwargs) -> httpx.Response:
    if origins is not None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
    for cached in CACHED:
        cached.cache_clear()
    app = create_app()
    async with lifespan(app):  # the HTTP client that the permission check uses
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api.test") as client:
            return await client.request(method, path, **kwargs)


def preflight_headers(method: str) -> dict[str, str]:
    return {
        "Origin": FRONT,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization",
    }


@pytest.mark.parametrize(("path", "method"), [(CONSULT, "GET"), (PAY, "POST")], ids=["consult", "pay"])
async def test_the_preflight_of_the_listed_site_is_allowed_for_each_operation(monkeypatch, path, method):
    response = await request(monkeypatch, FRONT, "OPTIONS", path, headers=preflight_headers(method))

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONT
    assert method in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(("path", "method"), [(CONSULT, "GET"), (PAY, "POST")], ids=["consult", "pay"])
async def test_a_request_from_the_listed_site_carries_the_cors_header_even_when_it_is_refused(
    monkeypatch, path, method
):
    response = await request(monkeypatch, FRONT, method, path, headers={"Origin": FRONT})

    assert response.status_code == 401  # no token: the access is refused as always
    assert response.headers["access-control-allow-origin"] == FRONT  # and the browser can read why
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(("path", "method"), [(CONSULT, "GET"), (PAY, "POST")], ids=["consult", "pay"])
async def test_a_site_that_is_not_listed_is_not_enabled(monkeypatch, path, method):
    other = {"Origin": "http://other.test"}

    answer = await request(monkeypatch, FRONT, method, path, headers=other)
    asked = await request(
        monkeypatch, FRONT, "OPTIONS", path, headers={**preflight_headers(method), **other}
    )

    assert "access-control-allow-origin" not in answer.headers
    assert "access-control-allow-origin" not in asked.headers
    assert asked.status_code == 400


@pytest.mark.parametrize(("path", "method"), [(CONSULT, "GET"), (PAY, "POST")], ids=["consult", "pay"])
async def test_without_the_variable_no_site_is_enabled(monkeypatch, path, method):
    answer = await request(monkeypatch, None, method, path, headers={"Origin": FRONT})
    asked = await request(monkeypatch, None, "OPTIONS", path, headers=preflight_headers(method))

    assert "access-control-allow-origin" not in answer.headers
    assert "access-control-allow-origin" not in asked.headers


async def test_two_listed_sites_are_both_enabled(monkeypatch):
    other = "http://admin.test"
    origins = f"{FRONT}, {other}"

    for origin in (FRONT, other):
        response = await request(
            monkeypatch, origins, "OPTIONS", CONSULT, headers={**preflight_headers("GET"), "Origin": origin}
        )
        assert response.headers["access-control-allow-origin"] == origin

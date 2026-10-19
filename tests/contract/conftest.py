"""Fixtures of the contract tests that need no database (the dashboard, spec 003).

Kept in its own file: the fixtures that use PostgreSQL stay in `tests/conftest.py`. Nothing here is
`autouse`, because this file applies to every test under `tests/contract/`.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio

from tests.dashboard_support import DashboardApi
from tests.helpers import TEST_TOKEN, USERS_BASE_URL, grant


@pytest_asyncio.fixture
async def dashboard_api(users_stub: httpx.AsyncClient, monkeypatch) -> AsyncIterator[DashboardApi]:
    """The real application over HTTP, talking to the simulated users API and to no database.

    The users API client and `AuthorizationService` are the real ones (their translation of answers
    and failures is part of what is tested); only their transport is the in-memory simulation.
    `TEST_TOKEN` starts with the `dashboard:read` permission. The configuration of the dashboard is
    isolated from the environment and from `.env`, and its cache is cleared before and after.
    """
    from src.config import DashboardSettings, get_dashboard_settings
    from src.dependencies import get_users_api_client
    from src.integrations.users_api import UsersApiClient
    from src.main import create_app

    monkeypatch.delenv("DASHBOARD_RECENT_CLINICS_LIMIT", raising=False)
    monkeypatch.setitem(DashboardSettings.model_config, "env_file", None)
    get_dashboard_settings.cache_clear()

    app = create_app()

    async def users_client() -> UsersApiClient:
        return UsersApiClient(users_stub, USERS_BASE_URL, 5.0)

    app.dependency_overrides[get_users_api_client] = users_client
    await grant(users_stub, TEST_TOKEN, ["dashboard:read"])

    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        ) as client,
        httpx.AsyncClient(transport=transport, base_url="http://api.test") as anonymous,
    ):
        yield DashboardApi(app, client, anonymous, users_stub)

    get_dashboard_settings.cache_clear()

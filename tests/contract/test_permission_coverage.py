"""Every route declares its permission and every operation obeys the users API (SC-002).

Principles V and VIII: a route that has no declared permission and is not one of the public routes
(the documentation and, since spec 005, the public health routes) fails this test; and each real
operation is checked one by one against the simulation of the users API.
"""

from typing import Any
from uuid import UUID

import pytest
from fastapi.routing import APIRoute

from src.main import create_app
from tests.health_support import insert_component
from tests.helpers import TEST_TOKEN, Api

# The permission matrix: contracts/permission-matrix.md of spec 001 (the six subscriptions), the
# row of spec 003 (the dashboard) and the rows of spec 005 (the health of the services).
EXPECTED_PERMISSIONS = {
    "list_subscriptions": "subscriptions:read",
    "get_subscription": "subscriptions:read",
    "create_subscription": "subscriptions:write",
    "update_subscription": "subscriptions:update",
    "change_subscription_status": "subscriptions:update",
    "delete_subscription": "subscriptions:delete",
    "get_dashboard": "dashboard:read",
    "get_health": "health:read",
    "list_monitored_components": "health:read",
    "get_monitored_component": "health:read",
    "create_monitored_component": "health:write",
    "update_monitored_component": "health:update",
    "delete_monitored_component": "health:delete",
}
# The documentation and the public health routes that spec 005 defines (Principle VIII exception).
PUBLIC_ROUTES = {
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/health/live",
    "/health/ready",
    "/info",
    "/health/status",
}
ALL_PERMISSIONS = sorted(set(EXPECTED_PERMISSIONS.values()))

URL = "/api/v1/subscriptions"
COMPONENTS_URL = "/api/v1/monitored-components"
COMPONENT_ID = "00000000-0000-4000-8000-000000000001"
# operation_id -> (method, path, JSON body) against the subscription with id 1 and the component
# COMPONENT_ID
REQUESTS: dict[str, tuple[str, str, dict[str, Any] | None]] = {
    "list_subscriptions": ("GET", URL, None),
    "get_subscription": ("GET", f"{URL}/1", None),
    "create_subscription": (
        "POST",
        URL,
        {
            "name": "Nueva",
            "subscription_type_id": 1,
            "monthly_price": 1,
            "annual_price": 10,
            "consulting_rooms_limit": 1,
            "doctors_limit": 1,
            "assistants_limit": 1,
            "new_patients_per_year_limit": 1,
            "clinics_limit": 1,
        },
    ),
    "update_subscription": ("PATCH", f"{URL}/1", {"name": "Cambio"}),
    "change_subscription_status": ("PATCH", f"{URL}/1/status", {"status_id": 2}),
    "delete_subscription": ("DELETE", f"{URL}/1", None),
    "get_dashboard": ("GET", "/api/v1/dashboard", None),
    "get_health": ("GET", "/api/v1/health", None),
    "list_monitored_components": ("GET", COMPONENTS_URL, None),
    "get_monitored_component": ("GET", f"{COMPONENTS_URL}/{COMPONENT_ID}", None),
    "create_monitored_component": (
        "POST",
        COMPONENTS_URL,
        {"code": "nuevo", "name": "Nuevo", "kind": "service", "base_url": "http://components.test/healthy"},
    ),
    "update_monitored_component": ("PATCH", f"{COMPONENTS_URL}/{COMPONENT_ID}", {"name": "Cambio"}),
    "delete_monitored_component": ("DELETE", f"{COMPONENTS_URL}/{COMPONENT_ID}", None),
}


def declared_permissions() -> dict[str, str]:
    """operation_id -> x-required-permission, as the generated OpenAPI declares it."""
    schema = create_app().openapi()
    return {
        operation["operationId"]: operation["x-required-permission"]
        for path, item in schema["paths"].items()
        if path not in PUBLIC_ROUTES  # the public health routes declare no permission
        for operation in item.values()
    }


# --- the routes of the application ---


def test_every_route_declares_its_permission_or_is_public_documentation():
    app = create_app()
    schema = app.openapi()
    undeclared = []
    checked = 0
    public_seen = set()
    for route in app.routes:
        # FastAPI nests every included router: its routes are the ones with the operations.
        nested = getattr(route, "original_router", None)
        if nested is not None:
            api_routes = nested.routes
        elif isinstance(route, APIRoute):
            api_routes = [route]
        else:
            assert route.path in PUBLIC_ROUTES, f"unexpected public route {route.path}"
            public_seen.add(route.path)
            continue
        for api_route in api_routes:
            assert isinstance(api_route, APIRoute), f"unexpected route {api_route!r}"
            if api_route.path in PUBLIC_ROUTES:  # a public health route of spec 005
                public_seen.add(api_route.path)
                continue
            for method in api_route.methods - {"HEAD", "OPTIONS"}:
                checked += 1
                operation = schema["paths"][api_route.path][method.lower()]
                if "x-required-permission" not in operation:
                    undeclared.append(f"{method} {api_route.path}")

    assert undeclared == []
    assert checked == len(EXPECTED_PERMISSIONS)  # the walk really visited every operation
    assert public_seen == PUBLIC_ROUTES


def test_the_declared_permissions_match_the_matrix_exactly():
    assert declared_permissions() == EXPECTED_PERMISSIONS


def test_the_matrix_and_the_requests_of_this_test_cover_the_same_operations():
    assert set(REQUESTS) == set(EXPECTED_PERMISSIONS)


# --- each real operation against the users API ---


async def snapshot(api: Api) -> list[tuple]:
    subscriptions = await api.fetch_all(
        "SELECT id, name, monthly_price, status_id, updated_at FROM subscriptions ORDER BY id"
    )
    components = await api.fetch_all(
        "SELECT id, code, name, enabled, deleted_at, updated_at FROM monitored_components ORDER BY id"
    )
    return subscriptions + components


@pytest.fixture
async def seeded(api: Api) -> Api:
    await api.insert(name="Base")  # the subscription with id 1
    await insert_component(api.engine, code="base", id=UUID(COMPONENT_ID))
    return api


@pytest.mark.parametrize("operation_id", sorted(REQUESTS))
async def test_without_a_token_the_operation_asks_to_log_in_and_changes_nothing(
    seeded: Api, operation_id: str
):
    method, path, body = REQUESTS[operation_id]
    before = await snapshot(seeded)

    response = await seeded.anonymous.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert await snapshot(seeded) == before
    assert await seeded.users_calls() == []


@pytest.mark.parametrize("operation_id", sorted(REQUESTS))
async def test_with_an_invalid_token_the_operation_is_rejected_and_changes_nothing(
    seeded: Api, operation_id: str
):
    method, path, body = REQUESTS[operation_id]
    before = await snapshot(seeded)

    response = await seeded.client.request(
        method, path, json=body, headers={"Authorization": "Bearer not-a-registered-token"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert await snapshot(seeded) == before


@pytest.mark.parametrize("operation_id", sorted(REQUESTS))
async def test_without_the_permission_the_operation_is_forbidden_and_changes_nothing(
    seeded: Api, operation_id: str
):
    method, path, body = REQUESTS[operation_id]
    permission = EXPECTED_PERMISSIONS[operation_id]
    await seeded.set_permissions([p for p in ALL_PERMISSIONS if p != permission])
    before = await snapshot(seeded)

    response = await seeded.client.request(method, path, json=body)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert permission in response.json()["message"]
    assert await snapshot(seeded) == before


@pytest.mark.parametrize("operation_id", sorted(REQUESTS))
async def test_with_the_users_api_down_the_operation_is_refused_and_changes_nothing(
    seeded: Api, operation_id: str
):
    method, path, body = REQUESTS[operation_id]
    await seeded.users_fault("unavailable")
    before = await snapshot(seeded)

    response = await seeded.client.request(method, path, json=body)

    assert response.status_code == 503
    assert response.json()["code"] == "authorization_unavailable"
    assert await snapshot(seeded) == before


@pytest.mark.parametrize("operation_id", sorted(REQUESTS))
async def test_the_operation_asks_for_exactly_its_permission_and_runs_when_it_is_the_only_one(
    seeded: Api, operation_id: str
):
    method, path, body = REQUESTS[operation_id]
    permission = EXPECTED_PERMISSIONS[operation_id]
    await seeded.set_permissions([permission])  # only the permission of this operation

    response = await seeded.client.request(method, path, json=body)

    assert response.status_code in (200, 201, 204), response.text
    calls = await seeded.users_calls()
    assert [(c["permission"], c["authorization"]) for c in calls] == [
        (permission, f"Bearer {TEST_TOKEN}")
    ]

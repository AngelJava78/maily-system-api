"""Security dependencies: bearer token extraction and the per-operation permission check."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.exceptions import PermissionDeniedError, UnauthenticatedError
from src.security import (
    CLINIC_SUBSCRIPTIONS_CHARGE,
    SUBSCRIPTIONS_DELETE,
    SUBSCRIPTIONS_READ,
    SUBSCRIPTIONS_UPDATE,
    SUBSCRIPTIONS_WRITE,
    get_bearer_token,
    require_caller,
    require_permission,
)
from tests.unit.fakes import fake_caller_access


class FakeAuthorizationService:
    def __init__(self, error: Exception | None = None, access=None) -> None:
        self.error = error
        self.access = access
        self.calls: list[tuple[str, str]] = []
        self.caller_calls: list[tuple[str, str]] = []

    async def require(self, token: str, permission: str) -> None:
        self.calls.append((token, permission))
        if self.error is not None:
            raise self.error

    async def require_as_caller(self, token: str, permission: str):
        self.caller_calls.append((token, permission))
        if self.error is not None:
            raise self.error
        return self.access


def test_the_four_permissions_have_the_names_of_the_matrix():
    assert SUBSCRIPTIONS_READ == "subscriptions:read"
    assert SUBSCRIPTIONS_WRITE == "subscriptions:write"
    assert SUBSCRIPTIONS_UPDATE == "subscriptions:update"
    assert SUBSCRIPTIONS_DELETE == "subscriptions:delete"


async def test_the_bearer_token_is_extracted():
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="abc")

    assert await get_bearer_token(credentials) == "abc"


async def test_a_missing_header_or_another_scheme_is_unauthenticated():
    with pytest.raises(UnauthenticatedError):
        await get_bearer_token(None)  # what HTTPBearer returns without header or with `Basic`


async def test_empty_credentials_are_unauthenticated():
    with pytest.raises(UnauthenticatedError):
        await get_bearer_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=""))


async def test_the_dependency_asks_for_the_exact_permission_once():
    service = FakeAuthorizationService()
    dependency = require_permission(SUBSCRIPTIONS_READ)

    await dependency(token="abc", service=service)

    assert service.calls == [("abc", "subscriptions:read")]


async def test_the_dependency_propagates_the_errors_of_the_service():
    service = FakeAuthorizationService(PermissionDeniedError("subscriptions:write"))
    dependency = require_permission(SUBSCRIPTIONS_WRITE)

    with pytest.raises(PermissionDeniedError):
        await dependency(token="abc", service=service)

    assert service.calls == [("abc", "subscriptions:write")]


async def test_require_caller_asks_for_the_exact_permission_once_and_returns_the_access():
    access = fake_caller_access(tenant_id="t-1", permissions=[CLINIC_SUBSCRIPTIONS_CHARGE])
    service = FakeAuthorizationService(access=access)
    dependency = require_caller(CLINIC_SUBSCRIPTIONS_CHARGE)

    result = await dependency(token="abc", service=service)

    assert result is access
    assert service.caller_calls == [("abc", "clinic_subscriptions:charge")]


async def test_require_caller_propagates_the_errors_of_the_service():
    service = FakeAuthorizationService(PermissionDeniedError("clinic_subscriptions:charge"))
    dependency = require_caller(CLINIC_SUBSCRIPTIONS_CHARGE)

    with pytest.raises(PermissionDeniedError):
        await dependency(token="abc", service=service)

"""AuthorizationService: translates what the users API says into the errors of the application."""

import pytest

from src.exceptions import (
    AuthorizationUnavailableError,
    InvalidTokenError,
    PermissionDeniedError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.services.authorization_service import MAX_TOKEN_BYTES, AuthorizationService
from tests.unit.fakes import FakeUsersApi


async def test_a_person_with_the_permission_passes():
    users_api = FakeUsersApi(allowed=True)

    await AuthorizationService(users_api).require("abc", "subscriptions:read")

    assert users_api.calls == [("abc", "subscriptions:read")]


async def test_a_person_without_the_permission_is_denied_naming_it():
    users_api = FakeUsersApi(allowed=False)

    with pytest.raises(PermissionDeniedError) as error:
        await AuthorizationService(users_api).require("abc", "subscriptions:write")

    assert "subscriptions:write" in error.value.message


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("token_expired", TokenExpiredError),
        ("unauthenticated", UnauthenticatedError),
        ("invalid_token", InvalidTokenError),
        ("anything_else", InvalidTokenError),
    ],
)
async def test_a_rejected_token_becomes_the_matching_error(code, expected):
    with pytest.raises(expected):
        await AuthorizationService(FakeUsersApi(rejected_code=code)).require("abc", "x:y")


async def test_an_unavailable_users_api_is_never_taken_as_permission():
    with pytest.raises(AuthorizationUnavailableError):
        await AuthorizationService(FakeUsersApi(unavailable=True)).require("abc", "x:y")


async def test_a_token_above_the_limit_is_rejected_without_calling_the_users_api():
    users_api = FakeUsersApi()

    with pytest.raises(InvalidTokenError):
        await AuthorizationService(users_api).require("a" * (MAX_TOKEN_BYTES + 1), "x:y")

    assert users_api.calls == []


async def test_a_token_exactly_at_the_limit_is_forwarded():
    users_api = FakeUsersApi()
    token = "a" * MAX_TOKEN_BYTES

    await AuthorizationService(users_api).require(token, "x:y")

    assert users_api.calls == [(token, "x:y")]


async def test_the_limit_is_measured_in_bytes_not_characters():
    users_api = FakeUsersApi()

    with pytest.raises(InvalidTokenError):
        await AuthorizationService(users_api).require("ñ" * (MAX_TOKEN_BYTES // 2 + 1), "x:y")

    assert users_api.calls == []

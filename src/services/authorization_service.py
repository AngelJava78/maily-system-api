from src.exceptions import (
    AuthorizationUnavailableError,
    InvalidTokenError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
    TokenExpiredError,
    UnauthenticatedError,
)
from src.integrations.errors import UsersApiRejectedToken, UsersApiUnavailable
from src.integrations.users_api import CallerAccess, UsersApiClient

# A token above this size is rejected without asking the users API (no oversized headers are
# forwarded). Auth0 tokens are a few kilobytes at most.
MAX_TOKEN_BYTES = 8192


class AuthorizationService:
    """Decides, with the users API as the only authority, whether a request may go on.

    The decision is taken on every request with the permission of the operation; nothing is cached
    and anything that cannot be decided is refused (principle VIII).
    """

    def __init__(self, users_api: UsersApiClient) -> None:
        self._users_api = users_api

    async def require(self, token: str, permission: str) -> None:
        """Return only if the person who owns `token` has `permission`; otherwise raise."""
        if len(token.encode()) > MAX_TOKEN_BYTES:
            raise InvalidTokenError

        try:
            allowed = await self._users_api.check_permission(token, permission)
        except UsersApiRejectedToken as rejection:
            if rejection.code == "token_expired":
                raise TokenExpiredError from None
            if rejection.code == "unauthenticated":
                raise UnauthenticatedError from None
            raise InvalidTokenError from None
        except UsersApiUnavailable:
            raise AuthorizationUnavailableError from None

        if not allowed:
            raise PermissionDeniedError(permission)

    async def require_as_caller(self, token: str, permission: str) -> CallerAccess:
        """Return the caller's access only if they have `permission`; otherwise raise.

        Uses `GET /api/v1/authorization/me` instead of `/check` (research R1): one call per
        request, which also reports `tenant_id` for operations that must compare it against a
        resource's own tenant (e.g. `charge_clinic_subscription`, FR-030). The permission is
        resolved locally against the union of permissions of the caller's Active roles.
        """
        if len(token.encode()) > MAX_TOKEN_BYTES:
            raise InvalidTokenError

        try:
            access = await self._users_api.get_current_access(token)
        except UsersApiRejectedToken as rejection:
            if rejection.code == "token_expired":
                raise TokenExpiredError from None
            if rejection.code == "unauthenticated":
                raise UnauthenticatedError from None
            raise InvalidTokenError from None
        except UsersApiUnavailable:
            raise AuthorizationUnavailableError from None

        if access.password_change_required:
            raise PasswordChangeRequiredError
        if permission not in access.permissions:
            raise PermissionDeniedError(permission)
        return access

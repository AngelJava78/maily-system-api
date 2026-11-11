"""Security dependencies of FastAPI (principle VIII): the Routers apply them to every operation.

The token is never verified here: it is forwarded to the users API, which decides who the person is
and whether they have the permission of the operation.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.dependencies import get_authorization_service
from src.exceptions import UnauthenticatedError
from src.integrations.users_api import CallerAccess
from src.services.authorization_service import AuthorizationService

# Permissions of the operations on the subscriptions (contracts/permission-matrix.md).
SUBSCRIPTIONS_READ = "subscriptions:read"
SUBSCRIPTIONS_WRITE = "subscriptions:write"
SUBSCRIPTIONS_UPDATE = "subscriptions:update"
SUBSCRIPTIONS_DELETE = "subscriptions:delete"

# Permissions of the operations on the clinic subscriptions (spec 006, contracts/permission-matrix.md).
CLINIC_SUBSCRIPTIONS_READ = "clinic_subscriptions:read"
CLINIC_SUBSCRIPTIONS_WRITE = "clinic_subscriptions:write"
CLINIC_SUBSCRIPTIONS_DELETE = "clinic_subscriptions:delete"
# Unlike the other three (a System-type role, checked with /check), this one is checked with /me
# (require_caller) because it must also carry the caller's own tenant_id (research R1, FR-030).
CLINIC_SUBSCRIPTIONS_CHARGE = "clinic_subscriptions:charge"

# Permission of the dashboard operation (specs/003-platform-dashboard/contracts/permission-matrix.md).
DASHBOARD_READ = "dashboard:read"

# Permissions of the health operations (specs/005-health-monitoring/contracts/permission-matrix.md).
HEALTH_READ = "health:read"
HEALTH_WRITE = "health:write"
HEALTH_UPDATE = "health:update"
HEALTH_DELETE = "health:delete"

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    auto_error=False,  # the error is ours (uniform body, Spanish message, challenge header)
    description=(
        "Token de acceso emitido por Auth0. Este servicio no lo verifica: lo reenvía al API de "
        "usuarios."
    ),
)


async def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """The token of the `Authorization: Bearer ...` header.

    `HTTPBearer` returns `None` when the header is missing or does not use the Bearer scheme.
    """
    if credentials is None or not credentials.credentials.strip():
        raise UnauthenticatedError
    return credentials.credentials


def require_permission(permission: str) -> Callable[..., Awaitable[None]]:
    """Dependency that lets the request through only if the person has `permission`.

    It runs before the data of the request is validated or the subscription is looked up.
    """

    async def dependency(
        token: Annotated[str, Depends(get_bearer_token)],
        service: Annotated[AuthorizationService, Depends(get_authorization_service)],
    ) -> None:
        await service.require(token, permission)

    return dependency


def require_caller(permission: str) -> Callable[..., Awaitable[CallerAccess]]:
    """Dependency that lets the request through only if the person has `permission`, returning
    their `CallerAccess` (with `tenant_id`) to the Router (research R1).

    Unlike `require_permission`, this checks against `GET /api/v1/authorization/me` (one call),
    for the one operation that needs the caller's own organization: `charge_clinic_subscription`.
    """

    async def dependency(
        token: Annotated[str, Depends(get_bearer_token)],
        service: Annotated[AuthorizationService, Depends(get_authorization_service)],
    ) -> CallerAccess:
        return await service.require_as_caller(token, permission)

    return dependency

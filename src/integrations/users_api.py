"""Client of the users API: asks whether the person who owns a token has a permission.

Contract: `specs/001-subscriptions-api/contracts/users-api-integration.md`. This service never
verifies tokens itself: it forwards the token untouched and obeys the answer. Anything that is not
exactly the expected answer is "unavailable" (fail closed), never a decision.
"""

import asyncio
import logging

import httpx

from src.integrations.errors import UsersApiRejectedToken, UsersApiUnavailable

logger = logging.getLogger(__name__)

CHECK_PATH = "/api/v1/authorization/check"
_REJECTION_CODES = {"unauthenticated", "token_expired", "invalid_token"}


class UsersApiClient:
    def __init__(
        self, http_client: httpx.AsyncClient, base_url: str, timeout_seconds: float
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def check_permission(self, token: str, permission: str) -> bool:
        """Whether the person who owns `token` has `permission` (one call, no cache, no retries).

        Raises `UsersApiRejectedToken` when the users API refuses the token and
        `UsersApiUnavailable` for anything else that is not a valid answer.
        """
        try:
            # The time limit covers the whole call; `httpx` only limits each phase separately.
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    f"{self._base_url}{CHECK_PATH}",
                    params={"permission": permission},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.HTTPError, TimeoutError) as error:
            # Only the kind of failure is logged: never the token, the address or the body.
            logger.warning("Users API request failed (%s)", type(error).__name__)
            raise UsersApiUnavailable from None

        status = response.status_code
        if status == 401:
            raise UsersApiRejectedToken(self._rejection_code(response))
        if status != 200:
            if 400 <= status < 500:
                logger.error("Users API answered an unexpected status %s", status)
            else:
                logger.warning("Users API answered status %s", status)
            raise UsersApiUnavailable

        try:
            data = response.json()
        except ValueError:
            raise UsersApiUnavailable from None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("allowed"), bool)
            or data.get("permission") != permission
        ):
            raise UsersApiUnavailable
        return data["allowed"]

    @staticmethod
    def _rejection_code(response: httpx.Response) -> str:
        """The code of a 401; an unreadable body or an unknown code is an invalid token."""
        try:
            code = response.json().get("code")
        except (ValueError, AttributeError):
            return "invalid_token"
        return code if code in _REJECTION_CODES else "invalid_token"

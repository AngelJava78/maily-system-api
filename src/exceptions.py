"""Errors of the application: each one maps to an HTTP status and to the uniform error body.

They carry the stable English code and the already formatted Spanish message; the handlers in
`src/error_handlers.py` turn them into `ErrorResponse`.
"""

from typing import ClassVar

from src.messages import (
    AUTHORIZATION_UNAVAILABLE_MESSAGE,
    CLINICS_CHECK_UNAVAILABLE_MESSAGE,
    INVALID_TOKEN_MESSAGE,
    PERMISSION_DENIED_MESSAGE,
    SUBSCRIPTION_HAS_CLINICS_MESSAGE,
    SUBSCRIPTION_NAME_ALREADY_EXISTS_MESSAGE,
    SUBSCRIPTION_NOT_FOUND_MESSAGE,
    SUBSCRIPTION_STATUS_UNCHANGED_MESSAGE,
    TOKEN_EXPIRED_MESSAGE,
    UNAUTHENTICATED_MESSAGE,
    ErrorCode,
)

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}
_BEARER_INVALID_TOKEN = {"WWW-Authenticate": 'Bearer error="invalid_token"'}


class AppError(Exception):
    """Base of the errors that become an HTTP response with the uniform error body."""

    code: ClassVar[ErrorCode]
    status_code: ClassVar[int]

    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers  # extra response headers (e.g. `WWW-Authenticate` in a 401)


# --- Access control (the decision comes from the users API) ---


class UnauthenticatedError(AppError):
    """No access token was sent, or the `Authorization` header does not use the Bearer scheme."""

    code = ErrorCode.UNAUTHENTICATED
    status_code = 401

    def __init__(self) -> None:
        super().__init__(UNAUTHENTICATED_MESSAGE, headers=dict(_BEARER_CHALLENGE))


class TokenExpiredError(AppError):
    """The users API answered that the token has expired."""

    code = ErrorCode.TOKEN_EXPIRED
    status_code = 401

    def __init__(self) -> None:
        super().__init__(TOKEN_EXPIRED_MESSAGE, headers=dict(_BEARER_INVALID_TOKEN))


class InvalidTokenError(AppError):
    """The token is not valid; the reason is never revealed."""

    code = ErrorCode.INVALID_TOKEN
    status_code = 401

    def __init__(self) -> None:
        super().__init__(INVALID_TOKEN_MESSAGE, headers=dict(_BEARER_INVALID_TOKEN))


class PermissionDeniedError(AppError):
    """The person is authenticated but lacks the permission that the operation requires."""

    code = ErrorCode.PERMISSION_DENIED
    status_code = 403

    def __init__(self, permission: str) -> None:
        super().__init__(PERMISSION_DENIED_MESSAGE.format(permission=permission))


class AuthorizationUnavailableError(AppError):
    """The permission could not be checked right now: the request is refused (fail closed)."""

    code = ErrorCode.AUTHORIZATION_UNAVAILABLE
    status_code = 503

    def __init__(self) -> None:
        super().__init__(AUTHORIZATION_UNAVAILABLE_MESSAGE)


# --- Subscriptions ---


class SubscriptionNotFoundError(AppError):
    """The subscription does not exist or is deleted."""

    code = ErrorCode.SUBSCRIPTION_NOT_FOUND
    status_code = 404

    def __init__(self, subscription_id: int) -> None:
        super().__init__(SUBSCRIPTION_NOT_FOUND_MESSAGE.format(subscription_id=subscription_id))


class SubscriptionNameAlreadyExistsError(AppError):
    """Another subscription that is not deleted already uses the name (ignoring case)."""

    code = ErrorCode.SUBSCRIPTION_NAME_ALREADY_EXISTS
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(SUBSCRIPTION_NAME_ALREADY_EXISTS_MESSAGE.format(name=name))


class SubscriptionStatusUnchangedError(AppError):
    """The requested status is the one the subscription already has."""

    code = ErrorCode.SUBSCRIPTION_STATUS_UNCHANGED
    status_code = 409

    def __init__(self, subscription_id: int, status_name: str) -> None:
        super().__init__(
            SUBSCRIPTION_STATUS_UNCHANGED_MESSAGE.format(
                subscription_id=subscription_id, status=status_name
            )
        )


class SubscriptionHasClinicsError(AppError):
    """The subscription has clinics assigned, so it cannot be deleted."""

    code = ErrorCode.SUBSCRIPTION_HAS_CLINICS
    status_code = 409

    def __init__(self, subscription_id: int) -> None:
        super().__init__(SUBSCRIPTION_HAS_CLINICS_MESSAGE.format(subscription_id=subscription_id))


class ClinicsCheckUnavailableError(AppError):
    """It could not be checked whether the subscription has clinics: nothing was deleted."""

    code = ErrorCode.CLINICS_CHECK_UNAVAILABLE
    status_code = 503

    def __init__(self, subscription_id: int) -> None:
        super().__init__(CLINICS_CHECK_UNAVAILABLE_MESSAGE.format(subscription_id=subscription_id))

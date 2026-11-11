"""Errors of the application: each one maps to an HTTP status and to the uniform error body.

They carry the stable English code and the already formatted Spanish message; the handlers in
`src/error_handlers.py` turn them into `ErrorResponse`.
"""

from typing import Any, ClassVar
from uuid import UUID

from src.messages import (
    AUTHORIZATION_UNAVAILABLE_MESSAGE,
    CLINIC_SUBSCRIPTION_ALREADY_ACTIVE_MESSAGE,
    CLINIC_SUBSCRIPTION_ALREADY_CANCELLED_MESSAGE,
    CLINIC_SUBSCRIPTION_CHARGE_CONFLICT_MESSAGE,
    CLINIC_SUBSCRIPTION_CHARGE_NOT_FOUND_MESSAGE,
    CLINIC_SUBSCRIPTION_CHARGE_PENDING_MESSAGE,
    CLINIC_SUBSCRIPTION_CHARGE_REQUIRES_ACTIVE_PLAN_MESSAGE,
    CLINIC_SUBSCRIPTION_NOT_CHARGEABLE_MESSAGE,
    CLINIC_SUBSCRIPTION_NOT_FOUND_MESSAGE,
    CLINIC_SUBSCRIPTION_PLAN_NOT_ACTIVE_MESSAGE,
    CLINICS_CHECK_UNAVAILABLE_MESSAGE,
    INVALID_TOKEN_MESSAGE,
    MODULE_CHECK_UNAVAILABLE_MESSAGE,
    MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE,
    MONITORED_COMPONENT_NOT_FOUND_MESSAGE,
    PASSWORD_CHANGE_REQUIRED_MESSAGE,
    PAYMENT_NOT_AUTHORIZED_MESSAGE,
    PAYMENTS_UNAVAILABLE_MESSAGE,
    PERMISSION_DENIED_MESSAGE,
    SUBSCRIPTION_HAS_CLINICS_MESSAGE,
    SUBSCRIPTION_MODULE_NOT_FOUND_MESSAGE,
    SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE,
    SUBSCRIPTION_NAME_ALREADY_EXISTS_MESSAGE,
    SUBSCRIPTION_NOT_FOUND_MESSAGE,
    SUBSCRIPTION_STATUS_UNCHANGED_MESSAGE,
    TOKEN_EXPIRED_MESSAGE,
    UNAUTHENTICATED_MESSAGE,
    VALIDATION_ERROR_MESSAGE,
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


class PasswordChangeRequiredError(AppError):
    """The users API answered that the caller must change a temporary password first (`/me`)."""

    code = ErrorCode.PASSWORD_CHANGE_REQUIRED
    status_code = 403

    def __init__(self) -> None:
        super().__init__(PASSWORD_CHANGE_REQUIRED_MESSAGE)


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


class SubscriptionModuleNotFoundError(AppError):
    """A requested module key is not an active clinic-type module in the users API."""

    code = ErrorCode.SUBSCRIPTION_MODULE_NOT_FOUND
    status_code = 422

    def __init__(self, module_key: str) -> None:
        super().__init__(SUBSCRIPTION_MODULE_NOT_FOUND_MESSAGE.format(module_key=module_key))


class SubscriptionModulePrerequisiteMissingError(AppError):
    """A requested module is included without the other module it depends on."""

    code = ErrorCode.SUBSCRIPTION_MODULE_PREREQUISITE_MISSING
    status_code = 409

    def __init__(self, module_key: str, prerequisite_key: str) -> None:
        super().__init__(
            SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE.format(
                module_key=module_key, prerequisite_key=prerequisite_key
            )
        )


class ModuleCheckUnavailableError(AppError):
    """The users API did not answer as expected while validating modules: nothing was saved."""

    code = ErrorCode.MODULE_CHECK_UNAVAILABLE
    status_code = 503

    def __init__(self) -> None:
        super().__init__(MODULE_CHECK_UNAVAILABLE_MESSAGE)


# --- Registry of monitored components (spec 005) ---


class MonitoredComponentNotFoundError(AppError):
    """The component does not exist or is deleted."""

    code = ErrorCode.MONITORED_COMPONENT_NOT_FOUND
    status_code = 404

    def __init__(self, component_id: UUID) -> None:
        super().__init__(MONITORED_COMPONENT_NOT_FOUND_MESSAGE.format(component_id=component_id))


class MonitoredComponentCodeAlreadyExistsError(AppError):
    """Another current component uses the code, or it is the code of an integrated component."""

    code = ErrorCode.MONITORED_COMPONENT_CODE_ALREADY_EXISTS
    status_code = 409

    def __init__(self, component_code: str) -> None:
        super().__init__(MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE.format(code=component_code))


class MonitoredComponentDataError(AppError):
    """Data that the Service rejects: a host outside the allowed list or a rule of `kind`.

    `errors` keeps the format of the errors of Pydantic (`type`, `loc`, `msg`, `input` and `ctx` with
    the `ValueError` of the message), so the answer is the same 422 as the validation of the request.
    """

    code = ErrorCode.VALIDATION_ERROR
    status_code = 422

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__(VALIDATION_ERROR_MESSAGE)
        self.errors = errors

    @staticmethod
    def field_error(field: str, message: str) -> dict[str, Any]:
        """One error on a field of the body, with its message in Spanish (never the value)."""
        return {
            "type": "value_error",
            "loc": ("body", field),
            "msg": message,
            "input": None,
            "ctx": {"error": ValueError(message)},
        }


# --- Clinic subscriptions (spec 006) ---


class ClinicSubscriptionNotFoundError(AppError):
    """The clinic subscription does not exist, is cancelled, or (only for `charge`) belongs to
    another organization than the caller's (FR-030: never revealed which of the three it was)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_NOT_FOUND
    status_code = 404

    def __init__(self, clinic_subscription_id: int) -> None:
        super().__init__(
            CLINIC_SUBSCRIPTION_NOT_FOUND_MESSAGE.format(
                clinic_subscription_id=clinic_subscription_id
            )
        )


class ClinicSubscriptionChargeNotFoundError(AppError):
    """The charge does not exist in that clinic subscription's history."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_CHARGE_NOT_FOUND
    status_code = 404

    def __init__(self, charge_id: int) -> None:
        super().__init__(CLINIC_SUBSCRIPTION_CHARGE_NOT_FOUND_MESSAGE.format(charge_id=charge_id))


class ClinicSubscriptionPlanNotActiveError(AppError):
    """The plan to assign does not exist or is not Active (FR-003)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_PLAN_NOT_ACTIVE
    status_code = 409

    def __init__(self, subscription_id: int) -> None:
        super().__init__(
            CLINIC_SUBSCRIPTION_PLAN_NOT_ACTIVE_MESSAGE.format(subscription_id=subscription_id)
        )


class ClinicSubscriptionAlreadyActiveError(AppError):
    """The clinic already has an Active or pending-resolution subscription (FR-004)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_ALREADY_ACTIVE
    status_code = 409

    def __init__(self) -> None:
        super().__init__(CLINIC_SUBSCRIPTION_ALREADY_ACTIVE_MESSAGE)


class ClinicSubscriptionChargePendingError(AppError):
    """The current charge is still pending (blocks a new charge or cancelling, research R7)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_CHARGE_PENDING
    status_code = 409

    def __init__(self, clinic_subscription_id: int) -> None:
        super().__init__(
            CLINIC_SUBSCRIPTION_CHARGE_PENDING_MESSAGE.format(
                clinic_subscription_id=clinic_subscription_id
            )
        )


class ClinicSubscriptionNotChargeableError(AppError):
    """The subscription is Cancelled (research R7): a new charge is refused without calling Pagos.

    A `pending` or `rejected` existing charge of the same period does NOT raise this: retrying
    reaches Pagos again with the same deterministic Idempotency-Key (historia 2, escenario 2),
    which is itself idempotent — there is nothing to block locally.
    """

    code = ErrorCode.CLINIC_SUBSCRIPTION_CHARGE_PENDING
    status_code = 409

    def __init__(self, clinic_subscription_id: int) -> None:
        super().__init__(
            CLINIC_SUBSCRIPTION_NOT_CHARGEABLE_MESSAGE.format(
                clinic_subscription_id=clinic_subscription_id
            )
        )


class ClinicSubscriptionAlreadyCancelledError(AppError):
    """The clinic subscription is already Cancelled (historia 5, escenario 3)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_ALREADY_CANCELLED
    status_code = 409

    def __init__(self, clinic_subscription_id: int) -> None:
        super().__init__(
            CLINIC_SUBSCRIPTION_ALREADY_CANCELLED_MESSAGE.format(
                clinic_subscription_id=clinic_subscription_id
            )
        )


class ClinicSubscriptionChargeRequiresActivePlanError(AppError):
    """The assigned plan is no longer Active: a charge cannot be computed (Edge Cases)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_CHARGE_REQUIRES_ACTIVE_PLAN
    status_code = 409

    def __init__(self) -> None:
        super().__init__(CLINIC_SUBSCRIPTION_CHARGE_REQUIRES_ACTIVE_PLAN_MESSAGE)


class PaymentNotAuthorizedError(AppError):
    """Pagos answered 403 to the charge (missing `payments:write`, no organization there, or a
    temporary password change pending at Pagos)."""

    code = ErrorCode.PAYMENT_NOT_AUTHORIZED
    status_code = 403

    def __init__(self) -> None:
        super().__init__(PAYMENT_NOT_AUTHORIZED_MESSAGE)


class ClinicSubscriptionChargeConflictError(AppError):
    """Pagos answered an idempotency key conflict: data changed between two attempts of the
    same period (Edge Cases)."""

    code = ErrorCode.CLINIC_SUBSCRIPTION_CHARGE_CONFLICT
    status_code = 409

    def __init__(self) -> None:
        super().__init__(CLINIC_SUBSCRIPTION_CHARGE_CONFLICT_MESSAGE)


class PaymentsUnavailableError(AppError):
    """mailySoft-pagos did not answer as expected: nothing was charged (FR-014, fail closed)."""

    code = ErrorCode.PAYMENTS_UNAVAILABLE
    status_code = 503

    def __init__(self) -> None:
        super().__init__(PAYMENTS_UNAVAILABLE_MESSAGE)

"""Errors of the integrations with other APIs.

They are not HTTP errors: the Services translate them into the errors of the application. Their
messages are generic and never include tokens, addresses or bodies of the other service.
"""


class IntegrationError(Exception):
    """Base of the failures of a call to another API."""


class UsersApiRejectedToken(IntegrationError):
    """The users API refused the token (401); `code` is the one it answered."""

    def __init__(self, code: str) -> None:
        super().__init__("The users API rejected the access token")
        self.code = code


class UsersApiUnavailable(IntegrationError):
    """The users API did not answer as expected: it cannot be known whether the person is allowed."""

    def __init__(self) -> None:
        super().__init__("The users API did not answer as expected")


class ClinicsApiUnavailable(IntegrationError):
    """The clinics API did not answer as expected: the clinics count is not available."""

    def __init__(self) -> None:
        super().__init__("The clinics API did not answer as expected")


class ClinicsApiNotFound(IntegrationError):
    """Clinics answered that a clinic subscription does not exist, is cancelled, or belongs to
    another organization than the caller's (indistinguishable from here, FR-003)."""

    def __init__(self) -> None:
        super().__init__("The clinics API reported the clinic subscription as not found")


class DashboardSourceUnavailable(IntegrationError):
    """A dashboard data source did not answer as expected: that indicator is not available."""

    def __init__(self) -> None:
        super().__init__("The dashboard data source did not answer as expected")


class PaymentsApiRejectedToken(IntegrationError):
    """mailySoft-pagos refused the token (401), forwarding Usuarios' own rejection; `code` is the
    one it answered."""

    def __init__(self, code: str) -> None:
        super().__init__("The payments API rejected the access token")
        self.code = code


class PaymentsApiPermissionDenied(IntegrationError):
    """mailySoft-pagos answered 403: missing `payments:write`/`payments:read`, no organization, or
    a temporary password change pending (Pagos' own Principle VIII)."""

    def __init__(self) -> None:
        super().__init__("The payments API denied the operation")


class PaymentsApiIdempotencyConflict(IntegrationError):
    """The same `Idempotency-Key` was already used with different data (Pagos' 409)."""

    def __init__(self) -> None:
        super().__init__("The payments API reported an idempotency key conflict")


class PaymentsApiUnavailable(IntegrationError):
    """mailySoft-pagos did not answer as expected: fail closed, nothing was charged or read."""

    def __init__(self) -> None:
        super().__init__("The payments API did not answer as expected")

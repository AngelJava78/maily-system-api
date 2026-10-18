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

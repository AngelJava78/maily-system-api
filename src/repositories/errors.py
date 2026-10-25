"""Persistence errors that the Repositories raise, so no SQLAlchemy type goes above them."""

from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


class UniqueViolationError(Exception):
    """A unique constraint or unique index rejected the write (SQLSTATE 23505)."""

    def __init__(self, constraint_name: str | None = None) -> None:
        super().__init__(constraint_name)
        self.constraint_name = constraint_name


def as_unique_violation(error: IntegrityError) -> UniqueViolationError | None:
    """Translate an `IntegrityError` when it is a unique violation; otherwise return `None`.

    The SQLSTATE and the constraint name come from the asyncpg exception that SQLAlchemy wraps
    (`error.orig.__cause__`).
    """
    cause = getattr(error.orig, "__cause__", None)
    if getattr(cause, "sqlstate", None) == UNIQUE_VIOLATION:
        return UniqueViolationError(getattr(cause, "constraint_name", None))
    return None


class ForeignKeyViolationError(Exception):
    """A foreign key rejected the write because the row it points to does not exist (23503)."""

    def __init__(self, constraint_name: str | None = None) -> None:
        super().__init__(constraint_name)
        self.constraint_name = constraint_name


def as_foreign_key_violation(error: IntegrityError) -> ForeignKeyViolationError | None:
    """Translate an `IntegrityError` when it is a foreign key violation; otherwise `None`."""
    cause = getattr(error.orig, "__cause__", None)
    if getattr(cause, "sqlstate", None) == FOREIGN_KEY_VIOLATION:
        return ForeignKeyViolationError(getattr(cause, "constraint_name", None))
    return None


class DatabaseUnavailableError(Exception):
    """The database did not answer the health check (spec 005, FR-005, FR-016).

    `kind` is `connection_error` (no connection could be obtained, or it broke) or
    `unexpected_error` (anything else). The message is generic: never an address or a detail.
    """

    def __init__(self, kind: str) -> None:
        super().__init__("The database did not answer as expected")
        self.kind = kind

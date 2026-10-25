from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.errors import DatabaseUnavailableError


class DatabaseHealthRepository:
    """The trivial query of the health check of the database (spec 005, research R5).

    It runs in two phases so the kind of failure can be told: getting the connection (any failure is
    `connection_error`) and running `SELECT 1` (a disconnection is `connection_error`, anything else
    `unexpected_error`). The time limit is the caller's (`asyncio.timeout`); a cancellation is a
    `BaseException` and is never caught here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        try:
            await self._session.connection()
        except Exception:
            raise DatabaseUnavailableError("connection_error") from None
        try:
            await self._session.execute(text("SELECT 1"))
        except DBAPIError as error:
            kind = "connection_error" if error.connection_invalidated else "unexpected_error"
            raise DatabaseUnavailableError(kind) from None
        except Exception:
            raise DatabaseUnavailableError("unexpected_error") from None

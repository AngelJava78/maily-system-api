"""Commit and rollback rules shared by the Repositories: every write is its own transaction."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from src.repositories.errors import as_foreign_key_violation, as_unique_violation


async def execute_and_commit(session: AsyncSession, statement: Executable) -> int | None:
    """Run a write statement that returns one id (`RETURNING id`) and commit it.

    Returns the id, or `None` when no row matched: nothing is committed and the transaction is
    rolled back. Any failure rolls the transaction back first, so the session stays usable: a
    unique violation is raised as `UniqueViolationError`, a foreign key violation as
    `ForeignKeyViolationError` and every other error as it is.
    """
    try:
        row_id = (await session.execute(statement)).scalar_one_or_none()
        if row_id is None:
            await session.rollback()
            return None
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        violation = as_unique_violation(error) or as_foreign_key_violation(error)
        if violation is not None:
            raise violation from error
        raise
    except Exception:
        await session.rollback()
        raise
    return row_id

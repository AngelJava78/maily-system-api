"""The trivial query of the database health check (spec 005, FR-005, FR-016; research R5)."""

import asyncio

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from src.repositories.database_health_repository import DatabaseHealthRepository
from src.repositories.errors import DatabaseUnavailableError

UNREACHABLE_URL = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/not_configured_test"


async def test_against_the_test_database_the_ping_succeeds(engine: AsyncEngine, migrated_db: None):
    async with AsyncSession(engine) as session:
        await DatabaseHealthRepository(session).ping()


async def test_a_database_that_cannot_be_reached_is_a_connection_error():
    unreachable = create_async_engine(UNREACHABLE_URL)
    try:
        async with AsyncSession(unreachable) as session:
            with pytest.raises(DatabaseUnavailableError) as error:
                await DatabaseHealthRepository(session).ping()
    finally:
        await unreachable.dispose()

    assert error.value.kind == "connection_error"
    assert "127.0.0.1" not in str(error.value)
    assert "nobody" not in str(error.value)


async def test_a_failure_of_the_query_that_is_not_a_disconnection_is_unexpected(
    engine: AsyncEngine, migrated_db: None, monkeypatch
):
    async def failing_execute(*args, **kwargs):
        raise ProgrammingError("SELECT 1", {}, Exception("SECRETO-INTERNO"))

    async with AsyncSession(engine) as session:
        monkeypatch.setattr(session, "execute", failing_execute)
        with pytest.raises(DatabaseUnavailableError) as error:
            await DatabaseHealthRepository(session).ping()

    assert error.value.kind == "unexpected_error"
    assert "SECRETO-INTERNO" not in str(error.value)


async def test_a_cancellation_is_not_swallowed(engine: AsyncEngine, migrated_db: None, monkeypatch):
    async def cancelled_execute(*args, **kwargs):
        raise asyncio.CancelledError

    async with AsyncSession(engine) as session:
        monkeypatch.setattr(session, "execute", cancelled_execute)
        with pytest.raises(asyncio.CancelledError):
            await DatabaseHealthRepository(session).ping()

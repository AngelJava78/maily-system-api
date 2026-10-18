"""Datos iniciales: el catálogo de estatus y nada más (Principio VI, FR-022)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.helpers import Migrator


async def test_the_status_catalog_has_exactly_the_four_system_statuses(db_session: AsyncSession):
    rows = (await db_session.execute(text("SELECT id, name FROM subscription_statuses ORDER BY id"))).all()

    assert [tuple(row) for row in rows] == [
        (1, "Activa"),
        (2, "Inactiva"),
        (3, "Bloqueada"),
        (4, "Eliminada"),
    ]


async def test_there_are_no_initial_subscriptions(db_session: AsyncSession):
    count = (await db_session.execute(text("SELECT count(*) FROM subscriptions"))).scalar_one()

    assert count == 0


@pytest.fixture
async def fresh_schema(migrator: Migrator):
    """El esquema recién migrado, para ver el estado inicial de la secuencia."""
    await migrator.downgrade("base")
    await migrator.upgrade("head")
    yield


async def test_a_status_added_by_hand_receives_id_five(engine: AsyncEngine, fresh_schema):
    async with engine.connect() as connection:
        transaction = await connection.begin()
        new_id = (
            await connection.execute(
                text("INSERT INTO subscription_statuses (name) VALUES ('Manual') RETURNING id")
            )
        ).scalar_one()
        await transaction.rollback()

    assert new_id == 5

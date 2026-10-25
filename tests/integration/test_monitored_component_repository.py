"""MonitoredComponentRepository against a real PostgreSQL 17 (spec 005; Principle V)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.models.monitored_component import MONITORED_COMPONENT_CODE_INDEX, MonitoredComponent
from src.repositories.errors import UniqueViolationError
from src.repositories.monitored_component_repository import MonitoredComponentRepository
from tests.health_support import insert_component
from tests.helpers import assert_pg_error

CHECK_VIOLATION = "23514"
LOCK_NOT_AVAILABLE = "55P03"


def service(code: str = "usuarios", **changes: Any) -> dict[str, Any]:
    """The values of a service as the Service passes them (without `enabled` and `sort_order`)."""
    return {
        "code": code,
        "name": "Usuarios",
        "kind": "service",
        "base_url": "http://components.test/healthy",
        "live_path": "/health/live",
        "ready_path": "/health/ready",
        "info_path": "/info",
        **changes,
    }


@pytest_asyncio.fixture
async def clean_registry(engine: AsyncEngine, migrated_db: None) -> AsyncIterator[None]:
    """The registry is emptied at the end (after every session of the test is closed)."""
    try:
        yield
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE monitored_components"))


@pytest_asyncio.fixture
async def session(engine: AsyncEngine, clean_registry: None) -> AsyncIterator[AsyncSession]:
    """A session whose commits are real."""
    new_session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield new_session
    finally:
        await new_session.close()


@pytest_asyncio.fixture
async def other_session(engine: AsyncEngine, clean_registry: None) -> AsyncIterator[AsyncSession]:
    """A second, independent session (another connection)."""
    new_session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield new_session
    finally:
        await new_session.close()


async def codes_in_table(engine: AsyncEngine) -> list[str]:
    async with AsyncSession(engine) as reader:
        return list((await reader.scalars(select(MonitoredComponent.code))).all())


# --- list_enabled (the read of the aggregation) ---


async def test_an_empty_registry_reads_as_an_empty_list(session: AsyncSession):
    assert await MonitoredComponentRepository(session).list_enabled() == []


async def test_only_the_current_enabled_components_are_read_in_their_order(
    engine: AsyncEngine, session: AsyncSession
):
    await insert_component(engine, code="ultimo", sort_order=30)
    await insert_component(engine, code="ab", sort_order=10)
    await insert_component(engine, code="a-c", sort_order=10)  # a hyphen sorts before letters ("C")
    await insert_component(engine, code="apagado", sort_order=0, enabled=False)
    await insert_component(engine, code="borrado", sort_order=0, deleted_at=datetime.now(UTC))
    await insert_component(engine, code="primero", sort_order=0)

    found = await MonitoredComponentRepository(session).list_enabled()

    assert [component.code for component in found] == ["primero", "a-c", "ab", "ultimo"]


# --- list_current, get_current ---


async def test_the_list_has_the_disabled_ones_without_the_deleted_ones_in_their_order(
    engine: AsyncEngine, session: AsyncSession
):
    await insert_component(engine, code="ab", sort_order=10)
    await insert_component(engine, code="a-c", sort_order=10)
    await insert_component(engine, code="apagado", sort_order=20, enabled=False)
    await insert_component(engine, code="borrado", sort_order=0, deleted_at=datetime.now(UTC))

    found = await MonitoredComponentRepository(session).list_current()

    assert [(component.code, component.enabled) for component in found] == [
        ("a-c", True),
        ("ab", True),
        ("apagado", False),
    ]


async def test_get_current_finds_a_current_one_disabled_or_not(engine: AsyncEngine, session: AsyncSession):
    component_id = await insert_component(engine, code="apagado", enabled=False)

    found = await MonitoredComponentRepository(session).get_current(component_id)

    assert (found.id, found.code, found.enabled) == (component_id, "apagado", False)


async def test_get_current_and_lock_current_do_not_see_a_deleted_or_missing_one(
    engine: AsyncEngine, session: AsyncSession
):
    deleted = await insert_component(engine, code="borrado", deleted_at=datetime.now(UTC))
    repository = MonitoredComponentRepository(session)

    for component_id in (deleted, uuid4()):
        assert await repository.get_current(component_id) is None
        assert await repository.lock_current(component_id) is None
        await repository.rollback()


# --- create ---


async def test_create_returns_the_stored_row_with_the_defaults_of_the_table(session: AsyncSession):
    created = await MonitoredComponentRepository(session).create(service())

    assert isinstance(created.id, UUID)
    assert (created.code, created.kind, created.base_url) == ("usuarios", "service", "http://components.test/healthy")
    assert (created.live_path, created.ready_path, created.info_path) == ("/health/live", "/health/ready", "/info")
    assert (created.enabled, created.sort_order, created.deleted_at) == (True, 0, None)
    assert created.created_at.tzinfo is not None
    assert created.created_at == created.updated_at


async def test_a_repeated_code_among_the_current_ones_is_a_unique_violation_of_its_index(
    session: AsyncSession,
):
    repository = MonitoredComponentRepository(session)
    await repository.create(service())

    with pytest.raises(UniqueViolationError) as error:
        await repository.create(service(name="Otro"))

    assert error.value.constraint_name == MONITORED_COMPONENT_CODE_INDEX
    assert len(await repository.list_current()) == 1  # the session is still usable


async def test_the_code_of_a_deleted_component_can_be_registered_again_with_another_id(
    session: AsyncSession,
):
    repository = MonitoredComponentRepository(session)
    first = await repository.create(service())
    assert await repository.soft_delete(first.id) is True

    second = await repository.create(service())

    assert second.id != first.id
    assert [component.id for component in await repository.list_current()] == [second.id]


async def test_two_simultaneous_creations_with_the_same_code_produce_one_row(
    engine: AsyncEngine, clean_registry: None
):
    async def attempt() -> bool:
        async with AsyncSession(engine, expire_on_commit=False) as attempt_session:
            try:
                await MonitoredComponentRepository(attempt_session).create(service("carrera"))
            except UniqueViolationError:
                return False
            return True

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == [False, True]
    assert await codes_in_table(engine) == ["carrera"]


# --- lock_current, update ---


async def test_lock_current_holds_the_row_until_the_transaction_ends(
    engine: AsyncEngine, session: AsyncSession, other_session: AsyncSession
):
    component_id = await insert_component(engine, code="bloqueado")
    first, second = MonitoredComponentRepository(session), MonitoredComponentRepository(other_session)

    assert (await first.lock_current(component_id)).code == "bloqueado"
    await other_session.execute(text("SET lock_timeout = '200ms'"))
    with pytest.raises(DBAPIError) as error:
        await second.lock_current(component_id)
    assert_pg_error(error, LOCK_NOT_AVAILABLE)
    await second.rollback()

    await session.commit()

    assert (await second.lock_current(component_id)).code == "bloqueado"
    await second.rollback()


async def test_update_changes_only_the_given_columns_and_moves_the_modification_date(
    engine: AsyncEngine, session: AsyncSession
):
    component_id = await insert_component(engine, code="usuarios", name="Usuarios", sort_order=5)

    updated = await MonitoredComponentRepository(session).update(component_id, {"name": "Cambio", "enabled": False})

    assert (updated.name, updated.enabled, updated.sort_order, updated.code) == ("Cambio", False, 5, "usuarios")
    assert updated.updated_at > updated.created_at  # another transaction: the trigger moved it


async def test_update_after_lock_current_commits_the_change_and_frees_the_row(
    engine: AsyncEngine, session: AsyncSession, other_session: AsyncSession
):
    component_id = await insert_component(engine, code="usuarios")
    repository = MonitoredComponentRepository(session)

    assert await repository.lock_current(component_id) is not None
    updated = await repository.update(component_id, {"sort_order": 7})

    await other_session.execute(text("SET lock_timeout = '200ms'"))
    assert (await MonitoredComponentRepository(other_session).lock_current(component_id)).sort_order == 7
    assert updated.sort_order == 7


async def test_update_of_a_deleted_or_missing_component_returns_none(engine: AsyncEngine, session: AsyncSession):
    deleted = await insert_component(engine, code="borrado", deleted_at=datetime.now(UTC))
    repository = MonitoredComponentRepository(session)

    assert await repository.update(deleted, {"name": "Cambio"}) is None
    assert await repository.update(uuid4(), {"name": "Cambio"}) is None


async def test_update_to_the_code_of_another_current_component_is_a_unique_violation(
    engine: AsyncEngine, session: AsyncSession
):
    await insert_component(engine, code="pacientes")
    component_id = await insert_component(engine, code="usuarios")

    with pytest.raises(UniqueViolationError) as error:
        await MonitoredComponentRepository(session).update(component_id, {"code": "pacientes"})

    assert error.value.constraint_name == MONITORED_COMPONENT_CODE_INDEX


# --- soft_delete ---


async def test_soft_delete_keeps_the_row_with_its_date_and_says_false_the_second_time(
    engine: AsyncEngine, session: AsyncSession
):
    component_id = await insert_component(engine, code="usuarios")
    repository = MonitoredComponentRepository(session)

    assert await repository.soft_delete(component_id) is True
    assert await repository.soft_delete(component_id) is False
    assert await repository.soft_delete(uuid4()) is False

    async with AsyncSession(engine) as reader:
        deleted_at = await reader.scalar(
            select(MonitoredComponent.deleted_at).where(MonitoredComponent.id == component_id)
        )
    assert deleted_at is not None


# --- the constraints of the table ---


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        (service(ready_path=None), "monitored_components_service_paths_check"),
        (service(info_path=None), "monitored_components_service_paths_check"),
        (service(kind="frontend", info_path=None), "monitored_components_frontend_ready_path_check"),
        (service("database"), "monitored_components_code_check"),
        (service(name=" Usuarios "), "monitored_components_name_check"),
        (service(sort_order=10_000), "monitored_components_sort_order_check"),
    ],
)
async def test_the_table_rejects_what_the_rules_forbid(session: AsyncSession, values, constraint):
    with pytest.raises(IntegrityError) as error:
        await MonitoredComponentRepository(session).create(values)

    assert_pg_error(error, CHECK_VIOLATION, constraint=constraint)

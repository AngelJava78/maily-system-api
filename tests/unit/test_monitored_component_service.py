"""Rules of the registry of components (spec 005, FR-024 to FR-031; research R14, R15).

`MonitoredComponentService` with a double of the Repository, a real `HealthState` and a test
configuration: the list of allowed hosts, the rules that depend on `kind`, the reserved codes, the
conflicts, the order of the errors and the invalidation of the cache (only when something changed).
"""

import dataclasses
from uuid import UUID, uuid4

import pytest

from src.config import AllowedHosts
from src.dtos.monitored_component import MonitoredComponentCreate, MonitoredComponentUpdate
from src.exceptions import (
    MonitoredComponentCodeAlreadyExistsError,
    MonitoredComponentDataError,
    MonitoredComponentNotFoundError,
)
from src.models.monitored_component import MONITORED_COMPONENT_CODE_INDEX
from src.repositories.errors import UniqueViolationError
from src.services.health_state import HealthState
from src.services.monitored_component_service import MonitoredComponentService, apply_kind_rules
from tests.health_support import TEST_HEALTH_CONFIG, make_component

DEFAULTS = {"live_path": "/health/live", "ready_path": "/health/ready", "info_path": "/info"}
SERVICE = {"code": "usuarios", "name": "Usuarios", "kind": "service", "base_url": "http://components.test/healthy"}


class FakeRepository:
    """The Repository of the registry, in memory; it records what the Service asked."""

    def __init__(self, *components, unique_violation: bool = False) -> None:
        self.rows = {component.id: component for component in components}
        self.calls: list[str] = []
        self.rollbacks = 0
        self.unique_violation = unique_violation
        self.created: dict | None = None
        self.updated: dict | None = None

    async def list_current(self):
        self.calls.append("list_current")
        return list(self.rows.values())

    async def get_current(self, component_id: UUID):
        self.calls.append("get_current")
        return self.rows.get(component_id)

    async def create(self, values: dict):
        self.calls.append("create")
        if self.unique_violation:
            raise UniqueViolationError(MONITORED_COMPONENT_CODE_INDEX)
        self.created = values
        component = make_component(**values)
        self.rows[component.id] = component
        return component

    async def lock_current(self, component_id: UUID):
        self.calls.append("lock_current")
        return self.rows.get(component_id)

    async def update(self, component_id: UUID, changes: dict):
        self.calls.append("update")
        if self.unique_violation:
            raise UniqueViolationError(MONITORED_COMPONENT_CODE_INDEX)
        self.updated = changes
        component = self.rows[component_id]
        for field, value in changes.items():
            setattr(component, field, value)
        return component

    async def soft_delete(self, component_id: UUID) -> bool:
        self.calls.append("soft_delete")
        return self.rows.pop(component_id, None) is not None

    async def rollback(self) -> None:
        self.rollbacks += 1


def service_with(repository: FakeRepository, *, allowed: str | None = None) -> tuple[MonitoredComponentService, HealthState]:
    state = HealthState()
    config = TEST_HEALTH_CONFIG
    if allowed is not None:
        config = dataclasses.replace(config, allowed_hosts=AllowedHosts.parse(allowed))
    return MonitoredComponentService(repository, state, config), state


def fields_of(error: pytest.ExceptionInfo[MonitoredComponentDataError]) -> list[str]:
    return [item["loc"][-1] for item in error.value.errors]


# --- apply_kind_rules ---


def test_a_service_without_paths_takes_the_routes_of_the_contract():
    values = apply_kind_rules({**SERVICE, "live_path": None, "ready_path": None, "info_path": None}, set(SERVICE))

    assert {field: values[field] for field in DEFAULTS} == DEFAULTS


@pytest.mark.parametrize("field", ["live_path", "ready_path", "info_path"])
def test_a_service_cannot_null_one_of_its_paths(field):
    values = {**SERVICE, **DEFAULTS, field: None}

    with pytest.raises(MonitoredComponentDataError) as error:
        apply_kind_rules(values, {*SERVICE, field})

    assert fields_of(error) == [field]


def test_a_frontend_needs_its_health_route():
    with pytest.raises(MonitoredComponentDataError) as error:
        apply_kind_rules({**SERVICE, "kind": "frontend", "live_path": None, "ready_path": None, "info_path": None}, set(SERVICE))

    assert fields_of(error) == ["live_path"]


def test_a_frontend_carries_no_readiness_route():
    values = {**SERVICE, "kind": "frontend", "live_path": "/healthz/", "ready_path": "/health/ready", "info_path": None}

    with pytest.raises(MonitoredComponentDataError) as error:
        apply_kind_rules(values, {*SERVICE, "ready_path"})

    assert fields_of(error) == ["ready_path"]


@pytest.mark.parametrize("info_path", [None, "/version.json"])
def test_the_information_route_of_a_frontend_is_optional(info_path):
    values = {**SERVICE, "kind": "frontend", "live_path": "/healthz/", "ready_path": None, "info_path": info_path}

    assert apply_kind_rules(values, set(SERVICE))["info_path"] == info_path


# --- create ---


async def test_a_creation_applies_the_defaults_and_invalidates_the_cache():
    repository = FakeRepository()
    service, state = service_with(repository)

    component = await service.create(MonitoredComponentCreate.model_validate(SERVICE))

    assert {field: repository.created[field] for field in DEFAULTS} == DEFAULTS
    assert (repository.created["enabled"], repository.created["sort_order"]) == (True, 0)
    assert component.code == "usuarios"
    assert state.generation == 1


@pytest.mark.parametrize("allowed", ["otro-host", ""])
async def test_a_host_outside_the_list_is_refused_before_touching_the_repository(allowed):
    repository = FakeRepository()
    service, state = service_with(repository, allowed=allowed)

    with pytest.raises(MonitoredComponentDataError) as error:
        await service.create(MonitoredComponentCreate.model_validate(SERVICE))

    assert fields_of(error) == ["base_url"]
    assert repository.calls == []
    assert state.generation == 0


@pytest.mark.parametrize("code", ["maily-system-api", "database"])
async def test_a_reserved_code_is_a_conflict_without_touching_the_repository(code):
    repository = FakeRepository()
    service, state = service_with(repository)

    with pytest.raises(MonitoredComponentCodeAlreadyExistsError):
        await service.create(MonitoredComponentCreate.model_validate({**SERVICE, "code": code}))

    assert repository.calls == []
    assert state.generation == 0


async def test_a_code_in_use_is_a_conflict_and_nothing_is_invalidated():
    service, state = service_with(FakeRepository(unique_violation=True))

    with pytest.raises(MonitoredComponentCodeAlreadyExistsError) as error:
        await service.create(MonitoredComponentCreate.model_validate(SERVICE))

    assert "usuarios" in error.value.message
    assert state.generation == 0


async def test_the_errors_of_the_host_and_of_the_kind_come_together():
    service, _ = service_with(FakeRepository(), allowed="otro-host")
    data = MonitoredComponentCreate.model_validate({**SERVICE, "kind": "frontend", "ready_path": "/x"})

    with pytest.raises(MonitoredComponentDataError) as error:
        await service.create(data)

    assert fields_of(error) == ["base_url", "live_path", "ready_path"]


# --- update ---


async def test_a_new_base_url_is_checked_before_locking_the_row():
    existing = make_component("usuarios", base_url="http://components.test/healthy")
    repository = FakeRepository(existing)
    service, state = service_with(repository)

    with pytest.raises(MonitoredComponentDataError) as error:
        await service.update(existing.id, MonitoredComponentUpdate.model_validate({"base_url": "http://otro-host"}))

    assert fields_of(error) == ["base_url"]
    assert repository.calls == []
    assert state.generation == 0


async def test_a_missing_component_is_not_found():
    repository = FakeRepository()
    service, state = service_with(repository)
    unknown = uuid4()

    with pytest.raises(MonitoredComponentNotFoundError) as error:
        await service.update(unknown, MonitoredComponentUpdate.model_validate({"name": "Otro"}))

    assert str(unknown) in error.value.message
    assert repository.rollbacks == 1
    assert state.generation == 0


async def test_turning_a_service_into_a_frontend_needs_a_null_readiness_route():
    existing = make_component("usuarios", base_url="http://components.test/healthy")
    repository = FakeRepository(existing)
    service, state = service_with(repository)

    with pytest.raises(MonitoredComponentDataError) as error:
        await service.update(existing.id, MonitoredComponentUpdate.model_validate({"kind": "frontend"}))

    assert fields_of(error) == ["ready_path"]
    assert repository.rollbacks == 1
    assert "update" not in repository.calls
    assert state.generation == 0


async def test_turning_a_frontend_into_a_service_takes_the_routes_of_the_contract():
    existing = make_component("web", kind="frontend", base_url="http://components.test/spa")
    repository = FakeRepository(existing)
    service, state = service_with(repository)

    await service.update(existing.id, MonitoredComponentUpdate.model_validate({"kind": "service", "live_path": "/health/live"}))

    assert repository.updated == {"kind": "service", **DEFAULTS}
    assert state.generation == 1


async def test_a_reserved_code_in_an_update_is_a_conflict_after_the_existence_check():
    existing = make_component("usuarios", base_url="http://components.test/healthy")
    repository = FakeRepository(existing)
    service, _ = service_with(repository)

    with pytest.raises(MonitoredComponentNotFoundError):
        await service.update(uuid4(), MonitoredComponentUpdate.model_validate({"code": "database"}))
    with pytest.raises(MonitoredComponentCodeAlreadyExistsError):
        await service.update(existing.id, MonitoredComponentUpdate.model_validate({"code": "database"}))

    assert "update" not in repository.calls


async def test_a_code_used_by_another_component_is_a_conflict():
    existing = make_component("usuarios", base_url="http://components.test/healthy")
    service, state = service_with(FakeRepository(existing, unique_violation=True))

    with pytest.raises(MonitoredComponentCodeAlreadyExistsError):
        await service.update(existing.id, MonitoredComponentUpdate.model_validate({"code": "pacientes"}))

    assert state.generation == 0


async def test_only_what_was_sent_changes_and_the_cache_is_invalidated():
    existing = make_component("usuarios", base_url="http://components.test/healthy")
    repository = FakeRepository(existing)
    service, state = service_with(repository)

    component = await service.update(existing.id, MonitoredComponentUpdate.model_validate({"enabled": False}))

    assert repository.updated == {"enabled": False}
    assert component.enabled is False
    assert state.generation == 1


# --- delete, get and list ---


async def test_deleting_a_missing_component_is_not_found_and_invalidates_nothing():
    service, state = service_with(FakeRepository())

    with pytest.raises(MonitoredComponentNotFoundError):
        await service.delete(uuid4())

    assert state.generation == 0


async def test_deleting_a_component_invalidates_the_cache():
    existing = make_component("usuarios")
    service, state = service_with(FakeRepository(existing))

    await service.delete(existing.id)

    assert state.generation == 1


async def test_getting_a_missing_component_is_not_found_with_its_identifier():
    unknown = uuid4()
    service, _ = service_with(FakeRepository())

    with pytest.raises(MonitoredComponentNotFoundError) as error:
        await service.get(unknown)

    assert str(unknown) in error.value.message


async def test_the_list_is_the_one_of_the_repository():
    first, second = make_component("a"), make_component("b")
    service, _ = service_with(FakeRepository(first, second))

    assert [component.code for component in await service.list()] == ["a", "b"]

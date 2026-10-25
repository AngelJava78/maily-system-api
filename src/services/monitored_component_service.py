"""Rules of the registry of monitored components (spec 005, FR-023 to FR-031; research R14, R15).

The order of the checks is the one of `contracts/error-catalog.md`: the data (the DTO and the list
of allowed hosts), the existence, the rules that depend on `kind` on the resulting component, and
the code (reserved, or in use: the unique index decides). Only a change that succeeds invalidates the
cached result of the health (FR-020); a failure changes nothing.
"""

from collections.abc import Mapping, Set
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from src.config import AllowedHosts, HealthConfig
from src.dtos.monitored_component import MonitoredComponentCreate, MonitoredComponentUpdate
from src.exceptions import (
    MonitoredComponentCodeAlreadyExistsError,
    MonitoredComponentDataError,
    MonitoredComponentNotFoundError,
)
from src.messages import (
    MONITORED_COMPONENT_FRONTEND_LIVE_PATH_REQUIRED_MESSAGE,
    MONITORED_COMPONENT_FRONTEND_READY_PATH_NOT_ALLOWED_MESSAGE,
    MONITORED_COMPONENT_HOST_NOT_ALLOWED_MESSAGE,
    MONITORED_COMPONENT_SERVICE_PATH_REQUIRED_MESSAGE,
)
from src.models.monitored_component import MONITORED_COMPONENT_CODE_INDEX, MonitoredComponent
from src.repositories.errors import UniqueViolationError
from src.repositories.monitored_component_repository import MonitoredComponentRepository
from src.services.health_service import RESERVED_CODES
from src.services.health_state import HealthState

# The routes of the contract v1 that a service takes when it does not send them.
SERVICE_DEFAULT_PATHS = {
    "live_path": "/health/live",
    "ready_path": "/health/ready",
    "info_path": "/info",
}
# What a modification may change: never the identifier or the dates.
EDITABLE_FIELDS = (
    "code",
    "name",
    "kind",
    "base_url",
    "live_path",
    "ready_path",
    "info_path",
    "enabled",
    "sort_order",
)

FieldErrors = list[dict[str, Any]]


def _kind_rules(values: Mapping[str, Any], sent: Set[str]) -> tuple[dict[str, Any], FieldErrors]:
    """The component with the rules of its `kind` applied, and the errors on the affected fields."""
    result = dict(values)
    errors: FieldErrors = []
    if result["kind"] == "service":
        for field, default in SERVICE_DEFAULT_PATHS.items():
            if result[field] is not None:
                continue
            if field in sent:  # a `null` sent on purpose
                errors.append(
                    MonitoredComponentDataError.field_error(
                        field, MONITORED_COMPONENT_SERVICE_PATH_REQUIRED_MESSAGE
                    )
                )
            else:
                result[field] = default
    else:
        if result["live_path"] is None:
            errors.append(
                MonitoredComponentDataError.field_error(
                    "live_path", MONITORED_COMPONENT_FRONTEND_LIVE_PATH_REQUIRED_MESSAGE
                )
            )
        if result["ready_path"] is not None:
            errors.append(
                MonitoredComponentDataError.field_error(
                    "ready_path", MONITORED_COMPONENT_FRONTEND_READY_PATH_NOT_ALLOWED_MESSAGE
                )
            )
    return result, errors


def apply_kind_rules(values: Mapping[str, Any], sent: Set[str]) -> dict[str, Any]:
    """Apply the rules that depend on `kind` (data-model.md section 3) to a whole component.

    `values` is a creation, or the stored row with a modification on top; `sent` is what the
    request carried (`model_fields_set`), so "not sent" and "sent as `null`" differ. A service takes
    the routes of the contract v1 that are null and were not sent, and refuses a route sent as
    `null`; a frontend needs its health route and carries no readiness route. Raises
    `MonitoredComponentDataError` with every affected field.
    """
    result, errors = _kind_rules(values, sent)
    if errors:
        raise MonitoredComponentDataError(errors)
    return result


def _host_errors(base_url: str, allowed_hosts: AllowedHosts) -> FieldErrors:
    """The error on `base_url` when its host is not in the list (or there is no list, FR-027)."""
    if allowed_hosts.allows(urlsplit(base_url).hostname or ""):
        return []
    return [
        MonitoredComponentDataError.field_error(
            "base_url", MONITORED_COMPONENT_HOST_NOT_ALLOWED_MESSAGE
        )
    ]


class MonitoredComponentService:
    """Administration of the registry: what the health of the platform checks besides itself."""

    def __init__(
        self, repository: MonitoredComponentRepository, state: HealthState, config: HealthConfig
    ) -> None:
        self._repository = repository
        self._state = state
        self._config = config

    async def list(self) -> list[MonitoredComponent]:
        """Every current component, enabled or not, by `sort_order` and `code`."""
        return await self._repository.list_current()

    async def get(self, component_id: UUID) -> MonitoredComponent:
        component = await self._repository.get_current(component_id)
        if component is None:
            raise MonitoredComponentNotFoundError(component_id)
        return component

    async def create(self, data: MonitoredComponentCreate) -> MonitoredComponent:
        """Register a component. The code in use is not checked beforehand: the index decides.

        Checking first would leave a race between two requests with the same code (FR-028).
        """
        values, kind_errors = _kind_rules(data.model_dump(), data.model_fields_set)
        errors = _host_errors(values["base_url"], self._config.allowed_hosts) + kind_errors
        if errors:
            raise MonitoredComponentDataError(errors)
        if values["code"] in RESERVED_CODES:
            raise MonitoredComponentCodeAlreadyExistsError(values["code"])
        try:
            component = await self._repository.create(values)
        except UniqueViolationError as error:
            if error.constraint_name == MONITORED_COMPONENT_CODE_INDEX:
                raise MonitoredComponentCodeAlreadyExistsError(values["code"]) from error
            raise
        self._state.invalidate()
        return component

    async def update(
        self, component_id: UUID, data: MonitoredComponentUpdate
    ) -> MonitoredComponent:
        """Change the fields that were sent and validate the resulting component like a creation.

        The row stays locked from the read to the write, so two simultaneous modifications are
        validated one on top of the other; every failure after the lock ends the transaction.
        """
        changes = data.model_dump(exclude_unset=True)
        if "base_url" in changes:
            host_errors = _host_errors(changes["base_url"], self._config.allowed_hosts)
            if host_errors:
                raise MonitoredComponentDataError(host_errors)
        current = await self._repository.lock_current(component_id)
        if current is None:
            await self._repository.rollback()
            raise MonitoredComponentNotFoundError(component_id)
        stored = {field: getattr(current, field) for field in EDITABLE_FIELDS}
        try:
            result = apply_kind_rules({**stored, **changes}, data.model_fields_set)
        except MonitoredComponentDataError:
            await self._repository.rollback()
            raise
        if result["code"] in RESERVED_CODES:
            await self._repository.rollback()
            raise MonitoredComponentCodeAlreadyExistsError(result["code"])
        # What was sent, plus the routes that the rules of `kind` filled in.
        final = {
            field: value
            for field, value in result.items()
            if field in changes or value != stored[field]
        }
        try:
            component = await self._repository.update(component_id, final)
        except UniqueViolationError as error:
            if error.constraint_name == MONITORED_COMPONENT_CODE_INDEX:
                raise MonitoredComponentCodeAlreadyExistsError(result["code"]) from error
            raise
        if component is None:  # cannot happen while the row is locked
            raise MonitoredComponentNotFoundError(component_id)
        self._state.invalidate()
        return component

    async def delete(self, component_id: UUID) -> None:
        """Logical deletion: the code is free again and the health stops showing it."""
        if not await self._repository.soft_delete(component_id):
            raise MonitoredComponentNotFoundError(component_id)
        self._state.invalidate()

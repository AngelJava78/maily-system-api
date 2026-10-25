"""Memory of the health feature in one process (spec 005, research R10 and R11).

One `HealthState` per application (`app.state.health`): the last result of an aggregation, the
aggregation in progress (at most one), a generation that a change of the registry increments, the
last copy of the registry that was read, the readiness check in progress and the last status of each
component (to log only the changes). It does no I/O and knows no configuration.
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.health_service import ComponentTarget, HealthResult, ReadinessResult


@dataclass(frozen=True, slots=True)
class CachedResult:
    """A finished aggregation: its result, when it finished (monotonic) and its generation."""

    result: "HealthResult"
    completed_at: float
    generation: int


@dataclass(frozen=True, slots=True)
class InFlight:
    """The aggregation in progress and the generation of the registry it started with."""

    generation: int
    task: "asyncio.Task[HealthResult]"


class HealthState:
    def __init__(self) -> None:
        self.generation = 0
        self.last: CachedResult | None = None
        self.in_flight: InFlight | None = None
        # None until the registry is read successfully once; then the last copy that was read.
        self.registry_snapshot: "tuple[ComponentTarget, ...] | None" = None
        self.readiness_task: "asyncio.Task[ReadinessResult] | None" = None
        self.last_statuses: dict[str, str] = {}

    def invalidate(self) -> None:
        """A change of the registry: no finished result of before the change is reused (FR-020)."""
        self.generation += 1
        self.last = None

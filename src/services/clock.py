"""The clock of the health Services (spec 005).

The Services receive it instead of reading the time themselves, so the tests can move it: the
schedule of the database and `next_start_at` depend on the wall time (in UTC), and the cache on a
monotonic clock that does not jump when the wall time changes.
"""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, aware and in UTC."""
        ...

    def monotonic(self) -> float:
        """Seconds of a clock that only moves forward (for ages and periods)."""
        ...


class SystemClock:
    """The real clock of the process."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

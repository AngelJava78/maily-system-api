"""The retry loop of the one-off backfill script (FR-010): never gives up, never guesses."""

import pytest

from src.integrations.errors import ClinicsApiUnavailable
from src.scripts.backfill_subscription_types import reconcile_with_retry


class FailsThenSucceeds:
    """Stands in for `SubscriptionService`: fails its first `failures` calls, then succeeds."""

    def __init__(self, failures: int, result: int) -> None:
        self.failures = failures
        self.result = result
        self.calls = 0

    async def reconcile_types_from_clinic_counts(self, token: str) -> int:
        self.calls += 1
        if self.calls <= self.failures:
            raise ClinicsApiUnavailable()
        return self.result


class AlwaysFails:
    def __init__(self) -> None:
        self.calls = 0

    async def reconcile_types_from_clinic_counts(self, token: str) -> int:
        self.calls += 1
        raise ClinicsApiUnavailable()


async def test_it_retries_until_the_clinics_api_answers_and_returns_that_result():
    service = FailsThenSucceeds(failures=2, result=3)
    waits: list[float] = []

    async def recording_sleep(seconds: float) -> None:
        waits.append(seconds)

    result = await reconcile_with_retry(service, "token", sleep=recording_sleep)

    assert result == 3
    assert service.calls == 3  # 2 failed attempts, then the one that succeeded
    assert len(waits) == 2
    assert waits[1] > waits[0]  # growing delay, never a tight loop


async def test_it_never_gives_up_on_a_clinics_api_that_never_answers():
    """Stopped by the test's own escape hatch (not production code): proves it would not stop."""
    service = AlwaysFails()
    attempts = 0

    async def recording_sleep(seconds: float) -> None:
        nonlocal attempts
        attempts += 1
        if attempts >= 5:
            raise RuntimeError("stop-test")

    with pytest.raises(RuntimeError, match="stop-test"):
        await reconcile_with_retry(service, "token", sleep=recording_sleep)

    assert service.calls == 5  # one attempt per wait, never answered, never "gave up" with a guess


async def test_the_delay_never_grows_without_bound():
    service = AlwaysFails()
    waits: list[float] = []

    async def recording_sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) >= 8:
            raise RuntimeError("stop-test")

    with pytest.raises(RuntimeError, match="stop-test"):
        await reconcile_with_retry(service, "token", sleep=recording_sleep)

    assert waits == sorted(waits)  # never decreases
    assert waits[-1] == waits[-2]  # capped: stopped growing well before 8 doublings

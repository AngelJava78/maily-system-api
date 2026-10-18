"""The catalog at the size the constitution allows for an unpaginated list (SC-001)."""

import time

from sqlalchemy import text

from tests.helpers import Api

URL = "/api/v1/subscriptions"
TOTAL = 500
LIMIT_SECONDS = 2.0


async def seed(api: Api) -> None:
    """500 subscriptions with statuses 1, 2, 3 and 4 in turn, created one second apart."""
    async with api.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO subscriptions (name, monthly_price, status_id, created_at) "
                "SELECT 'Plan ' || g, 100, ((g - 1) % 4) + 1, "
                "TIMESTAMPTZ '2026-01-01 00:00:00+00' + (g || ' seconds')::interval "
                "FROM generate_series(1, :total) AS g"
            ),
            {"total": TOTAL},
        )


async def test_five_hundred_subscriptions_come_in_order_in_under_two_seconds(api: Api):
    await seed(api)
    await api.counts({1: 4, 2: 1})

    started = time.perf_counter()
    response = await api.client.get(URL)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    body = response.json()
    # Every fourth one (status 4) is deleted and does not appear.
    expected = [n for n in range(1, TOTAL + 1) if n % 4 != 0]
    assert [s["name"] for s in body] == [f"Plan {n}" for n in expected]
    assert len(body) == 375
    assert elapsed < LIMIT_SECONDS


async def test_the_95th_percentile_of_thirty_queries_is_under_two_seconds(api: Api):
    await seed(api)
    timings = []

    for _ in range(30):
        started = time.perf_counter()
        response = await api.client.get(URL)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200

    timings.sort()
    percentile_95 = timings[int(len(timings) * 0.95) - 1]
    assert percentile_95 < LIMIT_SECONDS

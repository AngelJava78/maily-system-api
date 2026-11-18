"""What must happen once, happens once with simultaneous requests (spec 010, SC-005).

The real application, the real PostgreSQL and many requests at the same time over the same client, as the
people of an organization could make them: creating the record and moving the payment date.
"""

import asyncio

import pytest
from sqlalchemy import text

from tests.billing_support import ORG_ID, BillingApi, at

CREATED = "2026-11-20T15:30:00Z"


@pytest.fixture
async def plan_id(billing_api: BillingApi) -> int:
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at=CREATED)
    return plan


async def start_and_approve(billing_api: BillingApi, approved_at: str) -> str:
    assert (await billing_api.start_payment()).status_code == 201
    payment_id = (await billing_api.payments())[-1]["id"]
    await billing_api.set_payment_status(payment_id, "approved", updated_at=approved_at)
    return payment_id


async def test_twenty_simultaneous_first_consultations_create_one_record(billing_api: BillingApi, plan_id: int):
    responses = await asyncio.gather(*(billing_api.get_period() for _ in range(20)))

    assert {r.status_code for r in responses} == {200}
    assert len({r.text for r in responses}) == 1
    assert len(await billing_api.periods()) == 1


async def test_twenty_simultaneous_consultations_after_an_approval_move_the_date_once(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await start_and_approve(billing_api, "2026-12-01T10:00:00Z")

    responses = await asyncio.gather(*(billing_api.get_period() for _ in range(20)))

    assert {r.status_code for r in responses} == {200}
    assert {r.json()["payment_due_at"] for r in responses} == {"2027-01-04T15:30:00Z"}
    assert [(c[7], c[10]) for c in await billing_api.charges()] == [("applied", at("2027-01-04T15:30:00Z"))]
    [(_, _, _, paid_until)] = await billing_api.periods()
    assert paid_until == at("2027-01-04T15:30:00Z")  # one month, not twenty


async def test_two_approved_charges_and_ten_simultaneous_consultations_apply_both_in_order(
    billing_api: BillingApi, plan_id: int
):
    billing_api.clock.set(at("2026-12-01T10:00:00Z"))
    await billing_api.start_payment()
    async with billing_api.engine.begin() as connection:
        await connection.execute(
            text("UPDATE subscriptions SET monthly_price = 799.00 WHERE id = :id"), {"id": plan_id}
        )
    await billing_api.start_payment()
    first, second = (p["id"] for p in await billing_api.payments())
    await billing_api.set_payment_status(first, "approved", updated_at="2026-12-01T10:00:00Z")
    await billing_api.set_payment_status(second, "approved", updated_at="2026-12-01T10:01:00Z")

    responses = await asyncio.gather(*(billing_api.get_period() for _ in range(10)))

    assert {r.status_code for r in responses} == {200}
    charges = await billing_api.charges()
    assert [c[7] for c in charges] == ["applied", "applied"]
    # The second continues where the first ends, however the requests interleaved.
    assert [(c[9], c[10]) for c in charges] == [
        (at("2026-12-04T15:30:00Z"), at("2027-01-04T15:30:00Z")),
        (at("2027-01-04T15:30:00Z"), at("2027-02-04T15:30:00Z")),
    ]
    [(_, _, _, paid_until)] = await billing_api.periods()
    assert paid_until == at("2027-02-04T15:30:00Z")


async def test_simultaneous_consultations_and_starts_never_duplicate_a_charge(billing_api: BillingApi, plan_id: int):
    work = [billing_api.get_period() for _ in range(5)] + [billing_api.start_payment() for _ in range(5)]

    responses = await asyncio.gather(*work)

    assert all(r.status_code in (200, 201) for r in responses)
    assert len(await billing_api.charges()) == 1
    assert len(await billing_api.payments()) == 1
    assert len(await billing_api.periods()) == 1
    assert (await billing_api.periods())[0][0] == ORG_ID

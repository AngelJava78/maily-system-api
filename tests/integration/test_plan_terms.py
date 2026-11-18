"""`SubscriptionRepository.get_plan_terms` reads the plan that an organization is billed on (spec 010).

The catalog row is read whatever its status: an organization keeps paying the price of the plan that the
clinics API reports even if the plan no longer admits new clinics (FR-034).
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories import INT4_MAX
from src.repositories.subscription_repository import PlanTerms, SubscriptionRepository
from tests.helpers import insert_subscription


@pytest.mark.parametrize("status_id", [1, 2, 3, 4], ids=["active", "inactive", "blocked", "deleted"])
async def test_the_terms_of_a_plan_are_read_in_any_status(db_session: AsyncSession, status_id: int):
    plan_id = await insert_subscription(
        db_session,
        name=f"Plan {status_id}",
        monthly_price="499.00",
        annual_price="4990.00",
        trial_days=14,
        status_id=status_id,
    )

    terms = await SubscriptionRepository(db_session).get_plan_terms(plan_id)

    assert terms == PlanTerms(
        id=plan_id,
        name=f"Plan {status_id}",
        trial_days=14,
        monthly_price=Decimal("499.00"),
        annual_price=Decimal("4990.00"),
    )


async def test_the_terms_of_a_plan_with_a_status_added_by_hand_are_read_too(db_session: AsyncSession):
    await db_session.execute(text("INSERT INTO subscription_statuses (id, name) VALUES (5, 'Manual')"))
    plan_id = await insert_subscription(db_session, name="A mano", status_id=5)

    terms = await SubscriptionRepository(db_session).get_plan_terms(plan_id)

    assert terms is not None and terms.id == plan_id


async def test_the_prices_keep_their_two_decimals_and_a_free_plan_is_zero(db_session: AsyncSession):
    plan_id = await insert_subscription(db_session, name="Gratis", monthly_price="0.00", annual_price="0")

    terms = await SubscriptionRepository(db_session).get_plan_terms(plan_id)

    assert terms is not None
    assert (terms.monthly_price, terms.annual_price) == (Decimal("0.00"), Decimal("0.00"))
    assert terms.trial_days == 0
    assert isinstance(terms.monthly_price, Decimal)


async def test_a_plan_that_does_not_exist_has_no_terms(db_session: AsyncSession):
    repository = SubscriptionRepository(db_session)

    assert await repository.get_plan_terms(999_999) is None
    assert await repository.get_plan_terms(0) is None
    assert await repository.get_plan_terms(-1) is None


async def test_an_identifier_above_the_limit_of_the_column_is_not_looked_up(db_session: AsyncSession):
    # A value above int4 would make the driver fail: the Repository answers «not found» by itself.
    assert await SubscriptionRepository(db_session).get_plan_terms(INT4_MAX + 1) is None

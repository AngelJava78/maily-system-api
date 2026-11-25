"""The return address of the payments over HTTP (spec 011, stories 1 to 4).

The real application with the real PostgreSQL, the three simulated APIs and a clock that each test moves
(`billing_api`). The simulation of Pagos validates and keeps `redirect_urls` as Pagos does
(`specs/011-payment-return-url/contracts/payments-api-integration.md`); `PAYMENTS_RETURN_URL` is read once,
so each test that defines it clears the cache of the configuration, as a restart would.
"""

import logging

import pytest

from src.config import get_payments_settings
from tests.billing_support import BillingApi, at

CREATED = "2026-11-20T15:30:00Z"
RETURN_URL = "https://app.mailysoft.com/payment"
START_KEYS = {"checkout_url", "amount", "currency", "billing_period"}


@pytest.fixture
async def plan_id(billing_api: BillingApi) -> int:
    """A plan of 14 days of trial, 499.00 a month and 4990.00 a year; the organization is on it."""
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at=CREATED)
    return plan


def configure(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """`PAYMENTS_RETURN_URL` as the operator writes it, read again as after a restart."""
    monkeypatch.setenv("PAYMENTS_RETURN_URL", value)
    get_payments_settings.cache_clear()


@pytest.fixture
def return_url(monkeypatch: pytest.MonkeyPatch) -> str:
    configure(monkeypatch, RETURN_URL)
    return RETURN_URL


# --- story 1: the address travels to Pagos ---


async def test_with_the_address_pagos_receives_it_and_the_answer_does_not_change(
    billing_api: BillingApi, plan_id: int, return_url: str
):
    response = await billing_api.start_payment()

    assert response.status_code == 201
    assert set(response.json()) == START_KEYS  # the address never appears in the answer (FR-009)
    assert return_url not in response.text
    [payment] = await billing_api.payments()
    assert payment["redirect_urls"] == {"success": RETURN_URL}
    assert response.json()["checkout_url"] == payment["checkout_url"]


async def test_with_the_address_starting_twice_gives_the_same_checkout_and_one_payment(
    billing_api: BillingApi, plan_id: int, return_url: str
):
    first = await billing_api.start_payment()
    second = await billing_api.start_payment()

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    assert len(await billing_api.payments()) == 1
    assert len(await billing_api.charges()) == 1


async def test_the_address_travels_as_it_was_written(
    billing_api: BillingApi, plan_id: int, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch, "  https://app.mailysoft.com:8443/payment/?origen=pago  ")

    assert (await billing_api.start_payment()).status_code == 201

    [payment] = await billing_api.payments()
    assert payment["redirect_urls"] == {"success": "https://app.mailysoft.com:8443/payment/?origen=pago"}


# --- story 2: without the address, nothing changes ---


@pytest.mark.parametrize("value", [None, ""], ids=["undefined", "empty"])
async def test_without_the_address_the_payment_carries_no_return(
    billing_api: BillingApi, plan_id: int, monkeypatch: pytest.MonkeyPatch, value: str | None
):
    if value is not None:
        configure(monkeypatch, value)

    response = await billing_api.start_payment()

    assert response.status_code == 201
    [payment] = await billing_api.payments()
    assert "redirect_urls" not in payment  # not even empty or null (FR-007)


# --- story 3: Pagos refuses the address ---


async def test_when_pagos_refuses_the_address_nothing_is_registered(
    billing_api: BillingApi, plan_id: int, return_url: str, caplog: pytest.LogCaptureFixture
):
    await billing_api.payments_fault("return_not_allowed", operation="create")

    with caplog.at_level(logging.DEBUG, logger="src"):
        response = await billing_api.start_payment()

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"
    assert await billing_api.charges() == []
    assert await billing_api.payments() == []
    assert "SECRETO-INTERNO" not in response.text
    assert "return address" in caplog.text  # the operator is told what to check (FR-010)
    assert "mailysoft" not in caplog.text  # never the address itself


# --- story 4: the return is never proof of payment ---


async def test_the_parameters_of_the_return_never_apply_a_charge(
    billing_api: BillingApi, plan_id: int, return_url: str
):
    billing_api.clock.set(at("2026-12-10T09:00:00Z"))
    assert (await billing_api.start_payment()).status_code == 201
    before = (await billing_api.get_period()).json()

    returned = await billing_api.get_period(
        params={"collection_status": "approved", "status": "approved", "payment_id": "1", "external_reference": "x"}
    )

    assert returned.status_code == 200
    assert returned.json()["payment_in_progress"] is True
    assert returned.json()["payment_due_at"] == before["payment_due_at"]
    [charge] = await billing_api.charges()
    assert charge[7] == "pending"  # still waiting for Pagos (FR-012)

    [payment] = await billing_api.payments()
    await billing_api.set_payment_status(payment["id"], "approved", updated_at="2026-12-10T09:05:00Z")
    applied = (await billing_api.get_period()).json()

    assert applied["payment_in_progress"] is False
    assert applied["payment_due_at"] > before["payment_due_at"]
    [charge] = await billing_api.charges()
    assert charge[7] == "applied"  # only what Pagos reports applies a charge, once

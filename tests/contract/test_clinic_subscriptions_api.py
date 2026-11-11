"""The clinic subscriptions API over HTTP: the contract of each operation (spec 006)."""

from datetime import UTC, datetime

from tests.helpers import Api

URL = "/api/v1/clinic-subscriptions"
TENANT = "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f"
CALLER_TOKEN = "clinic-owner-token"
FIELDS = {
    "id",
    "tenant_id",
    "subscription_id",
    "billing_cycle",
    "started_at",
    "next_billing_at",
    "status",
    "current_charge",
    "created_at",
    "updated_at",
}
CHARGE_FIELDS = {
    "id",
    "clinic_subscription_id",
    "period",
    "amount",
    "currency",
    "payment_id",
    "payment_status",
    "checkout_url",
    "created_at",
    "updated_at",
}


async def grant_owner(api: Api, tenant_id: str = TENANT) -> None:
    await api.grant_caller(CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id=tenant_id)
    await api.grant_payments(CALLER_TOKEN)
    # The sync-on-read (research R8) uses the service account configured in the `api` fixture
    # ("pagos-service-token"), never the caller's own token: it must be registered too.
    await api.grant_payments("pagos-service-token", permissions=("payments:read",))


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- US1: assign a plan to a clinic ---


async def test_create_is_active_immediately_without_a_trial(api: Api):
    plan_id = await api.insert(name="Pro", monthly_price="1299.00")

    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert body["status"] == {"id": 1, "name": "Activa"}
    assert body["current_charge"] is None
    assert body["next_billing_at"] == body["started_at"]


async def test_create_defers_the_first_charge_when_the_plan_has_a_trial(api: Api):
    plan_id = await api.insert(name="Con prueba", trial_days=14)

    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"}
    )

    body = response.json()
    started = datetime.fromisoformat(body["started_at"])
    next_billing = datetime.fromisoformat(body["next_billing_at"])
    assert (next_billing - started).days == 14


async def test_create_rejects_a_plan_that_is_not_active(api: Api):
    plan_id = await api.insert(name="Inactivo", status_id=2)

    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_plan_not_active"


async def test_create_rejects_a_second_active_subscription_of_the_same_clinic(api: Api):
    plan_id = await api.insert(name="Pro")
    await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})

    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "annual"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_already_active"


async def test_create_rejects_an_invalid_billing_cycle(api: Api):
    plan_id = await api.insert(name="Pro")

    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "weekly"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "billing_cycle"


async def test_create_rejects_an_unknown_field(api: Api):
    plan_id = await api.insert(name="Pro")

    response = await api.client.post(
        URL,
        json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly", "status": "x"},
    )

    assert response.status_code == 422


# --- US2: charge ---


async def test_charge_sends_the_exact_body_to_payments(api: Api):
    plan_id = await api.insert(name="Pro", monthly_price="1299.00")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == CHARGE_FIELDS
    assert body["amount"] == 129900
    assert body["payment_status"] == "pending"
    assert body["checkout_url"] is not None

    [call] = await api.payments_calls()
    assert call["authorization"] == f"Bearer {CALLER_TOKEN}"


async def test_charge_is_idempotent_for_the_same_period(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)

    first = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))
    second = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert first.json()["payment_id"] == second.json()["payment_id"]
    create_calls = [c for c in await api.payments_calls() if c["path"] == "/api/v1/payments"]
    assert len(create_calls) == 2  # both reached Pagos; the stub kept them idempotent
    assert create_calls[0]["idempotency_key"] == create_calls[1]["idempotency_key"]


async def test_charge_from_another_organization_is_not_found(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.grant_caller(CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id="00000000-0000-4000-8000-000000000099")

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_not_found"


async def test_charge_without_an_organization_is_not_found(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.grant_caller(CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id=None)

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 404


async def test_charge_without_the_permission_is_forbidden(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.grant_caller(CALLER_TOKEN, [], tenant_id=TENANT)

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


async def test_charge_with_a_pending_password_change_is_forbidden(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.grant_caller(
        CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id=TENANT, password_change_required=True
    )

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


async def test_charge_a_cancelled_subscription_is_a_conflict(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.client.delete(f"{URL}/{created['id']}")
    await grant_owner(api)

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_charge_pending"


async def test_charge_when_payments_api_is_down_changes_nothing(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)
    await api.payments_fault("unavailable")

    response = await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"

    again = await api.client.get(f"{URL}/{created['id']}")
    assert again.json()["current_charge"] is None


# --- US3: know the outcome of the charge ---


async def test_get_syncs_a_pending_charge_and_advances_on_approval(api: Api):
    plan_id = await api.insert(name="Pro", monthly_price="1299.00")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)
    charge = (await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))).json()
    await api.set_payment_status(charge["payment_id"], "approved")

    response = await api.client.get(f"{URL}/{created['id']}")

    body = response.json()
    assert body["current_charge"]["payment_status"] == "approved"
    assert body["status"] == {"id": 1, "name": "Activa"}
    assert datetime.fromisoformat(body["next_billing_at"]) > datetime.fromisoformat(created["next_billing_at"])


# --- US4: consult / list ---


async def test_list_is_paginated_with_a_total_count_header(api: Api):
    plan_id = await api.insert(name="Pro")
    await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})

    response = await api.client.get(URL, params={"page": 1, "limit": 1})

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    assert len(response.json()) == 1


async def test_get_an_unknown_subscription_is_not_found(api: Api):
    response = await api.client.get(f"{URL}/999")

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_not_found"


async def test_list_charges_and_get_a_charge(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)
    charge = (await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))).json()

    listed = await api.client.get(f"{URL}/{created['id']}/charges")
    single = await api.client.get(f"{URL}/{created['id']}/charges/{charge['id']}")

    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [charge["id"]]
    assert single.status_code == 200
    assert single.json()["id"] == charge["id"]


async def test_get_an_unknown_charge_is_not_found(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()

    response = await api.client.get(f"{URL}/{created['id']}/charges/999")

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_charge_not_found"


# --- US5: cancel ---


async def test_cancel_an_active_subscription_without_a_pending_charge(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()

    response = await api.client.delete(f"{URL}/{created['id']}")

    assert response.status_code == 204
    again = await api.client.get(f"{URL}/{created['id']}")
    assert again.status_code == 404  # cancelled behaves like not found on a direct GET


async def test_cancel_rejects_a_pending_charge(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await grant_owner(api)
    await api.client.post(f"{URL}/{created['id']}/charges", headers=auth(CALLER_TOKEN))

    response = await api.client.delete(f"{URL}/{created['id']}")

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_charge_pending"


async def test_cancel_an_already_cancelled_subscription(api: Api):
    plan_id = await api.insert(name="Pro")
    created = (
        await api.client.post(URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"})
    ).json()
    await api.client.delete(f"{URL}/{created['id']}")

    response = await api.client.delete(f"{URL}/{created['id']}")

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_already_cancelled"

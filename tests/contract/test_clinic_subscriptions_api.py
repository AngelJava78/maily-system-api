"""The clinic subscription charges API over HTTP: the contract of each operation (spec 010)."""

from datetime import date

from tests.helpers import Api

TENANT = "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f"
CLINIC_SUBSCRIPTION_ID = "6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70"
CALLER_TOKEN = "clinic-owner-token"
PERIOD = "2026-12-01"
CHARGE_FIELDS = {
    "id",
    "clinic_subscription_id",
    "tenant_id",
    "period",
    "amount",
    "currency",
    "payment_id",
    "payment_status",
    "checkout_url",
    "created_at",
    "updated_at",
}


def url(clinic_subscription_id: str = CLINIC_SUBSCRIPTION_ID) -> str:
    return f"/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register(api: Api, plan_id: int, *, tenant_id: str = TENANT, billing_cycle: str = "monthly") -> None:
    await api.register_clinic_subscription(
        CLINIC_SUBSCRIPTION_ID, tenant_id=tenant_id, subscription_id=plan_id, billing_cycle=billing_cycle
    )


async def grant_owner(api: Api, tenant_id: str = TENANT) -> None:
    await api.grant_clinics_caller(CALLER_TOKEN, tenant_id)
    await api.grant_caller(CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id=tenant_id)
    await api.grant_payments(CALLER_TOKEN)
    # The sync-on-read (research R8) uses the service account configured in the `api` fixture
    # ("pagos-service-token"), never the caller's own token: it must be registered too.
    await api.grant_payments("pagos-service-token", permissions=("payments:read",))


# --- historia 1: charge ---


async def test_charge_sends_the_exact_body_to_payments(api: Api):
    plan_id = await api.insert(name="Pro", monthly_price="1299.00")
    await register(api, plan_id)
    await grant_owner(api)

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == CHARGE_FIELDS
    assert body["amount"] == 129900
    assert body["payment_status"] == "pending"
    assert body["checkout_url"] is not None
    assert body["clinic_subscription_id"] == CLINIC_SUBSCRIPTION_ID
    assert body["tenant_id"] == TENANT

    create_calls = [c for c in await api.payments_calls() if c["path"] == "/api/v1/payments"]
    assert len(create_calls) == 1
    assert create_calls[0]["authorization"] == f"Bearer {CALLER_TOKEN}"


async def test_charge_of_an_annual_plan_uses_the_annual_price(api: Api):
    plan_id = await api.insert(name="Pro", annual_price="12990.00")
    await register(api, plan_id, billing_cycle="annual")
    await grant_owner(api)

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.json()["amount"] == 1299000


async def test_charge_is_idempotent_for_the_same_period(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)

    first = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))
    second = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert first.json()["payment_id"] == second.json()["payment_id"]
    create_calls = [c for c in await api.payments_calls() if c["path"] == "/api/v1/payments"]
    assert len(create_calls) == 2  # both reached Pagos; the stub kept them idempotent
    assert create_calls[0]["idempotency_key"] == create_calls[1]["idempotency_key"]


async def test_charge_an_unknown_clinic_subscription_is_not_found(api: Api):
    await grant_owner(api)  # nothing registered in the Clinics stub

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_not_found"


async def test_charge_from_another_organization_is_not_found(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await api.grant_clinics_caller(CALLER_TOKEN, TENANT)
    await api.grant_caller(
        CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id="00000000-0000-4000-8000-000000000099"
    )

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_not_found"


async def test_charge_without_an_organization_is_not_found(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await api.grant_clinics_caller(CALLER_TOKEN, TENANT)
    await api.grant_caller(CALLER_TOKEN, ["clinic_subscriptions:charge"], tenant_id=None)

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 404


async def test_charge_requires_the_plan_to_be_active(api: Api):
    plan_id = await api.insert(name="Inactivo", status_id=2)
    await register(api, plan_id)
    await grant_owner(api)

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_plan_not_active"


async def test_charge_already_approved_for_the_period_is_a_conflict(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)
    created = (await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))).json()
    await api.set_payment_status(created["payment_id"], "approved")
    await api.client.get(f"{url()}/{created['id']}")  # triggers the sync-on-read

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 409
    assert response.json()["code"] == "clinic_subscription_charge_already_approved"


async def test_charge_rejects_an_invalid_body(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)

    response = await api.client.post(url(), json={}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "period"


async def test_charge_when_clinics_is_down_changes_nothing(api: Api):
    await grant_owner(api)
    await api.clinics_fault("unavailable", operation="clinic_subscription")

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 503
    assert response.json()["code"] == "clinics_check_unavailable"


async def test_charge_when_payments_api_is_down_changes_nothing(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)
    await api.payments_fault("unavailable")

    response = await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))

    assert response.status_code == 503
    assert response.json()["code"] == "payments_unavailable"

    listed = await api.client.get(url())
    assert listed.json() == []


# --- historia 2: know the outcome ---


async def test_get_charge_syncs_a_pending_charge_and_reflects_approval(api: Api):
    plan_id = await api.insert(name="Pro", monthly_price="1299.00")
    await register(api, plan_id)
    await grant_owner(api)
    created = (await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))).json()
    await api.set_payment_status(created["payment_id"], "approved")

    response = await api.client.get(f"{url()}/{created['id']}")

    assert response.json()["payment_status"] == "approved"


async def test_get_charge_when_payments_api_is_down_keeps_the_local_status(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)
    created = (await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))).json()
    await api.payments_fault("unavailable", operation="get")

    response = await api.client.get(f"{url()}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["payment_status"] == "pending"


# --- historia 3: consult / list the history ---


async def test_list_charges_and_get_a_charge(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await grant_owner(api)
    charge = (await api.client.post(url(), json={"period": PERIOD}, headers=auth(CALLER_TOKEN))).json()

    listed = await api.client.get(url())
    single = await api.client.get(f"{url()}/{charge['id']}")

    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [charge["id"]]
    assert single.status_code == 200
    assert single.json()["id"] == charge["id"]


async def test_list_is_paginated_with_a_total_count_header(api: Api):
    plan_id = await api.insert(name="Pro")
    await register(api, plan_id)
    await api.insert_clinic_subscription_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, tenant_id=TENANT, period=date(2026, 11, 1)
    )
    await api.insert_clinic_subscription_charge(
        clinic_subscription_id=CLINIC_SUBSCRIPTION_ID, tenant_id=TENANT, period=date(2026, 12, 1),
        payment_status="approved", checkout_url=None,
    )

    response = await api.client.get(url(), params={"page": 1, "limit": 1})

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    assert len(response.json()) == 1


async def test_get_an_unknown_charge_is_not_found(api: Api):
    response = await api.client.get(f"{url()}/999")

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_charge_not_found"


async def test_list_without_the_permission_is_forbidden(api: Api):
    await api.set_permissions([])

    response = await api.client.get(url())

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"

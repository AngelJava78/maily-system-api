"""Access control of `charge_clinic_subscription` (the one `/me`-based operation, research R1).

Separate from `test_permission_coverage.py`'s generic `/check`-based battery (see the note next to
`ME_BASED_OPERATIONS` there): this operation needs the caller's own `tenant_id`, which that battery's
stub tokens never carry.
"""

from tests.helpers import Api

URL = "/api/v1/clinic-subscriptions"
TENANT = "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f"
OTHER_TENANT = "00000000-0000-4000-8000-000000000099"
TOKEN = "clinic-owner-token"


async def create_subscription(api: Api) -> dict:
    plan_id = await api.insert(name="Pro")
    response = await api.client.post(
        URL, json={"tenant_id": TENANT, "subscription_id": plan_id, "billing_cycle": "monthly"}
    )
    return response.json()


async def test_without_a_token_the_charge_asks_to_log_in(api: Api):
    created = await create_subscription(api)

    response = await api.anonymous.post(f"{URL}/{created['id']}/charges")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_an_invalid_token_is_rejected(api: Api):
    created = await create_subscription(api)

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": "Bearer not-a-registered-token"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_without_the_permission_it_is_forbidden(api: Api):
    created = await create_subscription(api)
    await api.grant_caller(TOKEN, [], tenant_id=TENANT)

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert "clinic_subscriptions:charge" in response.json()["message"]


async def test_a_pending_password_change_is_forbidden(api: Api):
    created = await create_subscription(api)
    await api.grant_caller(
        TOKEN, ["clinic_subscriptions:charge"], tenant_id=TENANT, password_change_required=True
    )

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


async def test_with_the_users_api_down_it_is_refused(api: Api):
    created = await create_subscription(api)
    await api.users_fault("unavailable", operation="me")

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "authorization_unavailable"


async def test_another_organization_is_not_found(api: Api):
    created = await create_subscription(api)
    await api.grant_caller(TOKEN, ["clinic_subscriptions:charge"], tenant_id=OTHER_TENANT)

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "clinic_subscription_not_found"


async def test_no_organization_at_all_is_not_found(api: Api):
    created = await create_subscription(api)
    await api.grant_caller(TOKEN, ["clinic_subscriptions:charge"], tenant_id=None)

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 404


async def test_the_matching_organization_with_the_permission_succeeds(api: Api):
    created = await create_subscription(api)
    await api.grant_caller(TOKEN, ["clinic_subscriptions:charge"], tenant_id=TENANT)
    await api.grant_payments(TOKEN)

    response = await api.client.post(
        f"{URL}/{created['id']}/charges", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 201
    me_calls = [c for c in await api.users_calls() if c["path"] == "/api/v1/authorization/me"]
    assert len(me_calls) == 1  # research R1: exactly one call, to /me, never /check


async def test_the_operation_declares_x_required_permission_but_no_check_dependency(api: Api):
    from src.main import create_app

    schema = create_app().openapi()
    operation = schema["paths"][f"{URL}/{{clinic_subscription_id}}/charges"]["post"]

    assert operation["x-required-permission"] == "clinic_subscriptions:charge"
    assert operation["security"] == [{"BearerAuth": []}]

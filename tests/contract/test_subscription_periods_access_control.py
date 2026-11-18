"""Who can consult the period and start the payment (spec 010, story 4; FR-001 to FR-006, FR-038, FR-040).

Principle VIII: every request asks the users API for the exact permission of its operation, with the token
as it came, before anything else; the person must be the owner of the organization, which only the
clinics API can say; and every refusal leaves the tables as they were and never reaches the payments API.
Both operations go through the same cases, so the two are protected in the same way.
"""

import uuid

import pytest

from tests.billing_support import (
    ORG_ID,
    OTHER_ORG_ID,
    PERIODS_URL,
    PERMISSIONS,
    TEST_TOKEN,
    BillingApi,
)
from tests.helpers import CLINICS_BASE_URL, PAYMENTS_BASE_URL, USERS_BASE_URL, grant

CREATED = "2026-11-20T15:30:00Z"
# Inside every error of the simulations: it must never reach the person.
INTERNAL_MARKER = "SECRETO-INTERNO"
OPERATIONS = ["consult", "pay"]
READ, WRITE = PERMISSIONS
PERMISSION_OF = {"consult": READ, "pay": WRITE}
INVALID_ID = "no-es-un-uuid"
INVALID_ID_ERRORS = [
    {"field": "organization_id", "message": "El identificador de la organización debe ser un UUID."}
]


@pytest.fixture
async def plan_id(billing_api: BillingApi) -> int:
    plan = await billing_api.add_plan()
    await billing_api.register_organization(plan, created_at=CREATED)
    return plan


async def call(api: BillingApi, operation: str, organization_id=ORG_ID, *, anonymous: bool = False, **kwargs):
    """The operation, by default as the owner; `anonymous` sends no token of its own."""
    client = api.anonymous if anonymous else api.client
    url = f"{PERIODS_URL}/{organization_id}"
    if operation == "consult":
        return await client.get(url, **kwargs)
    return await client.post(f"{url}/payments", **kwargs)


async def assert_refused(
    api: BillingApi, response, status: int, code: str, *, clinics_asked: bool | None = None
) -> dict:
    """A refusal: the expected error, no secret in it, nothing written and the payments API never asked."""
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code
    for secret in (TEST_TOKEN, INTERNAL_MARKER, USERS_BASE_URL, CLINICS_BASE_URL, PAYMENTS_BASE_URL):
        assert secret not in response.text
    assert await api.snapshot() == []
    assert await api.payments_calls() == []
    assert await api.payments() == []
    if clinics_asked is not None:
        assert bool(await api.clinics_calls()) is clinics_asked
    return body


# =============================== the token (FR-001, FR-002) ===============================


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_without_a_token_the_person_is_asked_to_log_in(billing_api: BillingApi, plan_id: int, operation: str):
    response = await call(billing_api, operation, anonymous=True)

    await assert_refused(billing_api, response, 401, "unauthenticated", clinics_asked=False)
    assert response.headers["www-authenticate"] == "Bearer"
    assert await billing_api.users_calls() == []  # there is nothing to ask the users API about


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_a_scheme_other_than_bearer_is_not_a_token(billing_api: BillingApi, plan_id: int, operation: str):
    response = await call(
        billing_api, operation, anonymous=True, headers={"Authorization": f"Basic {TEST_TOKEN}"}
    )

    await assert_refused(billing_api, response, 401, "unauthenticated", clinics_asked=False)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_an_invalid_token_is_rejected(billing_api: BillingApi, plan_id: int, operation: str):
    response = await call(
        billing_api, operation, anonymous=True, headers={"Authorization": "Bearer no-registrado"}
    )

    await assert_refused(billing_api, response, 401, "invalid_token", clinics_asked=False)
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_an_expired_token_is_rejected(billing_api: BillingApi, plan_id: int, operation: str):
    await grant(billing_api.users_stub, TEST_TOKEN, PERMISSIONS, expired=True)

    response = await call(billing_api, operation)

    await assert_refused(billing_api, response, 401, "token_expired", clinics_asked=False)
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


# =============================== the permission (FR-002) ===============================


@pytest.mark.parametrize(
    ("operation", "granted"),
    [
        ("consult", []),
        ("consult", [WRITE]),  # writing does not allow reading
        ("consult", ["subscriptions:read", "dashboard:read", "payments:read"]),
        ("pay", []),
        ("pay", [READ]),  # reading does not allow paying
        ("pay", ["subscriptions:write", "payments:write"]),
    ],
)
async def test_without_the_permission_of_the_operation_it_is_forbidden(
    billing_api: BillingApi, plan_id: int, operation: str, granted: list[str]
):
    await billing_api.set_permissions(granted)

    response = await call(billing_api, operation)

    body = await assert_refused(billing_api, response, 403, "permission_denied", clinics_asked=False)
    assert PERMISSION_OF[operation] in body["message"]  # it names the permission of THIS operation
    other = ({READ, WRITE} - {PERMISSION_OF[operation]}).pop()
    assert other not in body["message"]


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_each_operation_asks_for_exactly_its_permission_with_the_token_as_it_came(
    billing_api: BillingApi, plan_id: int, operation: str
):
    response = await call(billing_api, operation)

    assert response.status_code in (200, 201)
    calls = await billing_api.users_calls()
    assert [(c["permission"], c["authorization"]) for c in calls] == [
        (PERMISSION_OF[operation], f"Bearer {TEST_TOKEN}")
    ]


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_the_only_permission_of_the_operation_is_enough(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.set_permissions([PERMISSION_OF[operation]])

    assert (await call(billing_api, operation)).status_code in (200, 201)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_a_revoked_permission_takes_effect_on_the_next_request(
    billing_api: BillingApi, plan_id: int, operation: str
):
    assert (await call(billing_api, operation)).status_code in (200, 201)
    before = await billing_api.snapshot()

    await billing_api.set_permissions([])
    response = await call(billing_api, operation)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert await billing_api.snapshot() == before  # the refusal changed nothing


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_the_users_api_down_means_no_access_and_nobody_else_is_asked(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.users_fault("unavailable")

    response = await call(billing_api, operation)

    await assert_refused(billing_api, response, 503, "authorization_unavailable", clinics_asked=False)


# =============================== the organization (FR-003, FR-038) ===============================


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_the_organization_of_another_person_and_one_that_does_not_exist_answer_the_same(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.register_organization(plan_id, organization_id=OTHER_ORG_ID, owner_token="otra-persona")
    missing = uuid.UUID("9f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b")

    foreign = await call(billing_api, operation, OTHER_ORG_ID)
    nonexistent = await call(billing_api, operation, missing)

    for response, identifier in ((foreign, OTHER_ORG_ID), (nonexistent, missing)):
        body = await assert_refused(billing_api, response, 404, "organization_not_found", clinics_asked=True)
        assert str(identifier) in body["message"]  # it only repeats what the person sent
    # Nothing tells them apart but the identifier that the person sent: no hint of whose it is.
    assert foreign.text.replace(str(OTHER_ORG_ID), "ID") == nonexistent.text.replace(str(missing), "ID")
    assert dict(foreign.headers) == dict(nonexistent.headers)  # both identifiers have the same length


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_the_clinics_api_receives_the_token_of_the_person_untouched(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await call(billing_api, operation)

    calls = await billing_api.clinics_calls()
    assert calls and {c["authorization"] for c in calls} == {f"Bearer {TEST_TOKEN}"}


CLINICS_FAILURES = [
    "unavailable",
    "unauthorized",
    "forbidden",
    "malformed",
    "not_json",
    "redirect",
    "slow",
    "not_found_other_code",
    "missing_billing_period",
    "invalid_billing_period",
]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("mode", CLINICS_FAILURES)
async def test_when_the_organization_cannot_be_checked_the_access_fails_closed(
    billing_api: BillingApi, plan_id: int, operation: str, mode: str
):
    if mode == "slow":
        billing_api.timeouts["clinics"] = 0.2
        await billing_api.clinics_fault("slow", delay=1)
    else:
        await billing_api.clinics_fault(mode)

    response = await call(billing_api, operation)

    await assert_refused(billing_api, response, 503, "organization_check_unavailable", clinics_asked=True)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_a_failure_of_the_clinics_api_does_not_outlive_it(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.clinics_fault("unavailable")
    assert (await call(billing_api, operation)).status_code == 503

    response = await call(billing_api, operation)  # the same request, once the clinics API is back

    assert response.status_code in (200, 201)


# =============================== the order of the checks (FR-002, FR-040) ===============================


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_without_the_permission_an_invalid_identifier_is_still_forbidden_not_invalid(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.set_permissions([])

    response = await call(billing_api, operation, INVALID_ID)

    await assert_refused(billing_api, response, 403, "permission_denied", clinics_asked=False)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_without_a_token_an_invalid_identifier_still_asks_to_log_in(
    billing_api: BillingApi, plan_id: int, operation: str
):
    response = await call(billing_api, operation, INVALID_ID, anonymous=True)

    await assert_refused(billing_api, response, 401, "unauthenticated", clinics_asked=False)


@pytest.mark.parametrize("operation", OPERATIONS)
async def test_with_the_users_api_down_an_invalid_identifier_is_still_unavailable(
    billing_api: BillingApi, plan_id: int, operation: str
):
    await billing_api.users_fault("unavailable")

    response = await call(billing_api, operation, INVALID_ID)

    await assert_refused(billing_api, response, 503, "authorization_unavailable", clinics_asked=False)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("identifier", [INVALID_ID, "123", "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2", "g" * 36])
async def test_with_the_permission_an_invalid_identifier_is_a_validation_error_that_asks_nobody_else(
    billing_api: BillingApi, plan_id: int, operation: str, identifier: str
):
    response = await call(billing_api, operation, identifier)

    body = await assert_refused(billing_api, response, 422, "validation_error", clinics_asked=False)
    assert body["errors"] == INVALID_ID_ERRORS
    # It was authorized first: the permission was asked, and that is all that was asked.
    assert len(await billing_api.users_calls()) == 1


# =============================== the contract is public (FR-002) ===============================


async def test_the_contract_is_published_without_a_token_and_says_the_permission_of_each_operation(
    billing_api: BillingApi,
):
    response = await billing_api.anonymous.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    consult = paths["/api/v1/subscription-periods/{organization_id}"]["get"]
    pay = paths["/api/v1/subscription-periods/{organization_id}/payments"]["post"]
    assert (consult["x-required-permission"], pay["x-required-permission"]) == (READ, WRITE)
    assert consult["security"] == pay["security"] == [{"BearerAuth": []}]

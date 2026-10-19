"""A data source that fails: only its own value becomes `null` and the rest is returned (story 6).

A `null` means "not available". A `0` or an empty list only means that the source answered there is
nothing. The access control never relaxes. All the sources here are fakes: no real API is called.
"""

import logging

import httpx
import pytest

from tests.dashboard_support import (
    DASHBOARD_URL,
    LEAK_MARKER,
    QUERIES,
    FakeDashboardSource,
    make_clinic,
)

FIELDS = {
    "total_clinics",
    "active_clinics",
    "trial_clinics",
    "total_doctors",
    "total_patients",
    "total_users",
    "recent_clinics",
}
HEALTHY = {"total_clinics": 3, "active_clinics": 3, "trial_clinics": 0}


def healthy_source(**changes) -> FakeDashboardSource:
    values = {"clinics": [make_clinic(n) for n in range(1, 4)], "doctors": 7, "patients": 80, "users": 9}
    return FakeDashboardSource(**{**values, **changes})


async def test_a_failed_source_leaves_its_key_present_with_null_and_the_rest_intact(dashboard_api):
    dashboard_api.use_source(healthy_source(fail={"doctors_total"}))

    response = await dashboard_api.get()
    body = response.json()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(body) == FIELDS
    assert "total_doctors" in body and body["total_doctors"] is None
    assert (body["total_patients"], body["total_users"]) == (80, 9)
    assert {k: body[k] for k in HEALTHY} == HEALTHY
    assert len(body["recent_clinics"]) == 3


async def test_when_the_recent_clinics_fail_the_list_is_null_not_empty(dashboard_api):
    dashboard_api.use_source(healthy_source(fail={"recent_clinics"}))

    body = (await dashboard_api.get()).json()

    assert body["recent_clinics"] is None
    assert {k: body[k] for k in HEALTHY} == HEALTHY
    assert body["total_doctors"] == 7


async def test_when_the_clinic_counts_fail_the_three_of_them_are_null(dashboard_api):
    dashboard_api.use_source(healthy_source(fail={"clinic_counts"}))

    body = (await dashboard_api.get()).json()

    assert (body["total_clinics"], body["active_clinics"], body["trial_clinics"]) == (None, None, None)
    assert len(body["recent_clinics"]) == 3
    assert (body["total_doctors"], body["total_patients"], body["total_users"]) == (7, 80, 9)


async def test_when_every_source_fails_it_is_still_a_200_with_seven_nulls(dashboard_api):
    dashboard_api.use_source(healthy_source(fail=set(QUERIES)))

    response = await dashboard_api.get()

    assert response.status_code == 200
    assert response.json() == dict.fromkeys(FIELDS)


async def test_a_source_that_has_nothing_answers_zeros_and_an_empty_list_not_nulls(dashboard_api):
    dashboard_api.use_source(FakeDashboardSource())

    body = (await dashboard_api.get()).json()

    assert body["recent_clinics"] == []
    assert all(body[name] == 0 for name in FIELDS - {"recent_clinics"})


async def test_nothing_of_the_failed_source_leaks_to_the_client_or_the_logs(dashboard_api, caplog):
    dashboard_api.use_source(healthy_source(fail=set(QUERIES)))
    caplog.set_level(logging.DEBUG)

    response = await dashboard_api.get()

    for secret in (LEAK_MARKER, "SECRETO-INTERNO", "interno", "9000"):
        assert secret not in response.text, secret
        assert secret not in caplog.text, secret
    assert "test-token" not in caplog.text


@pytest.mark.parametrize("scenario", ["no_token", "no_permission", "users_api_down"])
async def test_the_access_control_does_not_relax_when_the_sources_fail(dashboard_api, scenario):
    dashboard_api.use_source(healthy_source(fail=set(QUERIES)))
    client, status, code = dashboard_api.anonymous, 401, "unauthenticated"
    if scenario == "no_permission":
        await dashboard_api.set_permissions([])
        client, status, code = dashboard_api.client, 403, "permission_denied"
    if scenario == "users_api_down":
        await dashboard_api.users_fault("unavailable")
        client, status, code = dashboard_api.client, 503, "authorization_unavailable"

    response = await client.get(DASHBOARD_URL)

    assert response.status_code == status
    assert response.json()["code"] == code


async def test_a_programming_error_in_a_source_is_a_generic_500_not_a_null(dashboard_api):
    dashboard_api.use_source(healthy_source(crash={"users_total"}))
    transport = httpx.ASGITransport(app=dashboard_api.app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://api.test", headers=dict(dashboard_api.client.headers)
    ) as client:
        response = await client.get(DASHBOARD_URL)

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde.",
    }
    assert "boom" not in response.text


async def test_the_shape_of_the_response_is_the_same_whatever_the_source(dashboard_api):
    shapes = []
    for source in (None, healthy_source(), healthy_source(fail=set(QUERIES)), FakeDashboardSource()):
        if source is not None:  # None = the real dummy source of phase 1
            dashboard_api.use_source(source)
        shapes.append(set((await dashboard_api.get()).json()))

    assert shapes == [FIELDS] * 4

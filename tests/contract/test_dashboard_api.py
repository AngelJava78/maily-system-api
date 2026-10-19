"""The dashboard over HTTP: `GET /api/v1/dashboard` (spec 003).

Sections: the summary (user story 1), the `limit` parameter (story 3), the configured default (story
4) and the fictitious data (story 5). The access control has its own file.
"""

import re
import uuid

import httpx
import pytest

from tests.dashboard_support import FakeDashboardSource, make_clinic

FIELDS = {
    "total_clinics",
    "active_clinics",
    "trial_clinics",
    "total_doctors",
    "total_patients",
    "total_users",
    "recent_clinics",
}
CLINIC_KEYS = {"id", "name", "created_at", "status"}
DATE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

# data-model.md section 6: the first five (the default quantity) of the fictitious set, newest first.
# Rows 4 and 5 share the instant; Dental Sonríe has the smaller id.
FIRST_FIVE = [
    ("5457da22-336d-49d8-8876-4d7edb5586ae", "Clínica Santa Aurora"),
    ("7513bda5-dd0f-48a0-9053-383ac7ec2c92", "Consultorio Del Valle"),
    ("ca8b4382-8b86-4916-b3cb-002680986de3", "Centro Médico Horizonte"),
    ("41902d77-45cb-451e-9e11-65c60e56ecf8", "Dental Sonríe"),
    ("e042d32c-3886-4777-953c-68db1d969e0e", "Clínica San Rafael"),
]


def keys_of(value) -> set[str]:
    """Every key that appears anywhere in a JSON document."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys_of(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys_of(item)}
    return set()


# --- the summary (user story 1) ---


async def test_the_summary_comes_in_one_response_that_must_not_be_cached(dashboard_api):
    response = await dashboard_api.get()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == FIELDS


async def test_the_six_indicators_and_the_five_default_clinics_are_the_fictitious_ones(dashboard_api):
    body = (await dashboard_api.get()).json()

    assert (
        body["total_clinics"],
        body["active_clinics"],
        body["trial_clinics"],
        body["total_doctors"],
        body["total_patients"],
        body["total_users"],
    ) == (12, 8, 3, 37, 1284, 52)
    assert [(c["id"], c["name"]) for c in body["recent_clinics"]] == FIRST_FIVE


async def test_every_clinic_has_exactly_its_four_fields_in_the_published_formats(dashboard_api):
    clinics = (await dashboard_api.get()).json()["recent_clinics"]

    assert len(clinics) == 5
    for clinic in clinics:
        assert set(clinic) == CLINIC_KEYS
        assert str(uuid.UUID(clinic["id"])) == clinic["id"]
        assert DATE.match(clinic["created_at"]), clinic["created_at"]
        assert set(clinic["status"]) == {"id", "name"}
        assert isinstance(clinic["status"]["id"], int)
        assert isinstance(clinic["status"]["name"], str)
    dates = [c["created_at"] for c in clinics]
    assert dates == sorted(dates, reverse=True)


async def test_two_consecutive_requests_give_the_same_body(dashboard_api):
    first = await dashboard_api.get()
    second = await dashboard_api.get()

    assert first.content == second.content


async def test_the_indicators_of_the_response_are_coherent(dashboard_api):
    body = (await dashboard_api.get("?limit=10")).json()
    recent = body["recent_clinics"]

    assert body["active_clinics"] + body["trial_clinics"] <= body["total_clinics"]
    assert len(recent) <= body["total_clinics"]
    assert sum(1 for c in recent if c["status"]["id"] == 1) <= body["active_clinics"]
    assert sum(1 for c in recent if c["status"]["id"] == 2) <= body["trial_clinics"]
    assert body["total_users"] >= body["total_doctors"]


async def test_the_response_has_only_the_keys_of_the_contract_and_nothing_personal(dashboard_api):
    body = (await dashboard_api.get("?limit=10")).json()

    assert keys_of(body) == FIELDS | CLINIC_KEYS | {"id", "name"}  # `status` repeats id and name


async def test_the_data_source_can_be_replaced_without_touching_anything_else(dashboard_api):
    source = FakeDashboardSource(
        clinics=[make_clinic(1), make_clinic(2, status_id=2)], doctors=3, patients=4, users=5
    )
    dashboard_api.use_source(source)

    body = (await dashboard_api.get()).json()

    assert (
        body["total_clinics"],
        body["active_clinics"],
        body["trial_clinics"],
        body["total_doctors"],
        body["total_patients"],
        body["total_users"],
    ) == (2, 1, 1, 3, 4, 5)
    assert [c["name"] for c in body["recent_clinics"]] == ["Clínica 2", "Clínica 1"]


# --- the `limit` parameter (user story 3) ---

# The ten most recent of the fictitious set, in the order of the API (data-model.md section 6).
TEN_IDS = [id_ for id_, _ in FIRST_FIVE] + [
    "ecb1488c-d9cf-4d3c-bb5f-dd8e9365339d",
    "820e815b-8a28-448e-bb4e-152c2f89a2ad",
    "dd5600ca-3d55-4f38-8c91-c843ec327e9c",
    "a3e85cc2-e5c9-4106-a055-5e7dcc32bf8b",
    "c9e9c89d-96b1-4aef-9373-98771c6557e6",
]
LIMIT_MESSAGE = "El parámetro «limit» debe ser un número entero mayor o igual que 1."
INVALID_LIMIT_BODY = {
    "code": "validation_error",
    "message": "Hay datos no válidos en la solicitud.",
    "errors": [{"field": "limit", "message": LIMIT_MESSAGE}],
}


def recent_ids(response) -> list[str]:
    return [clinic["id"] for clinic in response.json()["recent_clinics"]]


@pytest.mark.parametrize("limit", [1, 2, 3, 7, 10])
async def test_a_valid_limit_returns_that_many_of_the_most_recent_clinics(dashboard_api, limit):
    response = await dashboard_api.get(f"?limit={limit}")

    assert response.status_code == 200
    assert recent_ids(response) == TEN_IDS[:limit]


async def test_leading_zeros_do_not_change_the_number(dashboard_api):
    response = await dashboard_api.get("?limit=007")

    assert recent_ids(response) == TEN_IDS[:7]


@pytest.mark.parametrize("limit", ["11", "1000", "9" * 30, "9" * 5000])
async def test_more_than_ten_is_not_an_error_it_returns_ten(dashboard_api, limit):
    response = await dashboard_api.get(f"?limit={limit}")

    assert response.status_code == 200
    assert recent_ids(response) == TEN_IDS


async def test_the_clinic_with_the_smaller_id_enters_when_a_tie_is_cut(dashboard_api):
    response = await dashboard_api.get("?limit=4")

    assert recent_ids(response)[-1] == "41902d77-45cb-451e-9e11-65c60e56ecf8"  # Dental Sonríe


@pytest.mark.parametrize(
    "query",
    [
        "?limit=0",
        "?limit=00",
        "?limit=abc",
        "?limit=",
        "?limit",
        "?limit=%20",
        "?limit=5.5",
        "?limit=5.0",
        "?limit=1e1",
        "?limit=+3",
        "?limit=%2B3",
        "?limit=-1",
        "?limit=%203",
        "?limit=3%20",
        "?limit=1_0",
        "?limit=0x10",
        "?limit=%EF%BC%91",  # a full-width digit one
        "?limit=3&limit=5",
        "?limit=3&limit=abc",
        "?limit=abc&limit=3",
    ],
)
async def test_an_invalid_limit_is_rejected_with_the_catalog_body_and_nothing_else(dashboard_api, query):
    response = await dashboard_api.get(query)

    assert response.status_code == 422, response.text
    assert response.json() == INVALID_LIMIT_BODY
    assert "cache-control" not in response.headers


async def test_the_rejection_never_repeats_the_value_that_was_sent(dashboard_api):
    response = await dashboard_api.get("?limit=valor-secreto")

    assert response.status_code == 422
    assert "valor-secreto" not in response.text


async def test_unknown_parameters_are_ignored(dashboard_api):
    response = await dashboard_api.get("?page=2&offset=3&limit=2")

    assert response.status_code == 200
    assert recent_ids(response) == TEN_IDS[:2]


async def test_with_fewer_clinics_than_requested_all_come_back_without_padding(dashboard_api):
    source = FakeDashboardSource(clinics=[make_clinic(n) for n in range(1, 5)])
    dashboard_api.use_source(source)

    body = (await dashboard_api.get("?limit=10")).json()

    assert len(body["recent_clinics"]) == 4
    assert body["total_clinics"] == 4


async def test_with_no_clinics_the_list_is_empty_and_the_counts_are_zero_not_null(dashboard_api):
    dashboard_api.use_source(FakeDashboardSource())

    body = (await dashboard_api.get("?limit=10")).json()

    assert body["recent_clinics"] == []
    for name in sorted(FIELDS - {"recent_clinics"}):
        assert body[name] == 0, name
        assert type(body[name]) is int


# --- the default quantity of the configuration (user story 4) ---


def configure_default(monkeypatch, value: str | None) -> None:
    from src.config import get_dashboard_settings

    if value is not None:
        monkeypatch.setenv("DASHBOARD_RECENT_CLINICS_LIMIT", value)
    get_dashboard_settings.cache_clear()  # as if the service had just started


async def test_without_the_variable_the_default_is_five(dashboard_api, monkeypatch):
    configure_default(monkeypatch, None)

    assert len(recent_ids(await dashboard_api.get())) == 5


@pytest.mark.parametrize("value", [3, 5, 10])
async def test_the_configured_value_rules_when_no_limit_is_sent(dashboard_api, monkeypatch, value):
    configure_default(monkeypatch, str(value))

    assert recent_ids(await dashboard_api.get()) == TEN_IDS[:value]


async def test_an_empty_variable_counts_as_not_configured(dashboard_api, monkeypatch):
    configure_default(monkeypatch, "")

    assert len(recent_ids(await dashboard_api.get())) == 5


async def test_the_limit_that_is_sent_wins_over_the_configured_default(dashboard_api, monkeypatch):
    configure_default(monkeypatch, "3")

    assert len(recent_ids(await dashboard_api.get("?limit=7"))) == 7
    assert len(recent_ids(await dashboard_api.get("?limit=1000"))) == 10


async def test_the_default_only_applies_when_no_limit_is_sent(dashboard_api, monkeypatch):
    configure_default(monkeypatch, "10")

    assert len(recent_ids(await dashboard_api.get("?limit=2"))) == 2
    assert len(recent_ids(await dashboard_api.get())) == 10


# --- the fictitious data (user story 5) ---


async def test_a_restart_gives_exactly_the_same_answer(dashboard_api):
    from src.config import get_dashboard_settings
    from src.main import create_app

    before = await dashboard_api.get("?limit=10")
    get_dashboard_settings.cache_clear()  # what a restart does
    restarted = create_app()
    restarted.dependency_overrides = dict(dashboard_api.app.dependency_overrides)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted),
        base_url="http://api.test",
        headers=dict(dashboard_api.client.headers),
    ) as client:
        after = await client.get("/api/v1/dashboard?limit=10")

    assert before.status_code == after.status_code == 200
    assert before.content == after.content


async def test_the_ten_clinics_have_valid_distinct_uuids(dashboard_api):
    ids = recent_ids(await dashboard_api.get("?limit=10"))

    assert len(ids) == len(set(ids)) == 10
    assert all(str(uuid.UUID(i)) == i for i in ids)


async def test_both_statuses_and_a_tie_can_be_checked_from_the_outside(dashboard_api):
    clinics = (await dashboard_api.get("?limit=10")).json()["recent_clinics"]
    statuses = {(c["status"]["id"], c["status"]["name"]) for c in clinics}
    instants = [c["created_at"] for c in clinics]
    tied = [c for c in clinics if instants.count(c["created_at"]) == 2]

    assert statuses == {(1, "Activa"), (2, "En prueba")}
    assert len(tied) == 2
    assert [c["id"] for c in tied] == sorted(c["id"] for c in tied)


async def test_the_dashboard_never_opens_a_database_session(dashboard_api):
    from src.database import get_session

    async def forbidden():
        pytest.fail("the dashboard must not use the database")
        yield  # pragma: no cover

    dashboard_api.app.dependency_overrides[get_session] = forbidden

    assert (await dashboard_api.get()).status_code == 200

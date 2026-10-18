"""The clinics API is secondary: its failures never take the subscriptions down (FR-009, SC-005)."""

import logging

import pytest

from tests.helpers import TEST_TOKEN, Api

URL = "/api/v1/subscriptions"
FAILURE_MODES = [
    "unavailable",
    "unauthorized",
    "forbidden",
    "malformed",
    "negative_count",
    "duplicate_id",
    "unrequested_id",
    "not_json",
    "redirect",
    "slow",
]


async def prepare_failure(api: Api, mode: str) -> None:
    if mode == "slow":
        api.timeouts["clinics"] = 0.2
        await api.clinics_fault("slow", delay=1)
    else:
        await api.clinics_fault(mode)


# --- US1: the catalog ---


@pytest.mark.parametrize("mode", FAILURE_MODES)
async def test_the_catalog_still_answers_when_the_clinics_api_fails(api: Api, mode: str):
    await api.insert(name="Una")
    await api.insert(name="Otra")
    await api.counts({1: 3, 2: 1})
    await prepare_failure(api, mode)

    response = await api.client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert [s["name"] for s in body] == ["Una", "Otra"]
    assert [s["clinics_count"] for s in body] == [None, None]  # unavailable, never a made-up zero


async def test_with_a_healthy_clinics_api_the_counts_are_real(api: Api):
    await api.insert(name="Una")
    await api.insert(name="Otra")
    await api.counts({1: 3})

    body = (await api.client.get(URL)).json()

    assert [s["clinics_count"] for s in body] == [3, 0]


async def test_the_token_of_the_person_reaches_the_clinics_api_untouched(api: Api):
    await api.insert(name="Una")

    await api.client.get(URL)

    assert (await api.clinics_calls())[0]["authorization"] == f"Bearer {TEST_TOKEN}"


# --- US7: deleting is the only operation that refuses when the clinics cannot be checked ---


@pytest.mark.parametrize("mode", FAILURE_MODES)
async def test_deleting_is_refused_and_nothing_is_deleted_when_the_clinics_cannot_be_checked(
    api: Api, mode: str
):
    subscription_id = await api.insert(name="Pro")
    await prepare_failure(api, mode)

    response = await api.client.delete(f"{URL}/{subscription_id}")

    assert response.status_code == 503
    assert response.json() == {
        "code": "clinics_check_unavailable",
        "message": (
            "No se pudo comprobar si la suscripción con el identificador 1 tiene clínicas "
            "asignadas. No se eliminó; inténtelo de nuevo más tarde."
        ),
    }
    assert await api.fetch_all("SELECT status_id FROM subscriptions") == [(1,)]  # SC-009: 0 deleted


@pytest.mark.parametrize("mode", ["not_json", "unavailable", "malformed"])
async def test_the_refused_deletion_reveals_nothing_of_the_clinics_api(
    api: Api, mode: str, caplog
):
    caplog.set_level(logging.DEBUG)
    subscription_id = await api.insert(name="Pro")
    await api.clinics_fault(mode)

    response = await api.client.delete(f"{URL}/{subscription_id}")

    assert "SECRETO-INTERNO" not in response.text and "clinics-api.test" not in response.text
    assert "SECRETO-INTERNO" not in caplog.text


@pytest.mark.parametrize("mode", ["not_json", "unavailable", "malformed"])
async def test_nothing_of_the_clinics_api_reaches_the_client_nor_the_logs(
    api: Api, mode: str, caplog
):
    caplog.set_level(logging.DEBUG)
    await api.insert(name="Una")
    await api.clinics_fault(mode)

    response = await api.client.get(URL)

    assert "SECRETO-INTERNO" not in response.text
    assert "clinics-api.test" not in response.text
    assert "SECRETO-INTERNO" not in caplog.text
    assert TEST_TOKEN not in caplog.text

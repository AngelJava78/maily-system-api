"""The subscriptions API over HTTP: the contract of each operation (spec 001-subscriptions-api)."""

from datetime import UTC, datetime, timedelta

from tests.helpers import Api

URL = "/api/v1/subscriptions"
FIELDS = {
    "id",
    "name",
    "description",
    "monthly_price",
    "features",
    "status",
    "clinics_count",
    "created_at",
    "updated_at",
}
MOMENT = datetime(2026, 1, 1, tzinfo=UTC)


# --- US1: the catalog ---


async def test_the_catalog_is_a_json_array_with_exactly_the_fields_of_the_contract(api: Api):
    await api.insert(
        name="Básico",
        monthly_price="1500",
        features=["1 consultorio", "Hasta 3 usuarios"],
    )
    await api.counts({1: 2})

    response = await api.client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list) and len(body) == 1
    subscription = body[0]
    assert set(subscription) == FIELDS
    assert subscription["name"] == "Básico"
    assert subscription["description"] is None
    assert subscription["monthly_price"] == "1500.00"  # a string with two decimals
    assert subscription["features"] == ["1 consultorio", "Hasta 3 usuarios"]
    assert subscription["status"] == {"id": 1, "name": "Activa"}
    assert subscription["clinics_count"] == 2
    assert datetime.fromisoformat(subscription["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(subscription["updated_at"]).tzinfo is not None


async def test_the_catalog_has_active_inactive_and_blocked_but_never_deleted(api: Api):
    for name, status in (("Activa", 1), ("Inactiva", 2), ("Bloqueada", 3), ("Eliminada", 4)):
        await api.insert(name=name, status_id=status)

    body = (await api.client.get(URL)).json()

    assert [(s["name"], s["status"]) for s in body] == [
        ("Activa", {"id": 1, "name": "Activa"}),
        ("Inactiva", {"id": 2, "name": "Inactiva"}),
        ("Bloqueada", {"id": 3, "name": "Bloqueada"}),
    ]


async def test_the_order_is_creation_date_then_id_and_stable_between_queries(api: Api):
    await api.insert(name="Tercera", created_at=MOMENT + timedelta(days=2))
    await api.insert(name="Primera", created_at=MOMENT)
    await api.insert(name="Segunda A", created_at=MOMENT + timedelta(days=1))
    await api.insert(name="Segunda B", created_at=MOMENT + timedelta(days=1))

    first = [s["name"] for s in (await api.client.get(URL)).json()]
    second = [s["name"] for s in (await api.client.get(URL)).json()]

    assert first == ["Primera", "Segunda A", "Segunda B", "Tercera"]
    assert second == first


async def test_an_empty_catalog_is_an_empty_list_not_an_error(api: Api):
    response = await api.client.get(URL)

    assert response.status_code == 200
    assert response.json() == []


async def test_there_is_no_sign_of_pagination(api: Api):
    await api.insert(name="Una")

    response = await api.client.get(URL, params={"page": 1, "page_size": 1})

    assert isinstance(response.json(), list)
    assert not {"link", "x-total-count", "x-total-pages"} & set(response.headers)


async def test_the_clinics_api_is_asked_once_without_filter_and_missing_ones_count_zero(api: Api):
    await api.insert(name="Con clínicas")
    await api.insert(name="Sin clínicas")
    await api.counts({1: 2})

    body = (await api.client.get(URL)).json()

    assert [s["clinics_count"] for s in body] == [2, 0]
    calls = await api.clinics_calls()
    assert len(calls) == 1
    assert calls[0]["subscription_ids"] == []


async def test_the_catalog_asks_the_users_api_for_the_read_permission(api: Api):
    await api.client.get(URL)

    assert [call["permission"] for call in await api.users_calls()] == ["subscriptions:read"]


async def test_without_the_read_permission_the_catalog_is_forbidden(api: Api):
    await api.insert(name="Visible")
    await api.set_permissions(["subscriptions:write", "subscriptions:update"])

    response = await api.client.get(URL)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert await api.clinics_calls() == []


async def test_without_a_token_the_catalog_asks_to_log_in(api: Api):
    response = await api.anonymous.get(URL)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


# --- US3: create ---

PRO = {
    "name": "Pro",
    "monthly_price": 4500,
    "features": ["Hasta 5 consultorios", "Usuarios ilimitados"],
}


async def test_creating_a_subscription_answers_201_with_everything_the_contract_promises(api: Api):
    response = await api.client.post(URL, json=PRO)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert body["status"] == {"id": 1, "name": "Activa"}
    assert body["monthly_price"] == "4500.00"
    assert body["clinics_count"] == 0
    assert body["description"] is None
    assert body["features"] == ["Hasta 5 consultorios", "Usuarios ilimitados"]
    assert response.headers["Location"] == f"{URL}/{body['id']}"


async def test_creating_does_not_ask_the_clinics_api_and_the_new_one_is_in_the_catalog(api: Api):
    await api.client.post(URL, json=PRO)

    assert await api.clinics_calls() == []
    names = [s["name"] for s in (await api.client.get(URL)).json()]
    assert names == ["Pro"]


async def test_only_the_required_data_is_enough(api: Api):
    response = await api.client.post(URL, json={"name": "Legacy full", "monthly_price": 0})

    assert response.status_code == 201
    assert response.json()["features"] == []
    assert response.json()["monthly_price"] == "0.00"


async def test_the_texts_are_saved_without_surrounding_spaces(api: Api):
    response = await api.client.post(
        URL,
        json={"name": "  Pro  ", "description": "  Para clínicas ", "monthly_price": 1, "features": [" Uno "]},
    )

    body = response.json()
    assert (body["name"], body["description"], body["features"]) == ("Pro", "Para clínicas", ["Uno"])


async def test_a_name_that_only_differs_in_capitals_conflicts(api: Api):
    await api.client.post(URL, json=PRO)

    response = await api.client.post(URL, json={**PRO, "name": "pro"})

    assert response.status_code == 409
    assert response.json() == {
        "code": "subscription_name_already_exists",
        "message": "Ya existe una suscripción con el nombre «pro».",
    }


async def test_the_name_of_a_deleted_subscription_is_free(api: Api):
    await api.insert(name="Solo", status_id=4)

    response = await api.client.post(URL, json={"name": "Solo", "monthly_price": 900})

    assert response.status_code == 201


async def test_the_name_of_an_inactive_subscription_stays_reserved(api: Api):
    await api.insert(name="Legacy", status_id=2)

    response = await api.client.post(URL, json={"name": "Legacy", "monthly_price": 1})

    assert response.status_code == 409


async def test_fields_that_cannot_be_sent_reject_the_whole_request(api: Api):
    for field, value in (("status", 1), ("id", 9), ("clinics_count", 3)):
        response = await api.client.post(URL, json={**PRO, field: value})

        assert response.status_code == 422, field
        assert response.json()["errors"] == [
            {"field": field, "message": f"El campo «{field}» no está permitido."}
        ]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_every_invalid_field_gets_its_own_message_and_none_repeats_the_value(api: Api):
    response = await api.client.post(
        URL, json={"name": "", "monthly_price": -5, "features": [""]}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert {e["field"] for e in body["errors"]} == {"name", "monthly_price", "features"}
    assert "-5" not in response.text.replace("99 999 999,99", "")


async def test_a_price_with_three_decimals_is_rejected(api: Api):
    response = await api.client.post(URL, json={"name": "Pro", "monthly_price": "4500.555"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "monthly_price"


async def test_without_the_write_permission_nothing_is_created(api: Api):
    await api.set_permissions(["subscriptions:read"])

    response = await api.client.post(URL, json=PRO)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


# --- US4: get one ---

NOT_FOUND_42 = {
    "code": "subscription_not_found",
    "message": "No se encontró la suscripción con el identificador 42.",
}


async def test_a_current_subscription_is_returned_with_the_same_detail_as_the_catalog(api: Api):
    subscription_id = await api.insert(
        name="Pro", monthly_price="4500", features=["Uno"], description="Para clínicas"
    )
    await api.counts({subscription_id: 3})

    response = await api.client.get(f"{URL}/{subscription_id}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == FIELDS
    assert (body["name"], body["monthly_price"], body["clinics_count"]) == ("Pro", "4500.00", 3)
    assert body == (await api.client.get(URL)).json()[0]


async def test_active_inactive_and_blocked_are_all_returned_with_their_status(api: Api):
    ids = {
        status: await api.insert(name=f"Estatus {status}", status_id=status) for status in (1, 2, 3)
    }

    for status, subscription_id in ids.items():
        body = (await api.client.get(f"{URL}/{subscription_id}")).json()
        assert body["status"]["id"] == status


async def test_the_clinics_api_is_asked_once_for_that_subscription_only(api: Api):
    first = await api.insert(name="Una")
    await api.insert(name="Otra")

    await api.client.get(f"{URL}/{first}")

    calls = await api.clinics_calls()
    assert len(calls) == 1
    assert calls[0]["subscription_ids"] == [first]


async def test_a_deleted_subscription_is_not_found_and_clinics_are_not_asked(api: Api):
    deleted = await api.insert(name="Eliminada", status_id=4)

    response = await api.client.get(f"{URL}/{deleted}")

    assert response.status_code == 404
    assert response.json()["code"] == "subscription_not_found"
    assert await api.clinics_calls() == []


async def test_a_missing_subscription_is_not_found_with_its_identifier_in_the_message(api: Api):
    response = await api.client.get(f"{URL}/42")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_42


async def test_an_identifier_above_int4_is_simply_not_found(api: Api):
    response = await api.client.get(f"{URL}/{2_147_483_648}")

    assert response.status_code == 404
    assert response.json()["code"] == "subscription_not_found"


async def test_an_identifier_that_is_not_a_positive_integer_is_a_validation_error(api: Api):
    for bad in ("0", "-1", "abc"):
        response = await api.client.get(f"{URL}/{bad}")

        assert response.status_code == 422, bad
        assert response.json()["errors"] == [
            {
                "field": "subscription_id",
                "message": "El identificador de la suscripción debe ser un número entero positivo.",
            }
        ]


async def test_a_subscription_is_returned_even_if_the_clinics_api_is_down(api: Api):
    subscription_id = await api.insert(name="Una")
    await api.clinics_fault("unavailable")

    response = await api.client.get(f"{URL}/{subscription_id}")

    assert response.status_code == 200
    assert response.json()["clinics_count"] is None


async def test_without_the_read_permission_even_a_missing_subscription_is_forbidden(api: Api):
    await api.set_permissions(["subscriptions:write"])

    response = await api.client.get(f"{URL}/42")

    assert response.status_code == 403  # it is not revealed whether it exists


# --- US5: update ---


async def test_updating_only_the_price_keeps_everything_else_and_moves_the_modification_date(
    api: Api,
):
    subscription_id = await api.insert(
        name="Pro", monthly_price="4500", description="Para clínicas", features=["Uno"]
    )
    before = (await api.client.get(f"{URL}/{subscription_id}")).json()

    response = await api.client.patch(
        f"{URL}/{subscription_id}", json={"monthly_price": "4700.00"}
    )

    assert response.status_code == 200
    after = response.json()
    assert after["monthly_price"] == "4700.00"
    for field in ("id", "name", "description", "features", "status", "created_at"):
        assert after[field] == before[field], field
    assert datetime.fromisoformat(after["updated_at"]) > datetime.fromisoformat(before["updated_at"])


async def test_a_name_can_change_its_capitals_but_not_take_the_one_of_another(api: Api):
    pro = await api.insert(name="Pro")
    await api.insert(name="Básico")

    renamed = await api.client.patch(f"{URL}/{pro}", json={"name": "PRO"})
    taken = await api.client.patch(f"{URL}/{pro}", json={"name": "básico"})

    assert renamed.status_code == 200 and renamed.json()["name"] == "PRO"
    assert taken.status_code == 409
    assert taken.json() == {
        "code": "subscription_name_already_exists",
        "message": "Ya existe una suscripción con el nombre «básico».",
    }


async def test_an_empty_update_is_rejected(api: Api):
    subscription_id = await api.insert(name="Pro")

    response = await api.client.patch(f"{URL}/{subscription_id}", json={})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "body", "message": "Hay que enviar al menos un dato para modificar."}
    ]


async def test_the_fields_of_the_system_cannot_be_updated(api: Api):
    subscription_id = await api.insert(name="Pro")

    for field, value in (
        ("status_id", 2),
        ("status", {"id": 2}),
        ("id", 9),
        ("clinics_count", 3),
        ("created_at", "2026-01-01T00:00:00Z"),
    ):
        response = await api.client.patch(f"{URL}/{subscription_id}", json={field: value})

        assert response.status_code == 422, field
        assert response.json()["errors"] == [
            {"field": field, "message": f"El campo «{field}» no está permitido."}
        ]
    assert (await api.fetch_all("SELECT status_id FROM subscriptions")) == [(1,)]


async def test_the_fields_that_cannot_be_null_are_reported_and_nothing_changes(api: Api):
    subscription_id = await api.insert(name="Pro", monthly_price="100", features=["Uno"])
    expected = {
        "name": "El nombre de la suscripción es obligatorio.",
        "monthly_price": "El precio mensual es obligatorio.",
        "features": "Lo que incluye la suscripción debe ser una lista de textos.",
    }

    for field, message in expected.items():
        response = await api.client.patch(f"{URL}/{subscription_id}", json={field: None})

        assert response.status_code == 422, field  # never a 500
        assert response.json()["errors"] == [{"field": field, "message": message}]
    assert (await api.fetch_all("SELECT name, features FROM subscriptions")) == [("Pro", ["Uno"])]


async def test_an_empty_or_null_description_clears_it_and_an_empty_list_empties_the_features(
    api: Api,
):
    subscription_id = await api.insert(name="Pro", description="Antes", features=["Uno"])

    for description in ("", None):
        await api.client.patch(f"{URL}/{subscription_id}", json={"description": "Otra"})
        response = await api.client.patch(f"{URL}/{subscription_id}", json={"description": description})
        assert response.json()["description"] is None

    cleared = await api.client.patch(f"{URL}/{subscription_id}", json={"features": []})
    assert cleared.json()["features"] == []


async def test_a_deleted_or_missing_subscription_cannot_be_updated(api: Api):
    deleted = await api.insert(name="Eliminada", status_id=4)

    for subscription_id in (deleted, 42):
        response = await api.client.patch(f"{URL}/{subscription_id}", json={"name": "Nuevo"})

        assert response.status_code == 404
        assert response.json()["code"] == "subscription_not_found"


async def test_the_update_answers_even_if_the_clinics_api_is_down(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.clinics_fault("unavailable")

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"name": "Nuevo"})

    assert response.status_code == 200
    assert response.json()["clinics_count"] is None
    assert response.json()["name"] == "Nuevo"


async def test_the_update_returns_the_clinics_count_asked_after_writing(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.counts({subscription_id: 6})

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"name": "Nuevo"})

    assert response.json()["clinics_count"] == 6
    assert (await api.clinics_calls())[0]["subscription_ids"] == [subscription_id]


async def test_without_the_update_permission_nothing_changes(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.set_permissions(["subscriptions:read", "subscriptions:write"])

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"name": "Nuevo"})

    assert response.status_code == 403
    assert (await api.fetch_all("SELECT name FROM subscriptions")) == [("Pro",)]


# --- US6: change the status ---


def status_url(subscription_id: int) -> str:
    return f"{URL}/{subscription_id}/status"


async def test_the_status_goes_active_inactive_blocked_active_and_the_catalog_shows_it(api: Api):
    subscription_id = await api.insert(name="Pro")

    for status_id, name in ((2, "Inactiva"), (3, "Bloqueada"), (1, "Activa")):
        response = await api.client.patch(status_url(subscription_id), json={"status_id": status_id})

        assert response.status_code == 200
        assert response.json()["status"] == {"id": status_id, "name": name}
        listed = (await api.client.get(URL)).json()
        assert [s["status"]["id"] for s in listed] == [status_id]


async def test_asking_for_the_status_it_already_has_is_a_conflict(api: Api):
    subscription_id = await api.insert(name="Pro", status_id=2)

    response = await api.client.patch(status_url(subscription_id), json={"status_id": 2})

    assert response.status_code == 409
    assert response.json() == {
        "code": "subscription_status_unchanged",
        "message": "La suscripción con el identificador 1 ya tiene el estatus Inactiva.",
    }


async def test_deleted_and_unknown_statuses_and_wrong_types_are_validation_errors(api: Api):
    subscription_id = await api.insert(name="Pro")

    for body in ({"status_id": 4}, {"status_id": 99}, {"status_id": True}, {"status_id": "2"},
                 {"status_id": None}, {}):
        response = await api.client.patch(status_url(subscription_id), json=body)

        assert response.status_code == 422, body
        assert response.json()["errors"][0]["field"] == "status_id", body
    assert (await api.fetch_all("SELECT status_id FROM subscriptions")) == [(1,)]  # never moved


async def test_an_extra_field_in_the_status_change_is_rejected(api: Api):
    subscription_id = await api.insert(name="Pro")

    response = await api.client.patch(status_url(subscription_id), json={"status_id": 2, "name": "x"})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "name", "message": "El campo «name» no está permitido."}
    ]


async def test_a_deleted_or_missing_subscription_has_no_status_to_change(api: Api):
    deleted = await api.insert(name="Eliminada", status_id=4)

    for subscription_id in (deleted, 42):
        response = await api.client.patch(status_url(subscription_id), json={"status_id": 1})

        assert response.status_code == 404
        assert response.json()["code"] == "subscription_not_found"


async def test_a_subscription_with_clinics_can_be_inactivated_and_blocked_without_asking_first(
    api: Api,
):
    subscription_id = await api.insert(name="Pro")
    await api.counts({subscription_id: 3})

    for status_id in (2, 3):
        response = await api.client.patch(status_url(subscription_id), json={"status_id": status_id})

        assert response.status_code == 200
        assert response.json()["clinics_count"] == 3
    calls = await api.clinics_calls()
    assert len(calls) == 2  # one per answer, made only after the change was written


async def test_the_status_change_succeeds_even_if_the_clinics_api_is_down(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.clinics_fault("unavailable")

    response = await api.client.patch(status_url(subscription_id), json={"status_id": 2})

    assert response.status_code == 200
    assert response.json()["clinics_count"] is None


async def test_the_status_change_moves_the_modification_date(api: Api):
    subscription_id = await api.insert(name="Pro")
    before = (await api.client.get(f"{URL}/{subscription_id}")).json()["updated_at"]

    after = (await api.client.patch(status_url(subscription_id), json={"status_id": 3})).json()

    assert datetime.fromisoformat(after["updated_at"]) > datetime.fromisoformat(before)


async def test_without_the_update_permission_the_status_does_not_change(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.set_permissions(["subscriptions:read", "subscriptions:delete"])

    response = await api.client.patch(status_url(subscription_id), json={"status_id": 2})

    assert response.status_code == 403
    assert (await api.fetch_all("SELECT status_id FROM subscriptions")) == [(1,)]


# --- US7: delete ---


async def test_deleting_a_subscription_without_clinics_answers_204_and_it_disappears(api: Api):
    subscription_id = await api.insert(name="Pro")

    response = await api.client.delete(f"{URL}/{subscription_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert (await api.client.get(URL)).json() == []
    assert (await api.client.get(f"{URL}/{subscription_id}")).status_code == 404
    assert (await api.client.patch(f"{URL}/{subscription_id}", json={"name": "X"})).status_code == 404
    assert (
        await api.client.patch(status_url(subscription_id), json={"status_id": 1})
    ).status_code == 404
    assert (await api.client.delete(f"{URL}/{subscription_id}")).status_code == 404
    # The row and its data are kept, with the Deleted status.
    assert await api.fetch_all("SELECT name, status_id FROM subscriptions") == [("Pro", 4)]


async def test_after_deleting_the_name_can_be_used_again(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.client.delete(f"{URL}/{subscription_id}")

    response = await api.client.post(URL, json={"name": "Pro", "monthly_price": 1})

    assert response.status_code == 201


async def test_a_subscription_with_clinics_cannot_be_deleted(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.counts({subscription_id: 3})

    response = await api.client.delete(f"{URL}/{subscription_id}")

    assert response.status_code == 409
    assert response.json() == {
        "code": "subscription_has_clinics",
        "message": (
            "No se puede eliminar la suscripción con el identificador 1 porque tiene clínicas "
            "asignadas."
        ),
    }
    still_there = (await api.client.get(f"{URL}/{subscription_id}")).json()
    assert still_there["status"] == {"id": 1, "name": "Activa"}


async def test_deleting_asks_the_clinics_api_for_that_subscription_with_the_token_of_the_person(
    api: Api,
):
    subscription_id = await api.insert(name="Pro")

    await api.client.delete(f"{URL}/{subscription_id}")

    calls = await api.clinics_calls()
    assert len(calls) == 1
    assert calls[0]["subscription_ids"] == [subscription_id]
    assert calls[0]["authorization"] == "Bearer test-token"


async def test_deleting_a_missing_or_deleted_subscription_is_not_found_without_asking_clinics(
    api: Api,
):
    deleted = await api.insert(name="Eliminada", status_id=4)

    for subscription_id in (deleted, 42):
        response = await api.client.delete(f"{URL}/{subscription_id}")

        assert response.status_code == 404
        assert response.json()["code"] == "subscription_not_found"
    assert await api.clinics_calls() == []


async def test_deleting_with_a_bad_identifier_is_a_validation_error(api: Api):
    response = await api.client.delete(f"{URL}/abc")

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "subscription_id"


async def test_without_the_delete_permission_nothing_is_deleted(api: Api):
    subscription_id = await api.insert(name="Pro")
    await api.set_permissions(["subscriptions:read", "subscriptions:update"])

    response = await api.client.delete(f"{URL}/{subscription_id}")

    assert response.status_code == 403
    assert (await api.fetch_all("SELECT status_id FROM subscriptions")) == [(1,)]
    assert await api.clinics_calls() == []

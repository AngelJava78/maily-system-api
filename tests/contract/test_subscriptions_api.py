"""The subscriptions API over HTTP: the contract of each operation (spec 004-correct-subscriptions-api)."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.helpers import Api

URL = "/api/v1/subscriptions"
FIELDS = {
    "id",
    "name",
    "description",
    "subscription_type",
    "monthly_price",
    "annual_price",
    "trial_days",
    "self_service",
    "module_keys",
    "other_features",
    "consulting_rooms_limit",
    "doctors_limit",
    "assistants_limit",
    "new_patients_per_year_limit",
    "clinics_limit",
    "status",
    "clinics_count",
    "created_at",
    "updated_at",
}
MOMENT = datetime(2026, 1, 1, tzinfo=UTC)

# The real clinic-module keys the stub seeds by default (tests/stubs/users_api/app.py); no
# dependencies between them any more (spec 009).
BASE_LIMITS = {
    "annual_price": 12990,
    "consulting_rooms_limit": 2,
    "doctors_limit": 3,
    "assistants_limit": 2,
    "new_patients_per_year_limit": 15000,
}
PRO = {
    "name": "Profesional",
    "subscription_type_id": 1,
    "monthly_price": 1299,
    "trial_days": 14,
    "self_service": True,
    "module_keys": ["appointments", "reminders", "prescriptions"],
    "other_features": ["Soporte por correo y WhatsApp", "Capacitación inicial en línea"],
    "clinics_limit": 1,
    **BASE_LIMITS,
}


def minimal_body(name: str, monthly_price: float = 1, **extra) -> dict:
    """The smallest valid `SubscriptionCreate` body (no modules beyond `patients`)."""
    return {
        "name": name,
        "subscription_type_id": extra.pop("subscription_type_id", 1),
        "monthly_price": monthly_price,
        "annual_price": extra.pop("annual_price", 10),
        "consulting_rooms_limit": extra.pop("consulting_rooms_limit", 1),
        "doctors_limit": extra.pop("doctors_limit", 1),
        "assistants_limit": extra.pop("assistants_limit", 1),
        "new_patients_per_year_limit": extra.pop("new_patients_per_year_limit", 1),
        "clinics_limit": extra.pop("clinics_limit", 1),
        **extra,
    }


# --- US1: the catalog ---


async def test_the_catalog_is_a_json_array_with_exactly_the_fields_of_the_contract(api: Api):
    await api.insert(
        name="Básico",
        monthly_price="1500",
        annual_price="15000",
        trial_days=14,
        self_service=True,
        module_keys=["patients", "scheduling"],
        other_features=["Soporte por correo"],
        consulting_rooms_limit=1,
        doctors_limit=1,
        assistants_limit=1,
        new_patients_per_year_limit=5000,
    )
    await api.counts({1: 2})

    response = await api.client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list) and len(body) == 1
    subscription = body[0]
    assert set(subscription) == FIELDS
    assert subscription["name"] == "Básico"
    assert subscription["subscription_type"] == {"id": 1, "name": "Individual"}
    assert subscription["description"] is None
    assert subscription["monthly_price"] == "1500.00"  # a string with two decimals
    assert subscription["annual_price"] == "15000.00"
    assert subscription["trial_days"] == 14
    assert subscription["self_service"] is True
    assert subscription["module_keys"] == ["patients", "scheduling"]
    assert subscription["other_features"] == ["Soporte por correo"]
    assert subscription["consulting_rooms_limit"] == 1
    assert subscription["new_patients_per_year_limit"] == 5000
    assert subscription["clinics_limit"] == 1
    assert subscription["status"] == {"id": 1, "name": "Activa"}
    assert subscription["clinics_count"] == 2
    assert datetime.fromisoformat(subscription["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(subscription["updated_at"]).tzinfo is not None


async def test_excluding_a_module_does_not_exclude_what_depends_on_it(api: Api):
    # "Avanzado" del mockup: todos los módulos salvo billing (ya no hay dependencias entre ellos,
    # spec 009; esto solo prueba que excluir uno no arrastra ningún otro).
    await api.insert(
        name="Avanzado",
        module_keys=[
            "patients",
            "scheduling",
            "reminders",
            "clinical_records",
            "clinical_record_templates",
            "prescriptions",
            "finance",
            "reports",
        ],
    )

    body = (await api.client.get(URL)).json()[0]

    assert "billing" not in body["module_keys"]
    assert "finance" in body["module_keys"]


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


async def test_the_catalog_asks_the_users_api_for_the_read_permission_but_not_for_modules(api: Api):
    await api.insert(name="Una", module_keys=["patients", "scheduling"])

    await api.client.get(URL)

    users_calls = await api.users_calls()
    assert [call["permission"] for call in users_calls] == ["subscriptions:read"]
    assert not [call for call in users_calls if call["path"] == "/api/v1/modules"]


async def test_the_catalog_shows_each_subscriptions_own_type_without_mixing_them_up(api: Api):
    await api.insert(name="Solo", subscription_type_id=1)
    await api.insert(name="Corporativo", subscription_type_id=2)

    body = (await api.client.get(URL)).json()

    assert [(s["name"], s["subscription_type"]) for s in body] == [
        ("Solo", {"id": 1, "name": "Individual"}),
        ("Corporativo", {"id": 2, "name": "Empresarial"}),
    ]


async def test_getting_by_id_shows_the_correct_type_for_each(api: Api):
    individual = await api.insert(name="Solo", subscription_type_id=1)
    enterprise = await api.insert(name="Corporativo", subscription_type_id=2)

    first = (await api.client.get(f"{URL}/{individual}")).json()
    second = (await api.client.get(f"{URL}/{enterprise}")).json()

    assert (first["subscription_type"], second["subscription_type"]) == (
        {"id": 1, "name": "Individual"},
        {"id": 2, "name": "Empresarial"},
    )


async def test_the_catalog_shows_each_subscriptions_own_clinics_limit_without_mixing_them_up(
    api: Api,
):
    await api.insert(name="Solo", subscription_type_id=1, clinics_limit=1)
    await api.insert(name="Corporativo", subscription_type_id=2, clinics_limit=40)

    body = (await api.client.get(URL)).json()

    assert [(s["name"], s["clinics_limit"]) for s in body] == [
        ("Solo", 1),
        ("Corporativo", 40),
    ]
    for subscription in body:
        for field in (
            "consulting_rooms_limit",
            "doctors_limit",
            "assistants_limit",
            "new_patients_per_year_limit",
        ):
            assert field in subscription


async def test_getting_by_id_shows_the_correct_clinics_limit_for_each(api: Api):
    individual = await api.insert(name="Solo", subscription_type_id=1, clinics_limit=1)
    enterprise = await api.insert(name="Corporativo", subscription_type_id=2, clinics_limit=40)

    first = (await api.client.get(f"{URL}/{individual}")).json()
    second = (await api.client.get(f"{URL}/{enterprise}")).json()

    assert (first["clinics_limit"], second["clinics_limit"]) == (1, 40)


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


async def test_creating_a_subscription_answers_201_with_everything_the_contract_promises(api: Api):
    response = await api.client.post(URL, json=PRO)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert body["status"] == {"id": 1, "name": "Activa"}
    assert body["monthly_price"] == "1299.00"
    assert body["annual_price"] == "12990.00"
    assert body["trial_days"] == 14
    assert body["self_service"] is True
    assert body["module_keys"] == ["appointments", "patients", "prescriptions", "reminders"]
    assert body["other_features"] == ["Soporte por correo y WhatsApp", "Capacitación inicial en línea"]
    assert body["consulting_rooms_limit"] == 2
    assert body["clinics_limit"] == 1
    assert body["clinics_count"] == 0
    assert body["description"] is None
    assert response.headers["Location"] == f"{URL}/{body['id']}"


async def test_creating_does_not_ask_the_clinics_api_and_the_new_one_is_in_the_catalog(api: Api):
    await api.client.post(URL, json=PRO)

    assert await api.clinics_calls() == []
    names = [s["name"] for s in (await api.client.get(URL)).json()]
    assert names == ["Profesional"]


async def test_creating_with_each_subscription_type_id_is_accepted_and_shown(api: Api):
    individual = await api.client.post(URL, json=minimal_body("Solo", 900, subscription_type_id=1))
    enterprise = await api.client.post(URL, json=minimal_body("Corporativo", 5000, subscription_type_id=2))

    assert individual.status_code == enterprise.status_code == 201
    assert individual.json()["subscription_type"] == {"id": 1, "name": "Individual"}
    assert enterprise.json()["subscription_type"] == {"id": 2, "name": "Empresarial"}


async def test_creating_without_a_subscription_type_id_is_rejected_and_creates_nothing(api: Api):
    body = minimal_body("Sin tipo", 1)
    del body["subscription_type_id"]

    response = await api.client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "subscription_type_id",
            "message": "El tipo de suscripción es obligatorio y debe ser un número entero positivo.",
        }
    ]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


@pytest.mark.parametrize("value", ["", "Individual", "premium", 0, -1, 1.5, True])
async def test_creating_with_a_malformed_subscription_type_id_is_rejected(api: Api, value):
    response = await api.client.post(URL, json=minimal_body("Inválido", 1, subscription_type_id=value))

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "subscription_type_id",
            "message": "El tipo de suscripción es obligatorio y debe ser un número entero positivo.",
        }
    ]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_creating_with_a_subscription_type_id_that_does_not_exist_is_rejected(api: Api):
    response = await api.client.post(URL, json=minimal_body("Inexistente", 1, subscription_type_id=99))

    assert response.status_code == 422
    assert response.json() == {
        "code": "subscription_type_not_found",
        "message": "No se encontró el tipo de suscripción con el identificador 99.",
    }
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_creating_an_individual_with_clinics_limit_one_is_accepted(api: Api):
    response = await api.client.post(
        URL, json=minimal_body("Solo", 1, subscription_type_id=1, clinics_limit=1)
    )

    assert response.status_code == 201
    assert response.json()["clinics_limit"] == 1


@pytest.mark.parametrize("value", [0, 2, 50, 100])
async def test_creating_an_individual_with_a_clinics_limit_other_than_one_is_rejected(
    api: Api, value
):
    response = await api.client.post(
        URL, json=minimal_body("Individual mal", 1, subscription_type_id=1, clinics_limit=value)
    )

    assert response.status_code == 422
    # 0 fails the plain 1-100 range first; 2/50/100 fail the Individual-only cross rule.
    expected_message = (
        "El límite de clínicas debe ser un número entero de 1 a 100."
        if value == 0
        else "Una suscripción Individual debe tener límite de clínicas igual a 1."
    )
    assert response.json()["errors"] == [{"field": "clinics_limit", "message": expected_message}]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


@pytest.mark.parametrize("value", [1, 50, 100])
async def test_creating_an_enterprise_with_clinics_limit_in_its_range_is_accepted(api: Api, value):
    response = await api.client.post(
        URL, json=minimal_body("Corporativo", 1, subscription_type_id=2, clinics_limit=value)
    )

    assert response.status_code == 201
    assert response.json()["clinics_limit"] == value


@pytest.mark.parametrize("value", [0, 101])
async def test_creating_an_enterprise_with_a_clinics_limit_outside_its_range_is_rejected(
    api: Api, value
):
    response = await api.client.post(
        URL, json=minimal_body("Fuera de rango", 1, subscription_type_id=2, clinics_limit=value)
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "clinics_limit",
            "message": "El límite de clínicas debe ser un número entero de 1 a 100.",
        }
    ]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_creating_without_a_clinics_limit_is_rejected_and_creates_nothing(api: Api):
    body = minimal_body("Sin limite", 1)
    del body["clinics_limit"]

    response = await api.client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "clinics_limit",
            "message": "El límite de clínicas debe ser un número entero de 1 a 100.",
        }
    ]
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_only_the_required_data_is_enough(api: Api):
    response = await api.client.post(URL, json=minimal_body("Legacy full", 0))

    assert response.status_code == 201
    body = response.json()
    assert body["other_features"] == []
    assert body["monthly_price"] == "0.00"
    assert body["trial_days"] == 0
    assert body["self_service"] is False
    assert body["module_keys"] == ["patients"]  # always included, even unrequested


async def test_patients_is_always_included_even_if_the_request_excludes_it(api: Api):
    response = await api.client.post(
        URL, json=minimal_body("Esencial", 1, module_keys=["reminders"])
    )

    assert response.json()["module_keys"] == ["patients", "reminders"]


async def test_the_texts_are_saved_without_surrounding_spaces(api: Api):
    response = await api.client.post(
        URL,
        json=minimal_body(
            "  Pro  ", 1, description="  Para clínicas ", other_features=[" Uno "]
        ),
    )

    body = response.json()
    assert (body["name"], body["description"], body["other_features"]) == ("Pro", "Para clínicas", ["Uno"])


async def test_a_name_that_only_differs_in_capitals_conflicts(api: Api):
    await api.client.post(URL, json=PRO)

    response = await api.client.post(URL, json={**PRO, "name": "profesional"})

    assert response.status_code == 409
    assert response.json() == {
        "code": "subscription_name_already_exists",
        "message": "Ya existe una suscripción con el nombre «profesional».",
    }


async def test_the_name_of_a_deleted_subscription_is_free(api: Api):
    await api.insert(name="Solo", status_id=4)

    response = await api.client.post(URL, json=minimal_body("Solo", 900))

    assert response.status_code == 201


async def test_the_name_of_an_inactive_subscription_stays_reserved(api: Api):
    await api.insert(name="Legacy", status_id=2)

    response = await api.client.post(URL, json=minimal_body("Legacy", 1))

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
        URL, json=minimal_body("", -5, other_features=[""])
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert {e["field"] for e in body["errors"]} == {"name", "monthly_price", "other_features"}
    assert "-5" not in response.text.replace("99 999 999,99", "")


async def test_a_price_with_three_decimals_is_rejected(api: Api):
    response = await api.client.post(URL, json=minimal_body("Pro", "4500.555"))

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "monthly_price"


async def test_without_the_annual_price_or_a_limit_the_request_is_rejected(api: Api):
    body = minimal_body("Sin anual", 1)
    del body["annual_price"]

    response = await api.client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "annual_price"


async def test_a_module_without_what_used_to_be_its_prerequisite_is_accepted(api: Api):
    response = await api.client.post(URL, json=minimal_body("Con factura", 1, module_keys=["billing"]))

    assert response.status_code == 201
    assert response.json()["module_keys"] == ["billing", "patients"]


async def test_creating_saturno_with_all_eighteen_active_modules_is_accepted(api: Api):
    saturno = minimal_body(
        "Saturno",
        1500,
        subscription_type_id=2,
        module_keys=[
            "appointments",
            "billing",
            "clinics",
            "consulting_rooms",
            "expenses",
            "finance",
            "incomes",
            "overview",
            "patient_diagnoses",
            "prescriptions",
            "reminders",
            "reports",
            "schedule",
            "services",
            "staff",
            "templates",
            "vital_signs",
        ],
        clinics_limit=10,
    )

    response = await api.client.post(URL, json=saturno)

    assert response.status_code == 201
    assert response.json()["module_keys"] == [
        "appointments",
        "billing",
        "clinics",
        "consulting_rooms",
        "expenses",
        "finance",
        "incomes",
        "overview",
        "patient_diagnoses",
        "patients",
        "prescriptions",
        "reminders",
        "reports",
        "schedule",
        "services",
        "staff",
        "templates",
        "vital_signs",
    ]


@pytest.mark.parametrize(
    "module_key",
    [
        "no_existe",
        "scheduling",  # retired from the real catalog (US2's example in spec.md)
    ],
)
async def test_an_unrecognised_module_is_a_validation_error(api: Api, module_key: str):
    response = await api.client.post(
        URL, json=minimal_body("Inventado", 1, module_keys=[module_key])
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "subscription_module_not_found",
        "message": f"La API de usuarios no reconoce el módulo «{module_key}» como un módulo de clínica vigente.",
    }


async def test_when_the_users_api_cannot_validate_modules_nothing_is_created(api: Api):
    await api.users_fault("unavailable", operation="modules")

    response = await api.client.post(
        URL, json=minimal_body("Falla", 1, module_keys=["scheduling"])
    )

    assert response.status_code == 503
    assert response.json()["code"] == "module_check_unavailable"
    assert await api.fetch_all("SELECT id FROM subscriptions") == []


async def test_creating_without_extra_modules_does_not_ask_the_users_api_for_them(api: Api):
    await api.client.post(URL, json=minimal_body("Solo pacientes", 1))

    assert not [c for c in await api.users_calls() if c["path"] == "/api/v1/modules"]


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
        name="Pro", monthly_price="4500", other_features=["Uno"], description="Para clínicas"
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


async def test_get_does_not_ask_the_users_api_for_modules(api: Api):
    subscription_id = await api.insert(name="Una", module_keys=["patients", "scheduling"])

    await api.client.get(f"{URL}/{subscription_id}")

    assert not [c for c in await api.users_calls() if c["path"] == "/api/v1/modules"]


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


async def test_updating_only_the_annual_price_keeps_everything_else_and_moves_the_modification_date(
    api: Api,
):
    subscription_id = await api.insert(
        name="Pro", monthly_price="4500", description="Para clínicas", other_features=["Uno"]
    )
    before = (await api.client.get(f"{URL}/{subscription_id}")).json()

    response = await api.client.patch(
        f"{URL}/{subscription_id}", json={"annual_price": "47000.00"}
    )

    assert response.status_code == 200
    after = response.json()
    assert after["annual_price"] == "47000.00"
    for field in ("id", "name", "description", "monthly_price", "other_features", "status", "created_at"):
        assert after[field] == before[field], field
    assert datetime.fromisoformat(after["updated_at"]) > datetime.fromisoformat(before["updated_at"])


async def test_trying_to_change_the_subscription_type_id_rejects_the_whole_update(api: Api):
    subscription_id = await api.insert(name="Pro", subscription_type_id=1, monthly_price="900")

    response = await api.client.patch(
        f"{URL}/{subscription_id}",
        json={"subscription_type_id": 2, "monthly_price": "950.00"},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "subscription_type_id",
            "message": "El tipo de suscripción no puede modificarse una vez creada.",
        }
    ]
    unchanged = (await api.client.get(f"{URL}/{subscription_id}")).json()
    assert (unchanged["subscription_type"], unchanged["monthly_price"]) == (
        {"id": 1, "name": "Individual"},
        "900.00",
    )


async def test_sending_the_same_subscription_type_id_it_already_has_is_still_rejected(api: Api):
    subscription_id = await api.insert(name="Pro", subscription_type_id=1)

    response = await api.client.patch(
        f"{URL}/{subscription_id}", json={"subscription_type_id": 1}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "subscription_type_id"


async def test_updating_without_the_subscription_type_id_field_works_normally_and_the_type_stays(api: Api):
    subscription_id = await api.insert(name="Pro", subscription_type_id=2)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"monthly_price": "950.00"})

    assert response.status_code == 200
    assert response.json()["subscription_type"] == {"id": 2, "name": "Empresarial"}


# --- US3 (007-add-clinics-limit): clinics_limit depends on the type when updating ---


async def test_trying_to_change_the_clinics_limit_of_an_individual_rejects_the_whole_update(api: Api):
    subscription_id = await api.insert(
        name="Solo", subscription_type_id=1, clinics_limit=1, monthly_price="900"
    )

    response = await api.client.patch(
        f"{URL}/{subscription_id}",
        json={"clinics_limit": 50, "monthly_price": "950.00"},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "clinics_limit",
            "message": "El límite de clínicas no puede modificarse en una suscripción Individual.",
        }
    ]
    unchanged = (await api.client.get(f"{URL}/{subscription_id}")).json()
    assert (unchanged["clinics_limit"], unchanged["monthly_price"]) == (1, "900.00")


async def test_sending_the_same_clinics_limit_an_individual_already_has_is_still_rejected(api: Api):
    subscription_id = await api.insert(name="Solo", subscription_type_id=1, clinics_limit=1)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"clinics_limit": 1})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "clinics_limit"


async def test_updating_an_enterprises_clinics_limit_within_its_range_works(api: Api):
    subscription_id = await api.insert(name="Corporativo", subscription_type_id=2, clinics_limit=10)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"clinics_limit": 80})

    assert response.status_code == 200
    assert response.json()["clinics_limit"] == 80


@pytest.mark.parametrize("value", [0, 101])
async def test_updating_an_enterprises_clinics_limit_outside_its_range_is_rejected(api: Api, value):
    subscription_id = await api.insert(name="Corporativo", subscription_type_id=2, clinics_limit=10)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"clinics_limit": value})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "clinics_limit",
            "message": "El límite de clínicas debe ser un número entero de 1 a 100.",
        }
    ]
    unchanged = (await api.client.get(f"{URL}/{subscription_id}")).json()
    assert unchanged["clinics_limit"] == 10


async def test_updating_without_the_clinics_limit_field_works_normally_and_it_stays(api: Api):
    subscription_id = await api.insert(name="Pro", subscription_type_id=2, clinics_limit=15)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"monthly_price": "950.00"})

    assert response.status_code == 200
    assert response.json()["clinics_limit"] == 15


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
    subscription_id = await api.insert(name="Pro", monthly_price="100", other_features=["Uno"])
    expected = {
        "name": "El nombre de la suscripción es obligatorio.",
        "monthly_price": "El precio mensual es obligatorio.",
        "annual_price": "El precio anual es obligatorio.",
        "trial_days": "Los días de prueba deben ser un número entero de 0 a 3650.",
        "self_service": "El autoconsumo debe ser verdadero o falso.",
        "module_keys": "Cada módulo debe identificarse con una clave válida.",
        "other_features": "Lo que incluye la suscripción debe ser una lista de textos.",
        "consulting_rooms_limit": "El límite de consultorios debe ser un número entero de 0 a 1 000 000.",
    }

    for field, message in expected.items():
        response = await api.client.patch(f"{URL}/{subscription_id}", json={field: None})

        assert response.status_code == 422, field  # never a 500
        assert response.json()["errors"] == [{"field": field, "message": message}]
    assert (await api.fetch_all("SELECT name, other_features FROM subscriptions")) == [("Pro", ["Uno"])]


async def test_an_empty_or_null_description_clears_it_and_an_empty_list_empties_other_features(
    api: Api,
):
    subscription_id = await api.insert(name="Pro", description="Antes", other_features=["Uno"])

    for description in ("", None):
        await api.client.patch(f"{URL}/{subscription_id}", json={"description": "Otra"})
        response = await api.client.patch(f"{URL}/{subscription_id}", json={"description": description})
        assert response.json()["description"] is None

    cleared = await api.client.patch(f"{URL}/{subscription_id}", json={"other_features": []})
    assert cleared.json()["other_features"] == []


async def test_updating_modules_replaces_the_whole_set_but_keeps_patients(api: Api):
    subscription_id = await api.insert(name="Pro", module_keys=["patients", "scheduling", "reminders"])

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"module_keys": ["finance"]})

    assert response.status_code == 200
    assert response.json()["module_keys"] == ["finance", "patients"]


async def test_updating_to_a_module_without_what_used_to_be_its_prerequisite_is_accepted(
    api: Api,
):
    subscription_id = await api.insert(name="Pro", module_keys=["patients", "reminders"])

    response = await api.client.patch(
        f"{URL}/{subscription_id}", json={"module_keys": ["billing"]}
    )

    assert response.status_code == 200
    assert response.json()["module_keys"] == ["billing", "patients"]


async def test_updating_modules_of_a_deleted_subscription_is_not_found_before_asking_the_users_api(
    api: Api,
):
    deleted = await api.insert(name="Eliminada", status_id=4)

    response = await api.client.patch(
        f"{URL}/{deleted}", json={"module_keys": ["scheduling"]}
    )

    assert response.status_code == 404
    assert not [c for c in await api.users_calls() if c["path"] == "/api/v1/modules"]


async def test_updating_without_module_keys_does_not_ask_the_users_api(api: Api):
    subscription_id = await api.insert(name="Pro")

    await api.client.patch(f"{URL}/{subscription_id}", json={"name": "Nuevo"})

    assert not [c for c in await api.users_calls() if c["path"] == "/api/v1/modules"]


async def test_lowering_a_limit_is_always_accepted(api: Api):
    subscription_id = await api.insert(name="Pro", doctors_limit=3)

    response = await api.client.patch(f"{URL}/{subscription_id}", json={"doctors_limit": 1})

    assert response.status_code == 200
    assert response.json()["doctors_limit"] == 1


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


# --- US6: change the status (modules, prices and limits are untouched) ---


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


async def test_changing_the_status_keeps_the_modules_prices_and_limits_unchanged(api: Api):
    subscription_id = await api.insert(
        name="Pro",
        monthly_price="1299",
        annual_price="12990",
        module_keys=["patients", "scheduling"],
        consulting_rooms_limit=2,
    )
    before = (await api.client.get(f"{URL}/{subscription_id}")).json()

    after = (
        await api.client.patch(status_url(subscription_id), json={"status_id": 2})
    ).json()

    for field in ("monthly_price", "annual_price", "module_keys", "consulting_rooms_limit"):
        assert after[field] == before[field], field


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

    response = await api.client.post(URL, json=minimal_body("Pro", 1))

    assert response.status_code == 201


async def test_deleting_does_not_touch_modules_prices_or_limits(api: Api):
    subscription_id = await api.insert(
        name="Pro", module_keys=["patients", "finance", "billing"], consulting_rooms_limit=4
    )

    await api.client.delete(f"{URL}/{subscription_id}")

    modules = await api.fetch_all(
        "SELECT module_key FROM subscription_modules WHERE subscription_id = :id ORDER BY module_key",
        id=subscription_id,
    )
    assert modules == [("billing",), ("finance",), ("patients",)]
    limits = await api.fetch_all(
        "SELECT consulting_rooms_limit FROM subscriptions WHERE id = :id", id=subscription_id
    )
    assert limits == [(4,)]


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

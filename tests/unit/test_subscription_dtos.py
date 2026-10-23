"""DTOs of the subscriptions: the rules of every field, quoted from data-model.md and the spec."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.error_handlers import translate_validation_errors

# --- SubscriptionRead: serialises an ORM-shaped object (FR-008) ---


def subscription_row(**overrides) -> SimpleNamespace:
    """A stand-in for `Subscription` with the attributes `SubscriptionRead.model_validate` reads."""
    base = dict(
        id=1,
        name="Profesional",
        description=None,
        monthly_price=Decimal("1299"),
        annual_price=Decimal("12990"),
        trial_days=14,
        self_service=True,
        module_keys=["patients", "scheduling"],
        other_features=["Soporte por correo"],
        consulting_rooms_limit=2,
        doctors_limit=3,
        assistants_limit=2,
        new_patients_per_year_limit=15000,
        status=SimpleNamespace(id=1, name="Activa"),
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
        updated_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    return SimpleNamespace(**{**base, **overrides})


def test_monthly_and_annual_price_serialise_with_exactly_two_decimals():
    read = SubscriptionRead.model_validate(subscription_row(monthly_price=Decimal("1299")))
    read.clinics_count = None

    dumped = read.model_dump(mode="json")

    assert (dumped["monthly_price"], dumped["annual_price"]) == ("1299.00", "12990.00")


def test_module_keys_and_other_features_are_exposed_as_given():
    read = SubscriptionRead.model_validate(
        subscription_row(module_keys=["finance", "patients"], other_features=["Uno", "Dos"])
    )

    assert read.module_keys == ["finance", "patients"]
    assert read.other_features == ["Uno", "Dos"]


def test_every_new_field_round_trips():
    read = SubscriptionRead.model_validate(subscription_row())

    assert (read.trial_days, read.self_service) == (14, True)
    assert (read.consulting_rooms_limit, read.doctors_limit) == (2, 3)
    assert (read.assistants_limit, read.new_patients_per_year_limit) == (2, 15000)


BASE_LIMITS = {
    "annual_price": 1000,
    "consulting_rooms_limit": 1,
    "doctors_limit": 1,
    "assistants_limit": 1,
    "new_patients_per_year_limit": 100,
}


def create(**values) -> SubscriptionCreate:
    return SubscriptionCreate.model_validate({"name": "Pro", "monthly_price": 100, **BASE_LIMITS, **values})


def messages_of(payload: dict) -> list[tuple[str, str]]:
    """The (field, message) pairs the API would answer for an invalid JSON body."""
    import json

    with pytest.raises(ValidationError) as info:
        SubscriptionCreate.model_validate_json(json.dumps(payload))
    errors = [{**e, "loc": ("body", *e["loc"])} for e in info.value.errors()]
    return [(e.field, e.message) for e in translate_validation_errors(errors, "subscriptions")]


# --- SubscriptionCreate: name ---


def test_the_name_is_trimmed():
    assert create(name="  Pro  ").name == "Pro"


def test_the_name_may_have_up_to_one_hundred_characters():
    assert create(name="n" * 100).name == "n" * 100


@pytest.mark.parametrize("name", ["n" * 101, "", "   ", None, 5])
def test_an_invalid_name_is_rejected(name):
    with pytest.raises(ValidationError):
        create(name=name)


def test_the_name_is_required():
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate({"monthly_price": 1, **BASE_LIMITS})


def test_the_name_length_is_counted_after_trimming():
    assert create(name=" " + "n" * 100 + " ").name == "n" * 100


# --- description ---


def test_the_description_is_optional():
    assert create().description is None


def test_a_description_may_have_up_to_five_hundred_characters():
    assert create(description="d" * 500).description == "d" * 500


def test_a_longer_description_is_rejected():
    with pytest.raises(ValidationError):
        create(description="d" * 501)


@pytest.mark.parametrize("description", ["", "   ", None])
def test_an_empty_description_means_no_description(description):
    assert create(description=description).description is None


# --- monthly_price and annual_price: Decimal with max_digits=10, decimal_places=2, ge=0 ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('4500', Decimal("4500")),
        ('4500.5', Decimal("4500.5")),
        ('"4500.50"', Decimal("4500.50")),
        ('0', Decimal("0")),
        ('99999999.99', Decimal("99999999.99")),
    ],
)
def test_valid_prices_are_accepted_exactly(raw, expected):
    body = f'{{"name": "Pro", "monthly_price": {raw}, "annual_price": {raw}, ' + (
        '"consulting_rooms_limit": 1, "doctors_limit": 1, "assistants_limit": 1, '
        '"new_patients_per_year_limit": 1}'
    )
    data = SubscriptionCreate.model_validate_json(body)

    assert data.monthly_price == expected
    assert data.annual_price == expected


@pytest.mark.parametrize("raw", ["-1", "4500.555", "100000000", '"abc"', "null", "true"])
def test_invalid_prices_are_rejected(raw):
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate_json(f'{{"name": "Pro", "monthly_price": {raw}, "annual_price": 1}}')


@pytest.mark.parametrize("raw", ["-1", "4500.555", "100000000", '"abc"', "null", "true"])
def test_invalid_annual_prices_are_rejected(raw):
    with pytest.raises(ValidationError):
        create(annual_price=raw) if raw != "null" else create(annual_price=None)


def test_the_monthly_price_is_required():
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate({"name": "Pro", **BASE_LIMITS})


def test_the_annual_price_is_required():
    without_annual = {k: v for k, v in BASE_LIMITS.items() if k != "annual_price"}
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate({"name": "Pro", "monthly_price": 100, **without_annual})


def test_the_annual_price_does_not_need_to_follow_any_ratio_with_the_monthly_price():
    # research R1 (Clarifications P1): independent, no enforced proportion.
    assert create(monthly_price=100, annual_price=100000).annual_price == Decimal("100000")
    assert create(monthly_price=100, annual_price=1).annual_price == Decimal("1")


# --- trial_days: int, 0 to 3650, defaults to 0 ---


def test_trial_days_defaults_to_zero():
    assert create().trial_days == 0


@pytest.mark.parametrize("value", [0, 1, 3650])
def test_valid_trial_days_are_accepted(value):
    assert create(trial_days=value).trial_days == value


@pytest.mark.parametrize("value", [-1, 3651, 1.5])
def test_invalid_trial_days_are_rejected(value):
    with pytest.raises(ValidationError):
        create(trial_days=value)


# --- self_service: bool, defaults to False ---


def test_self_service_defaults_to_false():
    assert create().self_service is False


def test_self_service_true_is_accepted():
    assert create(self_service=True).self_service is True


# --- module_keys: up to 50 keys matching ^[a-z][a-z0-9_]*$, defaults to [] ---


def test_module_keys_default_to_an_empty_list():
    assert create().module_keys == []


def test_module_keys_are_trimmed():
    assert create(module_keys=["  scheduling "]).module_keys == ["scheduling"]


def test_fifty_module_keys_are_accepted():
    assert len(create(module_keys=[f"m{n}" for n in range(50)]).module_keys) == 50


@pytest.mark.parametrize(
    "module_keys",
    [[f"m{n}" for n in range(51)], ["Scheduling"], ["123abc"], ["a b"], [1], "abc", None],
    ids=["51-items", "uppercase", "starts-with-digit", "has-space", "not-text", "not-a-list", "null"],
)
def test_invalid_module_keys_are_rejected(module_keys):
    with pytest.raises(ValidationError):
        create(module_keys=module_keys)


# --- other_features: at most 20 items of 1 to 150 characters, a list, optional ---


def test_the_other_features_default_to_an_empty_list():
    assert create().other_features == []


def test_the_other_features_keep_their_order_and_are_trimmed():
    assert create(other_features=["  Uno ", "Dos", "Tres"]).other_features == ["Uno", "Dos", "Tres"]


def test_twenty_other_features_are_accepted():
    assert len(create(other_features=[f"f{n}" for n in range(20)]).other_features) == 20


@pytest.mark.parametrize(
    "other_features",
    [[f"f{n}" for n in range(21)], [""], ["  "], ["e" * 151], [1], "abc", None],
    ids=["21-items", "empty", "blank", "151-chars", "not-text", "not-a-list", "null"],
)
def test_invalid_other_features_are_rejected(other_features):
    with pytest.raises(ValidationError):
        create(other_features=other_features)


def test_an_element_of_one_hundred_fifty_characters_is_accepted():
    assert create(other_features=["e" * 150]).other_features == ["e" * 150]


def test_an_other_features_null_or_text_is_reported_as_not_being_a_list_not_as_an_element_problem():
    expected = [("other_features", "Lo que incluye la suscripción debe ser una lista de textos.")]

    assert messages_of({"name": "Pro", "monthly_price": 1, **BASE_LIMITS, "other_features": None}) == expected
    assert messages_of({"name": "Pro", "monthly_price": 1, **BASE_LIMITS, "other_features": "abc"}) == expected


# --- the four clinic limits: int, 0 to 1,000,000, required ---


@pytest.mark.parametrize(
    "field", ["consulting_rooms_limit", "doctors_limit", "assistants_limit", "new_patients_per_year_limit"]
)
def test_each_limit_is_required(field):
    without = {k: v for k, v in BASE_LIMITS.items() if k != field}
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate({"name": "Pro", "monthly_price": 1, **without})


@pytest.mark.parametrize(
    "field", ["consulting_rooms_limit", "doctors_limit", "assistants_limit", "new_patients_per_year_limit"]
)
@pytest.mark.parametrize("value", [-1, 1_000_001, 1.5])
def test_each_limit_rejects_a_value_outside_its_range(field, value):
    with pytest.raises(ValidationError):
        create(**{field: value})


@pytest.mark.parametrize(
    "field", ["consulting_rooms_limit", "doctors_limit", "assistants_limit", "new_patients_per_year_limit"]
)
def test_each_limit_accepts_zero_and_the_maximum(field):
    assert getattr(create(**{field: 0}), field) == 0
    assert getattr(create(**{field: 1_000_000}), field) == 1_000_000


# --- fields that cannot be sent ---


@pytest.mark.parametrize(
    "field", ["id", "status", "status_id", "clinics_count", "created_at", "updated_at"]
)
def test_the_fields_of_the_system_are_rejected_as_not_allowed(field):
    found = messages_of({"name": "Pro", "monthly_price": 1, **BASE_LIMITS, field: 1})

    assert found == [(field, f"El campo «{field}» no está permitido.")]


def test_the_error_messages_never_repeat_the_value_received():
    found = messages_of(
        {"name": "Pro", "monthly_price": -1, **BASE_LIMITS, "password": "valor-secreto-9"}
    )

    assert all("valor-secreto-9" not in message for _, message in found)


# --- SubscriptionUpdate: the same rules, every field optional, at least one required ---


def update(**values) -> SubscriptionUpdate:
    return SubscriptionUpdate.model_validate(values)


def update_messages(payload: dict) -> list[tuple[str, str]]:
    import json

    with pytest.raises(ValidationError) as info:
        SubscriptionUpdate.model_validate_json(json.dumps(payload))
    errors = [{**e, "loc": ("body", *e["loc"])} for e in info.value.errors()]
    return [(e.field, e.message) for e in translate_validation_errors(errors, "subscriptions")]


def test_an_update_may_send_a_single_field():
    data = update(monthly_price="4700")

    assert data.model_dump(exclude_unset=True) == {"monthly_price": Decimal("4700")}


def test_an_empty_update_is_rejected_on_the_body():
    assert update_messages({}) == [("body", "Hay que enviar al menos un dato para modificar.")]


def test_an_update_has_the_same_limits_as_a_creation():
    assert update(name="  Pro  ").name == "Pro"
    assert update(name="n" * 100).name == "n" * 100
    for payload in (
        {"name": "n" * 101},
        {"name": "  "},
        {"description": "d" * 501},
        {"monthly_price": -1},
        {"monthly_price": "4500.555"},
        {"monthly_price": 100000000},
        {"annual_price": -1},
        {"trial_days": -1},
        {"trial_days": 3651},
        {"module_keys": ["Uppercase"]},
        {"module_keys": [f"m{n}" for n in range(51)]},
        {"other_features": [f"f{n}" for n in range(21)]},
        {"other_features": ["e" * 151]},
        {"other_features": [""]},
        {"consulting_rooms_limit": -1},
        {"consulting_rooms_limit": 1_000_001},
    ):
        with pytest.raises(ValidationError):
            update(**payload)


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"name": None}, "name", "El nombre de la suscripción es obligatorio."),
        ({"monthly_price": None}, "monthly_price", "El precio mensual es obligatorio."),
        ({"annual_price": None}, "annual_price", "El precio anual es obligatorio."),
        (
            {"trial_days": None},
            "trial_days",
            "Los días de prueba deben ser un número entero de 0 a 3650.",
        ),
        ({"self_service": None}, "self_service", "El autoconsumo debe ser verdadero o falso."),
        (
            {"module_keys": None},
            "module_keys",
            "Cada módulo debe identificarse con una clave válida.",
        ),
        (
            {"other_features": None},
            "other_features",
            "Lo que incluye la suscripción debe ser una lista de textos.",
        ),
        (
            {"consulting_rooms_limit": None},
            "consulting_rooms_limit",
            "El límite de consultorios debe ser un número entero de 0 a 1 000 000.",
        ),
        (
            {"doctors_limit": None},
            "doctors_limit",
            "El límite de doctores debe ser un número entero de 0 a 1 000 000.",
        ),
        (
            {"assistants_limit": None},
            "assistants_limit",
            "El límite de asistentes debe ser un número entero de 0 a 1 000 000.",
        ),
        (
            {"new_patients_per_year_limit": None},
            "new_patients_per_year_limit",
            "El límite de pacientes nuevos al año debe ser un número entero de 0 a 1 000 000.",
        ),
    ],
)
def test_the_fields_that_cannot_be_null_say_so_when_they_are_sent_as_null(payload, field, message):
    # Every field above is NOT NULL in the database: a null must never get that far.
    assert update_messages(payload) == [(field, message)]


@pytest.mark.parametrize("description", [None, "", "   "])
def test_a_null_or_empty_description_clears_it_and_the_change_is_kept(description):
    data = update(description=description)

    assert data.model_dump(exclude_unset=True) == {"description": None}


def test_an_empty_list_of_other_features_empties_the_list():
    assert update(other_features=[]).model_dump(exclude_unset=True) == {"other_features": []}


def test_an_empty_list_of_module_keys_is_accepted_patients_is_added_later_by_the_service():
    assert update(module_keys=[]).model_dump(exclude_unset=True) == {"module_keys": []}


@pytest.mark.parametrize(
    "field", ["id", "status", "status_id", "clinics_count", "created_at", "updated_at"]
)
def test_an_update_rejects_the_fields_of_the_system(field):
    assert update_messages({field: 1}) == [(field, f"El campo «{field}» no está permitido.")]


# --- SubscriptionStatusChange: a strict integer that must be 1, 2 or 3 ---

STATUS_REQUIRED = "El estatus es obligatorio y debe ser un número entero."
STATUS_NOT_ALLOWED = "El estatus debe ser uno de los que admite esta operación (1, 2 o 3)."


def status_messages(raw_json: str) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as info:
        SubscriptionStatusChange.model_validate_json(raw_json)
    errors = [{**e, "loc": ("body", *e["loc"])} for e in info.value.errors()]
    return [(e.field, e.message) for e in translate_validation_errors(errors, "subscriptions")]


@pytest.mark.parametrize("status_id", [1, 2, 3])
def test_the_three_manageable_statuses_are_valid(status_id):
    data = SubscriptionStatusChange.model_validate_json(f'{{"status_id": {status_id}}}')

    assert data.status_id == status_id


@pytest.mark.parametrize("raw", ["4", "0", "99", "-1"])
def test_a_status_outside_one_to_three_is_not_allowed_in_this_operation(raw):
    assert status_messages(f'{{"status_id": {raw}}}') == [("status_id", STATUS_NOT_ALLOWED)]


@pytest.mark.parametrize("raw", ['"2"', "2.5", "true", "false", '"x"', "null", "[]"])
def test_anything_that_is_not_an_integer_is_reported_as_such_and_true_is_never_one(raw):
    # `Literal[1, 2, 3]` would have accepted `true` as 1: the integer is strict.
    assert status_messages(f'{{"status_id": {raw}}}') == [("status_id", STATUS_REQUIRED)]


def test_a_missing_status_is_reported():
    assert status_messages("{}") == [("status_id", STATUS_REQUIRED)]


def test_an_extra_field_is_not_allowed():
    assert status_messages('{"status_id": 2, "name": "x"}') == [
        ("name", "El campo «name» no está permitido.")
    ]

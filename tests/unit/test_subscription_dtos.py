"""DTOs of the subscriptions: the rules of every field, quoted from data-model.md and the spec."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.error_handlers import translate_validation_errors


def create(**values) -> SubscriptionCreate:
    return SubscriptionCreate.model_validate({"name": "Pro", "monthly_price": 100, **values})


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
        SubscriptionCreate.model_validate({"monthly_price": 1})


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


# --- monthly_price: Decimal with max_digits=10, decimal_places=2, ge=0 ---


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
    data = SubscriptionCreate.model_validate_json(f'{{"name": "Pro", "monthly_price": {raw}}}')

    assert data.monthly_price == expected


@pytest.mark.parametrize("raw", ["-1", "4500.555", "100000000", '"abc"', "null", "true"])
def test_invalid_prices_are_rejected(raw):
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate_json(f'{{"name": "Pro", "monthly_price": {raw}}}')


def test_the_price_is_required():
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate({"name": "Pro"})


# --- features: at most 20 items of 1 to 150 characters, a list, optional ---


def test_the_features_default_to_an_empty_list():
    assert create().features == []


def test_the_features_keep_their_order_and_are_trimmed():
    assert create(features=["  Uno ", "Dos", "Tres"]).features == ["Uno", "Dos", "Tres"]


def test_twenty_features_are_accepted():
    assert len(create(features=[f"f{n}" for n in range(20)]).features) == 20


@pytest.mark.parametrize(
    "features",
    [[f"f{n}" for n in range(21)], [""], ["  "], ["e" * 151], [1], "abc", None],
    ids=["21-items", "empty", "blank", "151-chars", "not-text", "not-a-list", "null"],
)
def test_invalid_features_are_rejected(features):
    with pytest.raises(ValidationError):
        create(features=features)


def test_an_element_of_one_hundred_fifty_characters_is_accepted():
    assert create(features=["e" * 150]).features == ["e" * 150]


def test_a_features_null_or_text_is_reported_as_not_being_a_list_not_as_an_element_problem():
    expected = [("features", "Lo que incluye la suscripción debe ser una lista de textos.")]

    assert messages_of({"name": "Pro", "monthly_price": 1, "features": None}) == expected
    assert messages_of({"name": "Pro", "monthly_price": 1, "features": "abc"}) == expected


# --- fields that cannot be sent ---


@pytest.mark.parametrize(
    "field", ["id", "status", "status_id", "clinics_count", "created_at", "updated_at"]
)
def test_the_fields_of_the_system_are_rejected_as_not_allowed(field):
    found = messages_of({"name": "Pro", "monthly_price": 1, field: 1})

    assert found == [(field, f"El campo «{field}» no está permitido.")]


def test_the_error_messages_never_repeat_the_value_received():
    found = messages_of({"name": "Pro", "monthly_price": -1, "password": "valor-secreto-9"})

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
        {"features": [f"f{n}" for n in range(21)]},
        {"features": ["e" * 151]},
        {"features": [""]},
    ):
        with pytest.raises(ValidationError):
            update(**payload)


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"name": None}, "name", "El nombre de la suscripción es obligatorio."),
        ({"monthly_price": None}, "monthly_price", "El precio mensual es obligatorio."),
        (
            {"features": None},
            "features",
            "Lo que incluye la suscripción debe ser una lista de textos.",
        ),
    ],
)
def test_the_fields_that_cannot_be_null_say_so_when_they_are_sent_as_null(payload, field, message):
    # `features` is NOT NULL in the database: a null must never get that far.
    assert update_messages(payload) == [(field, message)]


@pytest.mark.parametrize("description", [None, "", "   "])
def test_a_null_or_empty_description_clears_it_and_the_change_is_kept(description):
    data = update(description=description)

    assert data.model_dump(exclude_unset=True) == {"description": None}


def test_an_empty_list_of_features_empties_the_list():
    assert update(features=[]).model_dump(exclude_unset=True) == {"features": []}


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

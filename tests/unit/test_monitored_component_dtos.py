"""Data of the registry of components, field by field (spec 005, FR-024 to FR-026, FR-030; R14).

The DTOs validate each field on its own (format, length, type, unknown fields); the rules that depend
on `kind` and the list of allowed hosts belong to the Service. The messages are the exact ones of
`contracts/error-catalog.md` and never repeat the value that was received.
"""

import pytest
from pydantic import ValidationError

from src.dtos.monitored_component import MonitoredComponentCreate, MonitoredComponentUpdate
from src.error_handlers import translate_validation_errors

RESOURCE = "monitored-components"
VALID = {"code": "usuarios", "name": "Usuarios", "kind": "service", "base_url": "http://mailysoft-usuarios:8000"}

CODE_INVALID = (
    "El código debe tener de 2 a 50 caracteres entre minúsculas sin acentos, dígitos y guiones, "
    "empezar con una letra y no terminar en guion ni tener dos guiones seguidos."
)
BASE_URL_INVALID = (
    "La dirección base debe ser una dirección http:// o https:// de hasta 255 caracteres, con un host "
    "válido y sin usuario, contraseña, consulta (?) ni fragmento (#)."
)
PATH_INVALID = (
    "La ruta debe empezar con una sola «/» y tener hasta 200 caracteres, sin segmentos «.» o «..» y "
    "sin «\\», «?», «#», «%», espacios ni caracteres de control."
)


def errors_of(model, data: dict) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        model.model_validate(data)
    return [(e.field, e.message) for e in translate_validation_errors(error.value.errors(), RESOURCE)]


def create(**changes) -> MonitoredComponentCreate:
    return MonitoredComponentCreate.model_validate({**VALID, **changes})


# --- code ---


@pytest.mark.parametrize("code", ["ab", "mailysoft-usuarios", "a1-b2", "a" * 50])
def test_a_valid_code(code):
    assert create(code=code).code == code


@pytest.mark.parametrize("code", ["a", "1a", "a-", "a--b", "Ab", "a_b", "ñu", "a" * 51, "-ab", 123])
def test_an_invalid_code(code):
    assert errors_of(MonitoredComponentCreate, {**VALID, "code": code}) == [("code", CODE_INVALID)]


@pytest.mark.parametrize("data", [{k: v for k, v in VALID.items() if k != "code"}, {**VALID, "code": ""}, {**VALID, "code": None}])
def test_the_code_is_mandatory(data):
    assert errors_of(MonitoredComponentCreate, data) == [("code", "El código del componente es obligatorio.")]


# --- name ---


def test_the_name_is_trimmed():
    assert create(name="  Usuarios  ").name == "Usuarios"


@pytest.mark.parametrize("name", ["", "   ", None])
def test_the_name_is_mandatory(name):
    assert errors_of(MonitoredComponentCreate, {**VALID, "name": name}) == [
        ("name", "El nombre del componente es obligatorio.")
    ]


def test_the_name_has_at_most_100_characters():
    assert create(name="x" * 100).name == "x" * 100
    assert errors_of(MonitoredComponentCreate, {**VALID, "name": "x" * 101}) == [
        ("name", "El nombre del componente no puede tener más de 100 caracteres.")
    ]


def test_the_name_is_a_text():
    assert errors_of(MonitoredComponentCreate, {**VALID, "name": 7}) == [
        ("name", "El nombre del componente debe ser un texto.")
    ]


# --- kind ---


@pytest.mark.parametrize("kind", ["service", "frontend"])
def test_a_registered_component_is_a_service_or_a_frontend(kind):
    assert create(kind=kind).kind == kind


@pytest.mark.parametrize("kind", ["database", "Service", "", 1])
def test_another_kind_is_invalid(kind):
    assert errors_of(MonitoredComponentCreate, {**VALID, "kind": kind}) == [
        ("kind", "El tipo del componente debe ser «service» o «frontend».")
    ]


def test_the_kind_is_mandatory():
    data = {k: v for k, v in VALID.items() if k != "kind"}

    assert errors_of(MonitoredComponentCreate, data) == [("kind", "El tipo del componente es obligatorio.")]


# --- base_url (SSRF) ---


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        ("http://mailysoft-usuarios:8000", "http://mailysoft-usuarios:8000"),
        ("https://Maily360-production.up.railway.app/", "https://maily360-production.up.railway.app"),
        ("HTTP://10.0.0.5:8080/api", "http://10.0.0.5:8080/api"),
        ("http://[::1]:8000", "http://[::1]:8000"),
        ("  https://h.test/app/  ", "https://h.test/app"),
    ],
)
def test_a_valid_base_url_is_stored_normalized(value, stored):
    assert create(base_url=value).base_url == stored


@pytest.mark.parametrize(
    "value",
    [
        "ftp://a",
        "http://",
        "http://usuario:clave@h",
        "http://h/?",
        "http://h?x=1",
        "http://h/#",
        "http://h#f",
        "http://h/" + "x" * 250,
        "http://h /x",
        "http://h\\x",
        "http://ñandu.mx",
        "http://2130706433",
        "http://0x7f.1",
        "http://h./",
        "http://-h",
        "http://h:0",
        "http://h:65536",
        "http://h:abc",
        "http://h/a/../b",
        "http://h/a%2fb",
        "mailysoft-usuarios:8000",
        42,
    ],
)
def test_an_invalid_base_url_is_rejected_without_repeating_it(value):
    found = errors_of(MonitoredComponentCreate, {**VALID, "base_url": value})

    assert found == [("base_url", BASE_URL_INVALID)]
    assert "clave" not in found[0][1]


@pytest.mark.parametrize("value", ["", "  ", None])
def test_the_base_url_is_mandatory(value):
    assert errors_of(MonitoredComponentCreate, {**VALID, "base_url": value}) == [
        ("base_url", "La dirección base del componente es obligatoria.")
    ]


# --- paths ---


@pytest.mark.parametrize("path", ["/health/live", "/healthz/", "/a:b@c", "/", "/a-b_c.d~e"])
def test_a_valid_path(path):
    assert create(live_path=path).live_path == path


@pytest.mark.parametrize(
    "path",
    [
        "health",
        "//otro-host/x",
        "/\\otro-host",
        "/../admin",
        "/a/./b",
        "/a/..",
        "/a?b",
        "/a#b",
        "/a%2e%2e",
        "/a b",
        "/a\u0000",
        "/" + "x" * 200,
        "",
        7,
    ],
)
@pytest.mark.parametrize("field", ["live_path", "ready_path", "info_path"])
def test_an_invalid_path_is_rejected_on_its_field(field, path):
    assert errors_of(MonitoredComponentCreate, {**VALID, field: path}) == [(field, PATH_INVALID)]


def test_the_paths_may_be_null_in_the_dto():
    component = create(live_path=None, ready_path=None, info_path=None)

    assert (component.live_path, component.ready_path, component.info_path) == (None, None, None)


# --- enabled and sort_order ---


def test_the_defaults_of_enabled_and_sort_order():
    component = create()

    assert (component.enabled, component.sort_order) == (True, 0)


@pytest.mark.parametrize("value", ["yes", 1, "true", None])
def test_enabled_is_a_boolean(value):
    assert errors_of(MonitoredComponentCreate, {**VALID, "enabled": value}) == [
        ("enabled", "«enabled» debe ser verdadero o falso.")
    ]


@pytest.mark.parametrize("value", [-1, 10000, 1.5, "5", True, None])
def test_the_sort_order_is_an_integer_from_0_to_9999(value):
    assert errors_of(MonitoredComponentCreate, {**VALID, "sort_order": value}) == [
        ("sort_order", "El orden debe ser un número entero de 0 a 9999.")
    ]


@pytest.mark.parametrize("value", [0, 9999])
def test_the_limits_of_the_sort_order_are_valid(value):
    assert create(sort_order=value).sort_order == value


# --- unknown fields ---


@pytest.mark.parametrize("field", ["id", "deleted_at", "created_at", "otro"])
def test_an_unknown_or_internal_field_is_rejected(field):
    assert errors_of(MonitoredComponentCreate, {**VALID, field: "x"}) == [
        (field, f"El campo «{field}» no está permitido.")
    ]


# --- MonitoredComponentUpdate ---


def test_an_update_needs_at_least_one_field():
    assert errors_of(MonitoredComponentUpdate, {}) == [("body", "Hay que enviar al menos un dato para modificar.")]


@pytest.mark.parametrize("field", ["id", "created_at", "updated_at", "deleted_at"])
def test_an_update_cannot_change_the_identifier_or_the_dates(field):
    assert errors_of(MonitoredComponentUpdate, {field: "x"}) == [(field, f"El campo «{field}» no está permitido.")]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("code", "El código del componente es obligatorio."),
        ("name", "El nombre del componente es obligatorio."),
        ("kind", "El tipo del componente es obligatorio."),
        ("base_url", "La dirección base del componente es obligatoria."),
        ("enabled", "«enabled» debe ser verdadero o falso."),
        ("sort_order", "El orden debe ser un número entero de 0 a 9999."),
    ],
)
def test_an_update_cannot_set_a_mandatory_field_to_null(field, message):
    assert errors_of(MonitoredComponentUpdate, {field: None}) == [(field, message)]


@pytest.mark.parametrize("field", ["live_path", "ready_path", "info_path"])
def test_an_update_may_send_a_null_path(field):
    update = MonitoredComponentUpdate.model_validate({field: None})

    assert update.model_fields_set == {field}
    assert getattr(update, field) is None


def test_an_update_keeps_what_was_sent_and_validates_it_like_a_creation():
    update = MonitoredComponentUpdate.model_validate({"base_url": "HTTPS://H.test/", "enabled": False})

    assert update.model_dump(exclude_unset=True) == {"base_url": "https://h.test", "enabled": False}
    assert errors_of(MonitoredComponentUpdate, {"base_url": "http://u:p@h"}) == [("base_url", BASE_URL_INVALID)]
    assert errors_of(MonitoredComponentUpdate, {"live_path": "//x"}) == [("live_path", PATH_INVALID)]

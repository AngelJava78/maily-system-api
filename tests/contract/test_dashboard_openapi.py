"""The OpenAPI document publishes the contract of the dashboard (spec 003, FR-026, FR-031).

Parallel to `test_openapi_contract.py`, which keeps watching the subscriptions. The reference is
`specs/003-platform-dashboard/contracts/openapi-dashboard.yaml` (no YAML library is part of the
stack, so the expectations are written here).
"""

import pytest

from src.main import create_app
from src.messages import ErrorCode

PATH = "/api/v1/dashboard"
FIELDS = {
    "total_clinics",
    "active_clinics",
    "trial_clinics",
    "total_doctors",
    "total_patients",
    "total_users",
    "recent_clinics",
}


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


@pytest.fixture(scope="module")
def operation(schema) -> dict:
    return schema["paths"][PATH]["get"]


def test_the_dashboard_is_one_get_operation_and_nothing_else_lives_under_its_path(schema):
    paths = {path: set(item) for path, item in schema["paths"].items() if path.startswith(PATH)}

    assert paths == {PATH: {"get"}}
    assert schema["paths"][PATH]["get"]["operationId"] == "get_dashboard"


def test_it_declares_its_tag_security_permission_and_documentation(operation):
    assert operation["tags"] == ["dashboard"]
    assert operation["security"] == [{"BearerAuth": []}]
    assert operation["x-required-permission"] == "dashboard:read"
    assert operation["summary"]
    assert "Permiso requerido: `dashboard:read`" in operation["description"]


def test_it_documents_the_responses_the_contract_promises(operation):
    assert {"200", "401", "403", "422", "503"} <= set(operation["responses"])


def test_the_errors_use_the_uniform_body_and_the_401_documents_its_header(operation):
    for status in ("401", "403", "422", "503"):
        content = operation["responses"][status]["content"]["application/json"]
        assert content["schema"]["$ref"] == "#/components/schemas/ErrorResponse", status
    assert "WWW-Authenticate" in operation["responses"]["401"]["headers"]


def test_the_success_response_says_it_must_not_be_cached(operation):
    assert "Cache-Control" in operation["responses"]["200"]["headers"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/DashboardRead"
    )


def test_limit_is_published_as_an_optional_integer_of_at_least_one(operation):
    [limit] = [p for p in operation["parameters"] if p["name"] == "limit"]

    assert limit["in"] == "query"
    assert limit.get("required", False) is False
    assert limit["schema"]["type"] == "integer"
    assert limit["schema"]["minimum"] == 1
    assert "10" in limit["description"]  # the cap is part of what the person reads


def test_the_seven_fields_are_mandatory_and_each_one_allows_null(schema):
    read = schema["components"]["schemas"]["DashboardRead"]

    assert set(read["required"]) == FIELDS
    assert set(read["properties"]) == FIELDS
    for name, definition in read["properties"].items():
        assert {"type": "null"} in definition["anyOf"], name


def test_the_counts_are_integers_that_cannot_be_negative(schema):
    read = schema["components"]["schemas"]["DashboardRead"]

    for name in FIELDS - {"recent_clinics"}:
        integer = [o for o in read["properties"][name]["anyOf"] if o.get("type") == "integer"]
        assert integer and integer[0]["minimum"] == 0, name


def test_the_list_is_bounded_to_ten_clinics(schema):
    read = schema["components"]["schemas"]["DashboardRead"]
    [array] = [o for o in read["properties"]["recent_clinics"]["anyOf"] if o.get("type") == "array"]

    assert array["maxItems"] == 10
    assert array["items"]["$ref"] == "#/components/schemas/RecentClinicRead"


def test_a_clinic_and_its_status_have_exactly_their_published_fields(schema):
    clinic = schema["components"]["schemas"]["RecentClinicRead"]
    status = schema["components"]["schemas"]["ClinicStatusRead"]

    assert set(clinic["properties"]) == {"id", "name", "created_at", "status"}
    assert set(clinic["required"]) == {"id", "name", "created_at", "status"}
    assert clinic["properties"]["id"]["format"] == "uuid"
    assert clinic["properties"]["created_at"]["format"] == "date-time"
    assert set(status["properties"]) == {"id", "name"}
    assert set(status["required"]) == {"id", "name"}


def test_no_error_code_was_added(schema):
    assert set(schema["components"]["schemas"]["ErrorCode"]["enum"]) == {c.value for c in ErrorCode}
    assert len(ErrorCode) == 17  # spec 005 added 2 registry codes; reviewed, no dashboard impact


# The public health routes of spec 005 (Principle VIII exception): the only operations without security.
PUBLIC_HEALTH_PATHS = {"/health/live", "/health/ready", "/info", "/health/status"}


def test_every_operation_of_the_api_declares_security_and_permission(schema):
    operations = [
        op
        for path, item in schema["paths"].items()
        if path not in PUBLIC_HEALTH_PATHS
        for op in item.values()
    ]

    assert len(operations) >= 7
    for operation in operations:
        assert operation["security"] == [{"BearerAuth": []}], operation["operationId"]
        assert operation["x-required-permission"], operation["operationId"]


def test_the_version_of_the_api_does_not_change_when_an_operation_is_added(schema):
    # The dashboard (spec 003) added an operation without bumping the version; spec 004 later
    # bumped it on its own (a breaking change to the subscriptions schema, research R9), not
    # because of this operation.
    assert schema["info"]["version"] == "2.0.0"

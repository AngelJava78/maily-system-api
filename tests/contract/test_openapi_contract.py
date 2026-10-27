"""The OpenAPI document that the application publishes (Principle IV, FR-034).

It is checked against the contract of
`specs/004-correct-subscriptions-api/contracts/openapi-subscriptions.yaml` (the list of operations
is fixed here: no YAML library is part of the stack).
"""

import pytest

from src.main import create_app
from src.messages import ErrorCode

# operation_id -> (method, path, permission, status codes that the contract promises)
OPERATIONS = {
    "list_subscriptions": ("get", "/api/v1/subscriptions", "subscriptions:read", {"200", "401", "403", "503"}),
    "create_subscription": ("post", "/api/v1/subscriptions", "subscriptions:write", {"201", "401", "403", "409", "422", "503"}),
    "get_subscription": ("get", "/api/v1/subscriptions/{subscription_id}", "subscriptions:read", {"200", "401", "403", "404", "422", "503"}),
    "update_subscription": ("patch", "/api/v1/subscriptions/{subscription_id}", "subscriptions:update", {"200", "401", "403", "404", "409", "422", "503"}),
    "delete_subscription": ("delete", "/api/v1/subscriptions/{subscription_id}", "subscriptions:delete", {"204", "401", "403", "404", "409", "422", "503"}),
    "change_subscription_status": ("patch", "/api/v1/subscriptions/{subscription_id}/status", "subscriptions:update", {"200", "401", "403", "404", "409", "422", "503"}),
}


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


def operations_of(schema: dict) -> dict[str, tuple[str, str, dict]]:
    return {
        operation["operationId"]: (method, path, operation)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
    }


def test_the_document_is_generated_openapi_3_with_the_version_of_the_contract(schema):
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["version"] == "4.0.0"
    assert schema["info"]["title"] == "MailySoft System API"


def test_it_has_exactly_the_six_operations_of_the_contract(schema):
    # The six operations of the subscriptions. The dashboard operation is checked in
    # test_dashboard_openapi.py.
    found = {
        operation_id: (method, path)
        for operation_id, (method, path, _) in operations_of(schema).items()
        if path.startswith("/api/v1/subscriptions")
    }

    assert found == {oid: (m, p) for oid, (m, p, _, _) in OPERATIONS.items()}


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_each_operation_declares_security_permission_and_documentation(schema, operation_id):
    _, _, permission, _ = OPERATIONS[operation_id]
    _, _, operation = operations_of(schema)[operation_id]

    assert operation["security"] == [{"BearerAuth": []}]
    assert operation["x-required-permission"] == permission
    assert operation["summary"]
    assert f"Permiso requerido: `{permission}`" in operation["description"]
    assert operation["tags"] == ["subscriptions"]


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_each_operation_documents_the_responses_the_contract_promises(schema, operation_id):
    _, _, _, expected_codes = OPERATIONS[operation_id]
    _, _, operation = operations_of(schema)[operation_id]

    assert expected_codes <= set(operation["responses"])


@pytest.mark.parametrize("operation_id", ["create_subscription", "update_subscription"])
def test_the_error_responses_use_the_uniform_error_body(schema, operation_id):
    _, _, operation = operations_of(schema)[operation_id]

    for status in ("401", "403", "409", "422", "503"):
        content = operation["responses"][status]["content"]["application/json"]
        assert content["schema"]["$ref"] == "#/components/schemas/ErrorResponse", status


def test_the_unauthorized_response_documents_the_challenge_header(schema):
    _, _, operation = operations_of(schema)["list_subscriptions"]

    assert "WWW-Authenticate" in operation["responses"]["401"]["headers"]


def test_the_security_scheme_is_http_bearer(schema):
    scheme = schema["components"]["securitySchemes"]["BearerAuth"]

    assert (scheme["type"], scheme["scheme"]) == ("http", "bearer")


def test_the_schemas_of_the_contract_exist(schema):
    schemas = schema["components"]["schemas"]

    for name in (
        "SubscriptionRead",
        "SubscriptionCreate",
        "SubscriptionUpdate",
        "SubscriptionStatusChange",
        "StatusRead",
        "SubscriptionTypeRead",
        "ErrorResponse",
    ):
        assert name in schemas, name


def test_the_error_codes_are_the_eighteen_of_the_catalog(schema):
    assert set(schema["components"]["schemas"]["ErrorCode"]["enum"]) == {c.value for c in ErrorCode}
    # spec 005 added the 2 codes of the registry of components; spec 006 added
    # subscription_type_not_found.
    assert len(ErrorCode) == 18


def test_the_price_is_published_as_a_string(schema):
    read = schema["components"]["schemas"]["SubscriptionRead"]

    assert read["properties"]["monthly_price"]["type"] == "string"


def test_the_status_change_only_offers_the_three_manageable_statuses(schema):
    change = schema["components"]["schemas"]["SubscriptionStatusChange"]

    assert change["properties"]["status_id"]["enum"] == [1, 2, 3]


# The public health routes of spec 005 (Principle VIII exception): the only operations without security.
PUBLIC_HEALTH_PATHS = {"/health/live", "/health/ready", "/info", "/health/status"}


def test_the_documentation_routes_declare_no_security(schema):
    assert not any(path in schema["paths"] for path in ("/docs", "/redoc", "/openapi.json"))
    assert all(
        operation["security"]
        for operation in (
            op for _, path, op in operations_of(schema).values() if path not in PUBLIC_HEALTH_PATHS
        )
    )

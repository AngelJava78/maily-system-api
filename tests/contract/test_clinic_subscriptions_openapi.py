"""The OpenAPI document that the application publishes, for the clinic subscriptions (spec 006).

Hand-transcribed against `contracts/openapi-clinic-subscriptions.yaml` (no YAML library is part of
the stack), same pattern as `tests/contract/test_openapi_contract.py` for the subscriptions catalog.
"""

import pytest

from src.main import create_app

# operation_id -> (method, path, permission, status codes the contract promises)
OPERATIONS = {
    "list_clinic_subscriptions": ("get", "/api/v1/clinic-subscriptions", "clinic_subscriptions:read", {"200", "401", "403", "503"}),
    "create_clinic_subscription": ("post", "/api/v1/clinic-subscriptions", "clinic_subscriptions:write", {"201", "401", "403", "409", "422", "503"}),
    "get_clinic_subscription": ("get", "/api/v1/clinic-subscriptions/{clinic_subscription_id}", "clinic_subscriptions:read", {"200", "401", "403", "404", "422", "503"}),
    "cancel_clinic_subscription": ("delete", "/api/v1/clinic-subscriptions/{clinic_subscription_id}", "clinic_subscriptions:delete", {"204", "401", "403", "404", "409", "422", "503"}),
    "list_clinic_subscription_charges": ("get", "/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges", "clinic_subscriptions:read", {"200", "401", "403", "404", "422", "503"}),
    "charge_clinic_subscription": ("post", "/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges", "clinic_subscriptions:charge", {"201", "401", "403", "404", "409", "503"}),
    "get_clinic_subscription_charge": ("get", "/api/v1/clinic-subscriptions/{clinic_subscription_id}/charges/{charge_id}", "clinic_subscriptions:read", {"200", "401", "403", "404", "422", "503"}),
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


def test_it_has_exactly_the_seven_operations_of_the_contract(schema):
    found = {
        operation_id: (method, path)
        for operation_id, (method, path, _) in operations_of(schema).items()
        if path.startswith("/api/v1/clinic-subscriptions")
    }

    assert found == {oid: (m, p) for oid, (m, p, _, _) in OPERATIONS.items()}


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_each_operation_declares_security_and_permission(schema, operation_id):
    _, _, permission, _ = OPERATIONS[operation_id]
    _, _, operation = operations_of(schema)[operation_id]

    assert operation["security"] == [{"BearerAuth": []}]
    assert operation["x-required-permission"] == permission
    assert operation["summary"]
    assert operation["tags"] == ["clinic-subscriptions"]


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_each_operation_documents_the_responses_the_contract_promises(schema, operation_id):
    _, _, _, expected_codes = OPERATIONS[operation_id]
    _, _, operation = operations_of(schema)[operation_id]

    assert expected_codes <= set(operation["responses"])


def test_the_schemas_of_the_contract_exist(schema):
    schemas = schema["components"]["schemas"]

    for name in ("ClinicSubscriptionRead", "ClinicSubscriptionCreate", "ClinicSubscriptionChargeRead"):
        assert name in schemas, name


def test_the_amount_is_published_as_an_integer_never_a_string(schema):
    read = schema["components"]["schemas"]["ClinicSubscriptionChargeRead"]

    assert read["properties"]["amount"]["type"] == "integer"


def test_create_requires_tenant_id_subscription_id_and_billing_cycle(schema):
    create = schema["components"]["schemas"]["ClinicSubscriptionCreate"]

    assert set(create["required"]) == {"tenant_id", "subscription_id", "billing_cycle"}

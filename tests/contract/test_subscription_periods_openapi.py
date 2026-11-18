"""The OpenAPI document publishes the contract of the subscription periods (spec 010, FR-001, FR-041).

Parallel to `test_openapi_contract.py`, `test_dashboard_openapi.py` and `test_health_openapi.py`. The
reference is `specs/010-subscription-periods/contracts/openapi-subscription-periods.yaml` (no YAML library
is part of the stack, so the expectations are written here). It needs no database.
"""

import pytest

from src.main import create_app
from src.messages import ErrorCode

CONSULT_PATH = "/api/v1/subscription-periods/{organization_id}"
PAY_PATH = "/api/v1/subscription-periods/{organization_id}/payments"
PERIOD_FIELDS = {
    "state",
    "trial_ends_at",
    "payment_due_at",
    "days_remaining",
    "subscription",
    "billing_period",
    "amount",
    "currency",
    "payment_in_progress",
}
NULLABLE_FIELDS = {"trial_ends_at", "payment_due_at", "days_remaining", "payment_in_progress"}
PAYMENT_FIELDS = {"checkout_url", "amount", "currency", "billing_period"}
NEW_CODES = {
    "organization_not_found",
    "organization_check_unavailable",
    "payments_unavailable",
    "nothing_to_charge",
    "organization_subscription_not_found",
}
PUBLIC_PATHS = {"/health/live", "/health/ready", "/info", "/health/status"}


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


@pytest.fixture(scope="module")
def consult(schema: dict) -> dict:
    return schema["paths"][CONSULT_PATH]["get"]


@pytest.fixture(scope="module")
def pay(schema: dict) -> dict:
    return schema["paths"][PAY_PATH]["post"]


def ref_of(response: dict) -> str:
    return response["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]


# --- the two operations ---


def test_the_two_operations_are_published_with_their_identifiers(schema: dict, consult: dict, pay: dict):
    assert list(schema["paths"][CONSULT_PATH]) == ["get"]
    assert list(schema["paths"][PAY_PATH]) == ["post"]
    assert (consult["operationId"], pay["operationId"]) == ("get_subscription_period", "create_subscription_payment")


def test_both_belong_to_the_tag_that_describes_them(schema: dict, consult: dict, pay: dict):
    tags = {tag["name"]: tag.get("description", "") for tag in schema["tags"]}

    assert consult["tags"] == pay["tags"] == ["subscription-periods"]
    assert tags["subscription-periods"]


def test_both_need_the_token_and_say_which_permission(consult: dict, pay: dict):
    assert consult["security"] == pay["security"] == [{"BearerAuth": []}]
    assert consult["x-required-permission"] == "subscription_periods:read"
    assert pay["x-required-permission"] == "subscription_periods:write"
    assert "Permiso requerido: `subscription_periods:read`" in consult["description"]
    assert "Permiso requerido: `subscription_periods:write`" in pay["description"]


@pytest.mark.parametrize("operation", ["consult", "pay"])
def test_the_organization_is_a_uuid_in_the_path(operation: str, consult: dict, pay: dict):
    [parameter] = {"consult": consult, "pay": pay}[operation]["parameters"]

    assert (parameter["name"], parameter["in"], parameter["required"]) == ("organization_id", "path", True)
    assert (parameter["schema"]["type"], parameter["schema"]["format"]) == ("string", "uuid")
    assert parameter["schema"]["description"]


def test_paying_takes_no_body(pay: dict):
    # The amount is the catalog's: the person never sends it (FR-016).
    assert "requestBody" not in pay


# --- the responses ---


def test_the_consultation_documents_its_answers(consult: dict):
    assert set(consult["responses"]) == {"200", "401", "403", "404", "409", "422", "500", "503"}
    assert ref_of(consult["responses"]["200"]) == "SubscriptionPeriodRead"


def test_the_payment_documents_its_answers(pay: dict):
    assert set(pay["responses"]) == {"200", "201", "401", "403", "404", "409", "422", "500", "503"}
    assert ref_of(pay["responses"]["201"]) == ref_of(pay["responses"]["200"]) == "SubscriptionPaymentRead"


@pytest.mark.parametrize("operation", ["consult", "pay"])
def test_every_failure_is_an_error_response_with_its_examples(operation: str, consult: dict, pay: dict):
    responses = {"consult": consult, "pay": pay}[operation]["responses"]

    for status, response in responses.items():
        if status in ("200", "201"):
            continue
        assert ref_of(response) == "ErrorResponse", status
        examples = response["content"]["application/json"]["examples"]
        assert examples, status
        for example in examples.values():
            assert example["value"]["code"] in {code.value for code in ErrorCode}, (status, example)
            assert example["value"]["message"], (status, example)


@pytest.mark.parametrize(
    ("operation", "status"), [("consult", "200"), ("pay", "200"), ("pay", "201")]
)
def test_the_answers_are_not_cached_and_the_header_says_so(operation: str, status: str, consult: dict, pay: dict):
    response = {"consult": consult, "pay": pay}[operation]["responses"][status]

    assert "Cache-Control" in response["headers"]
    assert response["headers"]["Cache-Control"]["schema"]["type"] == "string"


def test_the_unauthorized_answer_says_how_to_log_in(consult: dict, pay: dict):
    for operation in (consult, pay):
        assert "WWW-Authenticate" in operation["responses"]["401"]["headers"]


def test_the_examples_of_the_consultation_show_only_real_fields_and_every_one_that_cannot_be_null(
    consult: dict,
):
    # FastAPI drops the `null` values of an example when it generates the document (the examples of the
    # health routes lose theirs in the same way), so an example shows the fields that have a value. The
    # schema is what says that the nine are always present: required, and `null` where it applies.
    examples = consult["responses"]["200"]["content"]["application/json"]["examples"]

    assert examples
    for name, example in examples.items():
        shown = set(example["value"])
        assert shown <= PERIOD_FIELDS, (name, shown - PERIOD_FIELDS)  # nothing invented
        assert shown >= PERIOD_FIELDS - NULLABLE_FIELDS, (name, PERIOD_FIELDS - NULLABLE_FIELDS - shown)


def test_the_examples_of_the_payment_always_have_the_four_fields(pay: dict):
    for status in ("200", "201"):
        examples = pay["responses"][status]["content"]["application/json"]["examples"]
        assert examples
        for name, example in examples.items():
            assert set(example["value"]) == PAYMENT_FIELDS, (status, name)


# --- the schemas ---


def test_the_period_publishes_nine_required_fields(schema: dict):
    period = schema["components"]["schemas"]["SubscriptionPeriodRead"]

    assert set(period["required"]) == set(period["properties"]) == PERIOD_FIELDS
    properties = period["properties"]
    assert properties["state"]["enum"] == ["trial", "current", "overdue", "no_charge"]
    assert properties["billing_period"]["enum"] == ["monthly", "annual"]
    assert properties["amount"]["type"] == "string"  # decimal as text: never a float (Principle VI)
    for name in NULLABLE_FIELDS:
        assert {"type": "null"} in properties[name]["anyOf"], name
    for name in PERIOD_FIELDS - NULLABLE_FIELDS:
        assert "anyOf" not in properties[name], name
    # What the examples cannot show: that the nine are always present, `null` when they do not apply.
    assert "nueve campos siempre están presentes" in period["description"]
    assert {"type": "string", "format": "date-time"} in properties["trial_ends_at"]["anyOf"]
    assert {"type": "integer"} in properties["days_remaining"]["anyOf"]


def test_the_payment_publishes_four_required_fields(schema: dict):
    payment = schema["components"]["schemas"]["SubscriptionPaymentRead"]

    assert set(payment["required"]) == set(payment["properties"]) == PAYMENT_FIELDS
    assert payment["properties"]["amount"]["type"] == "string"


def test_nothing_in_the_schemas_exposes_a_token_an_address_or_a_payment_identifier(schema: dict):
    for name in ("SubscriptionPeriodRead", "SubscriptionPaymentRead", "PlanRead"):
        properties = set(schema["components"]["schemas"][name]["properties"])
        assert not properties & {"token", "authorization", "payment_id", "organization_id", "base_url"}, name


def test_every_field_is_described_in_spanish(schema: dict):
    for name in ("SubscriptionPeriodRead", "SubscriptionPaymentRead", "PlanRead"):
        schema_ = schema["components"]["schemas"][name]
        assert schema_["description"], name
        for field, definition in schema_["properties"].items():
            assert definition.get("description"), f"{name}.{field}"


def test_the_operations_are_described_in_spanish(consult: dict, pay: dict):
    for operation in (consult, pay):
        assert operation["summary"] and operation["description"]
        for response in operation["responses"].values():
            assert response["description"]
    assert consult["summary"].startswith("Consultar")
    assert pay["summary"].startswith("Iniciar")


def test_the_error_codes_of_the_schema_include_the_five_new_ones(schema: dict):
    codes = set(schema["components"]["schemas"]["ErrorCode"]["enum"])

    assert NEW_CODES <= codes
    assert codes == {code.value for code in ErrorCode}


# --- the whole API ---


def test_every_operation_declares_its_security_and_permission_except_the_public_ones(schema: dict):
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if path in PUBLIC_PATHS:
                assert "security" not in operation, (method, path)
                continue
            assert operation.get("security") == [{"BearerAuth": []}], (method, path)
            assert operation.get("x-required-permission"), (method, path)

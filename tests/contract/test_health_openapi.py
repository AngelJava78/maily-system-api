"""The OpenAPI document publishes the contract of the health operations (spec 005, FR-001, FR-008).

Parallel to `test_openapi_contract.py` (subscriptions) and `test_dashboard_openapi.py`. The reference
is `specs/005-health-monitoring/contracts/openapi-health.yaml` (no YAML library is part of the stack,
so the expectations are written here).
"""

import pytest

from src.main import create_app

COMPONENT_FIELDS = {
    "code",
    "name",
    "kind",
    "status",
    "latency_ms",
    "checked_at",
    "version",
    "commit",
    "build_date",
    "environment",
    "checks",
    "error",
    "next_start_at",
}
COMPONENT_ERRORS = {
    "timeout",
    "connection_error",
    "dns_error",
    "host_not_allowed",
    "unexpected_status",
    "invalid_response",
    "response_too_large",
    "not_ready",
    "unexpected_error",
}


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


def operation(schema: dict, method: str, path: str) -> dict:
    return schema["paths"][path][method]


def enum_of(definition: dict) -> set:
    """The values of an enumerated property, also when it can be `null` (`anyOf`)."""
    if "enum" in definition:
        return set(definition["enum"])
    return {value for option in definition.get("anyOf", []) for value in option.get("enum", [])}


# --- get_health ---


def test_get_health_declares_its_tag_security_permission_and_documentation(schema):
    get_health = operation(schema, "get", "/api/v1/health")

    assert get_health["operationId"] == "get_health"
    assert get_health["tags"] == ["Salud"]
    assert get_health["security"] == [{"BearerAuth": []}]
    assert get_health["x-required-permission"] == "health:read"
    assert get_health["summary"]
    assert "Permiso requerido: `health:read`" in get_health["description"]


def test_get_health_documents_its_responses_with_the_uniform_error_body(schema):
    responses = operation(schema, "get", "/api/v1/health")["responses"]

    assert {"200", "401", "403", "503"} <= set(responses)
    for status in ("401", "403", "503"):
        assert responses[status]["content"]["application/json"]["schema"]["$ref"] == (
            "#/components/schemas/ErrorResponse"
        )
    assert "Cache-Control" in responses["200"]["headers"]
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/HealthRead"


def test_the_result_of_health_has_exactly_its_four_mandatory_fields(schema):
    read = schema["components"]["schemas"]["HealthRead"]

    assert set(read["properties"]) == set(read["required"]) == {
        "status",
        "checked_at",
        "registry_available",
        "components",
    }
    assert enum_of(read["properties"]["status"]) == {"ok", "degraded", "down"}


def test_a_component_has_exactly_its_thirteen_mandatory_fields_and_no_address(schema):
    component = schema["components"]["schemas"]["ComponentHealthRead"]

    assert set(component["properties"]) == set(component["required"]) == COMPONENT_FIELDS
    assert enum_of(component["properties"]["status"]) == {"up", "degraded", "down", "stopped", "unknown"}
    assert enum_of(component["properties"]["kind"]) == {"service", "database", "frontend"}
    assert enum_of(component["properties"]["error"]) == COMPONENT_ERRORS
    assert not {"base_url", "url", "host"} & set(component["properties"])


def test_a_check_has_the_shape_of_the_contract(schema):
    check = schema["components"]["schemas"]["CheckRead"]

    assert set(check["properties"]) == set(check["required"]) == {"name", "status", "latency_ms", "error"}
    assert enum_of(check["properties"]["status"]) == {"ok", "error"}
    assert enum_of(check["properties"]["error"]) == {
        "timeout",
        "connection_error",
        "not_configured",
        "unexpected_error",
    }


def test_the_tag_of_the_health_operations_is_published(schema):
    assert "Salud" in {tag["name"] for tag in schema["tags"]}


# --- the public routes of the contract v1 (user story 2) ---

PUBLIC_V1 = [
    ("/health/live", "get_health_live", "LiveRead"),
    ("/health/ready", "get_health_ready", "ReadyRead"),
    ("/info", "get_info", "InfoRead"),
]


@pytest.mark.parametrize(("path", "operation_id", "model"), PUBLIC_V1)
def test_a_public_route_declares_no_security_and_no_permission(schema, path, operation_id, model):
    public = operation(schema, "get", path)

    assert public["operationId"] == operation_id
    assert public["tags"] == ["Salud"]
    assert "security" not in public
    assert "x-required-permission" not in public
    assert public["summary"]
    assert "no exige token" in public["description"]


@pytest.mark.parametrize(("path", "operation_id", "model"), PUBLIC_V1)
def test_a_public_route_documents_no_store_and_its_schema(schema, path, operation_id, model):
    ok = operation(schema, "get", path)["responses"]["200"]

    assert "Cache-Control" in ok["headers"]
    assert ok["content"]["application/json"]["schema"]["$ref"] == f"#/components/schemas/{model}"


def test_readiness_documents_its_503_with_the_same_schema(schema):
    unavailable = operation(schema, "get", "/health/ready")["responses"]["503"]

    assert unavailable["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ReadyRead"
    assert "Cache-Control" in unavailable["headers"]


def test_info_has_exactly_the_five_fields_of_the_contract(schema):
    info = schema["components"]["schemas"]["InfoRead"]

    assert set(info["properties"]) == set(info["required"]) == {
        "service",
        "version",
        "commit",
        "build_date",
        "environment",
    }


def test_readiness_has_the_shape_of_the_contract(schema):
    ready = schema["components"]["schemas"]["ReadyRead"]

    assert set(ready["properties"]) == set(ready["required"]) == {"status", "checks"}
    assert enum_of(ready["properties"]["status"]) == {"ok", "unavailable"}


# --- the public status (user story 6) ---


def test_the_public_status_declares_no_security_and_only_its_200(schema):
    public = operation(schema, "get", "/health/status")

    assert public["operationId"] == "get_health_status"
    assert public["tags"] == ["Salud"]
    assert "security" not in public
    assert "x-required-permission" not in public
    assert public["summary"]
    assert "No es una *probe*" in public["description"]
    assert "no exige token" in public["description"]
    assert set(public["responses"]) == {"200"}
    ok = public["responses"]["200"]
    assert "Cache-Control" in ok["headers"]
    assert ok["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/PublicStatusRead"


def test_the_public_status_has_exactly_its_closed_list_of_fields(schema):
    schemas = schema["components"]["schemas"]
    status = schemas["PublicStatusRead"]
    component = schemas["PublicComponentRead"]

    assert set(status["properties"]) == set(status["required"]) == {"status", "checked_at", "components"}
    assert set(component["properties"]) == set(component["required"]) == {
        "code",
        "name",
        "kind",
        "status",
        "next_start_at",
    }
    assert status["properties"]["components"]["items"]["$ref"] == "#/components/schemas/PublicComponentRead"
    assert enum_of(status["properties"]["status"]) == {"ok", "degraded", "down"}
    assert enum_of(component["properties"]["status"]) == {"up", "degraded", "down", "stopped", "unknown"}
    assert enum_of(component["properties"]["kind"]) == {"service", "database", "frontend"}


# --- the registry of components (user story 3) ---

COMPONENTS = "/api/v1/monitored-components"
COMPONENT = f"{COMPONENTS}/{{component_id}}"
# operation_id -> (method, path, permission, responses of FR-001)
REGISTRY = {
    "list_monitored_components": ("get", COMPONENTS, "health:read", {"200", "401", "403", "500", "503"}),
    "create_monitored_component": (
        "post",
        COMPONENTS,
        "health:write",
        {"201", "401", "403", "409", "422", "500", "503"},
    ),
    "get_monitored_component": ("get", COMPONENT, "health:read", {"200", "401", "403", "404", "422", "500", "503"}),
    "update_monitored_component": (
        "patch",
        COMPONENT,
        "health:update",
        {"200", "401", "403", "404", "409", "422", "500", "503"},
    ),
    "delete_monitored_component": (
        "delete",
        COMPONENT,
        "health:delete",
        {"204", "401", "403", "404", "422", "500", "503"},
    ),
}
READ_FIELDS = {
    "id",
    "code",
    "name",
    "kind",
    "base_url",
    "live_path",
    "ready_path",
    "info_path",
    "enabled",
    "sort_order",
    "created_at",
    "updated_at",
}


def test_the_registry_is_exactly_its_five_operations(schema):
    paths = {path: set(item) for path, item in schema["paths"].items() if path.startswith(COMPONENTS)}

    assert paths == {COMPONENTS: {"get", "post"}, COMPONENT: {"get", "patch", "delete"}}


@pytest.mark.parametrize("operation_id", sorted(REGISTRY))
def test_each_registry_operation_declares_its_tag_security_permission_and_documentation(schema, operation_id):
    method, path, permission, _ = REGISTRY[operation_id]
    found = operation(schema, method, path)

    assert found["operationId"] == operation_id
    assert found["tags"] == ["Salud"]
    assert found["security"] == [{"BearerAuth": []}]
    assert found["x-required-permission"] == permission
    assert found["summary"]
    assert f"Permiso requerido: `{permission}`" in found["description"]


@pytest.mark.parametrize("operation_id", sorted(REGISTRY))
def test_each_registry_operation_documents_its_responses_with_the_uniform_error_body(schema, operation_id):
    method, path, _, expected = REGISTRY[operation_id]
    responses = operation(schema, method, path)["responses"]

    assert expected <= set(responses)
    for status in expected - {"200", "201", "204"}:
        assert responses[status]["content"]["application/json"]["schema"]["$ref"] == (
            "#/components/schemas/ErrorResponse"
        ), status


def test_the_registry_answers_with_its_read_schema(schema):
    read = "#/components/schemas/MonitoredComponentRead"
    listed = operation(schema, "get", COMPONENTS)["responses"]["200"]["content"]["application/json"]["schema"]

    assert (listed["type"], listed["items"]["$ref"]) == ("array", read)
    for method, path, status in (("post", COMPONENTS, "201"), ("get", COMPONENT, "200"), ("patch", COMPONENT, "200")):
        content = operation(schema, method, path)["responses"][status]["content"]["application/json"]
        assert content["schema"]["$ref"] == read, (method, path)


def test_a_registration_documents_the_location_of_the_new_component(schema):
    created = operation(schema, "post", COMPONENTS)["responses"]["201"]

    assert "Location" in created["headers"]


def test_the_identifier_of_a_component_is_a_uuid(schema):
    for method in ("get", "patch", "delete"):
        [parameter] = [p for p in operation(schema, method, COMPONENT)["parameters"] if p["name"] == "component_id"]
        assert (parameter["in"], parameter["required"]) == ("path", True)
        assert parameter["schema"]["format"] == "uuid"


def test_the_data_of_the_registry_admits_no_unknown_field(schema):
    schemas = schema["components"]["schemas"]
    create = schemas["MonitoredComponentCreate"]
    update = schemas["MonitoredComponentUpdate"]

    assert create["additionalProperties"] is False
    assert update["additionalProperties"] is False
    assert set(create["required"]) == {"code", "name", "kind", "base_url"}
    assert "required" not in update
    assert {"id", "created_at", "updated_at", "deleted_at"}.isdisjoint(create["properties"])
    assert {"id", "created_at", "updated_at", "deleted_at"}.isdisjoint(update["properties"])
    assert enum_of(create["properties"]["kind"]) == {"service", "frontend"}


def test_a_registered_component_is_published_without_its_deletion_date(schema):
    read = schema["components"]["schemas"]["MonitoredComponentRead"]

    assert set(read["properties"]) == set(read["required"]) == READ_FIELDS
    assert read["properties"]["id"]["format"] == "uuid"
    assert read["properties"]["created_at"]["format"] == "date-time"
    assert enum_of(read["properties"]["kind"]) == {"service", "frontend"}


def test_the_error_codes_of_the_api_are_eighteen(schema):
    codes = set(schema["components"]["schemas"]["ErrorCode"]["enum"])

    assert len(codes) == 18
    assert {"monitored_component_not_found", "monitored_component_code_already_exists"} <= codes

"""The Postman collection of the health of the services is complete and holds no secrets (spec 005).

Rules G1 to G8 of `specs/005-health-monitoring/contracts/e2e-collection.md`; G9 (the collections
together cover the API) lives in `test_dashboard_postman_collection.py`. They only read files of the
repository and the OpenAPI document that the application generates: no service, no Node.js, no
Postman and no network. Each rule is a pure function `check_*(...) -> list[str]` whose messages name
what is missing or what is left over, and the tests also run it on altered in-memory copies to prove
that it detects what it is for.
"""

import copy
import json
import re

import pytest

from tests.contract.postman_support import (
    BEARER_LITERAL_PATTERN,
    HEALTH_COLLECTION,
    HEALTH_HELPER_PREFIXES,
    HIGH_ENTROPY_PATTERN,
    JWT_PATTERN,
    POSTMAN,
    folders_of,
    health_operation_ids,
    load_json,
    prefix_of,
    requests_of,
)

STATUSES = (200, 201, 204, 401, 403, 404, 409, 422, 503)
ALLOWED_TOKENS = {"{{readerToken}}", "{{plainToken}}", "{{subscriptionsToken}}", "{{badToken}}"}
SCHEMA_SUFFIX = "/collection/v2.1.0/collection.json"
REGISTRY_PATH = ["api", "v1", "monitored-components"]
FORBIDDEN_RESOURCES = (["api", "v1", "subscriptions"], ["api", "v1", "dashboard"])
SIMULATIONS = {"{{usersStubUrl}}", "{{componentsStubUrl}}"}
FOLDERS = [
    "0. Preparación",
    "1. Contrato de salud (público)",
    "2. Registro",
    "3. Componentes caídos",
    "4. Errores del registro",
    "5. Control de acceso",
]


@pytest.fixture
def collection() -> dict:
    """A fresh copy of the real collection that a test may alter."""
    return load_json(HEALTH_COLLECTION)


@pytest.fixture(scope="module")
def environment() -> dict:
    return load_json(POSTMAN / "environments" / "e2e.postman_environment.json")


def all_requests(collection: dict) -> list[dict]:
    return list(requests_of(collection["item"]))


def operation_prefixes(collection: dict, helpers: set[str]) -> set[str]:
    return {
        prefix_of(r["name"]) for r in all_requests(collection) if prefix_of(r["name"]) not in helpers
    }


def checks_script_of(request: dict) -> str:
    return "\n".join(
        line for e in request.get("event", []) if e["listen"] == "test" for line in e["script"]["exec"]
    )


# --- G1: format ---


def check_format(collection: dict) -> list[str]:
    schema = collection.get("info", {}).get("schema", "")
    return [] if schema.endswith(SCHEMA_SUFFIX) else [f"info.schema is not the v2.1 one: {schema!r}"]


# --- G2: the operations of the API, in both directions ---


def check_operations(collection: dict, api_operations: set[str]) -> list[str]:
    problems = []
    names = [r["name"] for r in all_requests(collection)]
    for name in names:
        if ": " not in name:
            problems.append(f"the name «{name}» must be «<operationId>: <description>»")
    if len(set(names)) != len(names):
        problems.append(f"repeated request names: {sorted({n for n in names if names.count(n) > 1})}")
    if problems:
        return problems
    covered = operation_prefixes(collection, HEALTH_HELPER_PREFIXES)
    for missing in sorted(api_operations - covered):
        problems.append(f"operation without a request: {missing}")
    for extra in sorted(covered - api_operations):
        problems.append(f"request of an operation that the API does not have: {extra}")
    return problems


# --- G3: descriptions and visible checks ---


def check_descriptions_and_tests(collection: dict) -> list[str]:
    problems = []
    if not collection.get("info", {}).get("description", "").strip():
        problems.append("the collection has no description")
    for folder in folders_of(collection["item"]):
        if not folder.get("description", "").strip():
            problems.append(f"the folder «{folder['name']}» has no description")
    for request in all_requests(collection):
        if not request["request"].get("description", "").strip():
            problems.append(f"the request «{request['name']}» has no description")
        if "pm.test(" not in checks_script_of(request):
            problems.append(f"the request «{request['name']}» has no pm.test")
    return problems


# --- G4: every status has a case ---


def check_statuses(collection: dict) -> list[str]:
    covered = set()
    for request in all_requests(collection):
        if prefix_of(request["name"]) in HEALTH_HELPER_PREFIXES:
            continue
        covered |= {int(code) for code in re.findall(r"have\.status\((\d{3})\)", checks_script_of(request))}
    return [f"status without a case: {code}" for code in STATUSES if code not in covered]


# --- G5: authentication only references variables ---


def check_authentication(collection: dict) -> list[str]:
    problems = []
    if collection.get("auth", {}).get("bearer", [{}])[0].get("value") != "{{accessToken}}":
        problems.append("the authentication of the collection must be Bearer {{accessToken}}")
    for request in all_requests(collection):
        auth = request["request"].get("auth")
        if auth is None or auth["type"] == "noauth":
            continue
        value = auth["bearer"][0]["value"] if auth["type"] == "bearer" else None
        if value not in ALLOWED_TOKENS:
            problems.append(f"«{request['name']}» authenticates with {value!r}")
    return problems


# --- G6: no secrets ---


def check_no_secrets(collection: dict) -> list[str]:
    text = json.dumps(collection, ensure_ascii=False)
    problems = []
    if JWT_PATTERN.search(text):
        problems.append("the collection contains something that looks like a JWT")
    if BEARER_LITERAL_PATTERN.search(text):
        problems.append("the collection writes a Bearer token")
    if "secret" in text.lower():
        problems.append("the collection mentions a secret")
    for variable in collection.get("variable", []):
        key, value = variable["key"], str(variable.get("value", ""))
        if re.search(r"token|secret|password", key, re.IGNORECASE) and value:
            problems.append(f"the variable «{key}» has a value")
        if HIGH_ENTROPY_PATTERN.fullmatch(value):
            problems.append(f"the value of the variable «{key}» looks like a key")
    return problems


# --- G7: only the registry is written, and the simulations only through /__test__/ ---


def check_scope(collection: dict) -> list[str]:
    problems = []
    for request in all_requests(collection):
        name, spec = request["name"], request["request"]
        host, path = spec["url"]["host"][0], spec["url"]["path"]
        if host in SIMULATIONS:
            if path[:1] != ["__test__"]:
                problems.append(f"«{name}» must use {host} only through /__test__/")
        elif host == "{{baseUrl}}":
            if any(path[:3] == forbidden for forbidden in FORBIDDEN_RESOURCES):
                problems.append(f"«{name}» must not touch the subscriptions or the dashboard")
            if spec["method"] != "GET" and path[:3] != REGISTRY_PATH:
                problems.append(f"«{name}» writes outside the registry of components")
        else:
            problems.append(f"«{name}» uses the host {host}, which is not part of the stack")
    return problems


# --- G8: no variable that the environment would hide ---


def check_variable_names(collection: dict, environment: dict) -> list[str]:
    keys = {value["key"] for value in environment["values"]}
    hidden = sorted({v["key"] for v in collection.get("variable", [])} & keys)
    return [f"the environment variable «{key}» would hide the one of the collection" for key in hidden]


# =========================== the real collection passes every rule ===========================


def test_g1_the_collection_is_a_v2_1_json_document(collection):
    assert check_format(collection) == []


def test_g2_the_requests_cover_exactly_the_ten_health_operations(collection):
    assert check_operations(collection, health_operation_ids()) == []
    assert health_operation_ids() == {
        "get_health_live",
        "get_health_ready",
        "get_info",
        "get_health_status",
        "get_health",
        "list_monitored_components",
        "create_monitored_component",
        "get_monitored_component",
        "update_monitored_component",
        "delete_monitored_component",
    }


def test_g3_everything_is_described_and_every_request_checks_its_answer(collection):
    assert check_descriptions_and_tests(collection) == []


def test_g4_every_status_of_the_contract_has_a_case(collection):
    assert check_statuses(collection) == []


def test_g5_the_authentication_only_references_variables(collection):
    assert check_authentication(collection) == []


def test_g6_the_collection_holds_no_token_and_no_secret(collection):
    assert check_no_secrets(collection) == []


def test_g7_only_the_registry_is_written_and_the_simulations_only_through_the_test_surface(collection):
    assert check_scope(collection) == []


def test_g8_no_variable_of_the_environment_hides_one_of_the_collection(collection, environment):
    assert check_variable_names(collection, environment) == []


def test_the_collection_has_the_six_folders_of_the_contract(collection):
    assert [folder["name"] for folder in collection["item"]] == FOLDERS
    assert [len(folder["item"]) for folder in collection["item"]] == [3, 6, 14, 5, 9, 10]


def test_the_environment_knows_the_simulation_of_the_components(environment):
    values = {value["key"]: value["value"] for value in environment["values"]}

    assert values["componentsStubUrl"] == "http://127.0.0.1:8014"


def test_the_scripts_of_newman_run_the_health_collection_alone_and_with_the_others():
    scripts = load_json(POSTMAN / "package.json")["scripts"]

    assert "MailySoft-System-Salud.postman_collection.json" in scripts["e2e:health"]
    assert "junit-health.xml" in scripts["e2e:health"]
    assert scripts["e2e:all"] == "npm run e2e && npm run e2e:dashboard && npm run e2e:health"


# ================== the rules detect what they are for (altered in-memory copies) ==================


def without_requests(collection: dict, keep) -> dict:
    changed = copy.deepcopy(collection)
    for folder in changed["item"]:
        folder["item"] = [r for r in folder["item"] if keep(r)]
    return changed


def request_named(collection: dict, start: str) -> dict:
    return next(r for r in all_requests(collection) if r["name"].startswith(start))


def test_g1_detects_another_format(collection):
    collection["info"]["schema"] = "https://schema.getpostman.com/json/collection/v2.0.0/collection.json"

    assert check_format(collection)


def test_g2_detects_a_missing_operation_a_foreign_one_and_a_repeated_name(collection):
    api = health_operation_ids()
    missing = without_requests(collection, lambda r: not r["name"].startswith("get_info"))
    assert any("get_info" in p for p in check_operations(missing, api))

    foreign = copy.deepcopy(collection)
    extra = copy.deepcopy(request_named(foreign, "get_info"))
    extra["name"] = "purge_health: no existe"
    foreign["item"][1]["item"].append(extra)
    assert any("purge_health" in p for p in check_operations(foreign, api))

    repeated = copy.deepcopy(collection)
    repeated["item"][1]["item"].append(copy.deepcopy(request_named(repeated, "get_info")))
    assert any("repeated" in p for p in check_operations(repeated, api))


def test_g3_detects_a_request_without_checks_and_a_folder_without_description(collection):
    request_named(collection, "get_info")["event"] = []
    collection["item"][3]["description"] = "  "

    problems = check_descriptions_and_tests(collection)

    assert any("get_info" in p and "pm.test" in p for p in problems)
    assert any("3. Componentes caídos" in p for p in problems)


def test_g4_detects_a_status_without_a_case(collection):
    kept = without_requests(
        collection, lambda r: "have.status(204)" not in json.dumps(r["event"]) or r["name"].startswith("setup")
    )

    assert check_statuses(kept) == ["status without a case: 204"]


def test_g5_detects_a_literal_token_and_another_authentication(collection):
    request_named(collection, "get_health: sin permisos")["request"]["auth"] = {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "abc123", "type": "string"}],
    }
    collection["auth"]["bearer"][0]["value"] = "{{plainToken}}"

    problems = check_authentication(collection)

    assert any("abc123" in p for p in problems)
    assert any("accessToken" in p for p in problems)


@pytest.mark.parametrize(
    "intruder",
    [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.cuerpo.firma",  # a JWT
        "Authorization: Bearer abcdefgh12345678",  # a written token
        "la palabra secret no se escribe",  # the forbidden word
    ],
)
def test_g6_detects_something_that_looks_like_a_secret(collection, intruder):
    collection["info"]["description"] += " " + intruder

    assert check_no_secrets(collection)


def test_g6_the_marker_of_the_simulation_is_not_written_whole(collection):
    # The simulation puts a marker in every failure body and the collection checks that it never
    # reaches the client; the script builds it in two pieces so that the file never holds the word.
    scripts = "\n".join(checks_script_of(request) for request in all_requests(collection))

    assert '"SECRE" + "TO-INTERNO"' in scripts
    assert "secret" not in json.dumps(collection, ensure_ascii=False).lower()


def test_g6_detects_a_token_variable_with_a_value_and_a_value_that_looks_like_a_key(collection):
    collection["variable"] += [
        {"key": "accessToken", "value": "x"},
        {"key": "otra", "value": "A" * 40},
    ]

    problems = check_no_secrets(collection)

    assert any("accessToken" in p for p in problems)
    assert any("otra" in p for p in problems)


def test_g7_detects_a_write_outside_the_registry_and_a_path_into_other_resources(collection):
    request_named(collection, "get_health: aparecen")["request"]["method"] = "POST"
    request_named(collection, "get_health_live")["request"]["url"]["path"] = ["api", "v1", "subscriptions"]
    request_named(collection, "get_info")["request"]["url"]["path"] = ["api", "v1", "dashboard"]
    request_named(collection, "setup: reiniciar la simulación de componentes")["request"]["url"]["path"] = [
        "healthy",
        "health",
        "live",
    ]
    request_named(collection, "setup: vaciar el registro")["request"]["url"]["host"] = ["{{clinicsStubUrl}}"]

    problems = check_scope(collection)

    assert any("get_health: aparecen" in p and "outside the registry" in p for p in problems)
    assert any("get_health_live" in p and "subscriptions" in p for p in problems)
    assert any("get_info" in p and "dashboard" in p for p in problems)
    assert any("reiniciar la simulación de componentes" in p and "__test__" in p for p in problems)
    assert any("vaciar el registro" in p and "clinicsStubUrl" in p for p in problems)


def test_g8_detects_a_variable_that_the_environment_would_hide(collection, environment):
    collection["variable"].append({"key": "componentsStubUrl", "value": ""})

    assert check_variable_names(collection, environment) == [
        "the environment variable «componentsStubUrl» would hide the one of the collection"
    ]

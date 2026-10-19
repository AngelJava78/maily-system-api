"""The Postman collection of the dashboard is complete, read-only and holds no secrets (spec 003).

Rules G1 to G9 of `specs/003-platform-dashboard/contracts/e2e-collection.md`. They only read files of
the repository and the OpenAPI document that the application generates: no service, no Node.js, no
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
    COLLECTION,
    DASHBOARD_COLLECTION,
    DASHBOARD_HELPER_PREFIXES,
    DASHBOARD_PREFIX,
    E2E_HELPER_PREFIXES,
    HIGH_ENTROPY_PATTERN,
    JWT_PATTERN,
    MANUAL_COLLECTION,
    MANUAL_HELPER_PREFIXES,
    POSTMAN,
    folders_of,
    load_json,
    operation_ids_of_the_api,
    prefix_of,
    requests_of,
)

STATUSES = (200, 401, 403, 422, 503)
ALLOWED_TOKENS = {"{{plainToken}}", "{{subscriptionsToken}}", "{{badToken}}"}
SCHEMA_SUFFIX = "/collection/v2.1.0/collection.json"


@pytest.fixture
def collection() -> dict:
    """A fresh copy of the real collection that a test may alter."""
    return load_json(DASHBOARD_COLLECTION)


@pytest.fixture(scope="module")
def environment() -> dict:
    return load_json(POSTMAN / "environments" / "e2e.postman_environment.json")


def all_requests(collection: dict) -> list[dict]:
    return list(requests_of(collection["item"]))


def operation_prefixes(collection: dict, helpers: set[str]) -> set[str]:
    return {
        prefix_of(r["name"]) for r in all_requests(collection) if prefix_of(r["name"]) not in helpers
    }


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
    covered = operation_prefixes(collection, DASHBOARD_HELPER_PREFIXES)
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
        tests = [e for e in request.get("event", []) if e["listen"] == "test"]
        if not tests or not any("pm.test(" in line for e in tests for line in e["script"]["exec"]):
            problems.append(f"the request «{request['name']}» has no pm.test")
    return problems


# --- G4: every status has a case ---


def check_statuses(collection: dict) -> list[str]:
    covered = set()
    for request in all_requests(collection):
        if prefix_of(request["name"]) in DASHBOARD_HELPER_PREFIXES:
            continue
        script = "\n".join(
            line for e in request.get("event", []) if e["listen"] == "test" for line in e["script"]["exec"]
        )
        covered |= {int(code) for code in re.findall(r"have\.status\((\d{3})\)", script)}
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


# --- G7: read-only on the API, only the simulation is written ---


def check_read_only(collection: dict) -> list[str]:
    problems = []
    for request in all_requests(collection):
        name, spec = request["name"], request["request"]
        host, path = spec["url"]["host"][0], spec["url"]["path"]
        if prefix_of(name) == "setup":
            # A `setup` request either drives the simulation of the users API or reads the
            # published contract (a GET to /openapi.json) to know the API is up.
            drives_the_simulation = host == "{{usersStubUrl}}" and path[:1] == ["__test__"]
            reads_the_contract = (
                host == "{{baseUrl}}" and spec["method"] == "GET" and path == ["openapi.json"]
            )
            if not (drives_the_simulation or reads_the_contract):
                problems.append(
                    f"«{name}» must drive {{{{usersStubUrl}}}}/__test__/ or GET /openapi.json"
                )
        else:
            if host != "{{baseUrl}}" or spec["method"] != "GET":
                problems.append(f"«{name}» must be a GET to {{{{baseUrl}}}}")
            if path[:3] == ["api", "v1", "subscriptions"]:
                problems.append(f"«{name}» must not touch the subscriptions")
    return problems


# --- G8: no variable that the environment would hide ---


def check_variable_names(collection: dict, environment: dict) -> list[str]:
    keys = {value["key"] for value in environment["values"]}
    hidden = sorted({v["key"] for v in collection.get("variable", [])} & keys)
    return [f"the environment variable «{key}» would hide the one of the collection" for key in hidden]


# --- G9: the three collections together cover the API ---


def check_union(prefixes_by_collection: dict[str, set[str]], api_operations: set[str]) -> list[str]:
    covered = set().union(*prefixes_by_collection.values())
    problems = [f"operation without a request in any collection: {m}" for m in sorted(api_operations - covered)]
    problems += [f"request of an operation that the API does not have: {x}" for x in sorted(covered - api_operations)]
    return problems


def prefixes_of_the_three(dashboard: dict) -> dict[str, set[str]]:
    return {
        "subscriptions (e2e)": operation_prefixes(load_json(COLLECTION), E2E_HELPER_PREFIXES),
        "subscriptions (manual)": operation_prefixes(load_json(MANUAL_COLLECTION), MANUAL_HELPER_PREFIXES),
        "dashboard": operation_prefixes(dashboard, DASHBOARD_HELPER_PREFIXES),
    }


# =========================== the real collection passes every rule ===========================


def test_g1_the_collection_is_a_v2_1_json_document(collection):
    assert check_format(collection) == []


def test_g2_the_requests_cover_exactly_the_operations_under_the_dashboard_path(collection):
    assert check_operations(collection, operation_ids_of_the_api(DASHBOARD_PREFIX)) == []
    assert operation_ids_of_the_api(DASHBOARD_PREFIX) == {"get_dashboard"}


def test_g3_everything_is_described_and_every_request_checks_its_answer(collection):
    assert check_descriptions_and_tests(collection) == []


def test_g4_every_status_of_the_contract_has_a_case(collection):
    assert check_statuses(collection) == []


def test_g5_the_authentication_only_references_variables(collection):
    assert check_authentication(collection) == []


def test_g6_the_collection_holds_no_token_and_no_secret(collection):
    assert check_no_secrets(collection) == []


def test_g7_the_api_is_only_read_and_only_the_simulation_is_written(collection):
    assert check_read_only(collection) == []


def test_g8_no_variable_of_the_environment_hides_one_of_the_collection(collection, environment):
    assert check_variable_names(collection, environment) == []


def test_g9_the_three_collections_together_cover_exactly_the_operations_of_the_api(collection):
    assert check_union(prefixes_of_the_three(collection), operation_ids_of_the_api("/")) == []


def test_the_collection_has_the_four_folders_and_twenty_four_requests(collection):
    assert [folder["name"] for folder in collection["item"]] == [
        "0. Preparación",
        "1. Resumen",
        "2. limit inválido (422)",
        "3. Control de acceso",
    ]
    assert len(all_requests(collection)) == 24


# ================== the rules detect what they are for (altered in-memory copies) ==================


def without_requests(collection: dict, keep) -> dict:
    changed = copy.deepcopy(collection)
    for folder in changed["item"]:
        folder["item"] = [r for r in folder["item"] if keep(r)]
    return changed


def first_dashboard_request(collection: dict) -> dict:
    return next(r for r in all_requests(collection) if r["name"].startswith("get_dashboard: limit=3"))


def test_g1_detects_another_format(collection):
    collection["info"]["schema"] = "https://schema.getpostman.com/json/collection/v2.0.0/collection.json"

    assert check_format(collection)


def test_g2_detects_a_missing_operation_a_foreign_one_and_a_repeated_name(collection):
    api = operation_ids_of_the_api(DASHBOARD_PREFIX)
    missing = without_requests(collection, lambda r: not r["name"].startswith("get_dashboard"))
    assert any("get_dashboard" in p for p in check_operations(missing, api))

    foreign = copy.deepcopy(collection)
    extra = copy.deepcopy(first_dashboard_request(foreign))
    extra["name"] = "delete_dashboard: no existe"
    foreign["item"][1]["item"].append(extra)
    assert any("delete_dashboard" in p for p in check_operations(foreign, api))

    repeated = copy.deepcopy(collection)
    repeated["item"][1]["item"].append(copy.deepcopy(first_dashboard_request(repeated)))
    assert any("repeated" in p for p in check_operations(repeated, api))


def test_g3_detects_a_request_without_checks_and_a_folder_without_description(collection):
    first_dashboard_request(collection)["event"] = []
    collection["item"][2]["description"] = "  "

    problems = check_descriptions_and_tests(collection)

    assert any("limit=3" in p and "pm.test" in p for p in problems)
    assert any("2. limit inválido" in p for p in problems)


def test_g4_detects_a_status_without_a_case(collection):
    kept = without_requests(
        collection, lambda r: "have.status(503)" not in json.dumps(r["event"]) or r["name"].startswith("setup")
    )

    assert check_statuses(kept) == ["status without a case: 503"]


def test_g5_detects_a_literal_token_and_another_authentication(collection):
    first_dashboard_request(collection)["request"]["auth"] = {
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


def test_g6_detects_a_token_variable_with_a_value_and_a_value_that_looks_like_a_key(collection):
    collection["variable"] += [
        {"key": "accessToken", "value": "x"},
        {"key": "otra", "value": "A" * 40},
    ]

    problems = check_no_secrets(collection)

    assert any("accessToken" in p for p in problems)
    assert any("otra" in p for p in problems)


def test_g7_detects_a_write_and_a_path_into_the_subscriptions(collection):
    request = first_dashboard_request(collection)
    request["request"]["method"] = "POST"
    other = next(r for r in all_requests(collection) if r["name"].startswith("get_dashboard: limit=1 "))
    other["request"]["url"]["path"] = ["api", "v1", "subscriptions"]
    stub = next(r for r in all_requests(collection) if r["name"].startswith("setup: reiniciar"))
    stub["request"]["url"]["host"] = ["{{baseUrl}}"]

    problems = check_read_only(collection)

    assert any("limit=3" in p for p in problems)
    assert any("subscriptions" in p for p in problems)
    assert any("setup: reiniciar" in p for p in problems)


def test_g8_detects_a_variable_that_the_environment_would_hide(collection, environment):
    collection["variable"].append({"key": "baseUrl", "value": ""})

    assert check_variable_names(collection, environment) == [
        "the environment variable «baseUrl» would hide the one of the collection"
    ]


def test_g9_detects_an_operation_that_no_collection_covers(collection):
    prefixes = prefixes_of_the_three(collection)
    prefixes["dashboard"] = set()  # as if the dashboard collection did not exist

    problems = check_union(prefixes, operation_ids_of_the_api("/"))

    assert problems == ["operation without a request in any collection: get_dashboard"]

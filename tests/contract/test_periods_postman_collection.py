"""The Postman collection of the subscription periods is complete and holds no secrets (spec 010).

Rules G1 to G8 of `specs/010-subscription-periods/contracts/e2e-collection.md`; G9 (the collections
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
    HIGH_ENTROPY_PATTERN,
    JWT_PATTERN,
    PERIODS_COLLECTION,
    PERIODS_HELPER_PREFIXES,
    PERIODS_PREFIX,
    POSTMAN,
    folders_of,
    load_json,
    operation_ids_of_the_api,
    prefix_of,
    requests_of,
)
from tests.helpers import ROOT

STATUSES = (200, 201, 401, 403, 404, 409, 422, 503)
ALLOWED_TOKENS = {
    "{{ownerToken}}",
    "{{readerToken}}",
    "{{plainToken}}",
    "{{adminToken}}",
    "{{badToken}}",
}
SCHEMA_SUFFIX = "/collection/v2.1.0/collection.json"
PERIODS_PATH = ["api", "v1", "subscription-periods"]
SUBSCRIPTIONS_PATH = ["api", "v1", "subscriptions"]
SIMULATIONS = {"{{usersStubUrl}}", "{{clinicsStubUrl}}", "{{paymentsStubUrl}}"}
FOLDERS = [
    "0. Preparación",
    "1. Consulta",
    "2. Iniciar el pago",
    "3. Pago aprobado",
    "4. Control de acceso",
    "5. Degradación",
    "6. Contrato",
    "7. Limpieza",
]
REQUESTS_PER_FOLDER = [7, 12, 8, 27, 11, 14, 2, 6]
OPERATIONS = {"get_subscription_period", "create_subscription_payment", "list_subscription_charges"}


@pytest.fixture
def collection() -> dict:
    """A fresh copy of the real collection that a test may alter."""
    return load_json(PERIODS_COLLECTION)


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
    covered = operation_prefixes(collection, PERIODS_HELPER_PREFIXES)
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
        if prefix_of(request["name"]) in PERIODS_HELPER_PREFIXES:
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


# --- G7: the API is only written by paying and by the preparation, the simulations through /__test__/ ---


def check_scope(collection: dict) -> list[str]:
    problems = []
    for request in all_requests(collection):
        name, spec = request["name"], request["request"]
        host, path, method = spec["url"]["host"][0], spec["url"]["path"], spec["method"]
        helper = prefix_of(name) in PERIODS_HELPER_PREFIXES
        if host in SIMULATIONS:
            if path[:1] != ["__test__"]:
                problems.append(f"«{name}» must use {host} only through /__test__/")
        elif host == "{{baseUrl}}":
            if path[:3] == PERIODS_PATH:
                if method != "GET" and not (method == "POST" and len(path) == 5 and path[-1] == "payments"):
                    problems.append(f"«{name}» writes the periods in a way other than POST …/payments")
            elif path[:3] == SUBSCRIPTIONS_PATH:
                if method != "GET" and not (helper and method in ("POST", "DELETE")):
                    problems.append(f"«{name}» writes the catalog outside the preparation and the cleanup")
            elif not (method == "GET" and path == ["openapi.json"]):
                problems.append(f"«{name}» touches a route that this collection does not use: /{'/'.join(path)}")
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


def test_g2_the_requests_cover_exactly_the_three_operations_of_the_periods(collection):
    assert operation_ids_of_the_api(PERIODS_PREFIX) == OPERATIONS
    assert check_operations(collection, operation_ids_of_the_api(PERIODS_PREFIX)) == []


def test_g3_everything_is_described_and_every_request_checks_its_answer(collection):
    assert check_descriptions_and_tests(collection) == []


def test_g4_every_status_of_the_contract_has_a_case(collection):
    assert check_statuses(collection) == []


def test_g5_the_authentication_only_references_variables(collection):
    assert check_authentication(collection) == []


def test_g6_the_collection_holds_no_token_and_no_secret(collection):
    assert check_no_secrets(collection) == []


def test_g7_the_api_is_only_written_by_paying_and_the_simulations_only_through_the_test_surface(collection):
    assert check_scope(collection) == []


def test_g8_no_variable_of_the_environment_hides_one_of_the_collection(collection, environment):
    assert check_variable_names(collection, environment) == []


def test_the_collection_has_the_eight_folders_of_the_contract(collection):
    assert [folder["name"] for folder in collection["item"]] == FOLDERS
    assert [len(folder["item"]) for folder in collection["item"]] == REQUESTS_PER_FOLDER


def test_the_five_people_of_the_collection_are_the_ones_of_the_contract(collection):
    script = "\n".join(
        line for e in collection["event"] if e["listen"] == "prerequest" for line in e["script"]["exec"]
    )

    for token, permissions in {
        "ownerToken": ["subscription_periods:read", "subscription_periods:write"],
        "readerToken": ["subscription_periods:read"],
        "plainToken": [],
        "adminToken": ["modules:read"],
    }.items():
        assert f'register("{token}"' in script
        for permission in permissions:
            assert f'"{permission}"' in script
    assert '"e2e-invalid-"' in script  # the invalid one is only made up, never registered
    assert 'register("badToken"' not in script


def test_the_collection_exercises_the_scenarios_that_the_contract_lists(collection):
    names = "\n".join(r["name"] for r in all_requests(collection))

    for fragment in (
        "en prueba, faltan 9 días",
        "vencida, 26 días de atraso",
        "sin prueba",
        "sin cobro",
        "periodo de cobro anual",
        "repetirlo devuelve el mismo checkout",
        "el pago aprobado mueve la fecha un mes",
        "una segunda consulta no la mueve otra vez",
        "un pago rechazado no mueve la fecha",
        "un pago aprobado con otro importe no se aplica",
        "un pago creado por otra vía no mueve la fecha",
        "sin token responde 401",
        "con solo lectura responde 403",
        "la organización de otra persona responde 404",
        "el permiso se comprueba antes que el formato",
        "con Usuarios caído responde 503",
        "con Clínicas caída responde 503",
        "Clínicas sin periodo de cobro responde 503",
        "con Pagos caído devuelve lo guardado y no verifica",
        "con Pagos caído responde 503",
    ):
        assert fragment in names, fragment


def test_the_environment_knows_the_simulation_of_the_payments_api(environment):
    values = {value["key"]: value["value"] for value in environment["values"]}

    assert values["paymentsStubUrl"] == "http://127.0.0.1:8015"


def test_the_scripts_of_newman_run_the_periods_collection_alone_and_with_the_others():
    scripts = load_json(POSTMAN / "package.json")["scripts"]

    assert "MailySoft-System-Periodos.postman_collection.json" in scripts["e2e:periods"]
    assert "junit-periods.xml" in scripts["e2e:periods"]
    assert "e2e.postman_environment.json" in scripts["e2e:periods"]
    assert scripts["e2e:all"].endswith("npm run e2e:periods")
    assert {"e2e", "e2e:dashboard", "e2e:health"} <= {
        part.removeprefix("npm run ") for part in scripts["e2e:all"].split(" && ")
    }


def test_the_isolated_stack_has_the_simulation_of_the_payments_api_and_the_variables_of_the_api():
    stack = (POSTMAN / "docker-compose.e2e.yml").read_text(encoding="utf-8")

    assert "payments-api-stub:" in stack
    assert "./tests/stubs/payments_api:/stub:ro" in stack
    assert "${E2E_PAYMENTS_STUB_PORT:-8015}" in stack
    assert "PAYMENTS_API_BASE_URL: http://payments-api-stub:8080" in stack
    assert 'BILLING_CUTOFF_AT: "2020-01-01T00:00:00Z"' in stack
    # The API waits for the simulation: otherwise its first consultation could find it down.
    api_section = stack[stack.index("\n  api:") :]
    assert re.search(r"payments-api-stub:\s*\n\s*condition: service_healthy", api_section)


def test_every_simulation_that_the_collection_touches_exists_in_the_repository():
    for stub in ("users_api", "clinics_api", "payments_api"):
        assert (ROOT / "tests" / "stubs" / stub / "app.py").is_file()


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
    api = operation_ids_of_the_api(PERIODS_PREFIX)
    missing = without_requests(collection, lambda r: not r["name"].startswith("create_subscription_payment"))
    assert any("create_subscription_payment" in p for p in check_operations(missing, api))

    foreign = copy.deepcopy(collection)
    extra = copy.deepcopy(request_named(foreign, "get_subscription_period"))
    extra["name"] = "cancel_subscription_period: no existe"
    foreign["item"][1]["item"].append(extra)
    assert any("cancel_subscription_period" in p for p in check_operations(foreign, api))

    repeated = copy.deepcopy(collection)
    repeated["item"][1]["item"].append(copy.deepcopy(request_named(repeated, "get_subscription_period")))
    assert any("repeated" in p for p in check_operations(repeated, api))

    unnamed = copy.deepcopy(collection)
    request_named(unnamed, "get_subscription_period")["name"] = "consultar"
    assert any("must be" in p for p in check_operations(unnamed, api))


def test_g3_detects_a_request_without_checks_and_a_folder_without_description(collection):
    request_named(collection, "get_subscription_period: en prueba")["event"] = []
    collection["item"][3]["description"] = "  "
    request_named(collection, "create_subscription_payment: crea el cobro")["request"]["description"] = ""

    problems = check_descriptions_and_tests(collection)

    assert any("en prueba" in p and "pm.test" in p for p in problems)
    assert any("3. Pago aprobado" in p for p in problems)
    assert any("crea el cobro" in p and "description" in p for p in problems)


@pytest.mark.parametrize("status", STATUSES)
def test_g4_detects_a_status_without_a_case(collection, status):
    marker = f"have.status({status})"
    kept = without_requests(
        collection,
        lambda r: marker not in json.dumps(r["event"]) or prefix_of(r["name"]) in PERIODS_HELPER_PREFIXES,
    )

    assert check_statuses(kept) == [f"status without a case: {status}"]


def test_g5_detects_a_literal_token_and_another_authentication(collection):
    request_named(collection, "get_subscription_period: sin permiso")["request"]["auth"] = {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "abc123", "type": "string"}],
    }
    request_named(collection, "create_subscription_payment: token inválido")["request"]["auth"] = {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "{{subscriptionsToken}}", "type": "string"}],
    }
    collection["auth"]["bearer"][0]["value"] = "{{plainToken}}"

    problems = check_authentication(collection)

    assert any("abc123" in p for p in problems)
    assert any("subscriptionsToken" in p for p in problems)
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
    # The simulations put a marker in every failure body and the collection checks that it never reaches
    # the client; the script builds it in two pieces so that the file never holds the word.
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


def test_g7_detects_a_write_to_the_periods_a_write_to_the_catalog_and_a_foreign_route(collection):
    request_named(collection, "get_subscription_period: en prueba")["request"]["method"] = "DELETE"
    consult = request_named(collection, "get_subscription_period: la misma consulta")
    consult["request"]["url"]["path"] = ["api", "v1", "subscriptions", "1"]
    consult["request"]["method"] = "PATCH"
    request_named(collection, "get_subscription_period: sin token")["request"]["url"]["path"] = [
        "api",
        "v1",
        "dashboard",
    ]
    request_named(collection, "setup: reiniciar la simulación del API de pagos")["request"]["url"]["path"] = [
        "api",
        "v1",
        "payments",
    ]
    request_named(collection, "setup: reiniciar la simulación del API de clínicas")["request"]["url"]["host"] = [
        "{{componentsStubUrl}}"
    ]
    # A write to the catalog that is not part of the preparation or the cleanup.
    sneaky = copy.deepcopy(request_named(collection, "setup: crear el plan con prueba"))
    sneaky["name"] = "get_subscription_period: crea un plan a escondidas"
    collection["item"][1]["item"].append(sneaky)

    problems = check_scope(collection)

    assert any("en prueba" in p and "POST …/payments" in p for p in problems)
    assert any("la misma consulta" in p and "outside the preparation" in p for p in problems)
    assert any("sin token" in p and "does not use" in p for p in problems)
    assert any("API de pagos" in p and "__test__" in p for p in problems)
    assert any("API de clínicas" in p and "componentsStubUrl" in p for p in problems)
    assert any("a escondidas" in p and "outside the preparation" in p for p in problems)


def test_g7_allows_the_preparation_and_the_cleanup_to_write_the_catalog_and_paying_to_post(collection):
    assert check_scope(collection) == []
    writes = [
        (r["request"]["method"], r["request"]["url"]["path"][:3], prefix_of(r["name"]))
        for r in all_requests(collection)
        if r["request"]["url"]["host"] == ["{{baseUrl}}"] and r["request"]["method"] != "GET"
    ]
    assert {("POST", tuple(SUBSCRIPTIONS_PATH), "setup"), ("DELETE", tuple(SUBSCRIPTIONS_PATH), "setup")} <= {
        (m, tuple(p), who) for m, p, who in writes
    }
    assert ("POST", tuple(PERIODS_PATH), "create_subscription_payment") in {
        (m, tuple(p), who) for m, p, who in writes
    }


def test_g8_detects_a_variable_that_the_environment_would_hide(collection, environment):
    collection["variable"].append({"key": "paymentsStubUrl", "value": ""})

    assert check_variable_names(collection, environment) == [
        "the environment variable «paymentsStubUrl» would hide the one of the collection"
    ]

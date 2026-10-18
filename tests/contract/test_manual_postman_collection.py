"""The manual Postman collection (spec 002) follows the API and holds no secrets.

It runs with `uv run pytest` and needs neither a running service nor Node.js nor Postman: it only
reads the JSON files of `tests/postman/` and the OpenAPI document that the application generates.

Every rule (D0 to D11 of `specs/002-manual-postman-collection/contracts/drift-test.md`) is a pure
function `check_*(...) -> list[str]` that returns the problems it finds (an empty list when all is
well). The tests run each rule on the real files and, to prove that the rules do bite, on in-memory
copies that were broken on purpose.
"""

import copy
import re
from collections.abc import Iterator
from typing import Any

import pytest

from tests.contract.postman_support import (
    BEARER_LITERAL_PATTERN,
    COLLECTION as E2E_COLLECTION,
    HIGH_ENTROPY_PATTERN,
    JWT_PATTERN,
    MANUAL_COLLECTION,
    MANUAL_ENVIRONMENTS,
    MANUAL_HELPER_PREFIXES,
    folders_of,
    load_json,
    operation_ids_of_the_api,
    requests_of,
    scripts_of,
)

LIFECYCLE_FOLDER = "1. "
ERRORS_FOLDER = "2. "
ERROR_STATUSES = {401, 403, 404, 409, 422, 503}
ENVIRONMENT_KEYS = {
    "baseUrl",
    "auth0Domain",
    "auth0Audience",
    "auth0ClientId",
    "auth0ClientSecret",
    "plainClientId",
    "plainClientSecret",
    "clinicsStubUrl",
    "testDatabaseNotice",
}
SECRET_ENVIRONMENT_KEYS = {"auth0ClientSecret", "plainClientSecret"}
ACCESS_ENVIRONMENT_KEYS = {
    "auth0Domain",
    "auth0Audience",
    "auth0ClientId",
    "auth0ClientSecret",
    "plainClientId",
    "plainClientSecret",
}
SECRET_NAME_PATTERN = re.compile(r"token|secret|password", re.IGNORECASE)
CONSOLE_CALL_PATTERN = re.compile(r"console\.(?:log|info|warn|error|debug)\s*\(")
CONSOLE_FORBIDDEN_PATTERN = re.compile(r"secret|access_token|accessToken|plainToken", re.IGNORECASE)
NAME_PATTERN = re.compile(r"^([a-z_]+): (.+)$")
VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")
MUTATING_METHODS = {"PATCH", "PUT", "DELETE"}
OWNED_VARIABLES = {"subscriptionId", "otherSubscriptionId"}
READ_ONLY_VARIABLES = {"deletedSubscriptionId", "nonexistentSubscriptionId"}


# --- Helpers -------------------------------------------------------------------------------------


def strings_of(value: Any) -> Iterator[str]:
    """Every string of a JSON document, keys excluded."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings_of(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings_of(child)


def url_of(request: dict) -> str:
    return request["request"]["url"]["raw"]


def body_of(request: dict) -> str:
    return request["request"].get("body", {}).get("raw", "")


def method_of(request: dict) -> str:
    return request["request"]["method"]


def prefix_and_description(name: str) -> tuple[str, str] | None:
    match = NAME_PATTERN.match(name)
    return (match.group(1), match.group(2)) if match else None


def all_scripts(collection: dict) -> list[tuple[str, str]]:
    """(owner, text) of every script of the collection: its own, the folders' and the requests'."""
    scripts = [("la colección", scripts_of(collection, "prerequest"))]
    for item in [*folders_of(collection["item"]), *requests_of(collection["item"])]:
        for listen in ("prerequest", "test"):
            scripts.append((f"«{item['name']}» ({listen})", scripts_of(item, listen)))
    return [(owner, text) for owner, text in scripts if text]


# --- D0: format ----------------------------------------------------------------------------------


def check_format(collection: dict, environments: dict[str, dict]) -> list[str]:
    problems = []
    if not collection.get("info", {}).get("schema", "").endswith("/collection/v2.1.0/collection.json"):
        problems.append("la colección no está en formato Postman v2.1")
    for file_name, environment in environments.items():
        if environment.get("_postman_variable_scope") != "environment":
            problems.append(f"{file_name}: _postman_variable_scope debe ser «environment»")
        if not isinstance(environment.get("values"), list) or not environment.get("name"):
            problems.append(f"{file_name}: faltan el nombre o la lista de variables")
    return problems


# --- D1: operations <-> requests -----------------------------------------------------------------


def check_operations(collection: dict, operations: set[str]) -> list[str]:
    covered = set()
    for request in requests_of(collection["item"]):
        parts = prefix_and_description(request["name"])
        if parts and parts[0] not in MANUAL_HELPER_PREFIXES:
            covered.add(parts[0])
    problems = []
    if operations - covered:
        problems.append(f"operaciones sin petición: {sorted(operations - covered)}")
    if covered - operations:
        problems.append(f"peticiones de operaciones que la API no tiene: {sorted(covered - operations)}")
    return problems


# --- D2: every operation and every error status has a case --------------------------------------


def check_coverage(collection: dict, operations: set[str]) -> list[str]:
    problems = []
    folders = {folder["name"][:3]: folder for folder in collection["item"]}
    lifecycle = folders.get(LIFECYCLE_FOLDER)
    errors = folders.get(ERRORS_FOLDER)
    if lifecycle is None or errors is None:
        return ["faltan las carpetas «1. Ciclo de vida…» o «2. Casos de error»"]
    in_lifecycle = {
        parts[0]
        for request in requests_of(lifecycle["item"])
        if (parts := prefix_and_description(request["name"]))
    }
    if operations - in_lifecycle:
        problems.append(f"operaciones sin petición en el ciclo de vida: {sorted(operations - in_lifecycle)}")
    statuses = set()
    for request in requests_of(errors["item"]):
        parts = prefix_and_description(request["name"])
        match = re.match(r"(\d{3}) ", parts[1]) if parts else None
        if match:
            statuses.add(int(match.group(1)))
    if ERROR_STATUSES - statuses:
        problems.append(f"estatus sin caso de error: {sorted(ERROR_STATUSES - statuses)}")
    return problems


# --- D3: descriptions and visible checks ---------------------------------------------------------


def check_documentation(collection: dict) -> list[str]:
    problems = []
    if not collection.get("info", {}).get("description", "").strip():
        problems.append("la colección no tiene descripción")
    for folder in folders_of(collection["item"]):
        if not folder.get("description", "").strip():
            problems.append(f"la carpeta «{folder['name']}» no tiene descripción")
    for request in requests_of(collection["item"]):
        if not request["request"].get("description", "").strip():
            problems.append(f"«{request['name']}» no tiene descripción")
        if not re.search(r'pm\.test\(\s*"[^"]+', scripts_of(request, "test")):
            problems.append(f"«{request['name']}» no tiene ninguna comprobación (pm.test con título)")
    return problems


# --- D4: authentication --------------------------------------------------------------------------


def check_authentication(collection: dict) -> list[str]:
    problems = []
    script = scripts_of(collection, "prerequest")
    if "skipRequest" not in script or "/oauth/token" not in script:
        problems.append("la colección no trae el script previo de acceso (skipRequest y /oauth/token)")
    auth = collection.get("auth", {})
    if auth.get("type") != "bearer" or auth["bearer"][0]["value"] != "{{accessToken}}":
        problems.append("la autenticación de la colección debe ser Bearer {{accessToken}}")
    for request in requests_of(collection["item"]):
        own = request["request"].get("auth")
        if own is None or own["type"] == "noauth":
            continue
        value = own["bearer"][0]["value"] if own["type"] == "bearer" else None
        if value not in {"{{plainToken}}", "{{badToken}}"}:
            problems.append(f"«{request['name']}» escribe una autenticación que no es una variable permitida: {value}")
    return problems


# --- D5: no secrets (by structure) ---------------------------------------------------------------


def check_secrets(collection: dict, environments: dict[str, dict]) -> list[str]:
    problems = []
    for file_name, environment in environments.items():
        for variable in environment.get("values", []):
            key, value = variable["key"], variable.get("value", "")
            if variable.get("type") == "secret" and value != "":
                problems.append(f"{file_name}: la variable secreta «{key}» tiene valor")
            if key in ACCESS_ENVIRONMENT_KEYS and value != "":
                problems.append(f"{file_name}: la variable de acceso «{key}» debe ir vacía en el archivo")
            if key in SECRET_ENVIRONMENT_KEYS and variable.get("type") != "secret":
                problems.append(f"{file_name}: «{key}» debe ser de tipo secret")
            if HIGH_ENTROPY_PATTERN.fullmatch(str(value)):
                problems.append(f"{file_name}: el valor de «{key}» parece una clave")
        for text in strings_of(environment):
            if JWT_PATTERN.search(text):
                problems.append(f"{file_name}: contiene algo que parece un JWT")
    for variable in collection.get("variable", []):
        key, value = variable["key"], str(variable.get("value", ""))
        if SECRET_NAME_PATTERN.search(key) and value != "":
            problems.append(f"colección: la variable «{key}» tiene valor en el archivo")
        if HIGH_ENTROPY_PATTERN.fullmatch(value):
            problems.append(f"colección: el valor de «{key}» parece una clave")
    for text in strings_of(collection):
        if JWT_PATTERN.search(text):
            problems.append("colección: contiene algo que parece un JWT")
    auth_blocks = [("la colección", collection.get("auth", {}))]
    for request in requests_of(collection["item"]):
        auth_blocks.append((f"«{request['name']}»", request["request"].get("auth", {})))
        for header in request["request"].get("header", []):
            if BEARER_LITERAL_PATTERN.search(header.get("value", "")):
                problems.append(f"«{request['name']}» escribe un Bearer literal en una cabecera")
    for owner, block in auth_blocks:
        if any(BEARER_LITERAL_PATTERN.search(text) for text in strings_of(block)):
            problems.append(f"{owner} escribe un Bearer literal en su autenticación")
        for entry in block.get("bearer", []):
            if not re.fullmatch(r"\{\{\w+\}\}", str(entry.get("value", ""))):
                problems.append(f"{owner} escribe un token literal en su autenticación Bearer")
    return problems


# --- D5b: scripts do not print secrets -----------------------------------------------------------


def check_console(collection: dict) -> list[str]:
    problems = []
    for owner, text in all_scripts(collection):
        for line in text.splitlines():
            if CONSOLE_CALL_PATTERN.search(line) and CONSOLE_FORBIDDEN_PATTERN.search(line):
                problems.append(f"{owner} escribe en la consola algo sobre un secreto o un token: {line.strip()}")
    return problems


# --- D6: environments ----------------------------------------------------------------------------


def check_environments(collection: dict, environments: dict[str, dict]) -> list[str]:
    problems = []
    keys = {}
    values = {}
    for file_name, environment in environments.items():
        values[file_name] = {variable["key"]: variable.get("value", "") for variable in environment["values"]}
        keys[file_name] = set(values[file_name])
        if keys[file_name] != ENVIRONMENT_KEYS:
            missing = sorted(ENVIRONMENT_KEYS - keys[file_name])
            extra = sorted(keys[file_name] - ENVIRONMENT_KEYS)
            problems.append(f"{file_name}: variables que faltan {missing} o sobran {extra}")
        if "bases de datos de pruebas" not in environment.get("name", ""):
            problems.append(f"{file_name}: el nombre del entorno debe advertir de «bases de datos de pruebas»")
        if not str(values[file_name].get("testDatabaseNotice", "")).strip():
            problems.append(f"{file_name}: testDatabaseNotice no puede estar vacía")
        hidden = keys[file_name] & {variable["key"] for variable in collection.get("variable", [])}
        if hidden:
            problems.append(f"{file_name}: oculta variables de la colección: {sorted(hidden)}")
    if len({frozenset(found) for found in keys.values()}) > 1:
        problems.append("los dos entornos no definen las mismas variables")
    for file_name, found in values.items():
        if "local" in file_name and found.get("baseUrl") != "http://127.0.0.1:8010":
            problems.append(f"{file_name}: baseUrl debe valer http://127.0.0.1:8010")
        if "local" in file_name and found.get("clinicsStubUrl") != "http://127.0.0.1:8001":
            problems.append(f"{file_name}: clinicsStubUrl debe valer http://127.0.0.1:8001")
        if "deployed" in file_name and (found.get("baseUrl") or found.get("clinicsStubUrl")):
            problems.append(f"{file_name}: baseUrl y clinicsStubUrl deben ir vacías")
    return problems


# --- D7: nothing that is not ours is touched -----------------------------------------------------


def check_data_safety(collection: dict) -> list[str]:
    problems = []
    for request in requests_of(collection["item"]):
        name, method, url = request["name"], method_of(request), url_of(request)
        variables = set(VARIABLE_PATTERN.findall(url)) - {"baseUrl", "clinicsStubUrl"}
        if method in MUTATING_METHODS and variables - OWNED_VARIABLES:
            problems.append(f"«{name}» modifica o elimina usando {sorted(variables - OWNED_VARIABLES)} en su ruta")
        if method != "GET" and variables & READ_ONLY_VARIABLES:
            problems.append(f"«{name}» usa {sorted(variables & READ_ONLY_VARIABLES)} y no es una consulta (GET)")
        if re.search(r"/subscriptions/\d+", url):
            problems.append(f"«{name}» lleva un identificador literal en la ruta")
        if name.startswith("sim: ") and (
            method not in {"GET", "POST"} or not url.startswith("{{clinicsStubUrl}}/__test__/")
        ):
            problems.append(f"«{name}» no es un GET o POST a {{clinicsStubUrl}}/__test__/")
    return problems


# --- D8: every request quoted by a message exists ------------------------------------------------


def cited_requests(collection: dict, operations: set[str]) -> list[tuple[str, str]]:
    """(owner, fragment) for every `<operationId>: ...` quoted in a script, up to the next quote or »."""
    pattern = re.compile(r"(?:%s): [^\"'»\n]+" % "|".join(sorted(operations)))
    return [
        (owner, fragment.strip())
        for owner, text in all_scripts(collection)
        for fragment in pattern.findall(text)
    ]


def check_cited_requests(collection: dict, operations: set[str]) -> list[str]:
    names = {request["name"] for request in requests_of(collection["item"])}
    return [
        f"{owner} cita la petición «{fragment}», que no existe"
        for owner, fragment in cited_requests(collection, operations)
        if fragment not in names
    ]


# --- D9: independent of the end-to-end collection ------------------------------------------------


def check_independence(collection: dict, other_collection: dict) -> list[str]:
    problems = []
    if collection["info"]["name"] == other_collection["info"]["name"]:
        problems.append("la colección manual comparte nombre con la de punta a punta")
    if any("usersStubUrl" in text for text in strings_of(collection)):
        problems.append("la colección manual menciona usersStubUrl (depende de la simulación de usuarios)")
    for request in requests_of(collection["item"]):
        if request["name"].startswith("setup:"):
            problems.append(f"«{request['name']}» usa el prefijo setup: de la colección de punta a punta")
    return problems


# --- D10: names ----------------------------------------------------------------------------------


def check_names(collection: dict, operations: set[str]) -> list[str]:
    problems = []
    seen = set()
    for request in requests_of(collection["item"]):
        name = request["name"]
        parts = prefix_and_description(name)
        if parts is None:
            problems.append(f"«{name}» no tiene la forma «<operationId>: <descripción>»")
        elif parts[0] not in operations | MANUAL_HELPER_PREFIXES:
            problems.append(f"«{name}» empieza por «{parts[0]}», que no es una operación ni un prefijo auxiliar")
        if name in seen:
            problems.append(f"«{name}» está repetido")
        seen.add(name)
    return problems


# --- D11: an order that works --------------------------------------------------------------------


def check_order(collection: dict) -> list[str]:
    problems = []
    for folder in folders_of(collection["item"]):
        saved = set()
        for request in requests_of(folder["item"]):
            used = set(VARIABLE_PATTERN.findall(url_of(request) + "\n" + body_of(request)))
            for variable in sorted(used & OWNED_VARIABLES - saved):
                problems.append(
                    f"carpeta «{folder['name']}»: «{request['name']}» usa {{{{{variable}}}}} antes de que una petición lo guarde"
                )
            prefix = request["name"].split(": ", 1)[0]
            tests = scripts_of(request, "test")
            for variable in OWNED_VARIABLES:
                if prefix == "create_subscription" and f'set("{variable}"' in tests:
                    saved.add(variable)
    return problems


# --- Fixtures ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def collection() -> dict:
    return load_json(MANUAL_COLLECTION)


@pytest.fixture(scope="module")
def environments() -> dict[str, dict]:
    return {path.name: load_json(path) for path in MANUAL_ENVIRONMENTS.values()}


@pytest.fixture(scope="module")
def operations() -> set[str]:
    return operation_ids_of_the_api()


def broken(collection: dict) -> dict:
    return copy.deepcopy(collection)


def find(collection: dict, prefix: str) -> dict:
    return next(request for request in requests_of(collection["item"]) if request["name"].startswith(prefix))


# --- Tests on the real files ---------------------------------------------------------------------


def test_the_files_are_postman_v21(collection, environments):
    assert not check_format(collection, environments)


def test_the_collection_covers_exactly_the_operations_of_the_api(collection, operations):
    problems = check_operations(collection, operations)
    assert not problems, "\n".join(problems)


def test_every_operation_and_every_error_status_has_a_case(collection, operations):
    problems = check_coverage(collection, operations)
    assert not problems, "\n".join(problems)


def test_everything_is_described_and_every_request_checks_its_answer(collection):
    problems = check_documentation(collection)
    assert not problems, "\n".join(problems)


def test_names_are_well_formed_and_unique(collection, operations):
    problems = check_names(collection, operations)
    assert not problems, "\n".join(problems)


def test_every_folder_creates_what_it_uses_before_using_it(collection):
    problems = check_order(collection)
    assert not problems, "\n".join(problems)


def test_the_authentication_is_the_access_script_and_only_references_variables(collection):
    problems = check_authentication(collection)
    assert not problems, "\n".join(problems)


def test_no_file_of_the_manual_collection_holds_a_token_or_a_secret(collection, environments):
    problems = check_secrets(collection, environments)
    assert not problems, "\n".join(problems)


def test_the_scripts_never_print_a_secret_or_a_token(collection):
    problems = check_console(collection)
    assert not problems, "\n".join(problems)


def test_the_two_environments_define_the_same_variables_and_warn_about_test_databases(collection, environments):
    problems = check_environments(collection, environments)
    assert not problems, "\n".join(problems)


def test_a_request_that_changes_or_deletes_only_touches_what_the_collection_created(collection):
    problems = check_data_safety(collection)
    assert not problems, "\n".join(problems)


def test_the_requests_quoted_by_the_messages_of_the_script_exist(collection, operations):
    # The script quotes the requests that create data (the «OWNED» table and the hints): the rule must see them.
    assert {fragment for _, fragment in cited_requests(collection, operations)} >= {
        "create_subscription: crear la suscripción de prueba",
        "create_subscription: crear otra suscripción para el choque de nombres",
        "delete_subscription: eliminar la suscripción de prueba",
    }
    problems = check_cited_requests(collection, operations)
    assert not problems, "\n".join(problems)


def test_the_manual_collection_does_not_depend_on_the_end_to_end_one(collection):
    problems = check_independence(collection, load_json(E2E_COLLECTION))
    assert not problems, "\n".join(problems)


# --- Negative tests: the rules do bite -----------------------------------------------------------


def test_d1_names_the_operations_that_are_missing_and_the_ones_that_are_left_over(collection, operations):
    without_delete = broken(collection)
    for folder in folders_of(without_delete["item"]):
        folder["item"] = [item for item in folder["item"] if not item["name"].startswith("delete_subscription")]
    problems = check_operations(without_delete, operations)
    assert any("operaciones sin petición" in p and "delete_subscription" in p for p in problems)

    with_extra = broken(collection)
    find(with_extra, "list_subscriptions: comprobar")["name"] = "invented_operation: algo que la API no tiene"
    assert any("peticiones de operaciones que la API no tiene" in p and "invented_operation" in p for p in check_operations(with_extra, operations))
    assert any("invented_operation" in p for p in check_names(with_extra, operations))


def test_d2_names_the_error_status_without_a_case(collection, operations):
    without_conflicts = broken(collection)
    for folder in folders_of(without_conflicts["item"]):
        folder["item"] = [item for item in folder["item"] if ": 409 " not in item["name"]]
    problems = check_coverage(without_conflicts, operations)
    assert any("estatus sin caso de error" in p and "409" in p for p in problems)


def test_d3_names_the_request_without_description_or_checks(collection):
    undocumented = broken(collection)
    request = find(undocumented, "get_subscription: consultar")
    request["request"]["description"] = ""
    request["event"] = []
    problems = check_documentation(undocumented)
    assert any("get_subscription: consultar" in p and "descripción" in p for p in problems)
    assert any("get_subscription: consultar" in p and "comprobación" in p for p in problems)


def test_d4_rejects_a_literal_bearer(collection):
    with_token = broken(collection)
    find(with_token, "list_subscriptions: comprobar")["request"]["auth"] = {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "abcdefghijkl", "type": "string"}],
    }
    assert any("list_subscriptions: comprobar" in p for p in check_authentication(with_token))
    assert any("token literal" in p for p in check_secrets(with_token, {}))


def test_d5_names_the_file_and_the_variable_of_a_secret(collection, environments):
    with_secret = copy.deepcopy(environments)
    local = next(name for name in with_secret if "local" in name)
    for variable in with_secret[local]["values"]:
        if variable["key"] == "auth0ClientSecret":
            variable["value"] = "x" * 8
    problems = check_secrets(collection, with_secret)
    assert any(local in p and "auth0ClientSecret" in p for p in problems)


def test_d5_rejects_a_jwt_in_a_header(collection, environments):
    with_jwt = broken(collection)
    request = find(with_jwt, "list_subscriptions: comprobar")
    request["request"]["header"].append({"key": "Authorization", "value": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.abcdefghijk"})
    problems = check_secrets(with_jwt, environments)
    assert any("JWT" in p or "Bearer literal" in p for p in problems)


def test_d5b_rejects_a_script_that_prints_a_token(collection):
    leaking = broken(collection)
    leaking["event"][0]["script"]["exec"].append('console.log("token: " + pm.collectionVariables.get("accessToken"));')
    assert any("consola" in p for p in check_console(leaking))


def test_d6_names_the_environment_that_lost_a_variable(collection, environments):
    incomplete = copy.deepcopy(environments)
    deployed = next(name for name in incomplete if "deployed" in name)
    incomplete[deployed]["values"] = [v for v in incomplete[deployed]["values"] if v["key"] != "testDatabaseNotice"]
    problems = check_environments(collection, incomplete)
    assert any(deployed in p and "testDatabaseNotice" in p for p in problems)
    assert any("no definen las mismas variables" in p for p in problems)


def test_d6_rejects_an_environment_variable_that_hides_a_collection_one(collection, environments):
    hiding = copy.deepcopy(environments)
    local = next(name for name in hiding if "local" in name)
    hiding[local]["values"].append({"key": "accessToken", "value": "", "type": "default", "enabled": True})
    assert any("oculta" in p and "accessToken" in p for p in check_environments(collection, hiding))


def test_d7_rejects_a_delete_that_uses_an_id_the_collection_did_not_create(collection):
    unsafe = broken(collection)
    request = find(unsafe, "delete_subscription: eliminar la suscripción de prueba")
    request["request"]["url"]["raw"] = "{{baseUrl}}/api/v1/subscriptions/{{deletedSubscriptionId}}"
    assert any("delete_subscription: eliminar" in p for p in check_data_safety(unsafe))

    literal = broken(collection)
    find(literal, "get_subscription: consultar la suscripción creada")["request"]["url"]["raw"] = "{{baseUrl}}/api/v1/subscriptions/7"
    assert any("identificador literal" in p for p in check_data_safety(literal))


def test_d8_rejects_a_message_that_quotes_a_request_that_no_longer_exists(collection, operations):
    renamed = broken(collection)
    find(renamed, "create_subscription: crear la suscripción de prueba")["name"] = "create_subscription: crear la de prueba"
    problems = check_cited_requests(renamed, operations)
    assert any("create_subscription: crear la suscripción de prueba" in p and "no existe" in p for p in problems)


def test_d9_rejects_a_dependency_on_the_user_simulation(collection):
    dependent = broken(collection)
    find(dependent, "sim: reiniciar")["request"]["url"]["raw"] = "{{usersStubUrl}}/__test__/reset"
    assert any("usersStubUrl" in p for p in check_independence(dependent, load_json(E2E_COLLECTION)))


def test_d11_rejects_a_request_that_uses_a_subscription_before_it_is_created(collection):
    misordered = broken(collection)
    lifecycle = next(folder for folder in misordered["item"] if folder["name"].startswith(LIFECYCLE_FOLDER))
    lifecycle["item"].insert(0, lifecycle["item"].pop(1))  # «consultar» before «crear»
    problems = check_order(misordered)
    assert any("get_subscription: consultar" in p and "subscriptionId" in p for p in problems)

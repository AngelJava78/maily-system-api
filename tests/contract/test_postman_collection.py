"""The Postman collection covers exactly the operations of the API and holds no secrets.

It runs with `uv run pytest` and needs neither Docker nor Node.js: it only reads the JSON files of
`tests/postman/` (the collection itself is run by Newman, see the quickstart).
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

from src.main import create_app

POSTMAN = Path(__file__).resolve().parents[1] / "postman"
COLLECTION = POSTMAN / "collections" / "MailySoft-System-Suscripciones.postman_collection.json"
# Requests that prepare scenarios (`setup: ...`) or check the public documentation (`docs: ...`)
# are not operations of the API: their name does not start with an `operationId`.
HELPER_PREFIXES = {"setup", "docs"}
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.")


def requests_of(items: list[dict]) -> Iterator[dict]:
    for item in items:
        if "item" in item:
            yield from requests_of(item["item"])
        else:
            yield item


def collection() -> dict:
    return json.loads(COLLECTION.read_text(encoding="utf-8"))


def prefix_of(name: str) -> str:
    assert ": " in name, f"the name of the request «{name}» must be «<operationId>: <description>»"
    return name.split(": ", 1)[0]


def operation_ids_of_the_api() -> set[str]:
    schema = create_app().openapi()
    return {
        operation["operationId"] for item in schema["paths"].values() for operation in item.values()
    }


def test_the_collection_covers_exactly_the_operations_of_the_openapi():
    covered = {
        prefix_of(request["name"])
        for request in requests_of(collection()["item"])
        if prefix_of(request["name"]) not in HELPER_PREFIXES
    }
    operations = operation_ids_of_the_api()

    assert covered == operations, (
        f"operations missing in the collection: {sorted(operations - covered)}; "
        f"operations in the collection that the API does not have: {sorted(covered - operations)}"
    )


def test_every_operation_is_exercised_with_a_success_and_with_an_error_case():
    names = [request["name"] for request in requests_of(collection()["item"])]

    for operation_id in operation_ids_of_the_api():
        assert any(name.startswith(f"{operation_id}: ") for name in names), operation_id


def test_every_request_checks_its_answer():
    for request in requests_of(collection()["item"]):
        events = [e for e in request.get("event", []) if e["listen"] == "test"]
        assert events, f"«{request['name']}» has no tests"


def test_the_authentication_only_references_variables():
    document = collection()
    assert document["auth"]["bearer"][0]["value"] == "{{accessToken}}"

    for request in requests_of(document["item"]):
        auth = request["request"].get("auth")
        if auth and auth["type"] == "bearer":
            value = auth["bearer"][0]["value"]
            assert re.fullmatch(r"\{\{\w+\}\}", value), f"«{request['name']}» writes a token: {value}"


def test_no_file_of_the_postman_folder_holds_a_token_or_a_secret():
    files = [
        path
        for path in POSTMAN.rglob("*")
        if path.is_file()
        and "node_modules" not in path.parts
        and "reports" not in path.parts
        and path.name != "package-lock.json"
    ]
    assert files, "there is nothing to check"

    for path in files:
        content = path.read_text(encoding="utf-8")
        assert not JWT_PATTERN.search(content), f"{path.name} contains a JWT"
        assert "secret" not in content.lower(), f"{path.name} mentions a secret"
        assert not re.search(r"Bearer [A-Za-z0-9._-]{8,}", content), f"{path.name} writes a token"


def test_the_environments_have_no_variables_that_would_hide_the_collection_ones():
    for name in ("e2e", "dev"):
        values = json.loads(
            (POSTMAN / "environments" / f"{name}.postman_environment.json").read_text(encoding="utf-8")
        )["values"]
        keys = {value["key"] for value in values}

        # An environment variable has priority over a collection variable of the same name.
        assert not keys & {"accessToken", "plainToken", "subscriptionId", "suffix"}, name
        assert "baseUrl" in keys

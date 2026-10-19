"""Helpers shared by the Postman contract tests (end-to-end collection and manual collection).

Everything here only reads files of the repository and the OpenAPI document that the application
generates: no service, no Node.js and no Postman are needed.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.main import create_app

POSTMAN = Path(__file__).resolve().parents[1] / "postman"

# End-to-end collection of spec 001 (run by Newman against the isolated stack).
COLLECTION = POSTMAN / "collections" / "MailySoft-System-Suscripciones.postman_collection.json"
# Requests that prepare scenarios (`setup: ...`) or check the public documentation (`docs: ...`)
# are not operations of the API: their name does not start with an `operationId`.
E2E_HELPER_PREFIXES = {"setup", "docs"}

# Manual collection of spec 002 (used by hand from the Postman desktop application).
MANUAL_COLLECTION = POSTMAN / "collections" / "MailySoft-System-Manual.postman_collection.json"
MANUAL_ENVIRONMENTS = {
    "local": POSTMAN / "environments" / "manual-local.postman_environment.json",
    "deployed": POSTMAN / "environments" / "manual-deployed-test.postman_environment.json",
}
# `docs: ...` checks the public documentation and `sim: ...` drives the clinics simulation.
MANUAL_HELPER_PREFIXES = {"docs", "sim"}

# End-to-end collection of spec 003 (the dashboard; run by Newman against the same isolated stack).
DASHBOARD_COLLECTION = POSTMAN / "collections" / "MailySoft-System-Dashboard.postman_collection.json"
DASHBOARD_PREFIX = "/api/v1/dashboard"
DASHBOARD_HELPER_PREFIXES = {"setup", "docs"}

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.")
BEARER_LITERAL_PATTERN = re.compile(r"Bearer [A-Za-z0-9._~+/=-]{8,}")
# A value that looks like a key or a secret: 32 or more token characters and no spaces.
HIGH_ENTROPY_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def requests_of(items: list[dict]) -> Iterator[dict]:
    """Every request of a collection, however deep its folders are."""
    for item in items:
        if "item" in item:
            yield from requests_of(item["item"])
        else:
            yield item


def folders_of(items: list[dict]) -> Iterator[dict]:
    """Every folder of a collection, however deep it is."""
    for item in items:
        if "item" in item:
            yield item
            yield from folders_of(item["item"])


def prefix_of(name: str) -> str:
    assert ": " in name, f"the name of the request «{name}» must be «<operationId>: <description>»"
    return name.split(": ", 1)[0]


def scripts_of(item: dict, listen: str) -> str:
    """Text of the `listen` scripts (`prerequest` or `test`) of an item, one line per `exec` entry."""
    return "\n".join(
        line
        for event in item.get("event", [])
        if event.get("listen") == listen
        for line in event.get("script", {}).get("exec", [])
    )


SUBSCRIPTIONS_PREFIX = "/api/v1/subscriptions"


def operation_ids_of_the_api(path_prefix: str = SUBSCRIPTIONS_PREFIX) -> set[str]:
    """The `operationId` of the paths that start with `path_prefix`.

    By default, the subscriptions: the resource that the collections of specs 001 and 002 cover.
    Pass `"/"` for every operation of the API.
    """
    schema = create_app().openapi()
    return {
        operation["operationId"]
        for path, item in schema["paths"].items()
        if path.startswith(path_prefix)
        for operation in item.values()
    }

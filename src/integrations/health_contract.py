"""Reading and cleaning of the health contract v1 of the other services (spec 005, research R7).

Pure functions: they turn a bounded answer of a component (`ProbeResponse`) into records with only the
known fields of the contract (`specs/005-health-monitoring/contracts/health-contract-v1.md`). Texts
lose their control characters and are cut to 64 characters; at most 20 checks are read; dates go to
UTC; an error code outside the contract becomes `unexpected_error`. The raw body never comes out.
Deciding `up`, `degraded` or `down` is not done here: that is a rule of the Service.
"""

import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.integrations.health_probe import ProbeResponse

UNKNOWN = "unknown"
MAX_TEXT_LENGTH = 64
MAX_CHECKS = 20
CHECK_ERROR_CODES = frozenset({"timeout", "connection_error", "not_configured", "unexpected_error"})
_CHECK_STATUSES = ("ok", "error")


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check, in the shape of `/health/ready` of the contract."""

    name: str
    status: str
    latency_ms: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class BuildData:
    """The build of a component, cleaned; what is not available is `unknown`."""

    version: str
    commit: str
    build_date: str
    environment: str


UNKNOWN_BUILD = BuildData(UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN)


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """What one call said: fine or not, the code of the failure, its checks and its latency."""

    ok: bool
    error: str | None
    checks: tuple[CheckResult, ...]
    latency_ms: int


def _json_object(body: bytes | None) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _failed(response: ProbeResponse, error: str, checks: tuple[CheckResult, ...] = ()) -> CallOutcome:
    return CallOutcome(False, error, checks, response.latency_ms)


def _strip(value: str) -> str:
    return "".join(ch for ch in value if not unicodedata.category(ch).startswith("C")).strip()


def clean_text(value: object) -> str:
    """A text without control characters, trimmed and cut to 64; `unknown` if empty or not text."""
    if not isinstance(value, str):
        return UNKNOWN
    text = _strip(value)[:MAX_TEXT_LENGTH]
    return text or UNKNOWN


def clean_build_date(value: object) -> str:
    """An ISO 8601 date and time with its zone, in UTC with `Z`; anything else is `unknown`."""
    if not isinstance(value, str):
        return UNKNOWN
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return UNKNOWN
    if moment.utcoffset() is None:
        return UNKNOWN
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def clean_checks(value: object) -> tuple[CheckResult, ...]:
    """The first 20 elements of the list, without the malformed ones (FR-013)."""
    if not isinstance(value, list):
        return ()
    checks = []
    for item in value[:MAX_CHECKS]:
        if not isinstance(item, dict):
            continue
        name, status = item.get("name"), item.get("status")
        if not isinstance(name, str) or status not in _CHECK_STATUSES:
            continue
        clean_name = _strip(name)[:MAX_TEXT_LENGTH]
        if not clean_name:
            continue
        latency = item.get("latency_ms")
        # `bool` is an `int` in Python: exclude it explicitly.
        latency = latency if type(latency) is int and latency >= 0 else None
        error = None
        if status == "error":
            raw_error = item.get("error")
            error = raw_error if isinstance(raw_error, str) and raw_error in CHECK_ERROR_CODES else "unexpected_error"
        checks.append(CheckResult(clean_name, status, latency, error))
    return tuple(checks)


def parse_live(response: ProbeResponse) -> CallOutcome:
    """`/health/live`: fine only with a 200 and a JSON object whose `status` is `ok`."""
    if response.failure is not None:
        return _failed(response, response.failure)
    if response.status_code != 200:
        return _failed(response, "unexpected_status")
    body = _json_object(response.body)
    if body is None or body.get("status") != "ok":
        return _failed(response, "invalid_response")
    return CallOutcome(True, None, (), response.latency_ms)


def parse_ready(response: ProbeResponse) -> CallOutcome:
    """`/health/ready`: 200 `ok` is fine; 503 `unavailable` is `not_ready` (both with `checks`)."""
    if response.failure is not None:
        return _failed(response, response.failure)
    if response.status_code not in (200, 503):
        return _failed(response, "unexpected_status")
    body = _json_object(response.body)
    expected = "ok" if response.status_code == 200 else "unavailable"
    if body is None or body.get("status") != expected or not isinstance(body.get("checks"), list):
        return _failed(response, "invalid_response")
    checks = clean_checks(body["checks"])
    if response.status_code == 503:
        return _failed(response, "not_ready", checks)
    return CallOutcome(True, None, checks, response.latency_ms)


def parse_frontend(response: ProbeResponse) -> CallOutcome:
    """The health route of a frontend: only its status counts (any 2xx); the body is not read."""
    if response.failure is not None:
        return _failed(response, response.failure)
    if response.status_code is None or not 200 <= response.status_code <= 299:
        return _failed(response, "unexpected_status")
    return CallOutcome(True, None, (), response.latency_ms)


def parse_info(response: ProbeResponse) -> BuildData:
    """`/info`: each field cleaned on its own; any failure leaves the four in `unknown`."""
    if response.failure is not None or response.status_code != 200:
        return UNKNOWN_BUILD
    body = _json_object(response.body)
    if body is None:
        return UNKNOWN_BUILD
    return BuildData(
        version=clean_text(body.get("version")),
        commit=clean_text(body.get("commit")),
        build_date=clean_build_date(body.get("build_date")),
        environment=clean_text(body.get("environment")),
    )

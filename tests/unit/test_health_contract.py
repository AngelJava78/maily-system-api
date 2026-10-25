"""Reading and cleaning of the health contract v1 of the other services (spec 005, FR-013 to FR-015).

Research R7: only the known fields of the contract are kept; texts lose their control characters and
are cut to 64 characters; at most 20 checks; dates in UTC; an error code outside the contract becomes
`unexpected_error`. The raw body of another service never comes out.
"""

import json

import pytest

from src.integrations.health_contract import (
    MAX_CHECKS,
    UNKNOWN,
    BuildData,
    CheckResult,
    clean_build_date,
    clean_checks,
    clean_text,
    parse_frontend,
    parse_info,
    parse_live,
    parse_ready,
)
from src.integrations.health_probe import ProbeResponse

MARKER = "SECRETO-INTERNO"
DATABASE_OK = {"name": "database", "status": "ok", "latency_ms": 3, "error": None}


def answer(status: int, body: object = None, *, raw: bytes | None = None) -> ProbeResponse:
    content = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    return ProbeResponse(status_code=status, body=content, failure=None, latency_ms=12)


def failure(code: str) -> ProbeResponse:
    return ProbeResponse(status_code=None, body=None, failure=code, latency_ms=3000)


# --- live ---


@pytest.mark.parametrize("body", [{"status": "ok"}, {"status": "ok", "uptime": 5}])
def test_live_is_fine_with_200_and_status_ok(body):
    outcome = parse_live(answer(200, body))

    assert (outcome.ok, outcome.error, outcome.latency_ms) == (True, None, 12)


@pytest.mark.parametrize("status", [500, 307, 204])
def test_live_with_another_status_is_unexpected(status):
    assert parse_live(answer(status, {"status": "ok"})).error == "unexpected_status"


@pytest.mark.parametrize(
    "response",
    [
        answer(200, raw=f"<html>{MARKER}</html>".encode()),
        answer(200, raw=b"ok"),
        answer(200, [{"status": "ok"}]),
        answer(200, {"status": "fine"}),
        answer(200, raw=b""),
    ],
)
def test_live_with_another_body_is_an_invalid_response(response):
    outcome = parse_live(response)

    assert (outcome.ok, outcome.error) == (False, "invalid_response")


@pytest.mark.parametrize("code", ["timeout", "dns_error", "connection_error", "response_too_large"])
def test_a_network_failure_is_kept(code):
    outcome = parse_live(failure(code))

    assert (outcome.ok, outcome.error, outcome.latency_ms) == (False, code, 3000)


# --- ready ---


def test_ready_is_fine_with_200_ok_and_its_checks():
    outcome = parse_ready(answer(200, {"status": "ok", "checks": [DATABASE_OK]}))

    assert outcome.ok
    assert outcome.checks == (CheckResult("database", "ok", 3, None),)


def test_ready_503_of_the_contract_is_not_ready_with_its_checks():
    body = {
        "status": "unavailable",
        "checks": [{"name": "database", "status": "error", "latency_ms": 2001, "error": "timeout"}],
    }

    outcome = parse_ready(answer(503, body))

    assert (outcome.ok, outcome.error) == (False, "not_ready")
    assert outcome.checks == (CheckResult("database", "error", 2001, "timeout"),)


@pytest.mark.parametrize(
    "response",
    [
        answer(200, {"status": "unavailable", "checks": []}),
        answer(503, raw=b"<html>down</html>"),
        answer(200, {"status": "ok"}),  # no checks
        answer(503, {"status": "ok", "checks": []}),
        answer(200, {"status": "ok", "checks": "database"}),
    ],
)
def test_ready_with_another_body_is_an_invalid_response(response):
    assert parse_ready(response).error == "invalid_response"


@pytest.mark.parametrize("status", [404, 500, 302])
def test_ready_with_another_status_is_unexpected(status):
    assert parse_ready(answer(status, {"status": "ok", "checks": []})).error == "unexpected_status"


# --- frontend ---


@pytest.mark.parametrize("status", [200, 204, 299])
def test_a_frontend_is_fine_with_any_2xx_whatever_the_body(status):
    outcome = parse_frontend(ProbeResponse(status, None, None, 7))

    assert (outcome.ok, outcome.error, outcome.latency_ms) == (True, None, 7)


@pytest.mark.parametrize("status", [301, 404, 500])
def test_a_frontend_with_another_status_is_unexpected(status):
    assert parse_frontend(ProbeResponse(status, None, None, 7)).error == "unexpected_status"


def test_a_frontend_that_cannot_be_reached_keeps_the_failure():
    assert parse_frontend(failure("dns_error")).error == "dns_error"


# --- info ---


def test_a_valid_info_is_kept_with_the_date_in_utc():
    body = {
        "service": "otro",
        "version": "1.4.2",
        "commit": "0123456789abcdef",
        "build_date": "2026-10-20T15:30:00-06:00",
        "environment": "e2e",
    }

    assert parse_info(answer(200, body)) == BuildData("1.4.2", "0123456789abcdef", "2026-10-20T21:30:00Z", "e2e")


@pytest.mark.parametrize(
    "response",
    [failure("timeout"), answer(404, {"version": "1"}), answer(200, ["1"]), answer(200, raw=b"<html>")],
)
def test_any_failure_of_info_leaves_the_build_unknown(response):
    assert parse_info(response) == BuildData(UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN)


def test_each_invalid_field_of_info_is_unknown_on_its_own():
    body = {"version": 123, "commit": "a" * 100 + "\u0007", "build_date": "ayer", "environment": None}

    data = parse_info(answer(200, body))

    assert data == BuildData(UNKNOWN, "a" * 64, UNKNOWN, UNKNOWN)


# --- the cleaning rules ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  1.4.2  ", "1.4.2"),
        ("v1\u0007\n.2", "v1.2"),
        ("x" * 80, "x" * 64),
        ("", UNKNOWN),
        ("\u0000\u0007", UNKNOWN),
        (123, UNKNOWN),
        (None, UNKNOWN),
        (True, UNKNOWN),
    ],
)
def test_a_text_loses_control_characters_and_is_cut_to_64(value, expected):
    assert clean_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-24T16:05:00Z", "2026-10-24T16:05:00Z"),
        ("2026-10-24T10:05:00-06:00", "2026-10-24T16:05:00Z"),
        ("2026-10-24T16:05:00", UNKNOWN),
        ("ayer", UNKNOWN),
        (1700000000, UNKNOWN),
    ],
)
def test_a_build_date_needs_its_zone_and_is_normalized_to_utc(value, expected):
    assert clean_build_date(value) == expected


def test_only_the_first_20_checks_are_read_and_the_malformed_ones_are_dropped():
    malformed = [
        {"status": "ok", "latency_ms": 1, "error": None},  # no name
        {"name": "queue", "status": "warn", "latency_ms": 1, "error": None},
        "not an object",
        {"name": "  ", "status": "ok", "latency_ms": 1, "error": None},  # empty name
    ]
    good = [{"name": f"c{n}", "status": "ok", "latency_ms": n, "error": None} for n in range(30)]

    checks = clean_checks(malformed + good)

    assert len(checks) == MAX_CHECKS - len(malformed)
    assert checks[0] == CheckResult("c0", "ok", 0, None)


@pytest.mark.parametrize(
    ("latency", "expected"), [(12, 12), (0, 0), (True, None), ("12", None), (12.5, None), (-1, None), (None, None)]
)
def test_the_latency_of_a_check_is_a_non_negative_integer_or_none(latency, expected):
    [check] = clean_checks([{"name": "db", "status": "ok", "latency_ms": latency, "error": None}])

    assert check.latency_ms == expected


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        ("ok", "timeout", None),  # a check that is ok carries no error
        ("error", "timeout", "timeout"),
        ("error", "connection_error", "connection_error"),
        ("error", "not_configured", "not_configured"),
        ("error", "unexpected_error", "unexpected_error"),
        ("error", "disk_full", "unexpected_error"),
        ("error", None, "unexpected_error"),
        ("error", {"code": "x"}, "unexpected_error"),
    ],
)
def test_the_error_of_a_check_is_one_of_the_contract(status, error, expected):
    [check] = clean_checks([{"name": "db", "status": status, "latency_ms": 1, "error": error}])

    assert check.error == expected


def test_the_name_of_a_check_is_cleaned_like_a_text():
    [check] = clean_checks([{"name": "d\u0007b" + "x" * 80, "status": "ok", "latency_ms": 1}])

    assert check.name == ("db" + "x" * 80)[:64]


@pytest.mark.parametrize("value", [None, "checks", {"a": 1}, 3])
def test_checks_that_are_not_a_list_are_none(value):
    assert clean_checks(value) == ()


def test_no_result_keeps_the_marker_of_the_other_service():
    results = [
        parse_live(answer(200, raw=f"<html>{MARKER}</html>".encode())),
        parse_ready(answer(503, raw=MARKER.encode())),
        parse_info(answer(200, {"version": MARKER + "x" * 80, "commit": f"\u0007{MARKER}"})),
    ]

    assert MARKER not in repr(results[:2])
    assert results[2].version != MARKER + "x" * 80  # cut, never the raw text
    assert len(results[2].version) == 64

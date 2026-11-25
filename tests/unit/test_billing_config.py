"""Configuration of the subscription periods: the payments API and the cutoff date (spec 010).

`PaymentsSettings` (the address and the time limit of the payments API) and `BillingSettings` (the
cutoff date, FR-039) are validated at start-up like the rest of the configuration: a missing or invalid
variable is named and its value is never shown (FR-039, FR-040).
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.config import (
    BillingSettings,
    PaymentsSettings,
    configuration_error_message,
    payments_url_warnings,
)

ENV_NAMES = ("PAYMENTS_API_BASE_URL", "PAYMENTS_API_TIMEOUT_SECONDS", "PAYMENTS_RETURN_URL", "BILLING_CUTOFF_AT")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, billing_environment) -> None:
    """No variable of this feature: each test sets exactly what it needs.

    It asks for `billing_environment` (which defines them for the whole suite) so that it always runs
    after it and the variables are removed again.
    """
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def payments(**values: object) -> PaymentsSettings:
    return PaymentsSettings(_env_file=None, **{"payments_api_base_url": "http://payments-api:8080", **values})


def billing(**values: object) -> BillingSettings:
    return BillingSettings(_env_file=None, **{"billing_cutoff_at": "2026-11-18T00:00:00Z", **values})


# --- the payments API ---


def test_the_address_of_the_payments_api_is_required():
    with pytest.raises(ValidationError) as error:
        PaymentsSettings(_env_file=None)

    assert [e["loc"][0] for e in error.value.errors()] == ["payments_api_base_url"]


def test_the_timeout_defaults_to_five_seconds():
    assert payments().payments_api_timeout_seconds == 5.0


@pytest.mark.parametrize("value", [0, -1, 31, 30.01])
def test_the_timeout_must_be_above_zero_and_at_most_thirty(value):
    with pytest.raises(ValidationError):
        payments(payments_api_timeout_seconds=value)


def test_the_limits_of_the_timeout_are_valid():
    assert payments(payments_api_timeout_seconds=30).payments_api_timeout_seconds == 30
    assert payments(payments_api_timeout_seconds=0.1).payments_api_timeout_seconds == 0.1


def test_an_empty_variable_counts_as_not_defined(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAYMENTS_API_BASE_URL", "")

    with pytest.raises(ValidationError) as error:
        PaymentsSettings(_env_file=None)

    assert [e["loc"][0] for e in error.value.errors()] == ["payments_api_base_url"]


def test_the_variables_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAYMENTS_API_BASE_URL", "https://pagos.example.com")
    monkeypatch.setenv("PAYMENTS_API_TIMEOUT_SECONDS", "2.5")

    loaded = PaymentsSettings(_env_file=None)

    assert loaded.payments_api_base_url == "https://pagos.example.com"
    assert loaded.payments_api_timeout_seconds == 2.5


def test_the_address_is_stored_without_a_trailing_slash():
    assert payments(payments_api_base_url="http://x:8002/").payments_api_base_url == "http://x:8002"


@pytest.mark.parametrize("value", ["ftp://secreto", "payments-api:8080", "", "//host"])
def test_the_address_must_start_with_http_or_https(value):
    with pytest.raises(ValidationError):
        payments(payments_api_base_url=value)


def test_the_error_of_the_address_names_the_variable_and_never_its_value():
    with pytest.raises(ValidationError) as error:
        payments(payments_api_base_url="ftp://secreto")

    message = configuration_error_message(error.value)

    assert "PAYMENTS_API_BASE_URL" in message
    assert "secreto" not in message


# --- the warning of the address without encryption (FR-040) ---


@pytest.mark.parametrize(
    "url",
    [
        "https://pagos.empresa.com",
        "http://localhost:8002",
        "http://127.0.0.1",
        "http://[::1]:8000",
        "http://payments-api-stub:8080",
    ],
)
def test_no_warning_for_https_or_for_local_and_docker_addresses(url):
    assert payments_url_warnings(payments(payments_api_base_url=url)) == []


def test_an_insecure_address_warns_naming_the_variable_and_never_the_address():
    warnings = payments_url_warnings(payments(payments_api_base_url="http://usuario:clave@pagos.empresa.com"))

    assert len(warnings) == 1
    assert "PAYMENTS_API_BASE_URL" in warnings[0]
    assert "pagos.empresa.com" not in warnings[0]
    assert "usuario" not in warnings[0] and "clave" not in warnings[0]


# --- the cutoff date ---


def test_the_cutoff_date_is_required():
    with pytest.raises(ValidationError) as error:
        BillingSettings(_env_file=None)

    assert [(e["loc"][0], e["type"]) for e in error.value.errors()] == [("billing_cutoff_at", "missing")]


def test_an_empty_cutoff_counts_as_not_defined(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BILLING_CUTOFF_AT", "")

    with pytest.raises(ValidationError) as error:
        BillingSettings(_env_file=None)

    assert [(e["loc"][0], e["type"]) for e in error.value.errors()] == [("billing_cutoff_at", "missing")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-18T00:00:00Z", datetime(2026, 11, 18, tzinfo=UTC)),
        ("2026-11-18T00:00:00+00:00", datetime(2026, 11, 18, tzinfo=UTC)),
        ("2026-11-17T18:00:00-06:00", datetime(2026, 11, 18, tzinfo=UTC)),
        ("2026-11-18T05:30:00+05:30", datetime(2026, 11, 18, tzinfo=UTC)),
        ("2026-11-18T00:00:00.5Z", datetime(2026, 11, 18, 0, 0, 0, 500000, tzinfo=UTC)),
        (" 2026-11-18T00:00:00Z ", datetime(2026, 11, 18, tzinfo=UTC)),
    ],
)
def test_the_cutoff_is_an_iso_8601_date_with_a_zone_and_is_stored_in_utc(text, expected):
    loaded = billing(billing_cutoff_at=text).billing_cutoff_at

    assert loaded == expected
    assert loaded.utcoffset() == timedelta(0)
    assert loaded.tzinfo is UTC or loaded.tzinfo == timezone.utc


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-18T00:00:00",  # no zone: the instant would be ambiguous
        "2026-11-18",  # a date alone
        "1700000000",  # a timestamp
        "no-es-una-fecha",
        "2026-13-45T00:00:00Z",
        "   ",
    ],
)
def test_a_cutoff_without_a_zone_or_that_is_not_a_date_is_invalid(text):
    with pytest.raises(ValidationError) as error:
        billing(billing_cutoff_at=text)

    assert [e["loc"][0] for e in error.value.errors()] == ["billing_cutoff_at"]


def test_a_date_object_must_carry_its_zone_too():
    assert billing(billing_cutoff_at=datetime(2026, 11, 18, tzinfo=UTC)).billing_cutoff_at == datetime(
        2026, 11, 18, tzinfo=UTC
    )
    with pytest.raises(ValidationError):
        billing(billing_cutoff_at=datetime(2026, 11, 18))


def test_the_cutoff_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BILLING_CUTOFF_AT", "2026-11-17T18:00:00-06:00")

    assert BillingSettings(_env_file=None).billing_cutoff_at == datetime(2026, 11, 18, tzinfo=UTC)


def test_the_error_of_the_cutoff_names_the_variable_and_never_its_value():
    with pytest.raises(ValidationError) as error:
        billing(billing_cutoff_at="secreto-que-no-es-fecha")

    message = configuration_error_message(error.value)

    assert "BILLING_CUTOFF_AT" in message
    assert "secreto" not in message


def test_a_missing_cutoff_is_named_as_missing():
    with pytest.raises(ValidationError) as error:
        BillingSettings(_env_file=None)

    assert "Falta la variable de entorno BILLING_CUTOFF_AT" in configuration_error_message(error.value)


# --- the return address of the payments (spec 011, «Direcciones de referencia») ---

RETURN_URL = "https://app.mailysoft.com/payment"


def test_the_return_address_is_optional():  # row 1
    assert payments().payments_return_url is None


def test_an_empty_return_address_counts_as_not_defined(monkeypatch: pytest.MonkeyPatch):  # row 1, FR-002
    monkeypatch.setenv("PAYMENTS_API_BASE_URL", "http://payments-api:8080")
    monkeypatch.setenv("PAYMENTS_RETURN_URL", "")

    assert PaymentsSettings(_env_file=None).payments_return_url is None


def test_the_return_address_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAYMENTS_API_BASE_URL", "http://payments-api:8080")
    monkeypatch.setenv("PAYMENTS_RETURN_URL", RETURN_URL)

    assert PaymentsSettings(_env_file=None).payments_return_url == RETURN_URL


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        (RETURN_URL, RETURN_URL),  # row 2
        (
            "https://app.mailysoft.com:8443/payment?origen=pago",  # row 3: the port and the query are kept
            "https://app.mailysoft.com:8443/payment?origen=pago",
        ),
        ("https://staging.mailysoft.com/payment/", "https://staging.mailysoft.com/payment/"),  # row 4
        ("  https://app.mailysoft.com/payment  ", RETURN_URL),  # row 5: only the outer spaces go
        ("HTTPS://App.MailySoft.com/payment", "HTTPS://App.MailySoft.com/payment"),  # never lowered
        ("https://8.8.8.8/payment", "https://8.8.8.8/payment"),  # a public address
    ],
)
def test_a_valid_return_address_is_kept_as_it_was_written(value, kept):  # FR-003, FR-005
    assert payments(payments_return_url=value).payments_return_url == kept


def test_a_return_address_of_exactly_2048_characters_is_valid():
    value = "https://app.mailysoft.com/payment?x="
    value += "a" * (2048 - len(value))

    assert payments(payments_return_url=value).payments_return_url == value


INVALID_RETURN_ADDRESSES = {
    "http": "http://app.mailysoft.com/payment",  # row 6
    "ftp": "ftp://app.mailysoft.com/payment",  # row 7
    "relative": "/payment",  # row 8
    "no-scheme": "app.mailysoft.com/payment",  # row 8
    "no-host": "https:///payment",
    "credentials": "https://usuario:clave@app.mailysoft.com/payment",  # row 9
    "user-only": "https://usuario@app.mailysoft.com/payment",
    "empty-user": "https://@app.mailysoft.com/payment",
    "fragment": "https://app.mailysoft.com/payment#pago",  # row 10
    "empty-fragment": "https://app.mailysoft.com/payment#",
    "space": "https://app.mailysoft.com/pa yment",  # row 11
    "control": "https://app.mailysoft.com/pay\tment",
    "too-long": "https://app.mailysoft.com/payment?x=" + "a" * 2100,  # row 12
    "localhost": "https://localhost:8080/payment",  # row 13
    "sub-localhost": "https://app.localhost/payment",  # row 13
    "loopback": "https://127.0.0.1/payment",  # row 14
    "private-10": "https://10.0.0.5/payment",  # row 14
    "private-192": "https://192.168.1.20/payment",  # row 14
    "ipv6-loopback": "https://[::1]/payment",  # row 14
    "link-local": "https://169.254.10.10/payment",
    "unspecified": "https://0.0.0.0/payment",
    "single-label": "https://frontend/payment",  # row 15
    "bad-port": "https://app.mailysoft.com:99999/payment",  # row 16
    "blank": "   ",
}


@pytest.mark.parametrize("value", INVALID_RETURN_ADDRESSES.values(), ids=INVALID_RETURN_ADDRESSES.keys())
def test_an_invalid_return_address_is_refused(value):  # FR-003
    with pytest.raises(ValidationError) as error:
        payments(payments_return_url=value)

    assert [e["loc"][0] for e in error.value.errors()] == ["payments_return_url"]


@pytest.mark.parametrize("value", INVALID_RETURN_ADDRESSES.values(), ids=INVALID_RETURN_ADDRESSES.keys())
def test_the_error_of_the_return_address_names_the_variable_and_never_its_value(value):  # FR-004
    with pytest.raises(ValidationError) as error:
        payments(payments_return_url=value)

    message = configuration_error_message(error.value)

    assert "PAYMENTS_RETURN_URL" in message
    assert "PAYMENTS_API_BASE_URL" not in message
    for fragment in ("mailysoft", "usuario", "clave", "localhost", "127.0.0.1", "192.168", "frontend", "payment"):
        assert fragment not in message

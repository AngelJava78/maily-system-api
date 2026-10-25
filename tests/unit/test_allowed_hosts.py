"""Host names and the list of allowed hosts of the health checks (spec 005, FR-025, FR-027).

Research R14: a host is an IP literal or an ASCII host name; the list admits exact hosts and domain
suffixes (with a leading dot). An entry that is not one of those stops the service at start-up.
"""

import pytest

from src.config import AllowedHosts, valid_host

LONG_NAME = ".".join(["a" * 63] * 4)  # 255 characters: above the 253 of a host name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mailysoft-usuarios", "mailysoft-usuarios"),
        ("Maily360-Production.up.railway.app", "maily360-production.up.railway.app"),
        ("a.b.c", "a.b.c"),
        ("10.0.0.5", "10.0.0.5"),
        ("127.0.0.1", "127.0.0.1"),
        ("::1", "::1"),
    ],
)
def test_a_valid_host_is_returned_in_lower_case(text, expected):
    assert valid_host(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "-a",
        "a-",
        "a..b",
        "a.",
        "a" * 64,
        LONG_NAME,
        "a_b",
        "ñandu.mx",
        "2130706433",  # an integer is not an IP literal and cannot pass as a name
        "0x7f.1",
        "1.2.3",
        "a b",
        "[::1]",
        "a:8000",
    ],
)
def test_an_invalid_host_is_rejected(text):
    assert valid_host(text) is None


def test_the_list_separates_exact_hosts_and_suffixes():
    hosts = AllowedHosts.parse("mailysoft-usuarios, .Maily.Internal")

    assert hosts.exact == frozenset({"mailysoft-usuarios"})
    assert hosts.suffixes == (".maily.internal",)
    assert not hosts.is_empty


@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_text_is_an_empty_list(text):
    hosts = AllowedHosts.parse(text)

    assert hosts.is_empty
    assert not hosts.allows("mailysoft-usuarios")


def test_a_repeated_entry_is_accepted():
    assert AllowedHosts.parse("a, A ,a").exact == frozenset({"a"})


@pytest.mark.parametrize(
    "text",
    ["a,,b", "a,", ".", "*.maily.internal", "*", "http://a", "a/b", "a:8000", "[::1]", ".-x", "a b"],
)
def test_an_invalid_entry_is_rejected(text):
    with pytest.raises(ValueError):
        AllowedHosts.parse(text)


def test_the_error_never_repeats_the_entry():
    with pytest.raises(ValueError) as error:
        AllowedHosts.parse("bueno, secreto-123.interno/ruta")

    assert "secreto-123" not in str(error.value)


def test_a_suffix_admits_its_subdomains_only():
    hosts = AllowedHosts.parse(".maily.internal")

    assert hosts.allows("a.maily.internal")
    assert hosts.allows("x.y.maily.internal")
    assert not hosts.allows("maily.internal")
    assert not hosts.allows("otromaily.internal")


def test_an_exact_host_ignores_case_and_admits_nothing_else():
    hosts = AllowedHosts.parse("mailysoft-usuarios")

    assert hosts.allows("MAILYSOFT-USUARIOS")
    assert not hosts.allows("mailysoft-usuarios.x")
    assert not hosts.allows("x.mailysoft-usuarios")


def test_an_exact_ip_only_admits_itself():
    hosts = AllowedHosts.parse("10.0.0.5")

    assert hosts.allows("10.0.0.5")
    assert not hosts.allows("10.0.0.50")


def test_an_empty_list_admits_no_host():
    assert not AllowedHosts().allows("mailysoft-usuarios")

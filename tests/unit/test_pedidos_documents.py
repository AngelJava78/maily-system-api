"""The documents that let the feature move forward without the other APIs (spec 010, story 8; FR-049, SC-013).

For each API that this service consumes there is the contract that it consumes and the request document
that the owner of the product will hand over: what the business asks for, what is asked and in which
shape, how this service uses it and what it blocks. They are what the other teams read, so they are
checked like code: nothing may be left empty, and no credential may be written in them.
"""

import re
from pathlib import Path

import pytest

CONTRACTS = Path(__file__).resolve().parents[2] / "specs" / "010-subscription-periods" / "contracts"
APIS = ["usuarios", "clinicas", "pagos"]
PEDIDOS = {name: CONTRACTS / f"pedidos-{name}.md" for name in APIS}
CONSUMED = {
    "usuarios": CONTRACTS / "users-api-integration.md",
    "clinicas": CONTRACTS / "clinics-api-integration.md",
    "pagos": CONTRACTS / "payments-api-integration.md",
}
# The four parts of a request document, as the second-level headings that open them.
PARTS = {
    "what the business asks": r"^## \d+\. Qué pide el negocio\s*$",
    "what is asked": r"^## \d+\. Lo que te pido\s*$",
    "how it is used": r"^## \d+\. Cómo lo (usa|usará)\b.*$",
    "what it blocks": r"^## \d+\. Qué bloquea\s*$",
}
CREDENTIALS = [r"\bJWT\b", r"Bearer\s+eyJ", r"eyJ[A-Za-z0-9_-]{10,}", r"(?i)secret(o)?[\s:=]+\S{8,}", r"sk-[A-Za-z0-9]{10,}"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading_pattern: str) -> str:
    """The body of the second-level section whose heading matches, up to the next one."""
    match = re.search(heading_pattern, text, re.MULTILINE)
    assert match, heading_pattern
    rest = text[match.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: following.start()] if following else rest


@pytest.mark.parametrize("target", APIS)
def test_there_is_a_request_document_and_a_consumed_contract_for_each_api(target):
    assert PEDIDOS[target].is_file()
    assert CONSUMED[target].is_file()


@pytest.mark.parametrize("target", APIS)
@pytest.mark.parametrize("part", PARTS)
def test_each_request_document_has_its_four_parts_and_none_is_empty(target, part):
    text = read(PEDIDOS[target])

    body = section(text, PARTS[part])

    assert len(body.strip()) > 60, f"{PEDIDOS[target].name}: «{part}» is empty or a placeholder"


@pytest.mark.parametrize("target", APIS)
def test_the_parts_come_in_the_order_that_the_reader_needs(target):
    text = read(PEDIDOS[target])

    positions = [re.search(pattern, text, re.MULTILINE).start() for pattern in PARTS.values()]

    assert positions == sorted(positions)


@pytest.mark.parametrize("target", APIS)
def test_what_it_blocks_is_a_table_with_at_least_one_row(target):
    body = section(read(PEDIDOS[target]), PARTS["what it blocks"])

    rows = [line for line in body.splitlines() if line.startswith("|")]

    assert len(rows) >= 3, "header, separator and at least one row"
    assert re.fullmatch(r"\|[\s:|-]+\|", rows[1]), "the second row is the separator of the table"
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert all(cells), f"an empty cell in {row!r}"


@pytest.mark.parametrize("target", APIS)
def test_the_request_names_the_shape_that_is_proposed(target):
    asked = section(read(PEDIDOS[target]), PARTS["what is asked"])

    # What is missing comes with the form proposed: a field, a permission, a payload or a route.
    assert re.search(r"`[^`\n]+`", asked)
    assert "```" in asked or re.search(r"^\|.*\|$", asked, re.MULTILINE) or re.search(r"^- \*\*", asked, re.MULTILINE)


@pytest.mark.parametrize("target", APIS)
def test_the_request_says_it_does_not_block_the_development_or_what_it_blocks_and_how(target):
    body = section(read(PEDIDOS[target]), PARTS["what it blocks"]).lower()

    assert "bloquea" in body or "nada" in body


@pytest.mark.parametrize("target", APIS)
def test_the_consumed_contract_says_what_exists_and_what_is_missing(target):
    text = read(CONSUMED[target])

    assert re.search(r"\b(existe|existen)\b", text, re.IGNORECASE), "it never says what already exists"
    assert re.search(r"\bfalta(n)?\b", text, re.IGNORECASE), "it never says what is missing"
    assert len(text.strip()) > 500


@pytest.mark.parametrize("target", APIS)
def test_the_consumed_contract_links_the_request_that_closes_the_gap(target):
    assert PEDIDOS[target].name in read(CONSUMED[target])


@pytest.mark.parametrize("path", [*PEDIDOS.values(), *CONSUMED.values()], ids=lambda p: p.name)
def test_no_document_contains_a_token_or_a_secret(path):
    text = read(path)

    for pattern in CREDENTIALS:
        assert not re.search(pattern, text), f"{path.name} matches {pattern}"


@pytest.mark.parametrize("path", [*PEDIDOS.values(), *CONSUMED.values()], ids=lambda p: p.name)
def test_the_documents_are_written_in_spanish(path):
    text = read(path)

    # Principle VII: the documents are in Spanish (code, identifiers and fields stay in English).
    assert re.search(r"\b(el|la|los|las|que|para)\b", text)
    assert len(re.findall(r"\b(the|which|should|must)\b", text)) < 5

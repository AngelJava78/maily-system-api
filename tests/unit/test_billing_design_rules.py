"""Design rules of the subscription periods that no behavior test can see (spec 010).

They guard what the requirements say about how the feature is built, not what it does: nothing that can be
derived is stored, only own data is kept (Principle IX), nothing runs in the background, and money and time
go through the only places that may handle them. No database needed: they read the source and the models.
"""

import ast
import re
from pathlib import Path

import pytest

import src.models  # noqa: F401  (registers every model in the metadata)
from src.models.base import Base

SRC = Path(__file__).resolve().parents[2] / "src"
# The files that this feature added or whose organization part it added.
BILLING_FILES = [
    "services/billing_rules.py",
    "services/subscription_period_service.py",
    "repositories/subscription_period_repository.py",
    "routers/subscription_periods.py",
    "integrations/payments_api.py",
    "dtos/subscription_period.py",
    "models/subscription_period.py",
    "models/subscription_charge.py",
]
BACKGROUND = re.compile(
    r"BackgroundTasks|create_task|ensure_future|apscheduler|celery|threading\.Timer|call_later|call_at|sched\.scheduler"
)

PERIOD_COLUMNS = {"organization_id", "started_at", "trial_ends_at", "paid_until", "created_at", "updated_at"}
CHARGE_COLUMNS = {
    "id",
    "organization_id",
    "payment_id",
    "amount",
    "currency",
    "billing_period",
    "settles_due_at",
    "attempt",
    "status",
    "closed_reason",
    "period_starts_at",
    "period_ends_at",
    "resolved_at",
    "created_at",
    "updated_at",
}
# What belongs to another API, or can be derived at the moment of the query (FR-012, FR-042).
NOT_OURS = {
    "state",
    "payment_due_at",
    "days_remaining",
    "payment_in_progress",
    "subscription_id",
    "plan_id",
    "plan_name",
    "subscription_name",
    "organization_name",
    "clinic_id",
    "owner_id",
    "user_id",
    "email",
    "checkout_url",
    "payment_status",
    "payment_url",
    "token",
}


def source(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["subscription_periods", "subscription_charges"])
def test_nothing_that_belongs_to_another_api_or_can_be_derived_is_stored(name: str):
    columns = set(Base.metadata.tables[name].columns.keys())

    assert not columns & NOT_OURS, sorted(columns & NOT_OURS)


def test_the_period_keeps_only_the_dates_that_the_requirements_name():
    # FR-007 to FR-010 and FR-042: the start, the end of the trial and until when it is paid.
    assert set(Base.metadata.tables["subscription_periods"].columns.keys()) == PERIOD_COLUMNS


def test_the_charge_keeps_only_what_this_service_asked_for_and_its_own_result():
    # FR-021 and FR-042: the id of the payment, what was requested and the result of the reconciliation.
    assert set(Base.metadata.tables["subscription_charges"].columns.keys()) == CHARGE_COLUMNS


def test_the_organization_is_a_reference_without_a_foreign_key_to_another_apis_table():
    foreign_keys = {
        (table, fk.column.table.name)
        for table in ("subscription_periods", "subscription_charges")
        for fk in Base.metadata.tables[table].foreign_keys
    }

    # The only relation is between the two tables of this feature: the organization is not ours.
    assert foreign_keys == {("subscription_charges", "subscription_periods")}


def test_the_amount_is_an_exact_decimal_never_a_float():
    amount = Base.metadata.tables["subscription_charges"].columns["amount"]

    assert amount.type.__class__.__name__ == "Numeric"
    assert (amount.type.precision, amount.type.scale) == (10, 2)
    assert amount.type.asdecimal is True


@pytest.mark.parametrize("relative", BILLING_FILES)
def test_nothing_of_the_feature_runs_in_the_background_or_on_a_schedule(relative: str):
    # FR-012: the state is computed when it is consulted; no scheduled job and no process in the background.
    assert not BACKGROUND.search(source(relative)), relative


@pytest.mark.parametrize("relative", BILLING_FILES)
def test_the_money_is_never_a_float(relative: str):
    # A `float` is fine for a timeout; it is never fine on a line that talks about an amount or a price.
    # Only real uses count (the syntax tree), not a docstring that says «never float».
    money = re.compile(r"amount|price|importe|monthly|annual|minor", re.IGNORECASE)
    text = source(relative)
    lines = text.splitlines()
    uses = [node.lineno for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Name) and node.id == "float"]
    offending = [lines[number - 1].strip() for number in uses if money.search(lines[number - 1])]

    assert offending == [], relative


def test_the_only_reader_of_the_system_clock_is_the_clock():
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r"datetime\.now\(|utcnow\(|date\.today\(|time\.time\(", path.read_text(encoding="utf-8"))
        and path.name != "clock.py"
    ]

    assert offenders == []  # the clock is injected so that the tests can move it (FR-045)


@pytest.mark.parametrize("relative", BILLING_FILES)
def test_no_leftover_marks_or_prints(relative: str):
    assert not re.search(r"\bprint\(|\bTODO\b|\bFIXME\b|\bXXX\b", source(relative)), relative

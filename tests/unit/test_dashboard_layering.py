"""The dashboard keeps no data in the database of the service (spec 003, FR-020).

No table, model, migration or repository: the modules of the dashboard must not even import
anything that touches the database. It reuses the `ast` walk of `test_layering.py`.
"""

from pathlib import Path

import pytest

from tests.unit.test_layering import SRC, imported_modules, violations_in

DASHBOARD_MODULES = [
    "routers/dashboard.py",
    "services/dashboard_service.py",
    "dtos/dashboard.py",
    "integrations/dashboard_source.py",
    "integrations/dummy_dashboard_source.py",
]
DATABASE_PACKAGES = (
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "src.database",
    "src.models",
    "src.repositories",
)


def source_of(module: str) -> str:
    path: Path = SRC / module
    assert path.is_file(), f"src/{module} does not exist"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("module", DASHBOARD_MODULES)
def test_the_module_does_not_touch_the_database(module):
    assert violations_in(source_of(module), DATABASE_PACKAGES) == []


def test_there_is_no_model_or_repository_of_the_dashboard():
    names = [p.name for folder in ("models", "repositories") for p in (SRC / folder).rglob("*.py")]

    assert [name for name in names if "dashboard" in name] == []


def test_the_dummy_source_needs_neither_network_nor_clock_nor_chance():
    source = source_of("integrations/dummy_dashboard_source.py")

    assert not {"socket", "httpx", "random", "secrets", "time"} & imported_modules(source)
    for forbidden in (".now(", "utcnow", "today("):
        assert forbidden not in source, forbidden


def test_the_router_does_not_know_the_data_sources():
    assert violations_in(source_of("routers/dashboard.py"), ("src.integrations",)) == []

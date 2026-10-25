"""The version comes from one source (spec 005, FR-007, SC-008; research R1).

`src.VERSION` is the source; `pyproject.toml`, `uv.lock`, the OpenAPI document and `/info` must say the
same. `tomllib` belongs to the standard library.
"""

import tomllib

import httpx

from src import VERSION
from src.main import create_app
from tests.health_support import TEST_HEALTH_CONFIG, HealthConfigHolder, install_health_overrides
from tests.helpers import ROOT
from tests.stubs.components.app import create_stub_app


def test_pyproject_says_the_version_of_the_code():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["version"] == VERSION


def test_the_lock_file_says_the_version_of_the_code():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    [own] = [package for package in lock["package"] if package["name"] == "mailysoft-system-api"]

    assert own["version"] == VERSION


def test_the_openapi_document_says_the_version_of_the_code():
    app = create_app()

    assert app.version == VERSION
    assert app.openapi()["info"]["version"] == VERSION


async def test_info_says_the_version_of_the_code():
    app = create_app()
    probe_client = install_health_overrides(app, create_stub_app(), HealthConfigHolder(TEST_HEALTH_CONFIG))
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api.test") as client,
        probe_client,
    ):
        body = (await client.get("/info")).json()

    assert body["version"] == VERSION
    assert body["service"] == "maily-system-api"

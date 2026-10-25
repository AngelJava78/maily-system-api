"""The public status publishes only its closed list of fields (spec 005, FR-047, SC-014).

The health result has components in every state, with versions, checks and error codes; the public
status of the same moment has none of that: only `status`, `checked_at` and `components`, and of
each component only `code`, `name`, `kind`, `status` and `next_start_at`.
"""

from datetime import UTC, datetime

from src.dependencies import get_database_pinger
from src.repositories.errors import DatabaseUnavailableError
from tests.health_support import RUNBOOK_SCHEDULE, HealthApi, stub_url

PUBLIC_FIELDS = {"status", "checked_at", "components"}
PUBLIC_COMPONENT_FIELDS = {"code", "name", "kind", "status", "next_start_at"}
ERROR_CODES = (
    "timeout",
    "connection_error",
    "dns_error",
    "host_not_allowed",
    "unexpected_status",
    "invalid_response",
    "response_too_large",
    "not_ready",
    "unexpected_error",
    "not_configured",
)
FORBIDDEN = ("components.test", "otro.example", "latency", "version", "checks", "registry_available", "1.4.2")


async def every_state(health_api: HealthApi) -> None:
    """Components up, degraded, down and unknown, and the database stopped at night."""
    await health_api.insert_component(code="sano", base_url=stub_url("healthy"), sort_order=10)
    await health_api.insert_component(code="no-listo", base_url=stub_url("not-ready"), sort_order=20)
    await health_api.insert_component(code="con-falla", base_url=stub_url("error"), sort_order=30)
    await health_api.insert_component(code="fuera-de-lista", base_url="http://otro.example/x", sort_order=40)

    async def ping() -> None:
        raise DatabaseUnavailableError("connection_error")

    health_api.use_value(get_database_pinger, ping)
    health_api.set_config(schedule=RUNBOOK_SCHEDULE)
    health_api.clock.set(datetime(2026, 10, 28, 3, 0, tzinfo=UTC))  # Tuesday 21:00 in Mexico City


async def test_the_health_result_of_the_scenario_has_every_state_versions_checks_and_errors(health_api: HealthApi):
    await every_state(health_api)

    private = (await health_api.health()).json()

    assert {component["status"] for component in private["components"]} == {
        "up",
        "degraded",
        "down",
        "stopped",
        "unknown",
    }
    assert "1.4.2" in {component["version"] for component in private["components"]}
    assert any(component["checks"] for component in private["components"])
    assert {component["error"] for component in private["components"]} >= {
        "not_ready",
        "unexpected_status",
        "host_not_allowed",
        "connection_error",
    }


async def test_the_public_status_has_exactly_its_fields_and_nothing_else(health_api: HealthApi):
    await every_state(health_api)
    await health_api.health()  # the same result serves both routes

    response = await health_api.status()

    body = response.json()
    assert set(body) == PUBLIC_FIELDS
    assert len(body["components"]) == 6
    for component in body["components"]:
        assert set(component) == PUBLIC_COMPONENT_FIELDS, component["code"]
    for text in FORBIDDEN + ERROR_CODES:
        assert text not in response.text, text

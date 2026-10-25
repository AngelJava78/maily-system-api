"""`/api/v1/monitored-components` over HTTP (spec 005, user story 3; FR-023 to FR-031).

The real application with the real PostgreSQL, the simulated users API and the simulated components
(`tests/stubs/components`): what is registered here is what the next health query checks.
"""

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from src.dependencies import get_monitored_component_repository
from src.repositories.monitored_component_repository import MonitoredComponentRepository
from tests.health_support import HealthApi, stub_url
from tests.helpers import TEST_TOKEN

PATH = "/api/v1/monitored-components"
SERVICE = {"code": "usuarios", "name": "MailySoft Usuarios", "kind": "service", "base_url": stub_url("healthy")}
FRONTEND = {"code": "mailysoft", "name": "MailySoft", "kind": "frontend", "base_url": stub_url("spa"), "live_path": "/healthz/"}
FIELDS = {
    "id",
    "code",
    "name",
    "kind",
    "base_url",
    "live_path",
    "ready_path",
    "info_path",
    "enabled",
    "sort_order",
    "created_at",
    "updated_at",
}

HOST_NOT_ALLOWED = "El host de la dirección base no está entre los hosts permitidos por el servicio."
BASE_URL_INVALID = (
    "La dirección base debe ser una dirección http:// o https:// de hasta 255 caracteres, con un host "
    "válido y sin usuario, contraseña, consulta (?) ni fragmento (#)."
)
PATH_INVALID = (
    "La ruta debe empezar con una sola «/» y tener hasta 200 caracteres, sin segmentos «.» o «..» y "
    "sin «\\», «?», «#», «%», espacios ni caracteres de control."
)
FRONTEND_READY_PATH = (
    "Un componente de tipo «frontend» no lleva ruta de disponibilidad: envíela nula o no la envíe."
)


async def create(health_api: HealthApi, **changes) -> dict:
    response = await health_api.client.post(PATH, json={**SERVICE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


async def health_codes(health_api: HealthApi) -> list[str]:
    body = (await health_api.health()).json()
    return [component["code"] for component in body["components"]]


async def registry(health_api: HealthApi) -> list[dict]:
    response = await health_api.client.get(PATH)
    assert response.status_code == 200
    return response.json()


def validation_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert (body["code"], body["message"]) == ("validation_error", "Hay datos no válidos en la solicitud.")
    return [(error["field"], error["message"]) for error in body["errors"]]


# --- 1. Registering ---


async def test_a_service_is_registered_with_the_routes_of_the_contract_and_its_dates(health_api: HealthApi):
    response = await health_api.client.post(PATH, json=SERVICE)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert response.headers["location"] == f"{PATH}/{body['id']}"
    UUID(body["id"])
    assert (body["code"], body["name"], body["kind"], body["base_url"]) == (
        "usuarios",
        "MailySoft Usuarios",
        "service",
        stub_url("healthy"),
    )
    assert (body["live_path"], body["ready_path"], body["info_path"]) == ("/health/live", "/health/ready", "/info")
    assert (body["enabled"], body["sort_order"]) == (True, 0)
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")


async def test_a_new_component_appears_in_the_next_health_query_even_with_a_cache(health_api: HealthApi):
    health_api.set_config(cache_seconds=15)
    assert "usuarios" not in await health_codes(health_api)  # this result is now cached

    await create(health_api)

    assert "usuarios" in await health_codes(health_api)


async def test_the_base_url_is_stored_normalized(health_api: HealthApi):
    body = await create(health_api, base_url="HTTP://Components.TEST/healthy/")

    assert body["base_url"] == "http://components.test/healthy"


async def test_a_frontend_with_its_health_route_and_no_readiness_route_is_accepted(health_api: HealthApi):
    response = await health_api.client.post(PATH, json=FRONTEND)

    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["live_path"], body["ready_path"], body["info_path"]) == (
        "frontend",
        "/healthz/",
        None,
        None,
    )


# --- 2. Conflicts ---


@pytest.mark.parametrize("code", ["usuarios", "maily-system-api", "database"])
async def test_a_repeated_or_reserved_code_is_a_conflict_and_nothing_is_created(health_api: HealthApi, code):
    await create(health_api)

    response = await health_api.client.post(PATH, json={**SERVICE, "code": code, "name": "Otro"})

    assert response.status_code == 409
    assert response.json() == {
        "code": "monitored_component_code_already_exists",
        "message": f"Ya existe un componente monitoreado con el código «{code}».",
    }
    assert [component["code"] for component in await registry(health_api)] == ["usuarios"]


async def test_two_simultaneous_registrations_with_the_same_code_let_one_win(health_api: HealthApi):
    responses = await asyncio.gather(
        health_api.client.post(PATH, json=SERVICE), health_api.client.post(PATH, json=SERVICE)
    )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert len(await registry(health_api)) == 1


# --- 3, 4 and 5. Validation ---


async def test_a_host_outside_the_allowed_list_is_refused_without_revealing_the_address_or_the_list(
    health_api: HealthApi,
):
    response = await health_api.client.post(PATH, json={**SERVICE, "base_url": "http://interno.example:8080"})

    assert validation_errors(response) == [("base_url", HOST_NOT_ALLOWED)]
    for forbidden in ("interno.example", "components.test", "dns-error.test"):
        assert forbidden not in response.text
    assert await registry(health_api) == []


@pytest.mark.parametrize(
    "base_url",
    [
        "http://usuario:clave@components.test",
        "http://components.test/healthy?x=1",
        "http://components.test/healthy#f",
        "ftp://components.test",
    ],
)
async def test_a_base_url_with_credentials_query_fragment_or_another_scheme_is_refused(
    health_api: HealthApi, base_url
):
    response = await health_api.client.post(PATH, json={**SERVICE, "base_url": base_url})

    assert validation_errors(response) == [("base_url", BASE_URL_INVALID)]
    assert "clave" not in response.text


@pytest.mark.parametrize(
    ("field", "path"),
    [("live_path", "//otro-host/x"), ("ready_path", "/../admin"), ("info_path", "/\\otro-host"), ("live_path", "/a?b")],
)
async def test_a_tricky_path_is_refused_on_its_field(health_api: HealthApi, field, path):
    response = await health_api.client.post(PATH, json={**SERVICE, field: path})

    assert validation_errors(response) == [(field, PATH_INVALID)]


async def test_a_frontend_with_a_readiness_route_is_refused(health_api: HealthApi):
    response = await health_api.client.post(PATH, json={**FRONTEND, "ready_path": "/health/ready"})

    assert validation_errors(response) == [("ready_path", FRONTEND_READY_PATH)]
    assert await registry(health_api) == []


async def test_an_unknown_field_rejects_the_whole_request(health_api: HealthApi):
    response = await health_api.client.post(PATH, json={**SERVICE, "deleted_at": None})

    assert validation_errors(response) == [("deleted_at", "El campo «deleted_at» no está permitido.")]
    assert await registry(health_api) == []


# --- 6. Disabling and enabling ---


async def test_a_disabled_component_is_neither_shown_nor_called_but_stays_in_the_registry(health_api: HealthApi):
    component = await create(health_api)
    await health_api.reset_components()

    response = await health_api.client.patch(f"{PATH}/{component['id']}", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert "usuarios" not in await health_codes(health_api)
    assert await health_api.component_calls() == []
    assert [(c["code"], c["enabled"]) for c in await registry(health_api)] == [("usuarios", False)]

    await health_api.client.patch(f"{PATH}/{component['id']}", json={"enabled": True})

    assert "usuarios" in await health_codes(health_api)


# --- 7 and 8. Deleting and missing components ---


async def test_a_deleted_component_disappears_and_its_code_can_be_registered_again(health_api: HealthApi):
    component = await create(health_api)
    item = f"{PATH}/{component['id']}"

    response = await health_api.client.delete(item)

    assert (response.status_code, response.content) == (204, b"")
    assert "usuarios" not in await health_codes(health_api)
    assert await registry(health_api) == []
    for request in (
        health_api.client.get(item),
        health_api.client.patch(item, json={"name": "Otro"}),
        health_api.client.delete(item),
    ):
        assert (await request).status_code == 404
    again = await create(health_api)
    assert again["id"] != component["id"]


async def test_an_identifier_that_does_not_exist_is_not_found(health_api: HealthApi):
    unknown = uuid4()

    response = await health_api.client.get(f"{PATH}/{unknown}")

    assert response.status_code == 404
    assert response.json() == {
        "code": "monitored_component_not_found",
        "message": f"No se encontró el componente monitoreado con el identificador {unknown}.",
    }


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_an_identifier_that_is_not_a_uuid_is_a_validation_error(health_api: HealthApi, method):
    kwargs = {"json": {"name": "Otro"}} if method == "patch" else {}

    response = await getattr(health_api.client, method)(f"{PATH}/42", **kwargs)

    assert validation_errors(response) == [("component_id", "El identificador del componente debe ser un UUID.")]


# --- 9. Modifying ---


async def test_an_empty_modification_is_refused_and_nothing_changes(health_api: HealthApi):
    component = await create(health_api)

    response = await health_api.client.patch(f"{PATH}/{component['id']}", json={})

    assert validation_errors(response) == [("body", "Hay que enviar al menos un dato para modificar.")]
    assert (await health_api.client.get(f"{PATH}/{component['id']}")).json() == component


async def test_a_modification_changes_only_what_was_sent(health_api: HealthApi):
    component = await create(health_api, sort_order=10)

    response = await health_api.client.patch(f"{PATH}/{component['id']}", json={"name": "Cambio"})

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["sort_order"], body["code"], body["id"]) == ("Cambio", 10, "usuarios", component["id"])
    assert body["created_at"] == component["created_at"]


async def test_a_new_base_url_is_checked_against_the_allowed_list_again(health_api: HealthApi):
    component = await create(health_api)

    response = await health_api.client.patch(f"{PATH}/{component['id']}", json={"base_url": "http://otro-host"})

    assert validation_errors(response) == [("base_url", HOST_NOT_ALLOWED)]


async def test_turning_a_service_into_a_frontend_needs_a_null_readiness_route(health_api: HealthApi):
    component = await create(health_api)
    item = f"{PATH}/{component['id']}"

    refused = await health_api.client.patch(item, json={"kind": "frontend"})
    accepted = await health_api.client.patch(item, json={"kind": "frontend", "ready_path": None})

    assert validation_errors(refused) == [("ready_path", FRONTEND_READY_PATH)]
    assert accepted.status_code == 200
    assert (accepted.json()["kind"], accepted.json()["ready_path"]) == ("frontend", None)


async def test_a_modification_to_a_reserved_or_repeated_code_is_a_conflict(health_api: HealthApi):
    await create(health_api, code="pacientes")
    component = await create(health_api)

    for code in ("pacientes", "database"):
        response = await health_api.client.patch(f"{PATH}/{component['id']}", json={"code": code})
        assert response.status_code == 409, code
        assert response.json()["code"] == "monitored_component_code_already_exists"


# --- 10. The permission comes before the data ---


async def test_without_the_permission_invalid_data_is_forbidden_not_invalid(health_api: HealthApi):
    await health_api.grant(["health:read"])

    response = await health_api.client.post(PATH, json={"code": "X", "base_url": "ftp://nada"})

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert await registry(health_api) == []


# --- 11. No call carries the token ---


async def test_the_calls_to_a_registered_component_never_carry_the_token(health_api: HealthApi):
    await create(health_api)
    await health_api.reset_components()

    await health_api.health()

    calls = await health_api.component_calls()
    assert {call["path"] for call in calls} == {"/healthy/health/live", "/healthy/health/ready", "/healthy/info"}
    assert not any(call["has_authorization"] or call["has_cookie"] for call in calls)
    assert TEST_TOKEN not in str(calls)


# --- 12. The list ---


async def test_the_list_has_every_current_component_without_envelope_in_its_order(health_api: HealthApi):
    await create(health_api, code="ultimo", sort_order=30)
    await create(health_api, code="ab", sort_order=10)
    await create(health_api, code="a-c", sort_order=10)
    await create(health_api, code="apagado", sort_order=20, enabled=False)
    deleted = await create(health_api, code="borrado", sort_order=0)
    await health_api.client.delete(f"{PATH}/{deleted['id']}")

    found = await registry(health_api)

    assert isinstance(found, list)
    assert [(c["code"], c["enabled"]) for c in found] == [
        ("a-c", True),
        ("ab", True),
        ("apagado", False),
        ("ultimo", True),
    ]
    assert all(set(component) == FIELDS for component in found)


async def test_an_empty_registry_is_an_empty_list(health_api: HealthApi):
    assert await registry(health_api) == []


# --- FR-037: with the database unavailable nothing changes (user story 5) ---


class UnavailableSession:
    """A session whose database is gone: every statement fails as the driver would report it."""

    def _failure(self) -> OperationalError:
        return OperationalError("UPDATE monitored_components", {}, OSError("SECRETO-INTERNO"))

    async def execute(self, *args, **kwargs):
        raise self._failure()

    async def scalars(self, *args, **kwargs):
        raise self._failure()

    async def commit(self) -> None:
        raise self._failure()

    async def rollback(self) -> None:
        return None


INTERNAL_ERROR = {"code": "internal_error", "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde."}


async def test_with_the_database_unavailable_the_registry_fails_without_changing_anything(health_api: HealthApi):
    item = f"{PATH}/{await health_api.insert_component(code='usuarios')}"
    health_api.use_value(get_monitored_component_repository, MonitoredComponentRepository(UnavailableSession()))
    state = health_api.app.state.health
    # The application answers 500 and then raises the error again for the server log.
    transport = httpx.ASGITransport(app=health_api.app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://api.test", headers=dict(health_api.client.headers)
    ) as client:
        responses = [
            await client.post(PATH, json={**SERVICE, "code": "nuevo"}),
            await client.patch(item, json={"name": "Cambio"}),
            await client.delete(item),
        ]

    for response in responses:
        assert (response.status_code, response.json()) == (500, INTERNAL_ERROR)
        assert "SECRETO-INTERNO" not in response.text
    assert state.generation == 0  # nothing was invalidated
    assert (await health_api.health()).status_code == 200

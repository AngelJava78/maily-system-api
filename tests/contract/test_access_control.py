"""Access control (US2): every operation needs a token and the permission the users API grants.

The mechanics are proven with a probe router defined here (two protected routes); the real six
operations are checked one by one in `test_permission_coverage.py` once they exist.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter
from pydantic import BaseModel

from src.dependencies import get_users_api_client
from src.integrations.users_api import UsersApiClient
from src.main import create_app
from src.routers.openapi_docs import protected
from src.security import SUBSCRIPTIONS_READ, SUBSCRIPTIONS_WRITE
from tests.helpers import USERS_BASE_URL, grant

TOKEN = "SECRET-TOKEN-XYZ"
LEAK_MARKER = "SECRETO-INTERNO"
UNAVAILABLE_BODY = {
    "code": "authorization_unavailable",
    "message": "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde.",
}


class ProbeBody(BaseModel):
    value: int


@dataclass
class Probe:
    client: httpx.AsyncClient
    users_stub: httpx.AsyncClient
    executed: list[str] = field(default_factory=list)
    holder: dict = field(default_factory=lambda: {"timeout": 5.0})

    def set_timeout(self, seconds: float) -> None:
        self.holder["timeout"] = seconds

    def headers(self, token: str = TOKEN) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def users_calls(self) -> list[dict]:
        return (await self.users_stub.get("/__test__/calls")).json()

    async def fault(self, mode: str, count: int = 1, delay: float = 30) -> None:
        response = await self.users_stub.post(
            "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay}
        )
        assert response.status_code == 200


@pytest_asyncio.fixture
async def probe(users_stub) -> AsyncIterator[Probe]:
    executed: list[str] = []
    router = APIRouter()

    @router.get("/probe", **protected(SUBSCRIPTIONS_READ))
    async def read_probe() -> dict:
        executed.append("GET")
        return {"ok": True}

    @router.post("/probe", **protected(SUBSCRIPTIONS_WRITE))
    async def write_probe(body: ProbeBody) -> dict:
        executed.append("POST")
        return {"value": body.value}

    app = create_app()
    app.include_router(router)
    instance = Probe(client=None, users_stub=users_stub, executed=executed)  # client set below

    async def users_api_client() -> UsersApiClient:
        return UsersApiClient(users_stub, USERS_BASE_URL, instance.holder["timeout"])

    app.dependency_overrides[get_users_api_client] = users_api_client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as client:
        instance.client = client
        yield instance


# --- (a) no usable token ---


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Basic dXNlcjpwYXNz"}, {"Authorization": "Bearer"}],
    ids=["no-header", "basic-scheme", "empty-bearer"],
)
async def test_without_a_usable_token_the_person_is_asked_to_log_in(probe: Probe, headers):
    response = await probe.client.get("/probe", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert await probe.users_calls() == []
    assert probe.executed == []


# --- (b) token rejected by the users API ---


async def test_an_unknown_token_is_an_invalid_token(probe: Probe):
    response = await probe.client.get("/probe", headers=probe.headers("unknown"))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'
    assert probe.executed == []


async def test_an_expired_token_is_reported_as_expired(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ], expired=True)

    response = await probe.client.get("/probe", headers=probe.headers())

    assert response.status_code == 401
    assert response.json()["code"] == "token_expired"
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


async def test_an_oversized_token_is_rejected_without_calling_the_users_api(probe: Probe):
    response = await probe.client.get("/probe", headers=probe.headers("a" * 9000))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert await probe.users_calls() == []


# --- (c) authenticated without the permission ---


async def test_a_person_without_the_permission_is_denied_naming_it(probe: Probe):
    await grant(probe.users_stub, TOKEN, [])

    response = await probe.client.get("/probe", headers=probe.headers())

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert response.json()["message"] == (
        "No tiene permiso para realizar esta operación. Permiso requerido: subscriptions:read."
    )
    assert probe.executed == []


async def test_read_permission_does_not_allow_writing(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])

    read = await probe.client.get("/probe", headers=probe.headers())
    write = await probe.client.post("/probe", json={"value": 1}, headers=probe.headers())

    assert read.status_code == 200
    assert write.status_code == 403
    assert "subscriptions:write" in write.json()["message"]
    assert probe.executed == ["GET"]


# --- (d) with the permission ---


async def test_a_person_with_the_permission_runs_the_operation(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ, SUBSCRIPTIONS_WRITE])

    read = await probe.client.get("/probe", headers=probe.headers())
    write = await probe.client.post("/probe", json={"value": 7}, headers=probe.headers())

    assert (read.status_code, read.json()) == (200, {"ok": True})
    assert (write.status_code, write.json()) == (200, {"value": 7})


# --- (e) the users API cannot decide: fail closed ---


@pytest.mark.parametrize(
    "mode",
    ["unavailable", "rate_limited", "malformed", "wrong_permission", "not_json", "forbidden", "redirect"],
)
async def test_when_the_users_api_cannot_decide_nothing_runs(probe: Probe, mode: str):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])
    await probe.fault(mode)

    response = await probe.client.get("/probe", headers=probe.headers())

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY
    assert probe.executed == []


async def test_a_users_api_that_times_out_leaves_the_operation_unexecuted(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])
    probe.set_timeout(0.2)
    await probe.fault("slow", delay=1)

    response = await probe.client.get("/probe", headers=probe.headers())

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY
    assert probe.executed == []


async def test_a_503_never_reveals_details_of_the_other_service(probe: Probe, caplog):
    caplog.set_level(logging.DEBUG)
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])
    leaked = []
    for mode in ("not_json", "unavailable", "malformed"):
        await probe.fault(mode)
        response = await probe.client.get("/probe", headers=probe.headers())
        leaked.append(response.text)

    assert all(text == httpx.Response(503, json=UNAVAILABLE_BODY).text for text in leaked)
    assert all(LEAK_MARKER not in text and "users-api.test" not in text for text in leaked)
    assert LEAK_MARKER not in caplog.text


# --- every request is decided on its own, with the exact permission ---


async def test_one_call_per_request_with_the_exact_permission_and_the_token_untouched(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ, SUBSCRIPTIONS_WRITE])

    await probe.client.get("/probe", headers=probe.headers())
    await probe.client.post("/probe", json={"value": 1}, headers=probe.headers())

    recorded = await probe.users_calls()
    assert [(c["permission"], c["authorization"]) for c in recorded] == [
        ("subscriptions:read", f"Bearer {TOKEN}"),
        ("subscriptions:write", f"Bearer {TOKEN}"),
    ]


async def test_decisions_are_not_cached_and_a_revoked_permission_applies_next_request(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])
    first = await probe.client.get("/probe", headers=probe.headers())

    await grant(probe.users_stub, TOKEN, [])  # the permission is revoked in the users API
    second = await probe.client.get("/probe", headers=probe.headers())

    assert (first.status_code, second.status_code) == (200, 403)
    assert len(await probe.users_calls()) == 2


# --- precedence: identity -> permission -> validation (research R4) ---


async def test_identity_is_checked_before_the_body_is_validated(probe: Probe):
    response = await probe.client.post("/probe", json={"value": "not a number"})

    assert response.status_code == 401


async def test_the_permission_is_checked_before_the_body_is_validated(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])

    response = await probe.client.post(
        "/probe", json={"value": "not a number"}, headers=probe.headers()
    )

    assert response.status_code == 403


async def test_with_the_permission_an_invalid_body_is_a_validation_error(probe: Probe):
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_WRITE])

    response = await probe.client.post(
        "/probe", json={"value": "not a number"}, headers=probe.headers()
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_an_unreadable_body_is_the_only_exception_and_answers_422_even_without_token(
    probe: Probe,
):
    # Accepted exception to FR-004 (spec, Clarifications): an unreadable body carries no data to
    # protect and the answer reveals nothing.
    response = await probe.client.post(
        "/probe", content=b"{oops", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["errors"][0]["field"] == "body"


# --- the token never leaks ---


async def test_the_token_never_appears_in_a_response_or_in_the_logs(probe: Probe, caplog):
    caplog.set_level(logging.DEBUG)
    await grant(probe.users_stub, TOKEN, [SUBSCRIPTIONS_READ])
    bodies = []
    bodies.append((await probe.client.get("/probe", headers=probe.headers())).text)
    bodies.append((await probe.client.post("/probe", json={"value": 1}, headers=probe.headers())).text)
    await probe.fault("unavailable")
    bodies.append((await probe.client.get("/probe", headers=probe.headers())).text)

    assert all(TOKEN not in body for body in bodies)
    assert TOKEN not in caplog.text


# --- documentation stays public and declares the security of each operation ---


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
async def test_the_documentation_needs_no_token(probe: Probe, path: str):
    response = await probe.client.get(path)

    assert response.status_code == 200


async def test_the_openapi_declares_security_permission_and_error_responses(probe: Probe):
    schema = (await probe.client.get("/openapi.json")).json()

    for method, permission in (("get", "subscriptions:read"), ("post", "subscriptions:write")):
        operation = schema["paths"]["/probe"][method]
        assert operation["security"] == [{"BearerAuth": []}]
        assert operation["x-required-permission"] == permission
        assert {"401", "403", "503"} <= set(operation["responses"])
    assert schema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"

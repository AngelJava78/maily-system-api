"""Simulation of mailySoft-pagos (specs/006-cobro-real-suscripciones/contracts/e2e-stubs.md).

Self-contained: it imports nothing from `src/` and uses no relative imports (same rule as
`tests/stubs/users_api/app.py` and `tests/stubs/clinics_api/app.py`). State lives in memory and is
lost with the process. Every fault body carries the marker `SECRETO-INTERNO` so the tests can check
that the details of another service never reach the clients of this API.

It imitates the two operations this service consumes (`POST /api/v1/payments` and
`GET /api/v1/payments/{id}`) and offers a test-only surface under `/__test__/`.
"""

import asyncio
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

MARKER = "SECRETO-INTERNO"

FAULT_MODES = (
    "unavailable",
    "forbidden",
    "not_found",
    "malformed",
    "not_json",
    "redirect",
    "slow",
    "unauthorized_unreadable",
    "unauthorized_unknown",
)
FAULT_OPERATIONS = ("create", "get")

_BODY_FIELDS = ("provider", "amount", "currency", "resource_type", "resource_id", "description")


class TokenIn(BaseModel):
    token: str
    permissions: list[str] = Field(default_factory=list)
    expired: bool = False


class FaultIn(BaseModel):
    mode: str
    count: int = 1
    delay_seconds: float = 30
    operation: str = "create"


class StatusIn(BaseModel):
    status: str


class _RecordCalls:
    """Pure ASGI middleware: records every request except the ones to `/__test__/`."""

    def __init__(self, app: Any, state: dict[str, Any]) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and not scope["path"].startswith("/__test__/"):
            headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
            self.state["calls"].append(
                {
                    "path": scope["path"],
                    "has_authorization": "authorization" in headers,
                    "authorization": headers.get("authorization"),
                    "idempotency_key": headers.get("idempotency-key"),
                    "header_names": sorted(headers),
                }
            )
        await self.app(scope, receive, send)


def _payment_body(payment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payment["id"],
        "status": payment["status"],
        "provider": payment["provider"],
        "amount": payment["amount"],
        "currency": payment["currency"],
        "resource_type": payment["resource_type"],
        "resource_id": payment["resource_id"],
        "description": payment["description"],
        "metadata": None,
        "refunded_amount": 0,
        "checkout_url": payment["checkout_url"] if payment["status"] == "pending" else None,
        "idempotency_key": payment["idempotency_key"],
        "created_at": "2026-11-10T00:00:00Z",
        "updated_at": "2026-11-10T00:00:00Z",
    }


def create_stub_app() -> FastAPI:
    app = FastAPI(title="mailySoft-pagos (stub)")
    state: dict[str, Any] = {"tokens": {}, "faults": [], "calls": [], "payments": {}, "by_key": {}}
    app.add_middleware(_RecordCalls, state=state)

    def take_fault(operation: str) -> dict[str, Any] | None:
        for fault in state["faults"]:
            if fault["operation"] == operation and fault["remaining"] > 0:
                fault["remaining"] -= 1
                return fault
        return None

    def error(status: int, code: str) -> JSONResponse:
        return JSONResponse({"code": code, "message": f"{MARKER} detalle interno"}, status_code=status)

    def authorize(request: Request, permission: str) -> JSONResponse | dict[str, Any]:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthenticated")
        entry = state["tokens"].get(token.strip())
        if entry is None:
            return error(401, "invalid_token")
        if entry["expired"]:
            return error(401, "token_expired")
        if permission not in entry["permissions"]:
            return error(403, "permission_denied")
        return entry

    @app.post("/api/v1/payments")
    async def create_payment(request: Request):
        fault = take_fault("create")
        if fault is not None:
            mode = fault["mode"]
            if mode == "unavailable":
                return error(503, "payment_provider_unavailable")
            if mode == "forbidden":
                return error(403, "permission_denied")
            if mode == "malformed":
                return JSONResponse({"detail": MARKER})
            if mode == "not_json":
                return PlainTextResponse(MARKER, status_code=200)
            if mode == "redirect":
                return RedirectResponse("http://evil.test/steal", status_code=307)
            if mode == "unauthorized_unreadable":
                return PlainTextResponse(MARKER, status_code=401)
            if mode == "unauthorized_unknown":
                return error(401, "something_else")
            if mode == "slow":
                await asyncio.sleep(fault["delay_seconds"])

        entry = authorize(request, "payments:write")
        if isinstance(entry, JSONResponse):
            return entry
        try:
            body = await request.json()
        except ValueError:
            return error(422, "validation_error")
        if not isinstance(body, dict) or any(field not in body for field in _BODY_FIELDS[:-1]):
            return error(422, "validation_error")

        idempotency_key = request.headers.get("idempotency-key") or str(uuid.uuid4())
        existing_id = state["by_key"].get(idempotency_key)
        if existing_id is not None:
            existing = state["payments"][existing_id]
            same = all(existing[field] == body.get(field) for field in _BODY_FIELDS[:-1])
            if not same:
                return error(409, "idempotency_key_conflict")
            return JSONResponse(_payment_body(existing), status_code=201)

        payment_id = str(uuid.uuid4())
        payment = {
            "id": payment_id,
            "status": "pending",
            "provider": body["provider"],
            "amount": body["amount"],
            "currency": body["currency"],
            "resource_type": body["resource_type"],
            "resource_id": body["resource_id"],
            "description": body.get("description"),
            "checkout_url": f"https://pagos.test/checkout/{payment_id}",
            "idempotency_key": idempotency_key,
        }
        state["payments"][payment_id] = payment
        state["by_key"][idempotency_key] = payment_id
        return JSONResponse(_payment_body(payment), status_code=201)

    @app.get("/api/v1/payments/{payment_id}")
    async def get_payment(request: Request, payment_id: str):
        fault = take_fault("get")
        if fault is not None:
            mode = fault["mode"]
            if mode == "unavailable":
                return error(503, "authorization_unavailable")
            if mode == "forbidden":
                return error(403, "permission_denied")
            if mode == "not_found":
                return error(404, "payment_not_found")
            if mode == "malformed":
                return JSONResponse({"detail": MARKER})
            if mode == "not_json":
                return PlainTextResponse(MARKER, status_code=200)
            if mode == "redirect":
                return RedirectResponse("http://evil.test/steal", status_code=307)
            if mode == "slow":
                await asyncio.sleep(fault["delay_seconds"])

        entry = authorize(request, "payments:read")
        if isinstance(entry, JSONResponse):
            return entry
        payment = state["payments"].get(payment_id)
        if payment is None:
            return error(404, "payment_not_found")
        return _payment_body(payment)

    @app.post("/__test__/tokens")
    async def register_token(body: TokenIn):
        state["tokens"][body.token] = {"permissions": set(body.permissions), "expired": body.expired}
        return {"token": "registered", "permissions": sorted(body.permissions)}

    @app.post("/__test__/payments/{payment_id}/status")
    async def set_status(payment_id: str, body: StatusIn):
        payment = state["payments"].get(payment_id)
        if payment is None:
            return JSONResponse({"detail": "unknown payment"}, status_code=404)
        payment["status"] = body.status
        return {"id": payment_id, "status": body.status}

    @app.post("/__test__/faults")
    async def add_fault(body: FaultIn):
        if body.mode not in FAULT_MODES:
            return JSONResponse({"detail": f"unknown mode {body.mode!r}"}, status_code=422)
        if body.operation not in FAULT_OPERATIONS:
            return JSONResponse({"detail": f"unknown operation {body.operation!r}"}, status_code=422)
        state["faults"].append(
            {
                "mode": body.mode,
                "remaining": body.count,
                "delay_seconds": body.delay_seconds,
                "operation": body.operation,
            }
        )
        return {"mode": body.mode, "count": body.count, "operation": body.operation}

    @app.get("/__test__/calls")
    async def calls():
        return state["calls"]

    @app.post("/__test__/reset")
    async def reset():
        state["tokens"].clear()
        state["faults"].clear()
        state["calls"].clear()
        state["payments"].clear()
        state["by_key"].clear()
        return {"reset": True}

    return app


app = create_stub_app()

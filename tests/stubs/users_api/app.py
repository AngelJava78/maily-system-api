"""Simulation of the users API (specs/001-subscriptions-api/contracts/e2e-stubs.md, section 1).

Self-contained: it imports nothing from `src/` and uses no relative imports, because the end-to-end
stack runs it with `uvicorn app:app --app-dir /stub`. The state lives in memory and is lost with the
process. Every fault body carries the marker `SECRETO-INTERNO` so the tests can check that the details
of another service never reach the clients of the subscriptions API.

It imitates the operation the subscriptions API consumes (`GET /api/v1/authorization/check`) and
offers a test-only surface under `/__test__/`.
"""

import asyncio
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")
MARKER = "SECRETO-INTERNO"

FAULT_MODES = (
    "unavailable",
    "rate_limited",
    "forbidden",
    "not_found",
    "unprocessable",
    "malformed",
    "wrong_permission",
    "not_json",
    "redirect",
    "slow",
    "unauthorized_unreadable",
    "unauthorized_unknown",
)


class TokenIn(BaseModel):
    token: str
    permissions: list[str] = Field(default_factory=list)
    expired: bool = False


class FaultIn(BaseModel):
    mode: str
    count: int = 1
    delay_seconds: float = 30


class _RecordCalls:
    """Pure ASGI middleware: records every request except the ones to `/__test__/`."""

    def __init__(self, app: Any, state: dict[str, Any]) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and not scope["path"].startswith("/__test__/"):
            headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
            query = parse_qs(scope["query_string"].decode())
            self.state["calls"].append(
                {
                    "path": scope["path"],
                    "permission": (query.get("permission") or [None])[0],
                    "has_authorization": "authorization" in headers,
                    "authorization": headers.get("authorization"),
                    "header_names": sorted(headers),
                }
            )
        await self.app(scope, receive, send)


def create_stub_app() -> FastAPI:
    app = FastAPI(title="Users API (stub)")
    state: dict[str, Any] = {"tokens": {}, "faults": [], "calls": []}
    app.add_middleware(_RecordCalls, state=state)

    def take_fault() -> dict[str, Any] | None:
        for fault in state["faults"]:
            if fault["remaining"] > 0:
                fault["remaining"] -= 1
                return fault
        return None

    def error(status: int, code: str) -> JSONResponse:
        return JSONResponse({"code": code, "message": f"{MARKER} detalle interno"}, status_code=status)

    @app.get("/api/v1/authorization/check")
    async def check(request: Request, permission: str | None = None):
        fault = take_fault()
        if fault is not None:
            mode = fault["mode"]
            if mode == "unavailable":
                return error(503, "authentication_unavailable")
            if mode == "rate_limited":
                return error(429, "rate_limited")
            if mode == "forbidden":
                return error(403, "forbidden")
            if mode == "not_found":
                return error(404, "not_found")
            if mode == "unprocessable":
                return error(422, "validation_error")
            if mode == "malformed":
                return JSONResponse({"permission": permission, "detail": MARKER})
            if mode == "wrong_permission":
                return JSONResponse({"permission": "other:permission", "allowed": True})
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

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthenticated")
        entry = state["tokens"].get(token.strip())
        if entry is None:
            return error(401, "invalid_token")
        if entry["expired"]:
            return error(401, "token_expired")
        if permission is None or len(permission) > 100 or not PERMISSION_PATTERN.match(permission):
            return error(422, "validation_error")
        return {"permission": permission, "allowed": permission in entry["permissions"]}

    @app.post("/__test__/tokens")
    async def register_token(body: TokenIn):
        state["tokens"][body.token] = {
            "permissions": set(body.permissions),
            "expired": body.expired,
        }
        return {"token": "registered", "permissions": sorted(body.permissions)}

    @app.post("/__test__/faults")
    async def add_fault(body: FaultIn):
        if body.mode not in FAULT_MODES:
            return JSONResponse({"detail": f"unknown mode {body.mode!r}"}, status_code=422)
        state["faults"].append(
            {"mode": body.mode, "remaining": body.count, "delay_seconds": body.delay_seconds}
        )
        return {"mode": body.mode, "count": body.count}

    @app.get("/__test__/calls")
    async def calls():
        return state["calls"]

    @app.post("/__test__/reset")
    async def reset():
        state["tokens"].clear()
        state["faults"].clear()
        state["calls"].clear()
        return {"reset": True}

    return app


app = create_stub_app()

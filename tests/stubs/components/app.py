"""Simulation of the monitored components (specs/005-health-monitoring/contracts/e2e-collection.md).

Self-contained: it imports nothing from `src/` and uses no relative imports, because the end-to-end
stack runs it with `uvicorn app:app --app-dir /stub`. One process imitates several components, one
per path prefix: the `base_url` of a component is `http://<host>/<prefix>`, so its routes are
`/<prefix>/health/live`, `/<prefix>/health/ready`, `/<prefix>/info` or, for a frontend,
`/<prefix>/healthz/`. Every body of a failure carries the marker `SECRETO-INTERNO`, so the tests can
check that nothing of another service reaches the clients of the health API. The state lives in
memory and is lost with the process.

The test-only surface lives under `/__test__/`: the calls received (`GET /__test__/calls`), a reset
(`POST /__test__/reset`) and the mode of a prefix (`POST /__test__/modes`).
"""

import asyncio
import gzip
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel

MARKER = "SECRETO-INTERNO"
MODES = (
    "healthy",
    "not-ready",
    "html",
    "not-json",
    "redirect",
    "slow",
    "too-large",
    "too-large-chunked",
    "gzip",
    "info-incomplete",
    "many-checks",
    "error",
    "spa",
)
DEFAULT_SLOW_SECONDS = 30.0
LARGE_BYTES = 70 * 1024  # above the 64 KiB that a health check reads
COOKIE = f"session={MARKER}; Path=/"

LIVE_OK = {"status": "ok"}
READY_OK = {
    "status": "ok",
    "checks": [{"name": "database", "status": "ok", "latency_ms": 3, "error": None}],
}
NOT_READY = {
    "status": "unavailable",
    "checks": [
        {"name": "database", "status": "error", "latency_ms": 2000, "error": "timeout"},
        {"name": "cache", "status": "error", "latency_ms": 5, "error": "disk_full"},
    ],
}
INCOMPLETE_INFO = {
    "version": 123,
    "commit": "a" * 100 + "\u0007",
    "build_date": "ayer",
    "environment": None,
    "extra": MARKER,
}
HTML_PAGE = f"<!doctype html><html><body>MailySoft {MARKER}</body></html>"


def info_of(prefix: str) -> dict[str, Any]:
    return {
        "service": f"stub-{prefix}",
        "version": "1.4.2",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "build_date": "2026-10-20T15:30:00-06:00",
        "environment": "e2e",
    }


def many_checks() -> list[Any]:
    """25 checks: the first is fine and some of the rest are malformed, like a careless service."""
    checks: list[Any] = [{"name": "database", "status": "ok", "latency_ms": 2, "error": None}]
    checks += [
        {"status": "ok", "latency_ms": 1, "error": None},  # no name
        {"name": "queue", "status": "warn", "latency_ms": 1, "error": None},  # unknown status
        {"name": "cache", "status": "ok", "latency_ms": "12", "error": None},  # latency as text
        {"name": "disk", "status": "ok", "latency_ms": True, "error": None},  # latency as a boolean
        {"name": "mail", "status": "error", "latency_ms": 9, "error": "weird"},  # unknown error
        "not an object",
    ]
    checks += [
        {"name": f"extra-{n}", "status": "ok", "latency_ms": n, "error": None} for n in range(19)
    ]
    return checks


class ModeIn(BaseModel):
    prefix: str
    mode: str


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
                    "method": scope["method"],
                    "header_names": sorted(headers),
                    "has_authorization": "authorization" in headers,
                    "has_cookie": "cookie" in headers,
                }
            )
        await self.app(scope, receive, send)


def create_stub_app() -> FastAPI:
    app = FastAPI(title="Monitored components (stub)")
    state: dict[str, Any] = {"calls": [], "modes": {}, "slow_seconds": DEFAULT_SLOW_SECONDS}
    app.add_middleware(_RecordCalls, state=state)

    # The test-only routes go first: the catch-all below would also match them.
    @app.get("/__test__/calls")
    async def calls():
        return state["calls"]

    @app.post("/__test__/reset")
    async def reset():
        state["calls"].clear()
        state["modes"].clear()
        state["slow_seconds"] = DEFAULT_SLOW_SECONDS
        return {"reset": True}

    @app.post("/__test__/modes")
    async def set_mode(body: ModeIn):
        if body.mode not in MODES:
            return JSONResponse({"detail": f"unknown mode {body.mode!r}"}, status_code=422)
        state["modes"][body.prefix] = body.mode
        return {"prefix": body.prefix, "mode": body.mode}

    def ok(body: dict[str, Any]) -> JSONResponse:
        return JSONResponse(body, headers={"Set-Cookie": COOKIE})

    def healthy(prefix: str, rest: str) -> Response:
        if rest == "health/live":
            return ok(LIVE_OK)
        if rest == "health/ready":
            return ok(READY_OK)
        if rest == "info":
            return ok(info_of(prefix))
        if rest == "healthz/":
            return HTMLResponse(HTML_PAGE)
        if rest == "healthz":  # like a web server that adds the final slash
            return RedirectResponse(f"/{prefix}/healthz/", status_code=301)
        return JSONResponse({"detail": MARKER}, status_code=404)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"status": "ok", "padding": "'
        for _ in range(LARGE_BYTES // 1024):
            yield b"x" * 1024
        yield f'", "marker": "{MARKER}"}}'.encode()

    @app.get("/{prefix}/{rest:path}")
    async def component(prefix: str, rest: str):
        mode = state["modes"].get(prefix, prefix)
        if mode == "healthy":
            return healthy(prefix, rest)
        if mode == "not-ready":
            return JSONResponse(NOT_READY, status_code=503) if rest == "health/ready" else healthy(prefix, rest)
        if mode in ("html", "spa"):
            return HTMLResponse(HTML_PAGE)
        if mode == "not-json":
            return PlainTextResponse(f"ok {MARKER}")
        if mode == "redirect":
            return RedirectResponse(f"/healthy/{rest}", status_code=307)
        if mode == "slow":
            await asyncio.sleep(state["slow_seconds"])
            return healthy(prefix, rest)
        if mode == "too-large":
            return JSONResponse({"status": "ok", "padding": "x" * LARGE_BYTES, "marker": MARKER})
        if mode == "too-large-chunked":
            return StreamingResponse(chunks(), media_type="application/json")
        if mode == "gzip":
            body = gzip.compress(json.dumps(LIVE_OK).encode())
            return Response(body, media_type="application/json", headers={"Content-Encoding": "gzip"})
        if mode == "info-incomplete":
            return JSONResponse(INCOMPLETE_INFO) if rest == "info" else healthy(prefix, rest)
        if mode == "many-checks":
            if rest == "health/ready":
                return JSONResponse({"status": "ok", "checks": many_checks()})
            return healthy(prefix, rest)
        if mode == "error":
            return JSONResponse({"detail": MARKER}, status_code=500)
        return JSONResponse({"detail": f"unknown component {MARKER}"}, status_code=404)

    return app


app = create_stub_app()

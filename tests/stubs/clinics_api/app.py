"""Simulation of the clinics API (specs/001-subscriptions-api/contracts/e2e-stubs.md, section 1;
ampliación en specs/010-cobro-real-suscripciones/contracts/e2e-stubs.md).

Self-contained: it imports nothing from `src/` and uses no relative imports, because the end-to-end
stack runs it with `uvicorn app:app --app-dir /stub`. The state lives in memory. Every fault body
carries the marker `SECRETO-INTERNO` so the tests can check that the details of another service never
reach the clients of the subscriptions API.

It imitates the three operations the system API consumes: `GET /api/v1/clinics/subscription-counts`
(spec 001), `GET /api/v1/clinics/clinic-subscriptions/{id}` (spec 010-cobro-real-suscripciones,
research R6) and `GET /api/v1/organizations/{id}` (spec 010-subscription-periods, including
`billing_period`, which the real API does not publish yet) — Clinics does not exist as a real
service yet, so this is the only place those last two contracts live until it does. Offers a
test-only surface under `/__test__/`.
"""

import asyncio
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

MARKER = "SECRETO-INTERNO"

FAULT_MODES = (
    "unavailable",
    "unauthorized",
    "forbidden",
    "malformed",
    "negative_count",
    "unrequested_id",
    "duplicate_id",
    "not_json",
    "redirect",
    "slow",
    "not_found",
    # Only for the organizations operation (spec 010-subscription-periods):
    "missing_billing_period",
    "invalid_billing_period",
    "not_found_other_code",
)
FAULT_OPERATIONS = ("counts", "clinic_subscription", "organizations")


class FaultIn(BaseModel):
    mode: str
    count: int = 1
    delay_seconds: float = 30
    # The operation that the fault applies to; `counts` (the first one of this stub) by default, so
    # the faults of spec 001 behave exactly as before.
    operation: str = "counts"


class ClinicTokenIn(BaseModel):
    token: str
    tenant_id: str | None = None


class ClinicSubscriptionIn(BaseModel):
    id: str
    tenant_id: str
    subscription_id: int
    billing_cycle: str


class OrganizationIn(BaseModel):
    id: str
    subscription_id: int
    billing_period: str = "monthly"
    created_at: str
    # Only the owner of the organization reads it; any other token gets a 404, like the real API.
    owner_token: str


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
                    "subscription_ids": [int(v) for v in query.get("subscription_id", []) if v.isdigit()],
                    "authorization": headers.get("authorization"),
                    "header_names": sorted(headers),
                }
            )
        await self.app(scope, receive, send)


def create_stub_app() -> FastAPI:
    app = FastAPI(title="Clinics API (stub)")
    state: dict[str, Any] = {
        "counts": {},
        "faults": [],
        "calls": [],
        "organizations": {},
        # spec 010-cobro-real-suscripciones: a token here only carries the organization Clinics
        # would resolve it to; it is a separate registry from the users API stub (Clinics is a
        # different service).
        "clinic_tokens": {},
        "clinic_subscriptions": {},
    }
    app.add_middleware(_RecordCalls, state=state)

    def take_fault(operation: str = "counts") -> dict[str, Any] | None:
        for fault in state["faults"]:
            if fault["remaining"] > 0 and fault["operation"] == operation:
                fault["remaining"] -= 1
                return fault
        return None

    def error(status: int, code: str) -> JSONResponse:
        return JSONResponse({"code": code, "message": f"{MARKER} detalle interno"}, status_code=status)

    @app.get("/api/v1/clinics/subscription-counts")
    async def subscription_counts(request: Request):
        requested = [int(v) for v in request.query_params.getlist("subscription_id") if v.isdigit()]
        mode = None
        fault = take_fault("counts")
        if fault is not None:
            mode = fault["mode"]
            if mode == "unavailable":
                return error(503, "unavailable")
            if mode == "unauthorized":
                return error(401, "unauthorized")
            if mode == "forbidden":
                return error(403, "forbidden")
            if mode == "malformed":
                return JSONResponse({"detail": MARKER})
            if mode == "not_json":
                return PlainTextResponse(MARKER, status_code=200)
            if mode == "redirect":
                return RedirectResponse("http://evil.test/steal", status_code=307)
            if mode == "slow":
                await asyncio.sleep(fault["delay_seconds"])

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthorized")

        items = [
            {"subscription_id": subscription_id, "clinics_count": count}
            for subscription_id, count in sorted(state["counts"].items())
            if count >= 1 and (not requested or subscription_id in requested)
        ]
        if mode == "negative_count":
            items = [{"subscription_id": requested[0] if requested else 1, "clinics_count": -1}]
        elif mode == "unrequested_id":
            # Not requested when a filter was sent and not a valid identifier (< 1) otherwise.
            items = items + [{"subscription_id": 0, "clinics_count": 1}]
        elif mode == "duplicate_id":
            items = items + (items[:1] or [{"subscription_id": 1, "clinics_count": 1}] * 2)
        return {"items": items}

    @app.get("/api/v1/clinics/clinic-subscriptions/{clinic_subscription_id}")
    async def get_clinic_subscription(request: Request, clinic_subscription_id: str):
        fault = take_fault("clinic_subscription")
        if fault is not None:
            mode = fault["mode"]
            if mode == "unavailable":
                return error(503, "unavailable")
            if mode == "forbidden":
                return error(403, "forbidden")
            if mode == "not_found":
                return error(404, "clinic_subscription_not_found")
            if mode == "malformed":
                return JSONResponse({"detail": MARKER})
            if mode == "not_json":
                return PlainTextResponse(MARKER, status_code=200)
            if mode == "redirect":
                return RedirectResponse("http://evil.test/steal", status_code=307)
            if mode == "slow":
                await asyncio.sleep(fault["delay_seconds"])

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthorized")
        caller = state["clinic_tokens"].get(token.strip())
        if caller is None:
            return error(404, "clinic_subscription_not_found")

        subscription = state["clinic_subscriptions"].get(clinic_subscription_id)
        caller_tenant_id = caller.get("tenant_id")
        if (
            subscription is None
            or caller_tenant_id is None
            or subscription["tenant_id"].lower() != caller_tenant_id.lower()
        ):
            # Same answer whether it does not exist, is cancelled (not modelled: just absent), or
            # belongs to another organization (indistinguishable, FR-003).
            return error(404, "clinic_subscription_not_found")
        return {
            "tenant_id": subscription["tenant_id"],
            "subscription_id": subscription["subscription_id"],
            "billing_cycle": subscription["billing_cycle"],
        }

    @app.get("/api/v1/organizations/{organization_id}")
    async def get_organization(organization_id: str, request: Request):
        fault = take_fault("organizations")
        mode = fault["mode"] if fault is not None else None
        if mode == "unavailable":
            return error(503, "unavailable")
        if mode == "unauthorized":
            return error(401, "unauthorized")
        if mode == "forbidden":
            return error(403, "permission_denied")
        if mode == "malformed":
            return JSONResponse({"detail": MARKER})
        if mode == "not_json":
            return PlainTextResponse(MARKER, status_code=200)
        if mode == "redirect":
            return RedirectResponse("http://evil.test/steal", status_code=307)
        if mode == "not_found_other_code":
            return error(404, "route_not_found")
        if mode == "slow":
            await asyncio.sleep(fault["delay_seconds"])

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthorized")

        organization = state["organizations"].get(organization_id)
        if organization is None or organization["owner_token"] != token.strip():
            # Not the person's own, or it does not exist: the real API does not tell them apart.
            return error(404, "not_found")

        body: dict[str, Any] = {
            "id": organization["id"],
            "name": "Organización de prueba",  # an extra field that the consumer must ignore
            "subscription_id": organization["subscription_id"],
            "billing_period": organization["billing_period"],
            "created_at": organization["created_at"],
        }
        if mode == "missing_billing_period":
            del body["billing_period"]
        elif mode == "invalid_billing_period":
            body["billing_period"] = "weekly"
        return body

    @app.post("/__test__/organizations")
    async def set_organization(body: OrganizationIn):
        state["organizations"][body.id] = body.model_dump()
        return {"id": body.id}

    @app.post("/__test__/counts")
    async def set_counts(body: dict[str, int]):
        state["counts"] = {int(key): value for key, value in body.items()}
        return {"counts": state["counts"]}

    @app.post("/__test__/tokens")
    async def register_clinic_token(body: ClinicTokenIn):
        state["clinic_tokens"][body.token] = {"tenant_id": body.tenant_id}
        return {"token": "registered", "tenant_id": body.tenant_id}

    @app.post("/__test__/clinic-subscriptions")
    async def register_clinic_subscription(body: ClinicSubscriptionIn):
        state["clinic_subscriptions"][body.id] = {
            "tenant_id": body.tenant_id,
            "subscription_id": body.subscription_id,
            "billing_cycle": body.billing_cycle,
        }
        return {"id": body.id}

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
        state["counts"] = {}
        state["organizations"].clear()
        state["faults"].clear()
        state["calls"].clear()
        state["clinic_tokens"].clear()
        state["clinic_subscriptions"].clear()
        return {"reset": True}

    return app


app = create_stub_app()

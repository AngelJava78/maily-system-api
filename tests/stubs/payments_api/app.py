"""Simulation of mailySoft-pagos, shared by two features (research R8):
- `specs/010-cobro-real-suscripciones/contracts/e2e-stubs.md` (clinic subscription charges).
- `specs/010-subscription-periods/contracts/e2e-collection.md` (subscription periods), with the optional
  return address of `specs/011-payment-return-url/contracts/payments-api-integration.md`.

Self-contained: it imports nothing from `src/` and uses no relative imports (same rule as
`tests/stubs/users_api/app.py` and `tests/stubs/clinics_api/app.py`). State lives in memory and is
lost with the process. Every fault body carries the marker `SECRETO-INTERNO` so the tests can check
that the details of another service never reach the clients of this API.

It imitates the two operations both features consume (`POST /api/v1/payments` and
`GET /api/v1/payments/{id}`) and offers a test-only surface under `/__test__/`. A token registered
with `/__test__/tokens` (clinic subscription charges, research R1) is checked for the permission the
operation needs; a token that was never registered is treated as authenticated with no restriction
(subscription periods never register one — they only need a bearer token to be present).
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

MARKER = "SECRETO-INTERNO"

STATUSES = ("pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded")
FAULT_MODES = (
    "unavailable",
    "unauthorized",
    "unauthorized_unreadable",
    "unauthorized_unknown",
    "forbidden",
    "organization_required",
    "not_found",
    "malformed",
    "not_json",
    "redirect",
    "slow",
    "unknown_status",
    "no_checkout",
    "return_not_allowed",
)
FAULT_OPERATIONS = ("create", "get", "any")

RESOURCE_TYPE = re.compile(r"^[a-z0-9-]+:[a-z0-9_-]+$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
# The return addresses of a payment (spec 011): `success` is required, the other two are optional.
REDIRECT_URL_FIELDS = ("success", "pending", "failure")
REDIRECT_URL_MAX_LENGTH = 2048


def _valid_redirect_urls(value: Any) -> bool:
    """The `redirect_urls` that Pagos accepts: an object with `success` and nothing unknown, every address
    an `https://` text of at most 2048 characters (its origin list is not simulated: a test uses the fault
    `return_not_allowed` for that refusal)."""

    def valid_address(address: Any) -> bool:
        return (
            isinstance(address, str)
            and address.lower().startswith("https://")  # the scheme is not case-sensitive
            and len(address) <= REDIRECT_URL_MAX_LENGTH
        )

    return (
        isinstance(value, dict)
        and set(value) <= set(REDIRECT_URL_FIELDS)
        and valid_address(value.get("success"))
        and all(value.get(name) is None or valid_address(value[name]) for name in ("pending", "failure"))
    )


class TokenIn(BaseModel):
    token: str
    permissions: list[str] = Field(default_factory=list)
    expired: bool = False


class FaultIn(BaseModel):
    mode: str
    count: int = 1
    delay_seconds: float = 30
    operation: str = "any"


class StatusIn(BaseModel):
    status: str
    amount: int | None = None
    currency: str | None = None
    # ISO 8601 with a zone; by default «now». Lets a test say when the payment was approved.
    updated_at: str | None = None
    # Spec 014: Mercado Pago's own vocabulary, forwarded verbatim (never translated by this stub).
    payment_method_id: str | None = None
    payment_type_id: str | None = None


class ForeignPaymentIn(BaseModel):
    """A payment that someone created in the payments API by another route (not through the service)."""

    resource_id: str
    status: str = "approved"
    amount: int = 49900
    currency: str = "MXN"
    resource_type: str = "system-api:subscription"
    description: str | None = None


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
                    "method": scope["method"],
                    "path": scope["path"],
                    "has_authorization": "authorization" in headers,
                    "authorization": headers.get("authorization"),
                    "idempotency_key": headers.get("idempotency-key"),
                    "header_names": sorted(headers),
                }
            )
        await self.app(scope, receive, send)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_stub_app() -> FastAPI:
    app = FastAPI(title="mailySoft-pagos (stub)")
    state: dict[str, Any] = {"tokens": {}, "faults": [], "calls": [], "payments": {}, "keys": {}}
    app.add_middleware(_RecordCalls, state=state)

    def take_fault(operation: str) -> dict[str, Any] | None:
        for fault in state["faults"]:
            if fault["remaining"] > 0 and fault["operation"] in (operation, "any"):
                fault["remaining"] -= 1
                return fault
        return None

    def error(status: int, code: str) -> JSONResponse:
        return JSONResponse({"code": code, "message": f"{MARKER} detalle interno"}, status_code=status)

    def authorize(request: Request, permission: str) -> JSONResponse | dict[str, Any]:
        """A registered token is checked for `permission`; an unregistered one is just authenticated
        (subscription periods never register one, research R1 only applies to clinic charges)."""
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return error(401, "unauthenticated")
        entry = state["tokens"].get(token.strip())
        if entry is None:
            return {}
        if entry["expired"]:
            return error(401, "token_expired")
        if permission not in entry["permissions"]:
            return error(403, "permission_denied")
        return entry

    def read(payment: dict[str, Any], mode: str | None = None) -> dict[str, Any]:
        """The `PaymentRead` of the real API; `mode` changes it to reproduce a faulty answer."""
        status = payment["status"]
        checkout = f"https://pagos.test/checkout/{payment['id']}" if status == "pending" else None
        body = {
            "id": payment["id"],
            "status": status,
            "provider": "mercado_pago",
            "amount": payment["amount"],
            "currency": payment["currency"],
            "resource_type": payment["resource_type"],
            "resource_id": payment["resource_id"],
            "description": payment.get("description"),
            "metadata": payment.get("metadata"),
            "refunded_amount": 0,
            "checkout_url": checkout,
            "payment_method_id": payment.get("payment_method_id"),
            "payment_type_id": payment.get("payment_type_id"),
            "idempotency_key": payment["idempotency_key"],
            "created_at": payment["created_at"],
            "updated_at": payment["updated_at"],
        }
        if mode == "unknown_status":
            body["status"] = "mystery"
        elif mode == "no_checkout":
            body["checkout_url"] = None
        return body

    async def early_answer(fault: dict[str, Any] | None):
        """The response of a fault that replaces the normal answer, or `None` to go on."""
        if fault is None:
            return None
        mode = fault["mode"]
        if mode == "unavailable":
            return error(503, "payment_provider_unavailable")
        if mode == "unauthorized":
            return error(401, "unauthenticated")
        if mode == "unauthorized_unreadable":
            return PlainTextResponse(MARKER, status_code=401)
        if mode == "unauthorized_unknown":
            return error(401, "something_else")
        if mode == "forbidden":
            return error(403, "permission_denied")
        if mode == "organization_required":
            return error(403, "organization_required")
        if mode == "not_found":
            return error(404, "payment_not_found")
        if mode == "malformed":
            return JSONResponse({"detail": MARKER})
        if mode == "not_json":
            return PlainTextResponse(MARKER, status_code=200)
        if mode == "redirect":
            return RedirectResponse("http://evil.test/steal", status_code=307)
        if mode == "return_not_allowed":
            # What Pagos answers when the origin of the return address is not in its allowed list.
            return JSONResponse(
                {
                    "code": "validation_error",
                    "message": f"{MARKER} detalle interno",
                    "errors": [
                        {
                            "field": "body.redirect_urls.success",
                            "message": "El origen de la dirección de regreso no está permitido.",
                        }
                    ],
                },
                status_code=422,
            )
        if mode == "slow":
            await asyncio.sleep(fault["delay_seconds"])
        return None

    @app.post("/api/v1/payments")
    async def create_payment(request: Request):
        fault = take_fault("create")
        answer = await early_answer(fault)
        if answer is not None:
            return answer
        entry = authorize(request, "payments:write")
        if isinstance(entry, JSONResponse):
            return entry

        try:
            body = await request.json()
        except ValueError:
            return error(422, "validation_error")
        valid = (
            isinstance(body, dict)
            and body.get("provider") == "mercado_pago"
            and type(body.get("amount")) is int
            and body["amount"] > 0
            and isinstance(body.get("currency"), str)
            and CURRENCY.fullmatch(body["currency"]) is not None
            and isinstance(body.get("resource_type"), str)
            and RESOURCE_TYPE.fullmatch(body["resource_type"]) is not None
            and isinstance(body.get("resource_id"), str)
            and 1 <= len(body["resource_id"]) <= 200
            and (body.get("description") is None or len(str(body["description"])) <= 500)
            and (body.get("metadata") is None or isinstance(body["metadata"], dict))
            and (body.get("redirect_urls") is None or _valid_redirect_urls(body["redirect_urls"]))
        )
        if not valid:
            return error(422, "validation_error")

        key = request.headers.get("idempotency-key") or f"generated-{uuid.uuid4()}"
        fingerprint = json.dumps(body, sort_keys=True)
        known = state["keys"].get(key)
        mode = fault["mode"] if fault is not None else None
        if known is not None:
            if known["fingerprint"] != fingerprint:
                return error(409, "idempotency_key_conflict")
            return JSONResponse(read(state["payments"][known["id"]], mode), status_code=201)

        payment = {
            "id": str(uuid.uuid4()),
            "status": "pending",
            "amount": body["amount"],
            "currency": body["currency"],
            "resource_type": body["resource_type"],
            "resource_id": body["resource_id"],
            "description": body.get("description"),
            "metadata": body.get("metadata"),
            "idempotency_key": key,
            "created_at": _now(),
            "updated_at": _now(),
        }
        if "redirect_urls" in body:
            # Kept only when the body carried the key, so a test tells «absent» from «null» (spec 011).
            payment["redirect_urls"] = body["redirect_urls"]
        state["payments"][payment["id"]] = payment
        state["keys"][key] = {"fingerprint": fingerprint, "id": payment["id"]}
        return JSONResponse(read(payment, mode), status_code=201)

    @app.get("/api/v1/payments/{payment_id}")
    async def get_payment(payment_id: str, request: Request):
        fault = take_fault("get")
        answer = await early_answer(fault)
        if answer is not None:
            return answer
        entry = authorize(request, "payments:read")
        if isinstance(entry, JSONResponse):
            return entry
        payment = state["payments"].get(payment_id)
        if payment is None:
            return error(404, "payment_not_found")
        return read(payment, fault["mode"] if fault is not None else None)

    # --- test-only surface ---

    @app.post("/__test__/tokens")
    async def register_token(body: TokenIn):
        state["tokens"][body.token] = {"permissions": set(body.permissions), "expired": body.expired}
        return {"token": "registered", "permissions": sorted(body.permissions)}

    @app.post("/__test__/payments/{payment_id}/status")
    async def set_status(payment_id: str, body: StatusIn):
        payment = state["payments"].get(payment_id)
        if payment is None:
            return JSONResponse({"detail": f"unknown payment {payment_id!r}"}, status_code=404)
        if body.status not in STATUSES:
            return JSONResponse({"detail": f"unknown status {body.status!r}"}, status_code=422)
        payment["status"] = body.status
        if body.amount is not None:
            payment["amount"] = body.amount
        if body.currency is not None:
            payment["currency"] = body.currency
        if body.payment_method_id is not None:
            payment["payment_method_id"] = body.payment_method_id
        if body.payment_type_id is not None:
            payment["payment_type_id"] = body.payment_type_id
        payment["updated_at"] = body.updated_at or _now()
        return read(payment)

    @app.post("/__test__/payments")
    async def create_foreign_payment(body: ForeignPaymentIn):
        if body.status not in STATUSES:
            return JSONResponse({"detail": f"unknown status {body.status!r}"}, status_code=422)
        identifier = str(uuid.uuid4())
        payment = {
            "id": identifier,
            "status": body.status,
            "amount": body.amount,
            "currency": body.currency,
            "resource_type": body.resource_type,
            "resource_id": body.resource_id,
            "description": body.description,
            "metadata": None,
            "idempotency_key": f"foreign-{identifier}",
            "created_at": _now(),
            "updated_at": _now(),
        }
        state["payments"][identifier] = payment
        return read(payment)

    @app.get("/__test__/payments")
    async def list_payments():
        # The `PaymentRead` of each payment plus, only for the tests, the return addresses it was created
        # with: Pagos never answers them, but a test checks what this service sent (spec 011).
        return [
            {**read(payment), **({"redirect_urls": payment["redirect_urls"]} if "redirect_urls" in payment else {})}
            for payment in state["payments"].values()
        ]

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
        state["payments"].clear()
        state["keys"].clear()
        state["faults"].clear()
        state["calls"].clear()
        return {"reset": True}

    return app


app = create_stub_app()

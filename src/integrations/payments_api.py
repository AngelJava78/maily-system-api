"""Client of the payments API (mailySoft-pagos): creates a payment and reads its state.

Shared by two features with different needs (research R8, spec 010-subscription-periods):
- `specs/010-cobro-real-suscripciones/contracts/payments-api-integration.md`: this service never
  sends `tenant_id` in the body (Pagos' own Principle X); `create_payment` forwards the caller's
  token untouched so Pagos resolves it. Reading a `pending` charge on sync uses a service account's
  own token instead (this service never stores the caller's), via `get_payment_as_service`.
- `specs/010-subscription-periods/contracts/payments-api-integration.md`: the payments are data of
  another system — their status and checkout address are asked for on every use and never stored.
  `get_payment` forwards the caller's own token and never talks to Auth0.

Anything that is not exactly the expected answer is "unavailable" and never a guessed status; the
caller decides how to degrade. Each operation is one call with a total time limit, no redirection
and no retry.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from src.integrations.errors import (
    PaymentsApiIdempotencyConflict,
    PaymentsApiPermissionDenied,
    PaymentsApiRejectedToken,
    PaymentsApiUnavailable,
)

logger = logging.getLogger(__name__)

PAYMENTS_PATH = "/api/v1/payments"
# The only payment provider that the payments API supports today.
PAYMENT_PROVIDER = "mercado_pago"
# The statuses of the contract of the payments API; any other value is an unexpected answer.
STATUSES = frozenset(
    {"pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"}
)
_REJECTION_CODES = {"unauthenticated", "token_expired", "invalid_token"}


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    """A payment as Pagos describes it; only the fields this service consumes (research R10).

    `amount` is an integer in the minimum unit of the currency (centavos). `checkout_url` is `None`
    once the payments API has been notified about the payment. `updated_at` is aware and in UTC: it
    is the date of the last change of the payment, used as the date of its approval (FR-031).
    """

    id: UUID
    status: str
    amount: int
    currency: str
    resource_type: str
    resource_id: str
    checkout_url: str | None
    updated_at: datetime


class PaymentsApiClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        timeout_seconds: float,
        service_token: str | None = None,
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # Only `get_payment_as_service` uses this; without it configured, that sync is skipped.
        self._service_token = service_token

    async def create_payment(
        self,
        token: str,
        *,
        idempotency_key: str,
        amount: int,
        currency: str,
        resource_type: str,
        resource_id: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentRecord:
        """Create a payment (or get the one that this `idempotency_key` already created).

        `token` is the caller's own token, forwarded untouched so Pagos resolves `tenant_id` with
        its own `GET /api/v1/authorization/me` (Pagos' Principle X); it is never sent in the body.

        Raises the specific `PaymentsApiRejectedToken` (401), `PaymentsApiPermissionDenied` (403) or
        `PaymentsApiIdempotencyConflict` (409, the same key with another body — never taken for the
        old payment); any other failure or answer that is not a valid payment raises the generic
        `PaymentsApiUnavailable`.
        """
        body: dict[str, Any] = {
            "provider": PAYMENT_PROVIDER,
            "amount": amount,
            "currency": currency,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        if description is not None:
            body["description"] = description
        if metadata is not None:
            body["metadata"] = metadata

        try:
            async with asyncio.timeout(self._timeout):
                response = await self._http.post(
                    f"{self._base_url}{PAYMENTS_PATH}",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Idempotency-Key": idempotency_key,
                        "Accept": "application/json",
                    },
                )
        except (httpx.HTTPError, TimeoutError) as error:
            # Only the kind of failure is logged: never the token, the address or the body.
            logger.warning("Payments API create request failed (%s)", type(error).__name__)
            raise PaymentsApiUnavailable from None

        status = response.status_code
        if status == 401:
            raise PaymentsApiRejectedToken(self._rejection_code(response))
        if status == 403:
            raise PaymentsApiPermissionDenied
        if status == 409:
            raise PaymentsApiIdempotencyConflict
        if status not in (200, 201):
            if 400 <= status < 500:
                logger.error("Payments API answered an unexpected status %s", status)
            else:
                logger.warning("Payments API answered status %s", status)
            raise PaymentsApiUnavailable
        return self._parse(response)

    async def get_payment(self, token: str, payment_id: UUID) -> PaymentRecord:
        """The current state of a payment of the organization of the person.

        Raises `PaymentsApiUnavailable` for any failure, for a payment that is not there (404) and
        for an answer that is not about the payment that was asked for.
        """
        response = await self._get(f"{PAYMENTS_PATH}/{payment_id}", token=token)
        if response.status_code != 200:
            logger.warning("Payments API unavailable to read a payment (status %s)", response.status_code)
            raise PaymentsApiUnavailable
        record = self._parse(response)
        if record.id != payment_id:
            logger.warning("Payments API answered about another payment")
            raise PaymentsApiUnavailable
        return record

    async def get_payment_as_service(self, payment_id: UUID) -> PaymentRecord:
        """The current state of a payment, for the sync-on-read of a `pending` charge (research R8).

        Uses the service account's own token (never the caller's, which this service never stores).
        Without a service token configured, the sync is skipped: raises immediately, without calling
        Pagos, so the caller falls back to the last known local status.
        """
        if self._service_token is None:
            raise PaymentsApiUnavailable
        response = await self._get(f"{PAYMENTS_PATH}/{payment_id}", token=self._service_token)
        if response.status_code != 200:
            logger.warning("Payments API unavailable (status %s)", response.status_code)
            raise PaymentsApiUnavailable
        return self._parse(response)

    async def _get(self, path: str, *, token: str) -> httpx.Response:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._http.get(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("Payments API get request failed (%s)", type(error).__name__)
            raise PaymentsApiUnavailable from None

    @staticmethod
    def _rejection_code(response: httpx.Response) -> str:
        """The code of a 401; an unreadable body or an unknown code is an invalid token."""
        try:
            code = response.json().get("code")
        except (ValueError, AttributeError):
            return "invalid_token"
        return code if code in _REJECTION_CODES else "invalid_token"

    @staticmethod
    def _parse(response: httpx.Response) -> PaymentRecord:
        unavailable = PaymentsApiUnavailable()
        try:
            data = response.json()
        except ValueError:
            logger.warning("Payments API answered a body that is not JSON")
            raise unavailable from None
        if not isinstance(data, dict):
            logger.warning("Payments API answered an unexpected body")
            raise unavailable

        identifier = data.get("id")
        status = data.get("status")
        amount = data.get("amount")
        currency = data.get("currency")
        resource_type = data.get("resource_type")
        resource_id = data.get("resource_id")
        checkout_url = data.get("checkout_url")
        updated_at_text = data.get("updated_at")
        try:
            payment_id = UUID(identifier) if isinstance(identifier, str) else None
            updated_at = (
                datetime.fromisoformat(updated_at_text) if isinstance(updated_at_text, str) else None
            )
        except ValueError:
            payment_id = updated_at = None

        # `bool` is an `int` in Python: exclude it explicitly.
        valid = (
            payment_id is not None
            and isinstance(status, str)
            and status in STATUSES
            and type(amount) is int
            and isinstance(currency, str)
            and len(currency) == 3
            and isinstance(resource_type, str)
            and isinstance(resource_id, str)
            and (checkout_url is None or isinstance(checkout_url, str))
            and updated_at is not None
            and updated_at.utcoffset() is not None
        )
        if not valid:
            logger.warning("Payments API answered an unexpected payment")
            raise unavailable
        return PaymentRecord(
            id=payment_id,
            status=status,
            amount=amount,
            currency=currency,
            resource_type=resource_type,
            resource_id=resource_id,
            checkout_url=checkout_url,
            updated_at=updated_at.astimezone(UTC),
        )

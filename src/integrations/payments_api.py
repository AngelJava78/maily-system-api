"""Client of the payments API: creates the payment of a charge and reads its state (spec 010).

Contract: `specs/010-subscription-periods/contracts/payments-api-integration.md`. The payments are data of
another system: their status and their checkout address are asked for on every use and never stored.
This service forwards the token of the person untouched and never talks to Auth0. Anything that is not
exactly the expected answer is "unavailable" and never a guessed status; the caller decides how to
degrade. Each operation is one call with a total time limit, no redirection and no retry.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from src.integrations.errors import PaymentsApiUnavailable

logger = logging.getLogger(__name__)

PAYMENTS_PATH = "/api/v1/payments"
# The only payment provider that the payments API supports today.
PAYMENT_PROVIDER = "mercado_pago"
# The statuses of the contract of the payments API; any other value is an unexpected answer.
STATUSES = frozenset(
    {"pending", "approved", "rejected", "cancelled", "partially_refunded", "refunded"}
)


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    """The part of a payment that the subscription periods use (research R10).

    `amount` is an integer in the minimum unit of the currency (centavos). `checkout_url` is `None`
    once the payments API has been notified about the payment. `updated_at` is aware and in UTC: it is
    the date of the last change of the payment, which is used as the date of its approval (FR-031).
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
        self, http_client: httpx.AsyncClient, base_url: str, timeout_seconds: float
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

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

        Raises `PaymentsApiUnavailable` for any failure or answer that is not a valid payment; that
        includes a 409 (the same key with another body), which must never be taken for the old payment.
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
        response = await self._send(
            "POST", PAYMENTS_PATH, token, json=body, extra_headers={"Idempotency-Key": idempotency_key}
        )
        if response.status_code not in (200, 201):
            logger.warning("Payments API unavailable to create a payment (status %s)", response.status_code)
            raise PaymentsApiUnavailable
        return self._parse(response)

    async def get_payment(self, token: str, payment_id: UUID) -> PaymentRecord:
        """The current state of a payment of the organization of the person.

        Raises `PaymentsApiUnavailable` for any failure, for a payment that is not there (404) and for
        an answer that is not about the payment that was asked for.
        """
        response = await self._send("GET", f"{PAYMENTS_PATH}/{payment_id}", token)
        if response.status_code != 200:
            logger.warning("Payments API unavailable to read a payment (status %s)", response.status_code)
            raise PaymentsApiUnavailable
        record = self._parse(response)
        if record.id != payment_id:
            logger.warning("Payments API answered about another payment")
            raise PaymentsApiUnavailable
        return record

    async def _send(
        self,
        method: str,
        path: str,
        token: str,
        *,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **(extra_headers or {}),
        }
        try:
            # The time limit covers the whole call; `httpx` only limits each phase separately.
            async with asyncio.timeout(self._timeout):
                return await self._http.request(
                    method, f"{self._base_url}{path}", headers=headers, json=json
                )
        except (httpx.HTTPError, TimeoutError) as error:
            # Only the kind of failure is logged: never the token, the address or the body.
            logger.warning("Payments API request failed (%s)", type(error).__name__)
            raise PaymentsApiUnavailable from None

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

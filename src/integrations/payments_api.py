"""Client of mailySoft-pagos: creates a charge and reads its status.

Contract: `specs/006-cobro-real-suscripciones/contracts/payments-api-integration.md`. This service
never sends `tenant_id` in the body (Pagos' own Principle X): Pagos resolves it from the caller's own
token, which `create_payment` forwards untouched. `get_payment` never uses the caller's token (this
service never stores one): it uses a service account's token instead (research R8); without one
configured, the sync is skipped rather than attempted.
"""

import asyncio
import logging
from dataclasses import dataclass
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
PROVIDER = "mercado_pago"
_REJECTION_CODES = {"unauthenticated", "token_expired", "invalid_token"}


@dataclass(frozen=True, slots=True)
class PaymentView:
    """A payment as Pagos describes it; only the fields this service consumes."""

    id: UUID
    status: str
    checkout_url: str | None
    amount: int
    currency: str


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
        description: str,
    ) -> PaymentView:
        """Create a generic charge (research R2 to R4). Raises on anything that is not a 201.

        `token` is the caller's own token, forwarded untouched so Pagos resolves `tenant_id` with
        its own `GET /api/v1/authorization/me` (Pagos' Principle X); it is never sent in the body.
        """
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._http.post(
                    f"{self._base_url}{PAYMENTS_PATH}",
                    json={
                        "provider": PROVIDER,
                        "amount": amount,
                        "currency": currency,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "description": description,
                    },
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
        if status != 201:
            if 400 <= status < 500:
                logger.error("Payments API answered an unexpected status %s", status)
            else:
                logger.warning("Payments API answered status %s", status)
            raise PaymentsApiUnavailable
        return self._parse(response)

    async def get_payment(self, payment_id: UUID) -> PaymentView:
        """The current state of a payment, for the sync-on-read of a `pending` charge (research R8).

        Uses the service account's own token (never the caller's, which this service never stores).
        Without `PAGOS_API_SERVICE_TOKEN` configured, the sync is skipped: raises immediately,
        without calling Pagos, so the caller falls back to the last known local status.
        """
        if self._service_token is None:
            raise PaymentsApiUnavailable

        try:
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    f"{self._base_url}{PAYMENTS_PATH}/{payment_id}",
                    headers={
                        "Authorization": f"Bearer {self._service_token}",
                        "Accept": "application/json",
                    },
                )
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("Payments API get request failed (%s)", type(error).__name__)
            raise PaymentsApiUnavailable from None

        if response.status_code != 200:
            logger.warning("Payments API unavailable (status %s)", response.status_code)
            raise PaymentsApiUnavailable
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> PaymentView:
        try:
            data = response.json()
        except ValueError:
            raise PaymentsApiUnavailable from None
        if not isinstance(data, dict):
            raise PaymentsApiUnavailable
        payment_id, status, amount, currency = (
            data.get("id"),
            data.get("status"),
            data.get("amount"),
            data.get("currency"),
        )
        checkout_url = data.get("checkout_url")
        valid = (
            isinstance(payment_id, str)
            and isinstance(status, str)
            and type(amount) is int
            and isinstance(currency, str)
            and (checkout_url is None or isinstance(checkout_url, str))
        )
        if not valid:
            raise PaymentsApiUnavailable
        try:
            parsed_id = UUID(payment_id)
        except ValueError:
            raise PaymentsApiUnavailable from None
        return PaymentView(
            id=parsed_id, status=status, checkout_url=checkout_url, amount=amount, currency=currency
        )

    @staticmethod
    def _rejection_code(response: httpx.Response) -> str:
        """The code of a 401; an unreadable body or an unknown code is an invalid token."""
        try:
            code = response.json().get("code")
        except (ValueError, AttributeError):
            return "invalid_token"
        return code if code in _REJECTION_CODES else "invalid_token"

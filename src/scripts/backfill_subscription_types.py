"""One-off deploy step (FR-009, FR-010; spec 006): not a migration, not an HTTP route.

Marks `enterprise` every pre-existing subscription that already has more than one clinic; every
subscription already has some type (`individual` by default) from the `0005` migration's column
default, so this step may run any time after `0005`, independently of the API's own start-up.

The clinics API has no service credential (research R4): this script needs a bearer token of a
person with whatever permission it already requires to read counts
(`BACKFILL_ACCESS_TOKEN`, or `--token`). It retries forever on failure (FR-010): it never completes
by guessing a type from an answer it could not confirm.

    uv run python -m src.scripts.backfill_subscription_types --token ...
"""

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

import httpx

from src.config import get_integration_settings
from src.database import get_session_factory
from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.errors import ClinicsApiUnavailable
from src.integrations.users_api import UsersApiClient
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

_INITIAL_DELAY_SECONDS = 2.0
_MAX_DELAY_SECONDS = 60.0

Sleep = Callable[[float], Awaitable[None]]


async def reconcile_with_retry(
    service: SubscriptionService, token: str, *, sleep: Sleep = asyncio.sleep
) -> int:
    """`service.reconcile_types_from_clinic_counts`, retried forever on `ClinicsApiUnavailable`.

    Growing delay, capped at `_MAX_DELAY_SECONDS`; `sleep` is injectable so tests never wait for
    real time. Never returns from a failed answer: only a successful one ends the loop.
    """
    delay = _INITIAL_DELAY_SECONDS
    while True:
        try:
            return await service.reconcile_types_from_clinic_counts(token)
        except ClinicsApiUnavailable:
            logger.warning("Clinics API unavailable; retrying in %.0fs", delay)
            await sleep(delay)
            delay = min(delay * 2, _MAX_DELAY_SECONDS)


def _token_from_args(token: str | None) -> str:
    resolved = token or os.environ.get("BACKFILL_ACCESS_TOKEN")
    if not resolved:
        raise SystemExit("Missing token: pass --token or set BACKFILL_ACCESS_TOKEN")
    return resolved


async def main(token: str) -> None:
    settings = get_integration_settings()
    async with httpx.AsyncClient() as http_client:
        clinics_api = ClinicsApiClient(
            http_client, settings.clinics_api_base_url, settings.clinics_api_timeout_seconds
        )
        users_api = UsersApiClient(
            http_client, settings.users_api_base_url, settings.users_api_timeout_seconds
        )
        async with get_session_factory()() as session:
            service = SubscriptionService(SubscriptionRepository(session), clinics_api, users_api)
            marked = await reconcile_with_retry(service, token)

    logger.info("Marked %d subscription(s) as enterprise", marked)


def _parse_token() -> str:
    """Resolves `--token`/`BACKFILL_ACCESS_TOKEN` outside of `asyncio.run` (`SystemExit` from
    inside a running coroutine can otherwise take a while to actually end the process)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", default=None, help="Access token (or set BACKFILL_ACCESS_TOKEN)")
    return _token_from_args(parser.parse_args().token)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(_parse_token()))

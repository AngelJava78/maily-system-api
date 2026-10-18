"""Composition root: builds the clients, Repository and Services of each request.

Every provider is `async def` so FastAPI does not run it in a thread. The Router only receives the
Service; the Service receives its Repositories and API clients; the Repository receives the
session.
"""

from typing import Annotated

import httpx
from fastapi import Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_integration_settings
from src.database import get_session
from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.users_api import UsersApiClient
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.authorization_service import AuthorizationService
from src.services.subscription_service import SubscriptionService


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """The HTTP client shared by the whole application (created and closed by `lifespan`)."""
    return request.app.state.http_client


async def get_users_api_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> UsersApiClient:
    settings = get_integration_settings()
    return UsersApiClient(
        client, settings.users_api_base_url, settings.users_api_timeout_seconds
    )


async def get_authorization_service(
    users_api: Annotated[UsersApiClient, Depends(get_users_api_client)],
) -> AuthorizationService:
    return AuthorizationService(users_api)


async def get_clinics_api_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> ClinicsApiClient:
    settings = get_integration_settings()
    return ClinicsApiClient(
        client, settings.clinics_api_base_url, settings.clinics_api_timeout_seconds
    )


async def get_subscription_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubscriptionRepository:
    return SubscriptionRepository(session)


async def get_subscription_service(
    repository: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    clinics_api: Annotated[ClinicsApiClient, Depends(get_clinics_api_client)],
) -> SubscriptionService:
    return SubscriptionService(repository, clinics_api)

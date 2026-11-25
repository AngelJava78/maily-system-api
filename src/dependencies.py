"""Composition root: builds the clients, Repository and Services of each request.

Every provider is `async def` so FastAPI does not run it in a thread. The Router only receives the
Service; the Service receives its Repositories and API clients; the Repository receives the
session. The dashboard has no Repository: its Service receives the data source (`build_dashboard_source`
is the only place that says which one, today the fictitious one of phase 1).

The health feature (spec 005) shares one aggregation among the requests of the process, so what the
aggregation uses cannot belong to one request: `read_enabled_components` and `ping_database` open
their own session, and the state, the clock and the HTTP client of the checks belong to the process.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated

import httpx
from fastapi import Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import (
    BuildInfo,
    HealthConfig,
    build_info_from,
    get_billing_settings,
    get_build_settings,
    get_dashboard_settings,
    get_health_settings,
    get_integration_settings,
    get_payments_settings,
    health_config_from,
)
from src.database import get_session, get_session_factory
from src.integrations.clinics_api import ClinicsApiClient
from src.integrations.dashboard_source import DashboardSource
from src.integrations.dummy_dashboard_source import DummyDashboardSource
from src.integrations.health_probe import HealthProbeClient
from src.integrations.payments_api import PaymentsApiClient
from src.integrations.users_api import UsersApiClient
from src.models.monitored_component import MonitoredComponent
from src.repositories.clinic_subscription_charge_repository import (
    ClinicSubscriptionChargeRepository,
)
from src.repositories.database_health_repository import DatabaseHealthRepository
from src.repositories.monitored_component_repository import MonitoredComponentRepository
from src.repositories.subscription_period_repository import SubscriptionPeriodRepository
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.authorization_service import AuthorizationService
from src.services.clinic_subscription_service import ClinicSubscriptionService
from src.services.clock import Clock, SystemClock
from src.services.dashboard_service import DashboardService
from src.services.health_service import HealthService
from src.services.health_state import HealthState
from src.services.monitored_component_service import MonitoredComponentService
from src.services.subscription_period_service import SubscriptionPeriodService
from src.services.subscription_service import SubscriptionService

RegistryReader = Callable[[], Awaitable[Sequence[MonitoredComponent]]]
DatabasePinger = Callable[[], Awaitable[None]]


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


async def get_payments_api_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> PaymentsApiClient:
    """Client of `mailySoft-pagos` used by the subscription periods (spec 010-subscription-periods):
    forwards the caller's own token on every call, never a service account's."""
    settings = get_payments_settings()
    return PaymentsApiClient(
        client, settings.payments_api_base_url, settings.payments_api_timeout_seconds
    )


async def get_clinic_payments_api_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> PaymentsApiClient:
    """Client of `mailySoft-pagos` used by the clinic subscription charges
    (spec 010-cobro-real-suscripciones): adds the service account's token (research R8), used only
    to sync a `pending` charge on read, never to create one."""
    settings = get_integration_settings()
    return PaymentsApiClient(
        client,
        settings.pagos_api_base_url,
        settings.pagos_api_timeout_seconds,
        settings.pagos_api_service_token,
    )


async def get_clinic_subscription_charge_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClinicSubscriptionChargeRepository:
    return ClinicSubscriptionChargeRepository(session)


async def get_subscription_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubscriptionRepository:
    return SubscriptionRepository(session)


async def get_subscription_service(
    repository: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    clinics_api: Annotated[ClinicsApiClient, Depends(get_clinics_api_client)],
    users_api: Annotated[UsersApiClient, Depends(get_users_api_client)],
) -> SubscriptionService:
    return SubscriptionService(repository, clinics_api, users_api)


async def get_clinic_subscription_service(
    repository: Annotated[
        ClinicSubscriptionChargeRepository, Depends(get_clinic_subscription_charge_repository)
    ],
    subscription_repository: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    clinics_api: Annotated[ClinicsApiClient, Depends(get_clinics_api_client)],
    payments_api: Annotated[PaymentsApiClient, Depends(get_clinic_payments_api_client)],
) -> ClinicSubscriptionService:
    return ClinicSubscriptionService(repository, subscription_repository, clinics_api, payments_api)


# Immutable and stateless, so one instance serves the whole application.
_DASHBOARD_SOURCE = DummyDashboardSource()


def build_dashboard_source() -> DashboardSource:
    """The data source of the dashboard. Phase 1: the fictitious one (`is_dummy` is true)."""
    return _DASHBOARD_SOURCE


async def get_dashboard_source() -> DashboardSource:
    return build_dashboard_source()


async def get_dashboard_service(
    source: Annotated[DashboardSource, Depends(get_dashboard_source)],
) -> DashboardService:
    return DashboardService(source, get_dashboard_settings().dashboard_recent_clinics_limit)


# --- Health of the services (spec 005) ---

# The real clock; stateless, so one instance serves the whole application.
_SYSTEM_CLOCK = SystemClock()


async def get_health_config() -> HealthConfig:
    """Time limits, cache, allowed hosts and schedule, read once (the tests replace them)."""
    return health_config_from(get_health_settings())


async def get_build_info() -> BuildInfo:
    return build_info_from(get_build_settings())


async def get_clock() -> Clock:
    return _SYSTEM_CLOCK


async def get_health_state(request: Request) -> HealthState:
    """The memory of the health feature of this application (created by `create_app`)."""
    return request.app.state.health


async def get_health_http_client(request: Request) -> httpx.AsyncClient:
    """The client of the health checks (created and closed by `lifespan`): never the shared one."""
    return request.app.state.health_http_client


async def read_enabled_components() -> Sequence[MonitoredComponent]:
    """The current and enabled components, read with a session of its own."""
    async with get_session_factory()() as session:
        return await MonitoredComponentRepository(session).list_enabled()


async def ping_database() -> None:
    """The trivial query of the health check, with a session of its own."""
    async with get_session_factory()() as session:
        await DatabaseHealthRepository(session).ping()


async def get_registry_reader() -> RegistryReader:
    return read_enabled_components


async def get_database_pinger() -> DatabasePinger:
    return ping_database


async def get_health_probe(
    client: Annotated[httpx.AsyncClient, Depends(get_health_http_client)],
    config: Annotated[HealthConfig, Depends(get_health_config)],
) -> HealthProbeClient:
    return HealthProbeClient(client, config.check_timeout_seconds)


async def get_health_service(
    state: Annotated[HealthState, Depends(get_health_state)],
    config: Annotated[HealthConfig, Depends(get_health_config)],
    build: Annotated[BuildInfo, Depends(get_build_info)],
    clock: Annotated[Clock, Depends(get_clock)],
    probe: Annotated[HealthProbeClient, Depends(get_health_probe)],
    read_registry: Annotated[RegistryReader, Depends(get_registry_reader)],
    ping: Annotated[DatabasePinger, Depends(get_database_pinger)],
) -> HealthService:
    return HealthService(
        state=state,
        config=config,
        build=build,
        clock=clock,
        probe=probe,
        read_registry=read_registry,
        ping_database=ping,
    )


async def get_monitored_component_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MonitoredComponentRepository:
    return MonitoredComponentRepository(session)


async def get_monitored_component_service(
    repository: Annotated[
        MonitoredComponentRepository, Depends(get_monitored_component_repository)
    ],
    state: Annotated[HealthState, Depends(get_health_state)],
    config: Annotated[HealthConfig, Depends(get_health_config)],
) -> MonitoredComponentService:
    """The registry: a change invalidates the cached result of the health of this application."""
    return MonitoredComponentService(repository, state, config)


# --- Subscription periods (spec 010) ---


async def get_subscription_period_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubscriptionPeriodRepository:
    return SubscriptionPeriodRepository(session)


async def get_subscription_period_service(
    periods: Annotated[SubscriptionPeriodRepository, Depends(get_subscription_period_repository)],
    subscriptions: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    clinics_api: Annotated[ClinicsApiClient, Depends(get_clinics_api_client)],
    payments_api: Annotated[PaymentsApiClient, Depends(get_payments_api_client)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> SubscriptionPeriodService:
    """The cutoff date (FR-039) and the return address of the payments (spec 011, FR-001) are read once at
    start-up; the clock is the one that the tests replace."""
    return SubscriptionPeriodService(
        periods,
        subscriptions,
        clinics_api,
        payments_api,
        clock,
        get_billing_settings().billing_cutoff_at,
        return_url=get_payments_settings().payments_return_url,
    )

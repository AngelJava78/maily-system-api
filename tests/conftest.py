"""Fixtures de las pruebas.

Las pruebas se ejecutan contra un PostgreSQL real (Principio V de la constitución), indicado en
TEST_DATABASE_URL. Aplican y revierten las migraciones de Alembic, por lo que la base de datos
DEBE ser exclusiva de las pruebas: su nombre tiene que terminar en `_test`.

Los imports de la aplicación y de httpx van dentro de las fixtures que los necesitan, para que
la suite de la capa de datos pueda correr aunque la aplicación aún no esté completa.
"""

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from tests.helpers import (
    CLINICS_BASE_URL,
    ROOT,
    TEST_TOKEN,
    USERS_BASE_URL,
    Api,
    Migrator,
    grant,
)


def _test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get(
        "TEST_DATABASE_URL"
    )


@pytest.fixture(scope="session", autouse=True)
def _never_reach_the_real_database() -> Iterator[None]:
    """Make DATABASE_URL point at the test database for the whole session.

    `.env` may hold the URL of a real database and the application reads it through
    `src.config.Settings`. Every test is meant to use `TEST_DATABASE_URL` only, but this
    guarantees that a test that built an engine from `DATABASE_URL` by mistake (or an Alembic call
    without an explicit URL) would hit the test database, never real data. Without a test database
    configured it points at an address that cannot connect.
    """
    from src.config import get_settings
    from src.database.session import get_engine, get_session_factory

    url = _test_database_url()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = (
        url or "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/not_configured_test"
    )
    for cached in (get_settings, get_engine, get_session_factory):
        cached.cache_clear()
    yield
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    for cached in (get_settings, get_engine, get_session_factory):
        cached.cache_clear()


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.fail(
            "Falta TEST_DATABASE_URL (variable de entorno o .env). Ejemplo: "
            "postgresql+asyncpg://postgres:postgres@localhost:5434/maily_system_test",
            pytrace=False,
        )
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(
            "Las pruebas eliminan y recrean el esquema, así que la base de datos de pruebas "
            f"debe llamarse '*_test' (recibido: '{database}'). No se ejecuta nada.",
            pytrace=False,
        )
    return url


@pytest_asyncio.fixture(scope="session")
async def engine(test_db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_db_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def migrator(test_db_url: str, engine: AsyncEngine) -> Migrator:
    return Migrator(test_db_url, engine)


@pytest_asyncio.fixture(scope="session")
async def migrated_db(migrator: Migrator) -> AsyncIterator[None]:
    """Base de datos de pruebas en `head` (estructura + estatus) durante toda la sesión."""
    await migrator.downgrade("base")
    await migrator.upgrade("head")
    yield
    await migrator.downgrade("base")


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine, migrated_db: None) -> AsyncIterator[AsyncSession]:
    """Sesión dentro de una transacción externa que se revierte al terminar la prueba.

    `commit()` y `rollback()` de la sesión operan sobre un SAVEPOINT, por lo que la prueba puede
    confirmar o fallar sin dejar rastro en la base de datos.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def committing_session(
    engine: AsyncEngine, migrated_db: None
) -> AsyncIterator[AsyncSession]:
    """Sesión sin transacción externa: cada `commit()` es real.

    Necesaria cuando la prueba depende de varias transacciones (p. ej. el trigger de `updated_at`,
    porque `CURRENT_TIMESTAMP` devuelve la hora de inicio de la transacción). Al terminar vacía
    `subscriptions`; el catálogo de estatus no se toca.
    """
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE subscriptions RESTART IDENTITY CASCADE"))


# --- Simulation of the users API (tests/stubs/users_api) ---
#
# The stub is mounted in memory with `httpx.ASGITransport`: no network and no Docker. The real
# `UsersApiClient` talks to it, so its translation of answers and failures is what gets tested.


@pytest.fixture
def users_stub_app():
    from tests.stubs.users_api.app import create_stub_app

    return create_stub_app()


@pytest_asyncio.fixture
async def users_stub(users_stub_app) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_stub_app), base_url=USERS_BASE_URL
    ) as client:
        yield client


@pytest.fixture
def users_api_client(users_stub: httpx.AsyncClient):
    from src.integrations.users_api import UsersApiClient

    return UsersApiClient(users_stub, USERS_BASE_URL, 5.0)


# --- Simulation of the clinics API (tests/stubs/clinics_api) ---


@pytest.fixture
def clinics_stub_app():
    from tests.stubs.clinics_api.app import create_stub_app

    return create_stub_app()


@pytest_asyncio.fixture
async def clinics_stub(clinics_stub_app) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=clinics_stub_app), base_url=CLINICS_BASE_URL
    ) as client:
        yield client


@pytest.fixture
def clinics_api_client(clinics_stub: httpx.AsyncClient):
    from src.integrations.clinics_api import ClinicsApiClient

    return ClinicsApiClient(clinics_stub, CLINICS_BASE_URL, 5.0)


# --- Simulation of the monitored components (tests/stubs/components, spec 005) ---


@pytest.fixture
def components_stub_app():
    from tests.stubs.components.app import create_stub_app

    return create_stub_app()


@pytest_asyncio.fixture
async def components_stub(components_stub_app) -> AsyncIterator[httpx.AsyncClient]:
    """A client of the simulation for its `/__test__/` surface."""
    from tests.health_support import COMPONENTS_HOST

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=components_stub_app), base_url=f"http://{COMPONENTS_HOST}"
    ) as client:
        yield client


# --- The application under test (US1 onwards) ---


@pytest_asyncio.fixture
async def api(
    engine: AsyncEngine,
    migrated_db: None,
    users_stub: httpx.AsyncClient,
    clinics_stub: httpx.AsyncClient,
    components_stub_app,
) -> AsyncIterator[Api]:
    """The real application over HTTP, talking to the real PostgreSQL and to the two simulations.

    The clients of the other APIs are the real ones (their translation of answers and failures is
    part of what is tested); only their transport is replaced by the in-memory simulations. The
    health checks (spec 005) go to the simulation of components.
    """
    from src.database import get_session
    from src.dependencies import get_clinics_api_client, get_users_api_client
    from src.integrations.clinics_api import ClinicsApiClient
    from src.integrations.users_api import UsersApiClient
    from src.main import create_app
    from tests.health_support import (
        TEST_HEALTH_CONFIG,
        HealthConfigHolder,
        install_health_overrides,
    )

    app = create_app()
    timeouts = {"users": 5.0, "clinics": 5.0}

    async def users_client() -> UsersApiClient:
        return UsersApiClient(users_stub, USERS_BASE_URL, timeouts["users"])

    async def clinics_client() -> ClinicsApiClient:
        return ClinicsApiClient(clinics_stub, CLINICS_BASE_URL, timeouts["clinics"])

    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as new_session:
            yield new_session

    app.dependency_overrides[get_users_api_client] = users_client
    app.dependency_overrides[get_clinics_api_client] = clinics_client
    app.dependency_overrides[get_session] = session
    probe_client = install_health_overrides(
        app, components_stub_app, HealthConfigHolder(TEST_HEALTH_CONFIG)
    )

    await grant(users_stub)  # TEST_TOKEN with the four permissions
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        ) as client,
        httpx.AsyncClient(transport=transport, base_url="http://api.test") as anonymous,
        probe_client,
    ):
        yield Api(client, anonymous, users_stub, clinics_stub, engine, timeouts)

    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE subscriptions, monitored_components RESTART IDENTITY CASCADE")
        )


@pytest_asyncio.fixture
async def health_api(
    engine: AsyncEngine,
    migrated_db: None,
    users_stub: httpx.AsyncClient,
    components_stub_app,
    components_stub: httpx.AsyncClient,
) -> AsyncIterator["HealthApi"]:
    """The real application for the health tests (spec 005): real PostgreSQL, simulated users API
    and components, a `FakeClock` and a configuration that each test may change.

    `TEST_TOKEN` starts with the four `health:*` permissions.
    """
    from src.database import get_session
    from src.dependencies import get_users_api_client
    from src.integrations.users_api import UsersApiClient
    from src.main import create_app
    from tests.health_support import (
        HEALTH_PERMISSIONS,
        TEST_HEALTH_CONFIG,
        FakeClock,
        HealthApi,
        HealthConfigHolder,
        install_health_overrides,
    )

    app = create_app()

    async def users_client() -> UsersApiClient:
        return UsersApiClient(users_stub, USERS_BASE_URL, 5.0)

    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as new_session:
            yield new_session

    app.dependency_overrides[get_users_api_client] = users_client
    app.dependency_overrides[get_session] = session
    clock = FakeClock()
    holder = HealthConfigHolder(TEST_HEALTH_CONFIG)
    probe_client = install_health_overrides(app, components_stub_app, holder, clock)

    await grant(users_stub, TEST_TOKEN, HEALTH_PERMISSIONS)
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        ) as client,
        httpx.AsyncClient(transport=transport, base_url="http://api.test") as anonymous,
        probe_client,
    ):
        yield HealthApi(app, client, anonymous, users_stub, components_stub, engine, clock, holder)

    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE monitored_components"))

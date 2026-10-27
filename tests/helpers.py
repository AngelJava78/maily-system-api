"""Utilidades compartidas por las pruebas (sin fixtures: estas viven en `conftest.py`)."""

import asyncio
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

ROOT = Path(__file__).resolve().parents[1]

# Token que las pruebas de la API registran en la simulación del API de usuarios.
TEST_TOKEN = "test-token"

# Direcciones ficticias de las simulaciones (el transporte ASGI ignora el host).
USERS_BASE_URL = "http://users-api.test"
CLINICS_BASE_URL = "http://clinics-api.test"

ALL_PERMISSIONS = (
    "subscriptions:read",
    "subscriptions:write",
    "subscriptions:update",
    "subscriptions:delete",
    # Needed in the users API to validate modules on create/update (contracts/permission-matrix.md);
    # not one of this service's own permissions.
    "modules:read",
)


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


class Migrator:
    """Aplica y revierte migraciones de Alembic sin bloquear el event loop.

    `alembic/env.py` usa `asyncio.run`, así que Alembic se ejecuta en un hilo aparte. Antes de cada
    operación se cierran las conexiones del pool para que ninguna retenga bloqueos.
    """

    def __init__(self, url: str, engine: AsyncEngine) -> None:
        self._url = url
        self._engine = engine

    async def upgrade(self, revision: str = "head") -> None:
        await self._run(command.upgrade, revision)

    async def downgrade(self, revision: str = "base") -> None:
        await self._run(command.downgrade, revision)

    async def _run(self, operation: Callable[[Config, str], None], revision: str) -> None:
        await self._engine.dispose()
        await asyncio.to_thread(operation, alembic_config(self._url), revision)


async def fetch_all(engine: AsyncEngine, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    """Ejecuta una consulta de solo lectura en su propia conexión y devuelve las filas."""
    async with engine.connect() as connection:
        result = await connection.execute(text(sql), params)
        return [tuple(row) for row in result]


def assert_pg_error(
    excinfo: pytest.ExceptionInfo[DBAPIError],
    sqlstate: str,
    *,
    constraint: str | None = None,
) -> None:
    """Comprueba el error de PostgreSQL por SQLSTATE y nombre de restricción.

    Se evita comparar el texto del mensaje porque depende del idioma del servidor.
    SQLSTATE usados: 23505 único, 23514 CHECK, 23503 clave foránea, 22003 numérico fuera de rango.
    """
    original = excinfo.value.orig.__cause__
    assert original.sqlstate == sqlstate, f"SQLSTATE {original.sqlstate}: {original}"
    if constraint is not None:
        assert original.constraint_name == constraint


async def grant(
    users_stub: httpx.AsyncClient,
    token: str = TEST_TOKEN,
    permissions: Iterable[str] = ALL_PERMISSIONS,
    *,
    expired: bool = False,
) -> None:
    """Registra (o sustituye) un token y sus permisos en la simulación del API de usuarios."""
    response = await users_stub.post(
        "/__test__/tokens",
        json={"token": token, "permissions": list(permissions), "expired": expired},
    )
    assert response.status_code == 200


class Api:
    """The application under test with the two simulated APIs, ready to be called over HTTP.

    `client` sends the token of `TEST_TOKEN` (registered with the four permissions); `anonymous`
    sends none. The simulations and the database are reachable to prepare scenarios.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        anonymous: httpx.AsyncClient,
        users_stub: httpx.AsyncClient,
        clinics_stub: httpx.AsyncClient,
        engine: AsyncEngine,
        timeouts: dict[str, float],
    ) -> None:
        self.client = client
        self.anonymous = anonymous
        self.users_stub = users_stub
        self.clinics_stub = clinics_stub
        self.engine = engine
        self.timeouts = timeouts

    async def insert(self, **values: Any) -> int:
        """Insert a subscription directly in the database (see `insert_subscription`)."""
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await insert_subscription(session, **values)

    async def counts(self, counts: dict[int, int]) -> None:
        response = await self.clinics_stub.post(
            "/__test__/counts", json={str(key): value for key, value in counts.items()}
        )
        assert response.status_code == 200

    async def clinics_fault(self, mode: str, count: int = 1, delay: float = 30) -> None:
        response = await self.clinics_stub.post(
            "/__test__/faults", json={"mode": mode, "count": count, "delay_seconds": delay}
        )
        assert response.status_code == 200

    async def users_fault(
        self, mode: str, count: int = 1, delay: float = 30, operation: str = "check"
    ) -> None:
        response = await self.users_stub.post(
            "/__test__/faults",
            json={"mode": mode, "count": count, "delay_seconds": delay, "operation": operation},
        )
        assert response.status_code == 200

    async def clinics_calls(self) -> list[dict[str, Any]]:
        return (await self.clinics_stub.get("/__test__/calls")).json()

    async def users_calls(self) -> list[dict[str, Any]]:
        return (await self.users_stub.get("/__test__/calls")).json()

    async def set_permissions(self, permissions: Iterable[str]) -> None:
        await grant(self.users_stub, TEST_TOKEN, permissions)

    async def fetch_all(self, sql: str, **params: Any) -> list[tuple[Any, ...]]:
        return await fetch_all(self.engine, sql, **params)


async def insert_subscription(
    session: AsyncSession,
    *,
    name: str = "Plan",
    subscription_type_id: int = 1,
    monthly_price: str | Decimal = "100.00",
    annual_price: str | Decimal = "1000.00",
    trial_days: int = 0,
    self_service: bool = False,
    module_keys: Iterable[str] = ("patients",),
    description: str | None = None,
    other_features: Iterable[str] = (),
    consulting_rooms_limit: int = 1,
    doctors_limit: int = 1,
    assistants_limit: int = 1,
    new_patients_per_year_limit: int = 100,
    status_id: int = 1,
    created_at: datetime | None = None,
) -> int:
    """Inserta una suscripción directamente en la base de datos, confirma y devuelve su id."""
    from sqlalchemy import insert

    from src.models.subscription import Subscription

    values: dict[str, Any] = {
        "name": name,
        "description": description,
        "subscription_type_id": subscription_type_id,
        "monthly_price": Decimal(str(monthly_price)),
        "annual_price": Decimal(str(annual_price)),
        "trial_days": trial_days,
        "self_service": self_service,
        "module_keys": sorted(module_keys),
        "other_features": list(other_features),
        "consulting_rooms_limit": consulting_rooms_limit,
        "doctors_limit": doctors_limit,
        "assistants_limit": assistants_limit,
        "new_patients_per_year_limit": new_patients_per_year_limit,
        "status_id": status_id,
    }
    if created_at is not None:
        values["created_at"] = created_at
    result = await session.execute(insert(Subscription).values(**values).returning(Subscription.id))
    subscription_id = result.scalar_one()
    await session.commit()
    return subscription_id

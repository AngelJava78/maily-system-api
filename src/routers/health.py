"""Health of the services (spec 005): the contract v1 in the root and the aggregated health.

- `public_router`: `/health/live`, `/health/ready` and `/info` (the contract v1) and `/health/status`
  (the public status), without a token (the exception of Principle VIII that the spec defines). They
  depend on nothing that reads `Authorization`, so a token that arrives is ignored; `/health/live`
  depends on nothing at all.
- `router`: `GET /api/v1/health`, declared with `protected(...)`, which makes it require the
  permission that the users API grants before the Service is asked for anything.

The Router only calls the Service it receives and serializes the answer with DTOs: it knows no
integration, Repository or ORM type (Principle I).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from src.dependencies import get_health_service
from src.dtos.health import (
    CheckRead,
    HealthRead,
    InfoRead,
    LiveRead,
    PublicComponentRead,
    PublicStatusRead,
    ReadyRead,
)
from src.routers.openapi_docs import protected
from src.security import HEALTH_READ
from src.services.health_service import HealthService

HEALTH_TAG = "Salud"
HEALTH_PATH = "/api/v1/health"

public_router = APIRouter(tags=[HEALTH_TAG])
router = APIRouter(tags=[HEALTH_TAG])

HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]

NO_STORE = {
    "Cache-Control": {
        "description": "La respuesta no debe guardarse en caché.",
        "schema": {"type": "string"},
        "example": "no-store",
    }
}

HEALTH_EXAMPLE = {
    "status": "down",
    "checked_at": "2026-10-24T17:40:03Z",
    "registry_available": True,
    "components": [
        {
            "code": "maily-system-api",
            "name": "MailySoft System API",
            "kind": "service",
            "status": "up",
            "latency_ms": 4,
            "checked_at": "2026-10-24T17:40:00Z",
            "version": "2.0.0",
            "commit": "3c81089d2f6a4b7e9a0c1d2e3f4a5b6c7d8e9f01",
            "build_date": "2026-10-24T16:05:00Z",
            "environment": "staging",
            "checks": [{"name": "database", "status": "ok", "latency_ms": 4, "error": None}],
            "error": None,
            "next_start_at": None,
        },
        {
            "code": "database",
            "name": "Base de datos",
            "kind": "database",
            "status": "up",
            "latency_ms": 4,
            "checked_at": "2026-10-24T17:40:00Z",
            "version": "unknown",
            "commit": "unknown",
            "build_date": "unknown",
            "environment": "unknown",
            "checks": [],
            "error": None,
            "next_start_at": None,
        },
        {
            "code": "mailysoft-pacientes",
            "name": "MailySoft Pacientes",
            "kind": "service",
            "status": "down",
            "latency_ms": 3001,
            "checked_at": "2026-10-24T17:40:03Z",
            "version": "unknown",
            "commit": "unknown",
            "build_date": "unknown",
            "environment": "unknown",
            "checks": [],
            "error": "timeout",
            "next_start_at": None,
        },
    ],
}

HEALTH_RESPONSE = {
    "description": "Salud de la plataforma.",
    "headers": NO_STORE,
    "content": {"application/json": {"examples": {"con_un_caido": {"value": HEALTH_EXAMPLE}}}},
}

# --- The contract v1 of this service (public) ---

LIVE_DESCRIPTION = """\
Responde 200 mientras el proceso atienda HTTP, sin consultar ninguna dependencia (ni la base de datos
ni otros APIs). Sirve como *liveness* y como *startup probe*.

Ruta pública: no exige token.
"""

READY_DESCRIPTION = """\
Comprueba **solo** la base de datos con una consulta trivial, con un tiempo máximo de
`HEALTH_READY_TIMEOUT_SECONDS` (2 s por defecto): responde 200 si responde y 503 si no, con el mismo
cuerpo. No consulta otros servicios ni tiene en cuenta el horario de la base de datos: mientras esté
detenida, el orquestador deja de enviarle tráfico.

Ruta pública: no exige token.
"""

INFO_DESCRIPTION = """\
Identifica el build: nombre del servicio, versión (la misma del documento OpenAPI), commit, fecha de
build y entorno. Los tres últimos salen de `APP_COMMIT_SHA`, `APP_BUILD_DATE` y `APP_ENVIRONMENT`; si
no se configuraron valen `unknown`.

Ruta pública: no exige token.
"""

READY_OK_EXAMPLE = {
    "status": "ok",
    "checks": [{"name": "database", "status": "ok", "latency_ms": 12, "error": None}],
}
READY_UNAVAILABLE_EXAMPLE = {
    "status": "unavailable",
    "checks": [{"name": "database", "status": "error", "latency_ms": 2001, "error": "timeout"}],
}


def _public_response(description: str, example: object) -> dict:
    return {
        "description": description,
        "headers": NO_STORE,
        "content": {"application/json": {"example": example}},
    }


@public_router.get(
    "/health/live",
    response_model=LiveRead,
    operation_id="get_health_live",
    summary="Comprobar que el proceso está vivo",
    description=LIVE_DESCRIPTION,
    responses={200: _public_response("El proceso está vivo.", {"status": "ok"})},
)
async def get_health_live(response: Response) -> LiveRead:
    # No dependency at all: it answers while the process attends HTTP, whatever else fails (FR-004).
    response.headers["Cache-Control"] = "no-store"
    return LiveRead(status="ok")


@public_router.get(
    "/health/ready",
    response_model=ReadyRead,
    operation_id="get_health_ready",
    summary="Comprobar que el servicio puede atender",
    description=READY_DESCRIPTION,
    responses={
        200: _public_response("La base de datos respondió.", READY_OK_EXAMPLE),
        503: {
            **_public_response(
                "La base de datos no respondió a tiempo, rechazó la conexión o falló de otra forma. "
                "No es un error de la API: es la respuesta de disponibilidad del contrato v1, con el "
                "mismo esquema que el 200.",
                READY_UNAVAILABLE_EXAMPLE,
            ),
            "model": ReadyRead,
        },
    },
)
async def get_health_ready(response: Response, service: HealthServiceDep) -> ReadyRead | JSONResponse:
    result = await service.readiness()
    body = ReadyRead(
        status="ok" if result.ok else "unavailable",
        checks=[CheckRead.model_validate(result.check, from_attributes=True)],
    )
    if not result.ok:
        return JSONResponse(
            status_code=503, content=body.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
        )
    response.headers["Cache-Control"] = "no-store"
    return body


@public_router.get(
    "/info",
    response_model=InfoRead,
    operation_id="get_info",
    summary="Consultar qué build corre",
    description=INFO_DESCRIPTION,
    responses={
        200: _public_response(
            "Identificación del build.",
            {
                "service": "maily-system-api",
                "version": "2.0.0",
                "commit": "unknown",
                "build_date": "unknown",
                "environment": "unknown",
            },
        )
    },
)
async def get_info(response: Response, service: HealthServiceDep) -> InfoRead:
    response.headers["Cache-Control"] = "no-store"
    return InfoRead.model_validate(service.info(), from_attributes=True)


# --- The public status of the platform (user story 6; not part of the contract v1) ---

STATUS_DESCRIPTION = """\
Estado mínimo de la plataforma para quien no puede comprobar su acceso (por ejemplo, el Backoffice de
noche, con la base de datos detenida por horario). Sale del **mismo resultado** y de la misma caché que
la consulta de salud, pero solo trae el estado global, cuándo se comprobó y, de cada componente, su
código, su nombre, su tipo, su estado y, si es la base de datos detenida por horario, cuándo vuelve a
encenderse. Nunca publica versiones, commits, fechas de build, entornos, direcciones, latencias,
chequeos ni códigos de error.

- Responde **siempre 200** mientras el proceso atienda HTTP, aunque la base de datos esté detenida o
  caída, el registro no pueda leerse o el API de usuarios no responda.
- No autoriza la petición: si llega una cabecera `Authorization`, se ignora (no se valida ni se
  reenvía).
- Reutiliza el último resultado mientras no hayan pasado `max(HEALTH_CACHE_SECONDS, 15)` segundos desde
  que terminó; después espera o lanza una agregación (a lo más una por proceso a la vez).
- **No es una *probe***: no debe usarse para *liveness* ni *readiness*.

Ruta pública: no exige token.
"""

STATUS_EXAMPLE = {
    "status": "degraded",
    "checked_at": "2026-10-24T03:15:00Z",
    "components": [
        {
            "code": "maily-system-api",
            "name": "MailySoft System API",
            "kind": "service",
            "status": "degraded",
            "next_start_at": None,
        },
        {
            "code": "database",
            "name": "Base de datos",
            "kind": "database",
            "status": "stopped",
            "next_start_at": "2026-10-26T14:00:00Z",
        },
        {
            "code": "mailysoft-usuarios",
            "name": "MailySoft Usuarios",
            "kind": "service",
            "status": "degraded",
            "next_start_at": None,
        },
        {"code": "mailysoft", "name": "MailySoft", "kind": "frontend", "status": "up", "next_start_at": None},
    ],
}


@public_router.get(
    "/health/status",
    response_model=PublicStatusRead,
    operation_id="get_health_status",
    summary="Consultar el estado público de la plataforma",
    description=STATUS_DESCRIPTION,
    responses={200: _public_response("Estado público de la plataforma.", STATUS_EXAMPLE)},
)
async def get_health_status(response: Response, service: HealthServiceDep) -> PublicStatusRead:
    # No security dependency: an `Authorization` header is ignored, never checked (FR-045).
    result = await service.public_status()
    response.headers["Cache-Control"] = "no-store"
    # Field by field: whatever the result of health gains never reaches this route (FR-047).
    return PublicStatusRead(
        status=result.status,
        checked_at=result.checked_at,
        components=[
            PublicComponentRead(
                code=component.code,
                name=component.name,
                kind=component.kind,
                status=component.status,
                next_start_at=component.next_start_at,
            )
            for component in result.components
        ],
    )


HEALTH_DESCRIPTION = """\
Devuelve, en una sola respuesta, el estado global y el de cada componente: primero los dos
integrados (`maily-system-api`, este servicio, y `database`, la base de datos de Azure) y después los
servicios y frontends registrados y habilitados, por `sort_order` y `code`.

- Concedido el acceso responde **siempre 200**: un componente caído se informa en su propio elemento,
  no como un error de la consulta.
- Estado global: `down` si algún componente está `down`; si no, `degraded` si alguno está `degraded`,
  `stopped` o `unknown`; si no, `ok`.
- `registry_available` es `false` si el registro no pudo leerse en esta agregación.
- El resultado se comparte entre las consultas durante `HEALTH_CACHE_SECONDS` (15 s por defecto) y
  conserva sus `checked_at`. No hay forma de saltarse la caché.
- Nunca trae direcciones, cuerpos de otros servicios ni secretos, y no se guarda en caché
  (`Cache-Control: no-store`).

Permiso requerido: `health:read`.
"""


@router.get(
    HEALTH_PATH,
    response_model=HealthRead,
    operation_id="get_health",
    summary="Consultar la salud de todos los componentes",
    description=HEALTH_DESCRIPTION,
    response_description="Salud de la plataforma.",
    **protected(HEALTH_READ, responses={200: HEALTH_RESPONSE}),
)
async def get_health(response: Response, service: HealthServiceDep) -> HealthRead:
    result = await service.health()
    response.headers["Cache-Control"] = "no-store"
    return HealthRead.model_validate(result, from_attributes=True)

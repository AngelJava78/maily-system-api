"""Dashboard API: one read-only operation under /api/v1/dashboard (spec 003).

The Router only reads the request, calls the Service it receives and serializes the answer with
DTOs: it knows no data source, Repository or ORM type (Principle I). The operation is declared with
`protected(...)`, which makes it require the permission that the users API grants.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError

from src.dependencies import get_dashboard_service
from src.dtos.dashboard import DashboardRead, RecentClinicRead
from src.routers.openapi_docs import error_response, protected
from src.security import DASHBOARD_READ, get_bearer_token
from src.services.dashboard_service import DashboardService, DashboardView

DASHBOARD_PATH = "/api/v1/dashboard"

# What `requested_limit` returns for an integer of more than 18 significant digits: all that matters
# is that it is far above the maximum, so it is only ever compared.
HUGE_LIMIT = 10**18
_DIGITS = re.compile(r"[0-9]+")  # ASCII digits only (`\d` would also accept other scripts)

router = APIRouter(prefix=DASHBOARD_PATH, tags=["dashboard"])

DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
# The token of the person: the Service hands it to the data sources (real ones forward it).
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]


def requested_limit(request: Request) -> int | None:
    """The `limit` of the query string: `None` if it was not sent, otherwise an integer of at least 1.

    It reads the raw text on purpose, instead of declaring `limit: int` (research R3): Pydantic would
    accept `5.0`, `+3` or `1_0`, would reject an integer of thousands of digits (which the spec says
    must give the maximum) and keeps only the last of a repeated parameter. Only plain ASCII digits
    are valid; a repeated, empty, decimal, signed or non-numeric value, or a zero, is a 422 with the
    uniform error body. It runs after the security dependency, so the access is decided first.
    """
    values = request.query_params.getlist("limit")
    if not values:
        return None
    invalid = RequestValidationError(
        # `input` stays empty: the value that was sent is never repeated in the answer.
        [{"type": "int_parsing", "loc": ("query", "limit"), "msg": "invalid limit", "input": None}]
    )
    if len(values) > 1 or not _DIGITS.fullmatch(values[0]):
        raise invalid
    digits = values[0].lstrip("0")
    if not digits:  # it was a zero
        raise invalid
    return HUGE_LIMIT if len(digits) > 18 else int(digits)


LimitDep = Annotated[int | None, Depends(requested_limit)]


def _to_read(view: DashboardView) -> DashboardRead:
    recent = view.recent_clinics
    return DashboardRead(
        total_clinics=view.total_clinics,
        active_clinics=view.active_clinics,
        trial_clinics=view.trial_clinics,
        total_doctors=view.total_doctors,
        total_patients=view.total_patients,
        total_users=view.total_users,
        recent_clinics=None if recent is None else [RecentClinicRead.model_validate(c) for c in recent],
    )


# --- Documentation of the response (OpenAPI, in Spanish) ---

SUMMARY_EXAMPLE = {
    "total_clinics": 12,
    "active_clinics": 8,
    "trial_clinics": 3,
    "total_doctors": 37,
    "total_patients": 1284,
    "total_users": 52,
    "recent_clinics": [
        {
            "id": "5457da22-336d-49d8-8876-4d7edb5586ae",
            "name": "Clínica Santa Aurora",
            "created_at": "2026-10-15T16:20:00Z",
            "status": {"id": 2, "name": "En prueba"},
        },
        {
            "id": "7513bda5-dd0f-48a0-9053-383ac7ec2c92",
            "name": "Consultorio Del Valle",
            "created_at": "2026-10-12T09:05:00Z",
            "status": {"id": 2, "name": "En prueba"},
        },
        {
            "id": "ca8b4382-8b86-4916-b3cb-002680986de3",
            "name": "Centro Médico Horizonte",
            "created_at": "2026-10-09T18:40:00Z",
            "status": {"id": 1, "name": "Activa"},
        },
        {
            "id": "41902d77-45cb-451e-9e11-65c60e56ecf8",
            "name": "Dental Sonríe",
            "created_at": "2026-10-08T15:00:00Z",
            "status": {"id": 2, "name": "En prueba"},
        },
        {
            "id": "e042d32c-3886-4777-953c-68db1d969e0e",
            "name": "Clínica San Rafael",
            "created_at": "2026-10-08T15:00:00Z",
            "status": {"id": 1, "name": "Activa"},
        },
    ],
}

SUMMARY_RESPONSE = {
    "description": "Resumen de la plataforma.",
    "headers": {
        "Cache-Control": {
            "description": "La respuesta no debe guardarse en caché.",
            "schema": {"type": "string"},
            "example": "no-store",
        }
    },
    "content": {
        "application/json": {
            "examples": {
                "por_defecto": {
                    "summary": "Sin `limit` (valor por defecto 5)",
                    "value": SUMMARY_EXAMPLE,
                },
                "sin_clinicas": {
                    "summary": "La plataforma no tiene datos",
                    "value": {
                        "total_clinics": 0,
                        "active_clinics": 0,
                        "trial_clinics": 0,
                        "total_doctors": 0,
                        "total_patients": 0,
                        "total_users": 0,
                        "recent_clinics": [],
                    },
                },
                "fuente_de_doctores_caida": {
                    "summary": "La fuente de doctores no respondió (futuro)",
                    "value": {
                        "total_clinics": 12,
                        "active_clinics": 8,
                        "trial_clinics": 3,
                        "total_doctors": None,
                        "total_patients": 1284,
                        "total_users": 52,
                        "recent_clinics": [],
                    },
                },
            }
        }
    },
}

LIMIT_DESCRIPTION = (
    "Cantidad de clínicas recientes que se devuelven: un entero de 1 a 10 escrito solo con dígitos. "
    "Un valor mayor que 10 **no se rechaza**: se devuelven 10. Sin `limit` rige el valor por "
    "defecto del servicio. Se rechaza con 422 un valor menor que 1, que no sea un entero (texto, "
    "decimales, notación científica, signo), vacío o repetido."
)
LIMIT_PARAMETER = {
    "name": "limit",
    "in": "query",
    "required": False,
    "description": LIMIT_DESCRIPTION,
    "schema": {"type": "integer", "minimum": 1, "examples": [5]},
}

VALIDATION_ERROR = error_response(
    "`limit` no es válido (menor que 1, que no es un entero, vacío o repetido). Solo se evalúa "
    "cuando el acceso ya se concedió.",
    limit_invalido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "limit",
                "message": "El parámetro «limit» debe ser un número entero mayor o igual que 1.",
            }
        ],
    },
)

DESCRIPTION = """\
Devuelve, en una sola consulta, seis indicadores de la plataforma y las clínicas más recientes.

- `active_clinics` y `trial_clinics` no se solapan (una clínica tiene un solo estatus) y su suma no
  supera `total_clinics`, que incluye también las clínicas en otros estatus.
- `total_doctors`, `total_patients` y `total_users` cuentan toda la plataforma. Todo doctor es un
  usuario, así que `total_users` no es menor que `total_doctors`; los pacientes no son usuarios.
- `recent_clinics` va de la clínica más nueva a la más antigua (por `created_at` y, a igualdad de
  fecha, por `id` ascendente). La lista está acotada a 10 elementos y **no se pagina**.
- La cantidad la fija `limit`; sin él rige el valor por defecto del servicio
  (`DASHBOARD_RECENT_CLINICS_LIMIT`: 3, 5 o 10; 5 si no se configura).
- Cualquiera de los siete valores puede ser `null` si su fuente de datos falla (no ocurre con los
  datos ficticios de la Fase 1). Un `0` o una lista vacía significan que la fuente respondió que no
  hay datos.
- La respuesta no se guarda en caché (`Cache-Control: no-store`).

Permiso requerido: `dashboard:read`.
"""


_options = protected(DASHBOARD_READ, responses={200: SUMMARY_RESPONSE, 422: VALIDATION_ERROR})
# `limit` is read by hand (see `requested_limit`), so the endpoint does not declare it: it is added to
# the published contract here, as an integer.
_options["openapi_extra"]["parameters"] = [LIMIT_PARAMETER]


@router.get(
    "",
    response_model=DashboardRead,
    operation_id="get_dashboard",
    summary="Consultar el resumen general de la plataforma",
    description=DESCRIPTION,
    **_options,
)
async def get_dashboard(
    response: Response,
    service: DashboardServiceDep,
    token: BearerTokenDep,
    limit: LimitDep,
) -> DashboardRead:
    view = await service.get(token, limit)
    response.headers["Cache-Control"] = "no-store"
    return _to_read(view)

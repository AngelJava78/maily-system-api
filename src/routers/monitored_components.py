"""Registry of monitored components (spec 005, user story 3): five operations under
/api/v1/monitored-components.

The Router only validates the request with DTOs, calls the Service it receives and serializes the
answer with DTOs: it knows no Repository, session or ORM type (Principle I). Every operation is
declared with `protected(...)`, so the `health:*` permission is checked before the data (FR-030).
These answers are the only ones of the API that publish the address of a component (FR-023).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Response

from src.dependencies import get_monitored_component_service
from src.dtos.monitored_component import (
    MonitoredComponentCreate,
    MonitoredComponentRead,
    MonitoredComponentUpdate,
)
from src.routers.health import HEALTH_TAG
from src.routers.openapi_docs import error_response, example_response, protected
from src.security import HEALTH_DELETE, HEALTH_READ, HEALTH_UPDATE, HEALTH_WRITE
from src.services.monitored_component_service import MonitoredComponentService

MONITORED_COMPONENTS_PATH = "/api/v1/monitored-components"

router = APIRouter(prefix=MONITORED_COMPONENTS_PATH, tags=[HEALTH_TAG])

MonitoredComponentServiceDep = Annotated[
    MonitoredComponentService, Depends(get_monitored_component_service)
]
EXAMPLE_ID = "7d3c2f0e-9a1b-4c5d-8e6f-0a1b2c3d4e5f"
ComponentIdPath = Annotated[
    UUID, Path(description="Identificador del componente (UUID).", examples=[EXAMPLE_ID])
]


# --- Documentation of the responses (OpenAPI, in Spanish) ---

SERVICE_EXAMPLE = {
    "id": EXAMPLE_ID,
    "code": "mailysoft-usuarios",
    "name": "MailySoft Usuarios",
    "kind": "service",
    "base_url": "http://mailysoft-usuarios:8000",
    "live_path": "/health/live",
    "ready_path": "/health/ready",
    "info_path": "/info",
    "enabled": True,
    "sort_order": 10,
    "created_at": "2026-10-24T17:00:00Z",
    "updated_at": "2026-10-24T17:00:00Z",
}
FRONTEND_EXAMPLE = {
    "id": "0b6a4f3e-2c1d-4e5f-8a9b-c0d1e2f3a4b5",
    "code": "mailysoft",
    "name": "MailySoft",
    "kind": "frontend",
    "base_url": "https://maily360-production.up.railway.app",
    "live_path": "/healthz/",
    "ready_path": None,
    "info_path": None,
    "enabled": False,
    "sort_order": 30,
    "created_at": "2026-10-24T17:05:00Z",
    "updated_at": "2026-10-24T18:30:00Z",
}

LIST_EXAMPLE = example_response(
    "Componentes registrados.", "registro", [SERVICE_EXAMPLE, FRONTEND_EXAMPLE]
)
READ_EXAMPLE = example_response("Componente encontrado.", "servicio", SERVICE_EXAMPLE)
UPDATED_EXAMPLE = example_response(
    "Componente modificado.", "deshabilitado", {**SERVICE_EXAMPLE, "enabled": False}
)
CREATED = {
    "description": "Componente registrado.",
    "headers": {
        "Location": {
            "description": "Ruta del componente registrado.",
            "schema": {"type": "string"},
            "example": f"{MONITORED_COMPONENTS_PATH}/{EXAMPLE_ID}",
        }
    },
    "content": {"application/json": {"examples": {"registrado": {"value": SERVICE_EXAMPLE}}}},
}

INTERNAL_ERROR = error_response(
    "Fallo inesperado, por ejemplo la base de datos no disponible (sin detalles técnicos). No "
    "cambia nada.",
    inesperado={
        "code": "internal_error",
        "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde.",
    },
)
NOT_FOUND = error_response(
    "El componente no existe o está eliminado.",
    no_encontrado={
        "code": "monitored_component_not_found",
        "message": f"No se encontró el componente monitoreado con el identificador {EXAMPLE_ID}.",
    },
)
CODE_CONFLICT = error_response(
    "Otro componente no eliminado usa el código, o es `maily-system-api` o `database` "
    "(reservados para los integrados). No cambia nada.",
    codigo_repetido={
        "code": "monitored_component_code_already_exists",
        "message": "Ya existe un componente monitoreado con el código «mailysoft-usuarios».",
    },
    codigo_reservado={
        "code": "monitored_component_code_already_exists",
        "message": "Ya existe un componente monitoreado con el código «database».",
    },
)
_INVALID_ID = {
    "code": "validation_error",
    "message": "Hay datos no válidos en la solicitud.",
    "errors": [
        {"field": "component_id", "message": "El identificador del componente debe ser un UUID."}
    ],
}
ID_VALIDATION_ERROR = error_response(
    "El identificador no es un UUID.", identificador_no_valido=_INVALID_ID
)
WRITE_VALIDATION_ERROR = error_response(
    "Algún dato no es válido, se envió un campo no permitido, el host de `base_url` no está en la "
    "lista permitida o la combinación no respeta las reglas de su `kind`. No cambia nada.",
    host_no_permitido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "base_url",
                "message": (
                    "El host de la dirección base no está entre los hosts permitidos por el "
                    "servicio."
                ),
            }
        ],
    },
    frontend_con_disponibilidad={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "ready_path",
                "message": (
                    "Un componente de tipo «frontend» no lleva ruta de disponibilidad: envíela "
                    "nula o no la envíe."
                ),
            }
        ],
    },
    campo_no_permitido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "deleted_at", "message": "El campo «deleted_at» no está permitido."}],
    },
)
UPDATE_VALIDATION_ERROR = error_response(
    "El identificador no es un UUID, no se envió ningún dato, algún dato no es válido o el "
    "componente resultante no respeta las reglas de su `kind`. No cambia nada.",
    identificador_no_valido=_INVALID_ID,
    sin_datos={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "body", "message": "Hay que enviar al menos un dato para modificar."}],
    },
    frontend_con_disponibilidad={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "ready_path",
                "message": (
                    "Un componente de tipo «frontend» no lleva ruta de disponibilidad: envíela "
                    "nula o no la envíe."
                ),
            }
        ],
    },
)

CREATE_EXAMPLES = {
    "servicio": {
        "summary": "Un servicio con las rutas del contrato v1",
        "value": {
            "code": "mailysoft-usuarios",
            "name": "MailySoft Usuarios",
            "kind": "service",
            "base_url": "http://mailysoft-usuarios:8000",
            "sort_order": 10,
        },
    },
    "frontend": {
        "summary": "MailySoft (servido por Maily360)",
        "value": {
            "code": "mailysoft",
            "name": "MailySoft",
            "kind": "frontend",
            "base_url": "https://maily360-production.up.railway.app",
            "live_path": "/healthz/",
            "sort_order": 30,
        },
    },
}
UPDATE_EXAMPLES = {
    "deshabilitar": {"summary": "Dejar de consultarlo", "value": {"enabled": False}},
    "mover": {"summary": "Cambiar el orden", "value": {"sort_order": 5}},
}


# --- Operations ---


@router.get(
    "",
    response_model=list[MonitoredComponentRead],
    operation_id="list_monitored_components",
    summary="Listar los componentes registrados (sin paginar)",
    description=(
        "Devuelve todos los componentes no eliminados, habilitados y deshabilitados, como una lista "
        "sin envoltorio y **sin paginar** (catálogo acotado: máximo esperado de 50), ordenada por "
        "`sort_order` y, a igualdad, por `code`. Los dos componentes integrados no aparecen: no se "
        "registran.\n\n"
        "Permiso requerido: `health:read`."
    ),
    response_description="Componentes registrados.",
    **protected(HEALTH_READ, responses={200: LIST_EXAMPLE, 500: INTERNAL_ERROR}),
)
async def list_monitored_components(
    service: MonitoredComponentServiceDep,
) -> list[MonitoredComponentRead]:
    return [MonitoredComponentRead.model_validate(component) for component in await service.list()]


@router.post(
    "",
    status_code=201,
    response_model=MonitoredComponentRead,
    operation_id="create_monitored_component",
    summary="Registrar un componente",
    description=(
        "Registra un servicio o un frontend. El registro empieza vacío; el componente aparece en "
        "la siguiente consulta de salud sin redesplegar.\n\n"
        "- `code` es único entre los no eliminados; `maily-system-api` y `database` están "
        "reservados (409).\n"
        "- `base_url`: `http` o `https`, con host y sin usuario, contraseña, consulta ni fragmento; "
        "su host debe estar en la lista permitida del servicio (`HEALTH_ALLOWED_HOSTS`). Se guarda "
        "sin barra final.\n"
        "- Un `service` toma por defecto `/health/live`, `/health/ready` e `/info`. Un `frontend` "
        "necesita `live_path` (su ruta de salud), no lleva `ready_path` e `info_path` es "
        "opcional.\n"
        "- Se rechaza toda la solicitud si trae un campo no reconocido.\n\n"
        "Permiso requerido: `health:write`."
    ),
    response_description="Componente registrado.",
    **protected(
        HEALTH_WRITE,
        responses={
            201: CREATED,
            409: CODE_CONFLICT,
            422: WRITE_VALIDATION_ERROR,
            500: INTERNAL_ERROR,
        },
    ),
)
async def create_monitored_component(
    data: Annotated[MonitoredComponentCreate, Body(openapi_examples=CREATE_EXAMPLES)],
    response: Response,
    service: MonitoredComponentServiceDep,
) -> MonitoredComponentRead:
    component = await service.create(data)
    response.headers["Location"] = f"{MONITORED_COMPONENTS_PATH}/{component.id}"
    return MonitoredComponentRead.model_validate(component)


@router.get(
    "/{component_id}",
    response_model=MonitoredComponentRead,
    operation_id="get_monitored_component",
    summary="Consultar un componente registrado",
    description=(
        "Devuelve el componente con ese identificador. Si no existe o está eliminado responde «no "
        "se encuentra».\n\n"
        "Permiso requerido: `health:read`."
    ),
    response_description="Componente encontrado.",
    **protected(
        HEALTH_READ,
        responses={
            200: READ_EXAMPLE,
            404: NOT_FOUND,
            422: ID_VALIDATION_ERROR,
            500: INTERNAL_ERROR,
        },
    ),
)
async def get_monitored_component(
    component_id: ComponentIdPath, service: MonitoredComponentServiceDep
) -> MonitoredComponentRead:
    return MonitoredComponentRead.model_validate(await service.get(component_id))


@router.patch(
    "/{component_id}",
    response_model=MonitoredComponentRead,
    operation_id="update_monitored_component",
    summary="Modificar, habilitar o deshabilitar un componente",
    description=(
        "Cambia solo los campos enviados (al menos uno) y valida el componente resultante con las "
        "mismas reglas que un alta: por ejemplo, pasar `kind` a `frontend` exige enviar "
        "`ready_path` nula. Un cambio de `base_url` vuelve a comprobar la lista permitida. No se "
        "pueden cambiar el identificador ni las fechas. Deshabilitado, el componente sigue en el "
        "registro pero no se consulta ni aparece en la salud.\n\n"
        "Permiso requerido: `health:update`."
    ),
    response_description="Componente modificado.",
    **protected(
        HEALTH_UPDATE,
        responses={
            200: UPDATED_EXAMPLE,
            404: NOT_FOUND,
            409: CODE_CONFLICT,
            422: UPDATE_VALIDATION_ERROR,
            500: INTERNAL_ERROR,
        },
    ),
)
async def update_monitored_component(
    component_id: ComponentIdPath,
    data: Annotated[MonitoredComponentUpdate, Body(openapi_examples=UPDATE_EXAMPLES)],
    service: MonitoredComponentServiceDep,
) -> MonitoredComponentRead:
    return MonitoredComponentRead.model_validate(await service.update(component_id, data))


@router.delete(
    "/{component_id}",
    status_code=204,
    response_class=Response,
    operation_id="delete_monitored_component",
    summary="Eliminar un componente (baja lógica)",
    description=(
        "Marca el componente como eliminado: su fila se conserva, deja de aparecer en el registro y "
        "en la salud, consultarlo después responde «no se encuentra» y su `code` queda libre para "
        "un componente nuevo (con otro identificador).\n\n"
        "Permiso requerido: `health:delete`."
    ),
    response_description="Componente eliminado (sin contenido).",
    **protected(
        HEALTH_DELETE,
        responses={404: NOT_FOUND, 422: ID_VALIDATION_ERROR, 500: INTERNAL_ERROR},
    ),
)
async def delete_monitored_component(
    component_id: ComponentIdPath, service: MonitoredComponentServiceDep
) -> Response:
    await service.delete(component_id)
    return Response(status_code=204)

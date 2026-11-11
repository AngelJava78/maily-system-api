"""Clinic subscriptions API: seven operations under /api/v1/clinic-subscriptions (spec 006).

Six operations (list, get, create, cancel, list_charges, get_charge) belong to whoever administers
the platform and are protected the same way as the subscriptions catalog (`protected`,
`require_permission`, `/authorization/check`). `charge_clinic_subscription` is the exception: it
belongs to a person of the clinic itself, so it is protected with `protected_caller`/
`require_caller` (`/authorization/me`), which also hands the Service the caller's own `tenant_id`
(research R1, FR-030).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, Response

from src.dependencies import get_clinic_subscription_service
from src.dtos.clinic_subscription import (
    ClinicSubscriptionChargeRead,
    ClinicSubscriptionCreate,
    ClinicSubscriptionRead,
)
from src.routers.openapi_docs import error_response, example_response, protected, protected_caller
from src.security import (
    CLINIC_SUBSCRIPTIONS_CHARGE,
    CLINIC_SUBSCRIPTIONS_DELETE,
    CLINIC_SUBSCRIPTIONS_READ,
    CLINIC_SUBSCRIPTIONS_WRITE,
    CallerAccess,
    get_bearer_token,
    require_caller,
)
from src.services.clinic_subscription_service import ClinicSubscriptionService, ClinicSubscriptionView

CLINIC_SUBSCRIPTIONS_PATH = "/api/v1/clinic-subscriptions"

router = APIRouter(prefix=CLINIC_SUBSCRIPTIONS_PATH, tags=["clinic-subscriptions"])

ServiceDep = Annotated[ClinicSubscriptionService, Depends(get_clinic_subscription_service)]
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]
ClinicSubscriptionIdPath = Annotated[
    int, Path(gt=0, description="Identificador de la suscripción de clínica.", examples=[1])
]
ChargeIdPath = Annotated[int, Path(gt=0, description="Identificador del cobro.", examples=[1])]
PageQuery = Annotated[int, Query(ge=1, description="Página (1 es la primera).")]
LimitQuery = Annotated[int, Query(ge=1, le=100, description="Elementos por página.")]


def _to_read(view: ClinicSubscriptionView) -> ClinicSubscriptionRead:
    read = ClinicSubscriptionRead.model_validate(view.clinic_subscription)
    read.current_charge = (
        None
        if view.current_charge is None
        else ClinicSubscriptionChargeRead.model_validate(view.current_charge)
    )
    return read


# --- Documentation of the responses (OpenAPI, in Spanish) ---

NOT_FOUND = error_response(
    "La suscripción de clínica no existe o está Cancelada.",
    no_encontrada={
        "code": "clinic_subscription_not_found",
        "message": "No se encontró la suscripción de clínica con el identificador 1.",
    },
)
CHARGE_NOT_FOUND = error_response(
    "El cobro no existe en esa suscripción de clínica.",
    no_encontrado={
        "code": "clinic_subscription_charge_not_found",
        "message": "No se encontró el cobro con el identificador 1 en esa suscripción de clínica.",
    },
)
CREATE_CONFLICT = error_response(
    "El plan no existe o no está Activo, o la clínica ya tiene una suscripción vigente.",
    plan_no_activo={
        "code": "clinic_subscription_plan_not_active",
        "message": "El plan con el identificador 2 no existe o no está Activo.",
    },
    ya_activa={
        "code": "clinic_subscription_already_active",
        "message": "La clínica ya tiene una suscripción vigente. Cancélela antes de asignar una nueva.",
    },
)
CANCEL_CONFLICT = error_response(
    "Tiene un cobro pendiente de resolver, o ya está Cancelada.",
    cobro_pendiente={
        "code": "clinic_subscription_charge_pending",
        "message": "La suscripción de clínica con el identificador 1 tiene un cobro pendiente de resolver.",
    },
    ya_cancelada={
        "code": "clinic_subscription_already_cancelled",
        "message": "La suscripción de clínica con el identificador 1 ya está cancelada.",
    },
)
CHARGE_CONFLICT = error_response(
    "Está Cancelada, el plan ya no está Activo, o hay un conflicto de idempotencia.",
    cancelada={
        "code": "clinic_subscription_charge_pending",
        "message": (
            "La suscripción de clínica con el identificador 1 está cancelada y no admite un "
            "nuevo cobro."
        ),
    },
    plan_inactivo={
        "code": "clinic_subscription_charge_requires_active_plan",
        "message": (
            "El plan de esta suscripción de clínica ya no está Activo. Asígnele un plan vigente "
            "antes de cobrar."
        ),
    },
    conflicto_idempotencia={
        "code": "clinic_subscription_charge_conflict",
        "message": "Ya existe un cobro distinto para este periodo. Revise el historial antes de reintentar.",
    },
)
CHARGE_FORBIDDEN = error_response(
    "Sin el permiso, con el cambio de contraseña pendiente, o mailySoft-pagos no autorizó el cobro.",
    sin_permiso={
        "code": "permission_denied",
        "message": "No tiene permiso para realizar esta operación. Permiso requerido: clinic_subscriptions:charge.",
    },
    cambio_contrasena={
        "code": "password_change_required",
        "message": "Debe cambiar su contraseña antes de usar esta operación.",
    },
    no_autorizado={
        "code": "payment_not_authorized",
        "message": "No se pudo autorizar el cobro con el proveedor de pagos.",
    },
)
PAYMENTS_UNAVAILABLE = error_response(
    "mailySoft-pagos no respondió; no se disparó ningún cobro.",
    no_disponible={
        "code": "payments_unavailable",
        "message": "No se pudo comunicar con el servicio de pagos por ahora. Inténtelo de nuevo más tarde.",
    },
)
CREATE_EXAMPLES = {
    "mensual": {
        "summary": "Plan mensual sin prueba",
        "value": {
            "tenant_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
            "subscription_id": 2,
            "billing_cycle": "monthly",
        },
    },
}
CREATED = example_response(
    "Suscripción de clínica creada, Activa.",
    "creada",
    {
        "id": 1,
        "tenant_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
        "subscription_id": 2,
        "billing_cycle": "monthly",
        "started_at": "2026-11-10T00:00:00Z",
        "next_billing_at": "2026-11-10T00:00:00Z",
        "status": {"id": 1, "name": "Activa"},
        "current_charge": None,
        "created_at": "2026-11-10T00:00:00Z",
        "updated_at": "2026-11-10T00:00:00Z",
    },
)


# --- Operations (System role, checked with /check) ---


@router.get(
    "",
    response_model=list[ClinicSubscriptionRead],
    operation_id="list_clinic_subscriptions",
    summary="Listar las suscripciones de clínica (paginado)",
    description="**Permiso requerido: `clinic_subscriptions:read`.**",
    **protected(CLINIC_SUBSCRIPTIONS_READ),
)
async def list_clinic_subscriptions(
    service: ServiceDep,
    response: Response,
    page: PageQuery = 1,
    limit: LimitQuery = 20,
    tenant_id: UUID | None = None,
    status_id: Annotated[int | None, Query(ge=1, le=3)] = None,
) -> list[ClinicSubscriptionRead]:
    views, total = await service.list(tenant_id=tenant_id, status_id=status_id, page=page, limit=limit)
    response.headers["X-Total-Count"] = str(total)
    return [_to_read(view) for view in views]


@router.post(
    "",
    status_code=201,
    response_model=ClinicSubscriptionRead,
    operation_id="create_clinic_subscription",
    summary="Asignar un plan del catálogo a una clínica",
    description=(
        "`tenant_id` se envía explícito (FR-006): quien crea no tiene organización propia. "
        "Una clínica tiene a lo sumo una suscripción Activa o con cobro pendiente de resolver a "
        "la vez (FR-004).\n\n**Permiso requerido: `clinic_subscriptions:write`.**"
    ),
    **protected(
        CLINIC_SUBSCRIPTIONS_WRITE,
        responses={201: CREATED, 409: CREATE_CONFLICT, 500: {"description": "Fallo inesperado."}},
    ),
)
async def create_clinic_subscription(
    data: Annotated[ClinicSubscriptionCreate, Body(openapi_examples=CREATE_EXAMPLES)],
    response: Response,
    service: ServiceDep,
) -> ClinicSubscriptionRead:
    view = await service.create(data)
    response.headers["Location"] = f"{CLINIC_SUBSCRIPTIONS_PATH}/{view.clinic_subscription.id}"
    return _to_read(view)


@router.get(
    "/{clinic_subscription_id}",
    response_model=ClinicSubscriptionRead,
    operation_id="get_clinic_subscription",
    summary="Consultar una suscripción de clínica",
    description=(
        "Si su cobro vigente está `pending`, se sincroniza con Pagos antes de responder "
        "(historia 3).\n\n**Permiso requerido: `clinic_subscriptions:read`.**"
    ),
    **protected(CLINIC_SUBSCRIPTIONS_READ, responses={404: NOT_FOUND}),
)
async def get_clinic_subscription(
    clinic_subscription_id: ClinicSubscriptionIdPath, service: ServiceDep
) -> ClinicSubscriptionRead:
    return _to_read(await service.get(clinic_subscription_id))


@router.delete(
    "/{clinic_subscription_id}",
    status_code=204,
    response_class=Response,
    operation_id="cancel_clinic_subscription",
    summary="Cancelar la suscripción de una clínica (baja lógica)",
    description=(
        "Se rechaza si tiene un cobro vigente `pending`, o si ya está Cancelada "
        "(historia 5).\n\n**Permiso requerido: `clinic_subscriptions:delete`.**"
    ),
    **protected(CLINIC_SUBSCRIPTIONS_DELETE, responses={404: NOT_FOUND, 409: CANCEL_CONFLICT}),
)
async def cancel_clinic_subscription(
    clinic_subscription_id: ClinicSubscriptionIdPath, service: ServiceDep
) -> Response:
    await service.cancel(clinic_subscription_id)
    return Response(status_code=204)


@router.get(
    "/{clinic_subscription_id}/charges",
    response_model=list[ClinicSubscriptionChargeRead],
    operation_id="list_clinic_subscription_charges",
    summary="Listar el historial de cobros de una suscripción de clínica (paginado)",
    description="**Permiso requerido: `clinic_subscriptions:read`.**",
    **protected(CLINIC_SUBSCRIPTIONS_READ, responses={404: NOT_FOUND}),
)
async def list_clinic_subscription_charges(
    clinic_subscription_id: ClinicSubscriptionIdPath,
    service: ServiceDep,
    response: Response,
    page: PageQuery = 1,
    limit: LimitQuery = 20,
) -> list[ClinicSubscriptionChargeRead]:
    charges, total = await service.list_charges(clinic_subscription_id, page=page, limit=limit)
    response.headers["X-Total-Count"] = str(total)
    return [ClinicSubscriptionChargeRead.model_validate(charge) for charge in charges]


@router.get(
    "/{clinic_subscription_id}/charges/{charge_id}",
    response_model=ClinicSubscriptionChargeRead,
    operation_id="get_clinic_subscription_charge",
    summary="Consultar un cobro del historial",
    description=(
        "Si está `pending`, se sincroniza con Pagos antes de responder (igual que "
        "`get_clinic_subscription`).\n\n**Permiso requerido: `clinic_subscriptions:read`.**"
    ),
    **protected(CLINIC_SUBSCRIPTIONS_READ, responses={404: CHARGE_NOT_FOUND}),
)
async def get_clinic_subscription_charge(
    clinic_subscription_id: ClinicSubscriptionIdPath, charge_id: ChargeIdPath, service: ServiceDep
) -> ClinicSubscriptionChargeRead:
    charge = await service.get_charge(clinic_subscription_id, charge_id)
    return ClinicSubscriptionChargeRead.model_validate(charge)


# --- Operation of a Clinic role, checked with /me (require_caller, research R1) ---


@router.post(
    "/{clinic_subscription_id}/charges",
    status_code=201,
    response_model=ClinicSubscriptionChargeRead,
    operation_id="charge_clinic_subscription",
    summary="Disparar el cobro de la suscripción de una clínica",
    description=(
        "Solo una persona de la **misma organización** que la suscripción de clínica (FR-012, "
        "FR-030): se resuelve el `tenant_id` de quien llama con `GET /api/v1/authorization/me` y "
        "se compara; si no coincide (o quien llama no tiene organización), responde 404, no 403. "
        "Llama a `POST /api/v1/payments` de mailySoft-pagos reenviando ese mismo token.\n\n"
        "**Permiso requerido: `clinic_subscriptions:charge`** (de un rol de Clínica)."
    ),
    **protected_caller(
        CLINIC_SUBSCRIPTIONS_CHARGE,
        responses={
            403: CHARGE_FORBIDDEN,
            404: NOT_FOUND,
            409: CHARGE_CONFLICT,
            503: PAYMENTS_UNAVAILABLE,
        },
    ),
)
async def charge_clinic_subscription(
    clinic_subscription_id: ClinicSubscriptionIdPath,
    service: ServiceDep,
    token: BearerTokenDep,
    caller: Annotated[CallerAccess, Depends(require_caller(CLINIC_SUBSCRIPTIONS_CHARGE))],
) -> ClinicSubscriptionChargeRead:
    charge = await service.charge(clinic_subscription_id, caller, token)
    return ClinicSubscriptionChargeRead.model_validate(charge)

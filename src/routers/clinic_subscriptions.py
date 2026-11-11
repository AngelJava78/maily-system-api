"""Charges of clinic subscriptions: three operations under /api/v1/clinic-subscriptions (spec 010).

`charge_clinic_subscription` belongs to a person of the clinic itself, so it is protected with
`protected_caller`/`require_caller` (`/authorization/me`), which also hands the Service the
caller's own `tenant_id` (research R1, FR-026). The other two (list/get the history) belong to
whoever administers the platform and are protected the same way as the subscriptions catalog
(`protected`, `require_permission`, `/authorization/check`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, Response

from src.dependencies import get_clinic_subscription_service
from src.dtos.clinic_subscription import ClinicSubscriptionChargeCreate, ClinicSubscriptionChargeRead
from src.routers.openapi_docs import error_response, example_response, protected, protected_caller
from src.security import (
    CLINIC_SUBSCRIPTIONS_CHARGE,
    CLINIC_SUBSCRIPTIONS_READ,
    CallerAccess,
    get_bearer_token,
    require_caller,
)
from src.services.clinic_subscription_service import ClinicSubscriptionService

CLINIC_SUBSCRIPTIONS_PATH = "/api/v1/clinic-subscriptions"

router = APIRouter(prefix=CLINIC_SUBSCRIPTIONS_PATH, tags=["clinic-subscriptions"])

ServiceDep = Annotated[ClinicSubscriptionService, Depends(get_clinic_subscription_service)]
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]
ClinicSubscriptionIdPath = Annotated[
    UUID,
    Path(description="Identificador (opaco) de la suscripción de clínica, propiedad de Clínicas."),
]
ChargeIdPath = Annotated[int, Path(gt=0, description="Identificador del cobro.", examples=[1])]
PageQuery = Annotated[int, Query(ge=1, description="Página (1 es la primera).")]
LimitQuery = Annotated[int, Query(ge=1, le=100, description="Elementos por página.")]


# --- Documentation of the responses (OpenAPI, in Spanish) ---

NOT_FOUND = error_response(
    "Clínicas no reconoce ese identificador, está cancelada, o es de otra organización que la de "
    "quien llama.",
    no_encontrada={
        "code": "clinic_subscription_not_found",
        "message": "No se encontró la suscripción de clínica con el identificador "
        "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f.",
    },
)
CHARGE_NOT_FOUND = error_response(
    "El cobro no existe.",
    no_encontrado={
        "code": "clinic_subscription_charge_not_found",
        "message": "No se encontró el cobro con el identificador 1.",
    },
)
CHARGE_CONFLICT = error_response(
    "El plan ya no está Activo, ya hay un cobro aprobado para este periodo, o hay un conflicto de "
    "idempotencia.",
    plan_inactivo={
        "code": "clinic_subscription_plan_not_active",
        "message": "El plan de esta suscripción de clínica no existe o no está Activo.",
    },
    ya_aprobado={
        "code": "clinic_subscription_charge_already_approved",
        "message": "Ya existe un cobro aprobado para este periodo.",
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
DEPENDENCY_UNAVAILABLE = error_response(
    "Clínicas o mailySoft-pagos no respondieron; no se disparó ningún cobro.",
    clinicas={
        "code": "clinics_check_unavailable",
        "message": "No se pudo comprobar la suscripción de clínica por ahora. No se disparó "
        "ningún cobro; inténtelo de nuevo más tarde.",
    },
    pagos={
        "code": "payments_unavailable",
        "message": "No se pudo comunicar con el servicio de pagos por ahora. Inténtelo de nuevo más tarde.",
    },
)
CHARGE_EXAMPLES = {"periodo": {"summary": "Cobro de diciembre", "value": {"period": "2026-12-01"}}}
CHARGED = example_response(
    "Cobro disparado (o el ya existente del mismo periodo, por idempotencia).",
    "creado",
    {
        "id": 1,
        "clinic_subscription_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
        "tenant_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
        "period": "2026-12-01",
        "amount": 129900,
        "currency": "MXN",
        "payment_id": "6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70",
        "payment_status": "pending",
        "checkout_url": "https://pagos.test/checkout/6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70",
        "created_at": "2026-11-11T00:00:00Z",
        "updated_at": "2026-11-11T00:00:00Z",
    },
)


# --- Operation of a Clinic role, checked with /me (require_caller, research R1) ---


@router.post(
    "/{clinic_subscription_id}/charges",
    status_code=201,
    response_model=ClinicSubscriptionChargeRead,
    operation_id="charge_clinic_subscription",
    summary="Disparar el cobro de la suscripción de una clínica",
    description=(
        "Consulta a Clínicas los datos de `clinic_subscription_id` (`tenant_id`, "
        "`subscription_id`, `billing_cycle`); solo una persona de la **misma organización** "
        "(FR-009, FR-026): si no coincide (o Clínicas dice que no existe), responde 404, no 403. "
        "Llama a `POST /api/v1/payments` de mailySoft-pagos reenviando ese mismo token.\n\n"
        "**Permiso requerido: `clinic_subscriptions:charge`** (de un rol de Clínica)."
    ),
    **protected_caller(
        CLINIC_SUBSCRIPTIONS_CHARGE,
        responses={
            201: CHARGED,
            403: CHARGE_FORBIDDEN,
            404: NOT_FOUND,
            409: CHARGE_CONFLICT,
            503: DEPENDENCY_UNAVAILABLE,
        },
    ),
)
async def charge_clinic_subscription(
    clinic_subscription_id: ClinicSubscriptionIdPath,
    data: Annotated[ClinicSubscriptionChargeCreate, Body(openapi_examples=CHARGE_EXAMPLES)],
    service: ServiceDep,
    token: BearerTokenDep,
    caller: Annotated[CallerAccess, Depends(require_caller(CLINIC_SUBSCRIPTIONS_CHARGE))],
) -> ClinicSubscriptionChargeRead:
    charge = await service.charge(clinic_subscription_id, data.period, caller, token)
    return ClinicSubscriptionChargeRead.model_validate(charge)


# --- Operations (System role, checked with /check) ---


@router.get(
    "/{clinic_subscription_id}/charges",
    response_model=list[ClinicSubscriptionChargeRead],
    operation_id="list_clinic_subscription_charges",
    summary="Listar el historial de cobros de una suscripción de clínica (paginado)",
    description="**Permiso requerido: `clinic_subscriptions:read`.**",
    **protected(CLINIC_SUBSCRIPTIONS_READ),
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
        "Si está `pending`, se sincroniza con Pagos antes de responder (historia 2).\n\n"
        "**Permiso requerido: `clinic_subscriptions:read`.**"
    ),
    **protected(CLINIC_SUBSCRIPTIONS_READ, responses={404: CHARGE_NOT_FOUND}),
)
async def get_clinic_subscription_charge(
    clinic_subscription_id: ClinicSubscriptionIdPath, charge_id: ChargeIdPath, service: ServiceDep
) -> ClinicSubscriptionChargeRead:
    charge = await service.get_charge(clinic_subscription_id, charge_id)
    return ClinicSubscriptionChargeRead.model_validate(charge)

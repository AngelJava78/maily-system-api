"""Subscription periods API: two operations under /api/v1/subscription-periods (spec 010).

The Router only reads the request, calls the Service it receives and serializes the answer with DTOs:
it knows no other API, Repository or ORM type (Principle I). Both operations are declared with
`protected(...)`, which makes them require the permission that the users API grants; the Service then
checks, with the clinics API, that the person is the owner of the organization.
"""

import math
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from src.dependencies import get_subscription_period_service
from src.dtos.subscription_period import (
    ChargeStatusName,
    PlanRead,
    SubscriptionChargeRead,
    SubscriptionChargesPageRead,
    SubscriptionPaymentRead,
    SubscriptionPeriodRead,
)
from src.routers.openapi_docs import AUTHORIZATION_UNAVAILABLE, error_response, protected
from src.security import SUBSCRIPTION_PERIODS_READ, SUBSCRIPTION_PERIODS_WRITE, get_bearer_token
from src.services.subscription_period_service import (
    PaymentStart,
    PeriodView,
    SubscriptionPeriodService,
)

SUBSCRIPTION_PERIODS_PATH = "/api/v1/subscription-periods"

router = APIRouter(prefix=SUBSCRIPTION_PERIODS_PATH, tags=["subscription-periods"])

ServiceDep = Annotated[SubscriptionPeriodService, Depends(get_subscription_period_service)]
# The token of the person: the Service hands it to the clinics API and to the payments API.
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]
OrganizationIdPath = Annotated[
    UUID,
    Path(
        description=(
            "Identificador de la organización (el `organization_id` de «mis clínicas» de Clínicas)."
        ),
        examples=["0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b"],
    ),
]
ORGANIZATION_EXAMPLE_ID = "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b"
DEFAULT_PAGE_SIZE = 10
PageQuery = Annotated[int, Query(ge=1, description="Página (1 es la primera).")]
PageSizeQuery = Annotated[
    int, Query(ge=1, le=100, description="Cuántos cobros como máximo trae una página.")
]
StatusQuery = Annotated[
    ChargeStatusName | None,
    Query(description="Si se da, solo trae los cobros con ese estado (`pending`/`applied`/`closed`)."),
]


def _to_period_read(view: PeriodView) -> SubscriptionPeriodRead:
    return SubscriptionPeriodRead(
        state=view.state,  # type: ignore[arg-type]
        trial_ends_at=view.trial_ends_at,
        payment_due_at=view.payment_due_at,
        days_remaining=view.days_remaining,
        subscription=PlanRead(id=view.plan_id, name=view.plan_name),
        billing_period=view.billing_period,  # type: ignore[arg-type]
        amount=view.amount,
        currency="MXN",
        payment_in_progress=view.payment_in_progress,
    )


def _to_payment_read(start: PaymentStart) -> SubscriptionPaymentRead:
    return SubscriptionPaymentRead(
        checkout_url=start.checkout_url,
        amount=start.amount,
        currency="MXN",
        billing_period=start.billing_period,  # type: ignore[arg-type]
    )


def _to_charge_read(charge: Any) -> SubscriptionChargeRead:
    return SubscriptionChargeRead(
        id=charge.id,
        status=charge.status,  # type: ignore[arg-type]
        closed_reason=charge.closed_reason,  # type: ignore[arg-type]
        amount=charge.amount,
        currency="MXN",
        billing_period=charge.billing_period,  # type: ignore[arg-type]
        plan=charge.plan,
        concept=charge.concept,
        payment_method=charge.payment_method,  # type: ignore[arg-type]
        period_starts_at=charge.period_starts_at,
        period_ends_at=charge.period_ends_at,
        created_at=charge.created_at,
    )


def _to_charges_page_read(
    charges: list[Any], total: int, page: int, page_size: int
) -> SubscriptionChargesPageRead:
    return SubscriptionChargesPageRead(
        items=[_to_charge_read(charge) for charge in charges],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


# --- Documentation of the responses (OpenAPI, in Spanish) ---

_CACHE_CONTROL_HEADER = {
    "Cache-Control": {
        "description": "La respuesta no debe guardarse en caché.",
        "schema": {"type": "string"},
        "example": "no-store",
    }
}


def _period_example(**changes: object) -> dict[str, object]:
    return {
        "state": "trial",
        "trial_ends_at": "2026-12-04T15:30:00Z",
        "payment_due_at": "2026-12-04T15:30:00Z",
        "days_remaining": 9,
        "subscription": {"id": 3, "name": "Plan Individual"},
        "billing_period": "monthly",
        "amount": "499.00",
        "currency": "MXN",
        "payment_in_progress": False,
        **changes,
    }


PERIOD_RESPONSE = {
    "description": "El estado del periodo de la organización.",
    "headers": _CACHE_CONTROL_HEADER,
    "content": {
        "application/json": {
            "examples": {
                "en_prueba": {
                    "summary": "En prueba (14 días, mensual de 499.00)",
                    "value": _period_example(),
                },
                "vencida": {
                    "summary": "Vencida hace cinco días",
                    "value": _period_example(state="overdue", days_remaining=-5),
                },
                "sin_cobro": {
                    "summary": "Plan sin cobro (importe 0.00)",
                    "value": _period_example(
                        state="no_charge",
                        trial_ends_at=None,
                        payment_due_at=None,
                        days_remaining=None,
                        subscription={"id": 1, "name": "Plan Gratuito"},
                        amount="0.00",
                    ),
                },
                "pagos_no_responde": {
                    "summary": "Pagos no respondió: no se pudo verificar un cobro en curso",
                    "value": _period_example(
                        state="current",
                        payment_due_at="2027-01-04T15:30:00Z",
                        days_remaining=31,
                        payment_in_progress=None,
                    ),
                },
            }
        }
    },
}

CHARGE_EXAMPLE = {
    "id": "6b1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e70",
    "status": "applied",
    "closed_reason": None,
    "amount": "499.00",
    "currency": "MXN",
    "billing_period": "monthly",
    "plan": "Plan Individual",
    "concept": "Suscripción Plan Individual — mensual",
    "payment_method": "card",
    "period_starts_at": "2026-10-19T12:00:00Z",
    "period_ends_at": "2026-11-19T12:00:00Z",
    "created_at": "2026-10-19T11:58:03Z",
}
CHARGES_RESPONSE = {
    "model": SubscriptionChargesPageRead,
    "description": "Una página del historial de cobros de la organización, el más reciente primero.",
    "headers": _CACHE_CONTROL_HEADER,
    "content": {
        "application/json": {
            "examples": {
                "con_cobros": {
                    "summary": "Una página con un cobro aplicado",
                    "value": {
                        "items": [CHARGE_EXAMPLE],
                        "total": 1,
                        "page": 1,
                        "page_size": 10,
                        "total_pages": 1,
                    },
                },
                "sin_cobros": {
                    "summary": "Una organización sin ningún cobro",
                    "value": {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0},
                },
            }
        }
    },
}

PAYMENT_START_EXAMPLE = {
    "checkout_url": "https://www.mercadopago.com.mx/checkout/v1/redirect?pref_id=123456789-abc",
    "amount": "499.00",
    "currency": "MXN",
    "billing_period": "monthly",
}
PAYMENT_CREATED_RESPONSE = {
    "model": SubscriptionPaymentRead,
    "description": "Se creó un cobro nuevo: la dirección del checkout al que llevar a la persona.",
    "headers": _CACHE_CONTROL_HEADER,
    "content": {"application/json": {"examples": {"nuevo": {"value": PAYMENT_START_EXAMPLE}}}},
}
PAYMENT_EXISTING_RESPONSE = {
    "model": SubscriptionPaymentRead,
    "description": "Ya había un cobro pendiente para este periodo: se devuelve su checkout.",
    "headers": _CACHE_CONTROL_HEADER,
    "content": {"application/json": {"examples": {"pendiente": {"value": PAYMENT_START_EXAMPLE}}}},
}

ORGANIZATION_NOT_FOUND = error_response(
    "La organización no existe o no es de la persona: no se distingue, para no revelar si existe.",
    no_encontrada={
        "code": "organization_not_found",
        "message": f"No se encontró la organización con el identificador {ORGANIZATION_EXAMPLE_ID}.",
    },
)
PLAN_NOT_IN_CATALOG = error_response(
    "El plan que informa Clínicas para la organización no existe en el catálogo de suscripciones.",
    sin_plan={
        "code": "organization_subscription_not_found",
        "message": "El plan de la organización no existe en el catálogo de suscripciones.",
    },
)
NOTHING_TO_CHARGE_OR_PLAN = error_response(
    "No hay nada que cobrar (importe 0.00) o el plan de la organización no existe en el catálogo.",
    sin_cobro={
        "code": "nothing_to_charge",
        "message": "La suscripción de la organización no tiene nada que cobrar: su importe vigente es 0.00.",
    },
    sin_plan={
        "code": "organization_subscription_not_found",
        "message": "El plan de la organización no existe en el catálogo de suscripciones.",
    },
)
INTERNAL_ERROR = error_response(
    "Fallo inesperado (sin detalles técnicos).",
    inesperado={
        "code": "internal_error",
        "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde.",
    },
)
INVALID_ORGANIZATION_ID = error_response(
    "El identificador de la organización no es un UUID. Solo se evalúa con el acceso concedido.",
    formato_invalido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "organization_id",
                "message": "El identificador de la organización debe ser un UUID.",
            }
        ],
    },
)
UNAVAILABLE = error_response(
    "No se pudo verificar el permiso (Usuarios) o la organización (Clínicas): no se hizo ni se cambió "
    "nada.",
    permiso=dict(
        AUTHORIZATION_UNAVAILABLE["content"]["application/json"]["examples"]["no_disponible"]["value"]
    ),
    organizacion={
        "code": "organization_check_unavailable",
        "message": (
            "No se pudo comprobar la organización por ahora. No se hizo ningún cambio; inténtelo de "
            "nuevo más tarde."
        ),
    },
)
UNAVAILABLE_TO_PAY = error_response(
    "Usuarios o Clínicas no respondieron, o Pagos no pudo crear el pago: no se registró ningún cobro "
    "nuevo.",
    permiso=dict(
        AUTHORIZATION_UNAVAILABLE["content"]["application/json"]["examples"]["no_disponible"]["value"]
    ),
    organizacion={
        "code": "organization_check_unavailable",
        "message": (
            "No se pudo comprobar la organización por ahora. No se hizo ningún cambio; inténtelo de "
            "nuevo más tarde."
        ),
    },
    pagos={
        "code": "payments_unavailable",
        "message": (
            "No se pudo crear el pago por ahora. No se registró ningún cobro nuevo; inténtelo de "
            "nuevo más tarde."
        ),
    },
)

GET_DESCRIPTION = """\
Devuelve en qué punto está la organización: si está en prueba (`trial`), al corriente (`current`),
vencida (`overdue`) o sin cobro (`no_charge`), cuándo termina la prueba, la fecha del siguiente pago,
los días que faltan (o de atraso), su plan, su periodo de cobro, el importe a pagar y si hay un cobro
en curso.

- La primera vez que se consulta una organización se crea su registro (una sola vez, también con
  consultas simultáneas). El primer periodo empieza en el alta de la organización, pero nunca antes de
  la fecha de corte del servicio; la prueba dura los `trial_days` de su plan **en ese momento** y su
  fin no cambia después, aunque cambie el plan.
- `days_remaining` es un entero con signo, redondeado hacia arriba, relativo a `payment_due_at`:
  positivo, faltan; `0` o negativo, ya venció (`-5` son cinco días completos de atraso). Con `trial` y
  `current` vale 1 o más; con `overdue`, 0 o menos; con `no_charge`, `null`.
- Antes de responder, la API revisa en Pagos los cobros que ella inició y siguen sin resolverse y aplica
  los aprobados: cada uno mueve `payment_due_at` exactamente una vez. Si Pagos no responde, devuelve lo
  guardado y `payment_in_progress` en `null`.
- Sin periodo de gracia: es `overdue` desde que el reloj alcanza `payment_due_at`.
- Las fechas van en UTC (ISO 8601 con `Z`); mostrarlas en la zona horaria de la clínica le toca a la
  aplicación. La respuesta no se guarda en caché (`Cache-Control: no-store`).
- La persona debe ser el Dueño de la organización: se comprueba leyéndola en Clínicas con su token (404
  si no lo es o no existe; 503 si Clínicas no responde).

Permiso requerido: `subscription_periods:read`.
"""

POST_DESCRIPTION = """\
Crea el cobro en Pagos —con la referencia `system-api:subscription` y el identificador de la
organización— y devuelve la dirección del checkout a la que la aplicación lleva a la persona.

- **No recibe importe**: lo calcula la API con el precio del catálogo del plan vigente de la organización
  y su periodo de cobro. Cualquier cuerpo, importe, moneda o periodo que traiga la petición se ignora.
- Se puede pagar durante la prueba, antes de la fecha del siguiente pago o ya vencida. Cuando el pago se
  apruebe, el periodo pagado empieza donde terminaría el anterior (si llegó a tiempo) o en la fecha de
  aprobación (si ya estaba vencida).
- **Idempotente por periodo**: iniciar el pago otra vez para el mismo periodo no crea un segundo cobro y
  devuelve el mismo checkout mientras siga pendiente (200). Si el cobro anterior del periodo se cerró sin
  pagarse, se crea uno nuevo (201). Si el importe vigente cambió (cambio de plan), también se crea uno
  nuevo; el anterior sigue siendo válido si se paga.
- Antes de crear nada revisa los cobros pendientes: si alguno ya fue aprobado se aplica primero.
- Si el importe vigente es 0.00, responde 409 `nothing_to_charge` sin llamar a Pagos. Si Pagos no
  responde, 503 `payments_unavailable` sin registrar ningún cobro.
- La respuesta no se guarda en caché (`Cache-Control: no-store`).

Permiso requerido: `subscription_periods:write`.
"""

GET_CHARGES_DESCRIPTION = """\
Devuelve el historial de cobros de la organización: pagados (`applied`), pendientes (`pending`) y
cerrados sin pagarse (`closed`, con su `closed_reason`), del más reciente al más antiguo.

- `period_starts_at`/`period_ends_at` solo están presentes cuando `status` es `applied` (el periodo que
  ese pago cubrió); `closed_reason` solo cuando `status` es `closed`. En cualquier otro caso valen `null`.
- `plan` (spec 013) es el nombre del plan vigente cuando se generó el cobro, como una foto: un cambio
  posterior de nombre del plan no lo reescribe. `null` en los cobros creados antes de este campo.
- `status` (parámetro opcional, spec 013) filtra el listado del lado del servidor; `total`/`total_pages`
  reflejan el total ya filtrado, no el de toda la organización.
- `concept` (spec 014) es el concepto amigable del cobro, como una foto; `null` en los cobros creados
  antes de este campo.
- `payment_method` (spec 014) es `card`, `oxxo` o `transfer`, solo cuando el cobro se resolvió y Pagos
  reportó un método reconocido; `null` mientras sigue `pending`, si Pagos no lo reportó, o en los cobros
  resueltos antes de este campo.
- No incluye el identificador del pago en Pagos ni los datos internos de la reconciliación: solo lo que
  la persona necesita ver.
- Esta lectura no sincroniza nada con Pagos (a diferencia de consultar el periodo): un cobro `pending`
  puede seguir mostrándose así aunque ya esté decidido; la siguiente consulta del periodo lo resuelve.
- La persona debe ser el Dueño de la organización (mismo control que consultar el periodo). La
  paginación va en el cuerpo de la respuesta, no en un encabezado.
- La respuesta no se guarda en caché (`Cache-Control: no-store`).

Permiso requerido: `subscription_periods:read`.
"""


@router.get(
    "/{organization_id}",
    response_model=SubscriptionPeriodRead,
    operation_id="get_subscription_period",
    summary="Consultar el periodo de prueba y el siguiente pago de una organización",
    description=GET_DESCRIPTION,
    **protected(
        SUBSCRIPTION_PERIODS_READ,
        responses={
            200: PERIOD_RESPONSE,
            404: ORGANIZATION_NOT_FOUND,
            409: PLAN_NOT_IN_CATALOG,
            422: INVALID_ORGANIZATION_ID,
            500: INTERNAL_ERROR,
            503: UNAVAILABLE,
        },
    ),
)
async def get_subscription_period(
    organization_id: OrganizationIdPath,
    response: Response,
    service: ServiceDep,
    token: BearerTokenDep,
) -> SubscriptionPeriodRead:
    view = await service.get_status(token, organization_id)
    response.headers["Cache-Control"] = "no-store"
    return _to_period_read(view)


@router.post(
    "/{organization_id}/payments",
    response_model=SubscriptionPaymentRead,
    status_code=201,
    operation_id="create_subscription_payment",
    summary="Iniciar el pago del siguiente periodo de una organización",
    description=POST_DESCRIPTION,
    **protected(
        SUBSCRIPTION_PERIODS_WRITE,
        responses={
            200: PAYMENT_EXISTING_RESPONSE,
            201: PAYMENT_CREATED_RESPONSE,
            404: ORGANIZATION_NOT_FOUND,
            409: NOTHING_TO_CHARGE_OR_PLAN,
            422: INVALID_ORGANIZATION_ID,
            500: INTERNAL_ERROR,
            503: UNAVAILABLE_TO_PAY,
        },
    ),
)
async def create_subscription_payment(
    organization_id: OrganizationIdPath,
    response: Response,
    service: ServiceDep,
    token: BearerTokenDep,
) -> SubscriptionPaymentRead:
    start = await service.start_payment(token, organization_id)
    response.status_code = 201 if start.created else 200
    response.headers["Cache-Control"] = "no-store"
    return _to_payment_read(start)


@router.get(
    "/{organization_id}/charges",
    response_model=SubscriptionChargesPageRead,
    operation_id="list_subscription_charges",
    summary="Consultar el historial de cobros de una organización (paginado)",
    description=GET_CHARGES_DESCRIPTION,
    **protected(
        SUBSCRIPTION_PERIODS_READ,
        responses={
            200: CHARGES_RESPONSE,
            404: ORGANIZATION_NOT_FOUND,
            422: INVALID_ORGANIZATION_ID,
            500: INTERNAL_ERROR,
            503: UNAVAILABLE,
        },
    ),
)
async def list_subscription_charges(
    organization_id: OrganizationIdPath,
    response: Response,
    service: ServiceDep,
    token: BearerTokenDep,
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
    status: StatusQuery = None,
) -> SubscriptionChargesPageRead:
    charges, total = await service.list_charges(
        token, organization_id, page=page, page_size=page_size, status=status
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_charges_page_read(charges, total, page, page_size)

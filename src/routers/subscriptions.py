"""Subscriptions API: six operations under /api/v1/subscriptions.

The Router only validates the request with DTOs, calls the Service it receives and serialises the
answer with DTOs: it knows no Repository, session or ORM type (Principle I). Every operation is
declared with `protected(...)`, which makes it require the permission that the users API grants.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response

from src.dependencies import get_subscription_service
from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.routers.openapi_docs import error_response, example_response, protected
from src.security import (
    SUBSCRIPTIONS_DELETE,
    SUBSCRIPTIONS_READ,
    SUBSCRIPTIONS_UPDATE,
    SUBSCRIPTIONS_WRITE,
    get_bearer_token,
)
from src.services.subscription_service import SubscriptionService, SubscriptionView

SUBSCRIPTIONS_PATH = "/api/v1/subscriptions"

router = APIRouter(prefix=SUBSCRIPTIONS_PATH, tags=["subscriptions"])

SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]
# The token of the person: the Service forwards it to the clinics API (it is the same dependency the
# security check uses, so FastAPI resolves it once per request).
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]
SubscriptionIdPath = Annotated[
    int, Path(gt=0, description="Identificador de la suscripción (entero positivo).", examples=[1])
]


def _to_read(view: SubscriptionView) -> SubscriptionRead:
    read = SubscriptionRead.model_validate(view.subscription)
    read.clinics_count = view.clinics_count
    return read


# --- Documentation of the responses (OpenAPI, in Spanish) ---

INTERNAL_ERROR = error_response(
    "Fallo inesperado (sin detalles técnicos).",
    inesperado={
        "code": "internal_error",
        "message": "Ocurrió un error inesperado. Inténtelo de nuevo más tarde.",
    },
)

LIST_EXAMPLE = example_response(
    "Lista de suscripciones vigentes.",
    "catalogo",
    [
        {
            "id": 2,
            "name": "Profesional",
            "description": "Para consultorios con varios doctores que llevan expediente y recetas.",
            "subscription_type": {"id": 2, "name": "Empresarial"},
            "monthly_price": "1299.00",
            "annual_price": "12990.00",
            "trial_days": 14,
            "self_service": True,
            "module_keys": [
                "clinical_record_templates",
                "clinical_records",
                "patients",
                "prescriptions",
                "reminders",
                "scheduling",
            ],
            "other_features": ["Soporte por correo y WhatsApp", "Capacitación inicial en línea"],
            "consulting_rooms_limit": 2,
            "doctors_limit": 3,
            "assistants_limit": 2,
            "new_patients_per_year_limit": 15000,
            "status": {"id": 1, "name": "Activa"},
            "clinics_count": 0,
            "created_at": "2026-10-23T15:00:00Z",
            "updated_at": "2026-10-23T15:00:00Z",
        },
        {
            "id": 5,
            "name": "Solo",
            "description": "Para el médico que trabaja por su cuenta.",
            "subscription_type": {"id": 1, "name": "Individual"},
            "monthly_price": "900.00",
            "annual_price": "9000.00",
            "trial_days": 0,
            "self_service": False,
            "module_keys": ["patients", "scheduling"],
            "other_features": [],
            "consulting_rooms_limit": 1,
            "doctors_limit": 1,
            "assistants_limit": 0,
            "new_patients_per_year_limit": 5000,
            "status": {"id": 2, "name": "Inactiva"},
            "clinics_count": None,
            "created_at": "2026-10-17T15:05:00Z",
            "updated_at": "2026-10-17T16:10:00Z",
        },
    ],
)

WRITE_CONFLICT = error_response(
    "Ya existe una suscripción no eliminada con ese nombre, o se pidió un módulo sin su "
    "prerrequisito.",
    nombre_repetido={
        "code": "subscription_name_already_exists",
        "message": "Ya existe una suscripción con el nombre «Pro».",
    },
    prerrequisito_faltante={
        "code": "subscription_module_prerequisite_missing",
        "message": "El módulo «billing» exige el módulo «finance», que no está incluido.",
    },
)
VALIDATION_ERROR = error_response(
    "Algún dato de la solicitud no es válido (o se envió un campo no permitido).",
    nombre_obligatorio={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "name", "message": "El nombre de la suscripción es obligatorio."}],
    },
    campo_no_permitido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "status", "message": "El campo «status» no está permitido."}],
    },
)
WRITE_VALIDATION_ERROR = error_response(
    "Algún dato no es válido, se envió un campo no permitido, o un módulo no es reconocido por la "
    "API de usuarios.",
    nombre_obligatorio={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "name", "message": "El nombre de la suscripción es obligatorio."}],
    },
    campo_no_permitido={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [{"field": "status", "message": "El campo «status» no está permitido."}],
    },
    tipo_obligatorio={
        "code": "validation_error",
        "message": "Hay datos no válidos en la solicitud.",
        "errors": [
            {
                "field": "subscription_type_id",
                "message": (
                    "El tipo de suscripción es obligatorio y debe ser un número entero positivo."
                ),
            }
        ],
    },
    tipo_no_encontrado={
        "code": "subscription_type_not_found",
        "message": "No se encontró el tipo de suscripción con el identificador 99.",
    },
    modulo_no_reconocido={
        "code": "subscription_module_not_found",
        "message": (
            "La API de usuarios no reconoce el módulo «facturacion» como un módulo de clínica "
            "vigente."
        ),
    },
)
NOT_FOUND = error_response(
    "La suscripción no existe o está Eliminada.",
    no_encontrada={
        "code": "subscription_not_found",
        "message": "No se encontró la suscripción con el identificador 42.",
    },
)
WRITE_UNAVAILABLE = error_response(
    "No se pudo verificar el permiso (`authorization_unavailable`) o no se pudieron comprobar los "
    "módulos pedidos (`module_check_unavailable`). No cambia nada.",
    permiso={
        "code": "authorization_unavailable",
        "message": "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde.",
    },
    modulos={
        "code": "module_check_unavailable",
        "message": (
            "No se pudo comprobar los módulos de la suscripción por ahora. No se guardó ningún "
            "cambio; inténtelo de nuevo más tarde."
        ),
    },
)
CREATED = {
    "description": "Suscripción creada.",
    "headers": {
        "Location": {
            "description": "Ruta de la suscripción creada.",
            "schema": {"type": "string"},
            "example": f"{SUBSCRIPTIONS_PATH}/7",
        }
    },
    "content": {
        "application/json": {
            "examples": {
                "creada": {
                    "value": {
                        "id": 7,
                        "name": "Profesional",
                        "description": "Para clínicas en crecimiento.",
                        "subscription_type": {"id": 2, "name": "Empresarial"},
                        "monthly_price": "1299.00",
                        "annual_price": "12990.00",
                        "trial_days": 14,
                        "self_service": True,
                        "module_keys": ["patients", "scheduling"],
                        "other_features": ["Soporte por correo y WhatsApp"],
                        "consulting_rooms_limit": 2,
                        "doctors_limit": 3,
                        "assistants_limit": 2,
                        "new_patients_per_year_limit": 15000,
                        "status": {"id": 1, "name": "Activa"},
                        "clinics_count": 0,
                        "created_at": "2026-10-23T15:00:00Z",
                        "updated_at": "2026-10-23T15:00:00Z",
                    }
                }
            }
        }
    },
}
CREATE_EXAMPLES = {
    "completo": {
        "summary": "Plan «Profesional» del mockup",
        "value": {
            "name": "Profesional",
            "description": "Para consultorios con varios doctores que llevan expediente y recetas.",
            "subscription_type_id": 2,
            "monthly_price": "1299.00",
            "annual_price": "12990.00",
            "trial_days": 14,
            "self_service": True,
            "module_keys": [
                "scheduling",
                "reminders",
                "clinical_records",
                "clinical_record_templates",
                "prescriptions",
            ],
            "other_features": ["Soporte por correo y WhatsApp", "Capacitación inicial en línea"],
            "consulting_rooms_limit": 2,
            "doctors_limit": 3,
            "assistants_limit": 2,
            "new_patients_per_year_limit": 15000,
        },
    },
    "minimo": {
        "summary": "Solo los datos obligatorios (solo incluye Pacientes)",
        "value": {
            "name": "Esencial",
            "subscription_type_id": 1,
            "monthly_price": 499,
            "annual_price": 4990,
            "consulting_rooms_limit": 1,
            "doctors_limit": 1,
            "assistants_limit": 1,
            "new_patients_per_year_limit": 5000,
        },
    },
}

HAS_CLINICS = error_response(
    "La suscripción tiene clínicas asignadas.",
    con_clinicas={
        "code": "subscription_has_clinics",
        "message": (
            "No se puede eliminar la suscripción con el identificador 1 porque tiene clínicas "
            "asignadas."
        ),
    },
)
DELETE_UNAVAILABLE = error_response(
    "No se pudo verificar el permiso (`authorization_unavailable`) o no se pudo comprobar si la "
    "suscripción tiene clínicas (`clinics_check_unavailable`). No cambia nada.",
    permiso={
        "code": "authorization_unavailable",
        "message": "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde.",
    },
    clinicas={
        "code": "clinics_check_unavailable",
        "message": (
            "No se pudo comprobar si la suscripción con el identificador 1 tiene clínicas "
            "asignadas. No se eliminó; inténtelo de nuevo más tarde."
        ),
    },
)
STATUS_UNCHANGED = error_response(
    "La suscripción ya tiene ese estatus.",
    sin_cambio={
        "code": "subscription_status_unchanged",
        "message": "La suscripción con el identificador 1 ya tiene el estatus Inactiva.",
    },
)
STATUS_EXAMPLES = {"inactivar": {"summary": "Retirar de la oferta", "value": {"status_id": 2}}}
UPDATE_EXAMPLES = {
    "precio_anual": {"summary": "Cambiar solo el precio anual", "value": {"annual_price": "13990.00"}},
    "modulos": {
        "summary": "Reemplazar el conjunto de módulos",
        "value": {"module_keys": ["scheduling", "reminders"]},
    },
}


# --- Operations ---


@router.get(
    "",
    response_model=list[SubscriptionRead],
    operation_id="list_subscriptions",
    summary="Listar las suscripciones vigentes (sin paginar)",
    description=(
        "Devuelve, en una sola respuesta y sin paginación, todas las suscripciones Activas, "
        "Inactivas y Bloqueadas (y las de un estatus añadido a mano), cada una con su estatus. "
        "Las Eliminadas no aparecen. Orden: fecha de creación ascendente y, a igualdad, "
        "identificador ascendente. Sin suscripciones devuelve una lista vacía. Si el API de "
        "clínicas no responde, todas las suscripciones se devuelven con `clinics_count: null`.\n\n"
        "**Permiso requerido: `subscriptions:read`.**"
    ),
    response_description="Lista de suscripciones vigentes.",
    **protected(SUBSCRIPTIONS_READ, responses={200: LIST_EXAMPLE, 500: INTERNAL_ERROR}),
)
async def list_subscriptions(
    service: SubscriptionServiceDep, token: BearerTokenDep
) -> list[SubscriptionRead]:
    return [_to_read(view) for view in await service.list(token)]


@router.post(
    "",
    status_code=201,
    response_model=SubscriptionRead,
    operation_id="create_subscription",
    summary="Crear una suscripción",
    description=(
        "Crea una suscripción con estatus Activa. Los textos se guardan sin espacios al inicio ni "
        "al final. El nombre no puede repetirse (sin distinguir mayúsculas) entre las "
        "suscripciones no eliminadas; el de una Eliminada se puede reutilizar. Se rechaza toda la "
        "solicitud si trae un dato no reconocido (`id`, `status`, `clinics_count`, fechas…). La "
        "respuesta trae `clinics_count: 0` porque una suscripción nueva no puede tener clínicas.\n\n"
        "`subscription_type_id` es obligatorio (hoy, `1` Individual o `2` Empresarial, del "
        "catálogo `subscription_types`) y queda fijo para siempre: ninguna otra operación de "
        "esta API lo modifica. Un identificador que no exista en el catálogo se rechaza con "
        "`subscription_type_not_found`.\n\n"
        "`module_keys` siempre incluye `patients`, se envíe o no. Si pide algún módulo además de "
        "`patients`, se valida contra la API de usuarios (módulo reconocido y de tipo Clínica) y "
        "contra las dependencias de esta API (Recordatorios exige Agenda y citas; Plantillas de "
        "expediente y Recetas exigen Expediente clínico; Facturación exige Finanzas).\n\n"
        "**Permiso requerido: `subscriptions:write`.**"
    ),
    response_description="Suscripción creada.",
    **protected(
        SUBSCRIPTIONS_WRITE,
        responses={
            201: CREATED,
            409: WRITE_CONFLICT,
            422: WRITE_VALIDATION_ERROR,
            503: WRITE_UNAVAILABLE,
            500: INTERNAL_ERROR,
        },
    ),
)
async def create_subscription(
    data: Annotated[SubscriptionCreate, Body(openapi_examples=CREATE_EXAMPLES)],
    response: Response,
    service: SubscriptionServiceDep,
    token: BearerTokenDep,
) -> SubscriptionRead:
    view = await service.create(data, token)
    response.headers["Location"] = f"{SUBSCRIPTIONS_PATH}/{view.subscription.id}"
    return _to_read(view)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionRead,
    operation_id="get_subscription",
    summary="Consultar una suscripción por su identificador",
    description=(
        "Devuelve la suscripción Activa, Inactiva o Bloqueada con ese identificador. Si no existe "
        "o está Eliminada responde «no se encuentra». Si el API de clínicas no responde, "
        "`clinics_count` es `null`.\n\n"
        "**Permiso requerido: `subscriptions:read`.**"
    ),
    response_description="Suscripción encontrada.",
    **protected(
        SUBSCRIPTIONS_READ,
        responses={404: NOT_FOUND, 422: VALIDATION_ERROR, 500: INTERNAL_ERROR},
    ),
)
async def get_subscription(
    subscription_id: SubscriptionIdPath, service: SubscriptionServiceDep, token: BearerTokenDep
) -> SubscriptionRead:
    return _to_read(await service.get(subscription_id, token))


@router.patch(
    "/{subscription_id}",
    response_model=SubscriptionRead,
    operation_id="update_subscription",
    summary="Actualizar una suscripción",
    description=(
        "Modifica, enviando solo lo que cambia, el nombre, la descripción, el precio mensual, el "
        "precio anual, los días de prueba, el autoconsumo, los módulos incluidos, los cuatro "
        "límites de la clínica y/o las otras funcionalidades de una suscripción vigente. Hay que "
        "enviar al menos uno. Enviar la descripción vacía (o `null`) la borra; enviar "
        "`other_features: []` vacía esa lista. No se puede cambiar el identificador, el estatus "
        "(ver `change_subscription_status`), las fechas, `clinics_count` ni "
        "`subscription_type_id` (es fijo desde la creación: enviarlo, con cualquier valor, "
        "rechaza toda la solicitud). Una suscripción puede conservar su propio nombre (incluso "
        "cambiando solo las mayúsculas).\n\n"
        "Si la solicitud trae `module_keys`, primero se comprueba que la suscripción exista (404 "
        "si no, antes de llamar a la API de usuarios) y luego se valida igual que al crear; "
        "`patients` nunca puede excluirse, se envíe o no en la lista.\n\n"
        "**Permiso requerido: `subscriptions:update`.**"
    ),
    response_description="Suscripción actualizada.",
    **protected(
        SUBSCRIPTIONS_UPDATE,
        responses={
            404: NOT_FOUND,
            409: WRITE_CONFLICT,
            422: WRITE_VALIDATION_ERROR,
            503: WRITE_UNAVAILABLE,
            500: INTERNAL_ERROR,
        },
    ),
)
async def update_subscription(
    subscription_id: SubscriptionIdPath,
    data: Annotated[SubscriptionUpdate, Body(openapi_examples=UPDATE_EXAMPLES)],
    service: SubscriptionServiceDep,
    token: BearerTokenDep,
) -> SubscriptionRead:
    return _to_read(await service.update(subscription_id, data, token))


@router.patch(
    "/{subscription_id}/status",
    response_model=SubscriptionRead,
    operation_id="change_subscription_status",
    summary="Cambiar el estatus de una suscripción",
    description=(
        "Cambia el estatus de una suscripción vigente a Activa (1), Inactiva (2) o Bloqueada (3), "
        "en cualquier dirección y tenga o no clínicas. Pedir el estatus que ya tiene se rechaza. "
        "«Eliminada» (4) y los estatus desconocidos se rechazan: eliminar tiene su propia "
        "operación.\n\n"
        "**Permiso requerido: `subscriptions:update`.**"
    ),
    response_description="Suscripción con su nuevo estatus.",
    **protected(
        SUBSCRIPTIONS_UPDATE,
        responses={
            404: NOT_FOUND,
            409: STATUS_UNCHANGED,
            422: VALIDATION_ERROR,
            500: INTERNAL_ERROR,
        },
    ),
)
async def change_subscription_status(
    subscription_id: SubscriptionIdPath,
    data: Annotated[SubscriptionStatusChange, Body(openapi_examples=STATUS_EXAMPLES)],
    service: SubscriptionServiceDep,
    token: BearerTokenDep,
) -> SubscriptionRead:
    return _to_read(await service.change_status(subscription_id, data, token))


@router.delete(
    "/{subscription_id}",
    status_code=204,
    response_class=Response,
    operation_id="delete_subscription",
    summary="Eliminar una suscripción (baja lógica)",
    description=(
        "Pasa la suscripción al estatus Eliminada: sus datos se conservan, deja de aparecer en el "
        "catálogo y en las consultas, no puede modificarse ni recuperarse con esta API y su nombre "
        "queda libre. **Se rechaza si tiene clínicas asignadas** (`subscription_has_clinics`) y "
        "también si no puede comprobarse porque el API de clínicas no responde "
        "(`clinics_check_unavailable`); en ambos casos no cambia nada.\n\n"
        "**Permiso requerido: `subscriptions:delete`.**"
    ),
    response_description="Suscripción eliminada (sin contenido).",
    **protected(
        SUBSCRIPTIONS_DELETE,
        responses={
            404: NOT_FOUND,
            409: HAS_CLINICS,
            422: VALIDATION_ERROR,
            503: DELETE_UNAVAILABLE,
            500: INTERNAL_ERROR,
        },
    ),
)
async def delete_subscription(
    subscription_id: SubscriptionIdPath, service: SubscriptionServiceDep, token: BearerTokenDep
) -> Response:
    await service.delete(subscription_id, token)
    return Response(status_code=204)

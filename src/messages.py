"""Shared vocabulary of the API: error codes and the Spanish messages shown to people.

This module imports no layer. The codes are English and stable (consumers rely on them); the
messages are Spanish and written for non-technical people (FR-021). The validation messages are
organised per resource (the first path segment after /api/v1/) so a feature never touches the
texts of another one. The texts come from `specs/004-correct-subscriptions-api/contracts/error-catalog.md`
(the complete catalog, superseding `specs/001-subscriptions-api/contracts/error-catalog.md`) and, for
the registry of monitored components, from `specs/005-health-monitoring/contracts/error-catalog.md`;
they must not be paraphrased.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_EXPIRED = "token_expired"
    INVALID_TOKEN = "invalid_token"
    PERMISSION_DENIED = "permission_denied"
    AUTHORIZATION_UNAVAILABLE = "authorization_unavailable"
    SUBSCRIPTION_NOT_FOUND = "subscription_not_found"
    SUBSCRIPTION_NAME_ALREADY_EXISTS = "subscription_name_already_exists"
    SUBSCRIPTION_STATUS_UNCHANGED = "subscription_status_unchanged"
    SUBSCRIPTION_HAS_CLINICS = "subscription_has_clinics"
    CLINICS_CHECK_UNAVAILABLE = "clinics_check_unavailable"
    SUBSCRIPTION_MODULE_NOT_FOUND = "subscription_module_not_found"
    SUBSCRIPTION_MODULE_PREREQUISITE_MISSING = "subscription_module_prerequisite_missing"
    MODULE_CHECK_UNAVAILABLE = "module_check_unavailable"
    SUBSCRIPTION_TYPE_NOT_FOUND = "subscription_type_not_found"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"
    MONITORED_COMPONENT_NOT_FOUND = "monitored_component_not_found"
    MONITORED_COMPONENT_CODE_ALREADY_EXISTS = "monitored_component_code_already_exists"


# --- Access control ---

UNAUTHENTICATED_MESSAGE = "Debe iniciar sesión para usar esta operación."
TOKEN_EXPIRED_MESSAGE = "Su sesión venció. Inicie sesión de nuevo."
INVALID_TOKEN_MESSAGE = "El token de acceso no es válido."
PERMISSION_DENIED_MESSAGE = (
    "No tiene permiso para realizar esta operación. Permiso requerido: {permission}."
)
AUTHORIZATION_UNAVAILABLE_MESSAGE = (
    "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde."
)

# --- Domain errors of the subscriptions ---

SUBSCRIPTION_NOT_FOUND_MESSAGE = (
    "No se encontró la suscripción con el identificador {subscription_id}."
)
SUBSCRIPTION_NAME_ALREADY_EXISTS_MESSAGE = "Ya existe una suscripción con el nombre «{name}»."
SUBSCRIPTION_STATUS_UNCHANGED_MESSAGE = (
    "La suscripción con el identificador {subscription_id} ya tiene el estatus {status}."
)
SUBSCRIPTION_HAS_CLINICS_MESSAGE = (
    "No se puede eliminar la suscripción con el identificador {subscription_id} porque tiene "
    "clínicas asignadas."
)
CLINICS_CHECK_UNAVAILABLE_MESSAGE = (
    "No se pudo comprobar si la suscripción con el identificador {subscription_id} tiene "
    "clínicas asignadas. No se eliminó; inténtelo de nuevo más tarde."
)
SUBSCRIPTION_MODULE_NOT_FOUND_MESSAGE = (
    "La API de usuarios no reconoce el módulo «{module_key}» como un módulo de clínica vigente."
)
SUBSCRIPTION_MODULE_PREREQUISITE_MISSING_MESSAGE = (
    "El módulo «{module_key}» exige el módulo «{prerequisite_key}», que no está incluido."
)
MODULE_CHECK_UNAVAILABLE_MESSAGE = (
    "No se pudo comprobar los módulos de la suscripción por ahora. No se guardó ningún cambio; "
    "inténtelo de nuevo más tarde."
)
SUBSCRIPTION_TYPE_NOT_FOUND_MESSAGE = (
    "No se encontró el tipo de suscripción con el identificador {subscription_type_id}."
)

# --- Domain errors of the registry of monitored components (spec 005) ---

MONITORED_COMPONENT_NOT_FOUND_MESSAGE = (
    "No se encontró el componente monitoreado con el identificador {component_id}."
)
MONITORED_COMPONENT_CODE_ALREADY_EXISTS_MESSAGE = (
    "Ya existe un componente monitoreado con el código «{code}»."
)

# --- Generic errors ---

VALIDATION_ERROR_MESSAGE = "Hay datos no válidos en la solicitud."
INTERNAL_ERROR_MESSAGE = "Ocurrió un error inesperado. Inténtelo de nuevo más tarde."

# --- Validation messages ---

FORBIDDEN_FIELD_MESSAGE = "El campo «{field}» no está permitido."
INVALID_BODY_MESSAGE = "El cuerpo de la solicitud no es válido."
INVALID_VALUE_MESSAGE = "El valor del campo «{field}» no es válido."

# Raised as `ValueError` by the validators of the DTOs (their text is already in Spanish). Public
# because `SubscriptionUpdate` reuses them for its "cannot be null" validators, not only
# `VALIDATION_MESSAGES` below.
SUBSCRIPTION_EMPTY_UPDATE_MESSAGE = "Hay que enviar al menos un dato para modificar."
SUBSCRIPTION_TYPE_REQUIRED_MESSAGE = (
    "El tipo de suscripción es obligatorio y debe ser un número entero positivo."
)
SUBSCRIPTION_TYPE_IMMUTABLE_MESSAGE = (
    "El tipo de suscripción no puede modificarse una vez creada."
)
SUBSCRIPTION_NAME_REQUIRED_MESSAGE = "El nombre de la suscripción es obligatorio."
SUBSCRIPTION_PRICE_REQUIRED_MESSAGE = "El precio mensual es obligatorio."
SUBSCRIPTION_ANNUAL_PRICE_REQUIRED_MESSAGE = "El precio anual es obligatorio."
SUBSCRIPTION_OTHER_FEATURES_NOT_LIST_MESSAGE = (
    "Lo que incluye la suscripción debe ser una lista de textos."
)
SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE = "Cada módulo debe identificarse con una clave válida."
SUBSCRIPTION_TRIAL_DAYS_INVALID_MESSAGE = (
    "Los días de prueba deben ser un número entero de 0 a 3650."
)
SUBSCRIPTION_SELF_SERVICE_INVALID_MESSAGE = "El autoconsumo debe ser verdadero o falso."
SUBSCRIPTION_CONSULTING_ROOMS_LIMIT_INVALID_MESSAGE = (
    "El límite de consultorios debe ser un número entero de 0 a 1 000 000."
)
SUBSCRIPTION_DOCTORS_LIMIT_INVALID_MESSAGE = (
    "El límite de doctores debe ser un número entero de 0 a 1 000 000."
)
SUBSCRIPTION_ASSISTANTS_LIMIT_INVALID_MESSAGE = (
    "El límite de asistentes debe ser un número entero de 0 a 1 000 000."
)
SUBSCRIPTION_NEW_PATIENTS_PER_YEAR_LIMIT_INVALID_MESSAGE = (
    "El límite de pacientes nuevos al año debe ser un número entero de 0 a 1 000 000."
)
SUBSCRIPTION_STATUS_NOT_ALLOWED_MESSAGE = (
    "El estatus debe ser uno de los que admite esta operación (1, 2 o 3)."
)

_PRICE_INVALID_MESSAGE = (
    "El precio mensual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales."
)
_ANNUAL_PRICE_INVALID_MESSAGE = (
    "El precio anual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales."
)
_OTHER_FEATURE_ITEM_MESSAGE = (
    "Cada elemento de lo que incluye la suscripción debe tener de 1 a 150 caracteres."
)
_TOO_MANY_MODULES_MESSAGE = "No se pueden pedir más de 50 módulos."
_STATUS_REQUIRED_MESSAGE = "El estatus es obligatorio y debe ser un número entero."

# --- Validation messages of the dashboard (spec 003, contracts/error-catalog.md) ---

# One text for every invalid `limit` (below 1, not an integer, empty or repeated): it never repeats
# the value that was received.
DASHBOARD_LIMIT_INVALID_MESSAGE = (
    "El parámetro «limit» debe ser un número entero mayor o igual que 1."
)

# --- Validation messages of the registry of components (spec 005, contracts/error-catalog.md) ---

# Raised as `ValueError` by the validators of the DTOs, and by the Service in the errors it decides
# (the list of allowed hosts and the rules that depend on `kind`). None repeats the value that was
# received: a `base_url` could carry credentials, and the list of allowed hosts is never revealed.
MONITORED_COMPONENT_CODE_REQUIRED_MESSAGE = "El código del componente es obligatorio."
MONITORED_COMPONENT_CODE_INVALID_MESSAGE = (
    "El código debe tener de 2 a 50 caracteres entre minúsculas sin acentos, dígitos y guiones, "
    "empezar con una letra y no terminar en guion ni tener dos guiones seguidos."
)
MONITORED_COMPONENT_NAME_REQUIRED_MESSAGE = "El nombre del componente es obligatorio."
MONITORED_COMPONENT_KIND_REQUIRED_MESSAGE = "El tipo del componente es obligatorio."
MONITORED_COMPONENT_KIND_INVALID_MESSAGE = "El tipo del componente debe ser «service» o «frontend»."
MONITORED_COMPONENT_BASE_URL_REQUIRED_MESSAGE = "La dirección base del componente es obligatoria."
MONITORED_COMPONENT_BASE_URL_INVALID_MESSAGE = (
    "La dirección base debe ser una dirección http:// o https:// de hasta 255 caracteres, con un "
    "host válido y sin usuario, contraseña, consulta (?) ni fragmento (#)."
)
MONITORED_COMPONENT_HOST_NOT_ALLOWED_MESSAGE = (
    "El host de la dirección base no está entre los hosts permitidos por el servicio."
)
MONITORED_COMPONENT_PATH_INVALID_MESSAGE = (
    "La ruta debe empezar con una sola «/» y tener hasta 200 caracteres, sin segmentos «.» o «..» "
    "y sin «\\», «?», «#», «%», espacios ni caracteres de control."
)
MONITORED_COMPONENT_SERVICE_PATH_REQUIRED_MESSAGE = (
    "Un componente de tipo «service» necesita esta ruta: no puede ser nula."
)
MONITORED_COMPONENT_FRONTEND_LIVE_PATH_REQUIRED_MESSAGE = (
    "Un componente de tipo «frontend» necesita su ruta de salud."
)
MONITORED_COMPONENT_FRONTEND_READY_PATH_NOT_ALLOWED_MESSAGE = (
    "Un componente de tipo «frontend» no lleva ruta de disponibilidad: envíela nula o no la envíe."
)
MONITORED_COMPONENT_ENABLED_INVALID_MESSAGE = "«enabled» debe ser verdadero o falso."
MONITORED_COMPONENT_SORT_ORDER_INVALID_MESSAGE = "El orden debe ser un número entero de 0 a 9999."
# The same text as in the subscriptions (contracts/error-catalog.md).
MONITORED_COMPONENT_EMPTY_UPDATE_MESSAGE = SUBSCRIPTION_EMPTY_UPDATE_MESSAGE
MONITORED_COMPONENT_ID_INVALID_MESSAGE = "El identificador del componente debe ser un UUID."

# (field, kind) -> message. The kinds are `required`, `too_long`, `too_many`, `not_text`,
# `not_list` and `invalid` (see `_KINDS` in `src/error_handlers.py`).
# Messages shared by every resource; today the only resource has its own block below.
FIELD_MESSAGES: dict[tuple[str, str], str] = {}

VALIDATION_MESSAGES: dict[str, dict[tuple[str, str], str]] = {
    "subscriptions": {
        ("subscription_type_id", "required"): SUBSCRIPTION_TYPE_REQUIRED_MESSAGE,
        ("subscription_type_id", "invalid"): SUBSCRIPTION_TYPE_REQUIRED_MESSAGE,
        ("subscription_type_id", "forbidden"): SUBSCRIPTION_TYPE_IMMUTABLE_MESSAGE,
        ("name", "required"): SUBSCRIPTION_NAME_REQUIRED_MESSAGE,
        ("name", "too_long"): "El nombre de la suscripción no puede tener más de 100 caracteres.",
        ("name", "not_text"): "El nombre de la suscripción debe ser un texto.",
        ("description", "too_long"): "La descripción no puede tener más de 500 caracteres.",
        ("monthly_price", "required"): SUBSCRIPTION_PRICE_REQUIRED_MESSAGE,
        ("monthly_price", "invalid"): _PRICE_INVALID_MESSAGE,
        ("annual_price", "required"): SUBSCRIPTION_ANNUAL_PRICE_REQUIRED_MESSAGE,
        ("annual_price", "invalid"): _ANNUAL_PRICE_INVALID_MESSAGE,
        ("trial_days", "invalid"): SUBSCRIPTION_TRIAL_DAYS_INVALID_MESSAGE,
        ("self_service", "invalid"): SUBSCRIPTION_SELF_SERVICE_INVALID_MESSAGE,
        ("module_keys", "not_list"): SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE,
        ("module_keys", "not_text"): SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE,
        ("module_keys", "invalid"): SUBSCRIPTION_MODULE_KEYS_NOT_VALID_MESSAGE,
        ("module_keys", "too_many"): _TOO_MANY_MODULES_MESSAGE,
        ("other_features", "not_list"): SUBSCRIPTION_OTHER_FEATURES_NOT_LIST_MESSAGE,
        ("other_features", "not_text"): SUBSCRIPTION_OTHER_FEATURES_NOT_LIST_MESSAGE,
        ("other_features", "too_many"): (
            "Lo que incluye la suscripción no puede tener más de 20 elementos."
        ),
        ("other_features", "required"): _OTHER_FEATURE_ITEM_MESSAGE,
        ("other_features", "too_long"): _OTHER_FEATURE_ITEM_MESSAGE,
        ("consulting_rooms_limit", "required"): SUBSCRIPTION_CONSULTING_ROOMS_LIMIT_INVALID_MESSAGE,
        ("consulting_rooms_limit", "invalid"): SUBSCRIPTION_CONSULTING_ROOMS_LIMIT_INVALID_MESSAGE,
        ("doctors_limit", "required"): SUBSCRIPTION_DOCTORS_LIMIT_INVALID_MESSAGE,
        ("doctors_limit", "invalid"): SUBSCRIPTION_DOCTORS_LIMIT_INVALID_MESSAGE,
        ("assistants_limit", "required"): SUBSCRIPTION_ASSISTANTS_LIMIT_INVALID_MESSAGE,
        ("assistants_limit", "invalid"): SUBSCRIPTION_ASSISTANTS_LIMIT_INVALID_MESSAGE,
        ("new_patients_per_year_limit", "required"): (
            SUBSCRIPTION_NEW_PATIENTS_PER_YEAR_LIMIT_INVALID_MESSAGE
        ),
        ("new_patients_per_year_limit", "invalid"): (
            SUBSCRIPTION_NEW_PATIENTS_PER_YEAR_LIMIT_INVALID_MESSAGE
        ),
        ("status_id", "required"): _STATUS_REQUIRED_MESSAGE,
        ("status_id", "invalid"): _STATUS_REQUIRED_MESSAGE,
        ("subscription_id", "invalid"): (
            "El identificador de la suscripción debe ser un número entero positivo."
        ),
    },
    "dashboard": {
        ("limit", "invalid"): DASHBOARD_LIMIT_INVALID_MESSAGE,
    },
    # The native errors of Pydantic; the formats raise their own message (see above).
    "monitored-components": {
        ("code", "required"): MONITORED_COMPONENT_CODE_REQUIRED_MESSAGE,
        ("name", "required"): MONITORED_COMPONENT_NAME_REQUIRED_MESSAGE,
        ("name", "too_long"): "El nombre del componente no puede tener más de 100 caracteres.",
        ("name", "not_text"): "El nombre del componente debe ser un texto.",
        ("kind", "required"): MONITORED_COMPONENT_KIND_REQUIRED_MESSAGE,
        ("base_url", "required"): MONITORED_COMPONENT_BASE_URL_REQUIRED_MESSAGE,
        ("enabled", "required"): MONITORED_COMPONENT_ENABLED_INVALID_MESSAGE,
        ("enabled", "invalid"): MONITORED_COMPONENT_ENABLED_INVALID_MESSAGE,
        ("sort_order", "required"): MONITORED_COMPONENT_SORT_ORDER_INVALID_MESSAGE,
        ("sort_order", "invalid"): MONITORED_COMPONENT_SORT_ORDER_INVALID_MESSAGE,
        ("component_id", "invalid"): MONITORED_COMPONENT_ID_INVALID_MESSAGE,
    },
}

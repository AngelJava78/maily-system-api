"""Helpers shared by the Routers to document their responses in OpenAPI (texts in Spanish)."""

from typing import Any

from fastapi import Depends

from src.dtos.errors import ErrorResponse
from src.security import require_permission


def error_response(description: str, **examples: dict[str, Any]) -> dict[str, Any]:
    """OpenAPI entry for an error: the uniform `ErrorResponse` body plus Spanish examples."""
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "examples": {name: {"value": body} for name, body in examples.items()}
            }
        },
    }


def example_response(description: str, example_name: str, value: Any) -> dict[str, Any]:
    """OpenAPI entry for a success response, with one example body."""
    return {
        "description": description,
        "content": {"application/json": {"examples": {example_name: {"value": value}}}},
    }


# --- Access control: responses that every protected operation shares ---

UNAUTHORIZED: dict[str, Any] = {
    **error_response(
        "No hay token, venció o no es válido. No se ejecuta ni se cambia nada. La respuesta "
        "incluye la cabecera `WWW-Authenticate`.",
        sin_token={
            "code": "unauthenticated",
            "message": "Debe iniciar sesión para usar esta operación.",
        },
        vencido={"code": "token_expired", "message": "Su sesión venció. Inicie sesión de nuevo."},
        no_valido={"code": "invalid_token", "message": "El token de acceso no es válido."},
    ),
    "headers": {
        "WWW-Authenticate": {
            "description": "Esquema de autenticación esperado.",
            "schema": {"type": "string"},
            "example": "Bearer",
        }
    },
}
FORBIDDEN = error_response(
    "La persona está autenticada pero no tiene el permiso que exige la operación. No se ejecuta "
    "ni se cambia nada, y no se revela si el recurso existe ni si los datos eran válidos.",
    sin_permiso={
        "code": "permission_denied",
        "message": (
            "No tiene permiso para realizar esta operación. Permiso requerido: "
            "subscriptions:write."
        ),
    },
)
AUTHORIZATION_UNAVAILABLE = error_response(
    "No se pudo verificar el permiso por ahora (el API de usuarios no responde o respondió algo "
    "inesperado): la petición se rechaza y se puede reintentar más tarde.",
    no_disponible={
        "code": "authorization_unavailable",
        "message": "No se pudo verificar su permiso por ahora. Inténtelo de nuevo más tarde.",
    },
)


def protected(
    permission: str, *, responses: dict[int | str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Arguments for a route decorator that makes the operation require `permission`.

    Use it as `@router.get("", **protected(SUBSCRIPTIONS_READ))`: one gesture declares the
    dependency that checks the permission, the `x-required-permission` extension and the shared
    401, 403 and 503 responses. The `responses` received override the shared ones with the same
    key (the deletion documents two different 503).
    """
    return {
        "dependencies": [Depends(require_permission(permission))],
        "openapi_extra": {"x-required-permission": permission},
        "responses": {
            401: UNAUTHORIZED,
            403: FORBIDDEN,
            503: AUTHORIZATION_UNAVAILABLE,
            **(responses or {}),
        },
    }

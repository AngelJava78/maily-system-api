"""Exception handlers: every error of the API leaves with the same body (FR-021).

- `AppError` (domain errors) -> its own status with `ErrorResponse(code, message)`.
- `RequestValidationError` -> 422 with `errors[]`, one element per invalid piece of data and
  with its message in Spanish (never the English text of Pydantic).
- Any other exception -> 500 with a generic message; the detail only goes to the server log, and
  never the body of the request.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.dtos.errors import ErrorResponse, FieldError
from src.exceptions import AppError
from src.messages import (
    FIELD_MESSAGES,
    FORBIDDEN_FIELD_MESSAGE,
    INTERNAL_ERROR_MESSAGE,
    INVALID_BODY_MESSAGE,
    INVALID_VALUE_MESSAGE,
    VALIDATION_ERROR_MESSAGE,
    VALIDATION_MESSAGES,
    ErrorCode,
)

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1/"
_REQUEST_PARTS = {"body", "query", "path", "header", "cookie"}

# Type of Pydantic error -> kind of message. The text of each (field, kind) lives in
# `src/messages.py`; a kind without text falls back to a generic message.
_KINDS = {
    "missing": "required",
    "string_too_short": "required",
    "string_too_long": "too_long",
    "too_long": "too_many",  # what a list with too many elements reports
    "string_type": "not_text",
    "list_type": "not_list",
    "extra_forbidden": "forbidden",
    "int_parsing": "invalid",
    "int_type": "invalid",
    "int_from_float": "invalid",
    "greater_than": "invalid",
    "greater_than_equal": "invalid",
    "less_than": "invalid",
    "less_than_equal": "invalid",
    "decimal_parsing": "invalid",
    "decimal_type": "invalid",
    "decimal_max_places": "invalid",
    "decimal_max_digits": "invalid",
    "decimal_whole_digits": "invalid",
    "finite_number": "invalid",
}


def _field_of(loc: Sequence[str | int]) -> str:
    """Name of the API field an error refers to, or `body` when it concerns the whole body."""
    parts = list(loc)
    if parts and parts[0] in _REQUEST_PARTS:
        parts = parts[1:]
    if parts and isinstance(parts[0], str):
        return parts[0]
    return "body"


def _kind_of(error: Mapping[str, Any]) -> str | None:
    error_type = error["type"]
    # A `null` where a value is mandatory reads better as "required" than as "wrong type"
    # (except for lists, whose own message already says "must be a list").
    if error_type.endswith("_type") and error_type != "list_type" and error.get("input") is None:
        return "required"
    return _KINDS.get(error_type)


def _message_of(error: Mapping[str, Any], field: str, resource: str) -> str:
    error_type = error["type"]
    if error_type == "value_error":
        # Our own validators raise ValueError with a message that is already in Spanish.
        original = (error.get("ctx") or {}).get("error")
        return str(original) if original is not None else INVALID_VALUE_MESSAGE.format(field=field)
    if error_type == "json_invalid" or field == "body":
        return INVALID_BODY_MESSAGE
    kind = _kind_of(error)
    if kind is not None:
        text = VALIDATION_MESSAGES.get(resource, {}).get((field, kind))
        if text is None:
            text = FIELD_MESSAGES.get((field, kind))
        if text is not None:
            return text
        if kind == "forbidden":
            return FORBIDDEN_FIELD_MESSAGE.format(field=field)
    return INVALID_VALUE_MESSAGE.format(field=field)


def translate_validation_errors(
    errors: Sequence[Mapping[str, Any]], resource: str
) -> list[FieldError]:
    """Turn Pydantic validation errors into `FieldError`s with Spanish messages.

    `resource` is the first path segment after /api/v1/ (e.g. `subscriptions`); it selects the
    block of messages of that resource. The value that was received is never repeated.
    """
    result = []
    for error in errors:
        field = _field_of(error["loc"])
        result.append(FieldError(field=field, message=_message_of(error, field, resource)))
    return result


def _resource_of(path: str) -> str:
    if not path.startswith(API_PREFIX):
        return ""
    return path[len(API_PREFIX) :].split("/", 1)[0]


def _error_response(
    status_code: int, body: ErrorResponse, headers: dict[str, str] | None = None
) -> JSONResponse:
    content = body.model_dump(mode="json", exclude_none=True)
    return JSONResponse(status_code=status_code, content=content, headers=headers)


async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    return _error_response(
        error.status_code,
        ErrorResponse(code=error.code, message=error.message),
        error.headers,
    )


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    body = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message=VALIDATION_ERROR_MESSAGE,
        errors=translate_validation_errors(error.errors(), _resource_of(request.url.path)),
    )
    return _error_response(422, body)


async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    # The trace goes to the log (in English); the request body and headers never do.
    logger.error(
        "Unhandled error while processing %s %s", request.method, request.url.path, exc_info=error
    )
    return _error_response(
        500, ErrorResponse(code=ErrorCode.INTERNAL_ERROR, message=INTERNAL_ERROR_MESSAGE)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

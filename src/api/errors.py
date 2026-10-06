"""Errores uniformes en JSON.

Toda respuesta de error tiene la misma forma, sea un 404, un 422 o un fallo interno:

    {"error": {"code": "not_found", "message": "...", "request_id": "...", "details": []}}

`request_id` coincide con la cabecera `X-Request-ID` y con la línea de log de la petición.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from src.api.middleware import REQUEST_ID_HEADER

CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
}

MESSAGES = {
    400: "Petición incorrecta",
    404: "No encontrado",
    405: "Método no permitido",
    422: "Parámetros no válidos",
    429: "Demasiadas peticiones",
    500: "Error interno del servidor",
}


class FieldError(BaseModel):
    field: str  # p. ej. "query.day"
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None
    details: list[FieldError] = []


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Errores para documentar en OpenAPI con `responses=` en una ruta o un router."""
    return {
        code: {"model": ErrorResponse, "description": MESSAGES.get(code, HTTPStatus(code).phrase)}
        for code in status_codes
    }


def error_response(
    request: Request,
    status_code: int,
    message: str | None = None,
    details: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = ErrorBody(
        code=CODES.get(status_code, "http_error"),
        message=message or MESSAGES.get(status_code) or HTTPStatus(status_code).phrase,
        request_id=request_id,
        details=details or [],
    )
    headers = dict(headers or {})
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(jsonable_encoder(ErrorResponse(error=body)), status_code=status_code, headers=headers)


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    # Si la ruta da un mensaje propio se usa; el genérico de Starlette ("Not Found") se traduce
    default = HTTPStatus(exc.status_code).phrase
    message = exc.detail if isinstance(exc.detail, str) and exc.detail != default else None
    return error_response(request, exc.status_code, message, headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        FieldError(field=".".join(str(part) for part in err["loc"]), message=err["msg"], type=err["type"])
        for err in exc.errors()
    ]
    return error_response(request, 422, details=details)


async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    # No se devuelve el detalle del fallo: queda en el log con el mismo request_id
    return error_response(request, 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _internal_error)

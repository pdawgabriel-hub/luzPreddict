"""Middleware de id de petición y logging.

Cada petición lleva un id que se devuelve en la cabecera `X-Request-ID` y aparece
en su línea de log, para poder buscarla en los logs de Vercel. Si el cliente ya
manda uno válido se reutiliza; si no, se genera.

Es un middleware ASGI puro: no lee ni modifica el cuerpo de la respuesta.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Solo caracteres seguros: el id acaba en los logs y no debe poder inyectar líneas
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

logger = logging.getLogger("src.api.requests")


def new_request_id() -> str:
    return uuid.uuid4().hex


def _incoming_request_id(scope: Scope) -> str | None:
    header = REQUEST_ID_HEADER.lower().encode()
    for name, value in scope["headers"]:
        if name == header:
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None


class RequestContextMiddleware:
    """Asigna un id a cada petición, lo devuelve en la respuesta y registra método, ruta, estado y duración."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id  # disponible como request.state.request_id
        started = time.perf_counter()
        status = 500  # si la aplicación falla antes de responder

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            level = logging.ERROR if status >= 500 else logging.INFO
            logger.log(
                level,
                "%s %s %d %.1fms id=%s",
                scope["method"],
                scope["path"],
                status,
                elapsed_ms,
                request_id,
            )

"""Límite de peticiones por IP con Upstash Redis.

Ventana fija de un minuto: cada IP tiene un contador por minuto en Redis que
caduca solo. Al superarlo, la API responde 429 con `Retry-After`; todas las
respuestas limitadas llevan `X-RateLimit-Limit`, `X-RateLimit-Remaining` y
`X-RateLimit-Reset` (segundos hasta que se reinicia el contador).

- Sin `UPSTASH_REDIS_REST_URL` y `UPSTASH_REDIS_REST_TOKEN` (tests, CI, desarrollo
  sin cuenta) el límite está desactivado.
- Si Upstash falla o tarda, la petición pasa: es preferible no limitar a dejar la
  API sin servicio.
- No se guarda la IP: la clave es un hash de la IP con el token como secreto.

Se habla con Upstash por su API REST con la biblioteca estándar, sin dependencias
nuevas. La dependencia es síncrona: FastAPI la ejecuta en un hilo y no bloquea.
"""

import hashlib
import hmac
import json
import logging
import math
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, Response

from src.utils.config import Settings

WINDOW_SECONDS = 60
UPSTASH_TIMEOUT_SECONDS = 1.0
LIMIT_HEADERS = ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After")

logger = logging.getLogger(__name__)


class Counter(Protocol):
    def hit(self, key: str, ttl_seconds: int) -> int:
        """Suma uno al contador `key` (que caduca a los `ttl_seconds`) y devuelve su valor."""


class UpstashCounter:
    """Contador en Upstash Redis a través de su API REST (INCR + EXPIRE en una sola petición)."""

    def __init__(self, url: str, token: str, timeout: float = UPSTASH_TIMEOUT_SECONDS):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def hit(self, key: str, ttl_seconds: int) -> int:
        commands = [["INCR", key], ["EXPIRE", key, ttl_seconds]]
        request = urllib.request.Request(
            f"{self.url}/pipeline",
            data=json.dumps(commands).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            results = json.load(response)
        errors = [r["error"] for r in results if "error" in r]
        if errors:
            raise RuntimeError(f"Upstash: {errors[0]}")
        return int(results[0]["result"])


@dataclass(frozen=True)
class RateLimitResult:
    limit: int
    count: int  # peticiones de esta IP en la ventana actual, contando esta
    reset_seconds: int  # segundos hasta que empieza la siguiente ventana

    @property
    def allowed(self) -> bool:
        return self.count <= self.limit

    @property
    def remaining(self) -> int:
        return max(self.limit - self.count, 0)

    def headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_seconds),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.reset_seconds)
        return headers


class RateLimiter:
    def __init__(
        self,
        counter: Counter,
        limit: int,
        secret: str,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        self.counter = counter
        self.limit = limit
        self.secret = secret.encode()
        self.window_seconds = window_seconds
        self.clock = clock

    def key(self, client: str, window_start: int) -> str:
        digest = hmac.new(self.secret, client.encode(), hashlib.sha256).hexdigest()[:32]
        return f"rate:{digest}:{window_start}"

    def check(self, client: str) -> RateLimitResult:
        now = self.clock()
        window_start = int(now // self.window_seconds) * self.window_seconds
        count = self.counter.hit(self.key(client, window_start), self.window_seconds)
        reset = max(math.ceil(window_start + self.window_seconds - now), 1)
        return RateLimitResult(self.limit, count, reset)


def build_rate_limiter(settings: Settings) -> RateLimiter | None:
    """El limitador de la configuración, o None si Upstash no está configurado."""
    if not (settings.upstash_redis_rest_url and settings.upstash_redis_rest_token):
        return None
    counter = UpstashCounter(settings.upstash_redis_rest_url, settings.upstash_redis_rest_token)
    return RateLimiter(counter, settings.rate_limit_per_minute, secret=settings.upstash_redis_rest_token)


def client_ip(request: Request) -> str:
    """IP del cliente. Vercel (y el nginx de Docker) ponen la real en `X-Real-IP`, sobrescribiendo la del cliente."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "desconocida")


def rate_limit(request: Request, response: Response) -> None:
    """Dependencia de las rutas limitadas: 429 si la IP supera el límite del minuto."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    try:
        result = limiter.check(client_ip(request))
    except Exception as exc:  # Upstash caído o lento: se deja pasar
        logger.warning("Límite de peticiones no disponible, se deja pasar (%s: %s)", type(exc).__name__, exc)
        return
    if not result.allowed:
        raise HTTPException(
            429,
            f"Has superado el límite de {result.limit} peticiones por minuto: "
            f"vuelve a intentarlo en {result.reset_seconds} s",
            headers=result.headers(),
        )
    response.headers.update(result.headers())

"""Cliente de la API pública de REE (apidatos.ree.es).

Es genérico: descarga cualquier indicador por tramos de fechas, reintenta los
errores temporales y devuelve las series con las fechas en UTC. Los módulos de
cada indicador (PVPC, generación…) deciden qué pedir y cómo guardarlo.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.config import get_settings

logger = logging.getLogger(__name__)

RETRY_STATUS = (429, 500, 502, 503, 504)


class ReeApiError(RuntimeError):
    """La API de REE ha rechazado la petición."""


@dataclass(frozen=True, slots=True)
class ReePoint:
    datetime: datetime  # inicio del periodo, en UTC
    value: float


def date_chunks(start: date, end: date, max_days: int) -> Iterator[tuple[date, date]]:
    """Divide [start, end], ambos incluidos, en tramos de como mucho `max_days` días."""
    if start > end:
        raise ValueError(f"La fecha inicial ({start}) es posterior a la final ({end})")
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def build_session(total_retries: int = 5, backoff_factor: float = 1.0) -> requests.Session:
    """Sesión HTTP que reintenta 429 y 5xx con espera creciente."""
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=RETRY_STATUS,
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def parse_series(payload: dict[str, Any]) -> dict[str, list[ReePoint]]:
    """Extrae todas las series de una respuesta de REE, indexadas por su tipo.

    Admite tanto series simples como agrupadas (las que traen `content`).
    """
    items = []
    for item in payload.get("included", []):
        content = item.get("attributes", {}).get("content")
        items.extend(content if content else [item])

    series: dict[str, list[ReePoint]] = {}
    for item in items:
        values = item.get("attributes", {}).get("values", [])
        series.setdefault(item["type"], []).extend(
            ReePoint(datetime.fromisoformat(v["datetime"]).astimezone(UTC), float(v["value"])) for v in values
        )
    return series


class ReeClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_days: int | None = None,
    ):
        settings = get_settings()
        self.session = session or build_session()
        self.base_url = (base_url or settings.ree_api_url).rstrip("/")
        self.timeout = timeout or settings.ree_timeout_seconds
        self.max_days = max_days or settings.ree_max_days_per_request

    def fetch(
        self,
        path: str,
        start: date,
        end: date,
        time_trunc: str = "hour",
        params: dict[str, Any] | None = None,
    ) -> dict[str, list[ReePoint]]:
        """Descarga un indicador entre `start` y `end` (días locales, incluidos).

        Devuelve cada serie ordenada por fecha y sin duplicados entre tramos.
        """
        url = f"{self.base_url}/{path.strip('/')}"
        merged: dict[str, dict[datetime, float]] = {}

        for chunk_start, chunk_end in date_chunks(start, end, self.max_days):
            logger.info("REE %s: %s a %s", path, chunk_start, chunk_end)
            query = {
                "start_date": f"{chunk_start:%Y-%m-%d}T00:00",
                "end_date": f"{chunk_end:%Y-%m-%d}T23:59",
                "time_trunc": time_trunc,
                **(params or {}),
            }
            response = self.session.get(url, params=query, timeout=self.timeout)
            payload = self._json_or_raise(response)
            for name, points in parse_series(payload).items():
                merged.setdefault(name, {}).update((p.datetime, p.value) for p in points)

        return {name: [ReePoint(ts, value) for ts, value in sorted(points.items())] for name, points in merged.items()}

    @staticmethod
    def _json_or_raise(response: requests.Response) -> dict[str, Any]:
        if response.ok:
            return response.json()
        try:
            errors = response.json().get("errors", [])
            detail = "; ".join(e.get("detail", "") for e in errors) or response.text
        except ValueError:
            detail = response.text
        raise ReeApiError(f"REE respondió {response.status_code}: {detail}")

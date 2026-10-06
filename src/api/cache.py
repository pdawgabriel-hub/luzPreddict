"""Cabeceras de caché: los datos solo cambian cuando corre la tarea diaria.

La tarea se programa a las 19:30 UTC, después de que REE publique los precios de
mañana (hacia las 20:15 en hora de Madrid), y se reintenta a las 21:30 UTC si
REE aún no había publicado (ver `.github/workflows/daily.yml`). Con un margen
para que termine, las respuestas de /v1 se pueden guardar hasta la siguiente de
esas horas: el navegador y la CDN de Vercel no vuelven a pedirlas antes.
"""

from datetime import UTC, datetime, time, timedelta

from fastapi import Response

from src.api.deps import NowDep

# Horas de la tarea diaria (UTC) más el margen para que termine
REFRESH_TIMES_UTC = (time(19, 50), time(21, 50))


def next_refresh(now: datetime) -> datetime:
    """Siguiente momento en que los datos pueden haber cambiado."""
    now = now.astimezone(UTC)
    candidates = [
        datetime.combine(now.date() + timedelta(days=offset), t, tzinfo=UTC)
        for offset in (0, 1)
        for t in REFRESH_TIMES_UTC
    ]
    return min(c for c in candidates if c > now)


def seconds_until_refresh(now: datetime) -> int:
    return int((next_refresh(now) - now).total_seconds())


def cache_until_refresh(response: Response, now: NowDep) -> None:
    """Dependencia de /v1: las respuestas correctas valen hasta la siguiente actualización."""
    seconds = seconds_until_refresh(now)
    response.headers["Cache-Control"] = f"public, max-age={seconds}, s-maxage={seconds}"


def no_store(response: Response) -> None:
    """Para lo que debe ser siempre actual, como /health."""
    response.headers["Cache-Control"] = "no-store"

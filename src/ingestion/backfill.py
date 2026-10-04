"""Descarga o actualiza el histórico de REE en la caché local: PVPC y generación.

Uso:
    python -m src.ingestion.backfill                  # incremental desde el último día guardado
    python -m src.ingestion.backfill --full           # todo el histórico de nuevo
    python -m src.ingestion.backfill --only pvpc      # solo uno de los dos conjuntos
    python -m src.ingestion.backfill --start 2025-01-01 --end 2025-01-31
"""

import argparse
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.ingestion import generation, prices
from src.ingestion.ree_client import ReeClient
from src.utils.calendar import local_date, market_timezone
from src.utils.config import get_settings
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


DATASETS = ("pvpc", "generacion")


def local_today() -> date:
    return datetime.now(market_timezone()).date()


def default_end(today: date | None = None) -> date:
    """Mañana en hora local: REE publica el PVPC del día siguiente hacia las 20:15."""
    return (today or local_today()) + timedelta(days=1)


def update_pvpc(
    start: date | None = None,
    end: date | None = None,
    full: bool = False,
    client: ReeClient | None = None,
    path: Path | None = None,
    today: date | None = None,
) -> pd.DataFrame:
    """Descarga el PVPC que falta y lo une al fichero local.

    Sin `start`, continúa desde el último día guardado (que se vuelve a pedir
    por si estaba incompleto) o, si no hay fichero, desde el inicio del histórico.
    """
    existing = prices.empty_prices() if full else prices.load_pvpc(path)
    if start is None:
        start = local_date(existing["datetime"].max()) if not existing.empty else get_settings().history_start
    end = end or default_end(today)

    if start > end:
        logger.info("PVPC al día: nada que descargar (%s > %s)", start, end)
        return existing

    new = prices.fetch_pvpc(start, end, client)
    merged = prices.merge_prices(existing, new)
    saved_to = prices.save_pvpc(merged, path)

    logger.info("PVPC: %d horas nuevas o actualizadas, %d en total -> %s", len(new), len(merged), saved_to)
    _warn_about_missing_hours(merged)
    return merged


def update_generation(
    start: date | None = None,
    end: date | None = None,
    full: bool = False,
    client: ReeClient | None = None,
    path: Path | None = None,
    today: date | None = None,
) -> pd.DataFrame:
    """Descarga la generación diaria que falta y la une al fichero local.

    Igual que el PVPC, pero termina hoy: la generación de un día se publica
    mientras transcurre, así que el último día guardado se vuelve a pedir.
    """
    existing = generation.empty_generation() if full else generation.load_generation(path)
    if start is None:
        start = existing["date"].max() if not existing.empty else get_settings().history_start
    end = end or today or local_today()

    if start > end:
        logger.info("Generación al día: nada que descargar (%s > %s)", start, end)
        return existing

    new = generation.fetch_generation(start, end, client)
    merged = generation.merge_generation(existing, new)
    saved_to = generation.save_generation(merged, path)

    days = merged["date"].nunique()
    logger.info("Generación: %d filas nuevas o actualizadas, %d días en total -> %s", len(new), days, saved_to)
    _warn_about_missing_days(merged)
    return merged


def _warn_about_missing_hours(df: pd.DataFrame) -> None:
    if df.empty:
        return
    expected = int((df["datetime"].max() - df["datetime"].min()) / pd.Timedelta(hours=1)) + 1
    if len(df) != expected:
        first, last = df["datetime"].min(), df["datetime"].max()
        logger.warning("PVPC: faltan %d horas entre %s y %s", expected - len(df), first, last)


def _warn_about_missing_days(df: pd.DataFrame) -> None:
    if df.empty:
        return
    first, last = df["date"].min(), df["date"].max()
    expected = (last - first).days + 1
    if df["date"].nunique() != expected:
        logger.warning("Generación: faltan %d días entre %s y %s", expected - df["date"].nunique(), first, last)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, help="primer día local (AAAA-MM-DD)")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        help="último día local (por defecto, mañana para el PVPC y hoy para la generación)",
    )
    parser.add_argument("--full", action="store_true", help="ignora la caché y descarga todo de nuevo")
    parser.add_argument("--only", choices=DATASETS, help="descarga solo uno de los conjuntos")
    args = parser.parse_args(argv)

    configure_logging()
    datasets = [args.only] if args.only else DATASETS
    if "pvpc" in datasets:
        update_pvpc(start=args.start, end=args.end, full=args.full)
    if "generacion" in datasets:
        update_generation(start=args.start, end=args.end, full=args.full)


if __name__ == "__main__":
    main()

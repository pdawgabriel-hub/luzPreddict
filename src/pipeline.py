"""Pipeline de datos y modelo sobre PostgreSQL.

Uso:
    python -m src.pipeline backfill [--full]   # descarga de REE lo que falta y lo guarda
    python -m src.pipeline train               # entrena y guarda el modelo en la base de datos
    python -m src.pipeline daily               # la tarea diaria: ingesta, previsión y error diario
    python -m src.pipeline predict             # muestra la previsión del siguiente día (sin guardar)

La tarea diaria es idempotente: se puede repetir (por ejemplo, el reintento de
las 21:30 UTC) sin duplicar datos ni previsiones. Si REE aún no ha publicado los precios de
mañana, termina como "pendiente".
"""

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from src.db import repository
from src.db.session import session_scope
from src.ingestion import generation, prices
from src.ingestion.backfill import local_today
from src.ingestion.ree_client import ReeClient
from src.models.evaluate import regression_metrics
from src.models.predict import Forecast, forecast_table, predict_day
from src.models.registry import load_from_db, save_to_db
from src.models.train import train_final_model
from src.processing import dataset
from src.processing.features import HISTORY_DAYS
from src.utils.calendar import local_date, local_day_hours
from src.utils.config import get_settings
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)

# Días ya publicados cuyo error se recalcula en cada ejecución (por si REE corrige algún precio)
ERROR_DAYS = 7


@dataclass(frozen=True)
class BackfillResult:
    prices_changed: int
    generation_changed: int
    last_price_day: date | None


@dataclass(frozen=True)
class DailyResult:
    status: str  # "completo" o "pendiente" (REE aún no ha publicado mañana)
    backfill: BackfillResult
    forecast: Forecast
    run_id: int
    errors_updated: int


# --- Pasos ---


def backfill(
    session: Session, client: ReeClient | None = None, full: bool = False, today: date | None = None
) -> BackfillResult:
    """Descarga de REE lo que falta desde lo último guardado (o todo, con `full`)."""
    today = today or local_today()
    history_start = get_settings().history_start
    client = client or ReeClient()

    last_price = repository.last_price_datetime(session)
    start = local_date(last_price) if last_price and not full else history_start
    prices_changed = dataset.save_prices(session, prices.fetch_pvpc(start, today + timedelta(days=1), client))

    last_generation = repository.last_generation_date(session)
    start = last_generation if last_generation and not full else history_start
    generation_changed = dataset.save_generation(session, generation.fetch_generation(start, today, client))

    last_price = repository.last_price_datetime(session)
    result = BackfillResult(prices_changed, generation_changed, local_date(last_price) if last_price else None)
    logger.info(
        "Ingesta: %d horas de PVPC y %d filas de generación nuevas o cambiadas; último día con precio: %s",
        result.prices_changed,
        result.generation_changed,
        result.last_price_day,
    )
    return result


def train(session: Session, metrics_days: int | None = None) -> str:
    """Entrena con el histórico guardado y guarda el modelo. Devuelve su versión."""
    kwargs = {"metrics_days": metrics_days} if metrics_days else {}
    artifact = train_final_model(dataset.load_clean_prices(session), **kwargs)
    save_to_db(session, artifact)
    logger.info("Modelo %s guardado en la base de datos", artifact.metadata.version)
    return artifact.metadata.version


def forecast_next_day(session: Session, day: date | None = None) -> Forecast:
    """Previsión del día indicado o del primero sin precio publicado, con el modelo guardado."""
    last_price = repository.last_price_datetime(session)
    if last_price is None:
        raise ValueError("No hay precios en la base de datos: ejecuta make backfill")
    day = day or local_date(last_price) + timedelta(days=1)
    since = local_day_hours(day)[0] - timedelta(days=HISTORY_DAYS + 1)
    history = dataset.load_clean_prices(session, since=since)
    return predict_day(history, day=day, load=lambda: load_from_db(session))


def save_forecast(session: Session, forecast: Forecast) -> int:
    """Guarda la previsión como ejecución nueva, salvo que repita la última de ese día.

    Si la última ejecución del día tiene el mismo modelo, versión y valores (por
    ejemplo, al repetir la tarea diaria), no se duplica: se devuelve esa.
    """
    hours = list(zip(forecast.prices.index.to_pydatetime(), forecast.prices.astype(float), strict=True))
    latest = repository.latest_forecast(session, forecast.day)
    if latest is not None and _same_forecast(latest, forecast.model, forecast.model_version, hours):
        logger.info("La previsión del %s no ha cambiado: se mantiene la ejecución %d", forecast.day, latest.id)
        return latest.id

    run = repository.save_forecast(
        session,
        repository.ForecastToSave(
            target_day=forecast.day,
            generated_at=forecast.generated_at,
            model=forecast.model,
            model_version=forecast.model_version,
            fallback_reason=forecast.fallback_reason,
            hours=hours,
        ),
    )
    return run.id


def _same_forecast(run, model: str, model_version: str | None, hours: list[tuple[datetime, float]]) -> bool:
    saved = [(h.datetime, h.prediction) for h in run.hours]
    return (
        (run.model, run.model_version) == (model, model_version)
        and [ts for ts, _ in saved] == [ts for ts, _ in hours]
        and all(abs(a - b) < 1e-6 for (_, a), (_, b) in zip(saved, hours, strict=True))
    )


def update_daily_errors(session: Session, last_day: date, days: int = ERROR_DAYS) -> int:
    """Error de la última previsión de cada uno de los últimos `days` días publicados."""
    rows = []
    for offset in range(days):
        day = last_day - timedelta(days=offset)
        run = repository.latest_forecast(session, day)
        if run is None:
            continue
        hours = local_day_hours(day)
        real = dict(repository.get_prices(session, start=hours[0], end=hours[-1] + timedelta(hours=1)))
        evaluated = [h for h in run.hours if h.datetime in real]
        if not evaluated:
            continue
        metrics = regression_metrics(
            pd.Series([real[h.datetime] for h in evaluated]), pd.Series([h.prediction for h in evaluated])
        )
        rows.append((day, run.model, metrics["mae"], metrics["rmse"], metrics["bias"], metrics["n"]))
    return repository.upsert_daily_errors(session, rows)


def daily(
    client: ReeClient | None = None,
    today: date | None = None,
    session_factory: Callable[[], object] = session_scope,
) -> DailyResult:
    """La tarea diaria. Cada paso va en su propia transacción."""
    today = today or local_today()
    with session_factory() as session:
        ingest = backfill(session, client=client, today=today)

    with session_factory() as session:
        forecast = forecast_next_day(session)
        run_id = save_forecast(session, forecast)

    with session_factory() as session:
        errors = update_daily_errors(session, ingest.last_price_day) if ingest.last_price_day else 0

    tomorrow = today + timedelta(days=1)
    status = "completo" if ingest.last_price_day and ingest.last_price_day >= tomorrow else "pendiente"
    if status == "pendiente":
        logger.warning("REE aún no ha publicado el PVPC del %s: se prevé ese día y se reintentará más tarde", tomorrow)
    return DailyResult(status, ingest, forecast, run_id, errors)


# --- Línea de comandos ---


def _print_forecast(forecast: Forecast) -> None:
    source = f"{forecast.model} {forecast.model_version}" if forecast.model_version else forecast.model
    print(f"\nPrevisión del PVPC para el {forecast.day:%d/%m/%Y} ({source})")
    if forecast.used_fallback:
        print(f"Respaldo activado: {forecast.fallback_reason}")
    table = forecast_table(forecast)
    print(table.to_string(index=False, formatters={"€/MWh": "{:.1f}".format, "€/kWh": "{:.3f}".format}))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    backfill_cmd = commands.add_parser("backfill", help="descarga de REE lo que falta")
    backfill_cmd.add_argument("--full", action="store_true", help="descarga todo el histórico de nuevo")
    train_cmd = commands.add_parser("train", help="entrena y guarda el modelo")
    train_cmd.add_argument("--metrics-days", type=int, help="días recientes para medir el modelo")
    commands.add_parser("daily", help="ingesta, previsión y error diario")
    predict_cmd = commands.add_parser("predict", help="muestra la previsión sin guardarla")
    predict_cmd.add_argument("--day", type=date.fromisoformat, help="día local a predecir (AAAA-MM-DD)")
    args = parser.parse_args(argv)

    configure_logging()
    started = datetime.now()
    if args.command == "backfill":
        with session_scope() as session:
            backfill(session, full=args.full)
    elif args.command == "train":
        with session_scope() as session:
            train(session, metrics_days=args.metrics_days)
    elif args.command == "predict":
        with session_scope() as session:
            _print_forecast(forecast_next_day(session, args.day))
    else:
        result = daily()
        _print_forecast(result.forecast)
        print(f"\nEstado: {result.status} · ejecución {result.run_id}", end=" · ")
        print(f"errores diarios actualizados: {result.errors_updated}")
    logger.info("Terminado en %.1f s", (datetime.now() - started).total_seconds())


if __name__ == "__main__":
    main()

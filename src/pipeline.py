"""Pipeline de datos y modelo sobre PostgreSQL.

Uso:
    python -m src.pipeline backfill [--full]   # descarga de REE lo que falta y lo guarda
    python -m src.pipeline train               # entrena y guarda el modelo en la base de datos
    python -m src.pipeline daily               # la tarea diaria: ingesta, previsión y error diario
    python -m src.pipeline predict             # muestra la previsión del siguiente día (sin guardar)

La tarea diaria es idempotente: se puede repetir (por ejemplo, el reintento de
las 21:30 UTC) sin duplicar datos ni previsiones. Si REE aún no ha publicado los precios de
mañana, termina como "pendiente".

En GitHub Actions, `daily` y `train` dejan además un resumen en la página de la
ejecución; `daily`, también su estado como salida del paso (`status`), para los pasos
siguientes del workflow.

Con `daily --notify`, la tarea envía el resumen de mañana al tema privado de ntfy del
desarrollador una sola vez al día: cuando llegan por primera vez los precios de REE o, si en el último
intento (`--last-attempt`) aún no han llegado, con la previsión.
"""

import argparse
import logging
import os
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
from src.models.predict import Forecast, predict_day, print_forecast
from src.models.registry import load_from_db, save_to_db
from src.models.train import train_final_model
from src.notifications import ntfy
from src.processing import dataset
from src.processing.features import HISTORY_DAYS
from src.services.digest import Digest, build_digest
from src.utils.calendar import local_date, local_day_hours, market_timezone
from src.utils.config import get_settings
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)

# Días ya publicados cuyo error se recalcula en cada ejecución (por si REE corrige algún precio)
ERROR_DAYS = 7
# Modelos que conservan su binario (el resto, solo los metadatos): cuatro semanas para volver atrás
KEEP_MODEL_BINARIES = 4


@dataclass(frozen=True)
class BackfillResult:
    prices_changed: int
    generation_changed: int
    last_price_day: date | None
    previous_last_price_day: date | None = None  # el último día con precio antes de esta ingesta


@dataclass(frozen=True)
class DailyResult:
    status: str  # "completo" o "pendiente" (REE aún no ha publicado mañana)
    backfill: BackfillResult
    forecast: Forecast
    run_id: int
    errors_updated: int
    today: date | None = None  # día local en que se ejecutó

    @property
    def tomorrow_just_published(self) -> bool:
        """Si los precios de mañana han llegado en esta ejecución (y no en una anterior)."""
        tomorrow = self.today + timedelta(days=1)
        before, after = self.backfill.previous_last_price_day, self.backfill.last_price_day
        return after is not None and after >= tomorrow and (before is None or before < tomorrow)


# --- Pasos ---


def backfill(
    session: Session, client: ReeClient | None = None, full: bool = False, today: date | None = None
) -> BackfillResult:
    """Descarga de REE lo que falta desde lo último guardado (o todo, con `full`)."""
    today = today or local_today()
    history_start = get_settings().history_start
    client = client or ReeClient()

    last_price = repository.last_price_datetime(session)
    previous_last_day = local_date(last_price) if last_price else None
    start = local_date(last_price) if last_price and not full else history_start
    prices_changed = dataset.save_prices(session, prices.fetch_pvpc(start, today + timedelta(days=1), client))

    last_generation = repository.last_generation_date(session)
    start = last_generation if last_generation and not full else history_start
    generation_changed = dataset.save_generation(session, generation.fetch_generation(start, today, client))

    last_price = repository.last_price_datetime(session)
    result = BackfillResult(
        prices_changed, generation_changed, local_date(last_price) if last_price else None, previous_last_day
    )
    logger.info(
        "Ingesta: %d horas de PVPC y %d filas de generación nuevas o cambiadas; último día con precio: %s",
        result.prices_changed,
        result.generation_changed,
        result.last_price_day,
    )
    return result


def train(session: Session, metrics_days: int | None = None) -> str:
    """Entrena con el histórico guardado y guarda el modelo. Devuelve su versión.

    Los modelos antiguos conservan sus metadatos pero pierden el binario (ver `KEEP_MODEL_BINARIES`).
    """
    kwargs = {"metrics_days": metrics_days} if metrics_days else {}
    artifact = train_final_model(dataset.load_clean_prices(session), **kwargs)
    save_to_db(session, artifact)
    logger.info("Modelo %s guardado en la base de datos", artifact.metadata.version)
    pruned = repository.prune_model_binaries(session, keep=KEEP_MODEL_BINARIES)
    if pruned:
        logger.info("Borrado el binario de %d modelos antiguos (se conservan sus metadatos)", pruned)
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
    hours = _hours_to_save(forecast)
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


def _hours_to_save(forecast: Forecast) -> list[repository.HourToSave]:
    index = forecast.prices.index
    no_bound = [None] * len(index)
    lower = forecast.lower.reindex(index).astype(float).tolist() if forecast.lower is not None else no_bound
    upper = forecast.upper.reindex(index).astype(float).tolist() if forecast.upper is not None else no_bound
    return [
        repository.HourToSave(*hour)
        for hour in zip(index.to_pydatetime(), forecast.prices.astype(float), lower, upper, strict=True)
    ]


def _same_value(a: float | None, b: float | None) -> bool:
    return a is None and b is None or (a is not None and b is not None and abs(a - b) < 1e-6)


def _same_forecast(run, model: str, model_version: str | None, hours: list[repository.HourToSave]) -> bool:
    saved = [repository.HourToSave(h.datetime, h.prediction, h.lower, h.upper) for h in run.hours]
    return (
        (run.model, run.model_version) == (model, model_version)
        and [h.datetime for h in saved] == [h.datetime for h in hours]
        and all(
            _same_value(getattr(a, field), getattr(b, field))
            for a, b in zip(saved, hours, strict=True)
            for field in ("prediction", "lower", "upper")
        )
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
    return DailyResult(status, ingest, forecast, run_id, errors, today)


# --- Resumen diario por ntfy ---


def _day_prices(session: Session, day: date) -> list[tuple[datetime, float]]:
    hours = local_day_hours(day)
    return repository.get_prices(session, start=hours[0], end=hours[-1] + timedelta(hours=1))


def daily_digest(session: Session, result: DailyResult, last_attempt: bool = False) -> Digest | None:
    """El resumen de mañana que toca enviar tras esta ejecución, o None si no toca.

    - Si los precios de mañana acaban de llegar: con los precios de REE.
    - Si en el último intento del día aún no han llegado: con la previsión.
    - En cualquier otro caso (p. ej. el reintento después de un día completo), nada:
      así se envía una sola vez al día.
    """
    tomorrow = result.today + timedelta(days=1)
    today_prices = _day_prices(session, result.today)
    if result.tomorrow_just_published:
        return build_digest(_day_prices(session, tomorrow), tomorrow, "published", previous_day_prices=today_prices)
    if result.status == "pendiente" and last_attempt and result.forecast.day == tomorrow:
        predicted = result.forecast.prices
        forecast = list(zip(predicted.index.to_pydatetime(), predicted.astype(float), strict=True))
        return build_digest(forecast, tomorrow, "forecast", result.forecast.model, previous_day_prices=today_prices)
    return None


def send_digest(digest: Digest) -> str:
    """Publica el resumen en el tema privado de ntfy. Devuelve el id del mensaje."""
    settings = get_settings()
    if not settings.ntfy_topic:
        raise ValueError("Falta NTFY_TOPIC: el tema de ntfy al que enviar el resumen")
    return ntfy.publish(settings.ntfy_server, settings.ntfy_topic, digest.title, digest.body, click=settings.site_url)


def notify(result: DailyResult, last_attempt: bool, session_factory: Callable[[], object] = session_scope) -> str:
    """Envía el resumen si toca y devuelve qué ha pasado, para el log y el resumen de GitHub.

    Un fallo de ntfy no hace fallar la tarea: los datos ya están guardados.
    """
    with session_factory() as session:
        digest = daily_digest(session, result, last_attempt)
    if digest is None:
        return "No toca enviar el resumen (ya se envió hoy o REE aún puede publicar)"
    try:
        message_id = send_digest(digest)
    except Exception as exc:
        logger.error("No se pudo enviar el resumen a ntfy: %s: %s", type(exc).__name__, exc)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning::No se pudo enviar el resumen a ntfy ({type(exc).__name__}: {exc})")
        return f"No se pudo enviar el resumen ({type(exc).__name__})"
    kind = "precios de REE" if digest.source == "published" else "previsión"
    logger.info("Resumen del %s enviado a ntfy (%s, id %s)", digest.day, kind, message_id)
    return f"Resumen del {digest.day:%d/%m/%Y} enviado a ntfy ({kind})"


# --- Línea de comandos ---


def _hour_range(ts: pd.Timestamp) -> str:
    tz = market_timezone()
    return f"{ts.tz_convert(tz):%H}–{(ts + pd.Timedelta(hours=1)).tz_convert(tz):%H} h"


def _mwh(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " €/MWh"


def github_summary(result: DailyResult) -> str:
    """Resumen en Markdown de la tarea diaria, para la página de la ejecución en GitHub."""
    forecast = result.forecast
    cheapest, priciest = forecast.prices.idxmin(), forecast.prices.idxmax()
    model = f"{forecast.model} {forecast.model_version}" if forecast.model_version else forecast.model
    status = "completo" if result.status == "completo" else "pendiente: REE aún no ha publicado mañana"
    last_day = result.backfill.last_price_day
    rows = [
        ("Último día con precio", f"{last_day:%d/%m/%Y}" if last_day else "ninguno"),
        ("Horas de PVPC nuevas o corregidas", str(result.backfill.prices_changed)),
        ("Previsión", f"{forecast.day:%d/%m/%Y} ({len(forecast.prices)} h) · ejecución {result.run_id}"),
        ("Modelo", model),
        ("Media prevista", _mwh(forecast.prices.mean())),
        ("Hora más barata", f"{_hour_range(cheapest)} · {_mwh(forecast.prices[cheapest])}"),
        ("Hora más cara", f"{_hour_range(priciest)} · {_mwh(forecast.prices[priciest])}"),
        ("Errores diarios actualizados", str(result.errors_updated)),
    ]
    lines = [f"### Tarea diaria · {status}", "", "| | |", "|---|---|", *(f"| {k} | {v} |" for k, v in rows)]
    if forecast.used_fallback:
        lines += ["", f"> Respaldo activado: {forecast.fallback_reason}"]
    return "\n".join(lines) + "\n"


def training_summary(version: str, metrics: dict) -> str:
    """Resumen en Markdown del entrenamiento: error frente a las referencias y cobertura del intervalo."""
    period, models = metrics["period"], metrics["models"]
    lines = [
        f"### Modelo {version}",
        "",
        f"Backtest de los últimos {period['days']} días ({period['start']} – {period['end']}), €/MWh:",
        "",
        "| Modelo | Error medio | RMSE | Sesgo |",
        "|---|---|---|---|",
        *(
            f"| {name} | {_mwh(m['mae'])} | {_mwh(m['rmse'])} | {_mwh(m['bias'])} |"
            for name, m in sorted(models.items(), key=lambda item: item[1]["mae"])
        ),
    ]
    if interval := metrics.get("interval"):
        coverage = f"{interval['coverage']:.1%}".replace(".", ",")
        lines += ["", f"Intervalo del {interval['level']:.0%}: el precio real cayó dentro el {coverage} de las horas."]
    return "\n".join(lines) + "\n"


def beats_baselines(metrics: dict) -> bool:
    models = metrics["models"]
    return all(models["lightgbm"]["mae"] < m["mae"] for name, m in models.items() if name != "lightgbm")


def _append_to_github(variable: str, text: str) -> None:
    """Escribe en el fichero de una variable de GitHub Actions; fuera de Actions no hace nada."""
    if path := os.environ.get(variable):
        with open(path, "a", encoding="utf-8") as file:
            file.write(text)


def report_to_github(result: DailyResult) -> None:
    _append_to_github("GITHUB_STEP_SUMMARY", github_summary(result))
    _append_to_github("GITHUB_OUTPUT", f"status={result.status}\nforecast_day={result.forecast.day.isoformat()}\n")


def report_training_to_github(version: str, metrics: dict) -> None:
    _append_to_github("GITHUB_STEP_SUMMARY", training_summary(version, metrics))
    if os.environ.get("GITHUB_ACTIONS") and not beats_baselines(metrics):
        # Anotación amarilla en la ejecución: el modelo se guarda igual, pero conviene revisarlo
        print(f"::warning::El modelo {version} no mejora a todas las referencias en el backtest: revisa sus métricas")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    backfill_cmd = commands.add_parser("backfill", help="descarga de REE lo que falta")
    backfill_cmd.add_argument("--full", action="store_true", help="descarga todo el histórico de nuevo")
    train_cmd = commands.add_parser("train", help="entrena y guarda el modelo")
    train_cmd.add_argument("--metrics-days", type=int, help="días recientes para medir el modelo")
    daily_cmd = commands.add_parser("daily", help="ingesta, previsión y error diario")
    daily_cmd.add_argument("--notify", action="store_true", help="envía el resumen de mañana a ntfy si toca")
    daily_cmd.add_argument(
        "--last-attempt", action="store_true", help="último intento del día: sin precios de REE, envía la previsión"
    )
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
            version = train(session, metrics_days=args.metrics_days)
            saved = repository.get_model_artifact(session, version, include_data=False)
            report_training_to_github(version, saved.metrics)
    elif args.command == "predict":
        with session_scope() as session:
            print_forecast(forecast_next_day(session, args.day))
    else:
        result = daily()
        report_to_github(result)
        if args.notify:
            notified = notify(result, args.last_attempt)
            print(notified)
            _append_to_github("GITHUB_STEP_SUMMARY", f"\n{notified}.\n")
        print_forecast(result.forecast)
        print(f"\nEstado: {result.status} · ejecución {result.run_id}", end=" · ")
        print(f"errores diarios actualizados: {result.errors_updated}")
    logger.info("Terminado en %.1f s", (datetime.now() - started).total_seconds())


if __name__ == "__main__":
    main()

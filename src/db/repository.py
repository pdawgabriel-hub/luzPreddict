"""Lectura y escritura en la base de datos.

Las escrituras son idempotentes: guardar los mismos datos dos veces deja la base
igual que una sola vez, así que la tarea diaria se puede reintentar sin miedo.
Precios y generación usan `INSERT ... ON CONFLICT DO UPDATE` y solo modifican
las filas cuyo valor cambia; las funciones devuelven cuántas filas eran nuevas
o distintas.

Sin pandas: recibe y devuelve tuplas y objetos de los modelos.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import islice
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from src.db.models import DailyError, ForecastHour, GenerationDay, ModelArtifact, ModelRun, PriceHour

# Filas por sentencia: PostgreSQL admite como mucho 65 535 parámetros por consulta
BATCH_SIZE = 5_000


def _batches(rows: Iterable[Any], size: int = BATCH_SIZE) -> Iterator[list[Any]]:
    iterator = iter(rows)
    while batch := list(islice(iterator, size)):
        yield batch


def _last_per_key(rows: Iterable[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    """Una fila por clave, la última que aparece. Fechas del mismo instante cuentan como la misma clave."""
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        unique[tuple(row[k] for k in keys)] = row
    return list(unique.values())


def _upsert(session: Session, model: Any, rows: Iterable[dict[str, Any]], keys: list[str], values: list[str]) -> int:
    """Inserta o actualiza filas; solo cuenta (y toca) las que son nuevas o cambian.

    Si la tabla tiene `updated_at` o `computed_at`, se pone al momento actual en
    las filas que cambian. Si una clave se repite en la entrada, gana el último
    valor (PostgreSQL rechaza actualizar la misma fila dos veces en una sentencia).
    """
    touched = next((c for c in ("updated_at", "computed_at") if c in model.__table__.c), None)
    changed = 0
    for batch in _batches(_last_per_key(rows, keys)):
        statement = insert(model).values(batch)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=keys,
            set_={
                **{v: excluded[v] for v in values},
                **({touched: func.now()} if touched else {}),
            },
            where=func.row(*(model.__table__.c[v] for v in values)).is_distinct_from(
                func.row(*(excluded[v] for v in values))
            ),
        )
        # RETURNING solo devuelve las filas insertadas o actualizadas: el recuento es fiable
        # (rowcount no lo es con INSERT de varias filas a través del ORM)
        changed += len(session.execute(statement.returning(model.__table__.c[keys[0]])).all())
    return changed


# --- Precios ---


def upsert_prices(session: Session, rows: Iterable[tuple[datetime, float]]) -> int:
    """Guarda precios horarios (inicio de la hora con zona horaria, €/MWh)."""
    return _upsert(
        session, PriceHour, ({"datetime": ts, "price": price} for ts, price in rows), ["datetime"], ["price"]
    )


def get_prices(
    session: Session, start: datetime | None = None, end: datetime | None = None
) -> list[tuple[datetime, float]]:
    """Precios con `start <= datetime < end`, ordenados, con las horas en UTC."""
    query = select(PriceHour.datetime, PriceHour.price).order_by(PriceHour.datetime)
    if start is not None:
        query = query.where(PriceHour.datetime >= start)
    if end is not None:
        query = query.where(PriceHour.datetime < end)
    return [(ts, price) for ts, price in session.execute(query)]


def last_price_datetime(session: Session) -> datetime | None:
    return session.scalar(select(func.max(PriceHour.datetime)))


# --- Generación ---


def upsert_generation(session: Session, rows: Iterable[tuple[date, str, float]]) -> int:
    """Guarda la generación diaria (día local, tecnología, MWh)."""
    records = ({"date": day, "technology": tech, "mwh": mwh} for day, tech, mwh in rows)
    return _upsert(session, GenerationDay, records, ["date", "technology"], ["mwh"])


def get_generation(
    session: Session, start: date | None = None, end: date | None = None
) -> list[tuple[date, str, float]]:
    """Generación con `start <= date <= end` (días locales, ambos incluidos)."""
    query = select(GenerationDay.date, GenerationDay.technology, GenerationDay.mwh).order_by(
        GenerationDay.date, GenerationDay.technology
    )
    if start is not None:
        query = query.where(GenerationDay.date >= start)
    if end is not None:
        query = query.where(GenerationDay.date <= end)
    return [(day, tech, mwh) for day, tech, mwh in session.execute(query)]


def last_generation_date(session: Session) -> date | None:
    return session.scalar(select(func.max(GenerationDay.date)))


# --- Previsiones ---


@dataclass(frozen=True)
class ForecastToSave:
    target_day: date
    generated_at: datetime
    model: str
    hours: Sequence[tuple[datetime, float]]
    model_version: str | None = None
    fallback_reason: str | None = None


def save_forecast(session: Session, forecast: ForecastToSave) -> ModelRun:
    """Guarda una ejecución de la previsión con sus horas.

    Una ejecución se identifica por (día previsto, momento de generación): si ya
    existe, se actualizan sus datos y sus horas en lugar de duplicarla.
    """
    run_values = {
        "target_day": forecast.target_day,
        "generated_at": forecast.generated_at,
        "model": forecast.model,
        "model_version": forecast.model_version,
        "fallback_reason": forecast.fallback_reason,
    }
    statement = insert(ModelRun).values(run_values)
    statement = statement.on_conflict_do_update(
        index_elements=["target_day", "generated_at"],
        set_={k: statement.excluded[k] for k in ("model", "model_version", "fallback_reason")},
    ).returning(ModelRun.id)
    run_id = session.execute(statement).scalar_one()

    _upsert(
        session,
        ForecastHour,
        ({"run_id": run_id, "datetime": ts, "prediction": value} for ts, value in forecast.hours),
        ["run_id", "datetime"],
        ["prediction"],
    )
    session.expire_all()
    return session.get(ModelRun, run_id, options=[selectinload(ModelRun.hours)])


def latest_forecast(session: Session, target_day: date) -> ModelRun | None:
    """La última previsión generada para un día, con sus horas."""
    query = (
        select(ModelRun)
        .where(ModelRun.target_day == target_day)
        .order_by(ModelRun.generated_at.desc())
        .limit(1)
        .options(selectinload(ModelRun.hours))
    )
    return session.scalars(query).first()


# --- Modelo entrenado ---


@dataclass(frozen=True)
class ArtifactToSave:
    version: str
    trained_at: datetime
    train_start: datetime
    train_end: datetime
    training_rows: int
    features: list[str]
    params: dict[str, Any]
    metrics: dict[str, Any]
    library_versions: dict[str, str]
    format_version: int
    data: bytes  # el modelo serializado


def save_model_artifact(session: Session, artifact: ArtifactToSave) -> None:
    """Guarda el modelo; si ya existe esa versión, la sustituye."""
    values = artifact.__dict__.copy()
    statement = insert(ModelArtifact).values(values)
    # El tipo json de PostgreSQL no admite comparaciones con "=", así que no se filtra por cambios:
    # la misma versión siempre tiene los mismos bytes
    statement = statement.on_conflict_do_update(
        index_elements=["version"], set_={k: statement.excluded[k] for k in values if k != "version"}
    )
    session.execute(statement)


def get_model_artifact(session: Session, version: str | None = None) -> ModelArtifact | None:
    """El modelo de una versión o, sin versión, el entrenado más recientemente."""
    if version is not None:
        return session.get(ModelArtifact, version)
    return session.scalars(select(ModelArtifact).order_by(ModelArtifact.trained_at.desc()).limit(1)).first()


# --- Error diario ---


def upsert_daily_errors(session: Session, rows: Iterable[tuple[date, str, float, float, float, int]]) -> int:
    """Guarda el error de cada día y modelo (día, modelo, MAE, RMSE, sesgo, horas)."""
    records = (
        {"day": day, "model": model, "mae": mae, "rmse": rmse, "bias": bias, "n": n}
        for day, model, mae, rmse, bias, n in rows
    )
    return _upsert(session, DailyError, records, ["day", "model"], ["mae", "rmse", "bias", "n"])


def get_daily_errors(
    session: Session, start: date | None = None, end: date | None = None, model: str | None = None
) -> list[DailyError]:
    """Errores diarios con `start <= day <= end`, ordenados por día y modelo."""
    query = select(DailyError).order_by(DailyError.day, DailyError.model)
    if start is not None:
        query = query.where(DailyError.day >= start)
    if end is not None:
        query = query.where(DailyError.day <= end)
    if model is not None:
        query = query.where(DailyError.model == model)
    return list(session.scalars(query))

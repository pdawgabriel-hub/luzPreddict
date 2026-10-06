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

from src.db.models import ForecastHour, GenerationDay, ModelRun, PriceHour

# Filas por sentencia: PostgreSQL admite como mucho 65 535 parámetros por consulta
BATCH_SIZE = 5_000


def _batches(rows: Iterable[Any], size: int = BATCH_SIZE) -> Iterator[list[Any]]:
    iterator = iter(rows)
    while batch := list(islice(iterator, size)):
        yield batch


def _upsert(session: Session, model: Any, rows: Iterable[dict[str, Any]], keys: list[str], values: list[str]) -> int:
    """Inserta o actualiza filas; solo cuenta (y toca) las que son nuevas o cambian."""
    changed = 0
    for batch in _batches(rows):
        statement = insert(model).values(batch)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=keys,
            set_={
                **{v: excluded[v] for v in values},
                **({"updated_at": func.now()} if "updated_at" in model.__table__.c else {}),
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

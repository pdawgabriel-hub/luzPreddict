"""Tablas de la base de datos (SQLAlchemy 2).

Todas las fechas y horas se guardan en UTC con `UTCDateTime`, que rechaza las
que no tienen zona horaria: PostgreSQL las interpretaría con la zona del
servidor y las desplazaría sin avisar.

Sin pandas: la API importa este módulo y debe seguir siendo ligera.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    TypeDecorator,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Nombres de restricciones predecibles: las migraciones de Alembic dependen de ellos
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator):
    """`timestamptz` que solo acepta datetimes con zona horaria y devuelve UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"Fecha sin zona horaria: {value!r}")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PriceHour(Base):
    """PVPC publicado por REE para cada hora."""

    __tablename__ = "price_hour"

    datetime: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)  # inicio de la hora
    price: Mapped[float] = mapped_column(Float)  # €/MWh
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class GenerationDay(Base):
    """Energía generada por cada tecnología en un día local (sistema nacional)."""

    __tablename__ = "generation_day"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    technology: Mapped[str] = mapped_column(String(64), primary_key=True)
    mwh: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class ModelArtifact(Base):
    """Modelo entrenado (serializado) con sus metadatos."""

    __tablename__ = "model_artifact"

    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    train_start: Mapped[datetime] = mapped_column(UTCDateTime)
    train_end: Mapped[datetime] = mapped_column(UTCDateTime)
    training_rows: Mapped[int] = mapped_column(Integer)
    features: Mapped[list[str]] = mapped_column(JSON)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    library_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    format_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class ModelRun(Base):
    """Una ejecución de la previsión: qué día se predijo, cuándo y con qué modelo."""

    __tablename__ = "model_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_day: Mapped[date] = mapped_column(Date, index=True)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    model: Mapped[str] = mapped_column(String(32))  # "lightgbm" o la referencia usada como respaldo
    model_version: Mapped[str | None] = mapped_column(ForeignKey("model_artifact.version", ondelete="SET NULL"))
    fallback_reason: Mapped[str | None] = mapped_column(Text)

    hours: Mapped[list["ForecastHour"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True, order_by="ForecastHour.datetime"
    )


class ForecastHour(Base):
    """Previsión de una hora dentro de una ejecución."""

    __tablename__ = "forecast_hour"

    run_id: Mapped[int] = mapped_column(ForeignKey("model_run.id", ondelete="CASCADE"), primary_key=True)
    datetime: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)
    prediction: Mapped[float] = mapped_column(Float)  # €/MWh

    run: Mapped[ModelRun] = relationship(back_populates="hours")


class DailyError(Base):
    """Error de la previsión de un día frente al precio real, por modelo."""

    __tablename__ = "daily_error"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    mae: Mapped[float] = mapped_column(Float)
    rmse: Mapped[float] = mapped_column(Float)
    bias: Mapped[float] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())

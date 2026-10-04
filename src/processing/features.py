"""Variables para predecir el PVPC del día siguiente.

Al predecir el día D solo se conoce el precio hasta el final del día D-1 (REE
publica el PVPC de D la víspera). Por eso todas las variables de precio usan
días anteriores a D.

Los retardos se calculan por día local y hora local ("la misma hora de hace k
días"), no contando filas: con `shift(24)` la última hora de un día de 25 horas
apuntaría a la primera hora del propio día, que todavía no se conoce.
"""

from datetime import date

import numpy as np
import pandas as pd

from src.utils.calendar import local_day_hours, market_timezone, national_holidays, tariff_holidays

TARGET = "price"
LAG_DAYS = (1, 2, 3, 7)

CALENDAR_FEATURES = ["hour", "dayofweek", "month", "dayofyear", "is_weekend", "is_holiday", "tariff_period"]
PRICE_FEATURES = [
    *(f"price_lag_{k}d" for k in LAG_DAYS),
    "same_hour_mean_7d",
    "prev_day_mean",
    "prev_day_min",
    "prev_day_max",
    "prev_day_last",
    "prev_7d_mean",
]
FEATURES = CALENDAR_FEATURES + PRICE_FEATURES

# Códigos de `tariff_period` (de más barato a más caro)
TARIFF_PERIOD_CODES = {"valle": 0, "llano": 1, "punta": 2}

# Días de historia que bastan para calcular las variables de un día (la más larga mira 7 días atrás)
HISTORY_DAYS = 10


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Añade las variables a una serie horaria con índice UTC y columna `price`.

    Las filas del día a predecir pueden tener `price` vacío: sus variables solo
    dependen de días anteriores.
    """
    if df.empty:
        return df.reindex(columns=[*df.columns, *FEATURES])

    local = df.index.tz_convert(market_timezone())
    local_day = pd.DatetimeIndex(local.date)  # medianoche del día local, sin zona
    hour = local.hour

    out = df.copy()
    out = out.join(_calendar_features(local_day, hour, df.index))
    out = out.join(_price_features(df[TARGET], local_day, hour, df.index))
    return out


def _calendar_features(local_day: pd.DatetimeIndex, hour: pd.Index, index: pd.DatetimeIndex) -> pd.DataFrame:
    years = range(local_day.year.min(), local_day.year.max() + 1) if len(local_day) else range(0)
    holidays = pd.DatetimeIndex(sorted(d for y in years for d in national_holidays(y)))
    tariff_days = pd.DatetimeIndex(sorted(d for y in years for d in tariff_holidays(y)))

    is_weekend = local_day.dayofweek >= 5
    is_valle_day = is_weekend | local_day.isin(tariff_days)
    is_punta_hour = ((hour >= 10) & (hour < 14)) | ((hour >= 18) & (hour < 22))
    tariff_period = np.select(
        [is_valle_day | (hour < 8), is_punta_hour],
        [TARIFF_PERIOD_CODES["valle"], TARIFF_PERIOD_CODES["punta"]],
        default=TARIFF_PERIOD_CODES["llano"],
    )

    return pd.DataFrame(
        {
            "hour": hour,
            "dayofweek": local_day.dayofweek,
            "month": local_day.month,
            "dayofyear": local_day.dayofyear,
            "is_weekend": is_weekend.astype("int8"),
            "is_holiday": local_day.isin(holidays).astype("int8"),
            "tariff_period": tariff_period.astype("int8"),
        },
        index=index,
    )


def _price_features(
    price: pd.Series, local_day: pd.DatetimeIndex, hour: pd.Index, index: pd.DatetimeIndex
) -> pd.DataFrame:
    # Precio por (día local, hora local). La hora repetida del día de 25 h se promedia.
    by_day_hour = price.groupby([local_day, hour]).mean()

    def same_hour_days_ago(k: int) -> np.ndarray:
        keys = pd.MultiIndex.from_arrays([local_day - pd.Timedelta(days=k), hour])
        return by_day_hour.reindex(keys).to_numpy()

    features = {f"price_lag_{k}d": same_hour_days_ago(k) for k in LAG_DAYS}
    last_week = pd.DataFrame({k: same_hour_days_ago(k) for k in range(1, 8)})
    features["same_hour_mean_7d"] = last_week.mean(axis=1).to_numpy()

    # Estadísticas de cada día local, asignadas al día siguiente
    daily = price.groupby(local_day).agg(["mean", "min", "max", "last"])
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"))
    daily["mean_7d"] = daily["mean"].rolling(7, min_periods=7).mean()
    previous = daily.reindex(local_day - pd.Timedelta(days=1))

    features.update(
        {
            "prev_day_mean": previous["mean"].to_numpy(),
            "prev_day_min": previous["min"].to_numpy(),
            "prev_day_max": previous["max"].to_numpy(),
            "prev_day_last": previous["last"].to_numpy(),
            "prev_7d_mean": previous["mean_7d"].to_numpy(),
        }
    )
    return pd.DataFrame(features, index=index)


def features_for_day(prices: pd.DataFrame, day: date, history_days: int = HISTORY_DAYS) -> pd.DataFrame:
    """Variables de las horas del día local `day` usando solo precios anteriores a ese día.

    Es lo que se conoce al predecir `day`: las horas de ese día entran con el
    precio vacío, aunque `prices` lo tenga. Lo usan el backtest y la previsión.
    """
    day_hours = pd.DatetimeIndex(local_day_hours(day), name="datetime")
    first_hour = day_hours[0]
    known = prices.loc[(prices.index < first_hour) & (prices.index >= first_hour - pd.Timedelta(days=history_days))]
    frame = pd.concat([known[[TARGET]], pd.DataFrame({TARGET: np.nan}, index=day_hours)])
    return build_features(frame).loc[day_hours]

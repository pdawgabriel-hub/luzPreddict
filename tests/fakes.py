"""Dobles de prueba compartidos por varios tests."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.ingestion import generation, prices
from src.ingestion.ree_client import ReePoint
from src.utils.calendar import local_day_hours, market_timezone


class FakeClient:
    """Devuelve una hora de PVPC por cada hora local del rango pedido."""

    def __init__(self, series=prices.PVPC_SERIES, price=100.0):
        self.series = series
        self.price = price
        self.calls = []

    def fetch(self, path, start, end, **kwargs):
        self.calls.append((path, start, end))
        points = []
        day = start
        while day <= end:
            points += [ReePoint(ts, self.price) for ts in local_day_hours(day)]
            day += timedelta(days=1)
        return {self.series: points}


class FakeGenerationClient:
    """Devuelve un valor diario por tecnología (y el total de REE) para cada día pedido."""

    def __init__(self, mwh=None):
        self.mwh = {"Eólica": 100.0, "Nuclear": 50.0} if mwh is None else mwh
        self.calls = []

    def fetch(self, path, start, end, time_trunc="hour", **kwargs):
        self.calls.append((path, start, end, time_trunc))
        series = {name: [] for name in [*self.mwh, generation.TOTAL_SERIES]}
        day = start
        while day <= end:
            midnight = local_day_hours(day)[0]
            for name, value in self.mwh.items():
                series[name].append(ReePoint(midnight, value))
            series[generation.TOTAL_SERIES].append(ReePoint(midnight, sum(self.mwh.values())))
            day += timedelta(days=1)
        return series


# --- Series de precios de prueba ---


def coded_prices(first_day=date(2026, 1, 1), n_days=14):
    """Serie horaria cuyo precio codifica el día y la hora local: día * 100 + hora."""
    rows = []
    for i in range(n_days):
        for ts in local_day_hours(first_day + timedelta(days=i)):
            rows.append((ts, i * 100 + ts.astimezone(market_timezone()).hour))
    index = pd.DatetimeIndex([ts for ts, _ in rows], name="datetime")
    return pd.DataFrame({"price": [float(p) for _, p in rows]}, index=index)


def row(df, day, hour):
    """Fila de un día y hora locales."""
    local = df.index.tz_convert(market_timezone())
    return df[(local.date == day) & (local.hour == hour)].iloc[0]


def synthetic_prices(first_day=date(2026, 1, 1), n_days=70, seed=0):
    """Precio con patrón semanal y horario claro, un nivel que va cambiando y ruido."""
    rng = np.random.default_rng(seed)
    index, values = [], []
    level = 150.0
    for i in range(n_days):
        day = first_day + timedelta(days=i)
        level += rng.normal(0, 3)
        weekend = 0.7 if day.weekday() >= 5 else 1.0
        for ts in local_day_hours(day):
            hour = ts.astimezone(market_timezone()).hour
            shape = 1.4 if 19 <= hour <= 21 else (0.6 if 13 <= hour <= 16 else 1.0)
            index.append(ts)
            values.append(level * weekend * shape + rng.normal(0, 5))
    return pd.DataFrame({"price": values}, index=pd.DatetimeIndex(index, name="datetime"))


class FakeReeClient:
    """Sirve PVPC y generación como la API de REE, con el PVPC publicado hasta `published_until`."""

    def __init__(self, published_until, price=100.0):
        self.published_until = published_until
        self.prices = FakeClient(price=price)
        self.generation = FakeGenerationClient()
        self.calls = []

    def fetch(self, path, start, end, time_trunc="hour", **kwargs):
        self.calls.append((path, start, end))
        if path == prices.PVPC_PATH:
            end = min(end, self.published_until)
            return self.prices.fetch(path, start, end) if start <= end else {}
        return self.generation.fetch(path, start, end, time_trunc)

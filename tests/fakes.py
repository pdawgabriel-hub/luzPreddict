"""Dobles de prueba compartidos por varios tests."""

from datetime import timedelta

from src.ingestion import generation, prices
from src.ingestion.ree_client import ReePoint
from src.utils.calendar import local_day_hours


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

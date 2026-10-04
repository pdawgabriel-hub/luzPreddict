"""Dobles de prueba compartidos por varios tests."""

from datetime import timedelta

from src.ingestion import prices
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

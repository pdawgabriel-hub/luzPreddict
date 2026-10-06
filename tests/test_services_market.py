from datetime import date

import pytest

from src.ingestion import generation
from src.services.market import RENEWABLE_TECHNOLOGIES, daily_mix, is_renewable, period_mix

DAY1, DAY2 = date(2026, 10, 5), date(2026, 10, 6)
ROWS = [
    (DAY2, "Nuclear", 100.0),
    (DAY1, "Eólica", 300.0),
    (DAY1, "Nuclear", 100.0),
    (DAY1, "Ciclo combinado", 100.0),
    (DAY2, "Eólica", 100.0),
    (DAY2, "Solar fotovoltaica", 200.0),
]


def test_ingestion_uses_the_same_technologies():
    assert generation.RENEWABLE_TECHNOLOGIES is RENEWABLE_TECHNOLOGIES


def test_renewables():
    assert is_renewable("Eólica") and is_renewable("Hidráulica")
    assert not is_renewable("Nuclear") and not is_renewable("Ciclo combinado")


def test_daily_mix():
    day1, day2 = daily_mix(ROWS)

    assert day1.day == DAY1
    assert (day1.total_mwh, day1.renewable_mwh, day1.renewable_pct) == (500, 300, 60)
    assert list(day1.mix) == ["Eólica", "Ciclo combinado", "Nuclear"]  # de mayor a menor; con empate, por nombre
    assert day2.renewable_pct == pytest.approx(75)


def test_repeated_rows_count_once():
    [day] = daily_mix([(DAY1, "Eólica", 100.0), (DAY1, "Eólica", 50.0), (DAY1, "Nuclear", 50.0)])
    assert day.total_mwh == 100
    assert day.renewable_pct == 50


def test_day_without_generation_has_no_percentage():
    [day] = daily_mix([(DAY1, "Eólica", 0.0)])
    assert day.renewable_pct is None


def test_period_mix():
    shares = period_mix(daily_mix(ROWS))

    assert [(s.technology, s.mwh) for s in shares] == [
        ("Eólica", 400),
        ("Nuclear", 200),
        ("Solar fotovoltaica", 200),
        ("Ciclo combinado", 100),
    ]
    assert sum(s.pct for s in shares) == pytest.approx(100)
    assert shares[0].pct == pytest.approx(400 / 900 * 100)
    assert [s.renewable for s in shares] == [True, False, True, False]


def test_empty():
    assert daily_mix([]) == []
    assert period_mix([]) == []

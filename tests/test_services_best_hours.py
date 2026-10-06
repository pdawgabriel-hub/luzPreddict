from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.best_hours import Window, best_window, cheapest_hours
from src.utils.calendar import local_day_hours

MADRID = ZoneInfo("Europe/Madrid")
START = datetime(2026, 10, 7, tzinfo=MADRID)  # miércoles, medianoche en Madrid


def day(prices, start=START):
    """Una hora por precio, seguidas, desde `start`."""
    return [(start + timedelta(hours=i), float(p)) for i, p in enumerate(prices)]


# Perfil típico: noche media, mediodía barato y pico de tarde
PROFILE = [
    150,
    140,
    130,
    125,
    120,
    130,
    160,
    200,
    220,
    180,
    150,
    120,
    100,
    90,
    70,
    75,
    95,
    140,
    250,
    300,
    320,
    290,
    200,
    170,
]


def test_best_window_finds_the_cheapest_consecutive_hours():
    window = best_window(day(PROFILE), hours=2)

    assert window == Window(
        start=START.astimezone(UTC) + timedelta(hours=14),
        end=START.astimezone(UTC) + timedelta(hours=16),
        hours=2,
        avg_price=72.5,
    )


def test_one_hour_window_is_the_cheapest_hour():
    assert best_window(day(PROFILE), hours=1).avg_price == 70


def test_whole_day_window_is_the_daily_mean():
    window = best_window(day(PROFILE), hours=24)
    assert window.avg_price == pytest.approx(sum(PROFILE) / 24)
    assert window.start == START.astimezone(UTC)


def test_ties_go_to_the_earliest_window():
    window = best_window(day([5, 1, 9, 1, 9]), hours=1)
    assert window.start == START.astimezone(UTC) + timedelta(hours=1)


def test_windows_never_cross_a_gap_in_the_data():
    prices = day([10, 1, 1, 10, 10]) + day([10, 10], start=START + timedelta(hours=6))
    del prices[2]  # falta la hora 2: las dos horas a 1 €/MWh ya no son seguidas

    window = best_window(prices, hours=2)

    assert window.avg_price == 5.5  # 1 y 10, o 10 y 1, pero nunca 1 y 1
    assert window.end - window.start == timedelta(hours=2)


def test_window_inside_a_time_range():
    prices = day(PROFILE)
    window = best_window(prices, hours=2, not_before=START + timedelta(hours=17), end_by=START + timedelta(hours=24))

    assert window.start == (START + timedelta(hours=22)).astimezone(UTC)  # 22-24 h: 200 y 170
    assert window.avg_price == 185


def test_range_shorter_than_the_window_gives_nothing():
    assert (
        best_window(day(PROFILE), hours=3, not_before=START + timedelta(hours=10), end_by=START + timedelta(hours=12))
        is None
    )


def test_not_enough_hours_gives_nothing():
    assert best_window(day([1, 2]), hours=3) is None
    assert best_window([], hours=1) is None


def test_unsorted_input_and_any_timezone():
    prices = list(reversed(day(PROFILE)))
    in_utc = [(ts.astimezone(UTC), p) for ts, p in day(PROFILE)]

    assert best_window(prices, hours=3) == best_window(in_utc, hours=3)


@pytest.mark.parametrize("day_, n_hours", [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_clock_change_days_are_continuous(day_, n_hours):
    hours = local_day_hours(day_)
    prices = [(ts, 100.0) for ts in hours]

    window = best_window(prices, hours=n_hours)

    assert window is not None
    assert window.end - window.start == timedelta(hours=n_hours)


def test_invalid_arguments():
    with pytest.raises(ValueError, match="al menos 1 hora"):
        best_window(day(PROFILE), hours=0)
    with pytest.raises(ValueError, match="sin zona horaria"):
        best_window([(datetime(2026, 10, 7, 0), 1.0)], hours=1)
    with pytest.raises(ValueError, match="al menos 1 hora"):
        cheapest_hours(day(PROFILE), 0)


# --- Horas sueltas más baratas ---


def test_cheapest_hours_need_not_be_consecutive():
    cheapest = cheapest_hours(day(PROFILE), 4)

    hours_of_day = [(ts - START.astimezone(UTC)) // timedelta(hours=1) for ts, _ in cheapest]
    assert hours_of_day == [14, 15, 13, 16]  # 70, 75, 90, 95
    assert [p for _, p in cheapest] == [70, 75, 90, 95]


def test_cheapest_hours_ties_go_to_the_earliest():
    assert [p for _, p in cheapest_hours(day([3, 1, 2, 1]), 2)] == [1, 1]
    assert cheapest_hours(day([3, 1, 2, 1]), 2)[0][0] == START.astimezone(UTC) + timedelta(hours=1)


def test_asking_for_more_hours_than_there_are():
    assert len(cheapest_hours(day([1, 2, 3]), 10)) == 3

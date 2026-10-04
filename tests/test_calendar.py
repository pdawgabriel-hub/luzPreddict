from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.utils.calendar import (
    TariffPeriod,
    easter_sunday,
    hours_in_day,
    is_national_holiday,
    local_date,
    local_day_hours,
    national_holidays,
    tariff_holidays,
    tariff_period,
)

MADRID = ZoneInfo("Europe/Madrid")


def at(day: str, hour: int) -> datetime:
    """Inicio de una hora local de Madrid."""
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=MADRID)


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 10, 6), 24),
        (date(2026, 3, 29), 23),  # cambio a horario de verano
        (date(2026, 10, 25), 25),  # cambio a horario de invierno
    ],
)
def test_hours_in_day(day, expected):
    assert hours_in_day(day) == expected


@pytest.mark.parametrize("day", [date(2026, 10, 6), date(2026, 3, 29), date(2026, 10, 25)])
def test_local_day_hours_are_consecutive_and_cover_the_day(day):
    hours = local_day_hours(day)
    assert all(h.tzinfo == UTC for h in hours)
    assert hours[0].astimezone(MADRID) == datetime(day.year, day.month, day.day, tzinfo=MADRID)
    assert all(b - a == timedelta(hours=1) for a, b in zip(hours, hours[1:], strict=False))
    next_midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=MADRID)
    assert hours[-1] + timedelta(hours=1) == next_midnight


def test_local_date_crosses_midnight():
    # 22:30 UTC del 31 de julio son las 00:30 del 1 de agosto en Madrid
    assert local_date(datetime(2026, 7, 31, 22, 30, tzinfo=UTC)) == date(2026, 8, 1)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="zona horaria"):
        local_date(datetime(2026, 1, 1, 12))
    with pytest.raises(ValueError, match="zona horaria"):
        tariff_period(datetime(2026, 1, 1, 12))


@pytest.mark.parametrize(
    "year, expected",
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))],
)
def test_easter_sunday(year, expected):
    assert easter_sunday(year) == expected


def test_national_holidays_include_good_friday_but_tariff_holidays_do_not():
    good_friday = date(2026, 4, 3)
    assert good_friday in national_holidays(2026)
    assert good_friday not in tariff_holidays(2026)
    assert len(national_holidays(2026)) == 10
    assert tariff_holidays(2026) == national_holidays(2026) - {good_friday}
    assert is_national_holiday(date(2026, 12, 25))
    assert not is_national_holiday(date(2026, 12, 24))


@pytest.mark.parametrize(
    "hour, expected",
    [
        (0, TariffPeriod.VALLE),
        (7, TariffPeriod.VALLE),
        (8, TariffPeriod.LLANO),
        (9, TariffPeriod.LLANO),
        (10, TariffPeriod.PUNTA),
        (13, TariffPeriod.PUNTA),
        (14, TariffPeriod.LLANO),
        (17, TariffPeriod.LLANO),
        (18, TariffPeriod.PUNTA),
        (21, TariffPeriod.PUNTA),
        (22, TariffPeriod.LLANO),
        (23, TariffPeriod.LLANO),
    ],
)
def test_tariff_period_on_a_weekday(hour, expected):
    assert tariff_period(at("2026-10-06", hour)) == expected  # martes


def test_weekday_has_eight_hours_of_each_period():
    periods = Counter(tariff_period(h) for h in local_day_hours(date(2026, 10, 6)))
    assert periods == {TariffPeriod.PUNTA: 8, TariffPeriod.LLANO: 8, TariffPeriod.VALLE: 8}


@pytest.mark.parametrize(
    "day",
    [
        "2026-10-03",  # sábado
        "2026-10-04",  # domingo
        "2026-10-12",  # lunes festivo de la tarifa
    ],
)
def test_weekends_and_tariff_holidays_are_all_valle(day):
    assert tariff_period(at(day, 12)) == TariffPeriod.VALLE
    assert tariff_period(at(day, 20)) == TariffPeriod.VALLE


def test_good_friday_is_a_normal_weekday_for_the_tariff():
    assert tariff_period(at("2026-04-03", 12)) == TariffPeriod.PUNTA


def test_tariff_period_uses_local_time_for_utc_inputs():
    # 08:30 UTC del martes 6 de octubre son las 10:30 en Madrid (horario de verano)
    assert tariff_period(datetime(2026, 10, 6, 8, 30, tzinfo=UTC)) == TariffPeriod.PUNTA

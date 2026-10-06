from datetime import date, timedelta

import pytest

from src.services.tariffs import PROFILES, Profile, compare_bill
from src.utils.calendar import TariffPeriod, local_day_hours, market_timezone


def period_prices(first_day, n_days, price_of=lambda local: 100.0):
    """Precios horarios (€/MWh) de `n_days` días locales; `price_of` recibe la hora local."""
    rows = []
    for i in range(n_days):
        for ts in local_day_hours(first_day + timedelta(days=i)):
            rows.append((ts, price_of(ts.astimezone(market_timezone()))))
    return rows


WEEK = date(2026, 10, 5)  # lunes 5 a domingo 11 de octubre de 2026
CONSTANT = "constante"


def test_constant_price_cost_is_kwh_times_price():
    bill = compare_bill(period_prices(WEEK, 7), total_kwh=70, profile=CONSTANT)

    assert bill.pvpc_cost == pytest.approx(70 * 0.100)
    assert bill.effective_price == pytest.approx(0.100)
    assert bill.break_even_price == pytest.approx(0.100)
    assert len(bill.days) == 7
    assert all(d.kwh == pytest.approx(10) for d in bill.days)


def test_periods_add_up_to_the_total():
    bill = compare_bill(period_prices(WEEK, 7), total_kwh=70, profile="tipico")

    assert sum(p.kwh for p in bill.periods.values()) == pytest.approx(70)
    assert sum(p.cost for p in bill.periods.values()) == pytest.approx(bill.pvpc_cost)


def test_with_a_flat_profile_periods_follow_the_2_0td_hours():
    # 5 laborables con 8 h de cada tramo y 2 días de fin de semana todo en valle
    bill = compare_bill(period_prices(WEEK, 7), total_kwh=7 * 24, profile=CONSTANT)

    assert bill.periods[TariffPeriod.PUNTA].kwh == pytest.approx(5 * 8)
    assert bill.periods[TariffPeriod.LLANO].kwh == pytest.approx(5 * 8)
    assert bill.periods[TariffPeriod.VALLE].kwh == pytest.approx(5 * 8 + 2 * 24)


def test_period_average_prices():
    expensive_peak = period_prices(
        WEEK, 1, lambda local: 300.0 if (10 <= local.hour < 14 or 18 <= local.hour < 22) else 100.0
    )

    bill = compare_bill(expensive_peak, total_kwh=24, profile=CONSTANT)

    assert bill.periods[TariffPeriod.PUNTA].avg_price == pytest.approx(0.300)
    assert bill.periods[TariffPeriod.VALLE].avg_price == pytest.approx(0.100)


def test_fixed_price_comparison():
    bill = compare_bill(period_prices(WEEK, 7), total_kwh=70, profile=CONSTANT, fixed_price=0.150)

    assert bill.fixed_cost == pytest.approx(70 * 0.150)
    assert bill.fixed_saving == pytest.approx(70 * 0.050)  # con PVPC se ahorran 5 cts por kWh
    assert bill.days_fixed_was_cheaper == 0


def test_days_when_the_fixed_price_was_better():
    # Lunes a miércoles a 200 €/MWh y el resto a 100: un fijo de 0,15 €/kWh gana 3 días
    prices = period_prices(WEEK, 7, lambda local: 200.0 if local.day <= 7 else 100.0)

    bill = compare_bill(prices, total_kwh=70, profile=CONSTANT, fixed_price=0.150)

    assert bill.days_fixed_was_cheaper == 3


def test_without_fixed_price_there_is_no_comparison():
    bill = compare_bill(period_prices(WEEK, 1), total_kwh=10)
    assert bill.fixed_cost is None and bill.fixed_saving is None and bill.days_fixed_was_cheaper is None


def test_shifting_consumption_to_cheap_hours_lowers_the_cost():
    cheap_midday = period_prices(WEEK, 7, lambda local: 50.0 if 13 <= local.hour < 17 else 200.0)

    no_shift = compare_bill(cheap_midday, total_kwh=70, profile="tipico", shift_fraction=0)
    shifted = compare_bill(cheap_midday, total_kwh=70, profile="tipico", shift_fraction=0.3)

    assert no_shift.pvpc_shifted_cost == pytest.approx(no_shift.pvpc_cost)
    assert shifted.pvpc_shifted_cost < shifted.pvpc_cost
    assert shifted.break_even_price < shifted.effective_price


def test_shifting_saves_nothing_when_every_hour_costs_the_same():
    bill = compare_bill(period_prices(WEEK, 7), total_kwh=70, shift_fraction=0.4)
    assert bill.pvpc_shifted_cost == pytest.approx(bill.pvpc_cost)


@pytest.mark.parametrize("day, hours", [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_clock_change_days_consume_the_same_as_any_other_day(day, hours):
    prices = period_prices(day - timedelta(days=1), 3)

    bill = compare_bill(prices, total_kwh=30, profile="tipico")

    assert [d.kwh for d in bill.days] == pytest.approx([10, 10, 10])
    assert len(prices) == 24 + hours + 24


def test_profiles_are_well_formed():
    assert set(PROFILES) == {"tipico", "teletrabajo", "coche_noche", "constante"}
    for profile in PROFILES.values():
        assert len(profile.weights) == 24
        assert all(w > 0 for w in profile.weights)


def test_custom_profile():
    only_nights = Profile("noche", "Noche", "Solo de 0 a 8 h", tuple(1.0 if h < 8 else 1e-9 for h in range(24)))
    prices = period_prices(WEEK, 1, lambda local: 50.0 if local.hour < 8 else 300.0)

    bill = compare_bill(prices, total_kwh=10, profile=only_nights)

    assert bill.effective_price == pytest.approx(0.050, abs=1e-6)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"total_kwh": 0}, "consumo debe ser positivo"),
        ({"total_kwh": 10, "shift_fraction": 1.5}, "entre 0 y 1"),
        ({"total_kwh": 10, "fixed_price": -0.1}, "precio fijo debe ser positivo"),
    ],
)
def test_invalid_arguments(kwargs, message):
    with pytest.raises(ValueError, match=message):
        compare_bill(period_prices(WEEK, 1), **kwargs)


def test_no_prices():
    with pytest.raises(ValueError, match="No hay precios"):
        compare_bill([], total_kwh=10)

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.simulator import APPLIANCES, Appliance, simulate, simulate_all, total_yearly_saving
from src.utils.calendar import local_day_hours

MADRID = ZoneInfo("Europe/Madrid")
DAY = date(2026, 10, 7)
# €/MWh por hora local: noche media, mediodía barato y pico de tarde
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
PRICES = [(ts, float(p)) for ts, p in zip(local_day_hours(DAY), PROFILE, strict=True)]


def at(hour, day=DAY):
    return datetime(day.year, day.month, day.day, hour, tzinfo=MADRID)


def test_cost_at_the_chosen_hour():
    sim = simulate(PRICES, "lavadora", at(19))  # 0,5 kW a las 19 y 20 h: 300 y 320 €/MWh

    assert sim.cost == pytest.approx(0.5 * (0.300 + 0.320))
    assert sim.start == at(19).astimezone(UTC)


def test_best_hour_and_saving():
    sim = simulate(PRICES, "lavadora", at(19), uses_per_week=4)

    assert sim.best.start == at(14).astimezone(UTC)  # 70 y 75 €/MWh
    assert sim.best_cost == pytest.approx(0.5 * (0.070 + 0.075))
    assert sim.saving_per_use == pytest.approx(0.5 * (0.620 - 0.145))
    assert sim.yearly_saving == pytest.approx(sim.saving_per_use * 4 * 52)


def test_no_saving_when_already_at_the_best_hour():
    sim = simulate(PRICES, "lavadora", at(14))
    assert sim.saving_per_use == 0
    assert sim.yearly_saving == 0


def test_best_hour_respects_the_available_range():
    # Fuera de casa hasta las 18 h y hay que terminar antes de medianoche
    sim = simulate(PRICES, "lavadora", at(19), not_before=at(18), end_by=at(0, DAY + timedelta(days=1)))

    assert sim.best.start == at(22).astimezone(UTC)  # 200 y 170 €/MWh
    assert sim.best.end <= at(0, DAY + timedelta(days=1))


def test_range_too_short_for_the_appliance():
    sim = simulate(PRICES, "coche", at(17), not_before=at(18), end_by=at(21))  # 6 h no caben en 3

    assert sim.best is None
    assert sim.best_cost is None
    assert sim.saving_per_use is None and sim.yearly_saving is None
    assert sim.cost > 0  # el coste a la hora elegida sí se puede calcular


def test_chosen_hour_without_prices_is_an_error():
    with pytest.raises(ValueError, match="No hay precio"):
        simulate(PRICES, "coche", at(21))  # 21-03 h: las horas de después de medianoche no están


def test_simulate_all_moves_long_appliances_so_they_fit():
    results = {s.appliance.id: s for s in simulate_all(PRICES, at(21), uses_per_week=3)}

    assert set(results) == set(APPLIANCES)
    assert results["lavadora"].start == at(21).astimezone(UTC)
    assert results["coche"].start == at(18).astimezone(UTC)  # 6 h que acaban a medianoche


def test_simulate_all_gives_the_same_costs_as_simulate():
    for sim in simulate_all(PRICES, at(19)):
        single = simulate(PRICES, sim.appliance, sim.start)
        assert sim.cost == pytest.approx(single.cost)
        assert sim.best_cost == pytest.approx(single.best_cost)


def test_total_yearly_saving_adds_every_appliance():
    sims = simulate_all(PRICES, at(19), uses_per_week=2)
    assert total_yearly_saving(sims) == pytest.approx(sum(s.yearly_saving for s in sims))


def test_custom_appliance():
    heater = Appliance("termo", "Termo eléctrico", 1.5, 2)
    sim = simulate(PRICES, heater, at(7))
    assert sim.cost == pytest.approx(1.5 * (0.200 + 0.220))
    assert heater.kwh == 3.0


@pytest.mark.parametrize("day, hours", [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_clock_change_days(day, hours):
    prices = [(ts, 100.0) for ts in local_day_hours(day)]

    sim = simulate(prices, "coche", local_day_hours(day)[0])

    assert len(prices) == hours
    assert sim.cost == pytest.approx(3.7 * 6 * 0.100)


def test_catalogue_is_well_formed():
    assert {"lavadora", "lavavajillas", "secadora", "horno", "coche"} == set(APPLIANCES)
    assert APPLIANCES["coche"].kwh == pytest.approx(22.2)


@pytest.mark.parametrize("power, hours", [(0, 2), (-1, 2), (1, 0)])
def test_invalid_appliances(power, hours):
    with pytest.raises(ValueError, match="Aparato no válido"):
        Appliance("x", "x", power, hours)


def test_invalid_arguments():
    with pytest.raises(ValueError, match="negativos"):
        simulate(PRICES, "lavadora", at(19), uses_per_week=-1)
    with pytest.raises(ValueError, match="sin zona horaria"):
        simulate([(datetime(2026, 10, 7, 0), 1.0)], "horno", at(0))

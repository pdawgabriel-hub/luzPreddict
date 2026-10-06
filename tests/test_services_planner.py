from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.services.planner import BASE_LOAD_KW, Task, plan_day
from src.services.simulator import APPLIANCES, Appliance
from src.utils.calendar import local_day_hours

MADRID = ZoneInfo("Europe/Madrid")
DAY = date(2026, 10, 7)
PROFILE = [150, 140, 130, 125, 120, 130, 160, 200, 220, 180, 150, 120]
PROFILE += [100, 90, 70, 75, 95, 140, 250, 300, 320, 290, 200, 170]
PRICES = [(ts, float(p)) for ts, p in zip(local_day_hours(DAY), PROFILE, strict=True)]


def at(hour):
    return datetime(DAY.year, DAY.month, DAY.day, hour, tzinfo=MADRID)


def task(id_, appliance, hour, **kwargs):
    return Task(id_, APPLIANCES[appliance] if isinstance(appliance, str) else appliance, at(hour), **kwargs)


def hour_of(ts):
    return ts.astimezone(MADRID).hour


def test_flexible_tasks_go_to_the_cheapest_hours():
    plan = plan_day(PRICES, [task("lavadora", "lavadora", 20)])

    (lavadora,) = plan.tasks
    assert hour_of(lavadora.start) == 14  # 70 y 75 €/MWh
    assert lavadora.cost == pytest.approx(0.5 * (0.070 + 0.075))
    assert lavadora.habitual_cost == pytest.approx(0.5 * (0.320 + 0.290))
    assert plan.saving == pytest.approx(lavadora.habitual_cost - lavadora.cost)


def test_the_contracted_power_spreads_tasks_apart():
    # Dos aparatos de 2 kW no caben a la vez con 3,45 kW (y 0,4 kW de base)
    heater = Appliance("termo", "Termo", 2.0, 2)
    tasks = [task("termo1", heater, 20), task("termo2", heater, 20)]

    plan = plan_day(PRICES, tasks, power_kw=3.45)

    # El primero ocupa 14-16 h (lo más barato); el segundo, la siguiente ventana sin solaparse: 12-14 h
    assert [hour_of(p.start) for p in plan.tasks] == [14, 12]
    assert max(plan.load.values()) <= 3.45 + 1e-9


def test_with_more_power_they_can_share_the_cheapest_hours():
    heater = Appliance("termo", "Termo", 2.0, 2)
    plan = plan_day(PRICES, [task("termo1", heater, 20), task("termo2", heater, 20)], power_kw=5.75)

    assert [hour_of(p.start) for p in plan.tasks] == [14, 14]


def test_fixed_tasks_stay_and_use_power_first():
    oven = task("horno", "horno", 14, fixed=True)  # cena… a las 14 h, ocupa el hueco barato
    big = Appliance("termo", "Termo", 3.0, 1)

    plan = plan_day(PRICES, [oven, task("termo", big, 20)], power_kw=4.6)

    by_id = {p.task.id: p for p in plan.tasks}
    assert hour_of(by_id["horno"].start) == 14
    assert hour_of(by_id["termo"].start) != 14  # 0,4 + 1,5 + 3,0 > 4,6
    assert hour_of(by_id["termo"].start) == 15


def test_task_that_never_fits_is_left_out():
    too_big = Appliance("horno-industrial", "Horno industrial", 5.0, 1)
    plan = plan_day(PRICES, [task("grande", too_big, 20), task("lavadora", "lavadora", 20)], power_kw=4.6)

    assert [t.id for t in plan.unplaced] == ["grande"]
    assert plan.plan_cost == pytest.approx(next(p.cost for p in plan.tasks if p.task.id == "lavadora"))
    # El ahorro solo compara lo que se ha podido colocar
    lavadora = next(p for p in plan.tasks if p.task.id == "lavadora")
    assert plan.saving == pytest.approx(lavadora.habitual_cost - lavadora.cost)


def test_habitual_schedule_overloads_are_detected():
    tasks = [task("coche", "coche", 18), task("horno", "horno", 20), task("secadora", "secadora", 20)]

    plan = plan_day(PRICES, tasks, power_kw=4.6)

    # A las 20 y 21 h: 0,4 + 3,7 + 1,5 (solo a las 20) + 1,2 > 4,6
    assert [hour_of(h) for h in plan.habitual_overloads] == [20, 21]
    assert max(plan.load.values()) <= 4.6 + 1e-9  # el plan no se pasa


def test_loads_include_the_base_consumption():
    plan = plan_day(PRICES, [])
    assert set(plan.load.values()) == {BASE_LOAD_KW}
    assert plan.plan_cost == plan.habitual_cost == plan.saving == 0


def test_habitual_start_is_moved_so_the_task_fits_in_the_day():
    plan = plan_day(PRICES, [task("coche", "coche", 21)])
    assert hour_of(plan.tasks[0].habitual_start) == 18  # 6 h que acaban a medianoche


def test_task_range_is_respected():
    plan = plan_day(PRICES, [task("lavadora", "lavadora", 20, not_before=at(18))])
    assert hour_of(plan.tasks[0].start) == 22  # lo más barato a partir de las 18 h


def test_results_keep_the_input_order_and_are_deterministic():
    tasks = [task("lavadora", "lavadora", 20), task("coche", "coche", 18), task("lavavajillas", "lavavajillas", 22)]
    first = plan_day(PRICES, tasks, power_kw=3.45)
    second = plan_day(PRICES, tasks, power_kw=3.45)

    assert [p.task.id for p in first.tasks] == ["lavadora", "coche", "lavavajillas"]
    assert [p.start for p in first.tasks] == [p.start for p in second.tasks]


@pytest.mark.parametrize("day, hours", [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_clock_change_days(day, hours):
    prices = [(ts, 100.0) for ts in local_day_hours(day)]
    plan = plan_day(prices, [Task("coche", APPLIANCES["coche"], local_day_hours(day)[0])])
    assert len(plan.load) == hours
    assert plan.tasks[0].placed


def test_invalid_arguments():
    with pytest.raises(ValueError, match="debe superar el consumo base"):
        plan_day(PRICES, [], power_kw=0.3)
    with pytest.raises(ValueError, match="mismo id"):
        plan_day(PRICES, [task("a", "horno", 20), task("a", "horno", 21)])
    with pytest.raises(ValueError, match="No hay precios"):
        plan_day([], [])
    with pytest.raises(ValueError, match="sin zona horaria"):
        plan_day([(datetime(2026, 10, 7, 0), 1.0)], [])

"""Casos límite de los servicios: cambios de hora, franjas vacías y tareas que no caben."""

import subprocess
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.best_hours import best_window, cheapest_hours
from src.services.digest import build_digest
from src.services.planner import BASE_LOAD_KW, Task, plan_day
from src.services.simulator import APPLIANCES, Appliance, simulate
from src.services.tariffs import compare_bill
from src.utils.calendar import TariffPeriod, local_day_hours

MADRID = ZoneInfo("Europe/Madrid")
AUTUMN = date(2026, 10, 25)  # 25 horas: la 2:00 se repite
SPRING = date(2026, 3, 29)  # 23 horas: no hay 2:00


def hours_of(*days, price=100.0):
    return [(ts, price) for d in days for ts in local_day_hours(d)]


def local(day, hour, fold=0):
    return datetime(day.year, day.month, day.day, hour, tzinfo=MADRID, fold=fold)


# --- La API no debe cargar pandas ---


@pytest.mark.parametrize(
    "module",
    [
        "src.services.best_hours",
        "src.services.tariffs",
        "src.services.simulator",
        "src.services.planner",
        "src.services.digest",
        "src.db.models",
        "src.db.repository",
        "src.db.session",
    ],
)
def test_services_and_db_do_not_import_pandas(module):
    """La API los importa y debe seguir siendo ligera para Vercel."""
    code = (
        f"import sys, {module}; heavy = {{'pandas', 'numpy', 'lightgbm', 'sklearn'}} & set(sys.modules); print(heavy)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "set()", f"{module} carga librerías pesadas: {result.stdout.strip()}"


# --- Días de 23 y 25 horas ---


def test_window_across_the_repeated_hour_lasts_its_real_hours():
    prices = [(ts, 10.0 if 1 <= i <= 3 else 100.0) for i, ts in enumerate(local_day_hours(AUTUMN))]

    window = best_window(prices, hours=3)

    assert window.start == local(AUTUMN, 1).astimezone(window.start.tzinfo)
    assert window.end - window.start == timedelta(hours=3)  # 1:00, 2:00 y la 2:00 repetida
    assert window.end == local(AUTUMN, 3).astimezone(window.end.tzinfo)


def test_window_across_midnight_of_the_clock_change():
    prices = hours_of(date(2026, 3, 28), SPRING)
    cheap = {local(date(2026, 3, 28), 23), local(SPRING, 0), local(SPRING, 1)}
    prices = [(ts, 1.0 if ts in cheap else 100.0) for ts, _ in prices]

    window = best_window(prices, hours=3)

    assert window.avg_price == 1.0
    assert window.end == local(SPRING, 3)  # tras la 1:00 viene directamente la 3:00


def test_repeated_hour_is_valle_in_both_occurrences():
    hours = local_day_hours(AUTUMN)
    bill = compare_bill([(ts, 100.0) for ts in hours], total_kwh=25, profile="constante")
    assert bill.periods[TariffPeriod.VALLE].kwh == pytest.approx(25)  # domingo: todo valle


def test_overnight_task_on_the_25_hour_night():
    plan = plan_day(hours_of(AUTUMN), [Task("coche", APPLIANCES["coche"], local(AUTUMN, 0))], power_kw=4.6)

    coche = plan.tasks[0]
    assert coche.placed
    # 6 horas reales: de 0:00 a 5:00 de reloj, porque la 2:00 se repite
    assert coche.start == local(AUTUMN, 0)
    assert coche.cost == pytest.approx(3.7 * 6 * 0.100)


def test_digest_of_a_23_hour_day():
    digest = build_digest(hours_of(SPRING), SPRING, "published")
    assert digest.title.startswith("Luz el domingo 29 de marzo")
    assert "2 h" not in digest.body.split("·")[0]  # la 2:00 no existe ese día


# --- Franjas vacías ---


def test_inverted_range_gives_no_window():
    assert best_window(hours_of(AUTUMN), 1, not_before=local(AUTUMN, 20), end_by=local(AUTUMN, 10)) is None


def test_range_outside_the_data_gives_no_window():
    next_week = local(AUTUMN, 0) + timedelta(days=7)
    assert best_window(hours_of(AUTUMN), 1, not_before=next_week) is None
    assert best_window(hours_of(AUTUMN), 1, end_by=local(AUTUMN, 0)) is None


def test_range_exactly_as_long_as_the_task():
    window = best_window(hours_of(AUTUMN), 2, not_before=local(AUTUMN, 10), end_by=local(AUTUMN, 12))
    assert window.start == local(AUTUMN, 10)


def test_simulation_and_plan_with_an_empty_range():
    prices = hours_of(date(2026, 10, 7))
    start = local(date(2026, 10, 7), 20)
    sim = simulate(prices, "lavadora", start, not_before=start, end_by=start)
    plan = plan_day(prices, [Task("lavadora", APPLIANCES["lavadora"], start, not_before=start, end_by=start)])

    assert sim.best is None and sim.yearly_saving is None
    assert [t.id for t in plan.unplaced] == ["lavadora"]
    assert plan.saving == 0


# --- Tareas que no caben ---


def test_task_longer_than_the_day():
    marathon = Appliance("maraton", "Carga larguísima", 0.5, 30)
    with pytest.raises(ValueError, match="más largas que el periodo con precios \\(24 h\\): maraton"):
        plan_day(hours_of(date(2026, 10, 7)), [Task("maraton", marathon, local(date(2026, 10, 7), 0))])


def test_habitual_start_before_the_data_is_moved_inside():
    day = date(2026, 10, 7)
    plan = plan_day(hours_of(day), [Task("lavadora", APPLIANCES["lavadora"], local(day, 0) - timedelta(hours=5))])
    assert plan.tasks[0].habitual_start == local(day, 0)


def test_day_full_of_fixed_tasks_leaves_no_room():
    day = date(2026, 10, 7)
    always_on = Appliance("calefaccion", "Calefacción", 4.0, 24)
    tasks = [
        Task("calefaccion", always_on, local(day, 0), fixed=True),
        Task("horno", APPLIANCES["horno"], local(day, 20)),
    ]

    plan = plan_day(hours_of(day), tasks, power_kw=4.6)

    assert [t.id for t in plan.unplaced] == ["horno"]
    assert len(plan.habitual_overloads) == 1  # el horno a las 20 h haría saltar el limitador


def test_power_exactly_at_the_limit_is_allowed():
    exact = Appliance("exacto", "Justo al límite", 4.6 - BASE_LOAD_KW, 1)
    plan = plan_day(hours_of(date(2026, 10, 7)), [Task("exacto", exact, local(date(2026, 10, 7), 20))], power_kw=4.6)
    assert plan.tasks[0].placed
    assert plan.habitual_overloads == []


# --- Datos con horas repetidas ---


def test_duplicated_hours_are_counted_once():
    """Si una hora llega dos veces, cuenta una sola vez (gana el último valor)."""
    day = date(2026, 10, 7)
    prices = hours_of(day) + [(local(day, 14), 5.0)]

    cheapest = cheapest_hours(prices, 3)

    assert len({ts for ts, _ in cheapest}) == 3  # sin repetir la misma hora
    assert cheapest[0] == (local(day, 14), 5.0)
    assert best_window(prices, 24).avg_price == pytest.approx((23 * 100 + 5) / 24)


def test_duplicated_hours_are_not_counted_twice_in_the_bill_or_the_digest():
    day = date(2026, 10, 7)
    duplicated = hours_of(day) + [(local(day, 14), 100.0)]

    assert compare_bill(duplicated, total_kwh=24, profile="constante").pvpc_cost == pytest.approx(24 * 0.100)
    assert build_digest(duplicated, day, "published").mean_price == pytest.approx(100.0)

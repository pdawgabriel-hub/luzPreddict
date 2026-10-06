from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.digest import build_digest, kwh
from src.utils.calendar import local_day_hours

MADRID = ZoneInfo("Europe/Madrid")
DAY = date(2026, 10, 7)  # miércoles
PROFILE = [150, 140, 130, 125, 120, 130, 160, 200, 220, 180, 150, 120]
PROFILE += [100, 90, 70, 75, 95, 140, 250, 300, 320, 290, 200, 170]
PRICES = [(ts, float(p)) for ts, p in zip(local_day_hours(DAY), PROFILE, strict=True)]


def flat(day, price):
    return [(ts, price) for ts in local_day_hours(day)]


def test_forecast_digest_text():
    digest = build_digest(PRICES, DAY, "forecast", model="lightgbm")

    assert digest.title == f"Luz el miércoles 7 de octubre: media {kwh(sum(PROFILE) / 24)} €/kWh"
    assert digest.body.splitlines() == [
        "Más barata: 14–16 h (0,073 €/kWh)",
        "Más cara: 19–21 h (0,310 €/kWh)",
        "Mejores horas: 14 h, 15 h, 13 h · Evita: 20 h, 19 h, 21 h",
        "Previsión de luzPreddict (LightGBM).",
    ]
    assert digest.text == f"{digest.title}\n{digest.body}"


def test_structured_fields():
    digest = build_digest(PRICES, DAY, "forecast", model="lightgbm")

    assert digest.mean_price == pytest.approx(sum(PROFILE) / 24)
    assert digest.cheapest_window.avg_price == pytest.approx(72.5)
    assert digest.priciest_window.avg_price == pytest.approx(310)
    assert digest.cheapest_hours[0] == datetime(2026, 10, 7, 14, tzinfo=MADRID).astimezone(UTC)
    assert len(digest.priciest_hours) == 3


def test_published_prices_say_so():
    assert build_digest(PRICES, DAY, "published").body.endswith("Precios publicados por REE.")


def test_fallback_forecast_says_so():
    digest = build_digest(PRICES, DAY, "forecast", model="precio_ayer")
    assert digest.body.endswith('Previsión de luzPreddict (respaldo "precio de ayer").')


@pytest.mark.parametrize(
    "previous_price, expected",
    [
        (100.0, "Un 70 % más cara que el día anterior."),  # media del día: 170 €/MWh
        (200.0, "Un 15 % más barata que el día anterior."),
        (170.0, "Similar al día anterior."),
    ],
)
def test_comparison_with_the_previous_day(previous_price, expected):
    previous = flat(DAY - timedelta(days=1), previous_price)
    today = flat(DAY, 170.0)

    digest = build_digest(today, DAY, "forecast", model="lightgbm", previous_day_prices=previous)

    assert expected in digest.body.splitlines()
    assert digest.change_vs_previous == pytest.approx(170 / previous_price - 1)


def test_without_the_previous_day_there_is_no_comparison():
    digest = build_digest(PRICES, DAY, "forecast", model="lightgbm")
    assert digest.change_vs_previous is None
    assert "día anterior" not in digest.body


def test_negative_prices_are_shown():
    prices = [(ts, -10.0 if i == 14 else 100.0) for i, ts in enumerate(local_day_hours(DAY))]
    digest = build_digest(prices, DAY, "published")
    assert "Mejores horas: 14 h" in digest.body
    assert kwh(-10) == "-0,010"


def test_25_hour_day():
    digest = build_digest(flat(date(2026, 10, 25), 100.0), date(2026, 10, 25), "published")
    assert digest.title == "Luz el domingo 25 de octubre: media 0,100 €/kWh"


def test_short_enough_for_a_notification():
    assert len(build_digest(PRICES, DAY, "forecast", model="lightgbm").text) < 300


def test_invalid_arguments():
    with pytest.raises(ValueError, match="Fuente desconocida"):
        build_digest(PRICES, DAY, "rumor")
    with pytest.raises(ValueError, match="No hay precios"):
        build_digest([], DAY, "published")


@pytest.mark.parametrize("price, text", [(72.5, "0,073"), (186.4, "0,186"), (0.0, "0,000"), (954.01, "0,954")])
def test_kwh_formatting_rounds_half_up(price, text):
    assert kwh(price) == text

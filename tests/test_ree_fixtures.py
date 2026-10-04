"""Tests con respuestas reales de REE guardadas en tests/fixtures.

Comprueban que el cliente y los módulos de PVPC y generación entienden el
formato real de la API, incluidos los días de 23 y 25 horas.
Para regenerar las respuestas: python -m tests.fixtures.update_fixtures
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.ingestion import generation, prices
from src.ingestion.ree_client import ReeApiError, ReeClient, parse_series

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def client_for(name):
    """Cliente cuya sesión responde siempre con la respuesta guardada."""
    fixture = load_fixture(name)
    response = MagicMock()
    response.status_code = fixture["status"]
    response.ok = fixture["status"] < 400
    response.json.return_value = fixture["body"]
    session = MagicMock()
    session.get.return_value = response
    return ReeClient(session=session)


def assert_continuous_hours(df):
    assert df["datetime"].diff().dropna().eq(pd.Timedelta(hours=1)).all()


# --- PVPC ---


def test_pvpc_on_the_day_clocks_go_back_has_25_hours():
    df = prices.fetch_pvpc(date(2025, 10, 25), date(2025, 10, 26), client=client_for("pvpc_2025-10-25_26"))

    assert len(df) == 24 + 25
    assert df["datetime"].iloc[0] == datetime(2025, 10, 24, 22, tzinfo=UTC)  # 00:00 del 25 en Madrid
    assert df["datetime"].iloc[-1] == datetime(2025, 10, 26, 22, tzinfo=UTC)  # 23:00 del 26 en Madrid
    assert_continuous_hours(df)


def test_pvpc_on_the_day_clocks_go_forward_has_23_hours():
    df = prices.fetch_pvpc(date(2026, 3, 29), date(2026, 3, 29), client=client_for("pvpc_2026-03-29"))

    assert len(df) == 23
    assert_continuous_hours(df)


def test_pvpc_prices_are_plausible():
    df = prices.fetch_pvpc(date(2025, 10, 25), date(2025, 10, 26), client=client_for("pvpc_2025-10-25_26"))

    assert df["price"].notna().all()
    assert df["price"].between(-50, 1000).all()  # €/MWh


def test_pvpc_response_also_brings_the_quarter_hourly_spot_price():
    # Desde octubre de 2025 el mercado diario va en tramos de 15 minutos; el PVPC sigue siendo horario
    series = parse_series(load_fixture("pvpc_2025-10-25_26")["body"])

    spot = series["Precio mercado spot"]
    assert len(spot) == 4 * len(series["PVPC"])
    assert spot[1].datetime - spot[0].datetime == timedelta(minutes=15)


# --- Generación ---


def test_generation_has_one_row_per_local_day_and_technology():
    df = generation.fetch_generation(
        date(2026, 9, 28), date(2026, 10, 3), client=client_for("generation_2026-09-28_10-03")
    )

    assert sorted(df["date"].unique()) == [date(2026, 9, 28) + timedelta(days=i) for i in range(6)]
    assert generation.TOTAL_SERIES not in set(df["technology"])
    assert {"Eólica", "Solar fotovoltaica", "Nuclear", "Ciclo combinado"} <= set(df["technology"])
    assert not df.duplicated(["date", "technology"]).any()


def test_generation_technologies_add_up_to_ree_total():
    fixture = load_fixture("generation_2026-09-28_10-03")
    ree_total = {
        datetime.fromisoformat(v["datetime"]).date(): v["value"]
        for item in fixture["body"]["included"]
        if item["type"] == generation.TOTAL_SERIES
        for v in item["attributes"]["values"]
    }

    df = generation.fetch_generation(
        date(2026, 9, 28), date(2026, 10, 3), client=client_for("generation_2026-09-28_10-03")
    )
    our_total = df.groupby("date")["mwh"].sum()

    for day, total in ree_total.items():
        assert our_total[day] == pytest.approx(total)


# --- Errores ---


def test_range_too_long_raises_with_ree_message():
    # REE responde 400 con un mensaje engañoso ("inténtelo más tarde"): reintentar no serviría
    with pytest.raises(ReeApiError, match="400: Los datos solicitados no están disponibles"):
        client_for("error_range_too_long").fetch("x", date(2026, 8, 1), date(2026, 8, 1))

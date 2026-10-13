from datetime import timedelta

import pytest

from src.api.cache import seconds_until_refresh
from src.api.deps import MAX_HISTORY_DAYS
from src.api.routers.web.model import build_backtest
from src.db import repository
from tests.api_helpers import METRICS, NOW, TODAY, make_client, save_artifact

# --- Backtest ---


def test_backtest_is_sorted_and_compared_with_the_best_baseline():
    backtest = build_backtest(METRICS)

    assert [m.model for m in backtest.models] == ["lightgbm", "media_7_dias", "precio_ayer"]
    assert [m.label for m in backtest.models] == ["LightGBM", "Media 7 días", "Precio de ayer"]
    assert [m.is_baseline for m in backtest.models] == [False, True, True]
    assert backtest.improvement_pct == round((32.45 - 21.93) / 32.45 * 100, 1)
    assert backtest.days == 90
    assert backtest.method.startswith("Walk-forward")


def test_model_worse_than_a_baseline_gives_a_negative_improvement():
    metrics = {
        **METRICS,
        "models": {
            "lightgbm": {"mae": 40.0, "rmse": 1, "bias": 0},
            "precio_ayer": {**METRICS["models"]["precio_ayer"]},
        },
    }
    backtest = build_backtest(metrics)

    assert backtest.models[0].model == "precio_ayer"
    assert backtest.improvement_pct < 0


@pytest.mark.parametrize("metrics", [{}, {"period": METRICS["period"]}, {"models": METRICS["models"]}])
def test_models_without_metrics_have_no_backtest(metrics):
    assert build_backtest(metrics) is None


def test_models_trained_before_the_interval_have_none():
    metrics = {k: v for k, v in METRICS.items() if k != "interval"}
    assert build_backtest(metrics).interval is None


def test_only_baselines_gives_no_improvement():
    metrics = {**METRICS, "models": {"precio_ayer": METRICS["models"]["precio_ayer"]}}
    assert build_backtest(metrics).improvement_pct is None


# --- Ruta ---


@pytest.fixture
def client(db_session):
    return make_client(db_session)


def test_no_model_is_a_404(client):
    response = client.get("/api/model")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Todavía no hay ningún modelo entrenado"


def test_model_report(client, db_session):
    save_artifact(db_session)
    repository.upsert_daily_errors(
        db_session,
        [
            (TODAY - timedelta(days=40), "lightgbm", 99.0, 99.0, 0.0, 24),  # fuera de los 30 días
            (TODAY - timedelta(days=2), "lightgbm", 20.0, 25.0, -1.0, 24),
            (TODAY - timedelta(days=1), "precio_ayer", 30.004, 40.0, 2.0, 24),
        ],
    )

    response = client.get("/api/model")
    body = response.json()

    assert body["model"]["version"] == "20261006-172844"
    assert body["model"]["features"] == ["hour", "price_lag_1d"]
    assert body["model"]["params"]["objective"] == "l1"
    assert body["model"]["trained_at"].endswith("+02:00")
    assert "data" not in body["model"]
    assert body["backtest"]["improvement_pct"] == 32.4
    assert body["backtest"]["interval"] == {"level": 0.8, "coverage": 0.795, "width": 54.83}
    assert (body["live"]["start"], body["live"]["end"]) == ("2026-09-08", "2026-10-07")
    assert [d["date"] for d in body["live"]["days"]] == ["2026-10-04", "2026-10-05"]
    assert body["live"]["days"][1] == {
        "date": "2026-10-05",
        "model": "precio_ayer",
        "mae": 30.0,
        "rmse": 40.0,
        "bias": 2.0,
    }
    assert body["live"]["mae"] == 25.0
    assert body["live"]["fallback_days"] == 1
    seconds = seconds_until_refresh(NOW)
    assert response.headers["cache-control"] == f"public, max-age={seconds}, s-maxage={seconds}"


def test_model_without_metrics_or_errors(client, db_session):
    save_artifact(db_session, metrics={})

    body = client.get("/api/model", params={"days": 7}).json()

    assert body["backtest"] is None
    assert body["live"] == {"start": "2026-10-01", "end": "2026-10-07", "days": [], "mae": None, "fallback_days": 0}


@pytest.mark.parametrize("days", [0, MAX_HISTORY_DAYS + 1])
def test_days_out_of_range(client, days):
    response = client.get("/api/model", params={"days": days})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "query.days"


def test_model_is_documented(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/model"]["get"]
    assert operation["tags"] == ["Previsión"]
    assert {"404", "422", "500"} <= set(operation["responses"])

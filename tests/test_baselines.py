from datetime import date

import numpy as np
import pytest

from src.models.baselines import BASELINES, predict_baseline
from src.processing.features import build_features
from tests.fakes import coded_prices, row


@pytest.fixture
def features():
    return build_features(coded_prices(n_days=14))


def test_available_baselines():
    assert set(BASELINES) == {"precio_ayer", "media_7_dias"}


def test_yesterday_baseline_is_the_same_hour_of_the_previous_day(features):
    prediction = predict_baseline("precio_ayer", features)
    assert prediction[row(features, date(2026, 1, 11), 18).name] == 9 * 100 + 18


def test_week_mean_baseline_is_the_mean_of_that_hour_in_the_last_7_days(features):
    prediction = predict_baseline("media_7_dias", features)
    expected = sum(d * 100 + 18 for d in range(3, 10)) / 7
    assert prediction[row(features, date(2026, 1, 11), 18).name] == pytest.approx(expected)


def test_missing_main_value_falls_back_to_the_next_source():
    # El 30 de marzo a las 2:00 no hay "precio de ayer": el 29 no tuvo 2:00
    features = build_features(coded_prices(first_day=date(2026, 3, 20), n_days=12))
    target = row(features, date(2026, 3, 30), 2)
    assert np.isnan(target["price_lag_1d"])

    prediction = predict_baseline("precio_ayer", features)

    assert prediction[target.name] == pytest.approx(target["same_hour_mean_7d"])


def test_baselines_predict_every_hour_once_there_is_history(features):
    for name in BASELINES:
        assert predict_baseline(name, features).iloc[24:].notna().all()


def test_unknown_baseline():
    with pytest.raises(KeyError, match="Referencia desconocida: magia"):
        predict_baseline("magia", build_features(coded_prices(n_days=2)))

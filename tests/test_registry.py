import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime

import joblib
import pandas as pd
import pytest

from src.models import lightgbm_model, train
from src.models.lightgbm_model import LightGBMForecaster
from src.models.registry import (
    FORMAT_VERSION,
    METADATA_FILENAME,
    MODEL_FILENAME,
    IncompatibleModelError,
    ModelArtifact,
    ModelMetadata,
    build_metadata,
    deserialize,
    load_artifact,
    save_artifact,
    serialize,
)
from src.processing.features import FEATURES, build_features
from tests.fakes import synthetic_prices

FAST = {"n_estimators": 30, "learning_rate": 0.1}
TRAINED_AT = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def features():
    return build_features(synthetic_prices(n_days=40))


@pytest.fixture(scope="module")
def artifact(features):
    model = LightGBMForecaster(params=FAST, train_days=None)
    model.fit(features)
    metrics = {"models": {"lightgbm": {"mae": 10.0}}}
    return ModelArtifact(model=model, metadata=build_metadata(model, metrics=metrics, trained_at=TRAINED_AT))


def test_metadata_describes_the_trained_model(artifact, features):
    meta = artifact.metadata
    trained_on = features.dropna(subset=["price"]).index

    assert meta.version == "20261005-193000"
    assert meta.trained_at == TRAINED_AT
    assert meta.train_start == trained_on.min()
    assert meta.train_end == trained_on.max()
    assert meta.training_rows == len(trained_on)
    assert meta.features == FEATURES
    assert meta.params["n_estimators"] == 30
    assert meta.metrics == {"models": {"lightgbm": {"mae": 10.0}}}
    assert {"python", "lightgbm", "pandas"} <= set(meta.library_versions)
    assert meta.format_version == FORMAT_VERSION


def test_metadata_is_json_friendly(artifact):
    as_json = json.dumps(artifact.metadata.to_dict())
    assert ModelMetadata.from_dict(json.loads(as_json)) == artifact.metadata


def test_roundtrip_keeps_predictions_and_metadata(artifact, features):
    restored = deserialize(serialize(artifact))

    assert restored.metadata == artifact.metadata
    pd.testing.assert_series_equal(restored.model.predict(features), artifact.model.predict(features))


def test_serialized_model_is_compact(artifact):
    assert len(serialize(artifact)) < 1_000_000


def test_rejects_a_model_trained_with_other_features(artifact):
    with pytest.raises(IncompatibleModelError, match="sobran \\['price_lag_7d'\\]"):
        deserialize(serialize(artifact), expected_features=[f for f in FEATURES if f != "price_lag_7d"])


def test_rejects_an_unknown_format_version(artifact):
    buffer = io.BytesIO()
    payload = {"model": artifact.model, "metadata": {**artifact.metadata.to_dict(), "format_version": 999}}
    joblib.dump(payload, buffer)

    with pytest.raises(IncompatibleModelError, match="Formato 999"):
        deserialize(buffer.getvalue())


def test_save_and_load(artifact, tmp_path, features):
    path = save_artifact(artifact, tmp_path)

    assert path == tmp_path / MODEL_FILENAME
    metadata_file = json.loads((tmp_path / METADATA_FILENAME).read_text(encoding="utf-8"))
    assert metadata_file["version"] == "20261005-193000"
    loaded = load_artifact(tmp_path)
    pd.testing.assert_series_equal(loaded.model.predict(features), artifact.model.predict(features))


def test_load_without_a_saved_model(tmp_path):
    with pytest.raises(FileNotFoundError, match="make train"):
        load_artifact(tmp_path)


def test_fit_command_trains_and_saves_with_metrics(monkeypatch, tmp_path, capsys):
    prices = synthetic_prices(n_days=45)
    monkeypatch.setattr(train, "load_pvpc", lambda: prices.reset_index())
    monkeypatch.setattr(lightgbm_model, "DEFAULT_PARAMS", {**lightgbm_model.DEFAULT_PARAMS, **FAST})

    train.main(["fit", "--output", str(tmp_path), "--metrics-days", "7"])

    meta = load_artifact(tmp_path).metadata
    assert meta.metrics["period"]["days"] == 7
    assert set(meta.metrics["models"]) == {"lightgbm", "precio_ayer", "media_7_dias"}
    assert "guardado en" in capsys.readouterr().out


def test_metrics_period_is_shortened_when_there_is_little_history(monkeypatch):
    monkeypatch.setattr(lightgbm_model, "DEFAULT_PARAMS", {**lightgbm_model.DEFAULT_PARAMS, **FAST})
    prices = synthetic_prices(n_days=20)

    artifact = train.train_final_model(prices, metrics_days=90)

    assert artifact.metadata.metrics["period"]["days"] == 20 - train.MIN_HISTORY_DAYS


def test_too_little_history_is_rejected():
    with pytest.raises(ValueError, match="al menos"):
        train.train_final_model(synthetic_prices(n_days=5))


def test_model_saved_by_the_cli_loads_from_another_program(tmp_path):
    """Al ejecutar `python -m src.models.train`, el modelo debe poder cargarse fuera de ese proceso."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    synthetic_prices(n_days=30).reset_index().to_parquet(raw_dir / "pvpc.parquet", index=False)
    models_dir = tmp_path / "models"

    subprocess.run(
        [sys.executable, "-m", "src.models.train", "fit", "--output", str(models_dir), "--metrics-days", "3"],
        check=True,
        capture_output=True,
        env={**os.environ, "DATA_DIR": str(tmp_path / "data")},
    )

    loaded = load_artifact(models_dir)
    assert type(loaded.model).__module__ == "src.models.lightgbm_model"
    assert loaded.model.predict(build_features(synthetic_prices(n_days=10))).notna().any()

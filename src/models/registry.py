"""Serialización del modelo entrenado junto con sus metadatos.

El modelo se convierte en bytes (joblib comprimido) para poder guardarlo en un
fichero o, más adelante, en la base de datos. Los metadatos permiten saber qué
modelo es, con qué datos se entrenó y cómo de bien funciona, y comprobar al
cargarlo que sigue siendo compatible con las variables actuales.

Solo se deben cargar modelos generados por este proyecto: joblib (pickle)
ejecuta código al deserializar.
"""

import io
import json
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import lightgbm
import pandas as pd

from src.processing.features import FEATURES
from src.utils.config import get_settings

FORMAT_VERSION = 1
MODEL_FILENAME = "lightgbm.joblib"
METADATA_FILENAME = "lightgbm.json"


class IncompatibleModelError(RuntimeError):
    """El modelo guardado no se puede usar con el código actual."""


@dataclass(frozen=True)
class ModelMetadata:
    version: str  # p. ej. "20261005-193000"
    trained_at: datetime  # UTC
    train_start: datetime  # primera hora con precio usada para entrenar (UTC)
    train_end: datetime  # última hora con precio usada para entrenar (UTC)
    training_rows: int
    features: list[str]
    params: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    library_versions: dict[str, str] = field(default_factory=dict)
    format_version: int = FORMAT_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("trained_at", "train_start", "train_end"):
            data[key] = data[key].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelMetadata":
        data = dict(data)
        for key in ("trained_at", "train_start", "train_end"):
            data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


@dataclass(frozen=True)
class ModelArtifact:
    model: Any  # un forecaster entrenado (p. ej. LightGBMForecaster)
    metadata: ModelMetadata


def build_metadata(
    model: Any, metrics: dict[str, Any] | None = None, trained_at: datetime | None = None
) -> ModelMetadata:
    """Metadatos de un LightGBMForecaster recién entrenado."""
    trained_at = trained_at or pd.Timestamp.now(tz="UTC").to_pydatetime()
    return ModelMetadata(
        version=trained_at.strftime("%Y%m%d-%H%M%S"),
        trained_at=trained_at,
        train_start=model.train_start_.to_pydatetime(),
        train_end=model.train_end_.to_pydatetime(),
        training_rows=model.training_rows_,
        features=list(model.features),
        params=dict(model.params),
        metrics=metrics or {},
        library_versions={
            "python": platform.python_version(),
            "lightgbm": lightgbm.__version__,
            "pandas": pd.__version__,
        },
    )


def serialize(artifact: ModelArtifact) -> bytes:
    buffer = io.BytesIO()
    joblib.dump({"model": artifact.model, "metadata": artifact.metadata.to_dict()}, buffer, compress=3)
    return buffer.getvalue()


def deserialize(data: bytes, expected_features: list[str] = FEATURES) -> ModelArtifact:
    """Reconstruye el artefacto y comprueba que es compatible con el código actual."""
    payload = joblib.load(io.BytesIO(data))
    metadata = ModelMetadata.from_dict(payload["metadata"])
    if metadata.format_version != FORMAT_VERSION:
        raise IncompatibleModelError(
            f"Formato {metadata.format_version} no compatible (se espera {FORMAT_VERSION}): vuelve a entrenar"
        )
    if metadata.features != list(expected_features):
        missing = sorted(set(expected_features) - set(metadata.features))
        extra = sorted(set(metadata.features) - set(expected_features))
        raise IncompatibleModelError(
            "Las variables del modelo no coinciden con las actuales "
            f"(faltan {missing}, sobran {extra}): vuelve a entrenar"
        )
    return ModelArtifact(model=payload["model"], metadata=metadata)


def default_dir() -> Path:
    return get_settings().models_dir


def save_artifact(artifact: ModelArtifact, directory: Path | None = None) -> Path:
    """Guarda el modelo y un JSON legible con sus metadatos. Devuelve la ruta del modelo."""
    directory = directory or default_dir()
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / MODEL_FILENAME
    model_path.write_bytes(serialize(artifact))
    (directory / METADATA_FILENAME).write_text(
        json.dumps(artifact.metadata.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return model_path


def load_artifact(directory: Path | None = None) -> ModelArtifact:
    path = (directory or default_dir()) / MODEL_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"No hay modelo guardado en {path}: ejecuta make train")
    return deserialize(path.read_bytes())

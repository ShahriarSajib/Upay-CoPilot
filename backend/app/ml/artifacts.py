"""Model persistence.

Trained models live in ``backend/artifacts`` as joblib bundles. Each bundle
carries its own metadata (training window, feature list, metrics) so a served
prediction can always say which model version produced it -- the explanation
layer quotes that back to the customer.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.core.config import settings


@dataclass
class ModelCard:
    """What a served model must be able to say about itself."""

    name: str
    task: str
    trained_at: str
    train_window: str
    validation_window: str
    features: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    baselines: dict[str, dict[str, float]] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def artifacts_path(name: str) -> Path:
    directory = settings.artifacts_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.joblib"


def save_bundle(name: str, payload: dict[str, Any]) -> Path:
    path = artifacts_path(name)
    joblib.dump(payload, path, compress=3)
    return path


def load_bundle(name: str) -> dict[str, Any] | None:
    path = artifacts_path(name)
    if not path.exists():
        return None
    return joblib.load(path)


def bundle_exists(name: str) -> bool:
    return artifacts_path(name).exists()


def list_cards() -> list[dict[str, Any]]:
    """Every trained model's card, for the /api/models endpoint."""
    cards = []
    for path in sorted(settings.artifacts_dir.glob("*.card.json")):
        cards.append(json.loads(path.read_text(encoding="utf-8")))
    return cards


def save_card(name: str, card: ModelCard) -> Path:
    path = artifacts_path(name).with_suffix(".card.json")
    path.write_text(json.dumps(card.to_dict(), indent=2), encoding="utf-8")
    return path


def safe_float(value: Any) -> float:
    """Coerce anything (numpy, nan, None) into a JSON-safe float."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if out != out or out in (float("inf"), float("-inf")):
        return float("nan")
    return out


def json_safe(value: Any) -> Any:
    """Recursively convert numpy/pandas values into JSON-serialisable Python."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return safe_float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float):
        return safe_float(value)
    return value

"""Shared pytest fixtures.

Run from the backend folder:  python -m pytest -v

Test categories
- Always run (no dataset, no trained model, no internet): almost everything.
- Uses a SMALL SYNTHETIC FIXTURE MODEL built inside the test (random numbers, three fake
  crop classes). It only proves the predict/validation/API code path works. It is NOT the
  real dataset and its predictions mean nothing agronomically.
- Needs the REAL downloaded dataset + trained model: tests marked `real_model`
  (skipped automatically until you run train_model.py).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import train_model  # noqa: E402
import weather_service  # noqa: E402
from app import create_app  # noqa: E402
from predict import FEATURES  # noqa: E402

REAL_MODEL = BACKEND_DIR / "models" / "crop_model.joblib"
REAL_DATASET = BACKEND_DIR / "data" / "Crop_recommendation.csv"


def make_synthetic_dataframe(rows_per_class=40, seed=0):
    """Tiny made-up data with three well-separated fake classes (test fixture only)."""
    rng = np.random.default_rng(seed)
    centres = {
        "cropa": [90, 40, 40, 25, 80, 6.5, 200],
        "cropb": [20, 60, 20, 18, 50, 7.0, 70],
        "cropc": [50, 20, 80, 30, 60, 5.5, 120],
    }
    frames = []
    for label, centre in centres.items():
        data = rng.normal(centre, [5, 5, 5, 1.5, 4, 0.2, 10], size=(rows_per_class, 7))
        frame = pd.DataFrame(data, columns=FEATURES)
        frame["label"] = label
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df[["N", "P", "K"]] = df[["N", "P", "K"]].clip(lower=0)
    df["humidity"] = df["humidity"].clip(0, 100)
    df["ph"] = df["ph"].clip(0, 14)
    df["rainfall"] = df["rainfall"].clip(lower=0)
    return df


@pytest.fixture(autouse=True)
def _clear_weather_cache():
    weather_service.clear_cache()
    yield
    weather_service.clear_cache()


@pytest.fixture
def synthetic_model_path(tmp_path):
    df, _ = train_model.clean_dataframe(make_synthetic_dataframe())
    bundle, report = train_model.train_from_dataframe(df, n_estimators=25)
    path = tmp_path / "fixture_model.joblib"
    train_model.save_bundle(bundle, report, path)
    return path


@pytest.fixture
def client(synthetic_model_path, tmp_path):
    """App with a synthetic fixture model; dataset path points at a missing file."""
    app = create_app({
        "TESTING": True,
        "MODEL_PATH": str(synthetic_model_path),
        "DATASET_PATH": str(tmp_path / "missing.csv"),
    })
    return app.test_client()


@pytest.fixture
def no_model_client(tmp_path):
    app = create_app({
        "TESTING": True,
        "MODEL_PATH": str(tmp_path / "nope.joblib"),
        "DATASET_PATH": str(tmp_path / "missing.csv"),
    })
    return app.test_client()


SOIL_PAYLOAD = {
    "mode": "soil", "N": 90, "P": 42, "K": 43,
    "temperature": 25.5, "humidity": 80, "ph": 6.5, "rainfall": 200,
}

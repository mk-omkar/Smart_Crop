"""Train the Random Forest crop classifier (used by soil-informed Mode A).

Usage (from the backend folder):
    python train_model.py
    python train_model.py --data data/Crop_recommendation.csv --output models/crop_model.joblib

Fails with a clear message if the dataset is missing or invalid. All reported metrics are
measured on a held-out test split; nothing is hardcoded.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support
from sklearn.model_selection import train_test_split

from predict import FEATURES, SOIL_SPECS

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = BASE_DIR / "data" / "Crop_recommendation.csv"
DEFAULT_MODEL = BASE_DIR / "models" / "crop_model.joblib"

REQUIRED_COLUMNS = FEATURES + ["label"]
MIN_ROWS = 50
RANDOM_STATE = 42


class DatasetError(Exception):
    """Dataset missing, unreadable or unusable."""


def clean_dataframe(df):
    """Keep required columns, coerce to numbers, drop unusable rows. Returns (df, dropped)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetError(
            f"Dataset is missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}."
        )

    df = df[REQUIRED_COLUMNS].copy()
    for feature in FEATURES:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")
    df["label"] = df["label"].astype("string").str.strip().str.lower()
    df = df.replace([np.inf, -np.inf], np.nan)

    before = len(df)
    df = df.dropna()
    df = df[df["label"] != ""]
    for feature in FEATURES:  # drop physically implausible rows (e.g. negative N, pH > 14)
        spec = SOIL_SPECS[feature]
        df = df[(df[feature] >= spec.minimum) & (df[feature] <= spec.maximum)]
    df["label"] = df["label"].astype(str)
    dropped = before - len(df)

    if len(df) < MIN_ROWS:
        raise DatasetError(f"Only {len(df)} usable rows remain after cleaning (need {MIN_ROWS}+).")
    counts = df["label"].value_counts()
    if len(counts) < 2:
        raise DatasetError("The dataset must contain at least two different crop labels.")
    if counts.min() < 2:
        rare = ", ".join(counts[counts < 2].index)
        raise DatasetError(f"Each crop needs at least 2 rows for a stratified split; too few: {rare}.")
    return df.reset_index(drop=True), dropped


def load_dataset(path):
    path = Path(path)
    if not path.is_file():
        raise DatasetError(
            f"Dataset not found at {path}.\n"
            "Download 'Crop_recommendation.csv' from "
            "https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset "
            "and place it in backend/data/ (see backend/data/README.md)."
        )
    try:
        raw = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        raise DatasetError(f"Could not read {path.name} as CSV: {exc}") from exc
    return clean_dataframe(raw)


def train_from_dataframe(df, test_size=0.2, seed=RANDOM_STATE, n_estimators=200):
    """Train + evaluate. Returns (bundle, classification_report_text)."""
    X, y = df[FEATURES], df["label"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )

    model = RandomForestClassifier(n_estimators=n_estimators, random_state=seed, n_jobs=-1)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    p_macro, r_macro, f_macro, _ = precision_recall_fscore_support(
        y_test, predictions, average="macro", zero_division=0
    )
    p_wt, r_wt, f_wt, _ = precision_recall_fscore_support(
        y_test, predictions, average="weighted", zero_division=0
    )
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
        "precision_macro": round(float(p_macro), 4),
        "recall_macro": round(float(r_macro), 4),
        "f1_macro": round(float(f_macro), 4),
        "precision_weighted": round(float(p_wt), 4),
        "recall_weighted": round(float(r_wt), 4),
        "f1_weighted": round(float(f_wt), 4),
        "test_rows": int(len(y_test)),
        "train_rows": int(len(y_train)),
    }
    report = classification_report(y_test, predictions, zero_division=0)

    # Per-crop typical conditions (5th-95th percentile) shown next to predictions.
    profiles = {}
    for crop, group in df.groupby("label"):
        profiles[str(crop)] = {
            f: [round(float(group[f].quantile(0.05)), 1), round(float(group[f].quantile(0.95)), 1)]
            for f in FEATURES
        }

    bundle = {
        "model": model,
        "feature_names": list(FEATURES),
        "classes": [str(c) for c in model.classes_],
        "feature_ranges": {
            f: [round(float(df[f].min()), 2), round(float(df[f].max()), 2)] for f in FEATURES
        },
        "crop_profiles": profiles,
        "metrics": metrics,
        "n_samples": int(len(df)),
        "random_state": seed,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
    }
    return bundle, report


def save_bundle(bundle, report, model_path):
    """Write the joblib model and a human-readable metadata JSON next to it."""
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)

    meta = {k: v for k, v in bundle.items() if k != "model"}
    meta["classification_report"] = report
    meta_path = model_path.with_name(model_path.stem + "_metadata.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train the Smart Crop Advisor model.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Path to Crop_recommendation.csv")
    parser.add_argument("--output", default=str(DEFAULT_MODEL), help="Where to save the model")
    parser.add_argument("--seed", type=int, default=RANDOM_STATE)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--n-estimators", type=int, default=200)
    args = parser.parse_args(argv)

    try:
        df, dropped = load_dataset(args.data)
    except DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    labels = sorted(df["label"].unique())
    print(f"Loaded {len(df)} usable rows from {Path(args.data).name} "
          f"({dropped} dropped as missing/invalid).")
    print(f"Found {len(labels)} crop labels: {', '.join(labels)}")

    bundle, report = train_from_dataframe(df, args.test_size, args.seed, args.n_estimators)
    meta_path = save_bundle(bundle, report, args.output)

    m = bundle["metrics"]
    print(f"\nTrain rows: {m['train_rows']}  Test rows: {m['test_rows']}  Seed: {args.seed}")
    print(f"Test accuracy:        {m['accuracy']:.4f}")
    print(f"Precision (macro):    {m['precision_macro']:.4f}")
    print(f"Recall (macro):       {m['recall_macro']:.4f}")
    print(f"F1-score (macro):     {m['f1_macro']:.4f}")
    print("\nClassification report (held-out test split):\n")
    print(report)
    print(f"Model saved to:    {args.output}")
    print(f"Metadata saved to: {meta_path}")
    print("\nNote: scores are measured on the same dataset's test split and do not "
          "guarantee accuracy on real farms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Mode A: soil-informed crop recommendation using the trained Random Forest model."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from common import DISCLAIMER, FieldSpec, validate_fields

# Order and names MUST match training (see train_model.py).
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]

# Plausible input limits (wider than the training data; out-of-range-for-training
# values are accepted but flagged with a warning).
SOIL_SPECS = {
    "N": FieldSpec("Nitrogen (N)", 0, 300, "(dataset scale)"),
    "P": FieldSpec("Phosphorus (P)", 0, 300, "(dataset scale)"),
    "K": FieldSpec("Potassium (K)", 0, 300, "(dataset scale)"),
    "temperature": FieldSpec("Temperature", -10, 55, "°C"),
    "humidity": FieldSpec("Humidity", 0, 100, "%"),
    "ph": FieldSpec("Soil pH", 0, 14),
    "rainfall": FieldSpec("Rainfall", 0, 1000, "mm"),
}

UNITS = {"N": "dataset scale", "P": "dataset scale", "K": "dataset scale",
         "temperature": "°C", "humidity": "%", "ph": "pH", "rainfall": "mm"}

METHOD = (
    "Machine learning: Random Forest classifier trained on the Crop Recommendation "
    "Dataset using 7 features (N, P, K, temperature, humidity, pH, rainfall)."
)
CONFIDENCE_NOTE = (
    "Scores are the Random Forest's vote shares for each crop. They describe how the "
    "model separates crops in its training data and are not real-world probabilities "
    "that a crop will succeed on your farm."
)


class ModelNotAvailableError(Exception):
    """Model file missing, unreadable or incompatible with this code."""


def load_model_bundle(path):
    """Load and sanity-check the saved model bundle."""
    path = Path(path)
    if not path.is_file():
        raise ModelNotAvailableError(
            f"Model file not found at {path.name}. Download the dataset into backend/data/ "
            "and run `python train_model.py` to create it."
        )
    try:
        bundle = joblib.load(path)
    except Exception as exc:  # noqa: BLE001 - corrupt/incompatible pickle
        raise ModelNotAvailableError(
            "The model file could not be loaded (it may be corrupt or made with a different "
            "scikit-learn version). Re-run `python train_model.py`."
        ) from exc

    if not isinstance(bundle, dict) or "model" not in bundle or "feature_names" not in bundle:
        raise ModelNotAvailableError("The model file has an unexpected format. Re-train the model.")
    if list(bundle["feature_names"]) != FEATURES:
        raise ModelNotAvailableError(
            "The model was trained with different features than this app expects. Re-train it."
        )
    return bundle


def _range_warnings(values, bundle):
    warnings = []
    ranges = bundle.get("feature_ranges") or {}
    for name in FEATURES:
        if name in ranges:
            low, high = ranges[name]
            if values[name] < low or values[name] > high:
                warnings.append(
                    f"{SOIL_SPECS[name].label} = {values[name]:g} is outside the range seen in "
                    f"the training data ({low:g}–{high:g}); the prediction may be unreliable."
                )
    return warnings


def predict_crop(bundle, payload, top_k=3):
    """Validate a soil-mode payload and return a recommendation dict.

    Raises common.ValidationError for missing/invalid values.
    """
    values = validate_fields(payload, SOIL_SPECS, required=FEATURES)

    # Build the frame with the exact training column names and order.
    features = list(bundle["feature_names"])
    frame = pd.DataFrame([[values[f] for f in features]], columns=features)

    model = bundle["model"]
    probabilities = model.predict_proba(frame)[0]
    order = np.argsort(probabilities)[::-1][:top_k]
    top = [
        {"crop": str(model.classes_[i]), "score": round(float(probabilities[i]), 3)}
        for i in order
    ]
    predicted = top[0]["crop"]

    metrics = bundle.get("metrics") or {}
    return {
        "mode": "soil",
        "method_type": "machine_learning",
        "method": METHOD,
        "predicted_crop": predicted,
        "top_predictions": top,
        "confidence_note": CONFIDENCE_NOTE,
        "inputs": {name: {"value": values[name], "unit": UNITS[name]} for name in features},
        "typical_conditions": (bundle.get("crop_profiles") or {}).get(predicted),
        "typical_conditions_note": (
            "5th–95th percentile of each feature among this crop's rows in the training dataset."
        ),
        "warnings": _range_warnings(values, bundle),
        "model_info": {
            "trained_at": bundle.get("trained_at"),
            "training_rows": bundle.get("n_samples"),
            "held_out_test_accuracy": metrics.get("accuracy"),
            "evaluation_note": (
                "Accuracy was measured on a held-out part of the same dataset; it does not "
                "guarantee accuracy on real farms."
            ),
        },
        "disclaimer": DISCLAIMER,
    }

"""Unit tests for validation, rules scoring, training-data checks and model loading."""

import math

import pandas as pd
import pytest

import crop_rules
import predict
import train_model
import weather_service
from common import FieldSpec, ValidationError, parse_number, validate_fields
from conftest import make_synthetic_dataframe
from predict import FEATURES, SOIL_SPECS

SPEC = FieldSpec("Thing", 0, 10, "u")


# ------------------------------------------------------------ common helpers

@pytest.mark.parametrize("value, expected", [(5, 5.0), ("5.5", 5.5), (" 0 ", 0.0), (10, 10.0)])
def test_parse_number_ok(value, expected):
    assert parse_number(value, SPEC) == expected


@pytest.mark.parametrize("value", [True, None, "", "abc", [], {}, math.nan, math.inf, -0.1, 10.1])
def test_parse_number_rejects(value):
    with pytest.raises(ValueError):
        parse_number(value, SPEC)


def test_validate_fields_reports_every_problem():
    with pytest.raises(ValidationError) as info:
        validate_fields({"a": 99}, {"a": SPEC, "b": SPEC}, required=["a", "b"])
    assert set(info.value.errors) == {"a", "b"}


def test_validate_fields_optional_missing_is_skipped():
    assert validate_fields({}, {"a": SPEC}, required=[]) == {}


# --------------------------------------------------------------- coordinates

def test_coordinates_ok():
    assert weather_service.validate_coordinates("13.08", 80.27) == (13.08, 80.27)


@pytest.mark.parametrize("lat, lon", [(None, 1), (1, None), ("x", 1), (95, 1), (1, -181), ("inf", 1)])
def test_coordinates_invalid(lat, lon):
    with pytest.raises(weather_service.CoordinateError):
        weather_service.validate_coordinates(lat, lon)


# ------------------------------------------------------------------ soil specs

def test_feature_order_matches_training_contract():
    assert FEATURES == ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
    assert list(SOIL_SPECS) == FEATURES


def test_ph_range_is_0_to_14():
    assert (SOIL_SPECS["ph"].minimum, SOIL_SPECS["ph"].maximum) == (0, 14)


# ---------------------------------------------------------------- rules scoring

RANGE = {"min": 10, "optimal_min": 20, "optimal_max": 30, "max": 40}


@pytest.mark.parametrize("value, expected", [
    (25, 1.0), (20, 1.0), (30, 1.0), (15, 0.5), (35, 0.5), (10, 0.0), (40, 0.0), (5, 0.0), (45, 0.0),
])
def test_factor_score(value, expected):
    assert crop_rules.factor_score(value, RANGE) == pytest.approx(expected)


def test_default_rules_file_loads_and_covers_dataset_crops():
    rules = crop_rules.load_rules()
    expected = {
        "rice", "maize", "chickpea", "kidneybeans", "pigeonpeas", "mothbeans", "mungbean",
        "blackgram", "lentil", "pomegranate", "banana", "mango", "grapes", "watermelon",
        "muskmelon", "apple", "orange", "papaya", "coconut", "cotton", "jute", "coffee",
    }
    assert expected <= set(rules["crops"])


def test_rules_missing_file(tmp_path):
    with pytest.raises(crop_rules.RulesNotAvailableError):
        crop_rules.load_rules(tmp_path / "none.json")


def test_rules_invalid_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"crops": {"x": {"seasons": ["kharif"]}}}')
    with pytest.raises(crop_rules.RulesNotAvailableError):
        crop_rules.load_rules(bad)


def test_rules_results_sorted_and_limited():
    rules = crop_rules.load_rules()
    result = crop_rules.recommend_by_weather(
        rules, {"temperature": 27, "humidity": 75, "rainfall": 120}
    )
    scores = [r["score"] for r in result["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert len(scores) <= crop_rules.MAX_RESULTS


# ---------------------------------------------------------- training data checks

def test_train_missing_dataset_raises_clear_error(tmp_path):
    with pytest.raises(train_model.DatasetError, match="Dataset not found"):
        train_model.load_dataset(tmp_path / "nothing.csv")


def test_train_cli_returns_error_code_for_missing_dataset(tmp_path, capsys):
    code = train_model.main(["--data", str(tmp_path / "x.csv"), "--output", str(tmp_path / "m.joblib")])
    assert code == 1
    assert "ERROR" in capsys.readouterr().err
    assert not (tmp_path / "m.joblib").exists()


def test_train_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"N": [1], "label": ["x"]}).to_csv(path, index=False)
    with pytest.raises(train_model.DatasetError, match="missing required column"):
        train_model.load_dataset(path)


def test_train_unreadable_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(train_model.DatasetError):
        train_model.load_dataset(path)


def test_clean_dataframe_drops_invalid_rows():
    df = make_synthetic_dataframe()
    n = len(df)
    df["K"] = df["K"].astype(object)  # allow a non-numeric string in a numeric column
    df.loc[0, "N"] = None
    df.loc[1, "ph"] = 20
    df.loc[2, "humidity"] = -4
    df.loc[3, "label"] = "  "
    df.loc[4, "K"] = "abc"
    cleaned, dropped = train_model.clean_dataframe(df)
    assert dropped == 5 and len(cleaned) == n - 5


def test_clean_dataframe_too_few_rows():
    with pytest.raises(train_model.DatasetError, match="usable rows"):
        train_model.clean_dataframe(make_synthetic_dataframe(rows_per_class=5))


def test_clean_dataframe_single_class():
    df = make_synthetic_dataframe()
    df["label"] = "only"
    with pytest.raises(train_model.DatasetError, match="two different"):
        train_model.clean_dataframe(df)


def test_training_is_reproducible_and_reports_measured_metrics():
    df, _ = train_model.clean_dataframe(make_synthetic_dataframe())
    b1, report = train_model.train_from_dataframe(df, n_estimators=20, seed=7)
    b2, _ = train_model.train_from_dataframe(df, n_estimators=20, seed=7)
    assert b1["metrics"] == b2["metrics"]
    assert b1["feature_names"] == FEATURES
    assert set(b1["metrics"]) >= {"accuracy", "precision_macro", "recall_macro", "f1_macro"}
    assert "precision" in report and "recall" in report


# ----------------------------------------------------------- model loading

def test_load_model_missing_file(tmp_path):
    with pytest.raises(predict.ModelNotAvailableError, match="not found"):
        predict.load_model_bundle(tmp_path / "missing.joblib")


def test_load_model_corrupt_file(tmp_path):
    path = tmp_path / "corrupt.joblib"
    path.write_bytes(b"this is not a model")
    with pytest.raises(predict.ModelNotAvailableError):
        predict.load_model_bundle(path)


def test_load_model_wrong_feature_order(tmp_path):
    import joblib
    path = tmp_path / "wrong.joblib"
    joblib.dump({"model": object(), "feature_names": ["K", "N"]}, path)
    with pytest.raises(predict.ModelNotAvailableError, match="different features"):
        predict.load_model_bundle(path)


def test_prediction_uses_training_feature_order(synthetic_model_path):
    bundle = predict.load_model_bundle(synthetic_model_path)
    assert bundle["feature_names"] == FEATURES
    result = predict.predict_crop(bundle, {
        "N": 20, "P": 60, "K": 20, "temperature": 18, "humidity": 50, "ph": 7.0, "rainfall": 70,
    })
    assert result["predicted_crop"] == "cropb"


def test_prediction_rejects_missing_values(synthetic_model_path):
    bundle = predict.load_model_bundle(synthetic_model_path)
    with pytest.raises(ValidationError) as info:
        predict.predict_crop(bundle, {"N": 1})
    assert "ph" in info.value.errors

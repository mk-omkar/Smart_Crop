"""API tests. External HTTP is mocked; nothing here calls the live weather service."""

import pytest
import requests

import weather_service
from conftest import REAL_DATASET, REAL_MODEL, SOIL_PAYLOAD
from app import create_app


class FakeResponse:
    def __init__(self, payload=None, status=200, bad_json=False):
        self._payload, self.status_code, self._bad_json = payload, status, bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def forecast_payload():
    return {
        "timezone": "Asia/Kolkata",
        "current": {"time": "2026-10-09T12:00", "temperature_2m": 29.34,
                    "relative_humidity_2m": 71.0, "precipitation": 0.0},
        "daily": {
            "time": ["2026-10-09", "2026-10-10"],
            "temperature_2m_mean": [28.2, 27.9],
            "temperature_2m_max": [32.0, 31.1],
            "temperature_2m_min": [24.1, 24.0],
            "precipitation_sum": [1.2, 0.0],
        },
    }


def archive_payload(days=300):
    return {"daily": {
        "time": [f"d{i}" for i in range(days)],
        "temperature_2m_mean": [27.0] * days,
        "precipitation_sum": [3.0] * days,
        "relative_humidity_2m_mean": [70.0] * days,
    }}


def fake_get_factory(forecast=None, archive=None):
    def fake_get(url, params=None, timeout=None):
        if "archive" in url:
            return archive if archive is not None else FakeResponse(archive_payload())
        return forecast if forecast is not None else FakeResponse(forecast_payload())
    return fake_get


# ------------------------------------------------------------------- health

def test_health_reports_real_state_with_model(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["rules_loaded"] is True
    assert body["dataset_available"] is False  # fixture points at a missing CSV


def test_health_missing_model_and_dataset(no_model_client):
    response = no_model_client.get("/api/health")
    body = response.get_json()
    assert response.status_code == 200
    assert body["status"] == "degraded"
    assert body["model_loaded"] is False
    assert body["dataset_available"] is False
    assert "model" in body["problems"]


def test_health_dataset_available_when_file_exists(tmp_path, synthetic_model_path):
    csv = tmp_path / "data.csv"
    csv.write_text("N,P,K,temperature,humidity,ph,rainfall,label\n")
    app = create_app({"MODEL_PATH": str(synthetic_model_path), "DATASET_PATH": str(csv)})
    assert app.test_client().get("/api/health").get_json()["dataset_available"] is True


# ------------------------------------------------------------------ weather

@pytest.mark.parametrize("query", [
    "", "latitude=abc&longitude=77", "latitude=91&longitude=77",
    "latitude=12&longitude=181", "latitude=12", "latitude=nan&longitude=1",
])
def test_weather_rejects_invalid_coordinates(client, query):
    response = client.get(f"/api/weather?{query}")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_coordinates"


def test_weather_success_is_normalised_and_labelled(client, monkeypatch):
    monkeypatch.setattr(weather_service.requests, "get", fake_get_factory())
    response = client.get("/api/weather?latitude=13.08&longitude=80.27")
    body = response.get_json()
    assert response.status_code == 200
    assert body["current"]["temperature_c"] == 29.3
    assert body["current"]["relative_humidity_pct"] == 71
    assert "not seasonal" in body["current"]["label"].lower() or "snapshot" in body["current"]["label"].lower()
    assert len(body["forecast"]["days"]) == 2
    assert body["forecast"]["days"][0]["precipitation_sum_mm"] == 1.2
    assert body["climate"]["average_monthly_rainfall_mm"] == pytest.approx(91.3, abs=0.1)
    assert body["climate"]["mean_temperature_c"] == 27.0
    assert body["climate_error"] is None
    assert body["fetched_at"]


def test_logs_never_contain_coordinates(client, monkeypatch, caplog):
    import logging
    monkeypatch.setattr(weather_service.requests, "get", fake_get_factory())
    with caplog.at_level(logging.DEBUG):
        client.get("/api/weather?latitude=13.0827&longitude=80.2707")
        client.get("/api/weather?latitude=13.0827&longitude=nope")
    assert "/api/weather" in caplog.text  # requests are still logged
    for secret in ("13.0827", "80.2707", "latitude=", "longitude="):
        assert secret not in caplog.text


def test_weather_is_cached_per_location(client, monkeypatch):
    calls = []
    inner = fake_get_factory()

    def counting_get(url, params=None, timeout=None):
        calls.append(url)
        return inner(url, params, timeout)

    monkeypatch.setattr(weather_service.requests, "get", counting_get)
    client.get("/api/weather?latitude=13.08&longitude=80.27")
    first = len(calls)
    client.get("/api/weather?latitude=13.081&longitude=80.271")  # same ~1 km cell
    assert len(calls) == first


def test_weather_climate_failure_does_not_fake_data(client, monkeypatch):
    monkeypatch.setattr(
        weather_service.requests, "get",
        fake_get_factory(archive=FakeResponse({"reason": "bad"}, status=400)),
    )
    body = client.get("/api/weather?latitude=13&longitude=80").get_json()
    assert body["climate"] is None
    assert body["climate_error"]
    assert body["current"]["temperature_c"] is not None


@pytest.mark.parametrize("exc, status, code", [
    (requests.Timeout(), 504, "weather_timeout"),
    (requests.ConnectionError(), 502, "weather_unreachable"),
])
def test_weather_network_errors(client, monkeypatch, exc, status, code):
    def boom(*args, **kwargs):
        raise exc
    monkeypatch.setattr(weather_service.requests, "get", boom)
    response = client.get("/api/weather?latitude=13&longitude=80")
    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code


def test_weather_upstream_http_error(client, monkeypatch):
    monkeypatch.setattr(
        weather_service.requests, "get",
        fake_get_factory(forecast=FakeResponse({"reason": "Too many requests"}, status=429)),
    )
    response = client.get("/api/weather?latitude=13&longitude=80")
    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "weather_upstream_error"


def test_weather_malformed_upstream_json(client, monkeypatch):
    monkeypatch.setattr(
        weather_service.requests, "get", fake_get_factory(forecast=FakeResponse(bad_json=True))
    )
    response = client.get("/api/weather?latitude=13&longitude=80")
    assert response.status_code == 502


def test_weather_missing_current_block(client, monkeypatch):
    monkeypatch.setattr(
        weather_service.requests, "get", fake_get_factory(forecast=FakeResponse({"daily": {}}))
    )
    assert client.get("/api/weather?latitude=13&longitude=80").status_code == 502


# ----------------------------------------------------------------- geocode

def test_geocode_filters_by_region(client, monkeypatch):
    payload = {"results": [
        {"name": "Hosur", "admin1": "Tamil Nadu", "admin2": "Krishnagiri", "country": "India",
         "latitude": 12.74, "longitude": 77.83},
        {"name": "Hosur", "admin1": "Karnataka", "admin2": "Bagalkot", "country": "India",
         "latitude": 16.0, "longitude": 75.7},
    ]}
    monkeypatch.setattr(weather_service.requests, "get", lambda *a, **k: FakeResponse(payload))
    body = client.get("/api/geocode?name=Hosur&region=tamil").get_json()
    assert [r["admin1"] for r in body["results"]] == ["Tamil Nadu"]


def test_geocode_requires_every_region_term(client, monkeypatch):
    payload = {"results": [
        {"name": "Hosur", "admin1": "Tamil Nadu", "admin2": "Krishnagiri", "country": "India",
         "latitude": 12.74, "longitude": 77.83},
        {"name": "Hosur", "admin1": "Tamil Nadu", "admin2": "Other", "country": "India",
         "latitude": 11.0, "longitude": 77.0},
    ]}
    monkeypatch.setattr(weather_service.requests, "get", lambda *a, **k: FakeResponse(payload))
    body = client.get("/api/geocode?name=Hosur&region=krishnagiri,tamil nadu").get_json()
    assert [r["admin2"] for r in body["results"]] == ["Krishnagiri"]


def test_geocode_rejects_short_name(client):
    assert client.get("/api/geocode?name=a").status_code == 400


# ------------------------------------------------------ soil recommendation

def test_soil_missing_model_returns_503(no_model_client):
    response = no_model_client.post("/api/recommend", json=SOIL_PAYLOAD)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "model_unavailable"


@pytest.mark.parametrize("body", [None, [], "text", 5])
def test_soil_invalid_body(client, body):
    response = client.post("/api/recommend", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_body"


def test_soil_non_json_body(client):
    response = client.post("/api/recommend", data="N=1", content_type="text/plain")
    assert response.status_code == 400


def test_soil_wrong_mode(client):
    response = client.post("/api/recommend", json={**SOIL_PAYLOAD, "mode": "weather"})
    assert response.status_code == 400


@pytest.mark.parametrize("field, value, fragment", [
    ("N", -5, "Nitrogen"), ("P", -1, "Phosphorus"), ("K", 9999, "Potassium"),
    ("ph", 15, "pH"), ("ph", -0.1, "pH"), ("humidity", 120, "Humidity"),
    ("humidity", "wet", "Humidity"), ("temperature", 999, "Temperature"),
    ("rainfall", -3, "Rainfall"), ("N", True, "Nitrogen"), ("K", float("inf"), "Potassium"),
])
def test_soil_invalid_values(client, field, value, fragment):
    payload = {**SOIL_PAYLOAD, field: value}
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 422
    details = response.get_json()["error"]["details"]
    assert field in details and fragment in details[field]


def test_soil_missing_features_lists_all(client):
    response = client.post("/api/recommend", json={"mode": "soil", "N": 10})
    assert response.status_code == 422
    details = response.get_json()["error"]["details"]
    assert set(details) == {"P", "K", "temperature", "humidity", "ph", "rainfall"}


def test_soil_valid_prediction_with_fixture_model(client):
    response = client.post("/api/recommend", json=SOIL_PAYLOAD)
    body = response.get_json()
    assert response.status_code == 200
    assert body["mode"] == "soil" and body["method_type"] == "machine_learning"
    assert body["predicted_crop"] == "cropa"  # fixture class centred on these values
    assert body["top_predictions"][0]["score"] >= body["top_predictions"][-1]["score"]
    assert "not real-world probabilities" in body["confidence_note"]
    assert body["inputs"]["ph"]["value"] == 6.5
    assert body["disclaimer"]


def test_soil_accepts_numeric_strings(client):
    payload = {**SOIL_PAYLOAD, "N": "90", "ph": " 6.5 "}
    assert client.post("/api/recommend", json=payload).status_code == 200


def test_soil_warns_when_outside_training_range(client):
    body = client.post("/api/recommend", json={**SOIL_PAYLOAD, "rainfall": 900}).get_json()
    assert any("outside the range" in w for w in body["warnings"])


# ----------------------------------------------------- weather recommendation

def test_weather_mode_works_without_soil_data(client):
    response = client.post(
        "/api/recommend/weather",
        json={"temperature": 27, "humidity": 80, "rainfall": 200, "season": "kharif"},
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["method_type"] == "rule_based"
    assert "not machine learning" in body["method"].lower()
    assert body["recommendations"], "expected at least one suitable crop"
    # Rice's optimal ranges are centred on these values, so it must make the shortlist.
    assert "rice" in [r["crop"] for r in body["recommendations"]]
    assert all(r["factors"] for r in body["recommendations"])
    assert any("Soil nutrients" in w for w in body["missing_data_warnings"])
    assert "soil test" in body["soil_test_recommendation"].lower()
    assert body["limitations"]


def test_weather_mode_does_not_need_model(no_model_client):
    response = no_model_client.post(
        "/api/recommend/weather", json={"temperature": 27, "humidity": 80, "rainfall": 200}
    )
    assert response.status_code == 200


def test_weather_mode_warns_about_missing_factors(client):
    body = client.post("/api/recommend/weather", json={"temperature": 27}).get_json()
    warnings = " ".join(body["missing_data_warnings"])
    assert "Humidity was not provided" in warnings
    assert "rainfall was not provided" in warnings.lower()


def test_weather_mode_season_filter(client):
    kharif = client.post(
        "/api/recommend/weather",
        json={"temperature": 22, "humidity": 55, "rainfall": 40, "season": "rabi"},
    ).get_json()
    crops = {r["crop"] for r in kharif["recommendations"]}
    assert "rice" not in crops and "cotton" not in crops


def test_weather_mode_no_match_is_empty_not_error(client):
    body = client.post(
        "/api/recommend/weather", json={"temperature": -5, "humidity": 5, "rainfall": 1400}
    ).get_json()
    assert body["recommendations"] == []
    assert any("No crop" in w for w in body["missing_data_warnings"])


@pytest.mark.parametrize("payload, field", [
    ({}, "weather"),
    ({"humidity": 50}, "temperature"),
    ({"temperature": 25, "humidity": 150}, "humidity"),
    ({"temperature": "hot"}, "temperature"),
    ({"temperature": 25, "season": "monsoon"}, "season"),
    ({"temperature": 25, "rainfall": -1}, "rainfall"),
])
def test_weather_mode_validation(client, payload, field):
    response = client.post("/api/recommend/weather", json=payload)
    assert response.status_code == 422
    assert field in response.get_json()["error"]["details"]


def test_weather_mode_invalid_body(client):
    assert client.post("/api/recommend/weather", json=[1, 2]).status_code == 400


# ---------------------------------------------------------------- misc / real

def test_unknown_route_returns_json_error(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_wrong_method_returns_json_error(client):
    response = client.get("/api/recommend")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"


@pytest.mark.real_model
@pytest.mark.skipif(
    not (REAL_MODEL.is_file() and REAL_DATASET.is_file()),
    reason="Needs the downloaded dataset and a model trained with train_model.py",
)
def test_real_model_prediction():
    client = create_app({"TESTING": True}).test_client()
    body = client.post("/api/recommend", json=SOIL_PAYLOAD).get_json()
    assert body["predicted_crop"]
    assert body["model_info"]["held_out_test_accuracy"] is not None
    assert body["top_predictions"]

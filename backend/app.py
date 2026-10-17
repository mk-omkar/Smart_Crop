"""Smart Crop Advisor - Flask REST API.

Run:  python app.py        (default http://localhost:5000)

Error responses always look like:
    {"error": {"code": "...", "message": "...", "details": {...}}}
Status codes: 400 malformed request, 422 invalid/missing values, 502/504 weather service
problems, 503 model unavailable, 500 unexpected error.
"""

import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import crop_rules
import predict
import weather_service
from common import ValidationError

try:  # optional: load backend/.env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("crop_advisor")


def error_response(code, message, status, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


class ModelStore:
    """Loads the trained model lazily so training while the server runs just works."""

    def __init__(self, path):
        self.path = Path(path)
        self._bundle = None
        self._lock = threading.Lock()

    def get(self):
        """Return the bundle or raise predict.ModelNotAvailableError."""
        with self._lock:
            if self._bundle is None:
                self._bundle = predict.load_model_bundle(self.path)
                logger.info("Model loaded")
            return self._bundle

    def status(self):
        try:
            self.get()
            return True, None
        except predict.ModelNotAvailableError as exc:
            return False, str(exc)


def create_app(test_config=None):
    app = Flask(__name__)
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    app.config.update(
        MODEL_PATH=str(BASE_DIR / "models" / "crop_model.joblib"),
        DATASET_PATH=str(BASE_DIR / "data" / "Crop_recommendation.csv"),
        RULES_PATH=str(crop_rules.DEFAULT_RULES_PATH),
        CORS_ORIGINS=[o.strip() for o in origins.split(",") if o.strip()],
        MAX_CONTENT_LENGTH=16 * 1024,  # requests here are tiny; reject anything large
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Werkzeug's access log prints the full URL, which would include the farmer's exact
    # coordinates (?latitude=..&longitude=..). Silence it and log path + status only.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.after_request
    def log_request(response):
        logger.info("%s %s -> %s", request.method, request.path, response.status_code)
        return response

    store = ModelStore(app.config["MODEL_PATH"])
    app.extensions["model_store"] = store

    def get_rules():
        return crop_rules.load_rules(app.config["RULES_PATH"])

    def json_body():
        """Return the JSON object body, or None if missing/not an object."""
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None

    # ------------------------------------------------------------------ routes

    @app.get("/api/health")
    def health():
        model_loaded, model_problem = store.status()
        try:
            rules = get_rules()
            rules_loaded, rules_problem, crop_count = True, None, len(rules["crops"])
        except crop_rules.RulesNotAvailableError as exc:
            rules_loaded, rules_problem, crop_count = False, str(exc), 0

        dataset_available = Path(app.config["DATASET_PATH"]).is_file()
        body = {
            "status": "ok" if (model_loaded and rules_loaded) else "degraded",
            "model_loaded": model_loaded,
            "dataset_available": dataset_available,
            "rules_loaded": rules_loaded,
            "rule_crop_count": crop_count,
        }
        problems = {}
        if model_problem:
            problems["model"] = model_problem
        if rules_problem:
            problems["rules"] = rules_problem
        if problems:
            body["problems"] = problems
        return jsonify(body)

    @app.get("/api/weather")
    def weather():
        try:
            lat, lon = weather_service.validate_coordinates(
                request.args.get("latitude"), request.args.get("longitude")
            )
        except weather_service.CoordinateError as exc:
            return error_response("invalid_coordinates", "Invalid latitude or longitude.", 400, exc.errors)
        try:
            return jsonify(weather_service.get_weather_bundle(lat, lon))
        except weather_service.WeatherServiceError as exc:
            logger.warning("Weather request failed: %s", exc.code)  # no coordinates logged
            return error_response(exc.code, exc.message, exc.status_code)

    @app.get("/api/geocode")
    def geocode():
        try:
            results = weather_service.search_places(
                request.args.get("name"), request.args.get("region")
            )
        except ValueError as exc:
            return error_response("invalid_query", str(exc), 400)
        except weather_service.WeatherServiceError as exc:
            return error_response(exc.code, exc.message, exc.status_code)
        return jsonify({"results": results, "source": "Open-Meteo Geocoding API"})

    @app.post("/api/recommend")
    def recommend_soil():
        payload = json_body()
        if payload is None:
            return error_response("invalid_body", "Request body must be a JSON object.", 400)

        mode = payload.get("mode", "soil")
        if mode != "soil":
            return error_response(
                "invalid_mode",
                "This endpoint only supports mode 'soil'. Use /api/recommend/weather for "
                "weather-only recommendations.",
                400,
            )
        try:
            bundle = store.get()
        except predict.ModelNotAvailableError as exc:
            return error_response("model_unavailable", str(exc), 503)

        try:
            return jsonify(predict.predict_crop(bundle, payload))
        except ValidationError as exc:
            return error_response("validation_error", "Some inputs are missing or invalid.", 422, exc.errors)

    @app.post("/api/recommend/weather")
    def recommend_weather():
        payload = json_body()
        if payload is None:
            return error_response("invalid_body", "Request body must be a JSON object.", 400)
        try:
            rules = get_rules()
        except crop_rules.RulesNotAvailableError as exc:
            return error_response("rules_unavailable", str(exc), 503)
        try:
            return jsonify(crop_rules.recommend_by_weather(rules, payload))
        except ValidationError as exc:
            return error_response("validation_error", "Some inputs are missing or invalid.", 422, exc.errors)

    # ---------------------------------------------------------- error handlers

    @app.errorhandler(HTTPException)
    def handle_http(exc):
        codes = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}
        return error_response(codes.get(exc.code, "http_error"), exc.description, exc.code)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        logger.exception("Unhandled error")  # traceback only; request data is not logged
        return error_response("internal_error", "An unexpected server error occurred.", 500)

    return app


app = create_app()

if __name__=="__main__":
    port=int(os.environ.get("PORT","5000"))
    debug=os.environ.get("FLASK_DEBUG","0")=="1"
    logger.info("Smart Crop Advisor backend running on port %s",port)
    app.run(host="0.0.0.0",port=port,debug=debug)
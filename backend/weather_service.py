"""Open-Meteo integration: forecast, historical climate summary and place search.

All external HTTP calls live here so they are easy to mock in tests. No API key is
required. Coordinates are rounded to 2 decimals (~1 km) for caching and are never logged.
"""

import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

TIMEOUT = (5, 15)  # (connect, read) seconds
CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 256
ARCHIVE_LAG_DAYS = 7  # the archive trails real time by a few days
CLIMATE_WINDOW_DAYS = 365
MIN_CLIMATE_DAYS = 180


class CoordinateError(ValueError):
    """Latitude/longitude missing or invalid."""

    def __init__(self, errors):
        self.errors = dict(errors)
        super().__init__("; ".join(self.errors.values()))


class WeatherServiceError(Exception):
    """The external weather service failed. `status_code` is what our API returns."""

    def __init__(self, message, status_code=502, code="weather_service_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


# ---------------------------------------------------------------- validation

def _parse_coordinate(value, name, low, high):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, f"{name} is required."
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if not math.isfinite(number):
        return None, f"{name} must be a finite number."
    if number < low or number > high:
        return None, f"{name} must be between {low:g} and {high:g}."
    return number, None


def validate_coordinates(latitude, longitude):
    """Return (lat, lon) floats or raise CoordinateError listing every problem."""
    errors = {}
    lat, err = _parse_coordinate(latitude, "latitude", -90, 90)
    if err:
        errors["latitude"] = err
    lon, err = _parse_coordinate(longitude, "longitude", -180, 180)
    if err:
        errors["longitude"] = err
    if errors:
        raise CoordinateError(errors)
    return lat, lon


# --------------------------------------------------------------------- cache

_cache = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if item and time.monotonic() - item[0] < CACHE_TTL_SECONDS:
            return item[1]
        _cache.pop(key, None)
    return None


def _cache_set(key, value):
    with _cache_lock:
        if len(_cache) >= CACHE_MAX_ENTRIES:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest, None)
        _cache[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------- HTTP

def _get_json(url, params):
    """GET with timeout and uniform error translation. Never retries automatically."""
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.Timeout:
        raise WeatherServiceError(
            "The weather service took too long to respond. Please try again.",
            504, "weather_timeout",
        ) from None
    except requests.RequestException:
        raise WeatherServiceError(
            "Could not reach the weather service. Check the server's internet connection.",
            502, "weather_unreachable",
        ) from None

    if response.status_code != 200:
        reason = ""
        try:
            reason = str(response.json().get("reason", ""))[:200]
        except Exception:  # noqa: BLE001 - body may not be JSON
            pass
        logger.warning("Open-Meteo returned HTTP %s", response.status_code)
        message = "The weather service returned an error."
        if reason:
            message += f" ({reason})"
        raise WeatherServiceError(message, 502, "weather_upstream_error")

    try:
        data = response.json()
    except ValueError:
        raise WeatherServiceError(
            "The weather service returned an unreadable response.", 502, "weather_bad_response"
        ) from None
    if not isinstance(data, dict):
        raise WeatherServiceError(
            "The weather service returned an unexpected response.", 502, "weather_bad_response"
        )
    return data


def _round(value, digits=1):
    return round(value, digits) if isinstance(value, (int, float)) else None


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ forecast

def fetch_forecast(latitude, longitude):
    """Current conditions + 7-day daily forecast, normalised."""
    data = _get_json(FORECAST_URL, {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation",
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "forecast_days": 7,
        "timezone": "auto",
    })

    current = data.get("current")
    if not isinstance(current, dict):
        raise WeatherServiceError(
            "The weather service returned no current conditions for this location.",
            502, "weather_bad_response",
        )

    daily = data.get("daily") or {}
    dates = daily.get("time") or []

    def series(key):
        values = daily.get(key) or []
        return [values[i] if i < len(values) else None for i in range(len(dates))]

    means, maxes, mins, precip = (
        series("temperature_2m_mean"), series("temperature_2m_max"),
        series("temperature_2m_min"), series("precipitation_sum"),
    )
    days = [
        {
            "date": dates[i],
            "temperature_mean_c": _round(means[i]),
            "temperature_max_c": _round(maxes[i]),
            "temperature_min_c": _round(mins[i]),
            "precipitation_sum_mm": _round(precip[i]),
        }
        for i in range(len(dates))
    ]

    return {
        "source": "Open-Meteo Forecast API",
        "timezone": data.get("timezone"),
        "fetched_at": _now_iso(),
        "current": {
            "label": "Current conditions (a snapshot, not a seasonal average)",
            "time": current.get("time"),
            "temperature_c": _round(current.get("temperature_2m")),
            "relative_humidity_pct": _round(current.get("relative_humidity_2m"), 0),
            "precipitation_mm": _round(current.get("precipitation")),
            "precipitation_note": "Precipitation in the preceding hour, not seasonal rainfall.",
        },
        "forecast": {
            "label": "Short-term forecast (next days only; not total seasonal rainfall)",
            "days": days,
        },
    }


# ------------------------------------------------------------------- climate

def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def fetch_climate_summary(latitude, longitude):
    """Average conditions over roughly the past 12 months from the historical archive."""
    end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    start = end - timedelta(days=CLIMATE_WINDOW_DAYS - 1)
    base = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "auto",
    }

    # Try with humidity; fall back without it if the archive rejects that variable.
    try:
        data = _get_json(ARCHIVE_URL, {
            **base, "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean"
        })
    except WeatherServiceError as exc:
        if exc.code != "weather_upstream_error":
            raise
        data = _get_json(ARCHIVE_URL, {**base, "daily": "temperature_2m_mean,precipitation_sum"})

    daily = data.get("daily") or {}
    temps = daily.get("temperature_2m_mean") or []
    rain = [v for v in (daily.get("precipitation_sum") or []) if isinstance(v, (int, float))]
    humidity = daily.get("relative_humidity_2m_mean") or []

    if len(rain) < MIN_CLIMATE_DAYS or not [t for t in temps if isinstance(t, (int, float))]:
        raise WeatherServiceError(
            "Not enough historical data was returned to compute a climate summary.",
            502, "weather_insufficient_history",
        )

    total_rain = sum(rain)
    monthly_rain = total_rain / len(rain) * 30.4375
    return {
        "label": "Historical average over the past ~12 months (ERA5 reanalysis)",
        "source": "Open-Meteo Historical Weather API",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "days_with_data": len(rain),
        "mean_temperature_c": _round(_mean(temps)),
        "mean_relative_humidity_pct": _round(_mean(humidity), 0),
        "average_monthly_rainfall_mm": _round(monthly_rain),
        "total_rainfall_mm": _round(total_rain, 0),
        "note": (
            "A 12-month average hides seasonality: real crop-season rainfall can be much "
            "higher or lower than this monthly average."
        ),
    }


# -------------------------------------------------------------------- bundle

def get_weather_bundle(latitude, longitude):
    """Forecast (required) plus climate summary (best effort), cached per ~1 km cell."""
    key = ("weather", round(latitude, 2), round(longitude, 2))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    bundle = fetch_forecast(latitude, longitude)
    try:
        bundle["climate"] = fetch_climate_summary(latitude, longitude)
        bundle["climate_error"] = None
    except WeatherServiceError as exc:
        # Forecast still useful; tell the caller climate data is missing instead of faking it.
        bundle["climate"] = None
        bundle["climate_error"] = exc.message

    bundle["location"] = {"latitude": round(latitude, 4), "longitude": round(longitude, 4)}
    _cache_set(key, bundle)
    return bundle


# ------------------------------------------------------------------ geocoding

def search_places(name, region=None, count=20):
    """Look up places by name; optionally filter by district/state text."""
    name = (name or "").strip()
    if len(name) < 2 or len(name) > 100:
        raise ValueError("Place name must be between 2 and 100 characters.")
    # `region` may be "district,state"; every comma-separated term must match somewhere.
    terms = [t.strip().lower() for t in (region or "")[:100].split(",") if t.strip()]

    data = _get_json(GEOCODING_URL, {
        "name": name, "count": count, "language": "en", "format": "json",
    })
    results = []
    for item in data.get("results") or []:
        lat, lon = item.get("latitude"), item.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        place = {
            "name": item.get("name"),
            "admin3": item.get("admin3"),
            "admin2": item.get("admin2"),
            "admin1": item.get("admin1"),
            "country": item.get("country"),
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
        }
        if terms:
            haystack = " ".join(
                str(place[k] or "") for k in ("admin3", "admin2", "admin1", "country")
            ).lower()
            if not all(term in haystack for term in terms):
                continue
        results.append(place)
    return results[:10]

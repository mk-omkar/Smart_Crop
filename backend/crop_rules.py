"""Mode B: transparent rule-based crop suitability ranking from weather/climate only.

This is NOT a trained machine-learning model. It compares weather values against the
configurable crop requirement ranges in data/crop_rules.json.
"""

import json
from pathlib import Path

from common import DISCLAIMER, FieldSpec, ValidationError, validate_fields

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "data" / "crop_rules.json"

WEATHER_SPECS = {
    "temperature": FieldSpec("Mean temperature", -10, 55, "°C"),
    "humidity": FieldSpec("Humidity", 0, 100, "%"),
    "rainfall": FieldSpec("Average monthly rainfall", 0, 1500, "mm/month"),
}
UNITS = {"temperature": "°C", "humidity": "%", "rainfall": "mm/month"}
SEASONS = ("kharif", "rabi", "zaid", "any")

MIN_SCORE = 0.5      # crops scoring below this are not suggested
MAX_RESULTS = 5
GOOD_SCORE = 0.8

METHOD = (
    "Rule-based suitability ranking (not machine learning): each crop is scored by how well "
    "temperature, humidity and rainfall fit its requirement ranges in crop_rules.json."
)
LIMITATIONS = [
    "Soil nutrients (N, P, K) and soil pH are not considered, so suitability may be overstated.",
    "Crop requirement ranges are approximate demonstration values, not locally validated.",
    "Rainfall is a historical monthly average; real crop-season rainfall can differ a lot.",
    "Irrigation, crop variety, elevation, pests, markets and farm practices are not considered.",
    "This method was not trained on the 7-feature Kaggle dataset used by the soil-informed mode.",
]
SOIL_TEST_RECOMMENDATION = (
    "For a more reliable recommendation, get a soil test (N, P, K and pH) from a local soil "
    "testing lab and use the soil-informed mode."
)


class RulesNotAvailableError(Exception):
    """Rules file missing or invalid."""


def load_rules(path=DEFAULT_RULES_PATH):
    path = Path(path)
    if not path.is_file():
        raise RulesNotAvailableError(f"Crop rules file not found: {path.name}")
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
        crops = rules["crops"]
        for name, crop in crops.items():
            for factor in WEATHER_SPECS:
                r = crop[factor]
                if not (r["min"] <= r["optimal_min"] <= r["optimal_max"] <= r["max"]):
                    raise ValueError(f"{name}.{factor} range is not ordered")
            if not crop.get("seasons"):
                raise ValueError(f"{name} has no seasons")
    except (ValueError, KeyError, TypeError) as exc:
        raise RulesNotAvailableError(f"Crop rules file is invalid: {exc}") from exc
    return rules


def factor_score(value, rng):
    """1.0 inside the optimal range, falling linearly to 0.0 at the min/max limits."""
    if value < rng["min"] or value > rng["max"]:
        return 0.0
    if rng["optimal_min"] <= value <= rng["optimal_max"]:
        return 1.0
    if value < rng["optimal_min"]:
        return (value - rng["min"]) / (rng["optimal_min"] - rng["min"])
    return (rng["max"] - value) / (rng["max"] - rng["optimal_max"])


def centrality(value, rng):
    """Tie-breaker: 1.0 at the middle of the optimal range, lower toward its edges/outside.

    Many crops can score a perfect 1.0 (anywhere inside their optimal range); this prefers
    the crops whose optimal range is centred nearest to the observed value.
    """
    middle = (rng["optimal_min"] + rng["optimal_max"]) / 2
    half_span = max((rng["max"] - rng["min"]) / 2, 1e-9)
    return max(0.0, 1.0 - abs(value - middle) / half_span)


def validate_weather_payload(payload):
    """Return (values, season, warnings). Needs at least one weather value."""
    values = validate_fields(payload, WEATHER_SPECS, required=())
    if not values:
        raise ValidationError({
            "weather": "Provide at least one of: temperature, humidity, rainfall."
        })
    if "temperature" not in values:
        raise ValidationError({"temperature": "Mean temperature is required."})

    season = payload.get("season")
    if season is None or (isinstance(season, str) and not season.strip()):
        season = "any"
    if not isinstance(season, str) or season.strip().lower() not in SEASONS:
        raise ValidationError({"season": f"Season must be one of: {', '.join(SEASONS)}."})
    season = season.strip().lower()

    warnings = ["Soil nutrients (N, P, K) and pH were not provided and were not used."]
    for name in ("humidity", "rainfall"):
        if name not in values:
            warnings.append(
                f"{WEATHER_SPECS[name].label} was not provided; "
                "suggestions are based on the remaining factors only."
            )
    if season == "any":
        warnings.append("No season selected; crops from every sowing season are considered.")
    return values, season, warnings


def recommend_by_weather(rules, payload):
    """Rank crops by weather fit. Raises ValidationError for bad input."""
    values, season, warnings = validate_weather_payload(payload)
    meta = rules.get("metadata", {})
    weights = meta.get("weights", {"temperature": 0.4, "humidity": 0.2, "rainfall": 0.4})

    ranked = []
    excluded_by_season = 0
    for key, crop in rules["crops"].items():
        seasons = crop["seasons"]
        if season != "any" and season not in seasons and "perennial" not in seasons:
            excluded_by_season += 1
            continue

        factors, weighted, total_weight, blocked = [], 0.0, 0.0, False
        central = 0.0
        for factor, value in values.items():
            rng = crop[factor]
            score = factor_score(value, rng)
            if score == 0.0:
                blocked = True
                break
            weighted += weights.get(factor, 0.0) * score
            central += weights.get(factor, 0.0) * centrality(value, rng)
            total_weight += weights.get(factor, 0.0)
            factors.append({
                "factor": factor,
                "value": value,
                "unit": UNITS[factor],
                "score": round(score, 2),
                "status": "optimal" if score == 1.0 else "tolerable",
                "optimal_range": [rng["optimal_min"], rng["optimal_max"]],
                "tolerable_range": [rng["min"], rng["max"]],
            })
        if blocked or total_weight == 0:
            continue

        overall = weighted / total_weight
        if overall < MIN_SCORE:
            continue
        ranked.append({
            "crop": key,
            "display_name": crop.get("display_name", key.title()),
            "score": round(overall, 2),
            "match_level": "good" if overall >= GOOD_SCORE else "fair",
            "factors": factors,
            "seasons": seasons,
            "growing_conditions": {f: crop[f] for f in UNITS},
            "notes": crop.get("notes", ""),
            "_centrality": central / total_weight,
        })

    # Order by fit score, then by how central the values are in the optimal range.
    ranked.sort(key=lambda item: (-item["score"], -item["_centrality"], item["display_name"]))
    for item in ranked:
        item.pop("_centrality")
    results = ranked[:MAX_RESULTS]

    if not results:
        warnings.append(
            "No crop in the rule table matches these conditions well. "
            "Check your inputs, or consult a local agriculture officer."
        )
    if excluded_by_season:
        warnings.append(
            f"{excluded_by_season} non-perennial crop(s) were skipped because they are not "
            f"sown in the {season} season."
        )

    return {
        "mode": "weather",
        "method_type": "rule_based",
        "method": METHOD,
        "recommendations": results,
        "inputs": {
            **{n: {"value": v, "unit": UNITS[n]} for n, v in values.items()},
            "season": season,
        },
        "missing_data_warnings": warnings,
        "limitations": LIMITATIONS,
        "soil_test_recommendation": SOIL_TEST_RECOMMENDATION,
        "rules_info": {
            "name": meta.get("name"),
            "version": meta.get("version"),
            "disclaimer": meta.get("disclaimer"),
        },
        "disclaimer": DISCLAIMER,
    }

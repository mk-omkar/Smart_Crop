"""Shared validation helpers and constants used by the prediction and rule modules."""

import math
from dataclasses import dataclass

DISCLAIMER = (
    "These recommendations are preliminary and for educational/demonstration use. "
    "Verify them against local agricultural guidance (for example your nearest "
    "Krishi Vigyan Kendra or agriculture extension officer) before making planting decisions."
)


@dataclass(frozen=True)
class FieldSpec:
    """Describes one numeric input: label for messages, allowed range, unit."""

    label: str
    minimum: float
    maximum: float
    unit: str = ""


class ValidationError(Exception):
    """Raised when one or more input fields are missing or invalid.

    `errors` maps field name -> human-readable message.
    """

    def __init__(self, errors):
        self.errors = dict(errors)
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


def parse_number(value, spec):
    """Convert `value` to a finite float within the spec range, or raise ValueError."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{spec.label} must be a number.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{spec.label} is required.")
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"{spec.label} must be a number (got '{text[:20]}').") from None
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        raise ValueError(f"{spec.label} must be a number.")

    if not math.isfinite(number):
        raise ValueError(f"{spec.label} must be a finite number.")
    if number < spec.minimum or number > spec.maximum:
        unit = f" {spec.unit}" if spec.unit else ""
        raise ValueError(
            f"{spec.label} must be between {spec.minimum:g} and {spec.maximum:g}{unit}."
        )
    return number


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def validate_fields(payload, specs, required):
    """Validate a dict of numeric fields.

    specs: {field: FieldSpec}; required: iterable of field names that must be present.
    Returns {field: float} for provided valid fields. Raises ValidationError listing
    every problem at once so the user can fix them in one go.
    """
    errors = {}
    clean = {}
    for name, spec in specs.items():
        raw = payload.get(name)
        if _is_blank(raw):
            if name in required:
                errors[name] = f"{spec.label} is required."
            continue
        try:
            clean[name] = parse_number(raw, spec)
        except ValueError as exc:
            errors[name] = str(exc)
    if errors:
        raise ValidationError(errors)
    return clean

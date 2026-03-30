"""Request validation --- schema-based input checking for API routes.

Provides @validate_json decorator for consistent request validation.
Auto-sanitizes string fields via mandarin.sanitize.sanitize_user_text().
"""

import functools
import logging

from flask import request, jsonify

from .api_errors import api_error, VALIDATION_ERROR

logger = logging.getLogger(__name__)


def validate_json(schema):
    """Validate request JSON against a schema dict.

    Schema format:
    {
        "field_name": {
            "type": str | int | float | bool | list,
            "required": True | False,
            "min_length": int,      # for strings
            "max_length": int,      # for strings
            "min_value": number,    # for int/float
            "max_value": number,    # for int/float
            "enum": [values],       # allowed values
            "sanitize": True,       # auto-sanitize string (default True)
        }
    }

    Usage:
        @app.route("/api/items", methods=["POST"])
        @validate_json({"title": {"type": str, "required": True, "max_length": 500}})
        def create_item():
            data = request.get_json()  # Already validated + sanitized
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None:
                return api_error(VALIDATION_ERROR, "JSON body required", 400)

            errors = _validate(data, schema)
            if errors:
                return api_error(VALIDATION_ERROR, "; ".join(errors), 400)

            # Auto-sanitize string fields
            _sanitize_strings(data, schema)

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def _validate(data, schema):
    """Validate data against schema, return list of error messages."""
    errors = []

    for field, rules in schema.items():
        value = data.get(field)
        required = rules.get("required", False)
        field_type = rules.get("type")

        # Required check
        if required and (value is None or value == ""):
            errors.append(f"{field} is required")
            continue

        if value is None:
            continue  # Optional field not provided

        # Type check
        if field_type and not isinstance(value, field_type):
            # Allow int for float fields
            if field_type is float and isinstance(value, int):
                pass
            else:
                errors.append(f"{field} must be {field_type.__name__}")
                continue

        # String validations
        if isinstance(value, str):
            min_len = rules.get("min_length")
            max_len = rules.get("max_length")
            if min_len and len(value) < min_len:
                errors.append(f"{field} must be at least {min_len} characters")
            if max_len and len(value) > max_len:
                errors.append(f"{field} must be at most {max_len} characters")

        # Numeric validations
        if isinstance(value, (int, float)):
            min_val = rules.get("min_value")
            max_val = rules.get("max_value")
            if min_val is not None and value < min_val:
                errors.append(f"{field} must be at least {min_val}")
            if max_val is not None and value > max_val:
                errors.append(f"{field} must be at most {max_val}")

        # Enum validation
        allowed = rules.get("enum")
        if allowed and value not in allowed:
            errors.append(f"{field} must be one of: {', '.join(str(v) for v in allowed)}")

    return errors


def _sanitize_strings(data, schema):
    """Auto-sanitize string fields in-place."""
    try:
        from mandarin.sanitize import sanitize_user_text
    except ImportError:
        return

    for field, rules in schema.items():
        if field in data and isinstance(data[field], str):
            if rules.get("sanitize", True):
                max_len = rules.get("max_length", 10000)
                data[field] = sanitize_user_text(data[field], max_length=max_len)

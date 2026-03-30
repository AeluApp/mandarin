"""Tests for mandarin.web.validate — request validation decorator.

Covers:
- _validate: required, type, min/max length, min/max value, enum
- _sanitize_strings: auto-sanitization of string fields
- validate_json decorator: integration with Flask request
"""

import json

import pytest

from mandarin.web.validate import _validate, _sanitize_strings


# ---------------------------------------------------------------------------
# _validate — required fields
# ---------------------------------------------------------------------------

class TestValidateRequired:

    def test_required_missing_field(self):
        errors = _validate({}, {"name": {"type": str, "required": True}})
        assert len(errors) == 1
        assert "name is required" in errors[0]

    def test_required_empty_string(self):
        errors = _validate({"name": ""}, {"name": {"type": str, "required": True}})
        assert len(errors) == 1

    def test_required_present(self):
        errors = _validate({"name": "Alice"}, {"name": {"type": str, "required": True}})
        assert errors == []

    def test_optional_missing_ok(self):
        errors = _validate({}, {"name": {"type": str}})
        assert errors == []


# ---------------------------------------------------------------------------
# _validate — type checks
# ---------------------------------------------------------------------------

class TestValidateType:

    def test_wrong_type_string_for_int(self):
        errors = _validate({"age": "old"}, {"age": {"type": int}})
        assert len(errors) == 1
        assert "int" in errors[0]

    def test_int_coerced_to_float(self):
        errors = _validate({"score": 5}, {"score": {"type": float}})
        assert errors == []

    def test_correct_type(self):
        errors = _validate({"name": "Bob"}, {"name": {"type": str}})
        assert errors == []

    def test_bool_type(self):
        errors = _validate({"flag": True}, {"flag": {"type": bool}})
        assert errors == []

    def test_list_type(self):
        errors = _validate({"items": [1, 2]}, {"items": {"type": list}})
        assert errors == []


# ---------------------------------------------------------------------------
# _validate — string length
# ---------------------------------------------------------------------------

class TestValidateStringLength:

    def test_too_short(self):
        schema = {"name": {"type": str, "min_length": 3}}
        errors = _validate({"name": "ab"}, schema)
        assert len(errors) == 1
        assert "at least 3" in errors[0]

    def test_too_long(self):
        schema = {"name": {"type": str, "max_length": 5}}
        errors = _validate({"name": "toolong"}, schema)
        assert len(errors) == 1
        assert "at most 5" in errors[0]

    def test_within_bounds(self):
        schema = {"name": {"type": str, "min_length": 2, "max_length": 10}}
        errors = _validate({"name": "Alice"}, schema)
        assert errors == []


# ---------------------------------------------------------------------------
# _validate — numeric bounds
# ---------------------------------------------------------------------------

class TestValidateNumericBounds:

    def test_below_min(self):
        schema = {"score": {"type": int, "min_value": 0}}
        errors = _validate({"score": -1}, schema)
        assert len(errors) == 1
        assert "at least 0" in errors[0]

    def test_above_max(self):
        schema = {"score": {"type": int, "max_value": 10}}
        errors = _validate({"score": 11}, schema)
        assert len(errors) == 1
        assert "at most 10" in errors[0]

    def test_within_bounds(self):
        schema = {"score": {"type": int, "min_value": 0, "max_value": 10}}
        errors = _validate({"score": 5}, schema)
        assert errors == []

    def test_zero_min_value(self):
        """min_value=0 must not be treated as falsy."""
        schema = {"score": {"type": int, "min_value": 0}}
        errors = _validate({"score": -1}, schema)
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# _validate — enum
# ---------------------------------------------------------------------------

class TestValidateEnum:

    def test_invalid_enum(self):
        schema = {"color": {"type": str, "enum": ["red", "blue"]}}
        errors = _validate({"color": "green"}, schema)
        assert len(errors) == 1
        assert "one of" in errors[0]

    def test_valid_enum(self):
        schema = {"color": {"type": str, "enum": ["red", "blue"]}}
        errors = _validate({"color": "red"}, schema)
        assert errors == []


# ---------------------------------------------------------------------------
# _sanitize_strings
# ---------------------------------------------------------------------------

class TestSanitizeStrings:

    def test_strips_html(self):
        data = {"name": "hello <script>alert(1)</script>"}
        schema = {"name": {"type": str}}
        _sanitize_strings(data, schema)
        assert "<script>" not in data["name"]

    def test_sanitize_false_skips(self):
        data = {"raw": "<b>keep</b>"}
        schema = {"raw": {"type": str, "sanitize": False}}
        _sanitize_strings(data, schema)
        assert "<b>" in data["raw"]

    def test_non_string_fields_ignored(self):
        data = {"count": 42}
        schema = {"count": {"type": int}}
        _sanitize_strings(data, schema)
        assert data["count"] == 42

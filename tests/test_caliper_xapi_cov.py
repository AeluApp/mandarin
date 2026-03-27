"""Tests for mandarin.caliper and mandarin.xapi — learning analytics export.

Covers module imports and basic functionality.
"""

import pytest


class TestCaliper:
    def test_import(self):
        import mandarin.caliper as mod
        assert hasattr(mod, '__file__')


class TestXapi:
    def test_import(self):
        import mandarin.xapi as mod
        assert hasattr(mod, '__file__')


class TestCcExport:
    def test_import(self):
        import mandarin.cc_export as mod
        assert hasattr(mod, '__file__')


class TestExport:
    def test_import(self):
        import mandarin.export as mod
        assert hasattr(mod, '__file__')

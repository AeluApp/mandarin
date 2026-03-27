"""Tests for mandarin.quality.dpmo — defects per million opportunities."""

import pytest


class TestDPMO:
    def test_import(self):
        import mandarin.quality.dpmo as mod
        assert hasattr(mod, '__file__')
        public = [x for x in dir(mod) if not x.startswith('_')]
        assert len(public) > 0

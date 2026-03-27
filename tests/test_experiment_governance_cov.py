"""Tests for mandarin.experiment_governance — experiment governance rules."""

import pytest


class TestExperimentGovernance:
    def test_import(self):
        import mandarin.experiment_governance as mod
        assert hasattr(mod, '__file__')
        public = [x for x in dir(mod) if not x.startswith('_')]
        assert len(public) > 0

"""Tests for mandarin.ai.research_synthesis — research paper synthesis."""

import pytest


class TestResearchSynthesis:
    def test_import(self):
        import mandarin.ai.research_synthesis as mod
        assert hasattr(mod, '__file__')
        public = [x for x in dir(mod) if not x.startswith('_')]
        assert len(public) > 0

"""Tests for mandarin.ai.validation — content validation functions."""

import pytest


class TestValidation:
    def test_import(self):
        import mandarin.ai.validation as mod
        assert hasattr(mod, 'validate_generated_content')
        assert hasattr(mod, 'screen_for_inappropriate_content')

    def test_validate_generated_content_vocab(self):
        from mandarin.ai.validation import validate_generated_content
        content = {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"}
        result = validate_generated_content("vocab", content)
        assert isinstance(result, dict)

    def test_validate_generated_content_passage(self):
        from mandarin.ai.validation import validate_generated_content
        content = {"body": "这是一个学习句子。", "title": "test"}
        result = validate_generated_content("passage", content)
        assert isinstance(result, dict)

    def test_screen_for_inappropriate_content(self):
        from mandarin.ai.validation import screen_for_inappropriate_content
        result = screen_for_inappropriate_content("这是一个学习句子")
        assert isinstance(result, dict)

    def test_screen_for_inappropriate_empty(self):
        from mandarin.ai.validation import screen_for_inappropriate_content
        result = screen_for_inappropriate_content("")
        assert isinstance(result, dict)

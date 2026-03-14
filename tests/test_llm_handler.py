"""Tests for mandarin.openclaw.llm_handler — intent classification and chat response."""

import json
import unittest
from dataclasses import dataclass
from unittest.mock import patch, MagicMock


class TestIntentResultDataclass(unittest.TestCase):
    """Tests for the IntentResult dataclass."""

    def test_create_with_defaults(self):
        from mandarin.openclaw.llm_handler import IntentResult
        r = IntentResult(intent="status", args={})
        self.assertEqual(r.intent, "status")
        self.assertEqual(r.args, {})
        self.assertEqual(r.reply, "")
        self.assertEqual(r.confidence, 1.0)
        self.assertFalse(r.from_llm)

    def test_create_with_all_fields(self):
        from mandarin.openclaw.llm_handler import IntentResult
        r = IntentResult(
            intent="chat", args={"key": "val"}, reply="Hi!",
            confidence=0.9, from_llm=True,
        )
        self.assertEqual(r.intent, "chat")
        self.assertEqual(r.args["key"], "val")
        self.assertEqual(r.reply, "Hi!")
        self.assertEqual(r.confidence, 0.9)
        self.assertTrue(r.from_llm)


class TestIntentsDict(unittest.TestCase):
    """Tests for the INTENTS constant."""

    def test_intents_has_expected_keys(self):
        from mandarin.openclaw.llm_handler import INTENTS
        expected = {"status", "review", "approve", "reject", "audit",
                    "briefing", "errors", "session", "help", "chat"}
        self.assertEqual(set(INTENTS.keys()), expected)

    def test_all_intent_descriptions_nonempty(self):
        from mandarin.openclaw.llm_handler import INTENTS
        for key, desc in INTENTS.items():
            self.assertTrue(len(desc) > 0, f"Intent '{key}' has empty description")


class TestClassifyWithKeywords(unittest.TestCase):
    """Tests for _classify_with_keywords (keyword fallback)."""

    def _fn(self, text):
        from mandarin.openclaw.llm_handler import _classify_with_keywords
        return _classify_with_keywords(text)

    # ── Slash commands ──

    def test_slash_status(self):
        r = self._fn("/status")
        self.assertEqual(r.intent, "status")
        self.assertEqual(r.confidence, 1.0)

    def test_slash_review(self):
        r = self._fn("/review")
        self.assertEqual(r.intent, "review")

    def test_slash_help(self):
        r = self._fn("/help")
        self.assertEqual(r.intent, "help")

    def test_slash_unknown_falls_through(self):
        r = self._fn("/unknowncmd")
        # Not in INTENTS, so falls through to keyword matching or chat
        self.assertIn(r.intent, ("chat", "help"))

    # ── Approve / reject patterns ──

    def test_approve_with_number(self):
        r = self._fn("approve 42")
        self.assertEqual(r.intent, "approve")
        self.assertEqual(r.args["item_id"], 42)
        self.assertEqual(r.confidence, 0.95)

    def test_ok_with_number(self):
        r = self._fn("ok 7")
        self.assertEqual(r.intent, "approve")
        self.assertEqual(r.args["item_id"], 7)

    def test_yes_with_number(self):
        r = self._fn("y 3")
        self.assertEqual(r.intent, "approve")
        self.assertEqual(r.args["item_id"], 3)

    def test_reject_with_number(self):
        r = self._fn("reject 10")
        self.assertEqual(r.intent, "reject")
        self.assertEqual(r.args["item_id"], 10)

    def test_reject_with_reason(self):
        r = self._fn("reject 10 bad quality")
        self.assertEqual(r.intent, "reject")
        self.assertEqual(r.args["item_id"], 10)
        self.assertEqual(r.args["reason"], "bad quality")

    def test_no_with_number(self):
        r = self._fn("no 5")
        self.assertEqual(r.intent, "reject")
        self.assertEqual(r.args["item_id"], 5)

    # ── Keyword matching ──

    def test_keyword_status_due(self):
        r = self._fn("how many items are due today")
        self.assertEqual(r.intent, "status")
        self.assertEqual(r.confidence, 0.7)

    def test_keyword_status_streak(self):
        r = self._fn("what's my streak")
        self.assertEqual(r.intent, "status")

    def test_keyword_review_queue(self):
        r = self._fn("show me the review queue")
        self.assertEqual(r.intent, "review")

    def test_keyword_audit(self):
        r = self._fn("latest audit results please")
        self.assertEqual(r.intent, "audit")

    def test_keyword_briefing_tutor(self):
        r = self._fn("tutor prep for tomorrow")
        self.assertEqual(r.intent, "briefing")

    def test_keyword_errors_mistake(self):
        r = self._fn("show my mistakes")
        self.assertEqual(r.intent, "errors")

    def test_keyword_session_practice(self):
        r = self._fn("let's practice")
        self.assertEqual(r.intent, "session")

    def test_keyword_help_question_mark(self):
        r = self._fn("?")
        self.assertEqual(r.intent, "help")

    def test_keyword_no_match_returns_chat(self):
        r = self._fn("I like bananas")
        self.assertEqual(r.intent, "chat")
        self.assertEqual(r.confidence, 0.5)


class TestExtractArgs(unittest.TestCase):
    """Tests for _extract_args helper."""

    def _fn(self, cmd, arg_text):
        from mandarin.openclaw.llm_handler import _extract_args
        return _extract_args(cmd, arg_text)

    def test_approve_extracts_item_id(self):
        args = self._fn("approve", "42")
        self.assertEqual(args["item_id"], 42)

    def test_reject_extracts_item_id_and_reason(self):
        args = self._fn("reject", "7 not good enough")
        self.assertEqual(args["item_id"], 7)
        self.assertEqual(args["reason"], "not good enough")

    def test_reject_without_reason(self):
        args = self._fn("reject", "7")
        self.assertEqual(args["item_id"], 7)
        self.assertNotIn("reason", args)

    def test_approve_non_numeric_arg(self):
        args = self._fn("approve", "abc")
        self.assertNotIn("item_id", args)

    def test_non_approve_reject_returns_empty(self):
        args = self._fn("status", "anything")
        self.assertEqual(args, {})

    def test_empty_arg_text(self):
        args = self._fn("approve", "")
        self.assertEqual(args, {})


class TestClassifyWithLLM(unittest.TestCase):
    """Tests for _classify_with_llm via mock."""

    def _make_response(self, success=True, text="", error=None):
        resp = MagicMock()
        resp.success = success
        resp.text = text
        resp.error = error
        return resp

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_successful_classification(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(
            text='{"intent": "status", "args": {}, "reply": "Checking status."}'
        )
        result = _classify_with_llm("what's my status")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "status")
        self.assertEqual(result.reply, "Checking status.")
        self.assertTrue(result.from_llm)
        self.assertEqual(result.confidence, 0.9)

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_llm_returns_markdown_wrapped_json(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(
            text='```json\n{"intent": "review", "args": {}, "reply": "ok"}\n```'
        )
        result = _classify_with_llm("review queue")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "review")

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_llm_failure_returns_none(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(success=False, error="timeout")
        result = _classify_with_llm("hello")
        self.assertIsNone(result)

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_invalid_json_returns_none(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(text="not json at all")
        result = _classify_with_llm("hello")
        self.assertIsNone(result)

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_unknown_intent_mapped_to_chat(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(
            text='{"intent": "nonexistent", "args": {}, "reply": "hmm"}'
        )
        result = _classify_with_llm("something")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "chat")

    @patch("mandarin.openclaw.llm_handler.generate")
    def test_missing_intent_defaults_to_chat(self, mock_gen):
        from mandarin.openclaw.llm_handler import _classify_with_llm
        mock_gen.return_value = self._make_response(
            text='{"args": {}, "reply": "hi"}'
        )
        result = _classify_with_llm("hi")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "chat")


class TestClassifyIntent(unittest.TestCase):
    """Tests for classify_intent — the top-level dispatcher."""

    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=False)
    def test_falls_back_to_keywords_when_ollama_unavailable(self, mock_avail):
        from mandarin.openclaw.llm_handler import classify_intent
        result = classify_intent("/status")
        self.assertEqual(result.intent, "status")
        self.assertFalse(result.from_llm)

    @patch("mandarin.openclaw.llm_handler._classify_with_llm", return_value=None)
    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=True)
    def test_falls_back_when_llm_returns_none(self, mock_avail, mock_llm):
        from mandarin.openclaw.llm_handler import classify_intent
        result = classify_intent("what's my streak")
        self.assertEqual(result.intent, "status")
        self.assertFalse(result.from_llm)

    @patch("mandarin.openclaw.llm_handler._classify_with_llm")
    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=True)
    def test_uses_llm_result_when_available(self, mock_avail, mock_llm):
        from mandarin.openclaw.llm_handler import IntentResult, classify_intent
        mock_llm.return_value = IntentResult(
            intent="audit", args={}, reply="Audit coming.",
            confidence=0.9, from_llm=True,
        )
        result = classify_intent("show me audit")
        self.assertEqual(result.intent, "audit")
        self.assertTrue(result.from_llm)


class TestGenerateChatResponse(unittest.TestCase):
    """Tests for generate_chat_response."""

    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=False)
    def test_fallback_when_no_ollama(self, mock_avail):
        from mandarin.openclaw.llm_handler import generate_chat_response
        result = generate_chat_response("hi there")
        self.assertIn("/status", result)
        self.assertIn("/review", result)

    @patch("mandarin.openclaw.llm_handler.generate")
    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=True)
    def test_returns_llm_text_on_success(self, mock_avail, mock_gen):
        from mandarin.openclaw.llm_handler import generate_chat_response
        resp = MagicMock()
        resp.success = True
        resp.text = "  Hello from Aelu!  "
        mock_gen.return_value = resp
        result = generate_chat_response("hi")
        self.assertEqual(result, "Hello from Aelu!")

    @patch("mandarin.openclaw.llm_handler.generate")
    @patch("mandarin.openclaw.llm_handler.is_ollama_available", return_value=True)
    def test_returns_fallback_on_llm_failure(self, mock_avail, mock_gen):
        from mandarin.openclaw.llm_handler import generate_chat_response
        resp = MagicMock()
        resp.success = False
        mock_gen.return_value = resp
        result = generate_chat_response("hi")
        self.assertIn("/status", result)


class TestSystemPrompt(unittest.TestCase):
    """Tests for the SYSTEM_PROMPT template."""

    def test_prompt_contains_intent_placeholder(self):
        from mandarin.openclaw.llm_handler import SYSTEM_PROMPT
        self.assertIn("{intents}", SYSTEM_PROMPT)

    def test_prompt_mentions_json(self):
        from mandarin.openclaw.llm_handler import SYSTEM_PROMPT
        self.assertIn("JSON", SYSTEM_PROMPT)

    def test_prompt_mentions_aelu(self):
        from mandarin.openclaw.llm_handler import SYSTEM_PROMPT
        self.assertIn("Aelu", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()

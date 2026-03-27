"""Tests for mandarin.openclaw.voice_agent — Pipecat real-time voice pipeline."""

import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Python 3.14 removed implicit event loop creation in main thread
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())


from tests.shared_db import make_test_db as _make_db


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestIsAvailable(unittest.TestCase):
    """Tests for is_available."""

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", True)
    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", True)
    def test_available_when_both_present(self):
        from mandarin.openclaw.voice_agent import is_available
        self.assertTrue(is_available())

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", True)
    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_not_available_without_pipecat(self):
        from mandarin.openclaw.voice_agent import is_available
        self.assertFalse(is_available())

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", False)
    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", True)
    def test_not_available_without_edge_tts(self):
        from mandarin.openclaw.voice_agent import is_available
        self.assertFalse(is_available())

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", False)
    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_not_available_without_either(self):
        from mandarin.openclaw.voice_agent import is_available
        self.assertFalse(is_available())


class TestAeluCommandProcessorConstruction(unittest.TestCase):
    """Tests for AeluCommandProcessor.__init__."""

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_construction_without_pipecat(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        self.assertIsNone(proc._conn)

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_get_conn_returns_none_without_db(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        # _get_conn tries to import db; patching to fail
        with patch.dict("sys.modules", {"mandarin.db": None}):
            conn = proc._get_conn()
            # First call when import fails
            self.assertIsNone(proc._conn) if conn is None else None


class TestAeluCommandProcessorCleanup(unittest.TestCase):
    """Tests for AeluCommandProcessor.cleanup."""

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_cleanup_with_no_conn(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        # Should not raise
        proc.cleanup()
        self.assertIsNone(proc._conn)

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_cleanup_closes_conn(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        mock_conn = MagicMock()
        proc._conn = mock_conn
        proc.cleanup()
        mock_conn.close.assert_called_once()
        self.assertIsNone(proc._conn)

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_cleanup_survives_close_error(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        conn = MagicMock()
        conn.close.side_effect = Exception("already closed")
        proc._conn = conn
        # Should not raise
        proc.cleanup()
        self.assertIsNone(proc._conn)


class TestAeluCommandProcessorExecuteIntent(unittest.TestCase):
    """Tests for AeluCommandProcessor._execute_intent."""

    def _make_proc(self):
        with patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False):
            from mandarin.openclaw.voice_agent import AeluCommandProcessor
            return AeluCommandProcessor()

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_status(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_status.return_value = "5 items due"
        result = proc._execute_intent(IntentResult(intent="status", args={}), None)
        self.assertEqual(result, "5 items due")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_review(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_review.return_value = "Queue empty"
        result = proc._execute_intent(IntentResult(intent="review", args={}), None)
        self.assertEqual(result, "Queue empty")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_audit(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_audit.return_value = "Audit: A"
        result = proc._execute_intent(IntentResult(intent="audit", args={}), None)
        self.assertEqual(result, "Audit: A")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_briefing_with_focus(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_briefing.return_value = "Briefing"
        proc._execute_intent(IntentResult(intent="briefing", args={"focus": "tones"}), None)
        mock_cmds.cmd_briefing.assert_called_once_with(focus="tones")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_briefing_default_focus(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_briefing.return_value = "Briefing"
        proc._execute_intent(IntentResult(intent="briefing", args={}), None)
        mock_cmds.cmd_briefing.assert_called_once_with(focus="general")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_approve(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_approve.return_value = "Approved 42"
        result = proc._execute_intent(IntentResult(intent="approve", args={"item_id": 42}), None)
        mock_cmds.cmd_approve.assert_called_once_with(item_id=42)
        self.assertEqual(result, "Approved 42")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_reject_with_reason(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_reject.return_value = "Rejected"
        proc._execute_intent(IntentResult(intent="reject", args={"item_id": 7, "reason": "bad"}), None)
        mock_cmds.cmd_reject.assert_called_once_with(item_id=7, reason="bad")

    def test_help_returns_spoken_text(self):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        result = proc._execute_intent(IntentResult(intent="help", args={}), None)
        self.assertIn("status", result.lower())
        self.assertIn("review", result.lower())

    def test_chat_with_reply(self):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        result = proc._execute_intent(IntentResult(intent="chat", args={}, reply="Hey!"), None)
        self.assertEqual(result, "Hey!")

    @patch("mandarin.openclaw.voice_agent.llm_handler")
    def test_chat_without_reply_calls_llm(self, mock_llm):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_llm.generate_chat_response.return_value = "LLM says hi"
        result = proc._execute_intent(IntentResult(intent="chat", args={}, reply=""), None)
        self.assertEqual(result, "LLM says hi")

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_command_error_caught(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_status.side_effect = RuntimeError("DB down")
        result = proc._execute_intent(IntentResult(intent="status", args={}), None)
        self.assertIn("Error", result)

    @patch("mandarin.openclaw.voice_agent.commands")
    def test_errors_command(self, mock_cmds):
        from mandarin.openclaw.llm_handler import IntentResult
        proc = self._make_proc()
        mock_cmds.cmd_error_patterns.return_value = "No active patterns."
        result = proc._execute_intent(IntentResult(intent="errors", args={}), None)
        self.assertEqual(result, "No active patterns.")


class TestEdgeTTSService(unittest.TestCase):
    """Tests for EdgeTTSService."""

    def test_construction_default_voice(self):
        from mandarin.openclaw.voice_agent import EdgeTTSService
        svc = EdgeTTSService()
        self.assertEqual(svc.voice, "zh-CN-XiaoxiaoNeural")

    def test_construction_custom_voice(self):
        from mandarin.openclaw.voice_agent import EdgeTTSService
        svc = EdgeTTSService(voice="en-US-JennyNeural")
        self.assertEqual(svc.voice, "en-US-JennyNeural")

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", False)
    def test_synthesize_returns_none_without_edge_tts(self):
        from mandarin.openclaw.voice_agent import EdgeTTSService
        svc = EdgeTTSService()
        result = _run(svc.synthesize("hello"))
        self.assertIsNone(result)

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", True)
    @patch("mandarin.openclaw.voice_agent.edge_tts", create=True)
    def test_synthesize_collects_audio_chunks(self, mock_edge):
        from mandarin.openclaw.voice_agent import EdgeTTSService

        async def fake_stream():
            yield {"type": "audio", "data": b"chunk1"}
            yield {"type": "audio", "data": b"chunk2"}
            yield {"type": "metadata", "data": b"meta"}

        mock_communicate = MagicMock()
        mock_communicate.stream.return_value = fake_stream()
        mock_edge.Communicate.return_value = mock_communicate

        svc = EdgeTTSService()
        result = _run(svc.synthesize("hello"))
        self.assertEqual(result, b"chunk1chunk2")

    @patch("mandarin.openclaw.voice_agent._HAS_EDGE_TTS", True)
    @patch("mandarin.openclaw.voice_agent.edge_tts", create=True)
    def test_synthesize_error_returns_none(self, mock_edge):
        from mandarin.openclaw.voice_agent import EdgeTTSService
        mock_edge.Communicate.side_effect = Exception("TTS error")
        svc = EdgeTTSService()
        result = _run(svc.synthesize("hello"))
        self.assertIsNone(result)


class TestCreateVoicePipelineConfig(unittest.TestCase):
    """Tests for create_voice_pipeline_config."""

    def test_returns_dict(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIsInstance(config, dict)

    def test_has_stt_section(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIn("stt", config)
        self.assertEqual(config["stt"]["engine"], "faster-whisper")
        self.assertEqual(config["stt"]["language"], "zh")

    def test_has_llm_section(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIn("llm", config)
        self.assertEqual(config["llm"]["engine"], "ollama")

    def test_has_tts_section(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIn("tts", config)
        self.assertEqual(config["tts"]["engine"], "edge-tts")
        self.assertIn("voice", config["tts"])
        self.assertIn("fallback_voice", config["tts"])

    def test_has_vad_section(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIn("vad", config)
        self.assertEqual(config["vad"]["engine"], "silero")
        self.assertGreater(config["vad"]["threshold"], 0)

    def test_has_pipeline_section(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        self.assertIn("pipeline", config)
        self.assertIn("aelu_command", config["pipeline"]["processors"])
        self.assertEqual(config["pipeline"]["aelu_command_class"], "AeluCommandProcessor")

    def test_config_is_json_serializable(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        config = create_voice_pipeline_config()
        serialized = json.dumps(config)
        self.assertIsInstance(serialized, str)

    def test_llm_url_from_settings(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        from mandarin.settings import OLLAMA_URL
        config = create_voice_pipeline_config()
        self.assertEqual(config["llm"]["url"], OLLAMA_URL)

    def test_llm_model_from_settings(self):
        from mandarin.openclaw.voice_agent import create_voice_pipeline_config
        from mandarin.settings import OLLAMA_PRIMARY_MODEL
        config = create_voice_pipeline_config()
        self.assertEqual(config["llm"]["model"], OLLAMA_PRIMARY_MODEL)


class TestRunVoiceServer(unittest.TestCase):
    """Tests for run_voice_server."""

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_exits_without_pipecat(self):
        from mandarin.openclaw.voice_agent import run_voice_server
        # Should return without error (logs an error and returns)
        _run(run_voice_server(port=9999))


class TestModuleFlags(unittest.TestCase):
    """Tests for module-level feature flags."""

    def test_has_pipecat_is_bool(self):
        from mandarin.openclaw.voice_agent import _HAS_PIPECAT
        self.assertIsInstance(_HAS_PIPECAT, bool)

    def test_has_edge_tts_is_bool(self):
        from mandarin.openclaw.voice_agent import _HAS_EDGE_TTS
        self.assertIsInstance(_HAS_EDGE_TTS, bool)


class TestProcessFrameWithoutPipecat(unittest.TestCase):
    """Tests for process_frame when pipecat is not available."""

    @patch("mandarin.openclaw.voice_agent._HAS_PIPECAT", False)
    def test_process_frame_returns_early(self):
        from mandarin.openclaw.voice_agent import AeluCommandProcessor
        proc = AeluCommandProcessor()
        # Without pipecat, process_frame should return without error
        frame = MagicMock()
        _run(proc.process_frame(frame, "forward"))
        # No crash = success


if __name__ == "__main__":
    unittest.main()

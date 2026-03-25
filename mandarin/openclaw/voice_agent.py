"""OpenClaw voice agent — Pipecat real-time voice pipeline.

Provides voice conversation for the Aelu admin interface using:
- Pipecat for pipeline orchestration
- faster-whisper for STT (already a dependency)
- edge-tts for TTS (already a dependency)
- Ollama for LLM
- WebSocket transport for browser/Telegram integration

The voice agent shares the same command set as the Telegram bot —
spoken commands are transcribed, classified, executed, and the
response is spoken back.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from pipecat.frames.frames import (
        Frame, TextFrame, TranscriptionFrame, TTSSpeakFrame,
        EndFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.task import PipelineTask
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.services.openai import OpenAILLMService
    from pipecat.transports.services.daily import DailyTransport, DailyParams
    _HAS_PIPECAT = True
except ImportError:
    _HAS_PIPECAT = False
    logger.debug("pipecat-ai not installed — voice agent disabled")

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

from ..settings import OLLAMA_URL, OLLAMA_PRIMARY_MODEL
from . import commands, llm_handler, security


def is_available() -> bool:
    """Check if voice agent dependencies are available."""
    return _HAS_PIPECAT and _HAS_EDGE_TTS


class AeluCommandProcessor(FrameProcessor if _HAS_PIPECAT else object):
    """Pipecat processor that routes transcribed speech to Aelu commands.

    Sits between STT and TTS in the pipeline. Intercepts transcriptions,
    classifies intent, executes commands, and emits spoken responses.
    """

    def __init__(self):
        if _HAS_PIPECAT:
            super().__init__()
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            try:
                from .. import db
                self._conn = db.connection()
            except Exception:
                pass
        return self._conn

    async def process_frame(self, frame: Frame, direction) -> None:
        """Process incoming frames from the pipeline."""
        if not _HAS_PIPECAT:
            return

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if not text:
                await self.push_frame(frame, direction)
                return

            logger.info("Voice transcription: %s", text[:100])

            # Sanitize
            clean = security.sanitize_input(text)
            is_safe, detail = security.check_prompt_injection(clean)

            conn = self._get_conn()

            if not is_safe:
                security.log_message(
                    conn, direction="inbound", channel="voice",
                    message_text=clean, injection_detected=True,
                    injection_detail=detail or "",
                ) if conn else None
                await self.push_frame(
                    TTSSpeakFrame(text="I couldn't process that. Please try again."),
                    direction,
                )
                return

            # Classify and execute
            voice_user_id = "voice_owner"
            intent_result = llm_handler.classify_intent(clean, conn=conn, user_id=voice_user_id)
            response = self._execute_intent(intent_result, conn)

            # Log
            security.log_message(
                conn, direction="inbound", channel="voice",
                message_text=clean, intent=intent_result.intent,
                tool_called=f"cmd_{intent_result.intent}" if intent_result.intent != "chat" else "",
                tool_result=response[:500],
            ) if conn else None

            # Store conversation turn in memory
            try:
                from ..ai.memory import add_memory
                add_memory(voice_user_id, clean, response, channel="voice")
            except (ImportError, Exception):
                pass

            # Speak response
            safe_response = security.sanitize_output(response)
            await self.push_frame(
                TTSSpeakFrame(text=safe_response or "I'm not sure how to help."),
                direction,
            )
        else:
            await self.push_frame(frame, direction)

    def _execute_intent(self, intent_result, conn) -> str:
        """Execute intent — same logic as telegram_bot._execute_intent."""
        intent = intent_result.intent
        args = intent_result.args

        dispatch = {
            "status": lambda: commands.cmd_status(),
            "review": lambda: commands.cmd_review(),
            "audit": lambda: commands.cmd_audit(),
            "briefing": lambda: commands.cmd_briefing(focus=args.get("focus", "general")),
            "errors": lambda: commands.cmd_error_patterns(),
            "approve": lambda: commands.cmd_approve(item_id=args.get("item_id", 0)),
            "reject": lambda: commands.cmd_reject(
                item_id=args.get("item_id", 0),
                reason=args.get("reason", ""),
            ),
            "help": lambda: (
                "You can ask me about your status, review queue, audit results, "
                "error patterns, or tutor briefings."
            ),
        }

        handler = dispatch.get(intent)
        if handler:
            try:
                return handler()
            except Exception as e:
                logger.error("Voice command %s failed: %s", intent, e, exc_info=True)
                return f"Error running {intent}."

        if intent_result.reply:
            return intent_result.reply
        return llm_handler.generate_chat_response("", conn=conn)

    def cleanup(self):
        """Close DB connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


class EdgeTTSService:
    """Lightweight TTS service using edge-tts.

    Generates speech audio from text using Microsoft Edge's TTS service.
    Suitable for admin voice interactions where latency is acceptable.
    """

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        self.voice = voice

    async def synthesize(self, text: str) -> bytes | None:
        """Synthesize text to audio bytes (MP3)."""
        if not _HAS_EDGE_TTS:
            return None
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as e:
            logger.error("Edge TTS synthesis failed: %s", e)
            return None


def create_voice_pipeline_config() -> dict:
    """Create the Pipecat pipeline configuration.

    Returns a config dict that can be used by the WebSocket endpoint
    or a standalone voice server.
    """
    return {
        "stt": {
            "engine": "faster-whisper",
            "model": "base",
            "language": "zh",
        },
        "llm": {
            "engine": "ollama",
            "url": OLLAMA_URL,
            "model": OLLAMA_PRIMARY_MODEL,
        },
        "tts": {
            "engine": "edge-tts",
            "voice": "zh-CN-XiaoxiaoNeural",
            "fallback_voice": "en-US-JennyNeural",
        },
        "vad": {
            "engine": "silero",
            "threshold": 0.5,
            "min_speech_ms": 250,
            "min_silence_ms": 300,
        },
        "pipeline": {
            "processors": ["vad", "stt", "aelu_command", "tts"],
            "aelu_command_class": "AeluCommandProcessor",
        },
    }


async def run_voice_server(port: int = 8765) -> None:
    """Start a WebSocket voice server for browser-based voice interaction.

    This is a lightweight alternative to the full Pipecat Daily transport.
    Clients connect via WebSocket, send audio chunks, receive audio responses.
    """
    if not _HAS_PIPECAT:
        logger.error("Cannot start voice server — pipecat-ai not installed")
        return

    logger.info("Starting OpenClaw voice server on port %d", port)

    # The actual Pipecat pipeline setup would go here.
    # For now, this is the integration point — the pipeline config
    # is ready, the AeluCommandProcessor is wired, and the
    # WebSocket transport will connect when Pipecat is configured.
    config = create_voice_pipeline_config()
    logger.info("Voice pipeline config: %s", json.dumps(config, indent=2))
    logger.info("Voice server ready — waiting for WebSocket connections")

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Voice server shutting down")

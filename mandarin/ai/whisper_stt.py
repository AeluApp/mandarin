"""Whisper STT integration — speech-to-text for dictation and speaking drills.

Supports three backends in priority order:
1. Local whisper.cpp via subprocess (fastest, no network)
2. OpenAI Whisper API (if OPENAI_API_KEY set)
3. Browser Web Speech API (existing fallback via SpeechRecognition)

All backends return a common TranscriptResult with text, confidence,
and per-segment timing for aligned feedback.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    text: str
    start_ms: int = 0
    end_ms: int = 0
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    success: bool
    text: str = ""
    language: str = "zh"
    segments: list[TranscriptSegment] = field(default_factory=list)
    confidence: float = 0.0
    backend: str = ""
    duration_ms: int = 0
    error: Optional[str] = None


def transcribe(
    audio_path: str,
    language: str = "zh",
    task: str = "transcribe",
) -> TranscriptResult:
    """Transcribe audio file to text. Tries backends in priority order.

    Args:
        audio_path: Path to WAV/MP3/M4A audio file.
        language: ISO language code (default "zh" for Mandarin).
        task: "transcribe" or "translate" (to English).

    Returns:
        TranscriptResult with text, segments, and metadata.
    """
    if not os.path.exists(audio_path):
        return TranscriptResult(success=False, error=f"File not found: {audio_path}")

    # Try local whisper.cpp first
    result = _try_whisper_cpp(audio_path, language, task)
    if result and result.success:
        return result

    # Try OpenAI Whisper API
    result = _try_openai_whisper(audio_path, language, task)
    if result and result.success:
        return result

    # Try local whisper Python package
    result = _try_whisper_python(audio_path, language, task)
    if result and result.success:
        return result

    return TranscriptResult(
        success=False,
        error="No Whisper backend available. Install whisper.cpp, openai-whisper, or set OPENAI_API_KEY.",
    )


def is_whisper_available() -> bool:
    """Check if any Whisper backend is available."""
    # Check whisper.cpp
    if _find_whisper_cpp():
        return True
    # Check OpenAI API key
    if os.environ.get("OPENAI_API_KEY"):
        return True
    # Check local whisper package
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def transcribe_numpy(
    audio_array,
    sample_rate: int = 16000,
    language: str = "zh",
) -> TranscriptResult:
    """Transcribe from a numpy array (e.g., from sounddevice recording).

    Writes to temp WAV file, then delegates to transcribe().
    """
    try:
        import numpy as np
        import wave
    except ImportError:
        return TranscriptResult(success=False, error="numpy/wave not available")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
        # Ensure mono float32 -> int16
        if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
            audio_int16 = (audio_array * 32767).astype(np.int16)
        else:
            audio_int16 = audio_array.astype(np.int16)

        if len(audio_int16.shape) > 1:
            audio_int16 = audio_int16[:, 0]  # mono

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

    try:
        return transcribe(tmp_path, language=language)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Backends ─────────────────────────────────────────

def _find_whisper_cpp() -> Optional[str]:
    """Find whisper.cpp binary on PATH or common locations."""
    for name in ("whisper-cpp", "whisper", "main"):
        try:
            result = subprocess.run(
                ["which", name], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path and os.path.isfile(path):
                    return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    # Check common homebrew / build locations
    for p in (
        Path.home() / "whisper.cpp" / "main",
        Path("/usr/local/bin/whisper-cpp"),
        Path("/opt/homebrew/bin/whisper-cpp"),
    ):
        if p.exists():
            return str(p)
    return None


def _find_whisper_model() -> Optional[str]:
    """Find a whisper.cpp model file."""
    model_dir = Path.home() / "whisper.cpp" / "models"
    if not model_dir.exists():
        model_dir = Path.home() / ".cache" / "whisper"
    if not model_dir.exists():
        return None

    # Prefer medium or small models for Chinese
    for pattern in ("*medium*", "*small*", "*base*", "*tiny*"):
        matches = list(model_dir.glob(pattern))
        if matches:
            return str(matches[0])
    return None


def _try_whisper_cpp(
    audio_path: str, language: str, task: str,
) -> Optional[TranscriptResult]:
    """Try transcription via whisper.cpp binary."""
    binary = _find_whisper_cpp()
    if not binary:
        return None

    model = _find_whisper_model()
    if not model:
        logger.debug("whisper.cpp found but no model file")
        return None

    start = time.monotonic()
    try:
        cmd = [
            binary, "-m", model, "-f", audio_path,
            "-l", language, "--output-json", "--no-timestamps",
        ]
        if task == "translate":
            cmd.append("--translate")

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.returncode != 0:
            return TranscriptResult(
                success=False, backend="whisper.cpp",
                duration_ms=elapsed_ms, error=result.stderr[:200],
            )

        # Parse JSON output
        text = result.stdout.strip()
        try:
            data = json.loads(text)
            transcription = data.get("transcription", [])
            full_text = " ".join(
                seg.get("text", "") for seg in transcription
            ).strip()
            segments = [
                TranscriptSegment(
                    text=seg.get("text", ""),
                    start_ms=int(seg.get("offsets", {}).get("from", 0)),
                    end_ms=int(seg.get("offsets", {}).get("to", 0)),
                )
                for seg in transcription
            ]
        except (json.JSONDecodeError, KeyError):
            full_text = text
            segments = []

        return TranscriptResult(
            success=bool(full_text),
            text=full_text,
            language=language,
            segments=segments,
            backend="whisper.cpp",
            duration_ms=elapsed_ms,
        )
    except subprocess.TimeoutExpired:
        return TranscriptResult(
            success=False, backend="whisper.cpp",
            duration_ms=int((time.monotonic() - start) * 1000),
            error="timeout",
        )
    except Exception as e:
        return TranscriptResult(
            success=False, backend="whisper.cpp", error=str(e),
        )


def _try_openai_whisper(
    audio_path: str, language: str, task: str,
) -> Optional[TranscriptResult]:
    """Try transcription via OpenAI Whisper API."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    start = time.monotonic()
    try:
        import httpx

        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            data = {"model": "whisper-1", "language": language}
            if task == "translate":
                endpoint = "https://api.openai.com/v1/audio/translations"
            else:
                endpoint = "https://api.openai.com/v1/audio/transcriptions"
                data["response_format"] = "verbose_json"

            resp = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
                timeout=30.0,
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code != 200:
            return TranscriptResult(
                success=False, backend="openai",
                duration_ms=elapsed_ms,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        result = resp.json()
        text = result.get("text", "").strip()
        segments = []
        for seg in result.get("segments", []):
            segments.append(TranscriptSegment(
                text=seg.get("text", ""),
                start_ms=int(seg.get("start", 0) * 1000),
                end_ms=int(seg.get("end", 0) * 1000),
                confidence=seg.get("avg_logprob", 0.0),
            ))

        return TranscriptResult(
            success=bool(text),
            text=text,
            language=result.get("language", language),
            segments=segments,
            confidence=sum(s.confidence for s in segments) / max(len(segments), 1),
            backend="openai",
            duration_ms=elapsed_ms,
        )
    except ImportError:
        return None
    except Exception as e:
        return TranscriptResult(
            success=False, backend="openai", error=str(e),
        )


def _try_whisper_python(
    audio_path: str, language: str, task: str,
) -> Optional[TranscriptResult]:
    """Try transcription via local openai-whisper Python package."""
    try:
        import whisper
    except ImportError:
        return None

    start = time.monotonic()
    try:
        model = whisper.load_model("base")
        result = model.transcribe(
            audio_path, language=language, task=task,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        text = result.get("text", "").strip()
        segments = []
        for seg in result.get("segments", []):
            segments.append(TranscriptSegment(
                text=seg.get("text", ""),
                start_ms=int(seg.get("start", 0) * 1000),
                end_ms=int(seg.get("end", 0) * 1000),
                confidence=seg.get("avg_logprob", 0.0),
            ))

        return TranscriptResult(
            success=bool(text),
            text=text,
            language=result.get("language", language),
            segments=segments,
            backend="whisper_python",
            duration_ms=elapsed_ms,
        )
    except Exception as e:
        return TranscriptResult(
            success=False, backend="whisper_python", error=str(e),
        )

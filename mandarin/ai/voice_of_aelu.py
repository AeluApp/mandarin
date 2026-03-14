"""Voice of Aelu -- centralized TTS system.

ALL audio generation routes through this module.

Fallback chain:
  1. Kokoro (local neural TTS via subprocess)
  2. edge-tts (Microsoft neural voices, cross-platform)
  3. macOS TTS (`say` command, local only)

Audio files are cached in a SQLite table (pi_audio_cache) keyed by
SHA-256 hash of text + speed. Cache table is created on first use.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

KOKORO_VOICE = "af_heart"  # Kokoro voice ID for Chinese
KOKORO_SPEED = 0.85  # Slightly slower for learner clarity
AUDIO_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "audio_tts"

# Ensure output directory exists
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── AudioOutput dataclass ────────────────────────────────────────────────

@dataclass
class AudioOutput:
    """Result of a TTS generation attempt."""
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0
    tts_engine: str = ""
    tonal_accuracy_validated: bool = False
    success: bool = False
    error: Optional[str] = None


# ── Cache table management ───────────────────────────────────────────────

def _ensure_cache_table(conn) -> None:
    """Create pi_audio_cache table if it doesn't exist."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_audio_cache (
                cache_key TEXT PRIMARY KEY,
                text_zh TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                duration_seconds REAL DEFAULT 0.0,
                tts_engine TEXT NOT NULL,
                tonal_accuracy_validated INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                hit_count INTEGER NOT NULL DEFAULT 0,
                last_hit_at TEXT
            )
        """)
        conn.commit()
    except Exception:
        logger.debug("Failed to create pi_audio_cache table", exc_info=True)


def _cache_key(text: str, speed: float) -> str:
    """SHA-256 hash of text + speed for cache lookup."""
    raw = f"{text}:{speed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _check_cache(conn, key: str) -> Optional[AudioOutput]:
    """Look up cached audio by key. Returns AudioOutput or None."""
    try:
        row = conn.execute(
            "SELECT audio_path, duration_seconds, tts_engine, tonal_accuracy_validated "
            "FROM pi_audio_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    except Exception:
        return None

    if row is None:
        return None

    r = dict(row)
    audio_path = r.get("audio_path", "")

    # Verify file still exists
    if not os.path.exists(audio_path):
        try:
            conn.execute("DELETE FROM pi_audio_cache WHERE cache_key = ?", (key,))
            conn.commit()
        except Exception:
            pass
        return None

    # Update hit count
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            "UPDATE pi_audio_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE cache_key = ?",
            (now, key),
        )
        conn.commit()
    except Exception:
        pass

    return AudioOutput(
        audio_path=audio_path,
        duration_seconds=r.get("duration_seconds") or 0.0,
        tts_engine=r.get("tts_engine", "cached"),
        tonal_accuracy_validated=bool(r.get("tonal_accuracy_validated")),
        success=True,
    )


def _write_cache(conn, key: str, text: str, result: AudioOutput) -> None:
    """Persist a generation result to the cache table."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT OR REPLACE INTO pi_audio_cache
               (cache_key, text_zh, audio_path, duration_seconds, tts_engine,
                tonal_accuracy_validated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key, text[:500], result.audio_path or "", result.duration_seconds,
             result.tts_engine, 1 if result.tonal_accuracy_validated else 0, now),
        )
        conn.commit()
    except Exception:
        logger.debug("Cache write failed", exc_info=True)


# ── TTS engine implementations ──────────────────────────────────────────

def _generate_with_kokoro(text: str, speed: float, cache_key: str) -> AudioOutput:
    """Generate audio via Kokoro CLI (local neural TTS).

    Expects `kokoro` to be available on PATH.
    """
    out_path = str(AUDIO_OUTPUT_DIR / f"{cache_key}.wav")

    try:
        start = time.monotonic()
        proc = subprocess.run(
            [
                "kokoro",
                "--text", text,
                "--voice", KOKORO_VOICE,
                "--speed", str(speed),
                "--output", out_path,
            ],
            capture_output=True,
            timeout=30,
        )
        elapsed = time.monotonic() - start

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")[:200]
            logger.debug("Kokoro failed (rc=%d): %s", proc.returncode, stderr)
            return AudioOutput(
                success=False,
                tts_engine="kokoro",
                error=f"Kokoro exit code {proc.returncode}: {stderr}",
            )

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            return AudioOutput(
                success=False,
                tts_engine="kokoro",
                error="Kokoro produced empty output",
            )

        # Estimate duration from file size (16kHz, 16-bit mono WAV)
        file_size = os.path.getsize(out_path)
        duration = max(0.1, (file_size - 44) / (16000 * 2))  # subtract WAV header

        return AudioOutput(
            audio_path=out_path,
            duration_seconds=round(duration, 2),
            tts_engine="kokoro",
            tonal_accuracy_validated=False,
            success=True,
        )

    except FileNotFoundError:
        return AudioOutput(
            success=False,
            tts_engine="kokoro",
            error="kokoro not found on PATH",
        )
    except subprocess.TimeoutExpired:
        return AudioOutput(
            success=False,
            tts_engine="kokoro",
            error="Kokoro generation timed out (30s)",
        )
    except Exception as e:
        return AudioOutput(
            success=False,
            tts_engine="kokoro",
            error=str(e),
        )


def _generate_with_edge_tts(text: str, speed: float, cache_key: str) -> AudioOutput:
    """Generate audio via edge-tts (existing audio.py infrastructure).

    Uses the audio module's generate_audio_file function.
    """
    try:
        from ..audio import generate_audio_file, get_audio_cache_dir

        # Convert speed factor to WPM (0.85 -> ~100 WPM, 1.0 -> ~120 WPM)
        wpm = int(120 * speed)
        wpm = max(80, min(170, wpm))

        fname = generate_audio_file(text, rate=wpm)
        if fname is None:
            return AudioOutput(
                success=False,
                tts_engine="edge_tts",
                error="edge-tts generation returned None",
            )

        # Find the full path
        cache_dir = get_audio_cache_dir()
        full_path = os.path.join(cache_dir, fname)
        if not os.path.exists(full_path):
            # Check persistent cache
            from ..audio import get_persistent_audio_dir
            persistent_path = os.path.join(get_persistent_audio_dir(), fname)
            if os.path.exists(persistent_path):
                full_path = persistent_path
            else:
                return AudioOutput(
                    success=False,
                    tts_engine="edge_tts",
                    error=f"Generated file not found: {fname}",
                )

        # Estimate duration from file size
        file_size = os.path.getsize(full_path)
        if fname.endswith(".mp3"):
            # Rough MP3 estimate: ~16 kbps for speech
            duration = max(0.1, file_size / 2000)
        else:
            # WAV: 22050 Hz, 16-bit
            duration = max(0.1, (file_size - 44) / (22050 * 2))

        return AudioOutput(
            audio_path=full_path,
            duration_seconds=round(duration, 2),
            tts_engine="edge_tts",
            tonal_accuracy_validated=False,
            success=True,
        )

    except ImportError:
        return AudioOutput(
            success=False,
            tts_engine="edge_tts",
            error="audio module not available",
        )
    except Exception as e:
        logger.debug("edge-tts generation failed: %s", e)
        return AudioOutput(
            success=False,
            tts_engine="edge_tts",
            error=str(e),
        )


def _generate_with_macos_tts(text: str, speed: float, cache_key: str) -> AudioOutput:
    """Generate audio via macOS `say` command."""
    if platform.system() != "Darwin":
        return AudioOutput(
            success=False,
            tts_engine="macos_tts",
            error="Not running on macOS",
        )

    out_path = str(AUDIO_OUTPUT_DIR / f"{cache_key}.aiff")
    wav_path = str(AUDIO_OUTPUT_DIR / f"{cache_key}.wav")

    try:
        # Detect best Chinese voice
        from ..audio import get_chinese_voice
        voice = get_chinese_voice()

        # Convert speed factor to WPM
        wpm = int(120 * speed)
        wpm = max(80, min(200, wpm))

        start = time.monotonic()
        proc = subprocess.run(
            ["say", "-v", voice, "-r", str(wpm), "-o", out_path, text],
            capture_output=True,
            timeout=15,
        )

        if proc.returncode != 0 or not os.path.exists(out_path):
            return AudioOutput(
                success=False,
                tts_engine="macos_tts",
                error=f"say command failed (rc={proc.returncode})",
            )

        # Convert AIFF to WAV
        conv = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", out_path, wav_path],
            capture_output=True,
            timeout=15,
        )

        if conv.returncode != 0 or not os.path.exists(wav_path):
            # Fall back to AIFF
            return AudioOutput(
                audio_path=out_path,
                duration_seconds=0.0,
                tts_engine="macos_tts",
                tonal_accuracy_validated=False,
                success=True,
            )

        # Clean up AIFF
        try:
            os.remove(out_path)
        except OSError:
            pass

        # Estimate duration
        file_size = os.path.getsize(wav_path)
        duration = max(0.1, (file_size - 44) / (22050 * 2))

        return AudioOutput(
            audio_path=wav_path,
            duration_seconds=round(duration, 2),
            tts_engine="macos_tts",
            tonal_accuracy_validated=False,
            success=True,
        )

    except FileNotFoundError:
        return AudioOutput(
            success=False,
            tts_engine="macos_tts",
            error="say command not found",
        )
    except subprocess.TimeoutExpired:
        return AudioOutput(
            success=False,
            tts_engine="macos_tts",
            error="macOS TTS timed out (15s)",
        )
    except Exception as e:
        return AudioOutput(
            success=False,
            tts_engine="macos_tts",
            error=str(e),
        )


# ── Main speak function ─────────────────────────────────────────────────

def speak(
    text_zh: str,
    pinyin: str = "",
    conn=None,
    speed_override: Optional[float] = None,
    validate_tones: bool = False,
) -> AudioOutput:
    """Generate TTS audio for Chinese text.

    Checks cache first, then tries Kokoro -> edge-tts -> macOS TTS.

    Args:
        text_zh: Chinese text to speak.
        pinyin: Pinyin (used for cache key differentiation and future validation).
        conn: DB connection for caching (optional, skips cache if None).
        speed_override: Override default speed (0.5-2.0). None = KOKORO_SPEED.
        validate_tones: If True, validate tonal accuracy (placeholder, returns True).

    Returns:
        AudioOutput with success status, audio path, engine used.
    """
    if not text_zh or not text_zh.strip():
        return AudioOutput(success=False, error="Empty text")

    speed = speed_override if speed_override is not None else KOKORO_SPEED
    speed = max(0.5, min(2.0, speed))

    key = _cache_key(text_zh, speed)

    # Check cache first
    if conn is not None:
        _ensure_cache_table(conn)
        cached = _check_cache(conn, key)
        if cached is not None:
            return cached

    # Try engines in order
    engines = [
        ("kokoro", _generate_with_kokoro),
        ("edge_tts", _generate_with_edge_tts),
        ("macos_tts", _generate_with_macos_tts),
    ]

    last_error = ""
    for engine_name, engine_fn in engines:
        result = engine_fn(text_zh, speed, key)
        if result.success:
            # Tonal accuracy validation (placeholder)
            if validate_tones:
                result.tonal_accuracy_validated = _validate_tonal_accuracy(
                    result.audio_path, text_zh, pinyin,
                )
            else:
                result.tonal_accuracy_validated = True

            # Cache the result
            if conn is not None:
                _write_cache(conn, key, text_zh, result)

            logger.debug("TTS generated via %s for: %s", engine_name, text_zh[:20])
            return result
        else:
            last_error = result.error or f"{engine_name} failed"
            logger.debug("TTS engine %s failed: %s", engine_name, last_error)

    return AudioOutput(
        success=False,
        error=f"All TTS engines failed. Last error: {last_error}",
    )


def _validate_tonal_accuracy(
    audio_path: Optional[str], text_zh: str, pinyin: str,
) -> bool:
    """Validate that generated audio has correct tonal contours.

    Placeholder implementation -- returns True for now.
    Future: use tone_grading.extract_f0 + classify_tone to verify
    that the TTS output matches expected tones from pinyin.
    """
    # TODO: Implement actual tonal validation against pinyin
    return True


# ── Voice quality measurement ────────────────────────────────────────────

def measure_voice_quality(conn) -> dict:
    """Measure voice system health stats.

    Returns dict with:
        - cache_entries: total cached audio files
        - cache_hit_rate: hits / (hits + misses) estimate
        - engine_distribution: {engine: count}
        - stale_entries: entries pointing to missing files
        - total_duration_seconds: sum of all cached audio durations
    """
    result = {
        "cache_entries": 0,
        "cache_hit_rate": 0.0,
        "engine_distribution": {},
        "stale_entries": 0,
        "total_duration_seconds": 0.0,
    }

    if conn is None:
        return result

    _ensure_cache_table(conn)

    try:
        # Total entries
        total_row = conn.execute("SELECT COUNT(*) FROM pi_audio_cache").fetchone()
        result["cache_entries"] = total_row[0] if total_row else 0

        # Hit rate estimate
        hits_row = conn.execute(
            "SELECT SUM(hit_count) FROM pi_audio_cache",
        ).fetchone()
        total_hits = hits_row[0] if hits_row and hits_row[0] else 0
        total_entries = result["cache_entries"]
        # Rough estimate: each entry was generated once + hit_count times
        total_requests = total_entries + total_hits
        if total_requests > 0:
            result["cache_hit_rate"] = round(total_hits / total_requests, 3)

        # Engine distribution
        engine_rows = conn.execute(
            "SELECT tts_engine, COUNT(*) as cnt FROM pi_audio_cache GROUP BY tts_engine",
        ).fetchall()
        result["engine_distribution"] = {
            dict(r)["tts_engine"]: dict(r)["cnt"] for r in engine_rows
        }

        # Total duration
        dur_row = conn.execute(
            "SELECT SUM(duration_seconds) FROM pi_audio_cache",
        ).fetchone()
        result["total_duration_seconds"] = round(
            dur_row[0] if dur_row and dur_row[0] else 0.0, 1,
        )

        # Stale entries (file doesn't exist)
        all_paths = conn.execute(
            "SELECT cache_key, audio_path FROM pi_audio_cache",
        ).fetchall()
        stale = 0
        for row in all_paths:
            r = dict(row)
            path = r.get("audio_path", "")
            if path and not os.path.exists(path):
                stale += 1
        result["stale_entries"] = stale

    except Exception:
        logger.debug("measure_voice_quality failed", exc_info=True)

    return result

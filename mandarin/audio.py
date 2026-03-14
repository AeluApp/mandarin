"""Audio playback and TTS for Mandarin learning.

Primary backend: edge-tts (Microsoft neural voices — cross-platform, free,
no API key).  Produces MP3 natively.

Fallback chain:
  1. edge-tts (all platforms, neural quality)
  2. macOS Swift helper / `say` command (local playback on macOS)
  3. Browser speechSynthesis (web UI fallback in JavaScript)

Web mode: generate_audio_file() creates MP3/WAV files served via Flask.
"""

import asyncio
import hashlib
import logging
import os
import platform
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Edge-TTS voices ──────────────────────────────────────────────────
EDGE_VOICES = {
    "female": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunxiNeural",
    "female_young": "zh-CN-XiaoyiNeural",
    "male_narrator": "zh-CN-YunjianNeural",
    "male_news": "zh-CN-YunyangNeural",
}
_preferred_voice = "female"

# ── Paths ────────────────────────────────────────────────────────────
_TTS_HELPER = str(Path(__file__).resolve().parent.parent / "tools" / "tts")
_tts_helper_available: Optional[bool] = None

# Persistent cache (pre-generated audio survives restarts)
_PERSISTENT_AUDIO_DIR = str(Path(__file__).resolve().parent.parent / "data" / "audio_cache")
os.makedirs(_PERSISTENT_AUDIO_DIR, exist_ok=True)

# Temp cache (on-demand generation)
_TEMP_AUDIO_DIR = os.path.join(tempfile.gettempdir(), "mandarin_audio")
os.makedirs(_TEMP_AUDIO_DIR, exist_ok=True)

# ── Edge-TTS async event loop (background thread) ───────────────────
_edge_loop = None
_edge_thread = None
_edge_lock = threading.Lock()
_edge_available: Optional[bool] = None


def _ensure_edge_loop():
    """Start background thread with async event loop for edge-tts."""
    global _edge_loop, _edge_thread
    with _edge_lock:
        if _edge_loop is not None and _edge_loop.is_running():
            return
        _edge_loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(_edge_loop)
            _edge_loop.run_forever()

        _edge_thread = threading.Thread(target=_run, daemon=True, name="edge-tts")
        _edge_thread.start()


def _is_edge_available() -> bool:
    """Check if edge-tts is importable."""
    global _edge_available
    if _edge_available is None:
        try:
            import edge_tts as _et  # noqa: F401
            _edge_available = True
            logger.info("edge-tts available (neural TTS)")
        except ImportError:
            _edge_available = False
            logger.info("edge-tts not available — falling back to macOS TTS")
    return _edge_available


def set_preferred_voice(voice_key: str):
    """Set preferred voice (female, male, female_young, male_narrator, male_news)."""
    global _preferred_voice
    if voice_key in EDGE_VOICES:
        _preferred_voice = voice_key


def get_preferred_voice() -> str:
    """Return current preferred voice key."""
    return _preferred_voice


# ── macOS TTS detection ──────────────────────────────────────────────

def _has_tts_helper() -> bool:
    global _tts_helper_available
    if _tts_helper_available is None:
        _tts_helper_available = os.path.isfile(_TTS_HELPER) and os.access(_TTS_HELPER, os.X_OK)
        if _tts_helper_available:
            logger.info("TTS helper available: %s", _TTS_HELPER)
    return _tts_helper_available


_chinese_voice = None


def _detect_best_chinese_voice() -> Optional[str]:
    if platform.system() != "Darwin":
        return None
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True, text=True, timeout=5
        )
        zh_cn_voices = []
        for line in result.stdout.splitlines():
            if "zh_CN" in line:
                name = line.split()[0]
                is_premium = "(Premium)" in line or "(Enhanced)" in line
                zh_cn_voices.append((name, is_premium))
        if not zh_cn_voices:
            return None
        for name, premium in zh_cn_voices:
            if premium:
                return name
        for name, _ in zh_cn_voices:
            if name == "Tingting":
                return name
        return zh_cn_voices[0][0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_chinese_voice() -> str:
    global _chinese_voice
    if _chinese_voice is None:
        _chinese_voice = _detect_best_chinese_voice() or "Tingting"
    return _chinese_voice


def is_audio_available() -> bool:
    """Check if audio is available — edge-tts works on all platforms."""
    if _is_edge_available():
        return True
    if platform.system() != "Darwin":
        return False
    return get_chinese_voice() is not None


# ── Rate handling ────────────────────────────────────────────────────

_default_rate = 100


def set_default_rate(rate: int):
    global _default_rate
    _default_rate = rate


def get_tts_rate(text: str, listening_level: float = 1.0) -> int:
    """Return adaptive TTS rate based on text length and learner level."""
    if listening_level < 3.0:
        base = int(90 + (listening_level - 1.0) * 10)
    elif listening_level < 6.0:
        base = int(110 + (listening_level - 3.0) * 10)
    else:
        base = int(140 + min(listening_level - 6.0, 3.0) * 10)
    if len(text.strip()) <= 2:
        base = max(base - 20, 80)
    return base


def _wpm_to_edge_rate(wpm: int) -> str:
    """Convert WPM (80-170) to edge-tts rate string like '+0%' or '-20%'."""
    # 120 WPM = natural (0%), 80 = -30%, 170 = +30%
    pct = int((wpm - 120) * (30 / 50))
    pct = max(-50, min(50, pct))
    return f"{pct:+d}%"


def _wpm_to_avspeech_rate(wpm: int) -> float:
    return max(0.25, min(0.6, 0.30 + (wpm - 80) * 0.003))


# ── Web audio callback ──────────────────────────────────────────────

_web_audio = threading.local()


def set_web_audio_callback(callback):
    _web_audio.callback = callback


def clear_web_audio_callback():
    _web_audio.callback = None


# ── Process management ───────────────────────────────────────────────

_current_process = None
_process_lock = threading.Lock()


def cancel_audio():
    global _current_process
    with _process_lock:
        if _current_process is None:
            return
        try:
            _current_process.kill()
            _current_process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("cancel_audio: kill/wait failed", exc_info=True)
        finally:
            _current_process = None


# ── Core generation ──────────────────────────────────────────────────

def _cache_key(text: str, rate: int, voice: str = "") -> str:
    """Deterministic hash for audio cache."""
    raw = f"{text}:{rate}:{voice}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _find_cached(key: str) -> Optional[str]:
    """Check persistent and temp cache for existing audio file."""
    for ext in (".mp3", ".wav"):
        fname = key + ext
        # Check persistent cache first
        persistent = os.path.join(_PERSISTENT_AUDIO_DIR, fname)
        if os.path.exists(persistent) and os.path.getsize(persistent) > 0:
            return fname
        # Check temp cache
        temp = os.path.join(_TEMP_AUDIO_DIR, fname)
        if os.path.exists(temp) and os.path.getsize(temp) > 0:
            return fname
    return None


def _generate_edge_tts(text: str, rate: int, voice_key: str = "") -> Optional[str]:
    """Generate MP3 via edge-tts. Returns filename or None."""
    if not _is_edge_available():
        return None

    import edge_tts

    vk = voice_key or _preferred_voice
    voice_name = EDGE_VOICES.get(vk, EDGE_VOICES["female"])
    rate_str = _wpm_to_edge_rate(rate)

    key = _cache_key(text, rate, vk)
    fname = f"{key}.mp3"
    out_path = os.path.join(_TEMP_AUDIO_DIR, fname)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return fname

    # Also check persistent cache
    persistent_path = os.path.join(_PERSISTENT_AUDIO_DIR, fname)
    if os.path.exists(persistent_path) and os.path.getsize(persistent_path) > 0:
        return fname

    try:
        _ensure_edge_loop()
        comm = edge_tts.Communicate(text, voice_name, rate=rate_str)
        future = asyncio.run_coroutine_threadsafe(comm.save(out_path), _edge_loop)
        future.result(timeout=30)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return fname
        return None
    except Exception as e:
        logger.warning("edge-tts generation failed: %s", e)
        return None


def _generate_macos_tts(text: str, rate: int) -> Optional[str]:
    """Generate WAV via macOS say + afconvert. Returns filename or None."""
    if platform.system() != "Darwin":
        return None

    key = _cache_key(text, rate, "macos")
    aiff_fname = f"{key}.aiff"
    wav_fname = f"{key}.wav"
    aiff_path = os.path.join(_TEMP_AUDIO_DIR, aiff_fname)
    wav_path = os.path.join(_TEMP_AUDIO_DIR, wav_fname)

    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
        return wav_fname

    try:
        proc = subprocess.run(
            ["say", "-v", get_chinese_voice(), "-r", str(rate), "-o", aiff_path, text],
            capture_output=True, timeout=15,
        )
        if proc.returncode != 0 or not os.path.exists(aiff_path):
            return None

        conv = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@22050",
             aiff_path, wav_path],
            capture_output=True, timeout=15,
        )
        if conv.returncode != 0 or not os.path.exists(wav_path):
            return None

        try:
            os.remove(aiff_path)
        except OSError:
            pass
        return wav_fname
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("macOS TTS failed: %s", e)
        return None


def generate_audio_file(text: str, rate: int = None, voice: str = "") -> Optional[str]:
    """Generate an audio file for Chinese text.

    Tries edge-tts first (MP3, neural quality, cross-platform),
    falls back to macOS say (WAV).

    Returns filename for serving via Flask, or None on failure.
    Files are cached by content hash.
    """
    if rate is None:
        rate = _default_rate
        if len(text.strip()) <= 2:
            rate = max(rate - 20, 80)

    vk = voice or _preferred_voice

    # Check cache first (both persistent and temp)
    key = _cache_key(text, rate, vk)
    cached = _find_cached(key)
    if cached:
        return cached

    # Also check legacy cache key (no voice param) for backwards compat
    legacy_key = _cache_key(text, rate, "")
    legacy_cached = _find_cached(legacy_key)
    if legacy_cached:
        return legacy_cached

    # Try edge-tts first
    result = _generate_edge_tts(text, rate, vk)
    if result:
        return result

    # Fall back to macOS
    return _generate_macos_tts(text, rate)


# ── Public playback functions ────────────────────────────────────────

def speak_chinese(text: str, rate: int = None):
    """Play Chinese text (non-blocking).

    Web mode: generates file and sends URL to browser.
    CLI mode on macOS: plays through speakers.
    """
    if rate is None:
        rate = _default_rate
        if len(text.strip()) <= 2:
            rate = max(rate - 20, 80)

    global _current_process
    callback = getattr(_web_audio, "callback", None)
    if callback:
        fname = generate_audio_file(text, rate)
        if fname:
            try:
                callback(fname)
            except (TypeError, OSError, ConnectionError) as e:
                logger.debug("web audio callback failed: %s", e)
        return

    if platform.system() != "Darwin":
        return
    cancel_audio()
    try:
        if _has_tts_helper():
            av_rate = _wpm_to_avspeech_rate(rate)
            proc = subprocess.Popen(
                [_TTS_HELPER, text, "--rate", str(av_rate)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            proc = subprocess.Popen(
                ["say", "-v", get_chinese_voice(), "-r", str(rate), text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        with _process_lock:
            _current_process = proc
    except FileNotFoundError:
        with _process_lock:
            _current_process = None


def speak_and_wait(text: str, rate: int = None):
    """Play Chinese text (blocking — waits for finish).

    Timeout scales with text length: base 15s + 1s per character.
    Web mode: generates file and sends URL, then pauses briefly.
    """
    if rate is None:
        rate = _default_rate
        if len(text.strip()) <= 2:
            rate = max(rate - 20, 80)

    global _current_process
    callback = getattr(_web_audio, "callback", None)
    if callback:
        fname = generate_audio_file(text, rate)
        if fname:
            try:
                callback(fname)
            except (TypeError, OSError, ConnectionError) as e:
                logger.debug("web audio callback failed: %s", e)
        import time
        time.sleep(0.8)
        return

    if platform.system() != "Darwin":
        return
    cancel_audio()
    timeout = max(15, 15 + len(text))
    try:
        if _has_tts_helper():
            av_rate = _wpm_to_avspeech_rate(rate)
            proc = subprocess.Popen(
                [_TTS_HELPER, text, "--rate", str(av_rate)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            proc = subprocess.Popen(
                ["say", "-v", get_chinese_voice(), "-r", str(rate), text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        with _process_lock:
            _current_process = proc
        proc.wait(timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        with _process_lock:
            if _current_process is not None:
                try:
                    _current_process.kill()
                except OSError:
                    pass
    finally:
        with _process_lock:
            _current_process = None


def get_audio_cache_dir() -> str:
    """Return the path to the temp audio cache directory."""
    return _TEMP_AUDIO_DIR


def get_persistent_audio_dir() -> str:
    """Return the path to the persistent audio cache directory."""
    return _PERSISTENT_AUDIO_DIR

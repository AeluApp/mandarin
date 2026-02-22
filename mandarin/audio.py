"""Audio playback and TTS for Mandarin learning.

Uses macOS built-in `say -v Tingting` for Chinese TTS — zero external
dependencies, zero audio files needed, fully offline.

Silent no-op on non-macOS platforms.

Web mode: generate_audio_file() creates AIFF files served via Flask.
"""

import logging
import os
import platform
import subprocess
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Directory for temporary audio files served to the web UI
_AUDIO_CACHE_DIR = os.path.join(tempfile.gettempdir(), "mandarin_audio")
os.makedirs(_AUDIO_CACHE_DIR, exist_ok=True)

# Thread-local web audio callback — when set, audio is generated as files
# and sent to the browser instead of playing through Mac speakers.
_web_audio = threading.local()


def set_web_audio_callback(callback):
    """Set a callback for web audio mode: callback(filename) sends to browser."""
    _web_audio.callback = callback


def clear_web_audio_callback():
    """Clear the web audio callback (return to local playback)."""
    _web_audio.callback = None

# Module-level process handle — tracks the currently playing TTS process
_current_process = None
_process_lock = threading.Lock()


def cancel_audio():
    """Kill any currently playing TTS process.

    Safe to call at any time — no-op if nothing is playing.
    """
    global _current_process
    with _process_lock:
        if _current_process is None:
            return
        try:
            _current_process.kill()
            _current_process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            _current_process = None


def is_audio_available() -> bool:
    """Check if audio playback is available on this platform."""
    if platform.system() != "Darwin":
        return False
    # Check if Tingting voice is installed
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True, text=True, timeout=5
        )
        available = "Tingting" in result.stdout
        if available:
            logger.debug("macOS TTS available (Tingting voice detected)")
        else:
            logger.debug("macOS TTS: Tingting voice not found")
        return available
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.debug("macOS TTS: 'say' command not available")
        return False


def speak_chinese(text: str, rate: int = 160):
    """Play Chinese text via macOS TTS (non-blocking).

    Cancels any previous audio before starting new playback.
    Returns immediately — audio plays in background.
    In web mode, generates a file and sends the URL to the browser.
    """
    global _current_process
    # Web mode: generate file and send to browser
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
        proc = subprocess.Popen(
            ["say", "-v", "Tingting", "-r", str(rate), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        with _process_lock:
            _current_process = proc
    except FileNotFoundError:
        with _process_lock:
            _current_process = None


def speak_and_wait(text: str, rate: int = 160):
    """Play Chinese text via macOS TTS (blocking — waits for finish).

    Cancels any previous audio before starting new playback.
    Timeout scales with text length: base 15s + 1s per character.
    In web mode, generates a file and sends the URL to the browser.
    """
    global _current_process
    # Web mode: generate file and send to browser
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
    timeout = max(15, 15 + len(text))
    try:
        proc = subprocess.Popen(
            ["say", "-v", "Tingting", "-r", str(rate), text],
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


def generate_audio_file(text: str, rate: int = 160) -> Optional[str]:
    """Generate an AIFF audio file from Chinese text via macOS TTS.

    Returns the filename (not full path) for serving via Flask, or None on
    failure.  Files are cached by text content hash so repeated calls for
    the same text are instant.
    """
    if platform.system() != "Darwin":
        return None

    import hashlib
    key = hashlib.sha256(f"{text}:{rate}".encode()).hexdigest()[:12]
    fname = f"{key}.aiff"
    fpath = os.path.join(_AUDIO_CACHE_DIR, fname)

    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return fname  # Already cached

    try:
        proc = subprocess.run(
            ["say", "-v", "Tingting", "-r", str(rate), "-o", fpath, text],
            capture_output=True, timeout=15,
        )
        if proc.returncode == 0 and os.path.exists(fpath):
            return fname
        logger.warning("say -o failed: rc=%d", proc.returncode)
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("generate_audio_file failed: %s", e)
        return None


def get_audio_cache_dir() -> str:
    """Return the path to the audio cache directory."""
    return _AUDIO_CACHE_DIR

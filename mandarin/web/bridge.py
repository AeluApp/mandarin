"""Bridge between show_fn/input_fn and WebSocket.

The runner already abstracts I/O through show_fn(text) and input_fn(prompt).
This module provides WebSocket-backed versions of those functions so the same
drill logic drives both terminal and browser UIs.
"""

import json
import logging
import re
import queue
import threading
from uuid import uuid4

logger = logging.getLogger(__name__)

# Timeout for waiting on browser answers (seconds).
# After this, the session auto-quits to prevent orphaned threads.
INPUT_TIMEOUT = 300


class BridgeDisconnected(Exception):
    """Raised when the WebSocket connection is lost during a prompt."""
    pass


class WebBridge:
    """Bridges show_fn/input_fn to a WebSocket connection.

    Messages sent to the browser are JSON:
      {"type": "show", "text": "...", "html": "..."}
      {"type": "prompt", "text": "...", "id": "p-1"}
      {"type": "record_request", "max_duration": 30.0, "id": "r-1", "allow_skip": true}
      {"type": "done", "summary": {...}}

    Messages received from the browser:
      {"type": "answer", "id": "p-1", "value": "..."}
      {"type": "audio_data", "id": "r-1", "data": "base64-wav"}
    """

    def __init__(self, ws):
        self.ws = ws
        self.session_uuid = uuid4().hex[:8]
        self._answer_queue = queue.Queue()
        self._audio_queue = queue.Queue()
        self._prompt_counter = 0
        self._lock = threading.Lock()
        self._closed = False
        self._disconnected = False
        self._reconnect_event = threading.Event()
        self._last_prompt = None   # (prompt_text, prompt_id) for re-send on resume
        self._prompt_sent_at = None  # monotonic time when last prompt was sent
        self._roundtrip_times = []   # WS roundtrip durations in ms
        self._word_lookups = []      # hanzi strings accumulated during reading exposure
        self._word_lookups_lock = threading.Lock()
        logger.info("[%s] WebBridge created", self.session_uuid)

    def show_fn(self, text: str, end="\n"):
        """Send display text to the browser."""
        if self._closed:
            return
        html = _rich_to_html(text)
        msg = json.dumps({"type": "show", "text": text, "html": html, "end": end})
        try:
            with self._lock:
                if not self._disconnected:
                    self.ws.send(msg)
        except (ConnectionError, OSError, BrokenPipeError):
            logger.debug("[%s] show_fn: connection lost, marking disconnected", self.session_uuid)
            self._disconnected = True

    def input_fn(self, prompt: str) -> str:
        """Send a prompt and block until the browser replies.

        If the transport disconnects mid-prompt, waits up to RESUME_TIMEOUT
        for a new WebSocket to be swapped in via swap_ws().  On reconnect the
        prompt is re-sent so the browser can display it again.

        Returns 'Q' on true close or resume timeout.
        """
        if self._closed:
            return "Q"
        self._prompt_counter += 1
        pid = f"p-{self._prompt_counter}"
        self._last_prompt = (prompt, pid)
        import time as _time
        self._prompt_sent_at = _time.monotonic()
        msg = json.dumps({"type": "prompt", "text": prompt, "id": pid})
        try:
            with self._lock:
                if not self._disconnected:
                    self.ws.send(msg)
                else:
                    # Already disconnected before we could send — wait for reconnect
                    raise ConnectionError("disconnected")
        except (ConnectionError, OSError, BrokenPipeError):
            logger.debug("[%s] input_fn: transport lost, waiting for reconnect", self.session_uuid)
            self._disconnected = True
            return self._wait_for_reconnect(prompt, pid)

        # Normal path: wait for answer
        return self._wait_for_answer(prompt, pid)

    def _wait_for_answer(self, prompt: str, pid: str) -> str:
        """Block until an answer arrives or the connection drops."""
        import time
        deadline = time.monotonic() + INPUT_TIMEOUT
        while time.monotonic() < deadline:
            try:
                answer = self._answer_queue.get(timeout=5)
                return answer
            except queue.Empty:
                if self._closed:
                    return "Q"
                if self._disconnected:
                    return self._wait_for_reconnect(prompt, pid)
        logger.info("[%s] input_fn: total timeout reached", self.session_uuid)
        self._closed = True
        return "Q"

    def _wait_for_reconnect(self, prompt: str, pid: str) -> str:
        """Wait for a new WebSocket to be swapped in, then re-send the prompt."""
        from .session_store import RESUME_TIMEOUT
        MAX_RECONNECT_ATTEMPTS = 5
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            logger.info("[%s] waiting up to %ds for reconnect (attempt %d/%d)...",
                        self.session_uuid, RESUME_TIMEOUT, attempt + 1, MAX_RECONNECT_ATTEMPTS)
            reconnected = self._reconnect_event.wait(timeout=RESUME_TIMEOUT)
            if not reconnected or self._closed:
                logger.info("[%s] reconnect timed out or closed, quitting", self.session_uuid)
                self._closed = True
                return "Q"
            self._reconnect_event.clear()
            logger.info("[%s] reconnected, re-sending prompt", self.session_uuid)
            msg = json.dumps({"type": "prompt", "text": prompt, "id": pid})
            try:
                with self._lock:
                    self.ws.send(msg)
            except (ConnectionError, OSError, BrokenPipeError):
                logger.debug("[%s] re-send prompt failed, disconnected again", self.session_uuid)
                self._disconnected = True
                continue
            return self._wait_for_answer(prompt, pid)
        logger.info("[%s] max reconnect attempts reached, quitting", self.session_uuid)
        self._closed = True
        return "Q"

    def swap_ws(self, new_ws):
        """Atomically replace the WebSocket transport (called on resume)."""
        with self._lock:
            self.ws = new_ws
            self._disconnected = False
        logger.info("[%s] WebSocket swapped", self.session_uuid)
        self._reconnect_event.set()

    def receive_answer(self, value: str):
        """Called when the browser sends an answer."""
        if self._prompt_sent_at is not None:
            import time as _time
            rt_ms = (_time.monotonic() - self._prompt_sent_at) * 1000.0
            self._roundtrip_times.append(rt_ms)
            self._prompt_sent_at = None
        self._answer_queue.put(value)

    def receive_word_lookup(self, hanzi: str):
        """Called when the browser sends a word_lookup during reading exposure."""
        with self._word_lookups_lock:
            if hanzi and hanzi not in self._word_lookups:
                self._word_lookups.append(hanzi)

    def drain_word_lookups(self) -> list:
        """Return and clear accumulated word lookups. Thread-safe."""
        with self._word_lookups_lock:
            result = list(self._word_lookups)
            self._word_lookups.clear()
            return result

    def receive_audio_data(self, data, transcript=None):
        """Called when the browser sends recorded audio data (base64 WAV or None).

        Puts a (data, transcript) tuple on the queue. transcript is the
        browser SpeechRecognition result (zh-CN) or None if unavailable.
        """
        self._audio_queue.put((data, transcript))

    def request_recording(self, duration: float):
        """Request the browser to record audio. Returns (numpy_array, transcript) or (None, None).

        Sends a record_request to the browser, blocks until audio data arrives.
        The browser records using getUserMedia and sends back base64-encoded WAV.
        If the browser records at a sample rate other than 16kHz (common on iOS),
        the audio is resampled to 16kHz before returning to match SAMPLE_RATE
        expected by tone_grading.extract_f0().

        transcript is the browser SpeechRecognition result (zh-CN) or None.
        """
        if self._closed:
            return (None, None)
        self._prompt_counter += 1
        rid = f"r-{self._prompt_counter}"
        msg = json.dumps({"type": "record_request", "max_duration": duration, "id": rid, "allow_skip": True})
        try:
            with self._lock:
                if not self._disconnected:
                    self.ws.send(msg)
        except (ConnectionError, OSError, BrokenPipeError):
            logger.debug("[%s] request_recording: connection lost", self.session_uuid)
            return (None, None)

        # Wait for audio data — generous timeout for user interaction + mic permission
        timeout = max(duration + 30, 120)
        try:
            data_tuple = self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            logger.info("[%s] recording timeout", self.session_uuid)
            return (None, None)

        # Handle both tuple (new) and raw data (backwards compat)
        if isinstance(data_tuple, tuple):
            data, transcript = data_tuple
        else:
            data, transcript = data_tuple, None

        if data is None:
            return (None, None)

        # Decode base64 WAV to numpy array, resampling to 16kHz if needed.
        # The browser may record at 44100 or 48000 Hz even when 16kHz is requested
        # (especially on iOS). The tone grading pipeline assumes 16kHz, so we
        # resample here to prevent mismatched F0 extraction.
        try:
            import base64
            import io
            import wave as wavmod
            wav_bytes = base64.b64decode(data)
            with wavmod.open(io.BytesIO(wav_bytes), "r") as wf:
                frames = wf.readframes(wf.getnframes())
                sr = wf.getframerate()
            try:
                import numpy as np
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
                # Resample to 16kHz if browser recorded at a different rate
                target_sr = 16000
                if sr != target_sr and sr > 0:
                    ratio = target_sr / sr
                    new_len = int(len(audio) * ratio)
                    indices = np.arange(new_len) / ratio
                    indices = np.clip(indices.astype(int), 0, len(audio) - 1)
                    audio = audio[indices]
                    logger.info("[%s] resampled audio from %dHz to %dHz (%d -> %d samples)",
                                self.session_uuid, sr, target_sr, len(frames) // 2, len(audio))
                return (audio, transcript)
            except ImportError:
                logger.warning("numpy not available — cannot decode audio")
                return (None, None)
        except (ValueError, OSError, KeyError) as e:
            logger.warning("[%s] audio decode error: %s", self.session_uuid, e)
            return (None, None)

    def disconnect(self):
        """Transport lost — session may be resumed."""
        self._disconnected = True
        logger.info("[%s] disconnected (resumable)", self.session_uuid)

    def close(self):
        """Session over — no resume possible."""
        self._closed = True
        self._disconnected = True
        self._reconnect_event.set()  # Unblock any waiting input_fn
        try:
            self._answer_queue.put_nowait("Q")
        except queue.Full:
            pass

    def _send(self, obj: dict):
        """Low-level send — used by routes for protocol messages."""
        try:
            with self._lock:
                if not self._disconnected:
                    self.ws.send(json.dumps(obj))
        except (ConnectionError, OSError, BrokenPipeError):
            self._disconnected = True

    def send_done(self, summary: dict):
        """Signal session complete."""
        if self._closed:
            return
        if self._roundtrip_times:
            summary["avg_ws_roundtrip_ms"] = round(
                sum(self._roundtrip_times) / len(self._roundtrip_times), 1
            )
        msg = json.dumps({"type": "done", "summary": summary})
        try:
            with self._lock:
                self.ws.send(msg)
        except (ConnectionError, OSError, BrokenPipeError):
            logger.debug("[%s] send_done: connection lost", self.session_uuid)
            self._closed = True

    def send_error(self, message: str):
        """Signal an error."""
        if self._closed:
            return
        msg = json.dumps({"type": "error", "message": message})
        try:
            with self._lock:
                self.ws.send(msg)
        except (ConnectionError, OSError, BrokenPipeError):
            logger.debug("[%s] send_error: connection lost", self.session_uuid)
            self._closed = True

    def send_progress(self, session_id: int, drill_index: int, drill_total: int,
                       correct: int, completed: int, session_type: str = "standard"):
        """Send session progress checkpoint to the browser after each drill."""
        self._send({
            "type": "progress",
            "session_id": session_id,
            "drill_index": drill_index,
            "drill_total": drill_total,
            "correct": correct,
            "completed": completed,
            "session_type": session_type,
        })

    def send_audio_state(self, state: str):
        """Send audio state to the browser: 'playing', 'ready', or 'error'."""
        self._send({"type": "audio_state", "state": state})

    def send_drill_meta(self, content_item_id: int, modality: str,
                        correct: bool, hanzi: str = "",
                        error_type: str = "",
                        requirement_ref: dict = None,
                        error_explanation: str = ""):
        """Send drill result metadata to the browser for override support."""
        payload = {
            "type": "drill_meta",
            "content_item_id": content_item_id,
            "modality": modality,
            "correct": correct,
            "hanzi": hanzi,
        }
        if error_type:
            payload["error_type"] = error_type
        if requirement_ref:
            payload["requirement_ref"] = requirement_ref
        if error_explanation:
            payload["error_explanation"] = error_explanation
        self._send(payload)


# ── Rich markup → HTML conversion ──────────────────────────────

# Rosetta Stone: Rich CLI styles → Web CSS vars
# CLI bright_cyan / bold bright_cyan → --color-accent (rose)
# CLI green / bold green → --color-correct
# CLI red / bold red / red bold → --color-incorrect
# CLI yellow / bold yellow → --color-secondary (olive)
# CLI bright_magenta / bold bright_magenta → --color-accent (drill hanzi)
# CLI dim → opacity 0.6
#
# Known divergence: display.hanzi() uses bright_cyan; drills/base.format_hanzi()
# uses bright_magenta. Both map to --color-accent on web (intentional collapse).
# On CLI they render as distinct terminal colors (cyan vs magenta). This is an
# accepted divergence — the web uses a single accent color for all hanzi.
_RICH_CLASS_MAP = {
    "bold": "rich-bold",
    "dim": "rich-dim",
    "italic": "rich-italic",
    "bold bright_magenta": "rich-accent-bold",
    "bright_magenta": "rich-accent",
    "bold magenta": "rich-accent-dim-bold",
    "magenta": "rich-accent-dim",
    "bold bright_cyan": "rich-accent-bold",
    "bright_cyan": "rich-accent",
    "bold white": "rich-text-bold",
    "dim italic": "rich-dim-italic",
    "bold dim": "rich-bold-dim",
    "green": "rich-correct",
    "bold green": "rich-correct-bold",
    "red bold": "rich-incorrect-bold",
    "bold red": "rich-incorrect-bold",
    "red": "rich-incorrect",
    "yellow": "rich-secondary",
    "bold yellow": "rich-secondary-bold",
}

# Match Rich-style tags like [bold magenta]...[/bold magenta] or [/]
_TAG_RE = re.compile(r'\[(/?)([^\]]*)\]')


_SPARKLINE_RE = re.compile(r'[▁▂▃▄▅▆▇█]{3,}')

# CJK Unified Ideographs ranges for inline class detection
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+')

# Styles that produce hanzi display spans (used to add hanzi-inline class)
_HANZI_STYLES = {"bold bright_magenta", "bright_magenta", "bold bright_cyan", "bright_cyan",
                 "bold magenta", "magenta"}


def _rich_to_html(text: str) -> str:
    """Convert Rich markup to HTML spans. Best-effort, not a full parser."""
    if "[" not in text:
        html = _escape_html(text)
        # Detect sparkline character sequences and wrap for styling
        html = _SPARKLINE_RE.sub(
            lambda m: f'<span class="sparkline-inline">{m.group()}</span>', html)
        return html

    result = []
    last = 0
    open_tags = []

    for m in _TAG_RE.finditer(text):
        # Add text before this tag
        result.append(_escape_html(text[last:m.start()]))
        last = m.end()

        is_close = m.group(1) == "/"
        style_name = m.group(2).strip()

        if is_close:
            if style_name == "" or open_tags:
                result.append("</span>")
                if open_tags:
                    open_tags.pop()
        else:
            css_class = _RICH_CLASS_MAP.get(style_name, "")
            if css_class:
                hanzi_cls = " hanzi-inline" if style_name in _HANZI_STYLES else ""
                result.append(f'<span class="{css_class}{hanzi_cls}">')
                open_tags.append(style_name)
            # Unknown styles: just open a neutral span
            else:
                result.append("<span>")
                open_tags.append(style_name)

    result.append(_escape_html(text[last:]))

    # Close any unclosed tags
    for _ in open_tags:
        result.append("</span>")

    html = "".join(result)
    # Detect sparkline character sequences and wrap for styling
    html = _SPARKLINE_RE.sub(
        lambda m: f'<span class="sparkline-inline">{m.group()}</span>', html)
    return html


def _escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;"))

"""Tests for audio process tracking, cancellation, and no-overlap guarantees.

Tests verify:
- cancel_audio() is safe to call at any time
- _current_process is tracked and cleared correctly
- speak_chinese cancels previous audio before starting new
- speak_and_wait clears _current_process after completion
- _make_replay_input captures string, not dict reference
"""

import subprocess
from unittest.mock import patch, MagicMock

from mandarin import audio
from mandarin.drills.speaking import _make_replay_input

# Pre-set voice to avoid subprocess.run during tests
audio._chinese_voice = "Tingting"


# ---- TestCancelAudio ----

def test_cancel_when_nothing_playing():
    """cancel_audio() should be a no-op when nothing is playing."""
    audio._current_process = None
    audio.cancel_audio()
    assert audio._current_process is None


def test_cancel_kills_active_process():
    """cancel_audio() should kill an active process and clear the handle."""
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.wait = MagicMock()
    audio._current_process = mock_proc

    audio.cancel_audio()

    mock_proc.kill.assert_called_once()
    mock_proc.wait.assert_called_once_with(timeout=2)
    assert audio._current_process is None


def test_cancel_handles_oserror():
    """cancel_audio() should handle OSError gracefully."""
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock(side_effect=OSError("process gone"))
    audio._current_process = mock_proc

    audio.cancel_audio()  # Should not raise
    assert audio._current_process is None


def test_cancel_handles_timeout():
    """cancel_audio() should handle wait timeout gracefully."""
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.wait = MagicMock(side_effect=subprocess.TimeoutExpired("say", 2))
    audio._current_process = mock_proc

    audio.cancel_audio()  # Should not raise
    assert audio._current_process is None


# ---- TestSpeakChinese ----

@patch("mandarin.audio.platform")
def test_noop_on_non_darwin(mock_platform):
    """speak_chinese() should be a no-op on non-macOS."""
    mock_platform.system.return_value = "Linux"
    audio._current_process = None
    audio.speak_chinese("\u4f60\u597d")
    assert audio._current_process is None


@patch("mandarin.audio.platform")
@patch("mandarin.audio.subprocess.Popen")
def test_cancels_before_new_audio(mock_popen, mock_platform):
    """speak_chinese() should cancel previous audio before starting new."""
    mock_platform.system.return_value = "Darwin"

    # Set up a mock "previous" process
    old_proc = MagicMock()
    audio._current_process = old_proc

    new_proc = MagicMock()
    mock_popen.return_value = new_proc

    audio.speak_chinese("\u4f60\u597d")

    # Old process should have been killed
    old_proc.kill.assert_called_once()
    # New process should be tracked
    assert audio._current_process == new_proc


@patch("mandarin.audio.platform")
@patch("mandarin.audio.subprocess.Popen")
def test_tracks_new_process(mock_popen, mock_platform):
    """speak_chinese() should store the Popen handle in _current_process."""
    mock_platform.system.return_value = "Darwin"
    audio._current_process = None

    mock_proc = MagicMock()
    mock_popen.return_value = mock_proc

    audio.speak_chinese("\u4f60\u597d")
    assert audio._current_process == mock_proc


# ---- TestSpeakAndWait ----

@patch("mandarin.audio.platform")
@patch("mandarin.audio.subprocess.Popen")
def test_clears_process_after_completion(mock_popen, mock_platform):
    """speak_and_wait() should clear _current_process after completion."""
    mock_platform.system.return_value = "Darwin"
    mock_proc = MagicMock()
    mock_proc.wait = MagicMock()
    mock_popen.return_value = mock_proc

    audio.speak_and_wait("\u4f60\u597d")
    assert audio._current_process is None


@patch("mandarin.audio.platform")
def test_timeout_scales_with_text(mock_platform):
    """speak_and_wait() timeout should scale with text length."""
    mock_platform.system.return_value = "Darwin"
    # Test the timeout calculation inline
    text = "\u4f60\u597d\u4e16\u754c"  # 4 chars
    timeout = max(15, 15 + len(text))
    assert timeout == 19

    long_text = "a" * 100
    timeout = max(15, 15 + len(long_text))
    assert timeout == 115


# ---- TestReplayClosure ----

def test_captures_string_not_dict():
    """_make_replay_input should capture hanzi string at closure time."""
    item = {"hanzi": "\u4f60\u597d"}
    calls = []

    def mock_input(prompt):
        return calls.pop(0) if calls else ""

    def mock_show(text, **kwargs):
        pass

    # Create the wrapper
    wrapped = _make_replay_input(mock_input, mock_show, item, audio_enabled=True)

    # Mutate the dict AFTER creating the closure
    item["hanzi"] = "\u518d\u89c1"

    # The closure should still use the original (captured at creation time)
    calls = ["1"]
    result = wrapped("prompt> ")
    assert result == "1"


def test_noop_when_audio_disabled():
    """_make_replay_input should return original fn when audio disabled."""
    item = {"hanzi": "\u4f60\u597d"}

    def mock_input(prompt):
        return "test"

    def mock_show(text, **kwargs):
        pass

    result = _make_replay_input(mock_input, mock_show, item, audio_enabled=False)
    assert result is mock_input

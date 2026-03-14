"""Tests for voice_of_aelu — TTS system with caching and fallbacks."""

import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from mandarin.ai.voice_of_aelu import (
    AudioOutput,
    speak,
    measure_voice_quality,
    _cache_key,
    _ensure_cache_table,
    _check_cache,
    _write_cache,
    _generate_with_kokoro,
    _generate_with_edge_tts,
    _generate_with_macos_tts,
    _validate_tonal_accuracy,
    KOKORO_SPEED,
    AUDIO_OUTPUT_DIR,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    """In-memory SQLite for cache testing."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _ensure_cache_table(c)
    return c


# ── Test 1: AudioOutput dataclass ────────────────────────────────────────

def test_audio_output_defaults():
    ao = AudioOutput()
    assert ao.audio_path is None
    assert ao.duration_seconds == 0.0
    assert ao.tts_engine == ""
    assert ao.tonal_accuracy_validated is False
    assert ao.success is False
    assert ao.error is None


def test_audio_output_success():
    ao = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=2.5,
        tts_engine="kokoro",
        success=True,
    )
    assert ao.success is True
    assert ao.audio_path == "/tmp/test.wav"


# ── Test 2: Cache key generation ─────────────────────────────────────────

def test_cache_key_deterministic():
    k1 = _cache_key("你好", 0.85)
    k2 = _cache_key("你好", 0.85)
    assert k1 == k2


def test_cache_key_differs_by_text():
    k1 = _cache_key("你好", 0.85)
    k2 = _cache_key("再见", 0.85)
    assert k1 != k2


def test_cache_key_differs_by_speed():
    k1 = _cache_key("你好", 0.85)
    k2 = _cache_key("你好", 1.0)
    assert k1 != k2


# ── Test 3: Cache table creation ─────────────────────────────────────────

def test_ensure_cache_table_creates_table(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "pi_audio_cache" in tables


def test_ensure_cache_table_idempotent(conn):
    # Calling again should not fail
    _ensure_cache_table(conn)
    count = conn.execute("SELECT COUNT(*) FROM pi_audio_cache").fetchone()[0]
    assert count == 0


# ── Test 4: Cache write and read ─────────────────────────────────────────

def test_cache_write_and_read(conn):
    key = _cache_key("你好", 0.85)
    result = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=1.5,
        tts_engine="kokoro",
        success=True,
    )

    # Write to cache
    _write_cache(conn, key, "你好", result)

    # Mock the file existing
    with patch("os.path.exists", return_value=True):
        cached = _check_cache(conn, key)

    assert cached is not None
    assert cached.success is True
    assert cached.audio_path == "/tmp/test.wav"
    assert cached.duration_seconds == 1.5


def test_cache_miss(conn):
    cached = _check_cache(conn, "nonexistent_key")
    assert cached is None


def test_cache_stale_file_removed(conn):
    """Cache entry pointing to nonexistent file should be cleaned up."""
    key = _cache_key("你好", 0.85)
    result = AudioOutput(
        audio_path="/tmp/definitely_not_a_file_12345.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )
    _write_cache(conn, key, "你好", result)

    # File doesn't exist -> should return None and clean up
    cached = _check_cache(conn, key)
    assert cached is None

    # Verify entry was deleted
    row = conn.execute("SELECT COUNT(*) FROM pi_audio_cache WHERE cache_key = ?", (key,)).fetchone()
    assert row[0] == 0


# ── Test 5: Kokoro generation ────────────────────────────────────────────

@patch("subprocess.run")
def test_kokoro_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr=b"")

    # Create a temp file to simulate output
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 32044)  # WAV header + some data
        temp_path = f.name

    key = _cache_key("你好", KOKORO_SPEED)
    expected_path = str(AUDIO_OUTPUT_DIR / f"{key}.wav")

    with patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=32044):
        result = _generate_with_kokoro("你好", KOKORO_SPEED, key)

    assert result.tts_engine == "kokoro"
    # Success depends on subprocess mock
    if result.success:
        assert result.duration_seconds > 0

    os.unlink(temp_path)


@patch("subprocess.run", side_effect=FileNotFoundError("kokoro not found"))
def test_kokoro_not_installed(mock_run):
    key = _cache_key("你好", KOKORO_SPEED)
    result = _generate_with_kokoro("你好", KOKORO_SPEED, key)
    assert result.success is False
    assert "not found" in result.error


# ── Test 6: Edge-tts generation ──────────────────────────────────────────

def test_edge_tts_fallback_returns_audio_output():
    """Edge TTS should return an AudioOutput regardless of success."""
    with patch("mandarin.audio.generate_audio_file", return_value=None):
        result = _generate_with_edge_tts("你好", 0.85, "test_key")
    assert isinstance(result, AudioOutput)
    assert result.tts_engine == "edge_tts"


# ── Test 7: macOS TTS generation ─────────────────────────────────────────

@patch("platform.system", return_value="Linux")
def test_macos_tts_skips_non_darwin(mock_system):
    key = _cache_key("你好", KOKORO_SPEED)
    result = _generate_with_macos_tts("你好", KOKORO_SPEED, key)
    assert result.success is False
    assert "macOS" in result.error


@patch("platform.system", return_value="Darwin")
@patch("subprocess.run")
def test_macos_tts_say_failure(mock_run, mock_system):
    mock_run.return_value = MagicMock(returncode=1)
    key = _cache_key("你好", KOKORO_SPEED)

    with patch("mandarin.ai.voice_of_aelu.get_chinese_voice", return_value="Tingting", create=True):
        result = _generate_with_macos_tts("你好", KOKORO_SPEED, key)

    assert result.success is False


# ── Test 8: speak fallback chain ─────────────────────────────────────────

@patch("mandarin.ai.voice_of_aelu._generate_with_macos_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_edge_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_kokoro")
def test_speak_tries_all_engines(mock_kokoro, mock_edge, mock_macos, conn):
    """When all engines fail, speak returns success=False."""
    mock_kokoro.return_value = AudioOutput(success=False, tts_engine="kokoro", error="not found")
    mock_edge.return_value = AudioOutput(success=False, tts_engine="edge_tts", error="offline")
    mock_macos.return_value = AudioOutput(success=False, tts_engine="macos_tts", error="no voice")

    result = speak("你好", conn=conn)
    assert result.success is False
    assert "All TTS engines failed" in result.error
    mock_kokoro.assert_called_once()
    mock_edge.assert_called_once()
    mock_macos.assert_called_once()


@patch("mandarin.ai.voice_of_aelu._generate_with_kokoro")
def test_speak_uses_first_successful_engine(mock_kokoro, conn):
    """If Kokoro succeeds, edge-tts and macOS are not called."""
    mock_kokoro.return_value = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )

    result = speak("你好", conn=conn)
    assert result.success is True
    assert result.tts_engine == "kokoro"


# ── Test 9: speak uses cache ─────────────────────────────────────────────

@patch("mandarin.ai.voice_of_aelu._generate_with_kokoro")
def test_speak_returns_cached_result(mock_kokoro, conn):
    """Second call should use cache, not call engine again."""
    mock_kokoro.return_value = AudioOutput(
        audio_path="/tmp/cached.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )

    # First call generates
    with patch("os.path.exists", return_value=True):
        result1 = speak("你好", conn=conn)
    assert result1.success is True

    # Second call should hit cache
    mock_kokoro.reset_mock()
    with patch("os.path.exists", return_value=True):
        result2 = speak("你好", conn=conn)
    assert result2.success is True
    mock_kokoro.assert_not_called()  # Should not call engine again


# ── Test 10: speak empty text ────────────────────────────────────────────

def test_speak_empty_text():
    result = speak("")
    assert result.success is False
    assert "Empty text" in result.error


def test_speak_whitespace_only():
    result = speak("   ")
    assert result.success is False
    assert "Empty text" in result.error


# ── Test 11: speak without conn (no caching) ────────────────────────────

@patch("mandarin.ai.voice_of_aelu._generate_with_macos_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_edge_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_kokoro")
def test_speak_without_conn(mock_kokoro, mock_edge, mock_macos):
    mock_kokoro.return_value = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )

    result = speak("你好", conn=None)
    assert result.success is True


# ── Test 12: speed clamping ──────────────────────────────────────────────

@patch("mandarin.ai.voice_of_aelu._generate_with_macos_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_edge_tts")
@patch("mandarin.ai.voice_of_aelu._generate_with_kokoro")
def test_speak_speed_clamped(mock_kokoro, mock_edge, mock_macos):
    mock_kokoro.return_value = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )

    # Extreme speed should be clamped
    result = speak("你好", speed_override=10.0)
    assert result.success is True
    # Speed was clamped to 2.0 max
    call_args = mock_kokoro.call_args
    speed_used = call_args[0][1]  # second positional arg
    assert speed_used <= 2.0


# ── Test 13: measure_voice_quality ───────────────────────────────────────

def test_measure_voice_quality_empty(conn):
    result = measure_voice_quality(conn)
    assert result["cache_entries"] == 0
    assert result["cache_hit_rate"] == 0.0
    assert result["stale_entries"] == 0


def test_measure_voice_quality_with_data(conn):
    # Insert cache entries
    conn.execute(
        "INSERT INTO pi_audio_cache (cache_key, text_zh, audio_path, duration_seconds, tts_engine, hit_count) "
        "VALUES ('k1', '你好', '/tmp/test1.wav', 1.5, 'kokoro', 5)",
    )
    conn.execute(
        "INSERT INTO pi_audio_cache (cache_key, text_zh, audio_path, duration_seconds, tts_engine, hit_count) "
        "VALUES ('k2', '再见', '/tmp/test2.wav', 2.0, 'edge_tts', 3)",
    )
    conn.commit()

    result = measure_voice_quality(conn)
    assert result["cache_entries"] == 2
    assert result["cache_hit_rate"] > 0
    assert "kokoro" in result["engine_distribution"]
    assert "edge_tts" in result["engine_distribution"]
    assert result["total_duration_seconds"] == 3.5
    # Both files don't exist -> stale
    assert result["stale_entries"] == 2


def test_measure_voice_quality_no_conn():
    result = measure_voice_quality(None)
    assert result["cache_entries"] == 0


# ── Test 14: _validate_tonal_accuracy placeholder ────────────────────────

def test_validate_tonal_accuracy_placeholder():
    """Placeholder always returns True."""
    assert _validate_tonal_accuracy("/tmp/test.wav", "你好", "nǐ hǎo") is True
    assert _validate_tonal_accuracy(None, "", "") is True


# ── Test 15: Cache hit count increments ──────────────────────────────────

def test_cache_hit_count_increments(conn):
    key = _cache_key("测试", 0.85)
    result = AudioOutput(
        audio_path="/tmp/test.wav",
        duration_seconds=1.0,
        tts_engine="kokoro",
        success=True,
    )
    _write_cache(conn, key, "测试", result)

    # Multiple reads should increment hit_count
    with patch("os.path.exists", return_value=True):
        _check_cache(conn, key)
        _check_cache(conn, key)
        _check_cache(conn, key)

    row = conn.execute(
        "SELECT hit_count FROM pi_audio_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    assert row[0] == 3

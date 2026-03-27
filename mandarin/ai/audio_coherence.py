"""Audio Coherence Verification (Doc 23 B-03).

Checks that generated TTS audio matches intended pinyin/text:
1. Generate audio via edge-tts
2. Transcribe with faster-whisper (local STT)
3. Convert expected + transcribed to pinyin via pypinyin
4. Compare pinyin sequences (Levenshtein similarity)
"""

import logging
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PASS_THRESHOLD = 0.85  # Minimum similarity score to pass

try:
    from pypinyin import pinyin, Style as PinyinStyle
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False
    logger.debug("pypinyin not installed — audio coherence checks disabled")

try:
    from faster_whisper import WhisperModel
    _HAS_WHISPER = True
    _whisper_model = None
except ImportError:
    _HAS_WHISPER = False
    _whisper_model = None
    logger.debug("faster-whisper not installed — audio coherence checks disabled")


def _get_whisper_model():
    """Lazy-load Whisper model (singleton)."""
    global _whisper_model
    if _whisper_model is None and _HAS_WHISPER:
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def _hanzi_to_pinyin(text: str) -> str:
    """Convert hanzi to pinyin string using pypinyin."""
    if not _HAS_PYPINYIN or not text:
        return ""
    result = pinyin(text, style=PinyinStyle.TONE)
    return " ".join(p[0] for p in result)


def _levenshtein_similarity(s1: str, s2: str) -> float:
    """Compute Levenshtein similarity (1 - normalized distance)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    # Use word-level comparison for pinyin
    words1 = s1.lower().split()
    words2 = s2.lower().split()
    len1, len2 = len(words1), len(words2)

    if len1 == 0 and len2 == 0:
        return 1.0

    # DP matrix
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if words1[i - 1] == words2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,       # deletion
                dp[i][j - 1] + 1,       # insertion
                dp[i - 1][j - 1] + cost  # substitution
            )

    distance = dp[len1][len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


def check_audio_coherence(
    conn: sqlite3.Connection,
    content_item_id: int,
) -> dict:
    """Check TTS→STT→pinyin coherence for a content item.

    Returns dict with similarity_score, passed, details.
    """
    if not _HAS_PYPINYIN:
        return {"status": "skipped", "reason": "pypinyin not installed"}
    if not _HAS_WHISPER:
        return {"status": "skipped", "reason": "faster-whisper not installed"}

    # Get content item
    item = conn.execute(
        "SELECT hanzi, pinyin FROM content_item WHERE id = ?",
        (content_item_id,),
    ).fetchone()
    if not item:
        return {"status": "error", "reason": "content item not found"}

    hanzi = item["hanzi"]
    item["pinyin"] or ""

    # Convert expected hanzi to pinyin
    expected_pinyin = _hanzi_to_pinyin(hanzi)

    # Generate TTS audio to temp file
    try:
        import asyncio
        audio_path = _generate_tts(hanzi)
        if not audio_path:
            return {"status": "error", "reason": "TTS generation failed"}
    except Exception as e:
        return {"status": "error", "reason": f"TTS error: {e}"}

    # Transcribe with Whisper
    try:
        model = _get_whisper_model()
        if model is None:
            return {"status": "error", "reason": "Whisper model unavailable"}

        segments, info = model.transcribe(str(audio_path), language="zh")
        transcribed_text = "".join(s.text for s in segments).strip()
    except Exception as e:
        return {"status": "error", "reason": f"Whisper error: {e}"}
    finally:
        # Clean up temp audio file
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

    # Convert transcribed text to pinyin
    transcribed_pinyin = _hanzi_to_pinyin(transcribed_text)

    # Compare pinyin sequences
    similarity = _levenshtein_similarity(expected_pinyin, transcribed_pinyin)
    passed = similarity >= _PASS_THRESHOLD

    # Log result
    try:
        conn.execute("""
            INSERT INTO audio_coherence_check
            (content_item_id, expected_pinyin, transcribed_text,
             transcribed_pinyin, similarity_score, passed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            content_item_id, expected_pinyin, transcribed_text,
            transcribed_pinyin, similarity, 1 if passed else 0,
        ))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Create expedite work item for failures
    if not passed:
        _create_failure_work_item(conn, content_item_id, hanzi,
                                  expected_pinyin, transcribed_pinyin, similarity)

    return {
        "status": "completed",
        "content_item_id": content_item_id,
        "hanzi": hanzi,
        "expected_pinyin": expected_pinyin,
        "transcribed_text": transcribed_text,
        "transcribed_pinyin": transcribed_pinyin,
        "similarity_score": round(similarity, 4),
        "passed": passed,
    }


def _generate_tts(text: str) -> str | None:
    """Generate TTS audio to a temp file using edge-tts."""
    import asyncio

    async def _gen():
        communicate = None
        try:
            import edge_tts
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
            await communicate.save(tmp.name)
            return tmp.name
        except Exception as e:
            logger.warning("TTS generation failed: %s", e)
            return None
        finally:
            if communicate is not None:
                for attr in ("session", "_session"):
                    sess = getattr(communicate, attr, None)
                    if sess is not None and hasattr(sess, "close"):
                        try:
                            await sess.close()
                        except Exception:
                            pass

    def _run_in_fresh_loop():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_gen())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(_run_in_fresh_loop).result(timeout=30)
        return _run_in_fresh_loop()
    except RuntimeError:
        return _run_in_fresh_loop()


def _create_failure_work_item(
    conn: sqlite3.Connection,
    content_item_id: int,
    hanzi: str,
    expected: str,
    transcribed: str,
    score: float,
) -> None:
    """Create an expedite work item for coherence failure."""
    try:
        existing = conn.execute(
            """SELECT id FROM work_item
               WHERE title LIKE ? AND status NOT IN ('done')""",
            (f"Audio coherence failure: {hanzi}%",),
        ).fetchone()
        if existing:
            return

        conn.execute("""
            INSERT INTO work_item
            (title, description, item_type, status, service_class, ready_at)
            VALUES (?, ?, 'standard', 'ready', 'expedite', datetime('now'))
        """, (
            f"Audio coherence failure: {hanzi}",
            f"Content item {content_item_id}: TTS audio does not match expected pinyin.\n"
            f"Expected pinyin: {expected}\n"
            f"Transcribed pinyin: {transcribed}\n"
            f"Similarity score: {score:.2%} (threshold: {_PASS_THRESHOLD:.0%})\n"
            f"- [ ] Review content item pronunciation\n"
            f"- [ ] Check TTS voice quality\n"
            f"- [ ] Re-run coherence check",
        ))
        conn.commit()
    except sqlite3.OperationalError:
        pass


def batch_check_coherence(
    conn: sqlite3.Connection,
    limit: int = 50,
) -> list[dict]:
    """Check coherence for unchecked content items."""
    try:
        items = conn.execute("""
            SELECT ci.id FROM content_item ci
            WHERE ci.status = 'drill_ready'
            AND NOT EXISTS (
                SELECT 1 FROM audio_coherence_check acc
                WHERE acc.content_item_id = ci.id
            )
            LIMIT ?
        """, (limit,)).fetchall()
    except sqlite3.OperationalError:
        return []

    results = []
    for item in items:
        result = check_audio_coherence(conn, item["id"])
        results.append(result)

    return results


def get_coherence_failures(conn: sqlite3.Connection) -> list[dict]:
    """Get items that failed coherence check and need human review."""
    try:
        rows = conn.execute("""
            SELECT acc.*, ci.hanzi, ci.pinyin as db_pinyin, ci.english
            FROM audio_coherence_check acc
            JOIN content_item ci ON ci.id = acc.content_item_id
            WHERE acc.passed = 0
            ORDER BY acc.checked_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []

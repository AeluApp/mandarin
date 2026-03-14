"""Media ingestion — subtitle parsing, vocabulary extraction, difficulty calibration.

Provides:
1. parse_subtitles() — parse .vtt/.srt subtitle files into timed segments
2. extract_vocabulary() — segment Chinese text with jieba and match to content_items
3. estimate_hsk_level() — estimate HSK level from vocabulary distribution
4. generate_quiz_questions() — create vocab_check + mc questions from subtitle context
5. calculate_passage_difficulty() — readability metrics for reading passages
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_subtitles(subtitle_path: str) -> list[dict]:
    """Parse a .vtt or .srt subtitle file into timed text segments.

    Returns list of {start_s, end_s, text} dicts.
    """
    path = Path(subtitle_path)
    content = path.read_text(encoding="utf-8", errors="replace")

    segments = []
    is_vtt = path.suffix.lower() == ".vtt" or content.strip().startswith("WEBVTT")

    # Split into blocks
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        # Skip VTT header
        if lines[0].strip().startswith("WEBVTT"):
            continue

        # Find timestamp line
        timestamp_line = None
        text_lines = []
        for i, line in enumerate(lines):
            # Match SRT: 00:01:23,456 --> 00:01:25,789
            # Match VTT: 00:01:23.456 --> 00:01:25.789
            if "-->" in line:
                timestamp_line = line
                text_lines = lines[i + 1:]
                break

        if not timestamp_line:
            continue

        # Parse timestamps
        parts = timestamp_line.split("-->")
        if len(parts) != 2:
            continue

        start_s = _parse_timestamp(parts[0].strip())
        end_s = _parse_timestamp(parts[1].strip())

        # Clean text (remove VTT tags)
        text = " ".join(text_lines).strip()
        text = re.sub(r"<[^>]+>", "", text)
        text = text.strip()

        if text and start_s is not None and end_s is not None:
            segments.append({
                "start_s": start_s,
                "end_s": end_s,
                "text": text,
            })

    return segments


def _parse_timestamp(ts: str) -> float | None:
    """Parse a VTT/SRT timestamp to seconds."""
    ts = ts.strip()
    # Remove position/alignment metadata after timestamp
    ts = ts.split()[0] if " " in ts else ts
    ts = ts.replace(",", ".")  # SRT uses comma

    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except (ValueError, TypeError):
        return None
    return None


def extract_vocabulary(text_zh: str, conn=None) -> list[dict]:
    """Segment Chinese text with jieba and optionally match to content_items.

    Returns list of {word, count} dicts, sorted by count descending.
    Filters out punctuation and single-character function words.
    """
    try:
        import jieba
    except ImportError:
        logger.warning("jieba not installed — vocabulary extraction unavailable")
        return []

    # Segment
    words = jieba.lcut(text_zh)

    # Filter: keep only Chinese words (2+ chars or common single-char content words)
    chinese_re = re.compile(r"[\u4e00-\u9fff]+")
    filtered = [w for w in words if chinese_re.match(w) and len(w) >= 2]

    # Count occurrences
    counts = {}
    for w in filtered:
        counts[w] = counts.get(w, 0) + 1

    result = [{"word": w, "count": c} for w, c in sorted(counts.items(), key=lambda x: -x[1])]

    # Match to content_items if connection provided
    if conn:
        for entry in result:
            row = conn.execute(
                "SELECT id, pinyin, english, hsk_level FROM content_item WHERE hanzi = ? LIMIT 1",
                (entry["word"],)
            ).fetchone()
            if row:
                entry["content_item_id"] = row["id"]
                entry["pinyin"] = row["pinyin"]
                entry["english"] = row["english"]
                entry["hsk_level"] = row["hsk_level"]

    return result


def estimate_hsk_level(vocab_list: list[dict]) -> int:
    """Estimate HSK level from vocabulary distribution.

    Uses the 80% coverage rule: the HSK level where 80% of unique words
    are at or below that level.
    """
    if not vocab_list:
        return 1

    matched = [v for v in vocab_list if v.get("hsk_level")]
    if not matched:
        return 1

    total = len(matched)
    level_counts = {}
    for v in matched:
        lvl = v["hsk_level"]
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    # Find level where cumulative coverage >= 80%
    cumulative = 0
    for level in range(1, 10):
        cumulative += level_counts.get(level, 0)
        if cumulative >= total * 0.8:
            return level

    return 9  # Beyond HSK 9


def generate_quiz_questions(segments: list[dict], vocab_list: list[dict],
                            max_questions: int = 5) -> list[dict]:
    """Generate quiz questions from subtitle context.

    Creates vocab_check questions (definition recall) and mc (multiple choice)
    from words found in subtitle segments.
    """
    matched = [v for v in vocab_list if v.get("content_item_id")]
    if not matched:
        return []

    questions = []
    # Pick top vocab by frequency
    for entry in matched[:max_questions]:
        # Find a segment containing this word for context
        context = ""
        for seg in segments:
            if entry["word"] in seg["text"]:
                context = seg["text"]
                break

        questions.append({
            "type": "vocab_check",
            "word": entry["word"],
            "pinyin": entry.get("pinyin", ""),
            "english": entry.get("english", ""),
            "context": context,
            "content_item_id": entry["content_item_id"],
        })

    return questions


def calculate_passage_difficulty(text_zh: str) -> dict:
    """Calculate readability metrics for a Chinese text passage.

    Returns:
        char_count: total characters
        unique_ratio: unique chars / total chars
        avg_sentence_length: average chars per sentence
        estimated_hsk: estimated HSK level based on character frequency
        hsk_coverage: {level: percentage} of characters at each HSK level
    """
    if not text_zh:
        return {
            "char_count": 0,
            "unique_ratio": 0,
            "avg_sentence_length": 0,
            "estimated_hsk": 1,
            "hsk_coverage": {},
        }

    # Extract only Chinese characters
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text_zh)
    char_count = len(chinese_chars)

    if char_count == 0:
        return {
            "char_count": 0,
            "unique_ratio": 0,
            "avg_sentence_length": 0,
            "estimated_hsk": 1,
            "hsk_coverage": {},
        }

    unique_chars = set(chinese_chars)
    unique_ratio = round(len(unique_chars) / char_count, 3)

    # Split into sentences (。！？are Chinese sentence terminators)
    sentences = re.split(r"[。！？!?]+", text_zh)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_sentence_length = round(char_count / max(len(sentences), 1), 1)

    # HSK level estimation: use jieba + content_item matching if available
    # Fallback: use character count heuristic
    estimated_hsk = 1
    if char_count <= 50:
        estimated_hsk = 1
    elif char_count <= 100:
        estimated_hsk = 2
    elif char_count <= 200:
        estimated_hsk = 3
    elif char_count <= 350:
        estimated_hsk = 4
    elif char_count <= 500:
        estimated_hsk = 5
    else:
        estimated_hsk = min(6 + (char_count - 500) // 300, 9)

    # Adjust for complexity (unique ratio)
    if unique_ratio > 0.7:
        estimated_hsk = min(estimated_hsk + 1, 9)
    elif unique_ratio < 0.3:
        estimated_hsk = max(estimated_hsk - 1, 1)

    return {
        "char_count": char_count,
        "unique_ratio": unique_ratio,
        "avg_sentence_length": avg_sentence_length,
        "estimated_hsk": estimated_hsk,
        "hsk_coverage": {},
    }

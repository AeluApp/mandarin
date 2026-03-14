#!/usr/bin/env python3
"""Ingest Chinese subtitles as listening/dialogue content.

Reads SRT/VTT files from a directory, parses timestamps and text,
estimates HSK level per subtitle block, and creates dialogue_scenario
records for use in listening drills.

WARNING: OpenSubtitles content licensing varies and is generally NOT
cleared for commercial use. This script is for subtitles YOU own or
have licensed. For production use, only ingest subtitles from:
- Content you created (Qwen2.5 generated transcripts)
- CC-BY licensed sources (verify per file)
- Public domain works

Usage:
    python scripts/ingest_open_subtitles.py <directory> [--source "Movie Name"] [--dry-run]
    python scripts/ingest_open_subtitles.py subs/ --source "哪吒" --hsk-max 4
"""

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


# ── HSK word frequency data ──────────────────────────────────────────

_HSK_WORDS = {}
_HSK_LOADED = False


def _load_hsk_words(conn):
    """Load HSK word->level mapping from the content_item table."""
    global _HSK_WORDS, _HSK_LOADED
    if _HSK_LOADED:
        return
    try:
        rows = conn.execute(
            "SELECT hanzi, hsk_level FROM content_item WHERE hsk_level IS NOT NULL"
        ).fetchall()
        for r in rows:
            _HSK_WORDS[r["hanzi"]] = r["hsk_level"]
        _HSK_LOADED = True
    except sqlite3.Error:
        pass


def estimate_hsk_level(text: str, conn=None) -> int:
    """Estimate HSK level of Chinese text using jieba segmentation."""
    try:
        import jieba
    except ImportError:
        return 3

    if conn:
        _load_hsk_words(conn)

    if not _HSK_WORDS:
        return 3

    words = list(jieba.cut(text))
    levels = []
    unknown_count = 0
    for w in words:
        w = w.strip()
        if not w or not re.search(r'[\u4e00-\u9fff]', w):
            continue
        level = _HSK_WORDS.get(w)
        if level:
            levels.append(level)
        else:
            unknown_count += 1

    if not levels:
        return 3

    levels.sort()
    idx = int(len(levels) * 0.8)
    estimated = levels[min(idx, len(levels) - 1)]

    total_chinese = len(levels) + unknown_count
    unknown_ratio = unknown_count / total_chinese if total_chinese > 0 else 0
    if unknown_ratio > 0.3:
        estimated = min(9, estimated + 1)
    if unknown_ratio > 0.5:
        estimated = min(9, estimated + 1)

    return max(1, min(9, estimated))


# ── SRT/VTT parsing ─────────────────────────────────────────────────


def parse_timestamp(ts: str) -> float | None:
    """Parse a VTT/SRT timestamp to seconds.

    Handles: 00:01:23,456 (SRT) and 00:01:23.456 (VTT)
    """
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


def parse_subtitle_file(filepath: Path) -> list:
    """Parse an SRT or VTT subtitle file.

    Returns list of {start_s, end_s, text} dicts.
    """
    content = filepath.read_text(encoding="utf-8", errors="replace")
    segments = []

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

        start_s = parse_timestamp(parts[0])
        end_s = parse_timestamp(parts[1])

        # Clean text
        text = " ".join(text_lines).strip()
        # Remove HTML/VTT tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove leading/trailing whitespace
        text = text.strip()

        if text and start_s is not None and end_s is not None:
            segments.append({
                "start_s": start_s,
                "end_s": end_s,
                "text": text,
            })

    return segments


def is_chinese_text(text: str) -> bool:
    """Check if text contains meaningful Chinese content."""
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    return len(chinese_chars) >= 2


def group_into_dialogue_turns(segments: list, max_gap_s: float = 3.0) -> list:
    """Group consecutive subtitle segments into dialogue exchanges.

    Segments within max_gap_s of each other are grouped together.
    Returns list of groups, each group is a list of segments.
    """
    if not segments:
        return []

    groups = []
    current_group = [segments[0]]

    for seg in segments[1:]:
        prev_end = current_group[-1]["end_s"]
        if seg["start_s"] - prev_end <= max_gap_s:
            current_group.append(seg)
        else:
            groups.append(current_group)
            current_group = [seg]

    if current_group:
        groups.append(current_group)

    return groups


def _generate_scenario_id(source: str, group_idx: int) -> str:
    """Generate a stable ID for a dialogue scenario."""
    raw = f"{source}:group_{group_idx}"
    return "sub_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def ingest_subtitle_file(
    conn, filepath: Path, source_name: str, hsk_max: int = 9,
    dry_run: bool = False
) -> dict:
    """Parse and ingest a single subtitle file.

    Returns counts: {segments, groups, inserted, skipped_dup, skipped_level, skipped_quality}.
    """
    counts = {
        "segments": 0, "groups": 0, "inserted": 0,
        "skipped_dup": 0, "skipped_level": 0, "skipped_quality": 0,
    }

    segments = parse_subtitle_file(filepath)
    counts["segments"] = len(segments)

    # Filter to Chinese-only segments
    chinese_segments = [s for s in segments if is_chinese_text(s["text"])]
    if not chinese_segments:
        logger.debug("No Chinese segments in %s", filepath.name)
        return counts

    # Group into dialogue turns
    groups = group_into_dialogue_turns(chinese_segments)
    counts["groups"] = len(groups)

    file_source = f"subtitle:{filepath.name}"

    for i, group in enumerate(groups):
        # Combine text for HSK estimation
        combined_text = " ".join(seg["text"] for seg in group)

        # Quality: at least 2 turns with meaningful Chinese
        if len(group) < 2:
            # Single subtitle — insert as sentence content_item instead
            seg = group[0]
            if not is_chinese_text(seg["text"]) or len(seg["text"]) < 4:
                counts["skipped_quality"] += 1
                continue

        hsk_level = estimate_hsk_level(combined_text, conn=conn)
        if hsk_level > hsk_max:
            counts["skipped_level"] += 1
            continue

        scenario_id = _generate_scenario_id(f"{source_name}:{filepath.name}", i)

        # Dedup check
        existing = conn.execute(
            "SELECT 1 FROM dialogue_scenario WHERE title = ? LIMIT 1",
            (scenario_id,),
        ).fetchone()
        if existing:
            counts["skipped_dup"] += 1
            continue

        # Build dialogue tree JSON
        turns = []
        for j, seg in enumerate(group):
            turns.append({
                "speaker": "A" if j % 2 == 0 else "B",
                "hanzi": seg["text"],
                "pinyin": "",
                "english": "",
                "start_s": seg["start_s"],
                "end_s": seg["end_s"],
            })

        tree_json = json.dumps({
            "type": "linear",
            "source": source_name,
            "file": filepath.name,
            "turns": turns,
        }, ensure_ascii=False)

        if dry_run:
            if counts["inserted"] < 5:
                logger.info(
                    "  [DRY] HSK %d, %d turns: %s",
                    hsk_level, len(turns), combined_text[:60],
                )
            counts["inserted"] += 1
            continue

        try:
            conn.execute(
                """INSERT INTO dialogue_scenario
                   (title, hsk_level, scenario_type, tree_json, difficulty)
                   VALUES (?, ?, 'subtitle', ?, ?)""",
                (scenario_id, hsk_level, tree_json, hsk_level / 9.0),
            )
            counts["inserted"] += 1
        except sqlite3.Error as e:
            logger.warning("Insert failed for group %d in %s: %s", i, filepath.name, e)

    if not dry_run:
        conn.commit()

    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Chinese subtitles (SRT/VTT) as dialogue content"
    )
    parser.add_argument(
        "directory",
        help="Directory containing SRT/VTT subtitle files",
    )
    parser.add_argument(
        "--source", type=str, default="unknown",
        help="Source name (e.g., movie title) for attribution",
    )
    parser.add_argument(
        "--hsk-max", type=int, default=9,
        help="Maximum HSK level to accept (default: 9)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and estimate but do not write to DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    sub_dir = Path(args.directory)
    if not sub_dir.exists():
        logger.error("Directory not found: %s", sub_dir)
        sys.exit(1)

    # Find subtitle files
    sub_files = sorted(
        p for p in sub_dir.iterdir()
        if p.suffix.lower() in {".srt", ".vtt"}
    )
    logger.info("Found %d subtitle files in %s", len(sub_files), sub_dir)

    if not sub_files:
        logger.info("No SRT/VTT files to process")
        return

    from mandarin import db

    totals = {
        "files": len(sub_files), "segments": 0, "groups": 0,
        "inserted": 0, "skipped_dup": 0, "skipped_level": 0, "skipped_quality": 0,
    }

    with db.connection() as conn:
        for filepath in sub_files:
            logger.info("Processing: %s", filepath.name)
            counts = ingest_subtitle_file(
                conn, filepath,
                source_name=args.source,
                hsk_max=args.hsk_max,
                dry_run=args.dry_run,
            )
            for k in ["segments", "groups", "inserted",
                       "skipped_dup", "skipped_level", "skipped_quality"]:
                totals[k] += counts[k]

            logger.info(
                "  %s: %d segments, %d groups, %d inserted",
                filepath.name, counts["segments"], counts["groups"], counts["inserted"],
            )

    prefix = "DRY RUN:" if args.dry_run else "Done."
    logger.info(
        "%s Files: %d, Segments: %d, Groups: %d, Inserted: %d, "
        "Skipped (dup): %d, Skipped (level): %d, Skipped (quality): %d",
        prefix, totals["files"], totals["segments"], totals["groups"],
        totals["inserted"], totals["skipped_dup"],
        totals["skipped_level"], totals["skipped_quality"],
    )


if __name__ == "__main__":
    main()

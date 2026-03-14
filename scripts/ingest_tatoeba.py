#!/usr/bin/env python3
"""Ingest Chinese-English sentence pairs from Tatoeba.

Tatoeba sentences are released under CC BY 2.0 FR.
Source: https://tatoeba.org/

Downloads the sentence export, filters for Chinese (cmn) with English (eng)
translations, estimates HSK level via jieba segmentation, and creates
content_item records with item_type='sentence'.

Usage:
    python scripts/ingest_tatoeba.py [--limit 10000] [--dry-run] [--verbose]
    python scripts/ingest_tatoeba.py --file sentences.csv --links links.csv
"""

import argparse
import csv
import io
import logging
import re
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

SENTENCES_URL = "https://downloads.tatoeba.org/exports/sentences.tar.bz2"
LINKS_URL = "https://downloads.tatoeba.org/exports/links.tar.bz2"

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
        logger.info("Loaded %d HSK words for level estimation", len(_HSK_WORDS))
    except sqlite3.Error:
        logger.warning("Could not load HSK words from DB")


def estimate_hsk_level(text: str, conn=None) -> int:
    """Estimate HSK level of Chinese text using jieba segmentation.

    Returns estimated HSK level (1-9). Defaults to 3 if unable to estimate.
    """
    try:
        import jieba
    except ImportError:
        return 3

    if conn:
        _load_hsk_words(conn)

    if not _HSK_WORDS:
        return 3

    words = list(jieba.cut(text))
    if not words:
        return 1

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

    # Use 80th percentile of word levels as the sentence level
    levels.sort()
    idx = int(len(levels) * 0.8)
    estimated = levels[min(idx, len(levels) - 1)]

    # Bump up if many unknown words
    total_chinese = len(levels) + unknown_count
    unknown_ratio = unknown_count / total_chinese if total_chinese > 0 else 0
    if unknown_ratio > 0.3:
        estimated = min(9, estimated + 1)
    if unknown_ratio > 0.5:
        estimated = min(9, estimated + 1)

    return max(1, min(9, estimated))


# ── Download & parse ─────────────────────────────────────────────────


def download_file(url: str, dest_dir: Path, timeout: int = 120) -> Path:
    """Download a file from URL. Returns path to downloaded file."""
    try:
        import requests
    except ImportError:
        logger.error("requests not installed: pip install requests")
        raise SystemExit(1)

    filename = url.split("/")[-1]
    dest_path = dest_dir / filename
    logger.info("Downloading %s ...", url)

    try:
        resp = requests.get(
            url, timeout=timeout, stream=True,
            headers={"User-Agent": "Aelu/1.0 (Mandarin Learning)"},
        )
        resp.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)

        logger.info("Downloaded %d bytes", dest_path.stat().st_size)
        return dest_path

    except Exception as e:
        logger.error("Download failed for %s: %s", url, e)
        raise


def parse_sentences_tsv(content: str) -> dict:
    """Parse Tatoeba sentences.csv TSV content.

    Format: id<TAB>lang<TAB>text
    Returns dict of {id: (lang, text)}.
    """
    sentences = {}
    reader = csv.reader(io.StringIO(content), delimiter="\t")
    for row in reader:
        if len(row) < 3:
            continue
        try:
            sid = int(row[0])
        except ValueError:
            continue
        lang = row[1].strip()
        text = row[2].strip()
        if lang and text:
            sentences[sid] = (lang, text)
    return sentences


def parse_links_tsv(content: str) -> list:
    """Parse Tatoeba links.csv TSV content.

    Format: sentence_id<TAB>translation_id
    Returns list of (id1, id2) tuples.
    """
    links = []
    reader = csv.reader(io.StringIO(content), delimiter="\t")
    for row in reader:
        if len(row) < 2:
            continue
        try:
            links.append((int(row[0]), int(row[1])))
        except ValueError:
            continue
    return links


def extract_from_tar(tar_path: Path, inner_filename: str) -> str:
    """Extract a file from a .tar.bz2 archive. Returns content as string."""
    with tarfile.open(tar_path, "r:bz2") as tar:
        for member in tar.getmembers():
            if member.name.endswith(inner_filename):
                f = tar.extractfile(member)
                if f:
                    return f.read().decode("utf-8", errors="replace")
    raise FileNotFoundError(f"{inner_filename} not found in {tar_path}")


def find_chinese_english_pairs(
    sentences: dict, links: list, limit: int = 10000
) -> list:
    """Match Chinese sentences with their English translations.

    Returns list of (cmn_id, cmn_text, eng_text) tuples.
    """
    # Index: sentence_id -> set of translation_ids
    link_map = {}
    for sid, tid in links:
        link_map.setdefault(sid, set()).add(tid)

    pairs = []
    seen_cmn = set()

    for sid, (lang, text) in sentences.items():
        if lang != "cmn":
            continue
        if sid in seen_cmn:
            continue

        # Find English translations
        translation_ids = link_map.get(sid, set())
        for tid in translation_ids:
            if tid in sentences and sentences[tid][0] == "eng":
                pairs.append((sid, text, sentences[tid][1]))
                seen_cmn.add(sid)
                break  # One English translation per Chinese sentence

        if len(pairs) >= limit:
            break

    return pairs


def is_good_sentence(text: str) -> bool:
    """Filter out poor-quality sentences."""
    # Must contain Chinese characters
    if not re.search(r'[\u4e00-\u9fff]', text):
        return False
    # Reasonable length (3-80 Chinese chars)
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chinese_chars) < 3 or len(chinese_chars) > 80:
        return False
    # No excessive punctuation or garbage
    if text.count("...") > 2:
        return False
    return True


def ingest_pairs(conn, pairs: list, dry_run: bool = False) -> dict:
    """Insert sentence pairs as content_items.

    Returns counts dict: {inserted, skipped_dup, skipped_quality, total}.
    """
    counts = {"inserted": 0, "skipped_dup": 0, "skipped_quality": 0, "total": len(pairs)}

    for tatoeba_id, cmn_text, eng_text in pairs:
        # Quality filter
        if not is_good_sentence(cmn_text):
            counts["skipped_quality"] += 1
            continue

        # Dedup: check if this exact hanzi already exists with tatoeba source
        existing = conn.execute(
            "SELECT 1 FROM content_item WHERE hanzi = ? AND source = ? LIMIT 1",
            (cmn_text, "tatoeba"),
        ).fetchone()
        if existing:
            counts["skipped_dup"] += 1
            continue

        # Also check if this hanzi exists from any source (broader dedup)
        existing_any = conn.execute(
            "SELECT 1 FROM content_item WHERE hanzi = ? LIMIT 1",
            (cmn_text,),
        ).fetchone()
        if existing_any:
            counts["skipped_dup"] += 1
            continue

        hsk_level = estimate_hsk_level(cmn_text, conn=conn)

        if dry_run:
            if counts["inserted"] < 10:
                logger.info(
                    "  [DRY] HSK %d: %s -> %s",
                    hsk_level, cmn_text[:40], eng_text[:40],
                )
            counts["inserted"] += 1
            continue

        try:
            conn.execute(
                """INSERT INTO content_item
                   (hanzi, pinyin, english, item_type, hsk_level, source,
                    source_context, status, review_status, scale_level)
                   VALUES (?, '', ?, 'sentence', ?, 'tatoeba', ?, 'drill_ready',
                           'pending_review', 'sentence')""",
                (cmn_text, eng_text, hsk_level, f"tatoeba:{tatoeba_id}"),
            )
            counts["inserted"] += 1
        except sqlite3.Error as e:
            logger.warning("Insert failed for tatoeba:%d: %s", tatoeba_id, e)

        # Commit in batches
        if counts["inserted"] % 500 == 0:
            conn.commit()
            logger.info("  Progress: %d inserted...", counts["inserted"])

    if not dry_run:
        conn.commit()

    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Tatoeba Chinese-English sentence pairs (CC BY 2.0 FR)"
    )
    parser.add_argument(
        "--limit", type=int, default=10000,
        help="Maximum sentence pairs to import (default: 10000)",
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Path to local sentences.tar.bz2 (skip download)",
    )
    parser.add_argument(
        "--links", type=str, default=None,
        help="Path to local links.tar.bz2 (skip download)",
    )
    parser.add_argument(
        "--sentences-csv", type=str, default=None,
        help="Path to pre-extracted sentences.csv TSV file",
    )
    parser.add_argument(
        "--links-csv", type=str, default=None,
        help="Path to pre-extracted links.csv TSV file",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and estimate but do not write to DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    from mandarin import db

    # ── Load sentence data ──
    if args.sentences_csv and args.links_csv:
        # Pre-extracted CSV files
        logger.info("Loading pre-extracted CSVs...")
        sentences_content = Path(args.sentences_csv).read_text(encoding="utf-8", errors="replace")
        links_content = Path(args.links_csv).read_text(encoding="utf-8", errors="replace")
    elif args.file and args.links:
        # Local tar.bz2 archives
        logger.info("Extracting from local archives...")
        sentences_content = extract_from_tar(Path(args.file), "sentences.csv")
        links_content = extract_from_tar(Path(args.links), "links.csv")
    else:
        # Download
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            sentences_tar = download_file(SENTENCES_URL, tmpdir)
            links_tar = download_file(LINKS_URL, tmpdir)
            logger.info("Extracting sentences...")
            sentences_content = extract_from_tar(sentences_tar, "sentences.csv")
            logger.info("Extracting links...")
            links_content = extract_from_tar(links_tar, "links.csv")

    # ── Parse ──
    logger.info("Parsing sentences...")
    sentences = parse_sentences_tsv(sentences_content)
    logger.info("Parsed %d sentences total", len(sentences))

    cmn_count = sum(1 for _, (lang, _) in sentences.items() if lang == "cmn")
    eng_count = sum(1 for _, (lang, _) in sentences.items() if lang == "eng")
    logger.info("  Chinese (cmn): %d, English (eng): %d", cmn_count, eng_count)

    logger.info("Parsing links...")
    links = parse_links_tsv(links_content)
    logger.info("Parsed %d translation links", len(links))

    # ── Match pairs ──
    logger.info("Finding Chinese-English pairs (limit %d)...", args.limit)
    pairs = find_chinese_english_pairs(sentences, links, limit=args.limit)
    logger.info("Found %d Chinese-English sentence pairs", len(pairs))

    if not pairs:
        logger.info("No pairs found — nothing to ingest")
        return

    # ── Ingest ──
    with db.connection() as conn:
        counts = ingest_pairs(conn, pairs, dry_run=args.dry_run)

    prefix = "DRY RUN: would have" if args.dry_run else "Done."
    logger.info(
        "%s Inserted: %d, Skipped (dup): %d, Skipped (quality): %d, Total pairs: %d",
        prefix, counts["inserted"], counts["skipped_dup"],
        counts["skipped_quality"], counts["total"],
    )


if __name__ == "__main__":
    main()

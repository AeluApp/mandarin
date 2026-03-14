#!/usr/bin/env python3
"""Ingest YouTube/Bilibili media metadata + subtitles for the media catalog.

Usage:
    python scripts/ingest_media.py URL [--output FILE] [--max-questions N]
    python scripts/ingest_media.py --help

Requires: yt-dlp, jieba

Downloads metadata and subtitles (if available), extracts vocabulary,
estimates HSK level, generates quiz questions, and outputs a JSON entry
compatible with data/media_catalog.json.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(
        description="Ingest YouTube/Bilibili media for the Aelu media catalog.",
        epilog="Example: python scripts/ingest_media.py 'https://youtube.com/watch?v=abc123'",
    )
    parser.add_argument("url", nargs="?", help="YouTube or Bilibili video URL")
    parser.add_argument("--batch", help="Path to text file with one URL per line for batch processing")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--max-questions", type=int, default=5,
                        help="Max quiz questions to generate (default: 5)")
    parser.add_argument("--db", help="Path to SQLite database for vocabulary matching")

    args = parser.parse_args()

    if args.batch:
        # Batch mode: process multiple URLs from a file
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"Error: batch file not found: {args.batch}", file=sys.stderr)
            sys.exit(1)
        urls = [line.strip() for line in batch_file.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")]
        print(f"Batch processing {len(urls)} URLs...", file=sys.stderr)

        entries = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] {url}", file=sys.stderr)
            try:
                entry = ingest_single_url(url, args)
                entries.append(entry)
                print(f"  OK: {entry.get('title', 'unknown')}", file=sys.stderr)
            except Exception as e:
                print(f"  FAILED: {e}", file=sys.stderr)
                continue

        # Output all entries
        output_json = json.dumps(entries, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output_json, encoding="utf-8")
            print(f"\nWritten {len(entries)} entries to {args.output}", file=sys.stderr)
        else:
            print(output_json)
        print(f"\nBatch complete: {len(entries)}/{len(urls)} succeeded", file=sys.stderr)
        return

    if not args.url:
        parser.error("url is required (or use --batch)")

    try:
        import yt_dlp
    except ImportError:
        print("Error: yt-dlp is required. Install with: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)

    entry = ingest_single_url(args.url, args)
    output_json = json.dumps(entry, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"\nWritten to {args.output}", file=sys.stderr)
    else:
        print(output_json)
    print("\nDone. Review the entry and add to data/media_catalog.json", file=sys.stderr)


def ingest_single_url(url, args):
    """Ingest a single URL and return a catalog entry dict."""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is required. Install with: pip install yt-dlp")

    # Step 1: Download metadata + subtitles
    print(f"Fetching metadata for: {url}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-Hans", "zh-Hant", "zh", "en"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmpdir, "%(id)s"),
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_id = info.get("id", "unknown")
        title = info.get("title", "Untitled")
        channel = info.get("channel", info.get("uploader", "Unknown"))
        duration = info.get("duration", 0)
        description = (info.get("description") or "")[:500]

        print(f"  Title: {title}", file=sys.stderr)
        print(f"  Channel: {channel}", file=sys.stderr)
        print(f"  Duration: {duration}s", file=sys.stderr)

        # Step 2: Find and parse subtitles
        from mandarin.media_ingest import (
            parse_subtitles, extract_vocabulary,
            estimate_hsk_level, generate_quiz_questions,
        )

        segments = []
        subtitle_lang = None
        for lang in ["zh-Hans", "zh-Hant", "zh", "en"]:
            sub_path = os.path.join(tmpdir, f"{video_id}.{lang}.vtt")
            if os.path.exists(sub_path):
                segments = parse_subtitles(sub_path)
                subtitle_lang = lang
                print(f"  Subtitles: {lang} ({len(segments)} segments)", file=sys.stderr)
                break

        if not segments:
            print("  Warning: No Chinese subtitles found", file=sys.stderr)

        # Step 3: Extract vocabulary
        full_text = " ".join(s["text"] for s in segments)
        conn = None
        if args.db:
            import sqlite3
            conn = sqlite3.connect(args.db)
            conn.row_factory = sqlite3.Row

        vocab = extract_vocabulary(full_text, conn=conn)
        print(f"  Vocabulary: {len(vocab)} unique words extracted", file=sys.stderr)

        # Step 4: Estimate HSK level
        hsk_level = estimate_hsk_level(vocab)
        print(f"  Estimated HSK level: {hsk_level}", file=sys.stderr)

        # Step 5: Generate quiz questions
        questions = generate_quiz_questions(segments, vocab, max_questions=args.max_questions)
        print(f"  Quiz questions: {len(questions)} generated", file=sys.stderr)

        if conn:
            conn.close()

        # Step 6: Build catalog entry
        entry = {
            "media_id": video_id,
            "title": title,
            "channel": channel,
            "url": url,
            "duration_seconds": duration,
            "description": description,
            "hsk_level": hsk_level,
            "subtitle_lang": subtitle_lang,
            "vocab_count": len(vocab),
            "top_vocab": [v["word"] for v in vocab[:20]],
            "questions": questions,
            "tags": [],
            "status": "review",
        }

        return entry


if __name__ == "__main__":
    main()

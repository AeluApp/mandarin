#!/usr/bin/env python3
"""Batch pre-generate audio files using edge-tts.

Pre-generates neural TTS audio for HSK vocabulary, reading passages,
grammar examples, and dialogue scenarios so audio is instant during sessions.

Usage:
    python tools/generate_audio.py                    # All HSK items
    python tools/generate_audio.py --hsk 1-3          # HSK 1-3 only
    python tools/generate_audio.py --passages          # Reading passages
    python tools/generate_audio.py --grammar           # Grammar examples
    python tools/generate_audio.py --voice male        # Use male voice
    python tools/generate_audio.py --stats             # Show cache stats
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AUDIO_DIR = ROOT / "data" / "audio_cache"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

VOICES = {
    "female": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunxiNeural",
    "female_young": "zh-CN-XiaoyiNeural",
    "male_narrator": "zh-CN-YunjianNeural",
}

RATES = {
    "slow": "-20%",
    "normal": "+0%",
    "fast": "+20%",
}


def cache_key(text: str, rate: str, voice_key: str) -> str:
    """Same hash scheme as audio.py runtime."""
    # Convert rate string to WPM equivalent for cache compatibility
    rate_map = {"-20%": 90, "+0%": 120, "+20%": 150}
    wpm = rate_map.get(rate, 120)
    raw = f"{text}:{wpm}:{voice_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def already_cached(key: str) -> bool:
    return (AUDIO_DIR / f"{key}.mp3").exists()


async def generate_one(text: str, rate: str, voice_name: str, voice_key: str) -> bool:
    """Generate one audio file. Returns True if generated, False if skipped/failed."""
    import edge_tts

    key = cache_key(text, rate, voice_key)
    out_path = AUDIO_DIR / f"{key}.mp3"

    if out_path.exists() and out_path.stat().st_size > 0:
        return False  # Already cached

    try:
        comm = edge_tts.Communicate(text, voice_name, rate=rate)
        await comm.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:
        print(f"  ERROR: {text[:20]}... — {e}")
        return False


async def batch_generate(items: list, voice_key: str, rates: list, label: str):
    """Generate audio for a list of (text, context) tuples."""
    voice_name = VOICES.get(voice_key, VOICES["female"])
    total = len(items) * len(rates)
    generated = 0
    skipped = 0
    failed = 0
    start = time.time()

    print(f"\n  {label}: {len(items)} items x {len(rates)} rates = {total} files")
    print(f"  Voice: {voice_name} | Output: {AUDIO_DIR}")

    for i, (text, ctx) in enumerate(items):
        for rate in rates:
            key = cache_key(text, rate, voice_key)
            if already_cached(key):
                skipped += 1
                continue
            ok = await generate_one(text, rate, voice_name, voice_key)
            if ok:
                generated += 1
            else:
                failed += 1

        if (i + 1) % 100 == 0 or i == len(items) - 1:
            elapsed = time.time() - start
            pct = (i + 1) / len(items) * 100
            print(f"  [{pct:5.1f}%] {i+1}/{len(items)} — "
                  f"generated={generated} skipped={skipped} failed={failed} "
                  f"({elapsed:.0f}s)")

    elapsed = time.time() - start
    print(f"  Done: {generated} generated, {skipped} cached, {failed} failed ({elapsed:.0f}s)")


def load_hsk_items(levels: list) -> list:
    """Load HSK vocabulary items."""
    items = []
    for level in levels:
        path = ROOT / "data" / "hsk" / f"hsk{level}.json"
        if not path.exists():
            print(f"  Warning: {path} not found")
            continue
        with open(path) as f:
            data = json.load(f)
        for entry in data.get("items", []):
            hanzi = entry.get("hanzi", "").strip()
            if hanzi:
                items.append((hanzi, f"hsk{level}"))
    return items


def load_passages() -> list:
    """Load reading passage texts."""
    path = ROOT / "data" / "reading_passages.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    passages = data if isinstance(data, list) else data.get("passages", [])
    items = []
    for p in passages:
        text = p.get("text_zh", "").strip()
        pid = p.get("id", "unknown")
        if text:
            # Full passage
            items.append((text, f"passage:{pid}"))
            # Also individual sentences
            for sent in _split_sentences(text):
                if sent.strip():
                    items.append((sent.strip(), f"sentence:{pid}"))
    return items


def load_grammar_examples() -> list:
    """Load grammar point example sentences."""
    items = []
    # Import grammar seed modules
    try:
        from mandarin.grammar_seed import GRAMMAR_POINTS
        for gp in GRAMMAR_POINTS:
            for ex in gp.get("examples", []):
                zh = ex.get("zh", "").strip()
                if zh:
                    items.append((zh, f"grammar:{gp['name']}"))
    except ImportError:
        pass

    # Also try grammar extras
    import glob
    for path in sorted(glob.glob(str(ROOT / "mandarin" / "grammar_extra_*.py"))):
        module_name = Path(path).stem
        try:
            import importlib
            mod = importlib.import_module(f"mandarin.{module_name}")
            points = getattr(mod, "GRAMMAR_POINTS", [])
            for gp in points:
                for ex in gp.get("examples", []):
                    zh = ex.get("zh", "").strip()
                    if zh:
                        items.append((zh, f"grammar:{gp.get('name', module_name)}"))
        except Exception:
            pass
    return items


def _split_sentences(text: str) -> list:
    """Split Chinese text into sentences."""
    import re
    parts = re.split(r'([。！？])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        sent = parts[i] + parts[i + 1]
        if sent.strip():
            sentences.append(sent.strip())
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return sentences


def show_stats():
    """Show audio cache statistics."""
    mp3_files = list(AUDIO_DIR.glob("*.mp3"))
    wav_files = list(AUDIO_DIR.glob("*.wav"))
    total_size = sum(f.stat().st_size for f in mp3_files + wav_files)
    print(f"\n  Audio cache: {AUDIO_DIR}")
    print(f"  MP3 files: {len(mp3_files)}")
    print(f"  WAV files: {len(wav_files)}")
    print(f"  Total size: {total_size / 1024 / 1024:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="Pre-generate TTS audio files")
    parser.add_argument("--hsk", default="1-9", help="HSK levels (e.g., '1-3' or '1,2,3')")
    parser.add_argument("--passages", action="store_true", help="Generate for reading passages")
    parser.add_argument("--grammar", action="store_true", help="Generate for grammar examples")
    parser.add_argument("--all", action="store_true", help="Generate everything")
    parser.add_argument("--voice", default="female", choices=VOICES.keys())
    parser.add_argument("--rates", default="normal", help="Comma-separated rates: slow,normal,fast")
    parser.add_argument("--stats", action="store_true", help="Show cache stats and exit")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    rate_keys = [r.strip() for r in args.rates.split(",")]
    rates = [RATES[r] for r in rate_keys if r in RATES]
    if not rates:
        rates = [RATES["normal"]]

    # Parse HSK levels
    if "-" in args.hsk:
        start, end = args.hsk.split("-")
        levels = list(range(int(start), int(end) + 1))
    elif "," in args.hsk:
        levels = [int(x) for x in args.hsk.split(",")]
    else:
        levels = [int(args.hsk)]

    do_all = args.all or (not args.passages and not args.grammar)

    print(f"\n  Aelu Audio Generator")
    print(f"  Voice: {args.voice} ({VOICES[args.voice]})")
    print(f"  Rates: {rate_keys}")

    if do_all or not (args.passages or args.grammar):
        items = load_hsk_items(levels)
        if items:
            asyncio.run(batch_generate(items, args.voice, rates, f"HSK {args.hsk} vocabulary"))

    if args.passages or args.all:
        items = load_passages()
        if items:
            asyncio.run(batch_generate(items, args.voice, rates, "Reading passages"))

    if args.grammar or args.all:
        items = load_grammar_examples()
        if items:
            asyncio.run(batch_generate(items, args.voice, rates, "Grammar examples"))

    show_stats()


if __name__ == "__main__":
    main()

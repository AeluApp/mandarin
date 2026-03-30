"""Tests for content ingestion scripts.

Covers: Tatoeba TSV parsing, HSK level estimation, CEDICT download URL,
subtitle SRT parsing, Forvo filename matching, deduplication, dry-run mode.
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from tests.shared_db import make_test_db

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def content_db():
    """Create a minimal in-memory DB with content_item + dialogue_scenario tables."""
    conn = make_test_db()
    # Seed some HSK words for level estimation
    hsk_words = [
        ("你好", "nǐ hǎo", "hello", 1),
        ("谢谢", "xiè xiè", "thank you", 1),
        ("学生", "xué shēng", "student", 1),
        ("老师", "lǎo shī", "teacher", 1),
        ("中国", "zhōng guó", "China", 1),
        ("工作", "gōng zuò", "work", 2),
        ("公司", "gōng sī", "company", 2),
        ("环境", "huán jìng", "environment", 3),
        ("经济", "jīng jì", "economy", 4),
        ("政治", "zhèng zhì", "politics", 5),
    ]
    for hanzi, pinyin, english, hsk in hsk_words:
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?)",
            (hanzi, pinyin, english, hsk),
        )
    conn.commit()
    yield conn
    conn.close()


# ── 1. Tatoeba TSV parsing ──────────────────────────────────────────


class TestTatoebaParsing:
    def test_parse_sentences_tsv(self):
        from scripts.ingest_tatoeba import parse_sentences_tsv

        content = "1\tcmn\t你好世界\n2\teng\tHello world\n3\tcmn\t谢谢你\n"
        result = parse_sentences_tsv(content)

        assert 1 in result
        assert result[1] == ("cmn", "你好世界")
        assert result[2] == ("eng", "Hello world")
        assert len(result) == 3

    def test_parse_sentences_tsv_malformed(self):
        from scripts.ingest_tatoeba import parse_sentences_tsv

        content = "bad line\n\n1\tcmn\t你好\n"
        result = parse_sentences_tsv(content)
        # Should skip malformed lines gracefully
        assert 1 in result
        assert len(result) == 1

    def test_parse_links_tsv(self):
        from scripts.ingest_tatoeba import parse_links_tsv

        content = "1\t2\n3\t4\nbad\n"
        result = parse_links_tsv(content)
        assert (1, 2) in result
        assert (3, 4) in result
        assert len(result) == 2

    def test_find_chinese_english_pairs(self):
        from scripts.ingest_tatoeba import find_chinese_english_pairs

        sentences = {
            1: ("cmn", "你好"),
            2: ("eng", "Hello"),
            3: ("cmn", "谢谢"),
            4: ("fra", "Merci"),
            5: ("eng", "Thank you"),
        }
        links = [(1, 2), (3, 5), (3, 4)]

        pairs = find_chinese_english_pairs(sentences, links, limit=100)
        assert len(pairs) == 2
        assert pairs[0] == (1, "你好", "Hello")
        assert pairs[1] == (3, "谢谢", "Thank you")

    def test_find_pairs_respects_limit(self):
        from scripts.ingest_tatoeba import find_chinese_english_pairs

        sentences = {
            1: ("cmn", "你好"), 2: ("eng", "Hello"),
            3: ("cmn", "谢谢"), 4: ("eng", "Thanks"),
        }
        links = [(1, 2), (3, 4)]

        pairs = find_chinese_english_pairs(sentences, links, limit=1)
        assert len(pairs) == 1

    def test_is_good_sentence(self):
        from scripts.ingest_tatoeba import is_good_sentence

        assert is_good_sentence("你好世界") is True
        assert is_good_sentence("Hi") is False  # No Chinese
        assert is_good_sentence("好") is False  # Too short (< 3 Chinese chars)


# ── 2. HSK level estimation ─────────────────────────────────────────


class TestHSKEstimation:
    def test_estimate_hsk_basic(self, content_db):
        from scripts.ingest_tatoeba import estimate_hsk_level

        # Simple HSK 1 sentence
        level = estimate_hsk_level("你好老师", conn=content_db)
        assert 1 <= level <= 3  # Common words, low-to-mid HSK

    def test_estimate_hsk_no_jieba_returns_default(self):
        from scripts.ingest_tatoeba import estimate_hsk_level

        # Without jieba or HSK data, should return default
        with mock.patch.dict(sys.modules, {"jieba": None}):
            # Force reimport to hit the ImportError
            import scripts.ingest_tatoeba as mod
            old_words = mod._HSK_WORDS
            old_loaded = mod._HSK_LOADED
            mod._HSK_WORDS = {}
            mod._HSK_LOADED = False
            try:
                level = mod.estimate_hsk_level("anything")
                assert level == 3  # Default fallback
            finally:
                mod._HSK_WORDS = old_words
                mod._HSK_LOADED = old_loaded

    def test_estimate_hsk_empty_text(self, content_db):
        from scripts.ingest_tatoeba import estimate_hsk_level

        level = estimate_hsk_level("", conn=content_db)
        assert 1 <= level <= 9


# ── 3. CEDICT download URL construction ─────────────────────────────


class TestCEDICT:
    def test_cedict_url_constant(self):
        from scripts.ingest_cedict import CEDICT_URL

        assert "mdbg.net" in CEDICT_URL
        assert CEDICT_URL.endswith(".gz")

    def test_cedict_uses_existing_parser(self):
        """Verify ingest_cedict imports from mandarin.dictionary."""
        from scripts.ingest_cedict import main
        from mandarin.dictionary import parse_cedict_line

        # The existing parser should still work
        result = parse_cedict_line("傳統 传统 [chuan2 tong3] /tradition/traditional/")
        assert result is not None
        assert result["simplified"] == "传统"
        assert result["traditional"] == "傳統"


# ── 4. Subtitle SRT parsing ─────────────────────────────────────────


class TestSubtitleParsing:
    def test_parse_srt_file(self, tmp_path):
        from scripts.ingest_open_subtitles import parse_subtitle_file

        srt_content = """1
00:00:01,000 --> 00:00:03,000
你好，欢迎来到这里。

2
00:00:04,000 --> 00:00:06,500
谢谢你的邀请。

3
00:00:08,000 --> 00:00:10,000
我们开始吧。
"""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(srt_content, encoding="utf-8")

        segments = parse_subtitle_file(srt_file)
        assert len(segments) == 3
        assert segments[0]["start_s"] == 1.0
        assert segments[0]["end_s"] == 3.0
        assert "你好" in segments[0]["text"]
        assert segments[1]["start_s"] == 4.0

    def test_parse_vtt_file(self, tmp_path):
        from scripts.ingest_open_subtitles import parse_subtitle_file

        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:03.000
你好世界

00:00:05.000 --> 00:00:07.000
再见朋友
"""
        vtt_file = tmp_path / "test.vtt"
        vtt_file.write_text(vtt_content, encoding="utf-8")

        segments = parse_subtitle_file(vtt_file)
        assert len(segments) == 2
        assert segments[0]["text"] == "你好世界"

    def test_parse_timestamp(self):
        from scripts.ingest_open_subtitles import parse_timestamp

        assert parse_timestamp("00:01:23,456") == pytest.approx(83.456, abs=0.001)
        assert parse_timestamp("00:01:23.456") == pytest.approx(83.456, abs=0.001)
        assert parse_timestamp("01:30:00.000") == pytest.approx(5400.0, abs=0.001)
        assert parse_timestamp("bad") is None

    def test_group_into_dialogue_turns(self):
        from scripts.ingest_open_subtitles import group_into_dialogue_turns

        segments = [
            {"start_s": 1.0, "end_s": 3.0, "text": "你好"},
            {"start_s": 3.5, "end_s": 5.0, "text": "你好啊"},
            {"start_s": 20.0, "end_s": 22.0, "text": "再见"},
            {"start_s": 22.5, "end_s": 24.0, "text": "再见朋友"},
        ]

        groups = group_into_dialogue_turns(segments, max_gap_s=3.0)
        assert len(groups) == 2
        assert len(groups[0]) == 2  # First two close together
        assert len(groups[1]) == 2  # Last two close together


# ── 5. Forvo filename matching ───────────────────────────────────────


class TestForvoMatching:
    def test_extract_hanzi_simple(self):
        from scripts.ingest_forvo import extract_hanzi_from_filename

        assert extract_hanzi_from_filename("你好.mp3") == "你好"
        assert extract_hanzi_from_filename("谢谢.wav") == "谢谢"

    def test_extract_hanzi_with_prefix(self):
        from scripts.ingest_forvo import extract_hanzi_from_filename

        assert extract_hanzi_from_filename("pronunciation_zh_你好.mp3") == "你好"
        assert extract_hanzi_from_filename("zh_谢谢_12345.mp3") == "谢谢"
        assert extract_hanzi_from_filename("cmn_老师.ogg") == "老师"

    def test_validate_audio_file(self, tmp_path):
        from scripts.ingest_forvo import validate_audio_file

        # Valid
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"\x00" * 100)
        assert validate_audio_file(mp3) is True

        # Empty file
        empty = tmp_path / "empty.mp3"
        empty.write_bytes(b"")
        assert validate_audio_file(empty) is False

        # Wrong extension
        txt = tmp_path / "test.txt"
        txt.write_text("not audio")
        assert validate_audio_file(txt) is False

    def test_match_and_update(self, content_db, tmp_path):
        from scripts.ingest_forvo import match_and_update

        # Create a fake audio file
        audio = tmp_path / "你好.mp3"
        audio.write_bytes(b"\xff" * 100)

        audio_files = [(audio, "你好")]

        # Patch PROJECT_ROOT for relative path calculation
        with mock.patch("scripts.ingest_forvo.PROJECT_ROOT", tmp_path):
            counts = match_and_update(content_db, audio_files, dry_run=False)

        assert counts["matched"] == 1
        assert counts["updated"] == 1
        assert counts["unmatched"] == 0

        # Verify DB was updated
        row = content_db.execute(
            "SELECT audio_available, audio_file_path FROM content_item WHERE hanzi = '你好'"
        ).fetchone()
        assert row["audio_available"] == 1
        assert row["audio_file_path"] is not None


# ── 6. Deduplication logic ───────────────────────────────────────────


class TestDeduplication:
    def test_tatoeba_dedup_skips_existing(self, content_db):
        from scripts.ingest_tatoeba import ingest_pairs

        # Insert a sentence that already exists
        content_db.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, source) VALUES ('你好世界', '', 'Hello world', 'tatoeba')"
        )
        content_db.commit()

        pairs = [(999, "你好世界", "Hello world")]
        counts = ingest_pairs(content_db, pairs, dry_run=False)

        assert counts["skipped_dup"] == 1
        assert counts["inserted"] == 0

    def test_tatoeba_dedup_broader_source_check(self, content_db):
        """Even if source differs, same hanzi is skipped."""
        from scripts.ingest_tatoeba import ingest_pairs

        # Insert a sentence from a non-tatoeba source
        content_db.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, source) VALUES ('今天天气很好啊', '', 'Nice weather', 'seed')"
        )
        content_db.commit()

        pairs = [(888, "今天天气很好啊", "Nice weather today")]
        counts = ingest_pairs(content_db, pairs, dry_run=False)

        assert counts["skipped_dup"] == 1

    def test_subtitle_dedup(self, content_db, tmp_path):
        from scripts.ingest_open_subtitles import ingest_subtitle_file

        srt_content = """1
00:00:01,000 --> 00:00:03,000
你好欢迎来到这里

2
00:00:03,500 --> 00:00:05,000
谢谢你的邀请朋友
"""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(srt_content, encoding="utf-8")

        # First ingest
        counts1 = ingest_subtitle_file(content_db, srt_file, "Movie", dry_run=False)
        # Second ingest of same file
        counts2 = ingest_subtitle_file(content_db, srt_file, "Movie", dry_run=False)

        assert counts2["skipped_dup"] >= counts1["inserted"]


# ── 7. Dry-run mode ─────────────────────────────────────────────────


class TestDryRun:
    def test_tatoeba_dry_run_no_insert(self, content_db):
        from scripts.ingest_tatoeba import ingest_pairs

        pairs = [(100, "这是一个新句子测试", "This is a test sentence")]
        counts = ingest_pairs(content_db, pairs, dry_run=True)

        assert counts["inserted"] == 1  # Counted but not written

        # Verify nothing was actually written
        row = content_db.execute(
            "SELECT COUNT(*) FROM content_item WHERE source = 'tatoeba'"
        ).fetchone()
        assert row[0] == 0

    def test_forvo_dry_run_no_update(self, content_db, tmp_path):
        from scripts.ingest_forvo import match_and_update

        audio = tmp_path / "你好.mp3"
        audio.write_bytes(b"\xff" * 100)
        audio_files = [(audio, "你好")]

        with mock.patch("scripts.ingest_forvo.PROJECT_ROOT", tmp_path):
            counts = match_and_update(content_db, audio_files, dry_run=True)

        assert counts["updated"] == 1  # Counted

        # But DB should not be changed
        row = content_db.execute(
            "SELECT audio_available FROM content_item WHERE hanzi = '你好'"
        ).fetchone()
        assert row["audio_available"] == 0


# ── 8. Wikimedia URL construction ────────────────────────────────────


class TestWikimediaURL:
    def test_build_commons_url(self):
        from scripts.ingest_wikimedia_audio import build_commons_url

        url = build_commons_url("zh-你好.ogg")
        assert "upload.wikimedia.org" in url
        assert "wikipedia/commons" in url
        # URL should have the MD5-based directory structure
        parts = url.split("/")
        assert len(parts) > 5

    def test_filename_patterns(self):
        from scripts.ingest_wikimedia_audio import FILENAME_PATTERNS

        # Should have sensible patterns
        assert any("{hanzi}" in p for p in FILENAME_PATTERNS)
        assert any(p.startswith("zh-") for p in FILENAME_PATTERNS)


# ── 9. Content sources manifest ──────────────────────────────────────


class TestContentSources:
    def test_sources_have_required_fields(self):
        from scripts.content_sources import SOURCES

        required = {"name", "url", "license", "content_type", "estimated_items",
                     "ingestion_command", "source_key"}
        for src in SOURCES:
            missing = required - set(src.keys())
            assert not missing, f"{src['name']} missing fields: {missing}"

    def test_sources_unique_keys(self):
        from scripts.content_sources import SOURCES

        keys = [s["source_key"] for s in SOURCES]
        assert len(keys) == len(set(keys)), "Duplicate source_keys found"

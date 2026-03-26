"""Tests for content quality analyzer — all DB via in-memory SQLite, LLM mocked."""

import pytest
pytest.importorskip("httpx")

import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from mandarin.ai.content_quality import (
    _score_to_grade,
    _make_finding,
    _tokenize_chinese,
    _get_stabilized_vocab,
    assess_passage_quality,
    assess_grammar_quality,
    assess_question_quality,
    assess_pronunciation_quality,
    assess_dialogue_quality,
    assess_listening_quality,
    assess_media_shelf_health,
    ContentQualityAnalyzer,
    generate_corpus_audit_report,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    """In-memory SQLite with tables needed by content_quality."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.executescript("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            item_type TEXT DEFAULT 'vocab',
            hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            review_status TEXT DEFAULT 'approved',
            content_lens TEXT,
            audio_available INTEGER DEFAULT 0,
            audio_file_path TEXT,
            difficulty REAL DEFAULT 0.5,
            is_mined_out INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]'
        );

        CREATE TABLE progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            content_item_id INTEGER NOT NULL,
            modality TEXT NOT NULL,
            mastery_stage TEXT DEFAULT 'seen',
            total_attempts INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        );

        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_zh TEXT,
            hsk_level INTEGER DEFAULT 1,
            category TEXT DEFAULT 'structure',
            description TEXT,
            examples_json TEXT DEFAULT '[]',
            difficulty REAL DEFAULT 0.5
        );

        CREATE TABLE content_grammar (
            content_item_id INTEGER NOT NULL,
            grammar_point_id INTEGER NOT NULL,
            PRIMARY KEY (content_item_id, grammar_point_id)
        );

        CREATE TABLE grammar_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            grammar_point_id INTEGER NOT NULL,
            drill_attempts INTEGER DEFAULT 0,
            drill_correct INTEGER DEFAULT 0,
            mastery_score REAL DEFAULT 0.0
        );

        CREATE TABLE dialogue_scenario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            title_zh TEXT,
            hsk_level INTEGER DEFAULT 1,
            register TEXT DEFAULT 'neutral',
            scenario_type TEXT DEFAULT 'dialogue',
            tree_json TEXT NOT NULL,
            difficulty REAL DEFAULT 0.5,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE audio_recording (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            content_item_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            overall_score REAL,
            tone_scores_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE listening_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            passage_id TEXT NOT NULL,
            comprehension_score REAL DEFAULT 0.0,
            questions_correct INTEGER DEFAULT 0,
            questions_total INTEGER DEFAULT 0,
            words_looked_up INTEGER DEFAULT 0,
            hsk_level INTEGER DEFAULT 1,
            completed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE reading_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            passage_id TEXT NOT NULL,
            words_looked_up INTEGER DEFAULT 0,
            questions_correct INTEGER DEFAULT 0,
            questions_total INTEGER DEFAULT 0,
            completed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE vocab_encounter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            content_item_id INTEGER,
            hanzi TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            looked_up INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE media_watch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            media_id TEXT NOT NULL,
            title TEXT NOT NULL,
            hsk_level INTEGER DEFAULT 1,
            media_type TEXT NOT NULL,
            times_presented INTEGER DEFAULT 0,
            times_watched INTEGER DEFAULT 0,
            last_watched_at TEXT,
            status TEXT DEFAULT 'available'
        );

        CREATE TABLE learner_profile (
            id INTEGER PRIMARY KEY,
            user_id INTEGER DEFAULT 1,
            level_reading REAL DEFAULT 1.0,
            level_listening REAL DEFAULT 1.0,
            level_speaking REAL DEFAULT 1.0
        );

        CREATE TABLE pi_ai_generation_cache (
            id TEXT PRIMARY KEY,
            prompt_hash TEXT NOT NULL UNIQUE,
            prompt_text TEXT,
            system_text TEXT,
            model_used TEXT,
            response_text TEXT,
            generated_at TEXT,
            hit_count INTEGER DEFAULT 0,
            last_hit_at TEXT
        );

        CREATE TABLE pi_ai_generation_log (
            id TEXT PRIMARY KEY,
            occurred_at TEXT,
            task_type TEXT NOT NULL,
            model_used TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            generation_time_ms INTEGER,
            from_cache INTEGER DEFAULT 0,
            success INTEGER DEFAULT 1,
            error TEXT,
            finding_id TEXT,
            item_id TEXT
        );
    """)
    c.execute("INSERT INTO learner_profile (id, user_id) VALUES (1, 1)")
    c.commit()
    return c


def _seed_content(conn, count=10, hsk_level=1, item_type="vocab"):
    """Insert N content items for testing."""
    for i in range(count):
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, item_type, hsk_level) VALUES (?, ?, ?, ?, ?)",
            (f"字{i}", f"zi{i}", f"char{i}", item_type, hsk_level),
        )
    conn.commit()


# ── Test 1: _score_to_grade mapping ──────────────────────────────────────

def test_score_to_grade_A():
    assert _score_to_grade(95) == "A"
    assert _score_to_grade(90) == "A"


def test_score_to_grade_B():
    assert _score_to_grade(85) == "B"
    assert _score_to_grade(80) == "B"


def test_score_to_grade_F():
    assert _score_to_grade(50) == "F"
    assert _score_to_grade(0) == "F"


def test_score_to_grade_boundaries():
    assert _score_to_grade(70) == "C"
    assert _score_to_grade(60) == "D"
    assert _score_to_grade(59) == "F"


# ── Test 2: _make_finding format ─────────────────────────────────────────

def test_make_finding_returns_complete_dict():
    f = _make_finding("test_dim", "Test Title", "warning", "Detail here", "Fix it")
    assert f["dimension"] == "test_dim"
    assert f["title"] == "Test Title"
    assert f["severity"] == "warning"
    assert f["detail"] == "Detail here"
    assert f["recommendation"] == "Fix it"


# ── Test 3: _tokenize_chinese ────────────────────────────────────────────

def test_tokenize_chinese_char_fallback():
    """Without jieba, should fall back to character-level tokenization."""
    tokens = _tokenize_chinese("你好世界")
    # Should produce individual characters (may use jieba if available)
    assert len(tokens) >= 2
    assert all(isinstance(t, str) for t in tokens)


def test_tokenize_chinese_empty():
    tokens = _tokenize_chinese("")
    assert tokens == []


# ── Test 4: _get_stabilized_vocab ────────────────────────────────────────

def test_get_stabilized_vocab_returns_set(conn):
    _seed_content(conn, 3)
    # Mark first item as familiar
    conn.execute(
        "INSERT INTO progress (content_item_id, modality, mastery_stage) VALUES (1, 'reading', 'familiar')",
    )
    conn.commit()

    result = _get_stabilized_vocab(conn)
    assert isinstance(result, set)
    assert len(result) >= 1


def test_get_stabilized_vocab_empty_db(conn):
    result = _get_stabilized_vocab(conn)
    assert result == set()


# ── Test 5: assess_grammar_quality ───────────────────────────────────────

def test_assess_grammar_quality_complete(conn):
    conn.execute(
        "INSERT INTO grammar_point (name, name_zh, description, examples_json, category, hsk_level) "
        "VALUES ('ba_construction', '把字句', 'Disposal construction', "
        "'[{\"hanzi\": \"我把书放在桌子上\"}]', 'structure', 2)",
    )
    conn.commit()

    result = assess_grammar_quality(conn, 1)
    assert result["overall_score"] > 0
    assert result["grade"] in ("A", "B", "C", "D", "F")
    assert "completeness" in result["dimension_scores"]
    assert "example_quality" in result["dimension_scores"]


def test_assess_grammar_quality_missing(conn):
    result = assess_grammar_quality(conn, 999)
    assert result["overall_score"] == 0
    assert result["grade"] == "F"
    assert "error" in result


def test_assess_grammar_quality_minimal(conn):
    """Grammar point with only name should score lower."""
    conn.execute(
        "INSERT INTO grammar_point (name, hsk_level) VALUES ('test_point', 1)",
    )
    conn.commit()

    result = assess_grammar_quality(conn, 1)
    assert result["overall_score"] < 80
    assert result["dimension_scores"]["completeness"] < 80


# ── Test 6: assess_question_quality ──────────────────────────────────────

def test_assess_question_quality_recall():
    q = {
        "question": "什么时候去北京？",
        "answer": "明天",
        "passage_body": "我明天去北京旅游。",
    }
    result = assess_question_quality(None, q)
    assert result["overall_score"] > 0
    assert result["dimension_scores"]["cognitive_level"] <= 60  # recall-level


def test_assess_question_quality_inference():
    q = {
        "question": "Why does the author suggest walking?",
        "answer": "Because it's healthy",
        "passage_body": "Walking is good for your health.",
    }
    result = assess_question_quality(None, q)
    # "why" is a synthesis marker
    assert result["dimension_scores"]["cognitive_level"] >= 80


def test_assess_question_quality_with_distractors():
    q = {
        "question": "什么是对的？",
        "answer": "A",
        "distractors": ["B", "C", "D"],
    }
    result = assess_question_quality(None, q)
    assert result["dimension_scores"]["distractor_quality"] > 50


def test_assess_question_quality_duplicate_distractors():
    q = {
        "question": "什么是对的？",
        "answer": "A",
        "distractors": ["B", "B", "C"],
    }
    result = assess_question_quality(None, q)
    # Duplicate penalty should lower score
    assert result["dimension_scores"]["distractor_quality"] < 90


# ── Test 7: assess_pronunciation_quality ─────────────────────────────────

def test_assess_pronunciation_quality_basic(conn):
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english) VALUES ('你好', 'nǐ hǎo', 'hello')",
    )
    conn.commit()

    result = assess_pronunciation_quality(conn, 1)
    assert result["overall_score"] > 0
    assert "tonal_accuracy" in result["dimension_scores"]
    assert "sandhi_marking" in result["dimension_scores"]


def test_assess_pronunciation_quality_with_recordings(conn):
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english) VALUES ('你好', 'nǐ hǎo', 'hello')",
    )
    conn.execute(
        "INSERT INTO audio_recording (content_item_id, file_path, overall_score) VALUES (1, '/tmp/test.wav', 0.85)",
    )
    conn.commit()

    result = assess_pronunciation_quality(conn, 1)
    assert result["dimension_scores"]["tonal_accuracy"] > 50


def test_assess_pronunciation_quality_missing(conn):
    result = assess_pronunciation_quality(conn, 999)
    assert result["overall_score"] == 0
    assert "error" in result


# ── Test 8: assess_dialogue_quality ──────────────────────────────────────

def test_assess_dialogue_quality_basic(conn):
    tree = {
        "turns": [
            {"text": "你好，请问这个怎么卖？", "speaker": "customer"},
            {"text": "这个二十块钱。", "speaker": "seller"},
            {"text": "太贵了吧，便宜一点行不行？", "speaker": "customer"},
        ]
    }
    conn.execute(
        "INSERT INTO dialogue_scenario (title, title_zh, tree_json, register, hsk_level) "
        "VALUES ('Shopping', '买东西', ?, 'casual', 2)",
        (json.dumps(tree, ensure_ascii=False),),
    )
    conn.commit()

    with patch("mandarin.ai.content_quality._assess_authenticity_llm") as mock_auth:
        mock_auth.return_value = {"score": 80, "issues": []}
        result = assess_dialogue_quality(conn, 1)

    assert result["overall_score"] > 0
    assert "turn_asymmetry" in result["dimension_scores"]
    assert "modal_particles" in result["dimension_scores"]


def test_assess_dialogue_quality_missing(conn):
    result = assess_dialogue_quality(conn, 999)
    assert result["overall_score"] == 0
    assert "error" in result


# ── Test 9: assess_listening_quality ─────────────────────────────────────

def test_assess_listening_quality_no_data(conn):
    result = assess_listening_quality(conn, "passage_1")
    assert result["overall_score"] > 0
    assert result["dimension_scores"]["consumption_rate"] < 50


def test_assess_listening_quality_with_progress(conn):
    conn.execute(
        "INSERT INTO listening_progress (passage_id, questions_correct, questions_total, hsk_level) "
        "VALUES ('p1', 3, 4, 2)",
    )
    conn.commit()

    result = assess_listening_quality(conn, "p1")
    assert result["dimension_scores"]["consumption_rate"] > 50
    assert result["dimension_scores"]["comprehension"] > 50


# ── Test 10: assess_media_shelf_health ───────────────────────────────────

def test_assess_media_shelf_health_empty(conn):
    result = assess_media_shelf_health(conn)
    assert result["overall_score"] <= 30
    assert result["grade"] == "F"


def test_assess_media_shelf_health_with_data(conn):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO media_watch (media_id, title, media_type, hsk_level, times_watched, last_watched_at) "
        "VALUES ('m1', 'Test Video', 'video', 2, 3, ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO media_watch (media_id, title, media_type, hsk_level, times_watched, last_watched_at) "
        "VALUES ('m2', 'Test Podcast', 'podcast', 2, 1, ?)",
        (now,),
    )
    conn.commit()

    result = assess_media_shelf_health(conn)
    assert result["overall_score"] > 30
    assert result["dimension_scores"]["consumption_rate"] > 50
    assert result["dimension_scores"]["media_type_diversity"] > 50


# ── Test 11: ContentQualityAnalyzer empty DB ─────────────────────────────

def test_analyzer_empty_db(conn):
    analyzer = ContentQualityAnalyzer()
    findings = analyzer.run(conn)
    assert isinstance(findings, list)
    # Should find "Empty corpus" or similar
    assert any(f["severity"] == "critical" for f in findings)


# ── Test 12: ContentQualityAnalyzer with content ─────────────────────────

def test_analyzer_with_content(conn):
    _seed_content(conn, 30, hsk_level=1)
    _seed_content(conn, 20, hsk_level=2)
    analyzer = ContentQualityAnalyzer()
    findings = analyzer.run(conn)
    assert isinstance(findings, list)


# ── Test 13: Corpus composition detects HSK gaps ─────────────────────────

def test_corpus_composition_finds_hsk_gaps(conn):
    # Only HSK 1 content
    _seed_content(conn, 50, hsk_level=1)
    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_corpus_composition(conn)
    # Should flag missing HSK 2-6
    gap_findings = [f for f in findings if "HSK" in f["title"]]
    assert len(gap_findings) > 0


# ── Test 14: Content type coverage ───────────────────────────────────────

def test_content_type_coverage_vocab_heavy(conn):
    _seed_content(conn, 100, item_type="vocab")
    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_content_type_coverage(conn)
    # Should flag vocab-heavy and missing sentence/phrase
    assert any("sentence" in f.get("detail", "").lower() or "vocab" in f.get("title", "").lower()
               for f in findings)


# ── Test 15: Acquisition pipeline ────────────────────────────────────────

def test_acquisition_pipeline_no_encounters(conn):
    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_acquisition_pipeline(conn)
    assert any("encounter" in f["title"].lower() for f in findings)


def test_acquisition_pipeline_with_encounters(conn):
    conn.execute(
        "INSERT INTO vocab_encounter (hanzi, source_type) VALUES ('你', 'reading')",
    )
    conn.execute(
        "INSERT INTO vocab_encounter (hanzi, source_type) VALUES ('好', 'listening')",
    )
    conn.commit()

    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_acquisition_pipeline(conn)
    # Should note missing media source
    assert any("media" in f.get("detail", "").lower() for f in findings)


# ── Test 16: Voice health ────────────────────────────────────────────────

def test_voice_health_no_recordings(conn):
    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_voice_health(conn)
    # No recordings = no findings (nothing broken)
    assert isinstance(findings, list)


def test_voice_health_broken_audio_refs(conn):
    conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english, audio_available) VALUES ('你', 'nǐ', 'you', 1)",
    )
    conn.commit()

    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_voice_health(conn)
    assert any("audio" in f["title"].lower() for f in findings)


# ── Test 17: Productive vocabulary gap ───────────────────────────────────

def test_productive_gap_reading_only(conn):
    _seed_content(conn, 5)
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO progress (content_item_id, modality, mastery_stage) VALUES (?, 'reading', 'familiar')",
            (i,),
        )
    conn.commit()

    analyzer = ContentQualityAnalyzer()
    findings = analyzer._analyze_productive_vocabulary_gap(conn)
    assert any("production" in f["title"].lower() for f in findings)


# ── Test 18: generate_corpus_audit_report ────────────────────────────────

def test_corpus_audit_report_structure(conn):
    _seed_content(conn, 20)
    report = generate_corpus_audit_report(conn)
    assert "generated_at" in report
    assert "corpus_size" in report
    assert "hsk_distribution" in report
    assert "health_grade" in report
    assert "findings" in report
    assert isinstance(report["findings"], list)


def test_corpus_audit_report_empty_db(conn):
    report = generate_corpus_audit_report(conn)
    assert report["corpus_size"] == 0
    assert report["health_grade"] in ("D", "F")


# ── Test 19: assess_passage_quality with mocked LLM ─────────────────────

@patch("mandarin.ai.content_quality._assess_authenticity_llm")
def test_assess_passage_quality_not_found(mock_auth, conn):
    mock_auth.return_value = {"score": 60, "issues": []}
    result = assess_passage_quality(conn, "nonexistent_passage")
    assert result["overall_score"] == 0
    assert "error" in result


# ── Test 20: Dialogue with modal particles scores higher ─────────────────

def test_dialogue_modal_particles(conn):
    # Dialogue with particles
    tree_with = {
        "turns": [
            {"text": "你吃饭了吗？"},
            {"text": "吃了啊，你呢？"},
        ]
    }
    conn.execute(
        "INSERT INTO dialogue_scenario (title, tree_json) VALUES ('With particles', ?)",
        (json.dumps(tree_with, ensure_ascii=False),),
    )

    # Dialogue without particles
    tree_without = {
        "turns": [
            {"text": "你吃饭"},
            {"text": "我吃饭"},
        ]
    }
    conn.execute(
        "INSERT INTO dialogue_scenario (title, tree_json) VALUES ('Without particles', ?)",
        (json.dumps(tree_without, ensure_ascii=False),),
    )
    conn.commit()

    with patch("mandarin.ai.content_quality._assess_authenticity_llm") as mock_auth:
        mock_auth.return_value = {"score": 70, "issues": []}
        with_particles = assess_dialogue_quality(conn, 1)
        without_particles = assess_dialogue_quality(conn, 2)

    assert with_particles["dimension_scores"]["modal_particles"] > without_particles["dimension_scores"]["modal_particles"]


# ── Test 21: Grammar with content integration scores higher ──────────────

def test_grammar_content_integration(conn):
    _seed_content(conn, 5)
    conn.execute(
        "INSERT INTO grammar_point (name, description, examples_json) VALUES ('test', 'desc', '[]')",
    )
    # Link grammar to multiple content items
    for i in range(1, 4):
        conn.execute(
            "INSERT INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, 1)",
            (i,),
        )
    conn.commit()

    result = assess_grammar_quality(conn, 1)
    assert result["dimension_scores"]["content_integration"] > 50


# ── Test 22: Question with answer in distractors penalized ───────────────

def test_question_answer_in_distractors():
    q = {
        "question": "什么颜色？",
        "answer": "红色",
        "distractors": ["红色", "蓝色", "绿色"],
    }
    result = assess_question_quality(None, q)
    assert result["dimension_scores"]["distractor_quality"] < 60


# ── Test 23: Media shelf diversity scoring ───────────────────────────────

def test_media_shelf_diversity(conn):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for media_type in ("video", "podcast", "song"):
        conn.execute(
            "INSERT INTO media_watch (media_id, title, media_type, hsk_level, times_watched, last_watched_at) "
            "VALUES (?, ?, ?, 2, 1, ?)",
            (f"m_{media_type}", f"Test {media_type}", media_type, now),
        )
    conn.commit()

    result = assess_media_shelf_health(conn)
    assert result["dimension_scores"]["media_type_diversity"] >= 90


# ── Test 24: Listening encounters extraction ─────────────────────────────

def test_listening_encounter_extraction(conn):
    conn.execute(
        "INSERT INTO listening_progress (passage_id, questions_correct, questions_total, hsk_level) "
        "VALUES ('lp1', 2, 3, 1)",
    )
    conn.execute(
        "INSERT INTO vocab_encounter (hanzi, source_type, source_id) VALUES ('听', 'listening', 'lp1')",
    )
    conn.execute(
        "INSERT INTO vocab_encounter (hanzi, source_type, source_id) VALUES ('说', 'listening', 'lp1')",
    )
    conn.commit()

    result = assess_listening_quality(conn, "lp1")
    assert result["dimension_scores"]["encounter_extraction"] > 30


# ── Test 25: Analyzer returns consistent severity levels ─────────────────

def test_analyzer_severity_levels(conn):
    analyzer = ContentQualityAnalyzer()
    findings = analyzer.run(conn)
    valid_severities = {"critical", "warning", "info"}
    for f in findings:
        assert f["severity"] in valid_severities, f"Invalid severity: {f['severity']}"

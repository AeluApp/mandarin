"""Tests for mandarin.ai.content_quality — quality analysis functions.

Covers:
- _score_to_grade helper
- _make_finding helper
- _tokenize_chinese fallback
- _safe_query / _safe_query_one helpers
- assess_question_quality
- assess_grammar_quality (via mocked DB)
- assess_passage_quality (via mocked DB)
- assess_listening_quality
- assess_media_shelf_health
- assess_dialogue_quality
- ContentQualityAnalyzer.run()
- generate_corpus_audit_report()
"""

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from tests.shared_db import make_test_db


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    """In-memory DB with tables needed by content_quality."""
    conn = make_test_db()
    yield conn
    conn.close()


# ── Helper tests ─────────────────────────────────────────────────────

class TestScoreToGrade:
    def test_grade_a(self):
        from mandarin.ai.content_quality import _score_to_grade
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(90) == "A"

    def test_grade_b(self):
        from mandarin.ai.content_quality import _score_to_grade
        assert _score_to_grade(85) == "B"
        assert _score_to_grade(80) == "B"

    def test_grade_c(self):
        from mandarin.ai.content_quality import _score_to_grade
        assert _score_to_grade(75) == "C"
        assert _score_to_grade(70) == "C"

    def test_grade_d(self):
        from mandarin.ai.content_quality import _score_to_grade
        assert _score_to_grade(65) == "D"
        assert _score_to_grade(60) == "D"

    def test_grade_f(self):
        from mandarin.ai.content_quality import _score_to_grade
        assert _score_to_grade(55) == "F"
        assert _score_to_grade(0) == "F"


class TestMakeFinding:
    def test_basic(self):
        from mandarin.ai.content_quality import _make_finding
        f = _make_finding("corpus", "Gap found", "critical", "detail", "fix it")
        assert f["dimension"] == "corpus"
        assert f["title"] == "Gap found"
        assert f["severity"] == "critical"
        assert f["detail"] == "detail"
        assert f["recommendation"] == "fix it"


class TestTokenizeChinese:
    def test_char_fallback(self):
        from mandarin.ai.content_quality import _tokenize_chinese
        # Without jieba, should fall back to character-level
        with patch.dict("sys.modules", {"jieba": None}):
            tokens = _tokenize_chinese("你好世界")
            assert len(tokens) == 4
            assert "你" in tokens

    def test_empty_string(self):
        from mandarin.ai.content_quality import _tokenize_chinese
        tokens = _tokenize_chinese("")
        assert tokens == []

    def test_non_chinese(self):
        from mandarin.ai.content_quality import _tokenize_chinese
        tokens = _tokenize_chinese("hello world")
        # Non-CJK characters are filtered out in char fallback
        # (if jieba is not available)
        assert isinstance(tokens, list)


class TestSafeQuery:
    def test_returns_rows(self, mem_db):
        from mandarin.ai.content_quality import _safe_query
        result = _safe_query(mem_db, "SELECT COUNT(*) as cnt FROM user")
        assert result is not None
        # _safe_query returns a list of rows; first row, first column
        assert len(result) > 0

    def test_returns_empty_on_error(self, mem_db):
        from mandarin.ai.content_quality import _safe_query
        result = _safe_query(mem_db, "SELECT * FROM nonexistent_table")
        assert result == []

    def test_safe_query_one(self, mem_db):
        from mandarin.ai.content_quality import _safe_query_one
        result = _safe_query_one(mem_db, "SELECT COUNT(*) FROM user")
        assert result is not None
        assert result[0] == 1

    def test_safe_query_one_error(self, mem_db):
        from mandarin.ai.content_quality import _safe_query_one
        result = _safe_query_one(mem_db, "SELECT * FROM nonexistent_table")
        assert result is None


# ── Assessment tests ──────────────────────────────────────────────────

class TestAssessQuestionQuality:
    def test_basic_question(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "什么是他的名字？",
            "answer": "张三",
            "distractors": ["李四", "王五", "赵六"],
            "passage_body": "他的名字是张三，来自北京。",
        })
        assert "overall_score" in result
        assert "grade" in result
        assert "dimension_scores" in result
        assert 0 <= result["overall_score"] <= 100

    def test_synthesis_question(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "为什么这个故事很重要？请分析原因。",
            "answer": "因为...",
            "distractors": [],
            "passage_body": "这是一个关于文化传统的故事。",
        })
        assert result["dimension_scores"]["cognitive_level"] == 100

    def test_inference_question(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "这段话暗示了什么？",
            "answer": "暗示...",
            "distractors": [],
        })
        assert result["dimension_scores"]["cognitive_level"] == 80

    def test_recall_question(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "谁写了这个故事？",
            "answer": "作者",
            "distractors": ["A", "B"],
        })
        assert result["dimension_scores"]["cognitive_level"] == 40

    def test_empty_question(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {})
        assert result["overall_score"] >= 0
        assert result["grade"] in ("A", "B", "C", "D", "F")

    def test_duplicate_distractors(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "什么？",
            "answer": "A",
            "distractors": ["B", "B", "C"],
        })
        # Should detect duplicate and penalize
        assert result["dimension_scores"]["distractor_quality"] < 100

    def test_answer_in_distractors(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "什么？",
            "answer": "A",
            "distractors": ["A", "B", "C"],
        })
        # Answer among distractors should penalize
        assert result["dimension_scores"]["distractor_quality"] < 80

    def test_empirical_data_ideal(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "什么？",
            "answer": "A",
            "distractors": ["B"],
            "empirical_correct_rate": 0.70,
        })
        assert result["dimension_scores"]["empirical_difficulty"] == 95

    def test_empirical_data_too_easy(self):
        from mandarin.ai.content_quality import assess_question_quality
        result = assess_question_quality(None, {
            "question": "什么？",
            "answer": "A",
            "distractors": ["B"],
            "empirical_correct_rate": 0.95,
        })
        assert result["dimension_scores"]["empirical_difficulty"] == 40


class TestAssessGrammarQuality:
    def test_not_found(self, mem_db):
        from mandarin.ai.content_quality import assess_grammar_quality
        result = assess_grammar_quality(mem_db, 999)
        assert result["overall_score"] == 0
        assert result["grade"] == "F"
        assert "error" in result

    def test_basic_grammar_point(self, mem_db):
        from mandarin.ai.content_quality import assess_grammar_quality
        mem_db.execute("""
            INSERT INTO grammar_point (id, name, name_zh, description, examples_json, category, hsk_level)
            VALUES (1, 'ba_construction', '把字句', 'Ba construction', ?, 'structure', 3)
        """, (json.dumps([
            {"hanzi": "我把书放在桌子上", "english": "I put the book on the table"},
            {"hanzi": "他把门关上了", "english": "He closed the door"},
            {"hanzi": "请把窗户打开", "english": "Please open the window"},
        ]),))
        mem_db.commit()

        result = assess_grammar_quality(mem_db, 1)
        assert result["overall_score"] > 0
        assert result["grade"] in ("A", "B", "C", "D", "F")
        assert "completeness" in result["dimension_scores"]
        assert "example_quality" in result["dimension_scores"]

    def test_grammar_with_links(self, mem_db):
        from mandarin.ai.content_quality import assess_grammar_quality
        mem_db.execute("""
            INSERT INTO grammar_point (id, name, name_zh, description, examples_json, category, hsk_level)
            VALUES (2, 'le_particle', '了', 'Le particle', '[]', 'particle', 1)
        """)
        # Add content items and links
        for i in range(5):
            mem_db.execute(
                "INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level) VALUES (?, ?, ?, ?, 1)",
                (i+1, f"字{i}", f"zi{i}", f"word{i}"),
            )
            mem_db.execute("INSERT INTO content_grammar (grammar_point_id, content_item_id) VALUES (2, ?)", (i+1,))
        mem_db.commit()

        result = assess_grammar_quality(mem_db, 2)
        assert result["dimension_scores"]["content_integration"] == 95


class TestAssessPassageQuality:
    @patch("mandarin.ai.content_quality.is_ollama_available", return_value=False)
    def test_passage_not_found(self, _mock, mem_db):
        from mandarin.ai.content_quality import assess_passage_quality
        result = assess_passage_quality(mem_db, "nonexistent")
        assert result["overall_score"] == 0
        assert "error" in result

    @patch("mandarin.ai.content_quality.is_ollama_available", return_value=False)
    def test_passage_not_found_returns_zero(self, _mock, mem_db):
        from mandarin.ai.content_quality import assess_passage_quality
        # Without actual passages file, should gracefully return 0
        result = assess_passage_quality(mem_db, "nonexistent_id")
        assert result["overall_score"] == 0


class TestAssessListeningQuality:
    def test_no_listening_data(self, mem_db):
        from mandarin.ai.content_quality import assess_listening_quality
        result = assess_listening_quality(mem_db, "item1")
        assert result["overall_score"] > 0
        assert result["dimension_scores"]["consumption_rate"] == 30

    def test_with_listening_data(self, mem_db):
        from mandarin.ai.content_quality import assess_listening_quality
        mem_db.execute("""
            INSERT INTO listening_progress (passage_id, user_id, hsk_level, questions_correct, questions_total)
            VALUES ('item2', 1, 1, 8, 10)
        """)
        mem_db.commit()
        result = assess_listening_quality(mem_db, "item2")
        assert result["dimension_scores"]["consumption_rate"] > 30
        assert result["dimension_scores"]["comprehension"] == 80


class TestAssessMediaShelfHealth:
    def test_no_media(self, mem_db):
        from mandarin.ai.content_quality import assess_media_shelf_health
        result = assess_media_shelf_health(mem_db)
        assert result["overall_score"] == 30
        assert result["grade"] == "F"

    def test_with_media(self, mem_db):
        from mandarin.ai.content_quality import assess_media_shelf_health
        mem_db.execute("""
            INSERT INTO media_watch (user_id, media_id, title, media_type, times_watched, last_watched_at)
            VALUES (1, 'v1', 'Video 1', 'video', 3, datetime('now'))
        """)
        mem_db.execute("""
            INSERT INTO media_watch (user_id, media_id, title, media_type, times_watched, last_watched_at)
            VALUES (1, 'p1', 'Podcast 1', 'podcast', 1, datetime('now', '-5 days'))
        """)
        mem_db.execute("""
            INSERT INTO media_watch (user_id, media_id, title, media_type, times_watched, last_watched_at)
            VALUES (1, 's1', 'Social 1', 'social_media', 2, datetime('now', '-1 day'))
        """)
        mem_db.commit()
        result = assess_media_shelf_health(mem_db)
        assert result["overall_score"] > 30
        assert result["dimension_scores"]["media_type_diversity"] == 95


class TestAssessDialogueQuality:
    @patch("mandarin.ai.content_quality.is_ollama_available", return_value=False)
    def test_not_found(self, _mock, mem_db):
        from mandarin.ai.content_quality import assess_dialogue_quality
        result = assess_dialogue_quality(mem_db, 999)
        assert result["overall_score"] == 0
        assert "error" in result

    @patch("mandarin.ai.content_quality.is_ollama_available", return_value=False)
    def test_basic_dialogue(self, _mock, mem_db):
        from mandarin.ai.content_quality import assess_dialogue_quality
        tree = {
            "turns": [
                {"text": "你好，请问这个怎么卖的？", "speaker": "customer"},
                {"text": "这个五块钱一斤。你要多少啊？便宜又好吃的。", "speaker": "vendor"},
                {"text": "给我两斤吧。", "speaker": "customer"},
            ]
        }
        mem_db.execute("""
            INSERT INTO dialogue_scenario (id, title, title_zh, register, hsk_level, tree_json)
            VALUES (1, 'Buying fruit', '买水果', 'casual', 2, ?)
        """, (json.dumps(tree),))
        mem_db.commit()

        result = assess_dialogue_quality(mem_db, 1)
        assert result["overall_score"] > 0
        assert "modal_particles" in result["dimension_scores"]


class TestContentQualityAnalyzer:
    def test_empty_corpus(self, mem_db):
        from mandarin.ai.content_quality import ContentQualityAnalyzer
        analyzer = ContentQualityAnalyzer()
        findings = analyzer.run(mem_db)
        assert isinstance(findings, list)
        # Should find "empty corpus" critical finding
        critical = [f for f in findings if f["severity"] == "critical"]
        assert len(critical) > 0

    def test_with_content(self, mem_db):
        from mandarin.ai.content_quality import ContentQualityAnalyzer
        # Add some content items
        for i in range(1, 25):
            mem_db.execute("""
                INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status, item_type)
                VALUES (?, ?, ?, ?, 'drill_ready', 'vocab')
            """, (f"字{i}", f"zi{i}", f"char{i}", min(i % 6 + 1, 6)))
        mem_db.commit()

        analyzer = ContentQualityAnalyzer()
        findings = analyzer.run(mem_db)
        assert isinstance(findings, list)


class TestCorpusAuditReport:
    def test_empty_db(self, mem_db):
        from mandarin.ai.content_quality import generate_corpus_audit_report
        report = generate_corpus_audit_report(mem_db)
        assert "health_grade" in report
        assert "findings" in report
        assert report["corpus_size"] == 0

    def test_with_data(self, mem_db):
        from mandarin.ai.content_quality import generate_corpus_audit_report
        for i in range(1, 10):
            mem_db.execute("""
                INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status)
                VALUES (?, ?, ?, 1, 'drill_ready')
            """, (f"字{i}", f"zi{i}", f"char{i}"))
        mem_db.commit()

        report = generate_corpus_audit_report(mem_db)
        assert report["corpus_size"] > 0
        assert "generated_at" in report
        assert "severity_counts" in report

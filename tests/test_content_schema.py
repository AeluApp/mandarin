"""Tests for mandarin.ai.content_schema — Document 5 schema additions."""

import json
import tempfile
from pathlib import Path

import pytest

from mandarin import db
from mandarin.db.core import _migrate
from mandarin.ai.content_schema import (
    CONTENT_QUALITY_SCHEMA,
    ensure_content_quality_tables,
    migrate_passages_to_db,
    get_passage_questions,
    record_question_answer,
    add_quality_finding,
    get_quality_findings,
    resolve_finding,
    save_corpus_audit,
    get_latest_corpus_audit,
    _classify_question_type,
    _cognitive_level_for_type,
)


@pytest.fixture
def cq_db():
    """Fresh DB with base schema + content quality tables."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    ensure_content_quality_tables(conn)
    yield conn, path
    conn.close()
    path.unlink(missing_ok=True)


@pytest.fixture
def sample_passages_file(tmp_path):
    """Write a minimal reading_passages.json for testing."""
    data = {
        "passages": [
            {
                "id": "test_001",
                "title": "Test Passage",
                "title_zh": "测试文章",
                "hsk_level": 1,
                "text_zh": "今天天气很好。",
                "text_pinyin": "Jīntiān tiānqì hěn hǎo.",
                "text_en": "The weather is nice today.",
                "questions": [
                    {
                        "type": "mc",
                        "q_zh": "今天天气怎么样？",
                        "q_en": "How is the weather today?",
                        "options": [
                            {"text": "很好", "text_en": "nice", "correct": True},
                            {"text": "不好", "text_en": "not good", "correct": False},
                            {"text": "很冷", "text_en": "cold", "correct": False},
                            {"text": "下雨", "text_en": "rainy", "correct": False},
                        ],
                        "difficulty": 0.2,
                        "explanation": "The passage says 天气很好.",
                    },
                    {
                        "type": "mc",
                        "q_zh": "这段话想说明什么？",
                        "q_en": "What does this passage suggest?",
                        "options": [
                            {"text": "心情好", "text_en": "happy mood", "correct": True},
                            {"text": "心情差", "text_en": "bad mood", "correct": False},
                        ],
                        "difficulty": 0.5,
                        "explanation": "Good weather often implies a good mood.",
                    },
                ],
            },
            {
                "id": "test_002",
                "title": "Second Passage",
                "title_zh": "第二篇",
                "hsk_level": 2,
                "text_zh": "我喜欢读书。",
                "text_pinyin": "Wǒ xǐhuān dú shū.",
                "text_en": "I like reading.",
                "questions": [
                    {
                        "type": "mc",
                        "q_zh": "他喜欢做什么？",
                        "q_en": "What does he like to do?",
                        "options": [
                            {"text": "读书", "text_en": "read", "correct": True},
                            {"text": "跑步", "text_en": "run", "correct": False},
                            {"text": "唱歌", "text_en": "sing", "correct": False},
                        ],
                        "difficulty": 0.1,
                        "explanation": "Direct recall.",
                    },
                ],
            },
        ]
    }
    path = tmp_path / "reading_passages.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ── Table creation ──────────────────────────────────────────────────────────


def test_tables_created(cq_db):
    """All six content quality tables exist after ensure."""
    conn, _ = cq_db
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for t in [
        "comprehension_question",
        "passage_quality",
        "audio_cache",
        "tonal_validation_failure",
        "content_quality_finding",
        "corpus_audit",
    ]:
        assert t in tables, f"Missing table: {t}"


def test_table_creation_idempotent(cq_db):
    """Calling ensure twice does not raise."""
    conn, _ = cq_db
    ensure_content_quality_tables(conn)
    ensure_content_quality_tables(conn)
    # No error means idempotent


def test_comprehension_question_columns(cq_db):
    """Verify comprehension_question has expected columns."""
    conn, _ = cq_db
    cols = {r[1] for r in conn.execute("PRAGMA table_info(comprehension_question)").fetchall()}
    expected = {
        "id", "passage_id", "question_zh", "question_en",
        "question_type", "cognitive_level",
        "answer_zh", "answer_en",
        "distractor_a_zh", "distractor_b_zh", "distractor_c_zh",
        "difficulty", "explanation", "answerable_without_reading",
        "times_answered", "times_correct", "quality_score", "created_at",
    }
    assert expected.issubset(cols)


# ── Passage migration ──────────────────────────────────────────────────────


def test_migrate_passages_counts(cq_db, sample_passages_file):
    """Migration returns correct passage and question counts."""
    conn, _ = cq_db
    result = migrate_passages_to_db(conn, sample_passages_file)
    assert result["passages"] == 2
    assert result["questions"] == 3


def test_migrate_passages_idempotent(cq_db, sample_passages_file):
    """Running migration twice does not duplicate rows (INSERT OR IGNORE)."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    migrate_passages_to_db(conn, sample_passages_file)
    count = conn.execute("SELECT COUNT(*) FROM comprehension_question").fetchone()[0]
    assert count == 3


def test_migrate_creates_correct_ids(cq_db, sample_passages_file):
    """Question ids follow passage_id_qN pattern."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM comprehension_question ORDER BY id"
    ).fetchall()]
    assert "test_001_q0" in ids
    assert "test_001_q1" in ids
    assert "test_002_q0" in ids


def test_migrate_extracts_distractors(cq_db, sample_passages_file):
    """Distractors are correctly extracted from non-correct options."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    row = conn.execute(
        "SELECT distractor_a_zh, distractor_b_zh, distractor_c_zh "
        "FROM comprehension_question WHERE id = 'test_001_q0'"
    ).fetchone()
    distractors = [row[0], row[1], row[2]]
    assert "不好" in distractors
    assert "很冷" in distractors
    assert "下雨" in distractors


def test_migrate_file_not_found(cq_db):
    """Migration raises FileNotFoundError for missing file."""
    conn, _ = cq_db
    with pytest.raises(FileNotFoundError):
        migrate_passages_to_db(conn, "/nonexistent/path.json")


# ── Question classification ────────────────────────────────────────────────


def test_classify_recall():
    """Simple factual question classified as recall."""
    assert _classify_question_type("街上有人吗？", "Are there people?") == "recall"


def test_classify_inference_zh():
    """Question with 说明 keyword classified as inference."""
    assert _classify_question_type("这说明了什么？", None) == "inference"


def test_classify_inference_en():
    """Question with 'suggest' keyword classified as inference."""
    assert _classify_question_type("这个问题", "What does this suggest?") == "inference"


def test_classify_synthesis():
    """Question about main theme classified as synthesis."""
    assert _classify_question_type("全文的主题是什么？", "What is the main idea?") == "synthesis"


def test_cognitive_levels():
    """Cognitive levels map correctly for each type."""
    assert _cognitive_level_for_type("recall") == 1
    assert _cognitive_level_for_type("inference") == 2
    assert _cognitive_level_for_type("vocabulary_in_context") == 2
    assert _cognitive_level_for_type("synthesis") == 3
    assert _cognitive_level_for_type("cultural") == 3


# ── Question retrieval ──────────────────────────────────────────────────────


def test_get_passage_questions(cq_db, sample_passages_file):
    """Retrieval returns correct structure and count."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    qs = get_passage_questions(conn, "test_001")
    assert len(qs) == 2
    assert all(isinstance(q, dict) for q in qs)
    assert qs[0]["passage_id"] == "test_001"
    assert qs[0]["question_zh"] == "今天天气怎么样？"
    assert qs[0]["times_answered"] == 0


def test_get_passage_questions_empty(cq_db):
    """Retrieval for nonexistent passage returns empty list."""
    conn, _ = cq_db
    qs = get_passage_questions(conn, "nonexistent_999")
    assert qs == []


# ── Answer recording ────────────────────────────────────────────────────────


def test_record_correct_answer(cq_db, sample_passages_file):
    """Recording a correct answer increments both counters."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    record_question_answer(conn, "test_001_q0", correct=True)
    row = conn.execute(
        "SELECT times_answered, times_correct FROM comprehension_question WHERE id = 'test_001_q0'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 1


def test_record_incorrect_answer(cq_db, sample_passages_file):
    """Recording an incorrect answer increments only times_answered."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    record_question_answer(conn, "test_001_q0", correct=False)
    row = conn.execute(
        "SELECT times_answered, times_correct FROM comprehension_question WHERE id = 'test_001_q0'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 0


def test_record_multiple_answers(cq_db, sample_passages_file):
    """Multiple recordings accumulate correctly."""
    conn, _ = cq_db
    migrate_passages_to_db(conn, sample_passages_file)
    record_question_answer(conn, "test_001_q0", correct=True)
    record_question_answer(conn, "test_001_q0", correct=True)
    record_question_answer(conn, "test_001_q0", correct=False)
    row = conn.execute(
        "SELECT times_answered, times_correct FROM comprehension_question WHERE id = 'test_001_q0'"
    ).fetchone()
    assert row[0] == 3
    assert row[1] == 2


# ── Quality findings ────────────────────────────────────────────────────────


def test_add_and_retrieve_finding(cq_db):
    """Insert a finding and retrieve it."""
    conn, _ = cq_db
    fid = add_quality_finding(
        conn,
        dimension="vocabulary",
        title="Low coverage at HSK 3",
        severity="medium",
        detail="Only 40% of HSK 3 vocab appears in passages.",
        recommendation="Add 15 more HSK 3 passages.",
    )
    assert fid is not None
    findings = get_quality_findings(conn)
    assert len(findings) == 1
    assert findings[0]["title"] == "Low coverage at HSK 3"
    assert findings[0]["severity"] == "medium"
    assert findings[0]["resolved"] == 0


def test_resolve_finding(cq_db):
    """Resolving a finding marks it resolved."""
    conn, _ = cq_db
    fid = add_quality_finding(conn, "tone", "Tone 3 sandhi gaps", "high")
    resolve_finding(conn, fid)
    findings = get_quality_findings(conn, unresolved_only=True)
    assert len(findings) == 0
    all_findings = get_quality_findings(conn)
    assert len(all_findings) == 1
    assert all_findings[0]["resolved"] == 1


def test_finding_severity_filter(cq_db):
    """Filtering by severity works."""
    conn, _ = cq_db
    add_quality_finding(conn, "vocab", "A", "low")
    add_quality_finding(conn, "tone", "B", "critical")
    add_quality_finding(conn, "grammar", "C", "low")
    low = get_quality_findings(conn, severity="low")
    assert len(low) == 2
    crit = get_quality_findings(conn, severity="critical")
    assert len(crit) == 1


def test_finding_invalid_severity(cq_db):
    """Invalid severity raises ValueError."""
    conn, _ = cq_db
    with pytest.raises(ValueError, match="Invalid severity"):
        add_quality_finding(conn, "x", "y", "bogus")


# ── Corpus audit ────────────────────────────────────────────────────────────


def test_save_and_retrieve_audit(cq_db):
    """Save an audit snapshot and retrieve it."""
    conn, _ = cq_db
    report = {"total_passages": 100, "grade": "B+", "findings": []}
    aid = save_corpus_audit(conn, report, overall_grade="B+", finding_count=0)
    assert aid is not None
    latest = get_latest_corpus_audit(conn)
    assert latest is not None
    assert latest["overall_grade"] == "B+"
    assert latest["finding_count"] == 0
    assert latest["report"]["total_passages"] == 100


def test_latest_audit_returns_most_recent(cq_db):
    """Multiple audits — latest is returned."""
    conn, _ = cq_db
    save_corpus_audit(conn, {"v": 1}, overall_grade="C")
    save_corpus_audit(conn, {"v": 2}, overall_grade="B+")
    latest = get_latest_corpus_audit(conn)
    assert latest["overall_grade"] == "B+"
    assert latest["report"]["v"] == 2


def test_latest_audit_empty_db(cq_db):
    """No audits returns None."""
    conn, _ = cq_db
    assert get_latest_corpus_audit(conn) is None

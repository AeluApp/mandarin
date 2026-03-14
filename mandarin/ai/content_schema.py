"""Document 5 content quality schema additions and migration.

Defines new tables for comprehension questions, passage quality tracking,
audio caching, tonal validation, content quality findings, and corpus audits.
All tables are additive — existing schema is not modified.

Usage:
    from mandarin.ai.content_schema import ensure_content_quality_tables
    with db.connection() as conn:
        ensure_content_quality_tables(conn)
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Schema DDL ──────────────────────────────────────────────────────────────

CONTENT_QUALITY_SCHEMA = """
-- Content quality extensions (additive — don't modify existing tables)

-- Comprehension questions normalized from JSON
CREATE TABLE IF NOT EXISTS comprehension_question (
    id TEXT PRIMARY KEY,
    passage_id TEXT NOT NULL,
    question_zh TEXT NOT NULL,
    question_en TEXT,
    question_type TEXT NOT NULL CHECK (question_type IN (
        'recall', 'inference', 'vocabulary_in_context', 'synthesis', 'cultural'
    )),
    cognitive_level INTEGER CHECK (cognitive_level BETWEEN 1 AND 3),
    answer_zh TEXT NOT NULL,
    answer_en TEXT,
    distractor_a_zh TEXT,
    distractor_b_zh TEXT,
    distractor_c_zh TEXT,
    difficulty REAL,
    explanation TEXT,
    answerable_without_reading INTEGER,
    times_answered INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    quality_score REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cq_passage ON comprehension_question(passage_id);
CREATE INDEX IF NOT EXISTS idx_cq_type ON comprehension_question(question_type);

-- Reading passage quality tracking
CREATE TABLE IF NOT EXISTS passage_quality (
    passage_id TEXT PRIMARY KEY,
    vocabulary_density REAL,
    authenticity_score REAL,
    coherence_score REAL,
    question_quality_score REAL,
    acquisition_rate REAL,
    overall_score REAL,
    grade TEXT,
    assessed_at TEXT DEFAULT (datetime('now'))
);

-- Audio cache for Voice of Aelu
CREATE TABLE IF NOT EXISTS audio_cache (
    cache_key TEXT PRIMARY KEY,
    text_zh TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    duration_seconds REAL,
    tts_engine TEXT NOT NULL,
    tonal_accuracy_validated INTEGER DEFAULT 0,
    generated_at TEXT DEFAULT (datetime('now')),
    hit_count INTEGER DEFAULT 0
);

-- Tonal validation failures
CREATE TABLE IF NOT EXISTS tonal_validation_failure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_zh TEXT NOT NULL,
    expected_pinyin TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    resolved INTEGER DEFAULT 0,
    resolution TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Content quality findings (from analyzer)
CREATE TABLE IF NOT EXISTS content_quality_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    detail TEXT,
    recommendation TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cqf_severity ON content_quality_finding(severity);
CREATE INDEX IF NOT EXISTS idx_cqf_dimension ON content_quality_finding(dimension);

-- Corpus audit snapshots
CREATE TABLE IF NOT EXISTS corpus_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_json TEXT NOT NULL,
    overall_grade TEXT,
    finding_count INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

# Tables created by the schema above (used for idempotency check)
_CONTENT_QUALITY_TABLES = frozenset({
    "comprehension_question",
    "passage_quality",
    "audio_cache",
    "tonal_validation_failure",
    "content_quality_finding",
    "corpus_audit",
})

# Keywords in question text (zh or en) that suggest inference rather than recall
_INFERENCE_KEYWORDS_ZH = re.compile(
    r"(说明|暗示|推测|为什么|表达|体现|反映|想说什么|告诉我们|你觉得)"
)
_INFERENCE_KEYWORDS_EN = re.compile(
    r"(suggest|infer|imply|tell us|what does.*mean|why|reflect|indicate|reveal)",
    re.IGNORECASE,
)

# Keywords suggesting vocabulary-in-context question
_VOCAB_KEYWORDS_ZH = re.compile(r"(意思|词|字|表示)")
_VOCAB_KEYWORDS_EN = re.compile(
    r"(mean|vocab|word|definition|translate)", re.IGNORECASE
)

# Keywords suggesting synthesis
_SYNTHESIS_KEYWORDS_ZH = re.compile(r"(总结|主题|全文|整体|综合)")
_SYNTHESIS_KEYWORDS_EN = re.compile(
    r"(summar|theme|overall|main idea|conclusion)", re.IGNORECASE
)

# Keywords suggesting cultural understanding
_CULTURAL_KEYWORDS_ZH = re.compile(r"(文化|传统|习俗|风俗|中国)")
_CULTURAL_KEYWORDS_EN = re.compile(
    r"(cultur|tradition|custom|chinese society)", re.IGNORECASE
)


# ── Table helpers ───────────────────────────────────────────────────────────

def _table_set(conn: sqlite3.Connection) -> set[str]:
    """Return the set of table names in the database."""
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def ensure_content_quality_tables(conn: sqlite3.Connection) -> None:
    """Create all content quality tables if they don't exist. Idempotent."""
    conn.executescript(CONTENT_QUALITY_SCHEMA)
    conn.commit()
    logger.info("Content quality tables ensured.")


# ── Question type classification ────────────────────────────────────────────

def _classify_question_type(q_zh: str, q_en: str | None) -> str:
    """Classify a question into one of the five content quality types.

    Heuristic priority:
      1. cultural (rare, specific keywords)
      2. vocabulary_in_context
      3. synthesis
      4. inference (asks "why", "suggest", "what does it mean")
      5. recall (default — direct factual retrieval)
    """
    texts = [q_zh]
    if q_en:
        texts.append(q_en)
    combined = " ".join(texts)

    if _CULTURAL_KEYWORDS_ZH.search(q_zh) or (
        q_en and _CULTURAL_KEYWORDS_EN.search(q_en)
    ):
        return "cultural"

    if _VOCAB_KEYWORDS_ZH.search(q_zh) or (
        q_en and _VOCAB_KEYWORDS_EN.search(q_en)
    ):
        return "vocabulary_in_context"

    if _SYNTHESIS_KEYWORDS_ZH.search(q_zh) or (
        q_en and _SYNTHESIS_KEYWORDS_EN.search(q_en)
    ):
        return "synthesis"

    if _INFERENCE_KEYWORDS_ZH.search(q_zh) or (
        q_en and _INFERENCE_KEYWORDS_EN.search(q_en)
    ):
        return "inference"

    return "recall"


def _cognitive_level_for_type(qtype: str) -> int:
    """Map question type to cognitive level (1=remember, 2=understand, 3=apply+)."""
    return {
        "recall": 1,
        "vocabulary_in_context": 2,
        "inference": 2,
        "synthesis": 3,
        "cultural": 3,
    }.get(qtype, 1)


# ── Passage migration ──────────────────────────────────────────────────────

def migrate_passages_to_db(
    conn: sqlite3.Connection,
    passages_json_path: str | Path,
) -> dict[str, int]:
    """Read reading_passages.json and insert normalized comprehension_question rows.

    For each passage, each question is normalized into its own row with:
    - Classified question_type (heuristic from question text)
    - Cognitive level derived from type
    - Correct answer extracted from options
    - Up to 3 distractors from non-correct options

    Returns dict with 'passages' and 'questions' counts.
    """
    path = Path(passages_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Passages file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    passages = data.get("passages", [])
    if not passages:
        return {"passages": 0, "questions": 0}

    ensure_content_quality_tables(conn)

    passage_count = 0
    question_count = 0

    for passage in passages:
        passage_id = passage.get("id", "")
        if not passage_id:
            continue

        questions = passage.get("questions", [])
        if not questions:
            continue

        passage_count += 1

        for qi, q in enumerate(questions):
            q_id = f"{passage_id}_q{qi}"

            q_zh = q.get("q_zh", "")
            q_en = q.get("q_en")

            if not q_zh:
                continue

            # Classify
            qtype = _classify_question_type(q_zh, q_en)
            cog_level = _cognitive_level_for_type(qtype)

            # Extract correct answer and distractors from options
            options = q.get("options", [])
            answer_zh = ""
            answer_en = ""
            distractors: list[str] = []

            for opt in options:
                if opt.get("correct"):
                    answer_zh = opt.get("text", "")
                    answer_en = opt.get("text_en", "")
                else:
                    distractors.append(opt.get("text", ""))

            if not answer_zh:
                # No correct option marked — skip this question
                continue

            # Pad distractors to 3 slots
            while len(distractors) < 3:
                distractors.append(None)

            difficulty = q.get("difficulty")
            explanation = q.get("explanation")

            conn.execute(
                """
                INSERT OR IGNORE INTO comprehension_question (
                    id, passage_id, question_zh, question_en,
                    question_type, cognitive_level,
                    answer_zh, answer_en,
                    distractor_a_zh, distractor_b_zh, distractor_c_zh,
                    difficulty, explanation, answerable_without_reading
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q_id, passage_id, q_zh, q_en,
                    qtype, cog_level,
                    answer_zh, answer_en,
                    distractors[0], distractors[1], distractors[2],
                    difficulty, explanation, 0,
                ),
            )
            question_count += 1

    conn.commit()
    logger.info(
        "Migrated %d passages, %d questions.", passage_count, question_count
    )
    return {"passages": passage_count, "questions": question_count}


# ── Question retrieval ──────────────────────────────────────────────────────

def get_passage_questions(
    conn: sqlite3.Connection, passage_id: str
) -> list[dict[str, Any]]:
    """Retrieve all comprehension questions for a passage.

    Returns a list of dicts with all question fields.
    """
    rows = conn.execute(
        """
        SELECT id, passage_id, question_zh, question_en,
               question_type, cognitive_level,
               answer_zh, answer_en,
               distractor_a_zh, distractor_b_zh, distractor_c_zh,
               difficulty, explanation, answerable_without_reading,
               times_answered, times_correct, quality_score, created_at
        FROM comprehension_question
        WHERE passage_id = ?
        ORDER BY id
        """,
        (passage_id,),
    ).fetchall()

    return [dict(r) for r in rows]


# ── Answer recording ────────────────────────────────────────────────────────

def record_question_answer(
    conn: sqlite3.Connection,
    question_id: str,
    correct: bool,
) -> None:
    """Increment times_answered (and times_correct if correct) for a question."""
    conn.execute(
        "UPDATE comprehension_question SET times_answered = times_answered + 1 WHERE id = ?",
        (question_id,),
    )
    if correct:
        conn.execute(
            "UPDATE comprehension_question SET times_correct = times_correct + 1 WHERE id = ?",
            (question_id,),
        )
    conn.commit()


# ── Quality findings ────────────────────────────────────────────────────────

def add_quality_finding(
    conn: sqlite3.Connection,
    dimension: str,
    title: str,
    severity: str,
    detail: str | None = None,
    recommendation: str | None = None,
) -> int:
    """Insert a content quality finding. Returns the new row id."""
    if severity not in ("low", "medium", "high", "critical"):
        raise ValueError(f"Invalid severity: {severity}")

    cur = conn.execute(
        """
        INSERT INTO content_quality_finding
            (dimension, title, severity, detail, recommendation)
        VALUES (?, ?, ?, ?, ?)
        """,
        (dimension, title, severity, detail, recommendation),
    )
    conn.commit()
    return cur.lastrowid


def get_quality_findings(
    conn: sqlite3.Connection,
    *,
    severity: str | None = None,
    unresolved_only: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve content quality findings with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []

    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if unresolved_only:
        clauses.append("resolved = 0")

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    rows = conn.execute(
        f"SELECT * FROM content_quality_finding {where} ORDER BY id DESC",
        params,
    ).fetchall()

    return [dict(r) for r in rows]


def resolve_finding(conn: sqlite3.Connection, finding_id: int) -> None:
    """Mark a content quality finding as resolved."""
    conn.execute(
        "UPDATE content_quality_finding SET resolved = 1 WHERE id = ?",
        (finding_id,),
    )
    conn.commit()


# ── Corpus audit snapshots ──────────────────────────────────────────────────

def save_corpus_audit(
    conn: sqlite3.Connection,
    report: dict[str, Any],
    overall_grade: str | None = None,
    finding_count: int | None = None,
) -> int:
    """Save a corpus audit snapshot. Returns the new row id."""
    cur = conn.execute(
        """
        INSERT INTO corpus_audit (report_json, overall_grade, finding_count)
        VALUES (?, ?, ?)
        """,
        (json.dumps(report, ensure_ascii=False), overall_grade, finding_count),
    )
    conn.commit()
    return cur.lastrowid


def get_latest_corpus_audit(
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    """Retrieve the most recent corpus audit snapshot."""
    row = conn.execute(
        "SELECT * FROM corpus_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["report"] = json.loads(result["report_json"])
    return result

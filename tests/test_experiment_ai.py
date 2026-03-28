"""Tests for mandarin.ai.experiment_ai — AI experiment advisor module.

Tests mock Ollama responses to verify:
- Hypothesis generation from learner data
- Variant design
- Qualitative feedback analysis
- Experiment prioritization
- Rollout recommendations
- Daemon integration (propose_ai_hypotheses, advise_on_concluded)
- JSON parsing robustness
- Graceful degradation when Ollama unavailable
- Governance queue integration
"""

import pytest
pytest.importorskip("httpx")

import json
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import make_test_db

from mandarin.ai.ollama_client import OllamaResponse


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def exp_db():
    """Provide a test DB connection with experiment tables."""
    conn, path = make_test_db()
    yield conn
    conn.close()
    path.unlink(missing_ok=True)


def _insert_session(conn, user_id=1, days_ago=0, items=10, correct=8, duration=300,
                    outcome="completed", modality_counts=None):
    """Insert a session_log row."""
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    mc = json.dumps(modality_counts) if modality_counts else None
    conn.execute(
        """INSERT INTO session_log
           (user_id, started_at, duration_seconds, items_completed, items_correct,
            session_outcome, modality_counts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, ts, duration, items, correct, outcome, mc),
    )
    conn.commit()


def _create_experiment(conn, name="test_exp", status="running",
                       variants=None, traffic_pct=100.0):
    """Create a test experiment."""
    variants = variants or ["control", "treatment"]
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO experiment
           (name, description, variants, traffic_pct, guardrail_metrics,
            min_sample_size, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, f"Test experiment {name}", json.dumps(variants), traffic_pct,
         json.dumps(["session_completion_rate"]), 50, status, now),
    )
    conn.commit()
    return cur.lastrowid


def _make_ollama_response(text, success=True):
    """Create a mock OllamaResponse."""
    return OllamaResponse(
        success=success,
        text=text,
        model_used="qwen2.5:7b",
        prompt_tokens=100,
        completion_tokens=200,
        generation_time_ms=500,
    )


# ── JSON Parsing Tests ──────────────────────────────────────────────────────


class TestParseJsonResponse:
    def test_direct_json(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_code_block(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_plain_code_block(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        text = 'Result:\n```\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_embedded_braces(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        text = 'Some text before {"key": "value"} some text after'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_empty_string(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        assert _parse_json_response("") is None

    def test_none_input(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        assert _parse_json_response(None) is None

    def test_invalid_json(self):
        from mandarin.ai.experiment_ai import _parse_json_response
        assert _parse_json_response("not json at all") is None


class TestParseHypotheses:
    def test_valid_hypotheses(self):
        from mandarin.ai.experiment_ai import _parse_hypotheses
        text = json.dumps({
            "hypotheses": [
                {"name": "test_exp", "hypothesis": "If X then Y", "primary_metric": "retention"},
                {"name": "test_exp2", "hypothesis": "If A then B", "primary_metric": "accuracy"},
            ]
        })
        result = _parse_hypotheses(text)
        assert len(result) == 2
        assert result[0]["name"] == "test_exp"

    def test_missing_name_filtered(self):
        from mandarin.ai.experiment_ai import _parse_hypotheses
        text = json.dumps({
            "hypotheses": [
                {"name": "valid", "hypothesis": "If X then Y"},
                {"hypothesis": "Missing name"},
            ]
        })
        result = _parse_hypotheses(text)
        assert len(result) == 1

    def test_missing_hypothesis_filtered(self):
        from mandarin.ai.experiment_ai import _parse_hypotheses
        text = json.dumps({
            "hypotheses": [
                {"name": "missing_hyp"},
            ]
        })
        result = _parse_hypotheses(text)
        assert len(result) == 0

    def test_invalid_json(self):
        from mandarin.ai.experiment_ai import _parse_hypotheses
        assert _parse_hypotheses("not json") == []

    def test_empty_hypotheses_list(self):
        from mandarin.ai.experiment_ai import _parse_hypotheses
        text = json.dumps({"hypotheses": []})
        assert _parse_hypotheses(text) == []


# ── Learner Signal Gathering ────────────────────────────────────────────────


class TestGatherLearnerSignals:
    def test_recent_sessions(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_learner_signals
        _insert_session(exp_db, days_ago=1, items=10, correct=8, duration=300)
        _insert_session(exp_db, days_ago=3, items=12, correct=10, duration=360)

        signals = _gather_learner_signals(exp_db)
        assert "recent_sessions" in signals
        assert signals["recent_sessions"]["total_30d"] == 2
        assert signals["recent_sessions"]["avg_accuracy"] > 0

    def test_modality_distribution(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_learner_signals
        _insert_session(exp_db, days_ago=1, modality_counts={"pinyin": 5, "character": 3})
        _insert_session(exp_db, days_ago=2, modality_counts={"pinyin": 4, "tone": 2})

        signals = _gather_learner_signals(exp_db)
        assert "modality_distribution" in signals
        assert signals["modality_distribution"]["pinyin"] == 9

    def test_weekly_completion_trend(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_learner_signals
        for d in range(0, 28, 2):
            _insert_session(exp_db, days_ago=d, outcome="completed")

        signals = _gather_learner_signals(exp_db)
        assert "weekly_completion_trend" in signals
        assert len(signals["weekly_completion_trend"]) > 0

    def test_empty_db(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_learner_signals
        signals = _gather_learner_signals(exp_db)
        # Should still return a dict, just with fewer keys
        assert isinstance(signals, dict)


# ── Experiment Context Gathering ────────────────────────────────────────────


class TestGatherExperimentContext:
    def test_basic_context(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_experiment_context
        _create_experiment(exp_db, name="ctx_test")
        context = _gather_experiment_context(exp_db, "ctx_test")
        assert "results" in context

    def test_nonexistent_experiment(self, exp_db):
        from mandarin.ai.experiment_ai import _gather_experiment_context
        context = _gather_experiment_context(exp_db, "doesnt_exist")
        # Should return a dict (maybe with error in results), not crash
        assert isinstance(context, dict)


# ── Generate Hypotheses ─────────────────────────────────────────────────────


class TestGenerateHypotheses:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import generate_hypotheses
        result = generate_hypotheses(exp_db)
        assert result == []

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_successful_generation(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import generate_hypotheses

        _insert_session(exp_db, days_ago=1)
        _insert_session(exp_db, days_ago=3)

        mock_gen.return_value = _make_ollama_response(json.dumps({
            "hypotheses": [
                {
                    "name": "spaced_review_boost",
                    "description": "Test spaced review reminders",
                    "hypothesis": "If we add spaced review reminders, then retention improves",
                    "primary_metric": "retention_7d",
                    "expected_direction": "increase",
                    "risk_level": "low",
                    "variants": ["control", "spaced_reminder"],
                    "rationale": "Data shows accuracy plateauing without review",
                }
            ]
        }))

        result = generate_hypotheses(exp_db)
        assert len(result) == 1
        assert result[0]["name"] == "spaced_review_boost"
        mock_gen.assert_called_once()

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_llm_failure(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import generate_hypotheses

        _insert_session(exp_db, days_ago=1)
        mock_gen.return_value = OllamaResponse(success=False, error="timeout")

        result = generate_hypotheses(exp_db)
        assert result == []

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_no_signals(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import generate_hypotheses
        # Empty DB — no sessions, no signals
        result = generate_hypotheses(exp_db)
        assert result == []
        mock_gen.assert_not_called()


# ── Design Variants ─────────────────────────────────────────────────────────


class TestDesignVariants:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import design_variants
        result = design_variants(exp_db, "test", "If X then Y")
        assert result is None

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_successful_design(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import design_variants

        mock_gen.return_value = _make_ollama_response(json.dumps({
            "control": {"name": "control", "description": "Current behavior"},
            "treatment": {"name": "spaced_reminder", "description": "Add review prompts"},
            "guardrail_metrics": ["session_completion_rate"],
            "suggested_traffic_pct": 50,
            "suggested_min_sample": 100,
            "doctrine_compliance": "Reminders help, don't pressure",
        }))

        result = design_variants(exp_db, "spaced_review", "If we add reminders, retention improves")
        assert result is not None
        assert "control" in result
        assert "treatment" in result


# ── Analyze Experiment Feedback ──────────────────────────────────────────────


class TestAnalyzeExperimentFeedback:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import analyze_experiment_feedback
        result = analyze_experiment_feedback(exp_db, "test_exp")
        assert result is None

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_successful_analysis(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import analyze_experiment_feedback

        _create_experiment(exp_db, name="analyze_test")

        mock_gen.return_value = _make_ollama_response(json.dumps({
            "summary": "Treatment group shows improved completion but slightly shorter sessions",
            "signals": [
                {
                    "signal": "Session duration drop in treatment",
                    "interpretation": "Shorter but more focused sessions",
                    "confidence": "medium",
                    "sentiment": "neutral",
                }
            ],
            "concerns": ["Monitor for rushing through drills"],
            "recommendation": "proceed",
        }))

        result = analyze_experiment_feedback(exp_db, "analyze_test")
        assert result is not None
        assert result["recommendation"] == "proceed"
        assert len(result["signals"]) == 1

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_nonexistent_still_calls_llm(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import analyze_experiment_feedback

        # Nonexistent experiment still produces some context (error dict),
        # so the LLM is still called — verify it handles the response.
        mock_gen.return_value = _make_ollama_response(json.dumps({
            "summary": "Experiment not found",
            "signals": [],
            "concerns": [],
            "recommendation": "pause",
        }))
        result = analyze_experiment_feedback(exp_db, "nonexistent")
        assert result is not None
        assert result["recommendation"] == "pause"


# ── Prioritize Experiments ──────────────────────────────────────────────────


class TestPrioritizeExperiments:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import prioritize_experiments
        result = prioritize_experiments(exp_db, [{"name": "test"}])
        assert result == []

    def test_empty_hypotheses(self, exp_db):
        from mandarin.ai.experiment_ai import prioritize_experiments
        result = prioritize_experiments(exp_db, [])
        assert result == []

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_successful_prioritization(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import prioritize_experiments

        hypotheses = [
            {"name": "exp_a", "hypothesis": "Test A"},
            {"name": "exp_b", "hypothesis": "Test B"},
        ]

        mock_gen.return_value = _make_ollama_response(json.dumps({
            "ranked": [
                {"name": "exp_b", "priority_score": 0.8, "reasoning": "Higher uncertainty"},
                {"name": "exp_a", "priority_score": 0.5, "reasoning": "Lower expected impact"},
            ],
            "traffic_budget_note": "Sufficient traffic for one experiment",
            "conflict_warnings": [],
        }))

        result = prioritize_experiments(exp_db, hypotheses)
        assert len(result) == 2
        assert result[0]["name"] == "exp_b"
        assert result[0]["priority_score"] > result[1]["priority_score"]


# ── Recommend Rollout ───────────────────────────────────────────────────────


class TestRecommendRollout:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import recommend_rollout
        result = recommend_rollout(exp_db, "test_exp")
        assert result is None

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_successful_recommendation(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import recommend_rollout

        _create_experiment(exp_db, name="rollout_test", status="concluded")

        mock_gen.return_value = _make_ollama_response(json.dumps({
            "recommendation": "rollout",
            "confidence": "high",
            "reasoning": "Strong improvement with no counter-metric concerns",
            "conditions": ["Monitor unsubscribe rate during gradual rollout"],
            "monitoring_plan": "Watch weekly delayed recall rates",
        }))

        result = recommend_rollout(exp_db, "rollout_test")
        assert result is not None
        assert result["recommendation"] == "rollout"
        assert result["confidence"] == "high"


# ── Propose AI Hypotheses (Daemon Integration) ─────────────────────────────


class TestProposeAiHypotheses:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import propose_ai_hypotheses
        result = propose_ai_hypotheses(exp_db)
        assert result == []

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_submits_to_governance_queue(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import propose_ai_hypotheses

        _insert_session(exp_db, days_ago=1)
        _insert_session(exp_db, days_ago=3)

        # First call: generate_hypotheses
        # Second call: prioritize_experiments
        mock_gen.side_effect = [
            _make_ollama_response(json.dumps({
                "hypotheses": [
                    {
                        "name": "ai_test_exp",
                        "description": "AI-proposed test",
                        "hypothesis": "If we do X then Y",
                        "primary_metric": "retention_7d",
                        "variants": ["control", "treatment"],
                        "risk_level": "low",
                        "rationale": "Data suggests opportunity",
                    }
                ]
            })),
            _make_ollama_response(json.dumps({
                "ranked": [
                    {"name": "ai_test_exp", "priority_score": 0.7, "reasoning": "Good candidate"}
                ],
                "traffic_budget_note": "OK",
                "conflict_warnings": [],
            })),
        ]

        result = propose_ai_hypotheses(exp_db)
        assert len(result) == 1

        # Verify proposal was created
        proposal = exp_db.execute(
            "SELECT * FROM experiment_proposal WHERE name = 'ai_test_exp'"
        ).fetchone()
        assert proposal is not None
        assert proposal["source"] == "ai_advisor"

        # Verify governance queue entry was created
        queue_entry = exp_db.execute(
            """SELECT * FROM experiment_approval_queue
               WHERE experiment_name = 'ai_test_exp' AND status = 'pending'"""
        ).fetchone()
        assert queue_entry is not None
        assert queue_entry["proposed_by"] == "ai_advisor"
        assert queue_entry["action_type"] == "start_experiment"

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_skips_existing_experiment(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import propose_ai_hypotheses

        _insert_session(exp_db, days_ago=1)
        _create_experiment(exp_db, name="existing_exp", status="running")

        mock_gen.side_effect = [
            _make_ollama_response(json.dumps({
                "hypotheses": [
                    {
                        "name": "existing_exp",
                        "hypothesis": "Already exists",
                        "variants": ["control", "treatment"],
                    }
                ]
            })),
            _make_ollama_response(json.dumps({
                "ranked": [
                    {"name": "existing_exp", "priority_score": 0.5, "reasoning": "test"}
                ],
            })),
        ]

        result = propose_ai_hypotheses(exp_db)
        assert len(result) == 0  # Should skip — already exists

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_skips_existing_proposal(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import propose_ai_hypotheses

        _insert_session(exp_db, days_ago=1)

        # Pre-create a proposal
        exp_db.execute(
            """INSERT INTO experiment_proposal
               (name, description, hypothesis, source, variants, status)
               VALUES ('dup_prop', 'test', 'test', 'ai_advisor', '["c","t"]', 'pending')"""
        )
        exp_db.commit()

        mock_gen.side_effect = [
            _make_ollama_response(json.dumps({
                "hypotheses": [
                    {"name": "dup_prop", "hypothesis": "Duplicate", "variants": ["c", "t"]},
                ]
            })),
            _make_ollama_response(json.dumps({
                "ranked": [{"name": "dup_prop", "priority_score": 0.5, "reasoning": "test"}],
            })),
        ]

        result = propose_ai_hypotheses(exp_db)
        assert len(result) == 0


# ── Advise on Concluded ─────────────────────────────────────────────────────


class TestAdviseOnConcluded:
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=False)
    def test_ollama_unavailable(self, mock_avail, exp_db):
        from mandarin.ai.experiment_ai import advise_on_concluded
        result = advise_on_concluded(exp_db, "test_exp")
        assert result is None

    @patch("mandarin.ai.experiment_ai.generate")
    @patch("mandarin.ai.experiment_ai.is_ollama_available", return_value=True)
    def test_generates_recommendation(self, mock_avail, mock_gen, exp_db):
        from mandarin.ai.experiment_ai import advise_on_concluded

        _create_experiment(exp_db, name="concluded_test", status="concluded")

        # analyze_experiment_feedback call + recommend_rollout call
        mock_gen.side_effect = [
            # First: feedback analysis (called inside recommend_rollout)
            _make_ollama_response(json.dumps({
                "summary": "Good results",
                "signals": [],
                "concerns": [],
                "recommendation": "proceed",
            })),
            # Second: rollout recommendation
            _make_ollama_response(json.dumps({
                "recommendation": "rollout",
                "confidence": "medium",
                "reasoning": "Promising but limited data",
                "conditions": [],
                "monitoring_plan": "Watch retention",
            })),
        ]

        result = advise_on_concluded(exp_db, "concluded_test")
        assert result is not None
        assert result["recommendation"] == "rollout"


# ── E6–E8 Audit Checks ─────────────────────────────────────────────────────
# check_e6, check_e7, check_e8 were removed from scripts/audit_check.py
# during the audit check consolidation. These tests are no longer applicable.

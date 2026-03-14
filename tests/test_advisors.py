"""Tests for mandarin/intelligence/advisors.py.

Covers:
- _estimate_effort: file-type routing and minimum floor
- RetentionAdvisor, LearningAdvisor, GrowthAdvisor, StabilityAdvisor: evaluate()
  return shape, affinity multipliers, domain multipliers, tradeoff notes
- Mediator.resolve(): consensus path, conflict path (spread > 30), DB persistence
- Mediator.plan_sprint(): budget enforcement, priority ordering, dependency hints
- Mediator.evaluate_all(): all advisors run, DB persistence via pi_finding lookup
"""

import sqlite3
import pytest

from mandarin.intelligence.advisors import (
    EFFORT_ESTIMATES,
    _estimate_effort,
    RetentionAdvisor,
    LearningAdvisor,
    GrowthAdvisor,
    StabilityAdvisor,
    Mediator,
    _ADVISOR_AFFINITIES,
    _SEVERITY_SCORES,
    _ADVISORS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_conn():
    """Return an in-memory SQLite connection with row_factory and required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY,
            email TEXT,
            is_active INTEGER DEFAULT 1,
            subscription_tier TEXT DEFAULT 'free'
        );

        CREATE TABLE IF NOT EXISTS pi_finding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            dimension TEXT,
            severity TEXT,
            title TEXT,
            analysis TEXT,
            status TEXT DEFAULT 'investigating',
            hypothesis TEXT,
            falsification TEXT,
            root_cause_tag TEXT,
            linked_finding_id INTEGER,
            metric_name TEXT,
            metric_value_at_detection REAL,
            times_seen INTEGER DEFAULT 1,
            last_seen_audit_id INTEGER,
            resolved_at TEXT,
            resolution_notes TEXT
        );

        CREATE TABLE IF NOT EXISTS pi_advisor_opinion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER,
            advisor TEXT CHECK(advisor IN ('retention','learning','growth','stability')),
            created_at TEXT DEFAULT (datetime('now')),
            recommendation TEXT,
            priority_score REAL DEFAULT 0,
            effort_estimate REAL,
            rationale TEXT,
            tradeoff_notes TEXT
        );

        CREATE TABLE IF NOT EXISTS pi_advisor_resolution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            winning_advisor TEXT,
            resolution_rationale TEXT,
            tradeoff_summary TEXT,
            weekly_effort_budget REAL,
            constraint_notes TEXT
        );
    """)
    conn.commit()
    return conn


def insert_finding(conn, dimension="retention", severity="high",
                   title="test finding", status="investigating"):
    """Insert a pi_finding row and return its id."""
    cur = conn.execute(
        "INSERT INTO pi_finding (dimension, severity, title, analysis, status) "
        "VALUES (?, ?, ?, 'test analysis', ?)",
        (dimension, severity, title, status),
    )
    conn.commit()
    return cur.lastrowid


_DEFAULT_FILES = ["mandarin/scheduler.py"]


def make_finding(dimension="retention", severity="high", title="test finding",
                 files=_DEFAULT_FILES, recommendation="fix it"):
    """Return a finding dict matching the format used throughout the codebase."""
    return {
        "dimension": dimension,
        "severity": severity,
        "title": title,
        "analysis": "test analysis",
        "recommendation": recommendation,
        "claude_prompt": "...",
        "impact": "big",
        "files": files,
    }


# ---------------------------------------------------------------------------
# _estimate_effort
# ---------------------------------------------------------------------------

class TestEstimateEffort:

    def test_schema_file_returns_schema_migration_hours(self):
        finding = make_finding(files=["schema.sql"])
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["schema_migration"]

    def test_db_path_file_returns_schema_migration_hours(self):
        finding = make_finding(files=["mandarin/db/core.py"])
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["schema_migration"]

    def test_scheduler_file_returns_scheduler_change_hours(self):
        finding = make_finding(files=["mandarin/scheduler.py"])
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["scheduler_change"]

    def test_routes_file_returns_route_change_hours(self):
        # route_change=1.0 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["mandarin/web/routes.py"])
        expected = max(EFFORT_ESTIMATES["route_change"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_css_extension_returns_css_change_hours(self):
        # css_change=0.5 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["mandarin/web/static/style.css"])
        expected = max(EFFORT_ESTIMATES["css_change"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_style_in_name_returns_css_change_hours(self):
        # css_change=0.5 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["static/stylesheet.scss"])
        expected = max(EFFORT_ESTIMATES["css_change"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_email_file_returns_email_template_hours(self):
        # email_template=0.5 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["mandarin/email.py"])
        expected = max(EFFORT_ESTIMATES["email_template"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_drills_file_returns_drill_logic_hours(self):
        # drill_logic=2.0 > investigation floor=1.5, so raw value returned
        finding = make_finding(files=["mandarin/drills/tone.py"])
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["drill_logic"]

    def test_scripts_file_returns_content_addition_hours(self):
        # content_addition=1.0 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["scripts/expand_content.py"])
        expected = max(EFFORT_ESTIMATES["content_addition"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_settings_file_returns_config_change_hours(self):
        # config_change=0.5 < investigation floor=1.5, so floor applies
        finding = make_finding(files=["mandarin/settings.py"])
        expected = max(EFFORT_ESTIMATES["config_change"], EFFORT_ESTIMATES["investigation"])
        assert _estimate_effort(finding) == expected

    def test_unknown_file_returns_investigation_hours(self):
        finding = make_finding(files=["mandarin/audio.py"])
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["investigation"]

    def test_empty_files_returns_investigation_minimum(self):
        # No files at all: sum=0.0, floor kicks in → investigation hours
        finding = {
            "dimension": "retention", "severity": "high",
            "title": "empty files test", "files": [],
        }
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["investigation"]

    def test_missing_files_key_returns_investigation_minimum(self):
        finding = {"dimension": "retention", "severity": "high"}
        assert _estimate_effort(finding) == EFFORT_ESTIMATES["investigation"]

    def test_multiple_files_accumulates(self):
        # scheduler (3.0) + routes (1.0) = 4.0 > investigation minimum
        finding = make_finding(files=["mandarin/scheduler.py", "mandarin/web/routes.py"])
        expected = EFFORT_ESTIMATES["scheduler_change"] + EFFORT_ESTIMATES["route_change"]
        assert _estimate_effort(finding) == expected

    def test_minimum_floor_is_investigation(self):
        # Even a single css change (0.5) is less than investigation (1.5)
        finding = make_finding(files=["style.css"])
        result = _estimate_effort(finding)
        assert result == EFFORT_ESTIMATES["investigation"]

    def test_large_multi_file_finding_exceeds_minimum(self):
        finding = make_finding(files=[
            "schema.sql",           # 2.0
            "mandarin/scheduler.py", # 3.0
            "mandarin/web/routes.py", # 1.0
        ])
        expected = 2.0 + 3.0 + 1.0
        assert _estimate_effort(finding) == expected


# ---------------------------------------------------------------------------
# RetentionAdvisor
# ---------------------------------------------------------------------------

class TestRetentionAdvisor:

    def setup_method(self):
        self.advisor = RetentionAdvisor()

    def test_evaluate_returns_expected_keys(self):
        finding = make_finding(dimension="retention", severity="high")
        result = self.advisor.evaluate(finding)
        for key in ("advisor", "recommendation", "priority_score",
                    "effort_estimate", "rationale", "tradeoff_notes"):
            assert key in result, f"Missing key: {key}"

    def test_advisor_name_is_retention(self):
        finding = make_finding()
        assert self.advisor.evaluate(finding)["advisor"] == "retention"

    def test_recommendation_passes_through(self):
        finding = make_finding(recommendation="reduce churn")
        assert self.advisor.evaluate(finding)["recommendation"] == "reduce churn"

    def test_retention_dimension_high_severity_base_score(self):
        # affinity=2.0, severity=high(25), domain_mult=1.0 (no conn) → 50.0
        finding = make_finding(dimension="retention", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["priority_score"] == pytest.approx(50.0, rel=1e-3)

    def test_ux_dimension_affinity_multiplier(self):
        # affinity=1.8, severity=high(25), domain_mult=1.0 → 45.0
        finding = make_finding(dimension="ux", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["priority_score"] == pytest.approx(45.0, rel=1e-3)

    def test_unknown_dimension_uses_default_affinity(self):
        # affinity=0.5 (default), severity=high(25), domain_mult=1.0 → 12.5
        finding = make_finding(dimension="unknown_dim", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["priority_score"] == pytest.approx(12.5, rel=1e-3)

    def test_critical_severity_scores_higher_than_high(self):
        high = make_finding(dimension="retention", severity="high")
        crit = make_finding(dimension="retention", severity="critical")
        assert self.advisor.evaluate(crit)["priority_score"] > self.advisor.evaluate(high)["priority_score"]

    def test_low_severity_scores_lower_than_medium(self):
        low = make_finding(dimension="retention", severity="low")
        med = make_finding(dimension="retention", severity="medium")
        assert self.advisor.evaluate(low)["priority_score"] < self.advisor.evaluate(med)["priority_score"]

    def test_domain_multiplier_applied_when_conn_provided_retention_dim(self):
        conn = make_conn()
        conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@b.com')")
        conn.commit()
        finding = make_finding(dimension="retention", severity="high")
        result = self.advisor.evaluate(finding, conn)
        # Continuous domain_mult = 1.0 + churn_risk * 0.5 (0 declining → 1.0)
        # affinity=2.0, severity=25, domain_mult=1.0 → 50.0
        assert result["priority_score"] == pytest.approx(50.0, rel=1e-3)

    def test_domain_multiplier_applied_ux_dim_with_conn(self):
        conn = make_conn()
        finding = make_finding(dimension="ux", severity="high")
        result = self.advisor.evaluate(finding, conn)
        # Continuous domain_mult = 1.0 + churn_risk * 0.5 (no sessions → 1.0)
        # affinity=1.8, severity=25, domain_mult=1.0 → 45.0
        assert result["priority_score"] == pytest.approx(45.0, rel=1e-3)

    def test_domain_multiplier_not_applied_for_other_dim_with_conn(self):
        conn = make_conn()
        finding = make_finding(dimension="engineering", severity="high")
        result_with_conn = self.advisor.evaluate(finding, conn)
        result_no_conn = self.advisor.evaluate(finding)
        assert result_with_conn["priority_score"] == result_no_conn["priority_score"]

    def test_tradeoff_notes_for_drill_quality_dim(self):
        finding = make_finding(dimension="drill_quality", severity="high")
        result = self.advisor.evaluate(finding)
        assert "learning sequences" in result["tradeoff_notes"]

    def test_tradeoff_notes_for_srs_funnel_dim(self):
        finding = make_finding(dimension="srs_funnel", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] != ""

    def test_tradeoff_notes_empty_for_retention_dim(self):
        finding = make_finding(dimension="retention", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] == ""

    def test_effort_estimate_reflects_files(self):
        finding = make_finding(dimension="retention", files=["schema.sql"])
        result = self.advisor.evaluate(finding)
        assert result["effort_estimate"] == EFFORT_ESTIMATES["schema_migration"]

    def test_rationale_contains_advisor_name(self):
        finding = make_finding(dimension="retention", severity="medium")
        result = self.advisor.evaluate(finding)
        assert "retention" in result["rationale"]


# ---------------------------------------------------------------------------
# LearningAdvisor
# ---------------------------------------------------------------------------

class TestLearningAdvisor:

    def setup_method(self):
        self.advisor = LearningAdvisor()

    def test_evaluate_returns_expected_keys(self):
        finding = make_finding(dimension="drill_quality")
        result = self.advisor.evaluate(finding)
        for key in ("advisor", "recommendation", "priority_score",
                    "effort_estimate", "rationale", "tradeoff_notes"):
            assert key in result

    def test_advisor_name_is_learning(self):
        assert self.advisor.evaluate(make_finding())["advisor"] == "learning"

    def test_drill_quality_affinity_is_highest(self):
        finding = make_finding(dimension="drill_quality", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_srs_funnel_domain_multiplier_applied(self):
        finding = make_finding(dimension="srs_funnel", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_error_taxonomy_domain_multiplier_applied(self):
        finding = make_finding(dimension="error_taxonomy", severity="medium")
        result = self.advisor.evaluate(finding)
        # affinity=1.5, severity=12, domain_mult=1.5 → 27.0
        assert result["priority_score"] == pytest.approx(27.0, rel=1e-3)

    def test_cross_modality_domain_multiplier_applied(self):
        finding = make_finding(dimension="cross_modality", severity="medium")
        result = self.advisor.evaluate(finding)
        # affinity=1.5, severity=12, domain_mult=1.5 → 27.0
        assert result["priority_score"] == pytest.approx(27.0, rel=1e-3)

    def test_scheduler_audit_no_domain_multiplier(self):
        finding = make_finding(dimension="scheduler_audit", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=1.3, severity=25, domain_mult=1.0 → 32.5
        assert result["priority_score"] == pytest.approx(32.5, rel=1e-3)

    def test_tradeoff_notes_for_retention_dim(self):
        finding = make_finding(dimension="retention", severity="high")
        result = self.advisor.evaluate(finding)
        assert "retention" in result["tradeoff_notes"].lower()

    def test_tradeoff_notes_for_ux_dim(self):
        finding = make_finding(dimension="ux", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] != ""

    def test_no_tradeoff_notes_for_drill_quality(self):
        finding = make_finding(dimension="drill_quality", severity="high")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] == ""

    def test_conn_not_required(self):
        finding = make_finding(dimension="drill_quality")
        # Should not raise without conn
        result = self.advisor.evaluate(finding)
        assert result["priority_score"] > 0


# ---------------------------------------------------------------------------
# GrowthAdvisor
# ---------------------------------------------------------------------------

class TestGrowthAdvisor:

    def setup_method(self):
        self.advisor = GrowthAdvisor()

    def test_evaluate_returns_expected_keys(self):
        finding = make_finding(dimension="profitability")
        result = self.advisor.evaluate(finding)
        for key in ("advisor", "recommendation", "priority_score",
                    "effort_estimate", "rationale", "tradeoff_notes"):
            assert key in result

    def test_advisor_name_is_growth(self):
        assert self.advisor.evaluate(make_finding())["advisor"] == "growth"

    def test_profitability_affinity_and_domain_multiplier(self):
        finding = make_finding(dimension="profitability", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_marketing_affinity_and_domain_multiplier(self):
        finding = make_finding(dimension="marketing", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_onboarding_affinity_and_domain_multiplier(self):
        finding = make_finding(dimension="onboarding", severity="medium")
        result = self.advisor.evaluate(finding)
        # affinity=1.8, severity=12, domain_mult=1.5 → 32.4
        assert result["priority_score"] == pytest.approx(32.4, rel=1e-3)

    def test_copy_dim_no_domain_multiplier(self):
        finding = make_finding(dimension="copy", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=1.3, severity=25, domain_mult=1.0 → 32.5
        assert result["priority_score"] == pytest.approx(32.5, rel=1e-3)

    def test_tradeoff_notes_for_drill_quality(self):
        finding = make_finding(dimension="drill_quality")
        result = self.advisor.evaluate(finding)
        assert "growth" in result["tradeoff_notes"].lower() or "churn" in result["tradeoff_notes"].lower()

    def test_tradeoff_notes_for_content_dim(self):
        finding = make_finding(dimension="content")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] != ""

    def test_no_tradeoff_notes_for_profitability(self):
        finding = make_finding(dimension="profitability")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] == ""

    def test_low_severity_marketing(self):
        finding = make_finding(dimension="marketing", severity="low")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=5, domain_mult=1.5 → 15.0
        assert result["priority_score"] == pytest.approx(15.0, rel=1e-3)


# ---------------------------------------------------------------------------
# StabilityAdvisor
# ---------------------------------------------------------------------------

class TestStabilityAdvisor:

    def setup_method(self):
        self.advisor = StabilityAdvisor()

    def test_evaluate_returns_expected_keys(self):
        finding = make_finding(dimension="engineering")
        result = self.advisor.evaluate(finding)
        for key in ("advisor", "recommendation", "priority_score",
                    "effort_estimate", "rationale", "tradeoff_notes"):
            assert key in result

    def test_advisor_name_is_stability(self):
        assert self.advisor.evaluate(make_finding())["advisor"] == "stability"

    def test_engineering_affinity_and_domain_multiplier(self):
        finding = make_finding(dimension="engineering", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_security_affinity_and_domain_multiplier(self):
        finding = make_finding(dimension="security", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=25, domain_mult=1.5 → 75.0
        assert result["priority_score"] == pytest.approx(75.0, rel=1e-3)

    def test_critical_severity_doubles_domain_multiplier(self):
        finding = make_finding(dimension="timing", severity="critical")
        result = self.advisor.evaluate(finding)
        # affinity=1.8, severity=40, domain_mult=2.0 → 144.0
        assert result["priority_score"] == pytest.approx(144.0, rel=1e-3)

    def test_critical_severity_engineering_extreme_priority(self):
        finding = make_finding(dimension="engineering", severity="critical")
        result = self.advisor.evaluate(finding)
        # affinity=2.0, severity=40, domain_mult=2.0 → 160.0
        assert result["priority_score"] == pytest.approx(160.0, rel=1e-3)

    def test_critical_beats_high_significantly(self):
        high = make_finding(dimension="security", severity="high")
        crit = make_finding(dimension="security", severity="critical")
        high_score = self.advisor.evaluate(high)["priority_score"]
        crit_score = self.advisor.evaluate(crit)["priority_score"]
        assert crit_score > high_score * 2

    def test_platform_dim_no_critical_multiplier(self):
        finding = make_finding(dimension="platform", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=1.5, severity=25, domain_mult=1.0 (high, not critical) → 37.5
        assert result["priority_score"] == pytest.approx(37.5, rel=1e-3)

    def test_pm_dim_low_affinity(self):
        finding = make_finding(dimension="pm", severity="high")
        result = self.advisor.evaluate(finding)
        # affinity=1.0, severity=25, domain_mult=1.0 → 25.0
        assert result["priority_score"] == pytest.approx(25.0, rel=1e-3)

    def test_tradeoff_notes_for_profitability_dim(self):
        finding = make_finding(dimension="profitability")
        result = self.advisor.evaluate(finding)
        assert "stability" in result["tradeoff_notes"].lower() or "feature" in result["tradeoff_notes"].lower()

    def test_tradeoff_notes_for_marketing_dim(self):
        finding = make_finding(dimension="marketing")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] != ""

    def test_tradeoff_notes_for_onboarding_dim(self):
        finding = make_finding(dimension="onboarding")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] != ""

    def test_no_tradeoff_notes_for_engineering(self):
        finding = make_finding(dimension="engineering")
        result = self.advisor.evaluate(finding)
        assert result["tradeoff_notes"] == ""


# ---------------------------------------------------------------------------
# All advisors: shared contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("advisor_cls", [
    RetentionAdvisor, LearningAdvisor, GrowthAdvisor, StabilityAdvisor
])
class TestAdvisorContract:

    def test_returns_dict(self, advisor_cls):
        advisor = advisor_cls()
        result = advisor.evaluate(make_finding())
        assert isinstance(result, dict)

    def test_priority_score_is_positive_float(self, advisor_cls):
        advisor = advisor_cls()
        result = advisor.evaluate(make_finding())
        assert isinstance(result["priority_score"], float)
        assert result["priority_score"] > 0

    def test_effort_estimate_is_positive_float(self, advisor_cls):
        advisor = advisor_cls()
        result = advisor.evaluate(make_finding())
        assert isinstance(result["effort_estimate"], float)
        assert result["effort_estimate"] > 0

    def test_critical_scores_higher_than_low_same_dim(self, advisor_cls):
        advisor = advisor_cls()
        dim = list(advisor.affinities.keys())[0]
        low = advisor.evaluate(make_finding(dimension=dim, severity="low"))
        crit = advisor.evaluate(make_finding(dimension=dim, severity="critical"))
        assert crit["priority_score"] > low["priority_score"]

    def test_high_affinity_dim_beats_unknown_dim(self, advisor_cls):
        advisor = advisor_cls()
        high_aff_dim = max(advisor.affinities, key=advisor.affinities.get)
        known = advisor.evaluate(make_finding(dimension=high_aff_dim, severity="medium"))
        unknown = advisor.evaluate(make_finding(dimension="totally_unknown_dim", severity="medium"))
        assert known["priority_score"] > unknown["priority_score"]

    def test_rationale_is_nonempty_string(self, advisor_cls):
        advisor = advisor_cls()
        result = advisor.evaluate(make_finding())
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 0


# ---------------------------------------------------------------------------
# Mediator.resolve — consensus path (spread <= 30)
# ---------------------------------------------------------------------------

class TestMediatorResolveConsensus:

    def setup_method(self):
        self.mediator = Mediator()
        self.conn = make_conn()

    def test_returns_dict_with_required_keys(self):
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 40.0, "tradeoff_notes": ""},
            {"advisor": "learning", "priority_score": 38.0, "tradeoff_notes": ""},
            {"advisor": "growth", "priority_score": 35.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 32.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        for key in ("winning_advisor", "resolution_rationale", "tradeoff_summary", "priority"):
            assert key in result, f"Missing key: {key}"

    def test_consensus_selects_highest_weighted_score(self):
        # retention and learning weight=1.5; growth and stability weight=1.0
        # retention: 40 * 1.5 = 60 → winner
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 40.0, "tradeoff_notes": ""},
            {"advisor": "learning", "priority_score": 30.0, "tradeoff_notes": ""},
            {"advisor": "growth", "priority_score": 35.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 20.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        # Spread: 40 - 20 = 20 ≤ 30 → consensus path
        assert result["winning_advisor"] == "retention"

    def test_consensus_rationale_mentions_consensus(self):
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 40.0, "tradeoff_notes": ""},
            {"advisor": "learning", "priority_score": 38.0, "tradeoff_notes": ""},
            {"advisor": "growth", "priority_score": 35.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 32.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert "Consensus" in result["resolution_rationale"] or "consensus" in result["resolution_rationale"]

    def test_consensus_growth_wins_when_weighted_highest(self):
        # growth: 50 * 1.0 = 50; learning: 32 * 1.5 = 48 → growth wins
        # spread: 50 - 28 = 22 ≤ 30 → consensus
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 28.0, "tradeoff_notes": ""},
            {"advisor": "learning", "priority_score": 32.0, "tradeoff_notes": ""},
            {"advisor": "growth", "priority_score": 50.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 30.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert result["winning_advisor"] == "growth"

    def test_empty_opinions_returns_none_winner(self):
        finding = make_finding()
        result = self.mediator.resolve(self.conn, finding, [])
        assert result["winning_advisor"] is None
        assert result["priority"] == 0

    def test_single_opinion_always_wins(self):
        finding = make_finding()
        opinions = [{"advisor": "stability", "priority_score": 10.0, "tradeoff_notes": "note"}]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert result["winning_advisor"] == "stability"

    def test_priority_value_is_numeric(self):
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 40.0, "tradeoff_notes": ""},
            {"advisor": "learning", "priority_score": 38.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert isinstance(result["priority"], (int, float))
        assert result["priority"] > 0


# ---------------------------------------------------------------------------
# Mediator.resolve — conflict path (spread > 30)
# ---------------------------------------------------------------------------

class TestMediatorResolveConflict:

    def setup_method(self):
        self.mediator = Mediator()
        self.conn = make_conn()

    def _conflicting_opinions(self):
        # spread = 80 - 10 = 70 > 30 → conflict
        return [
            {"advisor": "retention", "priority_score": 80.0, "tradeoff_notes": "retention tradeoff"},
            {"advisor": "learning",  "priority_score": 10.0, "tradeoff_notes": "learning tradeoff"},
            {"advisor": "growth",    "priority_score": 15.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 12.0, "tradeoff_notes": "stability note"},
        ]

    def test_conflict_detected_and_weighted_vote_used(self):
        finding = make_finding()
        result = self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        assert "weighted vote" in result["resolution_rationale"].lower() or \
               "Conflict" in result["resolution_rationale"]

    def test_conflict_winner_has_highest_weighted_score(self):
        # retention: 80 * 1.5 = 120 → winner
        finding = make_finding()
        result = self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        assert result["winning_advisor"] == "retention"

    def test_conflict_tradeoff_summary_from_losers(self):
        finding = make_finding()
        result = self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        # Losers had "learning tradeoff" and "stability note"
        assert "learning tradeoff" in result["tradeoff_summary"] or \
               "stability note" in result["tradeoff_summary"]

    def test_conflict_tradeoff_summary_excludes_winner(self):
        finding = make_finding()
        result = self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        # Winner is retention; "retention tradeoff" should NOT appear in tradeoff_summary
        assert "retention tradeoff" not in result["tradeoff_summary"]

    def test_conflict_tradeoff_empty_when_no_loser_notes(self):
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 80.0, "tradeoff_notes": ""},
            {"advisor": "learning",  "priority_score": 10.0, "tradeoff_notes": ""},
            {"advisor": "growth",    "priority_score": 15.0, "tradeoff_notes": ""},
            {"advisor": "stability", "priority_score": 12.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert result["tradeoff_summary"] == ""

    def test_resolution_saved_to_db_when_finding_exists(self):
        finding = make_finding(dimension="retention", title="conflict test")
        insert_finding(self.conn, dimension="retention", title="conflict test")
        result = self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        row = self.conn.execute(
            "SELECT * FROM pi_advisor_resolution WHERE winning_advisor = ?",
            (result["winning_advisor"],)
        ).fetchone()
        assert row is not None
        assert row["winning_advisor"] == result["winning_advisor"]

    def test_resolution_not_saved_when_finding_missing_from_db(self):
        finding = make_finding(dimension="retention", title="not in db")
        # Don't insert into pi_finding
        before = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_resolution").fetchone()[0]
        self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        after = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_resolution").fetchone()[0]
        assert after == before

    def test_boundary_spread_exactly_30_is_consensus(self):
        # spread = 40 - 10 = 30 (not > 30) → consensus
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 40.0, "tradeoff_notes": ""},
            {"advisor": "learning",  "priority_score": 10.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert "Consensus" in result["resolution_rationale"] or "consensus" in result["resolution_rationale"]

    def test_boundary_spread_31_is_conflict(self):
        # spread = 41 - 10 = 31 > 30 → conflict
        finding = make_finding()
        opinions = [
            {"advisor": "retention", "priority_score": 41.0, "tradeoff_notes": ""},
            {"advisor": "learning",  "priority_score": 10.0, "tradeoff_notes": ""},
        ]
        result = self.mediator.resolve(self.conn, finding, opinions)
        assert "Conflict" in result["resolution_rationale"] or "weighted vote" in result["resolution_rationale"].lower()

    def test_resolved_finding_excluded_from_save(self):
        finding = make_finding(dimension="retention", title="resolved finding")
        insert_finding(self.conn, dimension="retention", title="resolved finding", status="resolved")
        before = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_resolution").fetchone()[0]
        self.mediator.resolve(self.conn, finding, self._conflicting_opinions())
        after = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_resolution").fetchone()[0]
        assert after == before


# ---------------------------------------------------------------------------
# Mediator.plan_sprint
# ---------------------------------------------------------------------------

class TestMediatorPlanSprint:

    def setup_method(self):
        self.mediator = Mediator()
        self.conn = make_conn()

    def test_returns_dict_with_required_keys(self):
        findings = [make_finding()]
        result = self.mediator.plan_sprint(self.conn, findings)
        for key in ("plan", "total_hours", "budget_hours", "remaining_hours", "deferred_count"):
            assert key in result

    def test_empty_findings_returns_empty_plan(self):
        result = self.mediator.plan_sprint(self.conn, [])
        assert result["plan"] == []
        assert result["total_hours"] == 0.0
        assert result["deferred_count"] == 0

    def test_plan_items_have_required_fields(self):
        findings = [make_finding(dimension="retention", severity="high")]
        result = self.mediator.plan_sprint(self.conn, findings)
        assert len(result["plan"]) > 0
        item = result["plan"][0]
        for field in ("title", "dimension", "severity", "priority",
                      "effort_hours", "winning_advisor", "tradeoff_summary", "files"):
            assert field in item, f"Missing field in plan item: {field}"

    def test_total_hours_does_not_exceed_budget(self):
        findings = [
            make_finding(title=f"finding {i}", files=["mandarin/scheduler.py"])
            for i in range(10)
        ]
        budget = 8.0
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=budget)
        assert result["total_hours"] <= budget

    def test_remaining_plus_total_equals_budget(self):
        findings = [make_finding(title="f1"), make_finding(title="f2")]
        budget = 20.0
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=budget)
        assert abs(result["remaining_hours"] + result["total_hours"] - budget) < 0.01

    def test_plan_ordered_by_priority_descending(self):
        # Use different severities/dimensions to ensure different priorities
        findings = [
            make_finding(dimension="copy", severity="low", title="low prio"),
            make_finding(dimension="retention", severity="critical", title="high prio"),
            make_finding(dimension="engineering", severity="medium", title="med prio"),
        ]
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=40.0)
        if len(result["plan"]) > 1:
            for i in range(len(result["plan"]) - 1):
                assert result["plan"][i]["priority"] >= result["plan"][i + 1]["priority"]

    def test_high_effort_finding_deferred_when_budget_tight(self):
        # schema_migration = 2.0 hours each; budget = 1.5 (investigation minimum)
        # A schema file finding has effort 2.0, which won't fit in 1.5
        finding = make_finding(files=["schema.sql"])
        result = self.mediator.plan_sprint(self.conn, [finding], weekly_budget_hours=1.0)
        assert result["deferred_count"] == 1
        assert len(result["plan"]) == 0

    def test_multiple_findings_fit_within_budget(self):
        findings = [
            make_finding(title=f"css fix {i}", files=["style.css"])
            for i in range(3)
        ]
        # Each css fix: effort = max(0.5, 1.5) = 1.5 (investigation floor)
        # 3 * 1.5 = 4.5 fits in 10.0
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=10.0)
        assert len(result["plan"]) == 3
        assert result["deferred_count"] == 0

    def test_deferred_count_correct(self):
        findings = [
            make_finding(title=f"big finding {i}", files=["schema.sql"])
            for i in range(5)
        ]
        # Each schema = 2.0h; budget 5.0 → 2 fit, 3 deferred
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=5.0)
        assert len(result["plan"]) + result["deferred_count"] == 5

    def test_dependency_hints_added_for_shared_files(self):
        shared_file = "mandarin/scheduler.py"
        findings = [
            make_finding(title="fix A", files=[shared_file]),
            make_finding(title="fix B", files=[shared_file]),
        ]
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=40.0)
        # The second item touching the same file should get a depends_on hint
        has_dep = any("depends_on" in item for item in result["plan"])
        assert has_dep

    def test_no_false_dependency_for_different_files(self):
        findings = [
            make_finding(title="fix A", files=["mandarin/scheduler.py"]),
            make_finding(title="fix B", files=["mandarin/web/routes.py"]),
        ]
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=40.0)
        for item in result["plan"]:
            assert "depends_on" not in item

    def test_default_budget_is_20_hours(self):
        result = self.mediator.plan_sprint(self.conn, [])
        assert result["budget_hours"] == 20.0

    def test_custom_budget_respected(self):
        result = self.mediator.plan_sprint(self.conn, [], weekly_budget_hours=12.5)
        assert result["budget_hours"] == 12.5

    def test_winning_advisor_present_in_each_plan_item(self):
        findings = [make_finding(dimension="engineering", severity="critical")]
        result = self.mediator.plan_sprint(self.conn, findings, weekly_budget_hours=40.0)
        for item in result["plan"]:
            assert item["winning_advisor"] is not None


# ---------------------------------------------------------------------------
# Mediator.evaluate_all
# ---------------------------------------------------------------------------

class TestMediatorEvaluateAll:

    def setup_method(self):
        self.mediator = Mediator()
        self.conn = make_conn()

    def test_returns_dict_keyed_by_title(self):
        findings = [make_finding(title="finding alpha")]
        result = self.mediator.evaluate_all(self.conn, findings)
        assert "finding alpha" in result

    def test_each_finding_has_four_opinions(self):
        findings = [make_finding(title="four advisors test")]
        result = self.mediator.evaluate_all(self.conn, findings)
        opinions = result["four advisors test"]
        assert len(opinions) == 4

    def test_all_four_advisor_names_present(self):
        findings = [make_finding(title="names test")]
        result = self.mediator.evaluate_all(self.conn, findings)
        advisor_names = {op["advisor"] for op in result["names test"]}
        assert advisor_names == {"retention", "learning", "growth", "stability"}

    def test_multiple_findings_all_included(self):
        findings = [
            make_finding(title="finding one"),
            make_finding(title="finding two"),
            make_finding(title="finding three"),
        ]
        result = self.mediator.evaluate_all(self.conn, findings)
        assert set(result.keys()) == {"finding one", "finding two", "finding three"}

    def test_empty_findings_returns_empty_dict(self):
        result = self.mediator.evaluate_all(self.conn, [])
        assert result == {}

    def test_opinions_saved_to_db_when_finding_in_db(self):
        finding = make_finding(dimension="retention", title="save test")
        insert_finding(self.conn, dimension="retention", title="save test")
        self.mediator.evaluate_all(self.conn, [finding])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM pi_advisor_opinion WHERE finding_id IN "
            "(SELECT id FROM pi_finding WHERE title = 'save test')"
        ).fetchone()[0]
        assert count == 4  # one per advisor

    def test_opinions_not_saved_when_finding_not_in_db(self):
        finding = make_finding(dimension="retention", title="not in db")
        before = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_opinion").fetchone()[0]
        self.mediator.evaluate_all(self.conn, [finding])
        after = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_opinion").fetchone()[0]
        assert after == before

    def test_opinions_have_correct_advisor_field(self):
        finding = make_finding(title="advisor field test")
        result = self.mediator.evaluate_all(self.conn, [finding])
        for op in result["advisor field test"]:
            assert op["advisor"] in {"retention", "learning", "growth", "stability"}

    def test_each_opinion_has_priority_score(self):
        finding = make_finding(title="score test")
        result = self.mediator.evaluate_all(self.conn, [finding])
        for op in result["score test"]:
            assert "priority_score" in op
            assert op["priority_score"] > 0

    def test_resolved_finding_excluded_from_opinion_save(self):
        finding = make_finding(dimension="retention", title="resolved finding")
        insert_finding(self.conn, dimension="retention", title="resolved finding", status="resolved")
        before = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_opinion").fetchone()[0]
        self.mediator.evaluate_all(self.conn, [finding])
        after = self.conn.execute("SELECT COUNT(*) FROM pi_advisor_opinion").fetchone()[0]
        assert after == before

    def test_duplicate_titles_last_active_finding_used(self):
        finding = make_finding(dimension="retention", title="dup title")
        # Insert two findings with same title, second is newer
        insert_finding(self.conn, dimension="retention", title="dup title")
        insert_finding(self.conn, dimension="retention", title="dup title")
        # Should not raise; saves opinions to the latest active finding
        self.mediator.evaluate_all(self.conn, [finding])

    def test_unknown_title_graceful(self):
        finding = {"title": None, "dimension": "retention", "severity": "low",
                   "files": [], "recommendation": ""}
        # Should not raise
        result = self.mediator.evaluate_all(self.conn, [finding])
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Affinity multiplier correctness: cross-advisor comparisons
# ---------------------------------------------------------------------------

class TestAffinityMultipliers:

    def test_retention_advisor_scores_retention_higher_than_engineering(self):
        advisor = RetentionAdvisor()
        ret = advisor.evaluate(make_finding(dimension="retention", severity="medium"))
        eng = advisor.evaluate(make_finding(dimension="engineering", severity="medium"))
        assert ret["priority_score"] > eng["priority_score"]

    def test_learning_advisor_scores_drill_quality_higher_than_marketing(self):
        advisor = LearningAdvisor()
        dq = advisor.evaluate(make_finding(dimension="drill_quality", severity="medium"))
        mkt = advisor.evaluate(make_finding(dimension="marketing", severity="medium"))
        assert dq["priority_score"] > mkt["priority_score"]

    def test_growth_advisor_scores_profitability_higher_than_engineering(self):
        advisor = GrowthAdvisor()
        prof = advisor.evaluate(make_finding(dimension="profitability", severity="medium"))
        eng = advisor.evaluate(make_finding(dimension="engineering", severity="medium"))
        assert prof["priority_score"] > eng["priority_score"]

    def test_stability_advisor_scores_security_higher_than_copy(self):
        advisor = StabilityAdvisor()
        sec = advisor.evaluate(make_finding(dimension="security", severity="medium"))
        copy_ = advisor.evaluate(make_finding(dimension="copy", severity="medium"))
        assert sec["priority_score"] > copy_["priority_score"]

    def test_each_advisor_has_at_least_one_strong_affinity_dim(self):
        for advisor in _ADVISORS:
            max_aff = max(advisor.affinities.values())
            assert max_aff >= 1.5, f"{advisor.name} has no strong affinity dim"

    def test_affinity_constants_match_advisor_attributes(self):
        assert RetentionAdvisor().affinities == _ADVISOR_AFFINITIES["retention"]
        assert LearningAdvisor().affinities  == _ADVISOR_AFFINITIES["learning"]
        assert GrowthAdvisor().affinities    == _ADVISOR_AFFINITIES["growth"]
        assert StabilityAdvisor().affinities == _ADVISOR_AFFINITIES["stability"]


# ---------------------------------------------------------------------------
# Severity score table
# ---------------------------------------------------------------------------

class TestSeverityScores:

    def test_critical_is_highest(self):
        assert _SEVERITY_SCORES["critical"] > _SEVERITY_SCORES["high"]

    def test_high_greater_than_medium(self):
        assert _SEVERITY_SCORES["high"] > _SEVERITY_SCORES["medium"]

    def test_medium_greater_than_low(self):
        assert _SEVERITY_SCORES["medium"] > _SEVERITY_SCORES["low"]

    def test_all_four_severity_levels_defined(self):
        for level in ("critical", "high", "medium", "low"):
            assert level in _SEVERITY_SCORES

    def test_score_propagates_correctly_through_evaluate(self):
        advisor = RetentionAdvisor()
        # affinity for unknown dim = 0.5, no domain mult
        crit = advisor.evaluate(make_finding(dimension="unknown_dim", severity="critical"))
        high = advisor.evaluate(make_finding(dimension="unknown_dim", severity="high"))
        med  = advisor.evaluate(make_finding(dimension="unknown_dim", severity="medium"))
        low  = advisor.evaluate(make_finding(dimension="unknown_dim", severity="low"))
        assert crit["priority_score"] > high["priority_score"] > med["priority_score"] > low["priority_score"]

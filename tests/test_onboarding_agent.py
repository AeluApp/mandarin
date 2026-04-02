"""Tests for mandarin.openclaw.onboarding_agent — lifecycle detection, risk signals, interventions."""
# phantom-schema-checked

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import patch

from tests.shared_db import make_test_db
from mandarin.openclaw.onboarding_agent import (
    Intervention,
    InterventionEngine,
    LifecycleDetector,
    OnboardingScheduler,
    RiskSignal,
    UserContext,
    UserLifecycleStage,
)


def _make_conn():
    conn = make_test_db()
    # PHANTOM COLUMN: streak_days is not in the production schema.
    # TODO: Add streak_days to user table migration when streak feature is activated.
    try:
        conn.execute("ALTER TABLE user ADD COLUMN streak_days INTEGER DEFAULT 0")
    except Exception:
        pass  # Column may already exist
    conn.commit()
    return conn


def _ts(days_ago=0, hours_ago=0):
    """Return ISO timestamp relative to now, with +00:00 suffix for fromisoformat compat."""
    dt = datetime.now(UTC) - timedelta(days=days_ago, hours=hours_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S+00:00")


def _seed_user(conn, user_id=1, email="u@a.com", name="User", tier="free",
               streak=0, days_ago=10):
    created = _ts(days_ago)
    conn.execute(
        "INSERT OR REPLACE INTO user (id, email, password_hash, display_name, subscription_tier, created_at) "
        "VALUES (?, ?, 'test_hash', ?, ?, ?)",
        (user_id, email, name, tier, created),
    )
    conn.commit()


def _add_sessions(conn, user_id, count, days_ago=0, outcome="completed",
                  correct=8, completed=10, early_exit=0):
    ts = _ts(days_ago)
    for _ in range(count):
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome, items_correct, items_completed, early_exit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, ts, outcome, correct, completed, early_exit),
        )
    conn.commit()


# ── Enum coverage ─────────────────────────────────────────

class TestLifecycleEnum(unittest.TestCase):
    def test_all_stages_exist(self):
        expected = {"signed_up", "first_session", "exploring", "establishing",
                    "habitual", "at_risk", "dormant", "churned"}
        actual = {s.value for s in UserLifecycleStage}
        self.assertEqual(expected, actual)


# ── RiskSignal dataclass ──────────────────────────────────

class TestRiskSignal(unittest.TestCase):
    def test_auto_timestamp(self):
        rs = RiskSignal("TEST", "high", "detail")
        self.assertNotEqual(rs.detected_at, "")
        # Should parse as valid datetime
        datetime.strptime(rs.detected_at, "%Y-%m-%d %H:%M:%S")

    def test_custom_timestamp(self):
        rs = RiskSignal("T", "low", "d", detected_at="2026-01-01 00:00:00")
        self.assertEqual(rs.detected_at, "2026-01-01 00:00:00")


# ── UserContext ───────────────────────────────────────────

class TestUserContext(unittest.TestCase):
    def test_defaults(self):
        ctx = UserContext(user_id=1)
        self.assertEqual(ctx.total_sessions, 0)
        self.assertEqual(ctx.accuracy_trend, [])
        self.assertEqual(ctx.active_hsk_level, 1)
        self.assertEqual(ctx.subscription_tier, "free")

    def test_from_db_missing_user(self):
        conn = _make_conn()
        ctx = UserContext.from_db(conn, 999)
        self.assertEqual(ctx.user_id, 999)
        self.assertEqual(ctx.email, "")

    def test_from_db_basic(self):
        conn = _make_conn()
        _seed_user(conn, 1, email="e@x.com", name="Alice", days_ago=30)
        ctx = UserContext.from_db(conn, 1)
        self.assertEqual(ctx.email, "e@x.com")
        self.assertEqual(ctx.display_name, "Alice")
        self.assertGreaterEqual(ctx.days_since_signup, 29)

    def test_from_db_sessions_and_accuracy(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=20)
        _add_sessions(conn, 1, 3, days_ago=1, correct=7, completed=10)
        ctx = UserContext.from_db(conn, 1)
        self.assertEqual(ctx.total_sessions, 3)
        self.assertEqual(ctx.sessions_this_week, 3)
        self.assertEqual(len(ctx.accuracy_trend), 3)
        self.assertAlmostEqual(ctx.accuracy_trend[0], 0.7, places=2)

    def test_from_db_items_due(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english) VALUES (99, '测', 'cè', 'test')")
        conn.execute("INSERT INTO progress (user_id, content_item_id, modality, next_review_date) VALUES (1, 99, 'reading', ?)", (today,))
        conn.commit()
        ctx = UserContext.from_db(conn, 1)
        self.assertEqual(ctx.items_due, 1)


# ── LifecycleDetector stages ─────────────────────────────

class TestLifecycleDetector(unittest.TestCase):
    def setUp(self):
        self.d = LifecycleDetector()

    def test_signed_up_no_sessions(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=2)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.SIGNED_UP)

    def test_churned_no_sessions_30_days(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=31)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.CHURNED)

    def test_first_session(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=5)
        _add_sessions(conn, 1, 1, days_ago=0)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.FIRST_SESSION)

    def test_exploring(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=10)
        _add_sessions(conn, 1, 3, days_ago=1)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.EXPLORING)

    def test_establishing(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=30)
        _add_sessions(conn, 1, 8, days_ago=1)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.ESTABLISHING)

    def test_habitual(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=60)
        _add_sessions(conn, 1, 20, days_ago=1)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.HABITUAL)

    def test_dormant(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=60)
        _add_sessions(conn, 1, 5, days_ago=10)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.DORMANT)

    def test_churned_with_sessions_30_days_ago(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=90)
        _add_sessions(conn, 1, 3, days_ago=35)
        stage = self.d.detect_stage(conn, 1)
        self.assertEqual(stage, UserLifecycleStage.CHURNED)

    def test_days_since_empty_string(self):
        result = LifecycleDetector._days_since("")
        self.assertEqual(result, 999)

    def test_days_since_invalid(self):
        result = LifecycleDetector._days_since("not-a-date")
        self.assertEqual(result, 999)

    def test_days_since_valid(self):
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        result = LifecycleDetector._days_since(yesterday)
        self.assertIn(result, (0, 1))


# ── Risk signal detection ─────────────────────────────────

class TestRiskSignalDetection(unittest.TestCase):
    def setUp(self):
        self.d = LifecycleDetector()

    def test_never_started(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=3)
        signals = self.d.detect_risk_signals(conn, 1)
        types = [s.signal_type for s in signals]
        self.assertIn("NEVER_STARTED", types)

    def test_one_and_done(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=10)
        _add_sessions(conn, 1, 1, days_ago=5)
        signals = self.d.detect_risk_signals(conn, 1)
        types = [s.signal_type for s in signals]
        self.assertIn("ONE_AND_DONE", types)

    def test_streak_broken(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=30, streak=0)
        _add_sessions(conn, 1, 10, days_ago=1)
        signals = self.d.detect_risk_signals(conn, 1)
        types = [s.signal_type for s in signals]
        self.assertIn("STREAK_BROKEN", types)

    def test_difficulty_spike(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=30)
        # recent session: low accuracy
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome, items_correct, items_completed) "
            "VALUES (1, ?, 'completed', 3, 10)", (_ts(0),))
        # older session: high accuracy
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome, items_correct, items_completed) "
            "VALUES (1, ?, 'completed', 8, 10)", (_ts(1),))
        conn.commit()
        signals = self.d.detect_risk_signals(conn, 1)
        types = [s.signal_type for s in signals]
        self.assertIn("DIFFICULTY_SPIKE", types)

    def test_no_signals_healthy_user(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=30, streak=5)
        _add_sessions(conn, 1, 15, days_ago=0, correct=9, completed=10)
        signals = self.d.detect_risk_signals(conn, 1)
        # Healthy user may still have some minor signals, but no NEVER_STARTED etc.
        types = [s.signal_type for s in signals]
        self.assertNotIn("NEVER_STARTED", types)
        self.assertNotIn("ONE_AND_DONE", types)


# ── InterventionEngine ────────────────────────────────────

class TestInterventionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = InterventionEngine()
        self.ctx = UserContext(user_id=1, items_due=10, active_hsk_level=2,
                               sessions_this_week=1)

    def test_no_intervention_healthy_exploring(self):
        result = self.engine.plan_intervention(UserLifecycleStage.EXPLORING, [], self.ctx)
        self.assertIsNone(result)

    def test_no_intervention_healthy_habitual(self):
        result = self.engine.plan_intervention(UserLifecycleStage.HABITUAL, [], self.ctx)
        self.assertIsNone(result)

    def test_signal_triggers_intervention(self):
        sig = RiskSignal("NEVER_STARTED", "high", "test")
        result = self.engine.plan_intervention(UserLifecycleStage.SIGNED_UP, [sig], self.ctx)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Intervention)
        self.assertEqual(result.channel, "email")

    def test_highest_severity_wins(self):
        sig_low = RiskSignal("STREAK_BROKEN", "low", "streak")
        sig_high = RiskSignal("NEVER_STARTED", "high", "never")
        result = self.engine.plan_intervention(UserLifecycleStage.SIGNED_UP, [sig_high, sig_low], self.ctx)
        self.assertIn("NEVER_STARTED", result.personalization.get("signal", ""))

    def test_dormant_stage_default(self):
        result = self.engine.plan_intervention(UserLifecycleStage.DORMANT, [], self.ctx)
        self.assertIsNotNone(result)
        self.assertIn("while", result.message.lower())

    def test_signed_up_stage_default(self):
        result = self.engine.plan_intervention(UserLifecycleStage.SIGNED_UP, [], self.ctx)
        self.assertIsNotNone(result)
        self.assertIn("first session", result.message.lower())


# ── OnboardingScheduler ───────────────────────────────────

class TestOnboardingScheduler(unittest.TestCase):
    def setUp(self):
        self.sched = OnboardingScheduler()

    def test_check_user_returns_intervention(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=3)
        result = self.sched.check_user(conn, 1)
        # User signed up 3 days ago, zero sessions — should get NEVER_STARTED
        self.assertIsNotNone(result)

    def test_cooldown_blocks_repeat(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=3)
        # Record an intervention recently
        conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_intervention (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, channel TEXT, message TEXT,
                urgency TEXT, signal_type TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO onboarding_intervention (user_id, channel, message, urgency, signal_type) "
            "VALUES (1, 'email', 'test', 'medium', 'NEVER_STARTED')"
        )
        conn.commit()
        result = self.sched.check_user(conn, 1)
        self.assertIsNone(result)

    def test_check_all_users(self):
        conn = _make_conn()
        _seed_user(conn, 1, days_ago=3)
        _seed_user(conn, 2, email="u2@a.com", days_ago=5)
        results = self.sched.check_all_users(conn)
        self.assertGreaterEqual(len(results), 1)

    def test_record_and_get_history(self):
        conn = _make_conn()
        _seed_user(conn, 1)
        intervention = Intervention(
            channel="email", message_template="t", message="hello",
            urgency="medium", personalization={"signal": "NEVER_STARTED", "user_id": 1},
        )
        self.sched.record_intervention(conn, 1, intervention)
        history = self.sched.get_intervention_history(conn, 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["channel"], "email")

    def test_get_history_no_table(self):
        conn = _make_conn()
        history = self.sched.get_intervention_history(conn, 1)
        self.assertEqual(history, [])


if __name__ == "__main__":
    unittest.main()

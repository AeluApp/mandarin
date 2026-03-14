"""Adaptive onboarding + churn prevention agent.

Watches new user behavior, detects when someone is stuck/inactive/abandoning,
and intervenes with the right message at the right moment. This is retention
disguised as onboarding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class UserLifecycleStage(Enum):
    SIGNED_UP = "signed_up"
    FIRST_SESSION = "first_session"
    EXPLORING = "exploring"
    ESTABLISHING = "establishing"
    HABITUAL = "habitual"
    AT_RISK = "at_risk"
    DORMANT = "dormant"
    CHURNED = "churned"


@dataclass
class RiskSignal:
    signal_type: str
    severity: str  # low, medium, high
    detail: str
    detected_at: str = ""

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class UserContext:
    user_id: int
    email: str = ""
    display_name: str = ""
    days_since_signup: int = 0
    total_sessions: int = 0
    sessions_this_week: int = 0
    last_session_date: str = ""
    streak_days: int = 0
    accuracy_trend: list[float] = field(default_factory=list)
    active_hsk_level: int = 1
    items_due: int = 0
    subscription_tier: str = "free"

    @classmethod
    def from_db(cls, conn, user_id: int) -> "UserContext":
        user = conn.execute(
            "SELECT email, display_name, created_at, subscription_tier, streak_days FROM user WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            return cls(user_id=user_id)

        age = 0
        if user["created_at"]:
            try:
                created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - created).days
            except (ValueError, TypeError):
                pass

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ? AND session_outcome = 'completed'",
            (user_id,),
        ).fetchone()

        week = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ? AND session_outcome = 'completed'
            AND started_at >= datetime('now', '-7 days')
        """, (user_id,)).fetchone()

        last = conn.execute(
            "SELECT started_at FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        # Accuracy trend (last 5 sessions)
        recent = conn.execute("""
            SELECT items_correct, items_completed FROM session_log
            WHERE user_id = ? AND session_outcome = 'completed' AND items_completed > 0
            ORDER BY started_at DESC LIMIT 5
        """, (user_id,)).fetchall()
        trend = [round(r["items_correct"] / r["items_completed"], 3) for r in recent if r["items_completed"]]

        due = conn.execute(
            "SELECT COUNT(*) as cnt FROM progress WHERE user_id = ? AND next_review_date <= date('now')",
            (user_id,),
        ).fetchone()

        return cls(
            user_id=user_id,
            email=user["email"] or "",
            display_name=user["display_name"] or "",
            days_since_signup=age,
            total_sessions=total["cnt"] if total else 0,
            sessions_this_week=week["cnt"] if week else 0,
            last_session_date=last["started_at"] if last else "",
            streak_days=user["streak_days"] if "streak_days" in user.keys() else 0,
            accuracy_trend=trend,
            items_due=due["cnt"] if due else 0,
            subscription_tier=user["subscription_tier"] or "free",
        )


class LifecycleDetector:
    """Detect user lifecycle stage and risk signals."""

    def detect_stage(self, conn, user_id: int) -> UserLifecycleStage:
        ctx = UserContext.from_db(conn, user_id)
        return self._stage_from_context(ctx)

    def _stage_from_context(self, ctx: UserContext) -> UserLifecycleStage:
        if ctx.total_sessions == 0:
            if ctx.days_since_signup >= 30:
                return UserLifecycleStage.CHURNED
            return UserLifecycleStage.SIGNED_UP

        days_since_last = self._days_since(ctx.last_session_date)

        if days_since_last >= 30:
            return UserLifecycleStage.CHURNED
        if days_since_last >= 7:
            return UserLifecycleStage.DORMANT

        if ctx.total_sessions == 1:
            return UserLifecycleStage.FIRST_SESSION
        if ctx.total_sessions <= 5:
            if ctx.sessions_this_week == 0 and days_since_last >= 3:
                return UserLifecycleStage.AT_RISK
            return UserLifecycleStage.EXPLORING
        if ctx.total_sessions <= 14:
            if ctx.sessions_this_week == 0:
                return UserLifecycleStage.AT_RISK
            return UserLifecycleStage.ESTABLISHING

        # 15+ sessions
        if ctx.sessions_this_week == 0 and days_since_last >= 3:
            return UserLifecycleStage.AT_RISK
        return UserLifecycleStage.HABITUAL

    def detect_risk_signals(self, conn, user_id: int) -> list[RiskSignal]:
        ctx = UserContext.from_db(conn, user_id)
        signals = []

        # NEVER_STARTED
        if ctx.total_sessions == 0 and ctx.days_since_signup >= 1:
            signals.append(RiskSignal("NEVER_STARTED", "high",
                                      f"Signed up {ctx.days_since_signup} days ago, zero sessions"))

        # ABANDONED_SETUP
        incomplete = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ? AND session_outcome != 'completed'
            AND (SELECT COUNT(*) FROM session_log WHERE user_id = ? AND session_outcome = 'completed') = 0
        """, (user_id, user_id)).fetchone()
        if incomplete and incomplete["cnt"] > 0:
            signals.append(RiskSignal("ABANDONED_SETUP", "high",
                                      "Started session but never completed one"))

        # ONE_AND_DONE
        days_since_last = self._days_since(ctx.last_session_date)
        if ctx.total_sessions == 1 and days_since_last >= 2:
            signals.append(RiskSignal("ONE_AND_DONE", "medium",
                                      f"Completed 1 session, {days_since_last} days since"))

        # DECLINING_FREQUENCY
        if ctx.total_sessions >= 5:
            prev_week = conn.execute("""
                SELECT COUNT(*) as cnt FROM session_log
                WHERE user_id = ? AND session_outcome = 'completed'
                AND started_at >= datetime('now', '-14 days')
                AND started_at < datetime('now', '-7 days')
            """, (user_id,)).fetchone()
            prev = prev_week["cnt"] if prev_week else 0
            if prev > 0 and ctx.sessions_this_week < prev * 0.5:
                signals.append(RiskSignal("DECLINING_FREQUENCY", "medium",
                                          f"Sessions dropped from {prev}/week to {ctx.sessions_this_week}/week"))

        # DECLINING_ACCURACY
        if len(ctx.accuracy_trend) >= 3:
            if all(ctx.accuracy_trend[i] < ctx.accuracy_trend[i + 1]
                   for i in range(min(3, len(ctx.accuracy_trend) - 1))):
                signals.append(RiskSignal("DECLINING_ACCURACY", "medium",
                                          f"Accuracy trending down: {[round(a, 2) for a in ctx.accuracy_trend[:4]]}"))

        # INCREASING_EARLY_EXITS
        early = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ? AND early_exit = 1
            AND started_at >= datetime('now', '-7 days')
        """, (user_id,)).fetchone()
        total_week = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = ? AND started_at >= datetime('now', '-7 days')
        """, (user_id,)).fetchone()
        if total_week and total_week["cnt"] >= 3:
            early_rate = (early["cnt"] if early else 0) / total_week["cnt"]
            if early_rate > 0.5:
                signals.append(RiskSignal("INCREASING_EARLY_EXITS", "medium",
                                          f"{early['cnt']}/{total_week['cnt']} sessions ended early this week"))

        # LONG_GAP
        if ctx.total_sessions >= 3 and days_since_last >= 5:
            signals.append(RiskSignal("LONG_GAP", "medium",
                                      f"{days_since_last} days since last session"))

        # STREAK_BROKEN
        if ctx.streak_days == 0 and ctx.total_sessions >= 7:
            signals.append(RiskSignal("STREAK_BROKEN", "low",
                                      "Had a streak, now broken"))

        # DIFFICULTY_SPIKE
        if len(ctx.accuracy_trend) >= 2 and ctx.accuracy_trend[0] < 0.4 and ctx.accuracy_trend[1] > 0.6:
            signals.append(RiskSignal("DIFFICULTY_SPIKE", "medium",
                                      f"Accuracy dropped from {ctx.accuracy_trend[1]:.0%} to {ctx.accuracy_trend[0]:.0%}"))

        return signals

    @staticmethod
    def _days_since(date_str: str) -> int:
        if not date_str:
            return 999
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except (ValueError, TypeError):
            return 999


@dataclass
class Intervention:
    channel: str  # email, push, in_app
    message_template: str
    message: str
    urgency: str  # low, medium, high
    delay_hours: int = 0
    personalization: dict = field(default_factory=dict)


# ── Message templates ─────────────────────────────────────

_TEMPLATES = {
    "NEVER_STARTED": {
        "channel": "email", "urgency": "medium", "delay_hours": 0,
        "template": "Your first session is ready whenever you are. It takes about 5 minutes.",
    },
    "ABANDONED_SETUP": {
        "channel": "email", "urgency": "medium", "delay_hours": 4,
        "template": "Looks like your first session got interrupted. No worries — it picks up right where you left off.",
    },
    "ONE_AND_DONE": {
        "channel": "email", "urgency": "medium", "delay_hours": 12,
        "template": "You started learning {first_items}. Your second session picks up right where you left off.",
    },
    "DECLINING_FREQUENCY": {
        "channel": "push", "urgency": "low", "delay_hours": 0,
        "template": "You've been studying {pattern}. Even a 2-minute session keeps momentum.",
    },
    "DECLINING_ACCURACY": {
        "channel": "in_app", "urgency": "low", "delay_hours": 0,
        "template": "Some items are harder right now — that's part of learning. The scheduler is adjusting to give you more practice on these.",
    },
    "INCREASING_EARLY_EXITS": {
        "channel": "in_app", "urgency": "low", "delay_hours": 0,
        "template": "Sessions feeling too long? Try a mini session — just 90 seconds of focused review.",
    },
    "LONG_GAP": {
        "channel": "email", "urgency": "medium", "delay_hours": 0,
        "template": "Welcome back. We adjusted your schedule to account for the gap — no penalty, just a fresh start. {due_count} items are ready for review.",
    },
    "STREAK_BROKEN": {
        "channel": "push", "urgency": "low", "delay_hours": 0,
        "template": "Streaks restart — what matters is coming back. {due_count} items are ready for review.",
    },
    "DIFFICULTY_SPIKE": {
        "channel": "in_app", "urgency": "low", "delay_hours": 0,
        "template": "HSK {level} is harder — that's normal. Your accuracy will recover as these items cycle back.",
    },
    "DORMANT_RETURN": {
        "channel": "email", "urgency": "medium", "delay_hours": 0,
        "template": "It's been a while. Your progress is saved — pick up whenever you're ready. {due_count} items waiting.",
    },
}


class InterventionEngine:
    """Plan interventions based on lifecycle stage and risk signals."""

    def plan_intervention(
        self, stage: UserLifecycleStage, signals: list[RiskSignal], context: UserContext
    ) -> Optional[Intervention]:
        if not signals and stage in (
            UserLifecycleStage.EXPLORING,
            UserLifecycleStage.ESTABLISHING,
            UserLifecycleStage.HABITUAL,
        ):
            return None

        # Pick highest severity signal
        if signals:
            signals_sorted = sorted(signals, key=lambda s: {"high": 0, "medium": 1, "low": 2}.get(s.severity, 3))
            top = signals_sorted[0]
            tmpl_data = _TEMPLATES.get(top.signal_type)
            if not tmpl_data:
                if stage == UserLifecycleStage.DORMANT:
                    tmpl_data = _TEMPLATES["DORMANT_RETURN"]
                else:
                    return None

            message = tmpl_data["template"].format(
                first_items="your vocabulary items",
                pattern=f"{context.sessions_this_week} sessions this week",
                due_count=context.items_due,
                level=context.active_hsk_level,
            )

            return Intervention(
                channel=tmpl_data["channel"],
                message_template=tmpl_data["template"],
                message=message,
                urgency=tmpl_data["urgency"],
                delay_hours=tmpl_data["delay_hours"],
                personalization={"signal": top.signal_type, "user_id": context.user_id},
            )

        # Stage-based defaults
        if stage == UserLifecycleStage.SIGNED_UP:
            tmpl = _TEMPLATES["NEVER_STARTED"]
            return Intervention(
                channel=tmpl["channel"], message_template=tmpl["template"],
                message=tmpl["template"], urgency=tmpl["urgency"],
            )
        if stage == UserLifecycleStage.DORMANT:
            tmpl = _TEMPLATES["DORMANT_RETURN"]
            msg = tmpl["template"].format(due_count=context.items_due)
            return Intervention(
                channel=tmpl["channel"], message_template=tmpl["template"],
                message=msg, urgency=tmpl["urgency"],
            )

        return None


class OnboardingScheduler:
    """Scan users and plan interventions."""

    def __init__(self):
        self.detector = LifecycleDetector()
        self.engine = InterventionEngine()

    def check_user(self, conn, user_id: int) -> Optional[Intervention]:
        if not self._cooldown_check(conn, user_id):
            return None

        stage = self.detector.detect_stage(conn, user_id)
        signals = self.detector.detect_risk_signals(conn, user_id)
        context = UserContext.from_db(conn, user_id)
        return self.engine.plan_intervention(stage, signals, context)

    def check_all_users(self, conn) -> list[Intervention]:
        users = conn.execute("SELECT id FROM user").fetchall()
        interventions = []
        for u in users:
            intervention = self.check_user(conn, u["id"])
            if intervention:
                interventions.append(intervention)
        return interventions

    def _cooldown_check(self, conn, user_id: int) -> bool:
        """Don't message same user within 48h."""
        try:
            recent = conn.execute("""
                SELECT COUNT(*) as cnt FROM onboarding_intervention
                WHERE user_id = ? AND created_at >= datetime('now', '-48 hours')
            """, (user_id,)).fetchone()
            return (recent["cnt"] if recent else 0) == 0
        except Exception:
            return True  # Table doesn't exist yet = no previous interventions

    def record_intervention(self, conn, user_id: int, intervention: Intervention):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_intervention (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, channel TEXT, message TEXT,
                urgency TEXT, signal_type TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        signal = intervention.personalization.get("signal", "")
        conn.execute(
            "INSERT INTO onboarding_intervention (user_id, channel, message, urgency, signal_type) VALUES (?, ?, ?, ?, ?)",
            (user_id, intervention.channel, intervention.message, intervention.urgency, signal),
        )
        conn.commit()

    def get_intervention_history(self, conn, user_id: int) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT * FROM onboarding_intervention WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

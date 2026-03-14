"""Customer support automation — handle 80% of common questions, escalate the rest.

Built-in FAQ knowledge base covers account, billing, learning, technical, and privacy.
DB-connected troubleshooting for personalized diagnostics. Escalation routing
with full context for the 20% that needs human attention.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────

@dataclass
class SupportContext:
    user_id: int
    user_email: str = ""
    subscription_tier: str = "free"
    account_age_days: int = 0
    total_sessions: int = 0
    last_session_date: str = ""
    streak_days: int = 0
    platform: str = ""
    recent_crashes: int = 0
    recent_client_errors: int = 0

    @classmethod
    def from_user(cls, conn, user_id: int) -> "SupportContext":
        user = conn.execute(
            "SELECT email, subscription_tier, created_at FROM user WHERE id = ?",
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

        sessions = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ?", (user_id,)
        ).fetchone()

        last = conn.execute(
            "SELECT started_at FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        streak = 0
        try:
            u = conn.execute("SELECT streak_days FROM user WHERE id = ?", (user_id,)).fetchone()
            streak = u["streak_days"] if u and "streak_days" in u.keys() else 0
        except Exception:
            pass

        crashes = 0
        try:
            c = conn.execute(
                "SELECT COUNT(*) as cnt FROM crash_log WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()
            crashes = c["cnt"] if c else 0
        except Exception:
            pass

        client_errors = 0
        try:
            ce = conn.execute(
                "SELECT COUNT(*) as cnt FROM client_error_log WHERE user_id = ? AND created_at >= datetime('now', '-7 days')",
                (user_id,),
            ).fetchone()
            client_errors = ce["cnt"] if ce else 0
        except Exception:
            pass

        return cls(
            user_id=user_id,
            user_email=user["email"] or "",
            subscription_tier=user["subscription_tier"] or "free",
            account_age_days=age,
            total_sessions=sessions["cnt"] if sessions else 0,
            last_session_date=last["started_at"] if last else "",
            streak_days=streak,
            recent_crashes=crashes,
            recent_client_errors=client_errors,
        )


@dataclass
class SupportResponse:
    answer: str
    confidence: float
    category: str
    escalate: bool = False
    context: Optional[SupportContext] = None
    suggested_actions: list[str] = field(default_factory=list)


# ── FAQ knowledge base ────────────────────────────────────

_FAQ_ENTRIES = [
    # Account
    {"category": "account", "patterns": [r"reset.*password", r"forgot.*password", r"can't.*log\s*in"],
     "answer": "You can reset your password at the login page — tap 'Forgot password' and we'll send a reset link to your email. If you don't receive it within a few minutes, check your spam folder.",
     "requires_db": False},
    {"category": "account", "patterns": [r"change.*email", r"update.*email"],
     "answer": "To change your email address, go to Settings in the app, then tap your email to edit it. You'll need to verify the new address before it takes effect.",
     "requires_db": False},
    {"category": "account", "patterns": [r"delete.*account", r"remove.*account", r"close.*account"],
     "answer": "You can request account deletion from Settings > Privacy > Delete Account. This permanently removes all your learning data. We'll process the request within 30 days as required by our privacy policy.",
     "requires_db": False},
    {"category": "account", "patterns": [r"export.*data", r"download.*data", r"my.*data"],
     "answer": "You can export your learning data from Settings > Privacy > Export Data. This generates a JSON file with your progress, session history, and learning statistics.",
     "requires_db": False},
    {"category": "account", "patterns": [r"two.?factor", r"2fa", r"mfa", r"authenticator"],
     "answer": "You can enable two-factor authentication from Settings > Security > Enable 2FA. We support any TOTP authenticator app (Google Authenticator, Authy, etc.).",
     "requires_db": False},
    {"category": "account", "patterns": [r"change.*name", r"display.*name", r"username"],
     "answer": "You can change your display name in Settings > Profile. This name appears in class reports if you're in a classroom.",
     "requires_db": False},

    # Billing
    {"category": "billing", "patterns": [r"subscription.*plan", r"pricing", r"how much", r"cost"],
     "answer": "Aelu offers a free tier with core features, a Pro plan ($9/month) with full content and analytics, and an Institutional plan for classrooms. Visit the Pricing page for full details.",
     "requires_db": False},
    {"category": "billing", "patterns": [r"cancel.*subscription", r"unsubscribe", r"stop.*paying"],
     "answer": "You can cancel your subscription from Settings > Subscription > Cancel. You'll keep access until the end of your current billing period. No partial refunds, but no further charges either.",
     "requires_db": False},
    {"category": "billing", "patterns": [r"refund", r"money.*back", r"charge.*wrong"],
     "answer": "For refund requests, we review each case individually. If your charge was within the last 7 days, we can typically process a full refund. Please include your account email and the charge date.",
     "requires_db": True},
    {"category": "billing", "patterns": [r"payment.*fail", r"card.*decline", r"billing.*error"],
     "answer": "Payment failures usually happen when a card expires or has insufficient funds. Go to Settings > Subscription > Update Payment Method to try a different card. If the issue persists, your bank may be blocking the charge.",
     "requires_db": True},
    {"category": "billing", "patterns": [r"receipt", r"invoice", r"tax"],
     "answer": "Receipts are emailed automatically after each payment. You can also find them in Settings > Subscription > Billing History. Each receipt includes the information needed for tax purposes.",
     "requires_db": False},
    {"category": "billing", "patterns": [r"free.*trial", r"trial.*period"],
     "answer": "Aelu's free tier isn't a trial — it's permanent. You get core drill types and HSK 1-3 vocabulary forever. Pro unlocks HSK 4-9, advanced drills, speaking practice, and full analytics.",
     "requires_db": False},

    # Learning
    {"category": "learning", "patterns": [r"reset.*level", r"start.*over", r"restart"],
     "answer": "You can reset your progress from Settings > Learning > Reset Progress. This is permanent — all mastery data will be cleared. Consider using a Calibration session instead if you just want to re-assess your level.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"word.*came.*back", r"why.*reviewing", r"already.*know"],
     "answer": "Aelu uses spaced repetition — words come back at increasing intervals to strengthen long-term memory. If a word keeps appearing, it means the system detected some uncertainty in your recent answers. This is working as intended.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"session.*type", r"difference.*session", r"mini.*session"],
     "answer": "Standard sessions adapt to your day (shorter on busy days, longer on weekends). Mini sessions are 90 seconds for quick review. Catch-up sessions focus on weak spots. Calibration sessions help assess your level.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"accuracy.*mean", r"what.*percentage", r"score.*mean"],
     "answer": "Accuracy shows the percentage of correct answers in a session or over time. Anything above 70% means you're progressing well. Below 50% means items are too hard — the scheduler will adjust automatically.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"streak.*freeze", r"missed.*day", r"break.*streak"],
     "answer": "Streak freezes protect your streak when you miss a day. You earn freezes by maintaining a 7-day streak (max 2 saved). They're used automatically. Streaks restart naturally — what matters is consistency, not perfection.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"hsk.*level", r"what.*level", r"proficiency"],
     "answer": "Your estimated HSK level is based on vocabulary coverage and accuracy across HSK bands. Run 'Assess' from the menu for a detailed breakdown. The estimate improves with more sessions.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"add.*word", r"custom.*vocab", r"import.*list"],
     "answer": "You can add custom vocabulary from the CLI: `mandarin add <hanzi> <pinyin> <english>`. For bulk import, use `mandarin import-csv <file>` with columns: hanzi, pinyin, english, hsk_level.",
     "requires_db": False},
    {"category": "learning", "patterns": [r"grammar", r"sentence.*pattern", r"structure"],
     "answer": "Grammar points are integrated into drills — you'll encounter them naturally as you practice vocabulary that uses those patterns. Check your grammar progress in the Status or Report views.",
     "requires_db": False},

    # Technical
    {"category": "technical", "patterns": [r"app.*crash", r"keeps.*crashing", r"force.*close"],
     "answer": "Sorry about that. Try updating to the latest version first. If it keeps happening, the crash details are logged automatically — our team reviews these regularly. Reinstalling the app (your data syncs from the server) often resolves persistent crashes.",
     "requires_db": True},
    {"category": "technical", "patterns": [r"sync.*issue", r"not.*syncing", r"lost.*progress", r"data.*missing"],
     "answer": "Sync issues can happen with poor connectivity. Try: 1) Force-close and reopen the app. 2) Check your internet connection. 3) Pull down to refresh on the home screen. If data is still missing, our team can check the server-side records.",
     "requires_db": True},
    {"category": "technical", "patterns": [r"audio.*not.*work", r"no.*sound", r"can't.*hear"],
     "answer": "Check that: 1) Your device isn't on silent/vibrate. 2) The app has microphone permission (Settings > Aelu > Microphone). 3) No other app is using the audio. For speaking drills, you need microphone access enabled.",
     "requires_db": False},
    {"category": "technical", "patterns": [r"offline", r"no.*internet", r"without.*wifi"],
     "answer": "Aelu works offline for reviewing previously loaded items. New content requires an internet connection. Offline progress syncs automatically when you reconnect.",
     "requires_db": False},
    {"category": "technical", "patterns": [r"browser.*support", r"which.*browser", r"safari.*chrome"],
     "answer": "The web app works best in Chrome, Firefox, Safari, and Edge (latest versions). Mobile browsers work but the native app provides a better experience with offline support and push notifications.",
     "requires_db": False},
    {"category": "technical", "patterns": [r"slow", r"loading.*long", r"performance"],
     "answer": "If the app feels slow: 1) Check your internet speed. 2) Close other browser tabs/apps. 3) Clear the app cache (Settings > Advanced > Clear Cache). The app is designed to work well even on slower connections.",
     "requires_db": False},

    # Privacy
    {"category": "privacy", "patterns": [r"data.*stor", r"where.*data", r"server.*location"],
     "answer": "Your learning data is stored encrypted on our servers. Audio recordings for tone grading are processed and then deleted — we don't store raw audio long-term. See our Privacy Policy for full details.",
     "requires_db": False},
    {"category": "privacy", "patterns": [r"gdpr", r"european", r"eu.*data"],
     "answer": "Aelu is GDPR compliant. You can exercise your rights (access, rectification, erasure, portability) from Settings > Privacy, or by contacting us directly. We process data under legitimate interest for learning services and consent for optional features.",
     "requires_db": False},
    {"category": "privacy", "patterns": [r"delete.*data", r"erase.*data", r"right.*forgotten"],
     "answer": "Request data deletion from Settings > Privacy > Delete Account, or email us. We'll remove all personal data within 30 days. Some anonymized aggregate data may be retained for service improvement.",
     "requires_db": False},
    {"category": "privacy", "patterns": [r"analytics", r"tracking", r"opt.?out"],
     "answer": "Aelu uses minimal analytics — session counts, accuracy rates, and error patterns — to improve the learning algorithm. We don't sell data or use third-party ad trackers. You can opt out of optional analytics in Settings > Privacy.",
     "requires_db": False},
]


class SupportKnowledge:
    """FAQ and troubleshooting knowledge base."""

    def __init__(self):
        self.entries = _FAQ_ENTRIES
        self._compiled = [
            {**e, "_patterns": [re.compile(p, re.IGNORECASE) for p in e["patterns"]]}
            for e in self.entries
        ]

    def find_match(self, message: str) -> tuple[Optional[dict], float]:
        """Find best FAQ match. Returns (entry, confidence) or (None, 0)."""
        best_match = None
        best_score = 0.0

        for entry in self._compiled:
            for pat in entry["_patterns"]:
                if pat.search(message):
                    score = 0.9
                    if best_score < score:
                        best_match = entry
                        best_score = score
                    break

        if not best_match:
            # Keyword fallback
            words = set(message.lower().split())
            for entry in self._compiled:
                category_words = {"account": {"account", "login", "password", "email"},
                                  "billing": {"billing", "payment", "subscription", "charge", "refund"},
                                  "learning": {"learn", "study", "session", "drill", "vocabulary"},
                                  "technical": {"bug", "crash", "error", "broken", "fix"},
                                  "privacy": {"privacy", "data", "gdpr", "delete"}}
                cat_words = category_words.get(entry["category"], set())
                overlap = words & cat_words
                if overlap:
                    score = 0.5 + 0.1 * len(overlap)
                    if score > best_score:
                        best_match = entry
                        best_score = min(score, 0.75)

        return best_match, best_score

    def get_categories(self) -> list[str]:
        return sorted(set(e["category"] for e in self.entries))

    def get_entries_by_category(self, category: str) -> list[dict]:
        return [e for e in self.entries if e["category"] == category]


class SupportAgent:
    """Automated customer support with escalation."""

    def __init__(self, knowledge: Optional[SupportKnowledge] = None):
        self.knowledge = knowledge or SupportKnowledge()

    def handle_request(
        self, message: str, user_id: Optional[int] = None, conn=None
    ) -> SupportResponse:
        context = None
        if user_id and conn:
            try:
                context = SupportContext.from_user(conn, user_id)
            except Exception:
                pass

        match, confidence = self.knowledge.find_match(message)

        if match and confidence >= 0.7:
            answer = self._personalize(match["answer"], context)
            response = SupportResponse(
                answer=answer,
                confidence=confidence,
                category=match["category"],
                context=context,
                suggested_actions=self._suggest_actions(match, context),
            )
        else:
            response = SupportResponse(
                answer="I'm not sure I can help with that specific question. Let me connect you with our team for a more detailed answer.",
                confidence=confidence,
                category="unknown",
                escalate=True,
                context=context,
            )

        if self._should_escalate(message, response, context):
            response.escalate = True

        return response

    def _personalize(self, answer: str, context: Optional[SupportContext]) -> str:
        if not context:
            return answer
        # Add context-specific notes
        if context.subscription_tier == "free" and "Pro" in answer:
            answer += "\n\nYou're currently on the free tier."
        return answer

    def _suggest_actions(self, match: dict, context: Optional[SupportContext]) -> list[str]:
        actions = []
        cat = match["category"]
        if cat == "technical" and context and context.recent_crashes > 0:
            actions.append(f"Check crash logs — {context.recent_crashes} recent crashes detected")
        if cat == "billing" and context and context.subscription_tier != "free":
            actions.append("Review subscription status in Stripe dashboard")
        if cat == "learning" and context and context.total_sessions == 0:
            actions.append("User hasn't completed any sessions yet — may need onboarding help")
        return actions

    def _should_escalate(
        self, message: str, response: SupportResponse, context: Optional[SupportContext]
    ) -> bool:
        if response.confidence < 0.5:
            return True
        if response.category == "billing" and any(
            w in message.lower() for w in ["dispute", "unauthorized", "fraud", "chargeback"]
        ):
            return True
        if any(w in message.lower() for w in ["bug", "broken", "crash"]) and context and context.recent_crashes > 2:
            return True
        if context and context.subscription_tier != "free" and response.category == "technical":
            return True
        if any(w in message.lower() for w in ["furious", "unacceptable", "terrible", "worst", "lawsuit", "sue"]):
            return True
        return False

    @staticmethod
    def create_ticket(conn, user_id: int, message: str, response: SupportResponse) -> int:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_ticket (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, message TEXT, category TEXT,
                auto_response TEXT, confidence REAL,
                escalated INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
                resolution TEXT, created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT
            )
        """)
        cursor = conn.execute(
            """INSERT INTO support_ticket (user_id, message, category, auto_response, confidence, escalated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, message, response.category, response.answer,
             response.confidence, 1 if response.escalate else 0),
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def get_open_tickets(conn, limit: int = 20) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT * FROM support_ticket WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    @staticmethod
    def resolve_ticket(conn, ticket_id: int, resolution: str) -> bool:
        try:
            result = conn.execute(
                """UPDATE support_ticket SET status = 'resolved', resolution = ?,
                   resolved_at = datetime('now') WHERE id = ? AND status = 'open'""",
                (resolution, ticket_id),
            )
            conn.commit()
            return result.rowcount > 0
        except Exception:
            return False

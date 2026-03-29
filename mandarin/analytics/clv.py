"""Customer Lifetime Value and cohort retention analytics."""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def compute_cohort_retention(conn, cohort_month: str = None) -> list[dict]:
    """Compute retention curves by signup cohort.

    Returns: [{cohort, day_1, day_7, day_14, day_30, day_60, day_90, users}]
    """
    results = []
    try:
        # Get signup cohorts
        query = """
            SELECT strftime('%Y-%m', created_at) as cohort,
                   id as user_id,
                   created_at
            FROM user
            WHERE created_at IS NOT NULL
        """
        if cohort_month:
            query += f" AND strftime('%Y-%m', created_at) = '{cohort_month}'"
        query += " ORDER BY created_at"

        users = conn.execute(query).fetchall()

        cohorts = defaultdict(list)
        for u in users:
            cohorts[u["cohort"]].append(u)

        for cohort, cohort_users in sorted(cohorts.items()):
            user_ids = [u["user_id"] for u in cohort_users]
            n = len(user_ids)
            if n == 0:
                continue

            retention = {"cohort": cohort, "users": n}

            for day in [1, 7, 14, 30, 60, 90]:
                try:
                    placeholders = ",".join("?" * len(user_ids))
                    sql = f"""
                        SELECT COUNT(DISTINCT user_id) as cnt
                        FROM session_log
                        WHERE user_id IN ({placeholders})
                        AND started_at >= datetime(
                            (SELECT created_at FROM user WHERE id = user_id),
                            '+{day} days'
                        )
                        AND started_at < datetime(
                            (SELECT created_at FROM user WHERE id = user_id),
                            '+{day + 1} days'
                        )
                    """
                    active = conn.execute(sql, user_ids).fetchone()
                    retention[f"day_{day}"] = round(active["cnt"] / n * 100, 1) if active else 0.0
                except Exception:
                    retention[f"day_{day}"] = 0.0

            results.append(retention)
    except Exception as e:
        logger.debug("Cohort retention failed: %s", e)

    return results


def compute_ltv(conn, user_id: int = None) -> dict:
    """Compute simple LTV = ARPU x avg_lifetime_months."""
    try:
        if user_id:
            # Individual LTV
            revenue = conn.execute("""
                SELECT COALESCE(SUM(amount_cents), 0) / 100.0 as total_revenue
                FROM payment_event
                WHERE user_id = ? AND status = 'succeeded'
            """, (user_id,)).fetchone()

            first_session = conn.execute("""
                SELECT MIN(started_at) as first, MAX(started_at) as last
                FROM session_log WHERE user_id = ?
            """, (user_id,)).fetchone()

            total_rev = revenue["total_revenue"] if revenue else 0.0
            if first_session and first_session["first"] and first_session["last"]:
                days_active = conn.execute(
                    "SELECT julianday(?) - julianday(?)",
                    (first_session["last"], first_session["first"])
                ).fetchone()[0] or 1
                months = max(1, days_active / 30)
            else:
                months = 1

            return {"user_id": user_id, "total_revenue": total_rev,
                    "months_active": round(months, 1), "monthly_arpu": round(total_rev / months, 2)}

        # Aggregate LTV
        stats = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as total_users,
                   COALESCE(SUM(amount_cents), 0) / 100.0 as total_revenue
            FROM payment_event WHERE status = 'succeeded'
        """).fetchone()

        avg_lifetime = conn.execute("""
            SELECT AVG(span_days) / 30.0 as avg_months FROM (
                SELECT julianday(MAX(started_at)) - julianday(MIN(started_at)) as span_days
                FROM session_log
                GROUP BY user_id
                HAVING COUNT(*) > 1
            )
        """).fetchone()

        users = stats["total_users"] or 1
        revenue = stats["total_revenue"] or 0.0
        months = (avg_lifetime["avg_months"] or 1) if avg_lifetime else 1
        arpu = revenue / users

        return {"total_users": users, "total_revenue": revenue,
                "avg_lifetime_months": round(months, 1), "arpu": round(arpu, 2),
                "estimated_ltv": round(arpu * months, 2)}
    except Exception as e:
        logger.debug("LTV calculation failed: %s", e)
        return {"error": str(e)}


def predict_ltv_segment(conn, user_id: int) -> str:
    """Classify user as high/medium/low LTV based on first-14-day engagement."""
    try:
        stats = conn.execute("""
            SELECT COUNT(*) as sessions,
                   SUM(CASE WHEN early_exit = 0 OR early_exit IS NULL THEN 1 ELSE 0 END) as completed,
                   AVG(duration_seconds) as avg_duration
            FROM session_log
            WHERE user_id = ?
            AND started_at >= (SELECT created_at FROM user WHERE id = ?)
            AND started_at <= datetime((SELECT created_at FROM user WHERE id = ?), '+14 days')
        """, (user_id, user_id, user_id)).fetchone()

        if not stats or not stats["sessions"]:
            return "unknown"

        sessions = stats["sessions"]
        completion_rate = stats["completed"] / sessions if sessions else 0
        avg_duration = stats["avg_duration"] or 0

        # High: 5+ sessions, 70%+ completion, 5+ min avg
        if sessions >= 5 and completion_rate >= 0.7 and avg_duration >= 300:
            return "high"
        # Low: <2 sessions or <30% completion
        if sessions < 2 or completion_rate < 0.3:
            return "low"
        return "medium"
    except Exception:
        return "unknown"

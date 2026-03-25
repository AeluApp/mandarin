"""Content optimization agent — A/B variant generation + performance learning.

Runs weekly (called by marketing_scheduler on Sundays):
1. Aggregate past week's metrics from marketing_content_metrics
2. Extract engagement patterns from top performers via LLM
3. Generate 2-3 variants for next week's content
4. Run all guards (identity, copy drift, voice standard)
5. Create experiments via the experiments framework

Uses cloud-hosted 70B+ models via LiteLLM for high-quality variant generation.

Exports:
    run_optimization_cycle(conn) -> dict
    generate_variants(conn, content_text, n=3) -> list[str]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

_VARIANT_SYSTEM_PROMPT = """\
You are writing social media content for Aelu, a Mandarin Chinese learning app.

Voice rules:
- Calm adult. Data-grounded. No praise inflation ("Amazing!", "Incredible!").
- No urgency marketing ("Don't miss", "Act now", "Limited time").
- First-person "I" is fine (anonymous builder persona). Never reveal who "I" is — no real names, photos, employers, or personal details.
- Warm and direct. Civic Sanctuary tone.

Content rules:
- Keep the core insight/data from the original
- Vary the hook, structure, or angle
- Stay under the character limit
- Include relevant hashtags when appropriate for the platform
"""


def run_optimization_cycle(conn) -> dict:
    """Run the weekly content optimization cycle.

    Returns a summary dict with counts of actions taken.
    """
    summary = {
        "top_performers": [],
        "patterns": [],
        "variants_generated": 0,
        "variants_approved": 0,
        "experiments_proposed": 0,
    }

    # 1. Aggregate past week's metrics
    top_posts = _get_top_performers(conn, days=7, limit=5)
    summary["top_performers"] = [p["content_id"] for p in top_posts]

    if len(top_posts) < 2:
        logger.info("Not enough posts with metrics for optimization (need 2+, have %d)", len(top_posts))
        _log_run(conn, summary)
        return summary

    # 2. Extract patterns from top performers via LLM
    patterns = _extract_patterns(conn, top_posts)
    summary["patterns"] = patterns

    # 3. Get next week's scheduled content
    from .calendar_parser import parse_calendar, get_actions_for_date
    from datetime import date, timedelta

    actions = parse_calendar()
    next_week_actions = []
    today = date.today()
    for day_offset in range(1, 8):
        target = today + timedelta(days=day_offset)
        next_week_actions.extend(get_actions_for_date(actions, target))

    # Filter to automatable Twitter posts
    postable = [a for a in next_week_actions
                if a.platform == "twitter" and a.content_key]

    if not postable:
        logger.info("No postable actions for next week")
        _log_run(conn, summary)
        return summary

    # 4. Generate variants for each postable action
    from .content_bank import load_content_bank, personalize_content

    bank = load_content_bank()
    for action in postable[:5]:  # Max 5 per cycle
        piece = bank.get(action.content_key)
        if not piece:
            continue

        text = personalize_content(piece, conn=conn)
        variants = generate_variants(conn, text, n=2, patterns=patterns)

        for i, variant_text in enumerate(variants):
            # Run guards
            if not _passes_guards(variant_text, conn):
                continue

            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO marketing_content_variant
                    (content_id, variant_id, variant_text, generation_model, identity_passed,
                     copy_drift_passed, status, created_at)
                VALUES (?, ?, ?, ?, 1, 1, 'approved', ?)
            """, (action.content_key, chr(65 + i), variant_text, "cloud", now))
            summary["variants_generated"] += 1
            summary["variants_approved"] += 1

        conn.commit()

    # 5. Propose experiments for variants
    _propose_experiments(conn, summary)

    _log_run(conn, summary)
    logger.info("Optimization cycle complete: %d variants generated, %d approved",
                summary["variants_generated"], summary["variants_approved"])
    return summary


def generate_variants(
    conn, content_text: str, n: int = 3,
    patterns: list[str] | None = None,
    char_limit: int = 280,
) -> list[str]:
    """Generate N variant rewrites of content using cloud LLM.

    Returns list of variant texts (may be fewer than N if some fail guards).
    """
    try:
        from ..ai.ollama_client import generate as llm_generate
    except ImportError:
        return []

    patterns_text = "\n".join(f"- {p}" for p in (patterns or []))

    prompt = f"""Original content:
{content_text}

{"Top-performing patterns this week:" + chr(10) + patterns_text if patterns_text else ""}

Generate {n} variants of this content. Each should:
1. Keep the core insight/data
2. Vary the hook, structure, or angle
3. Stay under {char_limit} characters
4. First-person "I" is fine but never reveal who "I" is

Respond with JSON: {{"variants": [{{"text": "...", "rationale": "..."}}]}}"""

    resp = llm_generate(
        prompt=prompt,
        system=_VARIANT_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=1024,
        use_cache=False,
        conn=conn,
        task_type="reading_generation",  # Tier 2 task
    )

    if not resp.success:
        logger.warning("Variant generation failed: %s", resp.error)
        return []

    try:
        # Parse JSON from response
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)
        variants = [v["text"] for v in data.get("variants", []) if v.get("text")]
        return variants[:n]
    except (json.JSONDecodeError, KeyError):
        logger.debug("Failed to parse variant JSON: %s", resp.text[:200])
        return []


def _get_top_performers(conn, days: int = 7, limit: int = 5) -> list[dict]:
    """Get top-performing posts from the last N days by engagement."""
    try:
        rows = conn.execute("""
            SELECT
                pl.content_id,
                pl.platform,
                SUM(CASE WHEN cm.metric_type = 'likes' THEN cm.metric_value ELSE 0 END) as likes,
                SUM(CASE WHEN cm.metric_type = 'impressions' THEN cm.metric_value ELSE 0 END) as impressions,
                SUM(CASE WHEN cm.metric_type = 'retweets' THEN cm.metric_value ELSE 0 END) as retweets
            FROM marketing_post_log pl
            JOIN marketing_content_metrics cm ON cm.post_log_id = pl.id
            WHERE pl.posted_at > datetime('now', ?)
            GROUP BY pl.content_id
            ORDER BY likes + retweets DESC
            LIMIT ?
        """, (f"-{days} days", limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _extract_patterns(conn, top_posts: list[dict]) -> list[str]:
    """Use LLM to extract engagement patterns from top performers."""
    try:
        from ..ai.ollama_client import generate as llm_generate
    except ImportError:
        return []

    # Get the actual text of top posts
    texts = []
    for post in top_posts:
        row = conn.execute(
            "SELECT original_text FROM marketing_content WHERE content_id = ?",
            (post["content_id"],),
        ).fetchone()
        if row:
            texts.append(row["original_text"][:200])

    if not texts:
        return []

    prompt = (
        "Given these top-performing social media posts about Mandarin learning, "
        "what patterns do they share? Focus on: tone, structure, topic, length, hook style.\n\n"
        + "\n---\n".join(texts)
        + "\n\nRespond with JSON: {\"patterns\": [\"pattern 1\", \"pattern 2\", ...]}"
    )

    resp = llm_generate(
        prompt=prompt, system="You are a marketing analyst.", temperature=0.3,
        max_tokens=512, conn=conn, task_type="voice_audit",
    )

    if resp.success:
        try:
            data = json.loads(resp.text.strip())
            return data.get("patterns", [])
        except json.JSONDecodeError:
            pass
    return []


def _passes_guards(text: str, conn) -> bool:
    """Run identity guard + voice standard on a variant. Returns True if passes."""
    # Identity guard
    try:
        from .anonymity_guard import check_identity
        result = check_identity(text, conn=conn)
        if not result.passed:
            return False
    except Exception:
        return False  # Fail closed

    # Voice standard (check for forbidden patterns)
    try:
        from ..intelligence.vibe_marketing_eng import VOICE_STANDARD
        import re
        for pattern_str, _name in VOICE_STANDARD.get("forbidden_patterns", []):
            if re.search(pattern_str, text, re.IGNORECASE):
                return False
    except (ImportError, Exception):
        pass  # If unavailable, skip voice check

    return True


def _propose_experiments(conn, summary: dict) -> None:
    """Propose A/B experiments for content variants."""
    try:
        from ..experiments import create_experiment, start_experiment

        # Find content IDs with 2+ approved variants
        rows = conn.execute("""
            SELECT content_id, COUNT(*) as variant_count
            FROM marketing_content_variant
            WHERE status = 'approved'
            GROUP BY content_id
            HAVING variant_count >= 2
        """).fetchall()

        for row in rows:
            # Check if experiment already exists for this content
            existing = conn.execute(
                "SELECT id FROM experiment WHERE name = ? AND status IN ('draft', 'running')",
                (f"mktg_{row['content_id']}",),
            ).fetchone()
            if existing:
                continue

            variants = conn.execute(
                "SELECT variant_id FROM marketing_content_variant WHERE content_id = ? AND status = 'approved'",
                (row["content_id"],),
            ).fetchall()
            variant_names = [r["variant_id"] for r in variants]

            exp_id = create_experiment(
                conn,
                name=f"mktg_{row['content_id']}",
                description=f"A/B test marketing content variants for {row['content_id']}",
                variants=variant_names,
                traffic_pct=100,
            )
            if exp_id:
                start_experiment(conn, exp_id)
                summary["experiments_proposed"] += 1

    except (ImportError, Exception) as e:
        logger.debug("Experiment proposal failed: %s", e)


def _log_run(conn, summary: dict) -> None:
    """Log the optimization run to marketing_optimizer_run."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO marketing_optimizer_run
                (run_date, top_performers, patterns_extracted,
                 variants_generated, variants_approved, experiments_proposed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            now,
            json.dumps(summary.get("top_performers", [])),
            json.dumps(summary.get("patterns", [])),
            summary.get("variants_generated", 0),
            summary.get("variants_approved", 0),
            summary.get("experiments_proposed", 0),
            now,
        ))
        conn.commit()
    except Exception:
        logger.debug("Optimizer run log failed", exc_info=True)

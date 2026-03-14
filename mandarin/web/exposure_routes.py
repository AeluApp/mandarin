"""Exposure routes — reading, media shelf, listening, vocab encounters."""

import logging
import re
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from urllib.parse import quote_plus

from ..tier_gate import check_tier_access
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)


# ── Pinyin syllable splitter ──────────────────────────
# Splits run-together pinyin like "péngyou" into ["péng", "you"].
_PINYIN_INITIALS = (
    "zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
    "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w",
)
# Vowel class: all tone-marked and plain vowels
_V = "[aāáǎàeēéěèiīíǐìoōóǒòuūúǔùüǖǘǚǜ]"
_PINYIN_SYLLABLE_RE = re.compile(
    r"(?:(?:zh|ch|sh|[bpmfdtnlgkhjqxrzcsyw])?)"   # optional initial
    r"(" + _V + r"+" r"(?:ng?|r)?)",                # final: vowels + optional nasal/r
    re.IGNORECASE,
)


def _split_pinyin(pinyin: str, n_chars: int) -> list:
    """Best-effort split of run-together pinyin into n_chars syllables."""
    # Try space-separated first
    parts = pinyin.split()
    if len(parts) == n_chars:
        return parts
    # Greedy left-to-right parse via regex
    syllables = [m.group(0) for m in _PINYIN_SYLLABLE_RE.finditer(pinyin)]
    if len(syllables) == n_chars:
        return syllables
    # Fallback: return whole pinyin for first char, empty for rest
    return [pinyin] + [""] * (n_chars - 1) if n_chars > 0 else []

exposure_bp = Blueprint("exposure", __name__)


def _url_label(url: str) -> str:
    """Return a human-readable platform label for a URL."""
    if not url:
        return ""
    u = url.lower()
    if "youtube.com" in u:
        if "/results?" in u or "search_query=" in u:
            return "YouTube Search"
        return "YouTube"
    if "bilibili.com" in u:
        if "/search" in u or "keyword=" in u:
            return "Bilibili Search"
        return "Bilibili"
    if "douyin.com" in u:
        if "/search" in u:
            return "Douyin Search"
        return "Douyin"
    if "iq.com" in u:
        return "iQIYI"
    if "v.qq.com" in u or "wetv.vip" in u:
        return "WeTV / Tencent Video"
    if "youku.com" in u:
        return "Youku"
    if "netflix.com" in u:
        return "Netflix"
    if "primevideo.com" in u:
        return "Amazon Prime Video"
    if "tv.apple.com" in u:
        return "Apple TV"
    if "viki.com" in u:
        return "Viki"
    if "tubitv.com" in u:
        return "Tubi (free)"
    if "criterionchannel.com" in u:
        return "Criterion Channel"
    if "podcasts.apple.com" in u:
        return "Apple Podcasts"
    if "tv.cctv.com" in u:
        return "CCTV"
    if "vistopia.com" in u:
        return "Vistopia (看理想)"
    if "yixi.tv" in u:
        return "YiXi (一席)"
    if "play.google.com" in u:
        return "Google Play"
    if "mydramalist.com" in u:
        return "MyDramaList"
    if "instagram.com" in u:
        return "Instagram"
    if "tiktok.com" in u:
        return "TikTok"
    if "spotify.com" in u:
        return "Spotify"
    if "weibo.com" in u or "weibo.cn" in u:
        return "Weibo"
    if "xiaohongshu.com" in u or "xhslink.com" in u:
        return "RED (Xiaohongshu)"
    if "zhihu.com" in u:
        return "Zhihu"
    if "ximalaya.com" in u:
        return "Ximalaya"
    return ""


# Domains that are generally inaccessible outside China or require
# a Chinese account / VPN, so a YouTube search fallback is more useful.
_CHINA_ONLY_DOMAINS = {
    "v.qq.com", "list.youku.com", "www.youku.com", "youku.com",
    "www.douyin.com", "douyin.com",
    "tv.cctv.com", "www.vistopia.com.cn", "yixi.tv",
    "weibo.com", "www.weibo.com", "weibo.cn",
    "www.xiaohongshu.com", "xiaohongshu.com", "xhslink.com",
    "www.zhihu.com", "zhihu.com",
}


def _is_china_only(url: str) -> bool:
    """Return True if the URL goes to a platform that typically requires
    access from within China (or a Chinese account)."""
    if not url:
        return False
    try:
        parts = url.split("/")
        domain = parts[2].lower() if len(parts) >= 3 else ""
        return domain in _CHINA_ONLY_DOMAINS
    except (IndexError, AttributeError):
        return False


def _is_search_url(url: str) -> bool:
    """Return True if the URL is a search results page rather than direct content."""
    if not url:
        return True
    u = url.lower()
    return ("/results?" in u or "search_query=" in u or
            "/search/" in u or "/search?" in u or "keyword=" in u)


def _make_youtube_search_url(where_to_find: dict) -> str:
    """Generate a YouTube search URL from where_to_find metadata.

    Always targets YouTube since it is the most universally accessible
    platform for Chinese media content outside China.
    Returns empty string if no search terms are available.
    """
    if not isinstance(where_to_find, dict):
        return ""
    terms = where_to_find.get("search_terms", [])
    primary = where_to_find.get("primary", "")
    query = ""
    if terms:
        query = terms[0]
    elif "'" in primary:
        parts = primary.split("'")
        if len(parts) >= 2:
            query = parts[1]
    if not query:
        return ""
    return "https://www.youtube.com/results?search_query=" + quote_plus(query)


def _resolve_watch_links(entry: dict) -> dict:
    """Resolve the best watch URL(s) for a media catalog entry.

    Returns a dict with:
        watch_url: best primary link (direct content or best platform)
        watch_label: human-readable label for watch_url
        fallback_url: YouTube search fallback (empty if watch_url is already YT search)
        fallback_label: label for fallback_url
    """
    direct_url = entry.get("url", "")
    wtf = entry.get("where_to_find") or {}
    yt_search_url = _make_youtube_search_url(wtf) if isinstance(wtf, dict) else ""

    # Determine the primary watch_url
    # If the direct URL is a China-only platform, prefer YouTube search as primary
    if direct_url and not _is_china_only(direct_url):
        watch_url = direct_url
        watch_label = _url_label(direct_url) or entry.get("platform", "Watch")
        # Offer YT search as fallback only if the primary isn't already YT search
        if yt_search_url and not _is_search_url(direct_url):
            fallback_url = yt_search_url
            fallback_label = "YouTube Search"
        else:
            fallback_url = ""
            fallback_label = ""
    elif yt_search_url:
        # China-only or no direct URL -- use YouTube search as primary
        watch_url = yt_search_url
        watch_label = "YouTube Search"
        # Still offer the China-platform link as secondary for users with access
        if direct_url and direct_url != yt_search_url:
            fallback_url = direct_url
            fallback_label = _url_label(direct_url) or "Original source"
        else:
            fallback_url = ""
            fallback_label = ""
    elif direct_url:
        # No YT search available but we have a direct URL (even if China-only)
        watch_url = direct_url
        watch_label = _url_label(direct_url) or entry.get("platform", "Watch")
        fallback_url = ""
        fallback_label = ""
    else:
        watch_url = ""
        watch_label = ""
        fallback_url = ""
        fallback_label = ""

    return {
        "watch_url": watch_url,
        "watch_label": watch_label,
        "fallback_url": fallback_url,
        "fallback_label": fallback_label,
    }



# ── Reading / Graded Reader endpoints ──────────────────

@exposure_bp.route("/api/reading/passages")
def api_reading_passages():
    """Return reading passages, optionally filtered by HSK level."""
    try:
        user_id = _get_user_id()
        from ..tier_gate import FREE_READING_HSK_MAX
        free_only = False
        with db.connection() as gate_conn:
            if not check_tier_access(gate_conn, user_id, "reading"):
                free_only = True  # Allow HSK 1 reading on free tier
        from ..media import load_reading_passages
        hsk_level = request.args.get("hsk_level", type=int)
        if free_only:
            hsk_level = FREE_READING_HSK_MAX  # Constrain to HSK 1

        # When no explicit hsk_level requested, compute suggested level from mastery
        if not hsk_level:
            try:
                with db.connection() as conn:
                    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
                    suggested_hsk = 1
                    for level in sorted(mastery.keys()):
                        m = mastery[level]
                        total = m.get("seen", 0)
                        mastered = (m.get("durable", 0) or 0) + (m.get("stable", 0) or 0)
                        if total > 10 and (mastered / total) >= 0.6:
                            suggested_hsk = level + 1
                    hsk_level = min(suggested_hsk, 9)
            except Exception:
                pass  # Fall through to unfiltered if mastery lookup fails

        passages = load_reading_passages(hsk_level)

        # Fetch completion counts for this user
        completed_map = {}
        try:
            with db.connection() as conn:
                comp_rows = conn.execute("""
                    SELECT passage_id, COUNT(*) as times_read,
                           MAX(questions_correct) as best_correct,
                           MAX(questions_total) as best_total
                    FROM reading_progress WHERE user_id = ?
                    GROUP BY passage_id
                """, (user_id,)).fetchall()
                for cr in comp_rows:
                    completed_map[cr["passage_id"]] = {
                        "times_read": cr["times_read"],
                        "best_correct": cr["best_correct"] or 0,
                        "best_total": cr["best_total"] or 0,
                    }
        except Exception:
            pass  # Completion data is optional

        _PERSONALITY_TAGS = ("_wit_", "_friction_", "_satire_")

        # Source type filter
        source_type_filter = request.args.get("source_type", "").strip()

        def _infer_source_type(p):
            pid = (p.get("id") or "").lower()
            src = (p.get("source") or "").lower()
            if "gen_" in pid or "generated" in pid or "ollama" in src or "ai" in src:
                return "ai_generated"
            if "tmpl_" in pid or "template" in pid or "template" in src:
                return "template_generated"
            return "human_authored"

        def _make_entry(p):
            pid = p.get("id")
            comp = completed_map.get(pid, {})
            return {
                "id": pid,
                "title": p.get("title", ""),
                "title_zh": p.get("title_zh", ""),
                "hsk_level": p.get("hsk_level", 1),
                "free": (p.get("hsk_level") or 1) <= FREE_READING_HSK_MAX,
                "times_read": comp.get("times_read", 0),
                "best_correct": comp.get("best_correct", 0),
                "best_total": comp.get("best_total", 0),
                "source_type": _infer_source_type(p),
            }

        unread_personality = []
        other = []
        for p in passages:
            if free_only and (p.get("hsk_level") or 1) > FREE_READING_HSK_MAX:
                continue
            if source_type_filter and _infer_source_type(p) != source_type_filter:
                continue
            pid = p.get("id") or ""
            is_personality = any(tag in pid for tag in _PERSONALITY_TAGS)
            is_unread = completed_map.get(pid, {}).get("times_read", 0) == 0
            if is_personality and is_unread:
                unread_personality.append(_make_entry(p))
            else:
                other.append(_make_entry(p))

        # Interleave unread personality passages every ~5 items
        result = []
        pi = 0  # personality index
        for i, entry in enumerate(other):
            # Insert a personality passage every 5 items
            if pi < len(unread_personality) and i > 0 and i % 5 == 0:
                result.append(unread_personality[pi])
                pi += 1
            result.append(entry)
        # Append any remaining personality passages
        result.extend(unread_personality[pi:])

        return jsonify({"passages": result, "free_only": free_only})
    except (OSError, KeyError, TypeError) as e:
        logger.error("reading passages API error: %s", e)
        return jsonify({"error": "Passages unavailable"}), 500


@exposure_bp.route("/api/reading/passage/<passage_id>")
def api_reading_passage(passage_id):
    """Return a single passage with full text, glosses, and per-char mastery."""
    try:
        from ..media import load_reading_passages
        passages = load_reading_passages()
        passage = next((p for p in passages if p.get("id") == passage_id), None)
        if not passage:
            return jsonify({"error": "Passage not found"}), 404

        # Build per-character mastery map for adaptive rendering
        char_mastery = {}
        try:
            user_id = _get_user_id()
            text_zh = passage.get("text_zh", "")
            cjk_chars = list({c for c in text_zh if '\u4e00' <= c <= '\u9fff'})
            if cjk_chars:
                with db.connection() as conn:
                    placeholders = ",".join("?" for _ in cjk_chars)
                    rows = conn.execute(f"""
                        SELECT ci.hanzi, ci.pinyin,
                               COALESCE(p.mastery_stage, 'unseen') as stage
                        FROM content_item ci
                        LEFT JOIN progress p ON ci.id = p.content_item_id
                            AND p.modality = 'reading' AND p.user_id = ?
                        WHERE ci.hanzi IN ({placeholders})
                    """, [user_id] + cjk_chars).fetchall()
                    for r in rows:
                        char_mastery[r["hanzi"]] = {
                            "stage": r["stage"],
                            "pinyin": r["pinyin"] or "",
                        }
                    # Fallback: for chars not in content_item, find a
                    # word containing the char and extract its pinyin.
                    missing = [c for c in cjk_chars if c not in char_mastery]
                    for ch in missing:
                        fb = conn.execute(
                            """SELECT hanzi, pinyin FROM content_item
                               WHERE hanzi LIKE ? AND length(hanzi) <= 3
                                 AND review_status = 'approved'
                               ORDER BY hsk_level ASC, length(hanzi) ASC
                               LIMIT 1""",
                            (f"%{ch}%",)
                        ).fetchone()
                        if fb:
                            word = fb["hanzi"]
                            syllables = _split_pinyin(fb["pinyin"] or "", len(word))
                            idx = word.find(ch)
                            py = syllables[idx] if 0 <= idx < len(syllables) else ""
                            char_mastery[ch] = {"stage": "unseen", "pinyin": py}
        except Exception:
            pass  # Mastery data is optional — render without it

        result = dict(passage)
        result["char_mastery"] = char_mastery
        # Scale question depth by user HSK level
        all_questions = result.get("questions", [])
        try:
            uid = _get_user_id()
            with db.connection() as conn:
                m = db.get_mastery_by_hsk(conn, user_id=uid)
                u_hsk = max((k for k, v in (m or {}).items() if v.get("seen", 0) > 0), default=1)
        except Exception:
            u_hsk = 1
        if u_hsk <= 2:
            max_q = 2
        elif u_hsk <= 4:
            max_q = 3
        elif u_hsk <= 6:
            max_q = 4
        else:
            max_q = len(all_questions)
        sorted_qs = sorted(all_questions, key=lambda q: q.get("difficulty", 0.5))
        result["questions"] = sorted_qs[:max_q]
        result["user_hsk"] = u_hsk

        # Grammar highlights — match grammar_point patterns against passage text
        grammar_highlights = []
        try:
            text_zh = passage.get("text_zh", "")
            passage_hsk = passage.get("hsk_level", 1)
            with db.connection() as conn:
                import json as _json
                gp_rows = conn.execute("""
                    SELECT id, name, name_zh, hsk_level, category, description,
                           examples_json
                    FROM grammar_point
                    WHERE hsk_level <= ?
                """, (passage_hsk + 1,)).fetchall()
                seen_gp_ids = set()
                for gp in gp_rows:
                    if gp["id"] in seen_gp_ids:
                        continue
                    name_zh = gp["name_zh"] or ""
                    if name_zh and name_zh in text_zh:
                        grammar_highlights.append({
                            "grammar_point_id": gp["id"],
                            "name": gp["name"],
                            "name_zh": name_zh,
                            "hsk_level": gp["hsk_level"],
                            "category": gp["category"],
                        })
                        seen_gp_ids.add(gp["id"])
                        continue
                    examples = []
                    try:
                        examples = _json.loads(gp["examples_json"] or "[]")
                    except (ValueError, TypeError):
                        pass
                    for ex in examples:
                        pat = ""
                        if isinstance(ex, dict):
                            pat = ex.get("pattern_zh") or ex.get("zh") or ""
                        elif isinstance(ex, str):
                            pat = ex
                        if pat and len(pat) >= 2 and pat in text_zh:
                            grammar_highlights.append({
                                "grammar_point_id": gp["id"],
                                "name": gp["name"],
                                "name_zh": name_zh,
                                "hsk_level": gp["hsk_level"],
                                "category": gp["category"],
                            })
                            seen_gp_ids.add(gp["id"])
                            break
        except Exception:
            pass  # Grammar highlights are optional
        result["grammar_highlights"] = grammar_highlights

        return jsonify(result)
    except (OSError, KeyError, TypeError) as e:
        logger.error("reading passage API error: %s", e)
        return jsonify({"error": "Passage unavailable"}), 500


@exposure_bp.route("/api/reading/lookup", methods=["POST"])
def api_reading_lookup():
    """Look up a word during reading. Logs a vocab_encounter."""
    try:
        user_id = _get_user_id()
        data = request.get_json(silent=True) or {}
        hanzi = (data.get("hanzi") or "").strip()
        passage_id = data.get("passage_id", "")
        if not hanzi:
            return jsonify({"error": "hanzi required"}), 400

        with db.connection() as conn:
            row = conn.execute(
                "SELECT id, pinyin, english FROM content_item WHERE hanzi = ? AND review_status = 'approved' LIMIT 1",
                (hanzi,)
            ).fetchone()

            # Fallback: if single character not found, find a word containing it
            # and extract the relevant pinyin syllable.
            fallback_word = None
            if not row and len(hanzi) == 1:
                fallback_row = conn.execute(
                    """SELECT id, hanzi, pinyin, english FROM content_item
                       WHERE hanzi LIKE ? AND length(hanzi) <= 3
                         AND review_status = 'approved'
                       ORDER BY hsk_level ASC, length(hanzi) ASC
                       LIMIT 1""",
                    (f"%{hanzi}%",)
                ).fetchone()
                if fallback_row:
                    word_hanzi = fallback_row["hanzi"]
                    word_pinyin = fallback_row["pinyin"] or ""
                    char_idx = word_hanzi.find(hanzi)
                    syllables = _split_pinyin(word_pinyin, len(word_hanzi))
                    char_pinyin = syllables[char_idx] if 0 <= char_idx < len(syllables) else ""
                    row = fallback_row
                    fallback_word = word_hanzi

            content_item_id = row["id"] if row else None
            if fallback_word:
                pinyin = char_pinyin
                english = f"(in {fallback_word}: {row['english']})"
            else:
                pinyin = row["pinyin"] if row else ""
                english = row["english"] if row else ""

            recent = conn.execute(
                """SELECT 1 FROM vocab_encounter
                   WHERE user_id = ? AND hanzi = ? AND source_type = 'reading' AND source_id = ?
                     AND created_at >= datetime('now', '-5 minutes')
                   LIMIT 1""",
                (user_id, hanzi, passage_id)
            ).fetchone()
            if not recent:
                conn.execute(
                    """INSERT INTO vocab_encounter
                       (user_id, content_item_id, hanzi, source_type, source_id, looked_up)
                       VALUES (?, ?, ?, 'reading', ?, 1)""",
                    (user_id, content_item_id, hanzi, passage_id)
                )

                # Track first_lookup activation milestone
                try:
                    first = conn.execute(
                        """SELECT 1 FROM lifecycle_event
                           WHERE event_type = 'first_lookup' AND user_id = ? LIMIT 1""",
                        (str(user_id),),
                    ).fetchone()
                    if not first:
                        from ..marketing_hooks import log_lifecycle_event
                        log_lifecycle_event(
                            "first_lookup",
                            user_id=str(user_id),
                            conn=conn,
                            hanzi=hanzi,
                        )
                except Exception:
                    pass  # Don't break lookup for telemetry

            conn.commit()

            return jsonify({
                "hanzi": hanzi,
                "pinyin": pinyin,
                "english": english,
                "found": row is not None,
            })
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("reading lookup API error: %s", e)
        return jsonify({"error": "Lookup failed"}), 500


@exposure_bp.route("/api/reading/complete", methods=["POST"])
def api_reading_complete():
    """Record a reading passage completion.

    Logs vocab encounters for key vocabulary in the passage,
    bridging reading exposure back into the drill system's
    cleanup loop (recently-encountered words get scheduled sooner).
    """
    try:
        user_id = _get_user_id()
        data = request.get_json(silent=True) or {}
        passage_id = data.get("passage_id", "")
        if not passage_id:
            return jsonify({"error": "passage_id required"}), 400
        with db.connection() as conn:
            from ..media import load_reading_passages
            passages = load_reading_passages()
            passage = next((p for p in passages if p.get("id") == passage_id), None)
            if not passage:
                return jsonify({"error": "Passage not found"}), 404
            vocab = passage.get("vocab_preview", passage.get("key_vocab", []))
            encounters_logged = 0
            for v in vocab[:10]:
                hanzi = v if isinstance(v, str) else v.get("hanzi", "")
                if not hanzi:
                    continue
                ci = conn.execute(
                    "SELECT id FROM content_item WHERE hanzi = ? AND review_status = 'approved' LIMIT 1",
                    (hanzi,)
                ).fetchone()
                if ci:
                    conn.execute("""
                        INSERT INTO vocab_encounter
                        (user_id, content_item_id, hanzi, source_type, source_id, looked_up)
                        VALUES (?, ?, ?, 'reading', ?, 0)
                    """, (user_id, ci["id"], hanzi, passage_id))
                    encounters_logged += 1
            conn.commit()
            return jsonify({"status": "ok", "encounters_logged": encounters_logged})
    except Exception as e:
        logger.error("reading complete API error: %s", e)
        return jsonify({"error": str(e)}), 500


# ── Media Shelf endpoints ──────────────────────────────

@exposure_bp.route("/api/media/recommendations")
def api_media_recommendations():
    """Return media recommendations. Free users get HSK 1 media."""
    try:
        user_id = _get_user_id()
        from ..tier_gate import get_user_tier, FREE_MEDIA_HSK_MAX
        free_media = False
        with db.connection() as gate_conn:
            tier = get_user_tier(gate_conn, user_id)
            if tier not in ("paid", "admin", "teacher"):
                free_media = True
        from ..media import recommend_media, record_media_presentation
        limit = request.args.get("limit", 6, type=int)
        with db.connection() as conn:
            # Determine user's effective HSK level for filtering.
            # Use "working level" — the highest level where user has
            # meaningful progress (>=20% weighted), then +1 for stretch.
            # This prevents showing HSK 6-7 content to someone who only
            # casually saw a couple of items at those levels.
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            if mastery:
                working = [k for k, v in mastery.items()
                           if v.get("pct", 0) >= 20]
                if working:
                    hsk_max = max(working) + 1
                else:
                    # No meaningful progress yet — allow HSK 1-2
                    active = [k for k, v in mastery.items()
                              if v.get("seen", 0) > 0]
                    hsk_max = min(max(active) + 1, 2) if active else 1
            else:
                hsk_max = 1
            # Free tier: cap HSK level for recommendations
            if free_media:
                hsk_max = min(hsk_max, FREE_MEDIA_HSK_MAX)
            from ..scheduler import _get_lens_weights
            lens_weights = _get_lens_weights(conn, user_id)
            recs = recommend_media(conn, hsk_max=hsk_max, limit=limit,
                                   lens_weights=lens_weights, user_id=user_id)
            result = []
            for entry, watch in recs:
                entry_hsk = entry.get("hsk_level") or 1
                if free_media and entry_hsk > FREE_MEDIA_HSK_MAX:
                    continue
                record_media_presentation(conn, entry.get("id", ""), user_id=user_id)
                has_quiz = bool(entry.get("questions"))
                wtf = entry.get("where_to_find") or {}
                links = _resolve_watch_links(entry)
                result.append({
                    "id": entry.get("id"),
                    "title": entry.get("title", ""),
                    "hsk_level": entry_hsk,
                    "media_type": entry.get("media_type", ""),
                    "cost": entry.get("cost", "free"),
                    "content_name": entry.get("content_name", ""),
                    "content_name_en": entry.get("content_name_en", ""),
                    "year": entry.get("year"),
                    "content_lenses": entry.get("content_lenses", []),
                    "segment": entry.get("segment", {}),
                    "where_to_find": wtf,
                    "watch_url": links["watch_url"],
                    "watch_label": links["watch_label"],
                    "fallback_url": links["fallback_url"],
                    "fallback_label": links["fallback_label"],
                    "search_terms": wtf.get("search_terms", []) if isinstance(wtf, dict) else [],
                    "cultural_note": entry.get("cultural_note", ""),
                    "times_watched": watch.get("times_watched") or 0,
                    "avg_score": watch.get("avg_score"),
                    "liked": watch.get("liked"),
                    "has_quiz": has_quiz,
                    "free": entry_hsk <= FREE_MEDIA_HSK_MAX,
                })
            return jsonify({"recommendations": result, "free_only": free_media})
    except (sqlite3.Error, OSError, KeyError, TypeError) as e:
        logger.error("media recommendations API error: %s", e)
        return jsonify({"error": "Recommendations unavailable"}), 500


@exposure_bp.route("/api/media/stats")
@api_error_handler("MediaStats")
def api_media_stats():
    """Return media stats: total watched, avg comprehension, liked count."""
    user_id = _get_user_id()
    from ..media import get_watch_stats
    with db.connection() as conn:
        stats = get_watch_stats(conn, user_id=user_id)
    return jsonify({
        "total_watched": stats.get("watched") or 0,
        "avg_comprehension": round((stats.get("overall_avg") or 0) * 100),
        "liked_count": stats.get("liked_count") or 0,
    })


@exposure_bp.route("/api/media/history")
@api_error_handler("History")
def api_media_history():
    """Return watch history."""
    user_id = _get_user_id()
    from ..media import get_watch_history, get_watch_stats
    with db.connection() as conn:
        history = get_watch_history(conn, user_id=user_id)
        stats = get_watch_stats(conn, user_id=user_id)
        return jsonify({"history": history, "stats": stats})


@exposure_bp.route("/api/media/watched", methods=["POST"])
def api_media_watched():
    """Record a media entry as watched."""
    try:
        user_id = _get_user_id()
        from ..media import record_media_watched
        data = request.get_json(silent=True) or {}
        media_id = data.get("media_id", "")
        score = data.get("score", 0.0)
        if not media_id:
            return jsonify({"error": "media_id required"}), 400
        with db.connection() as conn:
            record_media_watched(conn, media_id, score, 0, 0, user_id=user_id)
            return jsonify({"status": "ok"})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("media watched API error: %s", e)
        return jsonify({"error": "Recording failed"}), 500


@exposure_bp.route("/api/media/skip", methods=["POST"])
def api_media_skip():
    """Record a media skip."""
    try:
        user_id = _get_user_id()
        from ..media import record_media_skip
        data = request.get_json(silent=True) or {}
        media_id = data.get("media_id", "")
        if not media_id:
            return jsonify({"error": "media_id required"}), 400
        with db.connection() as conn:
            record_media_skip(conn, media_id, user_id=user_id)
            return jsonify({"status": "ok"})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("media skip API error: %s", e)
        return jsonify({"error": "Skip recording failed"}), 500


@exposure_bp.route("/api/media/liked", methods=["POST"])
def api_media_liked():
    """Record media liked/disliked."""
    try:
        user_id = _get_user_id()
        from ..media import record_media_liked
        data = request.get_json(silent=True) or {}
        media_id = data.get("media_id", "")
        liked = data.get("liked")
        if not media_id:
            return jsonify({"error": "media_id required"}), 400
        with db.connection() as conn:
            record_media_liked(conn, media_id, bool(liked), user_id=user_id)
            return jsonify({"status": "ok"})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("media liked API error: %s", e)
        return jsonify({"error": "Like recording failed"}), 500


@exposure_bp.route("/api/media/comprehension/<media_id>")
def api_media_comprehension(media_id):
    """Return full media entry with questions for comprehension quiz."""
    try:
        user_id = _get_user_id()
        from ..media import load_media_catalog
        catalog = load_media_catalog()
        entry = next((e for e in catalog if e.get("id") == media_id), None)
        if not entry:
            return jsonify({"error": "Media entry not found"}), 404
        # Compute user's effective HSK level for scaffolding
        user_hsk = 1
        with db.connection() as conn:
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            if mastery:
                active = [k for k, v in mastery.items() if v.get("seen", 0) > 0]
                user_hsk = max(active) if active else 1
        segment = entry.get("segment", {})
        links = _resolve_watch_links(entry)
        # Filter out malformed questions before scaling
        all_questions = [
            q for q in entry.get("questions", [])
            if (q.get("q_zh") or q.get("q_en"))
            and (
                q.get("type") != "mc"
                or (
                    len(q.get("options", [])) >= 2
                    and any(o.get("correct") for o in q.get("options", []))
                )
            )
        ]
        content_hsk = entry.get("hsk_level", 1)
        if user_hsk <= 2:
            max_questions = 2
        elif user_hsk <= 4:
            max_questions = 3
        elif user_hsk <= 6:
            max_questions = 4
        else:
            max_questions = len(all_questions)
        # Sort by difficulty (easier first for lower levels)
        sorted_qs = sorted(all_questions, key=lambda q: q.get("difficulty", 0.5))
        questions = sorted_qs[:max_questions]
        return jsonify({
            "id": entry.get("id"),
            "title": entry.get("title", ""),
            "title_zh": entry.get("title_zh", ""),
            "hsk_level": content_hsk,
            "user_hsk": user_hsk,
            "passage_zh": segment.get("description_zh", ""),
            "passage_en": segment.get("description", ""),
            "vocab_preview": entry.get("vocab_preview", []),
            "questions": questions,
            "cultural_note": entry.get("cultural_note", ""),
            "follow_up": entry.get("follow_up", ""),
            "where_to_find": entry.get("where_to_find", {}),
            "watch_url": links["watch_url"],
            "watch_label": links["watch_label"],
            "fallback_url": links["fallback_url"],
            "fallback_label": links["fallback_label"],
            "segment": {
                "description": segment.get("description", ""),
                "start": segment.get("start", ""),
                "end": segment.get("end", ""),
            },
        })
    except (OSError, KeyError, TypeError) as e:
        logger.error("media comprehension API error: %s", e)
        return jsonify({"error": "Quiz unavailable"}), 500


@exposure_bp.route("/api/media/comprehension/submit", methods=["POST"])
def api_media_comprehension_submit():
    """Submit comprehension quiz results."""
    try:
        user_id = _get_user_id()
        from ..media import record_media_watched, get_media_entry
        data = request.get_json(silent=True) or {}
        media_id = data.get("media_id", "")
        score = data.get("score", 0.0)
        total = data.get("total", 0)
        correct = data.get("correct", 0)
        if not media_id:
            return jsonify({"error": "media_id required"}), 400
        if not isinstance(score, (int, float)):
            return jsonify({"error": "score must be a number"}), 400
        if not isinstance(total, int) or total < 0:
            return jsonify({"error": "total must be a non-negative integer"}), 400
        if not isinstance(correct, int) or correct < 0:
            return jsonify({"error": "correct must be a non-negative integer"}), 400
        score = max(0.0, min(1.0, float(score)))
        with db.connection() as conn:
            record_media_watched(conn, media_id, score, total, correct,
                                 user_id=user_id)

            # Bridge: record vocab encounters for media vocab_preview words
            # Only when comprehension score is decent (>0.6) — indicates
            # the user actually engaged with the content
            if score > 0.6:
                try:
                    entry = get_media_entry(media_id)
                    if entry:
                        vocab_preview = entry.get("vocab_preview", [])
                        for vp in vocab_preview[:5]:
                            hanzi = vp.get("hanzi", "") if isinstance(vp, dict) else str(vp)
                            if not hanzi:
                                continue
                            ci = conn.execute(
                                "SELECT id FROM content_item WHERE hanzi = ? AND review_status = 'approved' LIMIT 1",
                                (hanzi,)
                            ).fetchone()
                            if ci:
                                conn.execute("""
                                    INSERT INTO vocab_encounter
                                    (user_id, content_item_id, hanzi, source_type, source_id, looked_up)
                                    VALUES (?, ?, ?, 'media', ?, 0)
                                """, (user_id, ci["id"], hanzi, media_id))
                        conn.commit()
                except Exception:
                    logger.debug("vocab encounter bridge failed for media %s", media_id,
                                 exc_info=True)

            return jsonify({"status": "ok", "score": score})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("media comprehension submit error: %s", e)
        return jsonify({"error": "Submit failed"}), 500


# ── Listening endpoints ────────────────────────────────

@exposure_bp.route("/api/listening/passage")
def api_listening_passage():
    """Return a random passage for listening practice.

    Supports ?speed=slow|normal|fast for speed-graded listening.
    Free users get HSK 1-2 passages; paid users get all levels.
    """
    try:
        user_id = _get_user_id()
        from ..tier_gate import get_user_tier, FREE_LISTENING_HSK_MAX
        free_listening = False
        with db.connection() as gate_conn:
            tier = get_user_tier(gate_conn, user_id)
            if tier not in ("paid", "admin", "teacher"):
                free_listening = True
        from ..media import generate_listening_passage
        hsk_level = request.args.get("hsk_level", type=int)
        speed = request.args.get("speed", "normal")
        # Free tier: cap HSK level
        if free_listening:
            if hsk_level and hsk_level > FREE_LISTENING_HSK_MAX:
                return jsonify({"error": "upgrade_required", "feature": "listening", "max_free_hsk": FREE_LISTENING_HSK_MAX}), 403
            if not hsk_level:
                hsk_level = FREE_LISTENING_HSK_MAX  # Default to max free level
        with db.connection() as conn:
            passage = generate_listening_passage(conn, user_id=user_id,
                                                 hsk_level=hsk_level)
            if not passage:
                return jsonify({"error": "No suitable passage available"}), 404
            # Filter out passages above free tier level
            if free_listening and (passage.get("hsk_level") or 1) > FREE_LISTENING_HSK_MAX:
                return jsonify({"error": "upgrade_required", "feature": "listening", "max_free_hsk": FREE_LISTENING_HSK_MAX}), 403
            # Include speed info for frontend TTS rate control
            speed_rates = {"slow": 90, "normal": 120, "fast": 150}
            passage["tts_rate"] = speed_rates.get(speed, 120)
            passage["speed"] = speed
            return jsonify(passage)
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("listening passage API error: %s", e)
        return jsonify({"error": "Passage unavailable"}), 500


@exposure_bp.route("/api/listening/complete", methods=["POST"])
def api_listening_complete():
    """Record a listening exercise completion with comprehension scores."""
    try:
        user_id = _get_user_id()
        data = request.get_json(silent=True) or {}
        passage_id = data.get("passage_id", "")
        comprehension_score = data.get("comprehension_score", 0.0)
        questions_correct = data.get("questions_correct", 0)
        questions_total = data.get("questions_total", 0)
        words_encountered = data.get("words_encountered", [])

        if not passage_id:
            return jsonify({"error": "passage_id required"}), 400
        if not isinstance(comprehension_score, (int, float)):
            return jsonify({"error": "comprehension_score must be a number"}), 400

        comprehension_score = max(0.0, min(1.0, float(comprehension_score)))

        with db.connection() as conn:
            # Persist listening progress
            words_looked_up_count = sum(1 for w in words_encountered if w.get("looked_up"))
            hsk_level = data.get("hsk_level", 1)
            conn.execute("""
                INSERT INTO listening_progress
                (user_id, passage_id, comprehension_score, questions_correct,
                 questions_total, words_looked_up, hsk_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, passage_id, comprehension_score,
                  questions_correct, questions_total, words_looked_up_count, hsk_level))

            # Log vocab encounters
            for word in words_encountered[:50]:
                hanzi = (word.get("hanzi") or "").strip()
                if not hanzi:
                    continue
                row = conn.execute(
                    "SELECT id FROM content_item WHERE hanzi = ? AND review_status = 'approved' LIMIT 1", (hanzi,)
                ).fetchone()
                content_item_id = row["id"] if row else None
                conn.execute(
                    """INSERT INTO vocab_encounter
                       (user_id, content_item_id, hanzi, source_type, source_id, looked_up)
                       VALUES (?, ?, ?, 'listening', ?, ?)""",
                    (user_id, content_item_id, hanzi, passage_id, int(word.get("looked_up", False)))
                )
            conn.commit()

            return jsonify({"status": "ok", "comprehension_score": comprehension_score})
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
        logger.error("listening complete API error: %s", e)
        return jsonify({"error": "Recording failed"}), 500


@exposure_bp.route("/api/listening/stats")
@api_error_handler("ListeningStats")
def api_listening_stats():
    """Return listening stats: total completed, avg comprehension, per-level breakdown."""
    user_id = _get_user_id()
    with db.connection() as conn:
        total_row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   AVG(comprehension_score) as avg_score,
                   SUM(words_looked_up) as total_words
            FROM listening_progress WHERE user_id = ?
        """, (user_id,)).fetchone()

        by_level_rows = conn.execute("""
            SELECT hsk_level,
                   COUNT(*) as cnt,
                   AVG(comprehension_score) as avg_score
            FROM listening_progress
            WHERE user_id = ?
            GROUP BY hsk_level
            ORDER BY hsk_level ASC
        """, (user_id,)).fetchall()

        total_completed = total_row["cnt"] if total_row else 0
        avg_comprehension = round((total_row["avg_score"] or 0) * 100) if total_row else 0
        total_words = (total_row["total_words"] or 0) if total_row else 0

        by_level = [
            {
                "hsk_level": r["hsk_level"],
                "completed": r["cnt"],
                "avg_comprehension": round((r["avg_score"] or 0) * 100),
            }
            for r in by_level_rows
        ]

    return jsonify({
        "total_completed": total_completed,
        "avg_comprehension": avg_comprehension,
        "total_words_looked_up": total_words,
        "by_level": by_level,
    })


# ── Encounters summary ────────────────────────────────

@exposure_bp.route("/api/encounters/summary")
@api_error_handler("Encounters")
def api_encounters_summary():
    """Vocab encounter summary for the last 7 days."""
    user_id = _get_user_id()
    with db.connection() as conn:
        total_row = conn.execute(
            """SELECT COUNT(*) as cnt FROM vocab_encounter
               WHERE user_id = ? AND created_at >= datetime('now', '-7 days')""",
            (user_id,)
        ).fetchone()
        total_count = total_row["cnt"] if total_row else 0

        top_words = conn.execute(
            """SELECT hanzi, COUNT(*) as cnt FROM vocab_encounter
               WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
               GROUP BY hanzi ORDER BY cnt DESC LIMIT 10""",
            (user_id,)
        ).fetchall()

        sources = conn.execute(
            """SELECT source_type, COUNT(*) as cnt FROM vocab_encounter
               WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
               GROUP BY source_type""",
            (user_id,)
        ).fetchall()

        return jsonify({
            "total_lookups_7d": total_count,
            "top_words": [{"hanzi": r["hanzi"], "count": r["cnt"]} for r in top_words],
            "sources": {r["source_type"]: r["cnt"] for r in sources},
        })


@exposure_bp.route("/api/reading/progress", methods=["POST"])
@api_error_handler("ReadingProgress")
def api_reading_progress():
    """Record reading passage completion with stats."""
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    passage_id = data.get("passage_id", "")
    if not passage_id:
        return jsonify({"error": "passage_id required"}), 400

    words_looked_up = data.get("words_looked_up", 0)
    questions_correct = data.get("questions_correct", 0)
    questions_total = data.get("questions_total", 0)
    reading_time_seconds = data.get("reading_time_seconds")

    with db.connection() as conn:
        conn.execute("""
            INSERT INTO reading_progress
            (user_id, passage_id, words_looked_up, questions_correct,
             questions_total, reading_time_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, passage_id, words_looked_up, questions_correct,
              questions_total, reading_time_seconds))
        conn.commit()
    return jsonify({"status": "ok"})


@exposure_bp.route("/api/reading/stats")
@api_error_handler("ReadingStats")
def api_reading_stats():
    """Return reading stats: passages read, comprehension %, words/min."""
    user_id = _get_user_id()
    with db.connection() as conn:
        total_row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(questions_correct) as qc,
                   SUM(questions_total) as qt,
                   SUM(words_looked_up) as wl,
                   AVG(reading_time_seconds) as avg_time
            FROM reading_progress WHERE user_id = ?
        """, (user_id,)).fetchone()

        week_row = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM reading_progress
            WHERE user_id = ? AND completed_at >= datetime('now', '-7 days')
        """, (user_id,)).fetchone()

        total_passages = total_row["cnt"] if total_row else 0
        total_qc = (total_row["qc"] or 0) if total_row else 0
        total_qt = (total_row["qt"] or 0) if total_row else 0
        comprehension_pct = round(total_qc / total_qt * 100) if total_qt > 0 else 0
        avg_time = (total_row["avg_time"] or 0) if total_row else 0
        week_count = week_row["cnt"] if week_row else 0

        return jsonify({
            "total_passages": total_passages,
            "week_passages": week_count,
            "comprehension_pct": comprehension_pct,
            "avg_reading_time_seconds": round(avg_time),
            "total_words_looked_up": total_row["wl"] or 0 if total_row else 0,
        })


@exposure_bp.route("/api/reading/daily")
@api_error_handler("DailyPassage")
def api_daily_passage():
    """Return today's recommended reading passage based on user level."""
    user_id = _get_user_id()
    from ..media import load_reading_passages
    from datetime import date
    with db.connection() as conn:
        mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
        user_hsk = 1
        if mastery:
            active = [k for k, v in mastery.items() if v.get("seen", 0) > 0]
            user_hsk = max(active) if active else 1

    passages = load_reading_passages(user_hsk)
    if not passages:
        passages = load_reading_passages(1)
    if not passages:
        return jsonify({"error": "No passages available"}), 404

    # Deterministic daily selection using date as seed
    import hashlib
    day_seed = hashlib.md5(f"{user_id}:{date.today().isoformat()}".encode(), usedforsecurity=False).hexdigest()  # noqa: S324
    idx = int(day_seed, 16) % len(passages)
    passage = passages[idx]
    return jsonify({
        "id": passage.get("id"),
        "title": passage.get("title", ""),
        "title_zh": passage.get("title_zh", ""),
        "hsk_level": passage.get("hsk_level", 1),
        "text_zh": passage.get("text_zh", "")[:120],  # Preview only
    })


@exposure_bp.route("/api/exposure/recommended")
@api_error_handler
def api_exposure_recommended():
    """Recommend reading passages based on recent drill struggles.

    Finds items the user got wrong in the last 7 days, then suggests
    passages that contain those words — closing the drill→exposure loop.
    """
    user_id = current_user.id if hasattr(current_user, "id") else 1
    with db.connection() as conn:
        # Find items user struggled with recently (wrong answers, low mastery)
        struggle_items = conn.execute("""
            SELECT DISTINCT ci.hanzi, ci.hsk_level
            FROM drill_result dr
            JOIN content_item ci ON ci.id = dr.content_item_id
            WHERE dr.user_id = ?
              AND dr.correct = 0
              AND dr.drilled_at >= datetime('now', '-7 days')
            ORDER BY dr.drilled_at DESC
            LIMIT 20
        """, (user_id,)).fetchall()

        if not struggle_items:
            return jsonify({"passages": [], "reason": "no_struggles"})

        struggle_hanzi = [s["hanzi"] for s in struggle_items]
        avg_level = sum(s["hsk_level"] for s in struggle_items) / len(struggle_items)

        # Find passages that contain these words
        from ..data_loader import load_reading_passages
        all_passages = load_reading_passages()
        scored = []
        for p in all_passages:
            text = p.get("text_zh", "")
            matches = sum(1 for h in struggle_hanzi if h in text)
            if matches == 0:
                continue
            # Prefer passages near user's struggle level
            level_dist = abs(p.get("hsk_level", 3) - avg_level)
            score = matches * 10 - level_dist * 2
            scored.append((score, p, matches))

        scored.sort(key=lambda x: x[0], reverse=True)
        recommended = []
        for score, p, match_count in scored[:5]:
            recommended.append({
                "id": p.get("id"),
                "title": p.get("title", ""),
                "title_zh": p.get("title_zh", ""),
                "hsk_level": p.get("hsk_level", 1),
                "text_preview": p.get("text_zh", "")[:80],
                "matching_words": match_count,
            })

        return jsonify({
            "passages": recommended,
            "struggle_words": struggle_hanzi[:10],
            "reason": "drill_struggles",
        })


@exposure_bp.route("/api/content/analyze", methods=["POST"])
@api_error_handler("ContentAnalyze")
def api_content_analyze():
    """Analyze user-pasted Chinese text: HSK level, vocab, difficulty metrics.

    Accepts JSON: {"text": "...Chinese text..."}
    Returns: HSK level estimate, vocabulary list with known/unknown markers,
             difficulty metrics (char count, unique ratio, avg sentence length).
    """
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "No text provided"}), 400

    text = data["text"].strip()
    # NIST AI RMF: input length validation on Chinese text endpoints (max 2000 chars)
    if len(text) > 2000:
        return jsonify({"error": "Text too long (max 2000 characters)"}), 400
    if len(text) < 2:
        return jsonify({"error": "Text too short"}), 400

    from ..media_ingest import (
        extract_vocabulary, estimate_hsk_level, calculate_passage_difficulty,
    )

    user_id = _get_user_id()

    with db.connection() as conn:
        # Extract vocabulary with DB matching
        vocab = extract_vocabulary(text, conn=conn)

        # Estimate HSK level from vocab distribution
        hsk_level = estimate_hsk_level(vocab)

        # Calculate passage difficulty metrics
        difficulty = calculate_passage_difficulty(text)

        # Mark known/unknown based on user's mastery
        vocab_with_status = []
        for v in vocab[:50]:  # Cap at 50 words for response size
            entry = {
                "word": v["word"],
                "count": v["count"],
                "pinyin": v.get("pinyin", ""),
                "english": v.get("english", ""),
                "hsk_level": v.get("hsk_level"),
            }
            # Check user's mastery if we have a content_item_id
            if v.get("content_item_id"):
                entry["content_item_id"] = v["content_item_id"]
                mastery_row = conn.execute("""
                    SELECT mastery_stage FROM content_mastery
                    WHERE user_id = ? AND content_item_id = ?
                """, (user_id, v["content_item_id"])).fetchone()
                if mastery_row:
                    stage = mastery_row["mastery_stage"]
                    entry["known"] = stage in (
                        "passed_once", "stabilizing", "stable", "durable"
                    )
                    entry["stage"] = stage
                else:
                    entry["known"] = False
                    entry["stage"] = "not_seen"
            else:
                entry["known"] = False
                entry["stage"] = "not_in_db"

            vocab_with_status.append(entry)

        # Summary stats
        known_count = sum(1 for v in vocab_with_status if v.get("known"))
        total_vocab = len(vocab_with_status)

        return jsonify({
            "hsk_level": hsk_level,
            "difficulty": difficulty,
            "vocabulary": vocab_with_status,
            "summary": {
                "total_words": total_vocab,
                "known_words": known_count,
                "unknown_words": total_vocab - known_count,
                "known_pct": round(known_count / total_vocab * 100) if total_vocab > 0 else 0,
            },
        })


# ── Dictionary API ──────────────────────────────────────

@exposure_bp.route("/api/dictionary/lookup")
@api_error_handler("DictionaryLookup")
def api_dictionary_lookup():
    """Look up a Chinese word: pinyin, meaning, HSK level, related words.

    Query params:
        q (str): The hanzi/pinyin/english to look up (required).

    Returns definition, pinyin, HSK level, example sentences, related words,
    and CC-CEDICT entries if available.
    Also logs the lookup in vocab_encounter for history tracking.
    """
    q = (request.args.get("q") or request.args.get("hanzi") or "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    if len(q) > 100:
        return jsonify({"error": "Query too long"}), 400

    user_id = _get_user_id()

    with db.connection() as conn:
        # Primary lookup: exact match in content_item
        row = conn.execute("""
            SELECT id, hanzi, pinyin, english, hsk_level, context_note
            FROM content_item
            WHERE hanzi = ?
            LIMIT 1
        """, (q,)).fetchone()

        if not row:
            # Fallback: partial match (word containing the query)
            row = conn.execute("""
                SELECT id, hanzi, pinyin, english, hsk_level, context_note
                FROM content_item
                WHERE hanzi LIKE ?
                ORDER BY length(hanzi) ASC, hsk_level ASC
                LIMIT 1
            """, (f"%{q}%",)).fetchone()

        # CC-CEDICT dictionary lookup (if table exists)
        cedict_entries = []
        try:
            from ..dictionary import lookup as dict_lookup, find_example_sentences
            cedict_entries = dict_lookup(conn, q, limit=10)
            # Add example sentences to each CEDICT entry
            for entry in cedict_entries:
                entry["examples"] = find_example_sentences(
                    conn, entry["simplified"], limit=3
                )
        except (ImportError, sqlite3.OperationalError):
            pass

        if not row and not cedict_entries:
            return jsonify({
                "found": False,
                "query": q,
                "hanzi": q,
                "pinyin": "",
                "english": "",
                "hsk_level": None,
                "cedict_results": [],
            })

        result = {
            "found": True,
            "query": q,
            "cedict_results": cedict_entries,
        }

        if row:
            content_item_id = row["id"]

            # Get user's mastery stage for this item
            mastery_row = conn.execute("""
                SELECT mastery_stage, last_review_date
                FROM progress
                WHERE user_id = ? AND content_item_id = ?
                LIMIT 1
            """, (user_id, content_item_id)).fetchone()

            # Find related words (similar HSK level)
            related = conn.execute("""
                SELECT hanzi, pinyin, english, hsk_level
                FROM content_item
                WHERE id != ? AND hsk_level = ?
                  AND hanzi != ?
                ORDER BY RANDOM()
                LIMIT 5
            """, (content_item_id, row["hsk_level"], q)).fetchall()

            # Find grammar points linked to this item
            grammar_points = conn.execute("""
                SELECT gp.name, gp.name_zh, gp.pattern
                FROM content_grammar cg
                JOIN grammar_point gp ON gp.id = cg.grammar_point_id
                WHERE cg.content_item_id = ?
            """, (content_item_id,)).fetchall()

            # Example sentences from content library
            examples = []
            try:
                from ..dictionary import find_example_sentences
                examples = find_example_sentences(conn, q, limit=3)
            except (ImportError, sqlite3.OperationalError):
                pass

            # Log vocab encounter for lookup history
            try:
                conn.execute("""
                    INSERT INTO vocab_encounter
                    (user_id, content_item_id, hanzi, source_type, source_id, looked_up)
                    VALUES (?, ?, ?, 'dictionary', 'lookup', 1)
                """, (user_id, content_item_id, row["hanzi"]))
                conn.commit()
            except sqlite3.Error:
                pass  # Non-critical

            result.update({
                "hanzi": row["hanzi"],
                "pinyin": row["pinyin"] or "",
                "english": row["english"] or "",
                "hsk_level": row["hsk_level"],
                "context_note": row["context_note"] or "",
                "mastery_stage": mastery_row["mastery_stage"] if mastery_row else "unseen",
                "last_reviewed": mastery_row["last_review_date"] if mastery_row else None,
                "related_words": [
                    {"hanzi": r["hanzi"], "pinyin": r["pinyin"],
                     "english": r["english"], "hsk_level": r["hsk_level"]}
                    for r in related
                ],
                "grammar_points": [
                    {"name": g["name"], "name_zh": g["name_zh"], "pattern": g["pattern"]}
                    for g in grammar_points
                ],
                "examples": examples,
            })
        elif cedict_entries:
            # No content_item match but CEDICT found results
            first = cedict_entries[0]
            result.update({
                "hanzi": first["simplified"],
                "pinyin": first["pinyin"],
                "english": first["english"],
                "hsk_level": None,
            })

        return jsonify(result)


@exposure_bp.route("/api/dictionary/history")
@api_error_handler("DictionaryHistory")
def api_dictionary_history():
    """Return recent dictionary lookups for the current user.

    Uses the vocab_encounter table where source_type = 'dictionary'.
    """
    user_id = _get_user_id()
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT ve.hanzi, ve.created_at,
                   ci.pinyin, ci.english, ci.hsk_level
            FROM vocab_encounter ve
            LEFT JOIN content_item ci ON ci.id = ve.content_item_id
            WHERE ve.user_id = ? AND ve.source_type = 'dictionary'
            ORDER BY ve.created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

        history = []
        seen = set()
        for r in rows:
            hanzi = r["hanzi"]
            if hanzi in seen:
                continue
            seen.add(hanzi)
            history.append({
                "hanzi": hanzi,
                "pinyin": r["pinyin"] or "",
                "english": r["english"] or "",
                "hsk_level": r["hsk_level"],
                "looked_up_at": r["created_at"],
            })

    return jsonify({"history": history})


# ── Content Import API ──────────────────────────────────

@exposure_bp.route("/api/content/import", methods=["POST"])
@api_error_handler("ContentImport")
def api_content_import():
    """Import user-provided Chinese words into their study queue.

    Accepts JSON: {"words": ["你好", "谢谢", ...]}
    Matches against content_item table, creates progress records for matches.
    Returns count of matched/unmatched items.
    """
    from flask_login import current_user as cu
    if not cu.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401

    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    words = data.get("words", [])

    if not isinstance(words, list):
        return jsonify({"error": "words must be a JSON array of hanzi strings"}), 400
    if len(words) == 0:
        return jsonify({"error": "No words provided"}), 400
    if len(words) > 500:
        return jsonify({"error": "Maximum 500 words per import"}), 400

    matched = []
    unmatched = []
    already_queued = []

    with db.connection() as conn:
        for word in words:
            if not isinstance(word, str):
                continue
            word = word.strip()
            if not word:
                continue

            # Look up in content_item
            row = conn.execute(
                "SELECT id, hanzi, pinyin, english, hsk_level FROM content_item WHERE hanzi = ? AND review_status = 'approved'",
                (word,)
            ).fetchone()

            if not row:
                unmatched.append(word)
                continue

            # Check if already in progress
            existing = conn.execute(
                "SELECT id FROM progress WHERE user_id = ? AND content_item_id = ?",
                (user_id, row["id"])
            ).fetchone()

            if existing:
                already_queued.append({
                    "hanzi": row["hanzi"], "pinyin": row["pinyin"],
                    "english": row["english"], "hsk_level": row["hsk_level"],
                })
                continue

            # Create progress record — starts as 'unseen', scheduler will pick it up
            conn.execute("""
                INSERT INTO progress
                (user_id, content_item_id, modality, mastery_stage)
                VALUES (?, ?, 'reading', 'unseen')
            """, (user_id, row["id"]))

            matched.append({
                "hanzi": row["hanzi"], "pinyin": row["pinyin"],
                "english": row["english"], "hsk_level": row["hsk_level"],
            })

        conn.commit()

    return jsonify({
        "matched": len(matched),
        "unmatched": len(unmatched),
        "already_queued": len(already_queued),
        "matched_items": matched,
        "unmatched_words": unmatched[:50],  # Cap for response size
    })


# ── Passage Comments (Community) ─────────────────────────

@exposure_bp.route("/api/reading/comments")
@api_error_handler("PassageComments")
def api_passage_comments():
    """Get comments for a reading passage.

    Query params:
        passage_id (str): The passage ID (required).
        limit (int): Max comments to return (default 20).
    """
    passage_id = request.args.get("passage_id", "").strip()
    if not passage_id:
        return jsonify({"error": "passage_id required"}), 400

    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 50)

    with db.connection() as conn:
        rows = conn.execute("""
            SELECT pc.id, pc.text, pc.created_at,
                   u.display_name,
                   CASE WHEN u.anonymous_mode = 1 THEN 1 ELSE 0 END AS is_anonymous
            FROM passage_comment pc
            JOIN user u ON u.id = pc.user_id
            WHERE pc.passage_id = ?
            ORDER BY pc.created_at DESC
            LIMIT ?
        """, (passage_id, limit)).fetchall()

        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM passage_comment WHERE passage_id = ?",
            (passage_id,)
        ).fetchone()

        comments = []
        for r in rows:
            name = "Anonymous" if r["is_anonymous"] else (r["display_name"] or "Learner")
            comments.append({
                "id": r["id"],
                "text": r["text"],
                "author": name,
                "created_at": r["created_at"],
            })

    return jsonify({
        "comments": comments,
        "total_count": count_row["cnt"] if count_row else 0,
    })


@exposure_bp.route("/api/reading/comment", methods=["POST"])
@api_error_handler("PostComment")
def api_post_comment():
    """Post a comment on a reading passage.

    Body (JSON):
        passage_id (str): The passage ID.
        text (str): Comment text (max 500 chars).
    """
    from flask_login import current_user as cu
    if not cu.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401

    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    passage_id = (data.get("passage_id") or "").strip()
    text = (data.get("text") or "").strip()

    if not passage_id:
        return jsonify({"error": "passage_id required"}), 400
    if not text:
        return jsonify({"error": "Comment text required"}), 400
    if len(text) > 500:
        return jsonify({"error": "Comment too long (max 500 characters)"}), 400

    with db.connection() as conn:
        cursor = conn.execute("""
            INSERT INTO passage_comment (passage_id, user_id, text)
            VALUES (?, ?, ?)
        """, (passage_id, user_id, text))
        conn.commit()

        return jsonify({
            "id": cursor.lastrowid,
            "passage_id": passage_id,
            "text": text,
            "status": "ok",
        }), 201


# ── Study Buddy Matching (Community) ─────────────────────

@exposure_bp.route("/api/community/study-buddies")
@api_error_handler("StudyBuddies")
def api_study_buddies():
    """Return users at similar HSK level who opted in to study partner matching.

    Users opt in via the 'find_study_partner' setting.
    """
    from flask_login import current_user as cu
    if not cu.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401

    user_id = _get_user_id()

    with db.connection() as conn:
        # Get current user's level
        profile = conn.execute("""
            SELECT level_reading, level_listening
            FROM learner_profile WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not profile:
            return jsonify({"buddies": []})

        user_level = max(profile["level_reading"] or 1, profile["level_listening"] or 1)
        level_low = max(1, int(user_level) - 1)
        level_high = int(user_level) + 1

        # Find other opted-in users at similar levels
        rows = conn.execute("""
            SELECT u.display_name,
                   ROUND(MAX(lp.level_reading, lp.level_listening), 1) AS hsk_level,
                   lp.total_sessions,
                   u.last_login_at
            FROM user u
            JOIN learner_profile lp ON lp.user_id = u.id
            WHERE u.id != ?
              AND u.is_active = 1
              AND u.find_study_partner = 1
              AND MAX(lp.level_reading, lp.level_listening) BETWEEN ? AND ?
              AND u.last_login_at >= datetime('now', '-30 days')
            ORDER BY ABS(MAX(lp.level_reading, lp.level_listening) - ?) ASC
            LIMIT 10
        """, (user_id, level_low, level_high, user_level)).fetchall()

        buddies = []
        for r in rows:
            buddies.append({
                "display_name": r["display_name"] or "Learner",
                "hsk_level": r["hsk_level"],
                "total_sessions": r["total_sessions"] or 0,
                "recently_active": True,
            })

    return jsonify({"buddies": buddies, "your_level": round(user_level, 1)})

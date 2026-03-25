"""Mandarin tone sandhi rules, classification, and drill generation.

Implements the four core sandhi rules:
  1. 3rd + 3rd -> 2nd + 3rd
  2. 不 before 4th tone -> 2nd tone
  3. 一 tone changes by context
  4. Full 3rd -> half-3rd before non-3rd

Provides classification of sandhi contexts, database lookup of sandhi-relevant
items, and drill generation for sandhi contrast practice.

Zero Claude tokens at runtime -- all logic is deterministic.
pypinyin used for tone extraction when pinyin is not supplied.
"""

import logging
import random
import re
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from pypinyin import pinyin, Style
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False
    logger.debug("pypinyin not installed -- tone sandhi analysis limited")


# ─────────────────────────────────────────────
# SANDHI RULES
# ─────────────────────────────────────────────

SANDHI_RULES = {
    "third_third": {
        "name": "3rd + 3rd → 2nd + 3rd",
        "description": (
            "When two third tones appear consecutively, "
            "the first changes to second tone"
        ),
        "example": ("你好", "nǐhǎo", "níhǎo"),
        "condition": lambda tones: len(tones) >= 2 and tones[0] == 3 and tones[1] == 3,
    },
    "bu_fourth": {
        "name": "不 before 4th → 2nd tone",
        "description": "不 (bù) changes to bú before a fourth tone syllable",
        "example": ("不是", "bùshì", "búshì"),
        "condition": lambda char, next_tone: char == "不" and next_tone == 4,
    },
    "yi_tone_change": {
        "name": "一 tone changes by context",
        "description": "一 (yī) → yí before 4th tone, yì before 1st/2nd/3rd tone",
        "example_4th": ("一个", "yīgè", "yígè"),
        "example_other": ("一天", "yītiān", "yìtiān"),
    },
    "half_third": {
        "name": "Full 3rd → half-3rd before non-3rd",
        "description": (
            "A third tone before any non-third tone is pronounced "
            "as a half-third (dipping only)"
        ),
        "example": ("你们", "nǐmen", "nǐ(half)men"),
    },
}


# ─────────────────────────────────────────────
# PINYIN TONE EXTRACTION
# ─────────────────────────────────────────────

# Mapping of toned vowels to (base, tone_number)
_TONED_VOWELS = {
    "ā": ("a", 1), "á": ("a", 2), "ǎ": ("a", 3), "à": ("a", 4),
    "ē": ("e", 1), "é": ("e", 2), "ě": ("e", 3), "è": ("e", 4),
    "ī": ("i", 1), "í": ("i", 2), "ǐ": ("i", 3), "ì": ("i", 4),
    "ō": ("o", 1), "ó": ("o", 2), "ǒ": ("o", 3), "ò": ("o", 4),
    "ū": ("u", 1), "ú": ("u", 2), "ǔ": ("u", 3), "ù": ("u", 4),
    "ǖ": ("ü", 1), "ǘ": ("ü", 2), "ǚ": ("ü", 3), "ǜ": ("ü", 4),
}

# Reverse mapping: (base, tone_number) -> toned vowel
_TONE_TO_VOWEL = {v: k for k, v in _TONED_VOWELS.items()}


def _extract_tone_number(syllable: str) -> int:
    """Extract tone number (1-4) from a single pinyin syllable.

    Returns 0 for neutral tone or if no tone mark found.
    """
    for ch in syllable:
        if ch in _TONED_VOWELS:
            return _TONED_VOWELS[ch][1]
    # Check for trailing digit notation (e.g. "ni3")
    if syllable and syllable[-1].isdigit():
        d = int(syllable[-1])
        if 1 <= d <= 4:
            return d
    return 0


def _split_pinyin_syllables(pinyin_str: str) -> list[str]:
    """Split a pinyin string into individual syllables.

    Handles both space-separated and run-together forms.
    """
    if not pinyin_str:
        return []
    # Try space-separated first
    parts = pinyin_str.strip().split()
    if len(parts) > 1:
        return parts
    # Run-together: split on tone marks or capital letters
    # Use a regex that splits between a toned vowel and the next consonant
    syllables = re.findall(
        r"[a-züāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]+[0-4]?",
        pinyin_str.lower(),
    )
    return syllables if syllables else [pinyin_str]


def _get_tone_sequence(hanzi: str, pinyin_str: str | None = None) -> list[int]:
    """Get a list of tone numbers for each syllable.

    Uses the provided pinyin if available, otherwise falls back to pypinyin.
    """
    if pinyin_str:
        syllables = _split_pinyin_syllables(pinyin_str)
        return [_extract_tone_number(s) for s in syllables]

    if _HAS_PYPINYIN:
        try:
            tone_list = pinyin(hanzi, style=Style.TONE3, heteronym=False)
            tones = []
            for group in tone_list:
                syl = group[0] if group else ""
                tones.append(_extract_tone_number(syl))
            return tones
        except Exception:
            pass

    return []


def _replace_tone(syllable: str, new_tone: int) -> str:
    """Replace the tone mark in a pinyin syllable with a different tone.

    Returns the syllable with the new tone mark.
    """
    for ch in syllable:
        if ch in _TONED_VOWELS:
            base, _old_tone = _TONED_VOWELS[ch]
            new_char = _TONE_TO_VOWEL.get((base, new_tone))
            if new_char:
                return syllable.replace(ch, new_char, 1)
    return syllable


# ─────────────────────────────────────────────
# SANDHI CLASSIFICATION
# ─────────────────────────────────────────────

def classify_sandhi_context(hanzi: str, pinyin_str: str = "") -> list[dict]:
    """Parse hanzi and pinyin to identify which sandhi rules apply.

    Args:
        hanzi: Chinese characters to analyze.
        pinyin_str: Optional pinyin with tone marks. If empty, pypinyin is used.

    Returns:
        List of dicts, each with:
            rule_name, position, original_pinyin, actual_pinyin, explanation
    """
    results = []
    try:
        tones = _get_tone_sequence(hanzi, pinyin_str or None)
        syllables = _split_pinyin_syllables(pinyin_str) if pinyin_str else []

        # If we used pypinyin and have no syllable strings, generate them
        if not syllables and _HAS_PYPINYIN:
            try:
                raw = pinyin(hanzi, style=Style.TONE, heteronym=False)
                syllables = [g[0] for g in raw if g]
            except Exception:
                syllables = []

        if not tones:
            return results

        chars = list(hanzi)

        for i in range(len(tones)):
            char = chars[i] if i < len(chars) else ""
            tone_i = tones[i]
            next_tone = tones[i + 1] if i + 1 < len(tones) else None
            syl = syllables[i] if i < len(syllables) else ""
            syllables[i + 1] if i + 1 < len(syllables) else ""

            # Rule 1: 3rd + 3rd -> 2nd + 3rd
            if tone_i == 3 and next_tone == 3:
                actual = _replace_tone(syl, 2) if syl else syl
                results.append({
                    "rule_name": "third_third",
                    "position": i,
                    "original_pinyin": syl,
                    "actual_pinyin": actual,
                    "explanation": (
                        f"'{char}' is 3rd tone followed by 3rd tone "
                        f"'{chars[i + 1] if i + 1 < len(chars) else ''}', "
                        f"so it changes to 2nd tone: {syl} → {actual}"
                    ),
                })

            # Rule 2: 不 before 4th tone -> 2nd tone
            if char == "不" and next_tone == 4:
                actual = _replace_tone(syl, 2) if syl else "bú"
                results.append({
                    "rule_name": "bu_fourth",
                    "position": i,
                    "original_pinyin": syl or "bù",
                    "actual_pinyin": actual,
                    "explanation": (
                        f"不 before 4th-tone '{chars[i + 1] if i + 1 < len(chars) else ''}' "
                        f"changes from bù to bú"
                    ),
                })

            # Rule 3: 一 tone changes
            if char == "一" and next_tone is not None:
                if next_tone == 4:
                    actual = _replace_tone(syl, 2) if syl else "yí"
                    results.append({
                        "rule_name": "yi_tone_change",
                        "position": i,
                        "original_pinyin": syl or "yī",
                        "actual_pinyin": actual,
                        "explanation": (
                            f"一 before 4th-tone syllable changes from yī to yí"
                        ),
                    })
                elif next_tone in (1, 2, 3):
                    actual = _replace_tone(syl, 4) if syl else "yì"
                    results.append({
                        "rule_name": "yi_tone_change",
                        "position": i,
                        "original_pinyin": syl or "yī",
                        "actual_pinyin": actual,
                        "explanation": (
                            f"一 before tone {next_tone} syllable "
                            f"changes from yī to yì"
                        ),
                    })

            # Rule 4: Half-3rd before non-3rd
            if tone_i == 3 and next_tone is not None and next_tone != 3:
                results.append({
                    "rule_name": "half_third",
                    "position": i,
                    "original_pinyin": syl,
                    "actual_pinyin": f"{syl}(half)" if syl else syl,
                    "explanation": (
                        f"'{char}' is 3rd tone before non-3rd tone "
                        f"'{chars[i + 1] if i + 1 < len(chars) else ''}', "
                        f"pronounced as a half-third (dip without rise)"
                    ),
                })

    except Exception as exc:
        logger.debug("classify_sandhi_context error: %s", exc)

    return results


# ─────────────────────────────────────────────
# DATABASE LOOKUP
# ─────────────────────────────────────────────

def get_sandhi_pairs(conn: sqlite3.Connection, hsk_level: int = 3) -> list[dict]:
    """Query content_item for multi-character words where sandhi applies.

    Filters by HSK level and returns items with sandhi rule metadata.
    """
    try:
        rows = conn.execute("""
            SELECT id, hanzi, pinyin, english, hsk_level
            FROM content_item
            WHERE status = 'drill_ready'
              AND review_status = 'approved'
              AND LENGTH(hanzi) >= 2
              AND hsk_level <= ?
            ORDER BY hsk_level ASC, hanzi ASC
        """, (hsk_level,)).fetchall()
    except sqlite3.OperationalError:
        logger.debug("content_item table not available for sandhi lookup")
        return []

    results = []
    for row in rows:
        try:
            item = dict(row) if not isinstance(row, dict) else row
            contexts = classify_sandhi_context(item["hanzi"], item["pinyin"])
            # Only include items where a substantive sandhi rule fires
            # (skip half_third-only since it is subtle and less drillable)
            substantive = [
                c for c in contexts
                if c["rule_name"] in ("third_third", "bu_fourth", "yi_tone_change")
            ]
            if substantive:
                primary = substantive[0]
                results.append({
                    "item_id": item["id"],
                    "hanzi": item["hanzi"],
                    "pinyin": item["pinyin"],
                    "sandhi_rule": primary["rule_name"],
                    "original_pronunciation": primary["original_pinyin"],
                    "actual_pronunciation": primary["actual_pinyin"],
                })
        except Exception:
            continue

    return results


# ─────────────────────────────────────────────
# DRILL GENERATION
# ─────────────────────────────────────────────

def generate_sandhi_drill(
    conn: sqlite3.Connection,
    item: dict,
    user_id: int = None,
) -> dict:
    """Generate a sandhi contrast drill for a given item.

    The drill shows hanzi and asks how it is actually pronounced.
    The correct answer is the sandhi-modified pronunciation; the distractor
    is the citation (dictionary) form.

    Args:
        conn: Database connection.
        item: Dict with at least hanzi, pinyin, sandhi_rule.
              Should come from get_sandhi_pairs() or get_sandhi_items_for_session().
        user_id: Optional user id (reserved for future personalisation).

    Returns:
        Dict with type, hanzi, question, correct_answer, distractor,
        explanation, rule_name.
    """
    hanzi = item.get("hanzi", "")
    pinyin_str = item.get("pinyin", "")
    rule_name = item.get("sandhi_rule", "")

    contexts = classify_sandhi_context(hanzi, pinyin_str)
    primary = None
    for ctx in contexts:
        if ctx["rule_name"] == rule_name:
            primary = ctx
            break
    if primary is None and contexts:
        primary = contexts[0]
        rule_name = primary["rule_name"]

    if primary is None:
        # Fallback: cannot determine sandhi context
        return {
            "type": "sandhi_contrast",
            "hanzi": hanzi,
            "question": f"How is {hanzi} actually pronounced?",
            "correct_answer": pinyin_str,
            "distractor": pinyin_str,
            "explanation": "No sandhi rule detected for this item.",
            "rule_name": "",
        }

    primary["original_pinyin"]
    actual = primary["actual_pinyin"]
    rule_info = SANDHI_RULES.get(rule_name, {})

    # Build the full actual pronunciation by replacing the affected syllable
    syllables = _split_pinyin_syllables(pinyin_str)
    pos = primary.get("position", 0)
    if syllables and pos < len(syllables):
        correct_syllables = list(syllables)
        correct_syllables[pos] = actual
        correct_full = " ".join(correct_syllables)
    else:
        correct_full = actual

    # The distractor is the citation (unmodified) form
    distractor_full = " ".join(syllables) if syllables else pinyin_str

    # Make sure correct and distractor are different
    if correct_full == distractor_full:
        distractor_full = pinyin_str

    explanation = (
        f"{rule_info.get('name', rule_name)}: "
        f"{rule_info.get('description', primary['explanation'])}"
    )

    return {
        "type": "sandhi_contrast",
        "hanzi": hanzi,
        "question": f"How is {hanzi} actually pronounced?",
        "correct_answer": correct_full,
        "distractor": distractor_full,
        "explanation": explanation,
        "rule_name": rule_name,
    }


# ─────────────────────────────────────────────
# SESSION ITEM SELECTION
# ─────────────────────────────────────────────

def get_sandhi_items_for_session(
    conn: sqlite3.Connection,
    user_id: int,
    hsk_level: int,
    max_items: int = 3,
) -> list[dict]:
    """Get sandhi-relevant items for a study session.

    Prioritises items the user has previously gotten wrong on tone drills,
    then fills remaining slots from the general sandhi pair pool.

    Returns ready-to-use drill dicts (output of generate_sandhi_drill).
    """
    drills = []

    # Phase 1: Items with tone errors in review history
    try:
        error_rows = conn.execute("""
            SELECT DISTINCT re.content_item_id,
                   ci.hanzi, ci.pinyin, ci.english, ci.hsk_level
            FROM review_event re
            JOIN content_item ci ON ci.id = re.content_item_id
            WHERE re.user_id = ?
              AND re.correct = 0
              AND re.drill_type = 'tone'
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
              AND ci.hsk_level <= ?
              AND LENGTH(ci.hanzi) >= 2
            ORDER BY re.created_at DESC
            LIMIT ?
        """, (user_id, hsk_level, max_items * 2)).fetchall()
    except sqlite3.OperationalError:
        error_rows = []

    seen_ids = set()
    for row in error_rows:
        if len(drills) >= max_items:
            break
        try:
            item = dict(row) if not isinstance(row, dict) else row
            contexts = classify_sandhi_context(item["hanzi"], item["pinyin"])
            substantive = [
                c for c in contexts
                if c["rule_name"] in ("third_third", "bu_fourth", "yi_tone_change")
            ]
            if substantive:
                sandhi_item = {
                    "hanzi": item["hanzi"],
                    "pinyin": item["pinyin"],
                    "sandhi_rule": substantive[0]["rule_name"],
                    "item_id": item["content_item_id"]
                    if "content_item_id" in item else item.get("id"),
                }
                drill = generate_sandhi_drill(conn, sandhi_item, user_id)
                item_id = sandhi_item.get("item_id")
                if item_id not in seen_ids:
                    drill["content_item_id"] = item_id
                    drills.append(drill)
                    seen_ids.add(item_id)
        except Exception:
            continue

    # Phase 2: Fill remaining from general sandhi pool
    if len(drills) < max_items:
        pool = get_sandhi_pairs(conn, hsk_level)
        random.shuffle(pool)
        for pair in pool:
            if len(drills) >= max_items:
                break
            item_id = pair.get("item_id")
            if item_id in seen_ids:
                continue
            try:
                drill = generate_sandhi_drill(conn, pair, user_id)
                drill["content_item_id"] = item_id
                drills.append(drill)
                seen_ids.add(item_id)
            except Exception:
                continue

    return drills


# ─────────────────────────────────────────────
# INTELLIGENCE ANALYZER
# ─────────────────────────────────────────────

def analyze_sandhi_coverage(conn: sqlite3.Connection) -> list[dict]:
    """Analyzer for the intelligence system.

    Checks how many sandhi-relevant items exist in the content library
    and whether learners are being exposed to them.
    """
    from ..intelligence._base import _finding

    findings = []

    # 1. Check total sandhi-eligible items in library
    try:
        total_multi = conn.execute("""
            SELECT COUNT(*) FROM content_item
            WHERE status = 'drill_ready'
              AND review_status = 'approved'
              AND LENGTH(hanzi) >= 2
        """).fetchone()
        multi_count = (total_multi[0] if total_multi else 0) or 0

        sandhi_items = get_sandhi_pairs(conn, hsk_level=9)
        sandhi_count = len(sandhi_items)

        if multi_count > 0 and sandhi_count == 0:
            findings.append(_finding(
                dimension="methodology",
                severity="medium",
                title="No sandhi-eligible items found in content library",
                analysis=(
                    f"{multi_count} multi-character items exist but none "
                    f"trigger sandhi rules. This may indicate pinyin data "
                    f"quality issues or a content gap."
                ),
                recommendation=(
                    "Audit pinyin annotations on multi-character items. "
                    "Ensure 3rd-3rd pairs, 不-phrases, and 一-phrases are present."
                ),
                claude_prompt=(
                    "Check content_item for multi-char items with pinyin "
                    "that should trigger sandhi rules."
                ),
                impact="Learners miss critical pronunciation training.",
                files=["mandarin/ai/tone_sandhi.py"],
            ))
        elif sandhi_count > 0 and sandhi_count < 10:
            findings.append(_finding(
                dimension="methodology",
                severity="low",
                title=f"Only {sandhi_count} sandhi-eligible items in library",
                analysis=(
                    f"The content library has {sandhi_count} items that trigger "
                    f"sandhi rules. A richer set would improve tone sandhi drilling."
                ),
                recommendation=(
                    "Add more items featuring 3rd+3rd combinations, "
                    "不+4th tone phrases, and 一+tone patterns."
                ),
                claude_prompt=(
                    "Generate additional sandhi-rich vocabulary items "
                    "for the content library."
                ),
                impact="Limited sandhi drill variety may reduce learning gains.",
                files=["mandarin/ai/tone_sandhi.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 2. Check learner exposure to sandhi drills
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM review_event
            WHERE drill_type = 'tone_sandhi'
              AND created_at >= datetime('now', '-30 days')
        """).fetchone()
        sandhi_reviews = (row[0] if row else 0) or 0

        total_tone = conn.execute("""
            SELECT COUNT(*) FROM review_event
            WHERE drill_type IN ('tone', 'tone_sandhi')
              AND created_at >= datetime('now', '-30 days')
        """).fetchone()
        total_tone_reviews = (total_tone[0] if total_tone else 0) or 0

        if total_tone_reviews > 20 and sandhi_reviews == 0:
            findings.append(_finding(
                dimension="methodology",
                severity="low",
                title="No sandhi drill exposure in last 30 days",
                analysis=(
                    f"{total_tone_reviews} tone drills completed but zero "
                    f"sandhi drills. Learner is missing sandhi practice."
                ),
                recommendation=(
                    "Ensure tone_sandhi is included in drill type selection. "
                    "Check scheduler TONE_SANDHI_BOOST_WEIGHT."
                ),
                claude_prompt=(
                    "Verify tone_sandhi appears in drill options and "
                    "TONE_SANDHI_BOOST_WEIGHT is non-zero."
                ),
                impact="Tone sandhi is a common error source for learners.",
                files=[
                    "mandarin/ai/tone_sandhi.py",
                    "mandarin/scheduler.py",
                ],
            ))
    except sqlite3.OperationalError:
        pass

    return findings


ANALYZERS = [analyze_sandhi_coverage]

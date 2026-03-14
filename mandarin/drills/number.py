"""Number system drill: cardinal, date, price, phone, time, units."""

import json
import os
import random
from typing import Optional

from .base import DrillResult, format_hanzi, format_hanzi_inline, _run_mc_input

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")

# ── Lazy-loaded cache ──────────────────────────────
_NUMBER_DRILLS_CACHE = None


def _get_number_drills():
    global _NUMBER_DRILLS_CACHE
    if _NUMBER_DRILLS_CACHE is None:
        path = os.path.join(_DATA_DIR, "number_drills.json")
        with open(path) as f:
            data = json.load(f)
        _NUMBER_DRILLS_CACHE = data.get("entries", data)
    return _NUMBER_DRILLS_CACHE


def run_number_system_drill(item: dict, conn, show_fn, input_fn,
                            prominent: bool = True) -> Optional[DrillResult]:
    """Show an arabic number/value → pick the correct Chinese expression (MC).

    Filters entries by hsk_level <= item's level. Returns None if no suitable
    entries found (dispatcher falls back to MC).
    """
    entries = _get_number_drills()
    item_level = item.get("hsk_level") or 3

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    arabic = entry["arabic"]
    correct = entry["chinese"]
    pinyin = entry.get("pinyin", "")
    entry_type = entry.get("type", "cardinal")

    # Build distractors
    distractors = list(entry.get("distractors", []))
    while len(distractors) < 3:
        others = [e["chinese"] for e in candidates
                  if e["chinese"] != correct and e["chinese"] not in distractors]
        if others:
            distractors.append(random.choice(others))
        else:
            break

    options = [correct] + distractors[:3]
    random.shuffle(options)

    type_labels = {
        "cardinal": "Number",
        "date": "Date",
        "price": "Price",
        "phone": "Phone number",
        "time": "Time",
        "units": "Measurement",
    }
    type_label = type_labels.get(entry_type, "Number")

    show_fn(f"\n  {type_label}: [bold]{arabic}[/bold]", prominent=prominent)

    note = entry.get("note")
    if note and entry_type == "units":
        show_fn(f"  [dim](convert to Chinese units)[/dim]")

    show_fn("")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "number_system", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → {format_hanzi_inline(correct)}"
        if pinyin:
            feedback += f"  [{pinyin}]"
    if note:
        feedback += f"\n  [dim]{note}[/dim]"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="number_system", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "number",
        feedback=feedback,
    )

#!/usr/bin/env python3
"""
Rewrite dialogue options so each player turn has:
  - 1 correct answer (the highest-scored original option, set to 1.0)
  - 2 off-topic distractors pulled from OTHER scenarios at the same HSK level
    (scored 0.0, with feedback explaining they don't fit)

This turns the drill from a register-nuance test into a comprehension test:
only one option actually answers the NPC's question.

Deterministic: random.seed(42), so re-running produces identical output.
"""

import json
import os
import random
from collections import defaultdict
from pathlib import Path

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"
SEED = 42


def load_scenarios():
    """Load all scenario JSONs. Returns {filename: data}."""
    scenarios = {}
    for f in sorted(SCENARIO_DIR.iterdir()):
        if f.suffix != ".json":
            continue
        with open(f, encoding="utf-8") as fh:
            scenarios[f.name] = json.load(fh)
    return scenarios


def build_response_pool(scenarios):
    """
    Build a pool of best responses keyed by HSK level.
    Each entry: (scenario_filename, turn_index, option_dict)
    We take the highest-scored option from every player turn.
    """
    pool = defaultdict(list)
    for fname, data in scenarios.items():
        hsk = data["hsk_level"]
        for ti, turn in enumerate(data["tree"]["turns"]):
            if turn["speaker"] != "player":
                continue
            best = max(turn["options"], key=lambda o: o["score"])
            pool[hsk].append((fname, ti, best))
    return pool


def pick_distractors(pool, hsk_level, source_fname, source_turn_idx, rng, n=2):
    """
    Pick n distractors from the pool at the same HSK level,
    excluding the source scenario+turn. Falls back to adjacent levels
    if not enough candidates.
    """
    # Candidates: same HSK level, different scenario OR different turn
    candidates = [
        entry for entry in pool[hsk_level]
        if entry[0] != source_fname
    ]

    # Fallback to adjacent levels if needed
    if len(candidates) < n:
        for offset in [1, -1, 2, -2]:
            adj = hsk_level + offset
            if adj in pool:
                candidates.extend(pool[adj])
            if len(candidates) >= n:
                break

    chosen = rng.sample(candidates, min(n, len(candidates)))
    return [entry[2] for entry in chosen]  # return the option dicts


def make_distractor(option, prompt_en):
    """
    Build a distractor option from a borrowed response.
    Keep text_zh/text_pinyin/text_en, set score=0.0, replace feedback.
    """
    distractor = {}
    for key in ("text_zh", "text_pinyin", "text_en"):
        if key in option:
            distractor[key] = option[key]
    distractor["score"] = 0.0
    distractor["feedback"] = (
        f"Off-topic \u2014 you were asked to {prompt_en.lower().rstrip('.')}, "
        f"but this doesn't fit the conversation."
    )
    return distractor


def rewrite_all():
    scenarios = load_scenarios()
    pool = build_response_pool(scenarios)
    rng = random.Random(SEED)

    stats = {"scenarios": 0, "turns_rewritten": 0}

    for fname, data in scenarios.items():
        hsk = data["hsk_level"]
        modified = False

        for ti, turn in enumerate(data["tree"]["turns"]):
            if turn["speaker"] != "player":
                continue

            options = turn["options"]
            prompt_en = turn.get("prompt_en", "respond appropriately")

            # Keep the best option, set its score to 1.0
            best = max(options, key=lambda o: o["score"])
            best["score"] = 1.0

            # Pick 2 distractors from other scenarios
            distractors = pick_distractors(pool, hsk, fname, ti, rng, n=2)
            distractor_opts = [
                make_distractor(d, prompt_en) for d in distractors
            ]

            # Assemble new options: correct first, then distractors, then shuffle
            new_options = [best] + distractor_opts
            rng.shuffle(new_options)

            turn["options"] = new_options
            modified = True
            stats["turns_rewritten"] += 1

        if modified:
            stats["scenarios"] += 1
            out_path = SCENARIO_DIR / fname
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=4)

    return stats


if __name__ == "__main__":
    stats = rewrite_all()
    print(f"Rewrote {stats['turns_rewritten']} player turns "
          f"across {stats['scenarios']} scenarios.")

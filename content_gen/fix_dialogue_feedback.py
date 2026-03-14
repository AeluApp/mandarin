#!/usr/bin/env python3
"""
Batch 1 Track 2: Fix dialogue feedback language across all j-series dialogues.

Changes:
1. Remove "Off-topic — " prefix from wrong-answer feedback (keep the observation)
2. Remove literary-criticism language from correct-answer feedback
3. Make feedback more observational and less evaluative
"""
import json
import os
import glob
import re

# Patterns to remove from correct-answer feedback
PRAISE_REMOVALS = [
    (r'^Evocative (image |observation )?— ', ''),
    (r'^Beautifully? ', ''),
    (r'^Perfectly? ', ''),
    (r'^Thoughtful(ly)? ', ''),
    (r'^Insightful(ly)? ', ''),
    (r'^Powerful(ly)? ', ''),
    (r'^Poetic(ally)? ', ''),
    (r'^Beautiful ', ''),
    (r'^Elegant(ly)? ', ''),
    (r'^Lovely ', ''),
    (r'^Wonderful ', ''),
    (r'^Brilliant(ly)? ', ''),
    (r'^Appreciative and curious — ', ''),
    (r'^Appreciative and honest — ', ''),
    (r'^Reflective and poetic — ', ''),
    (r'^Open and grateful — ', ''),
    (r'^Generous and specific — ', ''),
    (r'^Warm and perceptive — ', ''),
    (r'^Eager and honest — ', ''),
    (r'^Self-deprecating humor — ', ''),
    (r' — a natural iyashikei response\.?', '.'),
    (r' — appreciative and grounded\.?', '.'),
    (r' — .*perfectly captures.*\.?', '.'),
    (r'Hilarious escalation — ', ''),
    (r'Perfect landing — ', ''),
    (r'Meta-irony of teaching Zhuangzi: ', ''),
]

# Fix "Off-topic — " in wrong-answer feedback
OFF_TOPIC_FIX = re.compile(r'^Off-topic\s*—\s*', re.IGNORECASE)

# Fix generic "misses the point" phrasing
MISSES_FIX = re.compile(r'^Misses the point\s*—\s*', re.IGNORECASE)

# Fix "reduces X to Y" academic phrasing
REDUCES_FIX = re.compile(r'^Reduces\s+', re.IGNORECASE)

stats = {
    'files_processed': 0,
    'off_topic_fixed': 0,
    'praise_fixed': 0,
    'misses_fixed': 0,
    'reduces_fixed': 0,
}

for filepath in sorted(glob.glob('dialogues/j*_dlg_*.json')):
    with open(filepath) as f:
        try:
            d = json.load(f)
        except:
            continue

    changed = False
    stats['files_processed'] += 1

    for turn in d['tree']['turns']:
        if turn['speaker'] != 'player':
            continue

        for opt in turn.get('options', []):
            fb = opt.get('feedback', '')
            score = opt.get('score', 0)
            original_fb = fb

            if score == 0 or score == 0.0:
                # Wrong answer: remove "Off-topic — " prefix
                if OFF_TOPIC_FIX.search(fb):
                    fb = OFF_TOPIC_FIX.sub('', fb)
                    # Capitalize first letter
                    if fb:
                        fb = fb[0].upper() + fb[1:]
                    stats['off_topic_fixed'] += 1

                if MISSES_FIX.search(fb):
                    fb = MISSES_FIX.sub('', fb)
                    if fb:
                        fb = fb[0].upper() + fb[1:]
                    stats['misses_fixed'] += 1

                if REDUCES_FIX.search(fb):
                    fb = REDUCES_FIX.sub('This reduces ', fb)
                    stats['reduces_fixed'] += 1

            elif score == 1.0 or score == 3 or score == 2:
                # Correct/good answers: remove literary-criticism language
                for pattern, replacement in PRAISE_REMOVALS:
                    new_fb = re.sub(pattern, replacement, fb)
                    if new_fb != fb:
                        fb = new_fb
                        stats['praise_fixed'] += 1
                        break  # Only apply first matching pattern

                # Capitalize after removal
                if fb and fb[0].islower():
                    fb = fb[0].upper() + fb[1:]

            if fb != original_fb:
                opt['feedback'] = fb
                changed = True

    if changed:
        with open(filepath, 'w') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

print(f"Files processed: {stats['files_processed']}")
print(f"Off-topic labels removed: {stats['off_topic_fixed']}")
print(f"Praise language fixed: {stats['praise_fixed']}")
print(f"'Misses the point' fixed: {stats['misses_fixed']}")
print(f"'Reduces' fixed: {stats['reduces_fixed']}")
print(f"Total feedback lines fixed: {sum(v for k,v in stats.items() if k != 'files_processed')}")

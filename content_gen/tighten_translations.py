#!/usr/bin/env python3
"""
Priority 7: Tighten English translations across all passages.
Remove cushioning conjunctions, support-copy phrasing, over-formality.
"""
import json
import re

# Translation tightening rules
REPLACEMENTS = [
    # Remove cushioning "but" when Chinese uses no conjunction
    # These are targeted — only replace when the pattern is clear

    # Over-formal constructions
    (r'\bIn that moment\b', 'Then'),
    (r'\bAt that moment\b', 'Then'),
    (r'\bIn that instant\b', 'Then'),

    # Support-copy hedging
    (r'\bIt is worth noting that\b', ''),
    (r'\bIt should be noted that\b', ''),
    (r'\bIt goes without saying that\b', ''),

    # Over-explained transitions
    (r'\bWhat I mean to say is that\b', ''),
    (r'\bWhat I\'m trying to say is\b', ''),

    # Overly formal "one" as pronoun when "you" works
    (r'\bone cannot help but\b', "you can't help but"),
    (r'\bOne cannot help but\b', "You can't help but"),
    (r'\bone can\'t help but\b', "you can't help but"),

    # Stiff formality
    (r'\bregardless of whether\b', 'whether or not'),
    (r'\birrespective of\b', 'regardless of'),
    (r'\bin the process of\b', 'while'),
    (r'\bfor the purpose of\b', 'to'),
    (r'\bwith regard to\b', 'about'),
    (r'\bwith respect to\b', 'about'),
    (r'\bin terms of\b', 'in'),
    (r'\bthe fact that\b', 'that'),

    # Padding
    (r'\bactually and truly\b', 'truly'),
    (r'\beach and every\b', 'every'),
    (r'\bfirst and foremost\b', 'first'),

    # Double em-dashes to single
    (r' — — ', ' — '),
]

stats = {'files': 0, 'replacements': 0}

for level in range(1, 10):
    fname = f'passages_hsk{level}.json'
    with open(fname) as f:
        passages = json.load(f)

    changed = False
    for p in passages:
        en = p['text_en']
        original = en

        for pattern, replacement in REPLACEMENTS:
            en = re.sub(pattern, replacement, en)

        # Clean up double spaces from removals
        en = re.sub(r'  +', ' ', en)
        # Clean up space before period
        en = re.sub(r' \.', '.', en)
        # Clean up leading space after removal
        en = re.sub(r'^\s+', '', en)
        # Capitalize after period if needed
        en = re.sub(r'\. ([a-z])', lambda m: '. ' + m.group(1).upper(), en)

        if en != original:
            p['text_en'] = en
            changed = True
            stats['replacements'] += 1

    if changed:
        with open(fname, 'w') as f:
            json.dump(passages, f, ensure_ascii=False, indent=2)

    stats['files'] += 1

print(f"Processed {stats['files']} files")
print(f"Translations tightened: {stats['replacements']}")

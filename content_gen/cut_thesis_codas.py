#!/usr/bin/env python3
"""
Cut thesis codas from HSK 7-9 passage text_en fields.

Identifies and removes final 1-2 sentences that explicitly restate
the theme/moral already embodied in the preceding scene.
"""

import json
import re
import sys
from pathlib import Path

# --- Thesis-coda detection patterns ---
# Each is (pattern, description) for reporting
CODA_PATTERNS = [
    # === EXPLICIT THESIS MARKERS ===
    # "Perhaps/Maybe X is/was really/truly..."
    (r'\bperhaps\b.*\b(?:really|truly|what)\b', 'perhaps-thesis'),
    (r'\bmaybe\b.*\b(?:really|truly|the real)\b', 'maybe-thesis'),

    # "In the end / ultimately / after all"
    (r'\bin the end\b', 'in-the-end'),
    (r'\bultimately\b', 'ultimately'),
    (r'\bafter all\b', 'after-all'),

    # "This/That is what makes X..."
    (r'\b(?:this|that|that\'s|it\'s) (?:is )?what makes\b', 'this-is-what-makes'),
    (r'\b(?:this|that|that\'s) (?:is )?what\b.*\bmeans\b', 'what-X-means'),

    # "What X teaches/shows/tells us"
    (r'\bwhat\b.*\bteaches?\b', 'what-teaches'),
    (r'\bwhat\b.*\breveals?\b', 'what-reveals'),

    # === ABSTRACT MEANING DECLARATIONS ===
    # "The real/true/deepest meaning/essence/value"
    (r'\bthe (?:real|true|deepest|highest|most (?:precious|important|beautiful|moving|profound))\b', 'superlative-abstraction'),
    (r'\bthe essence of\b', 'essence-of'),

    # "X isn't just/merely Y — it's Z"
    (r'\bisn\'t (?:just|merely|really|simply)\b', 'isnt-just'),
    (r'\bis not (?:just|merely|really|simply)\b', 'is-not-just'),
    (r'\bnot (?:just|merely|simply) (?:a|an|the|about)\b', 'not-merely'),

    # === SUDDEN UNDERSTANDING ===
    (r'\bi suddenly (?:understood|realized|felt|grasped)\b', 'sudden-realization'),
    (r'\bi came to (?:understand|realize)\b', 'came-to-understand'),
    (r'\bthen i (?:understood|realized|felt)\b', 'then-I-realized'),
    (r'\bthat (?:remark|sentence|thought|moment|word|idea) (?:stayed with|made me|stayed in)\b', 'remark-stayed'),

    # === REFLECTIVE "I THINK" CODAS ===
    (r'\bsometimes i (?:think|wonder|feel)\b', 'sometimes-I-think'),
    (r'\bi think (?:that\'s|this is|perhaps|the)\b', 'i-think-thesis'),
    (r'\bi (?:believe|feel|suspect)\b.*\b(?:perhaps|maybe|really|truly)\b', 'I-believe-thesis'),

    # === "FOR X, Y ISN'T Z" ===
    (r'\bfor (?:him|her|them|me|us|these|those|this|that|some|many|such|the)\b.*\b(?:isn\'t|is not|isn\'t just|is not just)\b', 'for-X-isnt'),

    # === ERA/AGE GENERALIZATIONS ===
    (r'\bwe live in an? (?:era|age|world|time)\b', 'we-live-in-era'),
    (r'\bin an? (?:era|age|world|society)\b.*\b(?:where|when|of|that)\b', 'in-an-era'),
    (r'\bin (?:this|our|today\'s) (?:era|age|world|society|time)\b', 'this-era'),
    (r'\bin an era\b', 'in-era'),

    # === WHAT-DISAPPEARS/WHAT-REMAINS ===
    (r'\bwhat (?:disappears|vanishes|is lost|we lose|they lose)\b', 'what-disappears'),
    (r'\bwhat (?:remains|survives|endures|stays)\b', 'what-remains'),
    (r'\bcan replicate\b.*\bcannot replicate\b', 'can-cannot'),

    # === CONDITIONAL LOSS "IF ONE DAY" ===
    (r'\bif one day\b.*\bwhat\b.*\bloses?\b', 'if-one-day-loss'),

    # === ABSTRACT DEFINITIONS ===
    # "X is the Y of Z" (abstract conceptual definitions)
    (r'\b(?:composure|patience|kindness|loneliness|beauty|silence|wisdom|tenderness|freedom|dignity)\b.*\bisn\'t\b.*\bbut\b', 'virtue-redefinition'),
    (r'\b(?:composure|patience|kindness|loneliness|beauty|silence|wisdom|tenderness|freedom|dignity)\b.*\bis not\b.*\bbut\b', 'virtue-redefinition-2'),

    # "This is probably/perhaps the most..."
    (r'\bthis is (?:probably|perhaps|maybe)\b', 'this-is-probably'),

    # === WHAT-X-REALLY-IS ===
    (r'\bwhat (?:he|she|they|we|it|people|one|the|those|these)\b.*\breally\b', 'what-X-really'),

    # === X IS THE LAST/ONLY/MOST ===
    (r'\bthe (?:last|final|only)\b.*\b(?:luxury|tenderness|resistance|defense|shelter|refuge|warmth|freedom)\b', 'last-X'),

    # === GENERALIZING OBSERVATIONS ===
    # "A city's X is measured by Y"
    (r'\ba city\'s\b.*\b(?:measured|determined|reflected|shown)\b', 'city-measured-by'),
    # "When X disappears, what disappears is..."
    (r'\bwhen (?:a|an|the)\b.*\b(?:closes?|disappears?|vanishes?|dies?)\b.*\bwhat\b', 'when-X-disappears-what'),

    # === ANALOGIES AS THESIS ===
    (r'\b(?:just as|like a|how similar)\b.*\b(?:human|people|we|society|life)\b', 'analogy-to-humanity'),

    # === EXPLICIT MORAL/LESSON ===
    (r'\bthis (?:is|was) (?:a|the) (?:lesson|truth|insight|realization|reminder)\b', 'this-is-lesson'),
    (r'\b(?:it|that) (?:taught|teaches|reminded|reminds) (?:me|us|him|her|them)\b', 'it-taught-me'),
    (r'\bwhat (?:it|this|that|they) taught\b', 'what-it-taught'),

    # === "A GOOD X SHOULD BE..." ===
    (r'\ba good (?:shop|store|restaurant|city|space|place|book|piece|person|life|relationship)\b.*\b(?:should|sells not|offers not)\b', 'good-X-should'),

    # === HANDS/IDENTITY THESIS ===
    (r'\bhands? (?:are|is) (?:a|the|an)\b.*\b(?:biography|record|history|testament)\b', 'hands-are-biography'),

    # === EXPLICIT NAMING OF THEME ===
    (r'\bthe (?:archaeology|ecology|topography|geography|anatomy|physics|philosophy|economics|diplomacy)\b.*\bof\b.*\b(?:pocket|smell|silence|sound|queue|wait|park|bench)\b', 'naming-discipline'),

    # === THIS STATEMENT REVEALS / TRUTH ===
    (r'\bthis (?:statement|observation|remark|insight) reveals\b', 'statement-reveals'),
    (r'\ba profound truth\b', 'profound-truth'),

    # === SPECIFIC PATTERNS FROM CORPUS ===
    # "Beauty isn't scarce—beauty just needs..."
    (r'\bbeauty\b.*\b(?:isn\'t scarce|just needs)\b', 'beauty-thesis'),
    # "The fishing rod is just a posture; what they're really fishing for..."
    (r'\bwhat they\'re really\b', 'what-theyre-really'),
    # "Behind X hides Y"
    (r'\bbehind\b.*\bhides?\b.*\b(?:longing|meaning|truth|love|warmth|fear|hope)\b', 'behind-hides'),
    # "The right to X is..."
    (r'\bthe right to (?:idleness|silence|leisure|rest)\b', 'right-to-X'),
    # "Inheritance is sometimes that fragile"
    (r'\binheritance is\b', 'inheritance-is'),
    # "Those X were never Y—their meaning lay in Z"
    (r'\btheir (?:meaning|value|worth|beauty|preciousness) (?:lay|lies|resided|is)\b', 'their-meaning-lay'),
    # "When efficiency becomes the only..."
    (r'\bwhen efficiency becomes\b', 'when-efficiency'),
    # "We've grown too accustomed"
    (r'\bwe\'ve grown too accustomed\b', 'grown-accustomed'),
    # "X can never eliminate"
    (r'\bcan never (?:eliminate|replicate|reproduce|recapture)\b', 'can-never-eliminate'),
    # "Learning to X is perhaps..."
    (r'\blearning to\b.*\bis (?:perhaps|maybe|probably)\b', 'learning-to-is-perhaps'),
    # "This X is more Y than..."
    (r'\bhas more (?:warmth|weight|meaning|value|power|persuasive)\b.*\bthan\b', 'more-X-than'),
    # "This counterintuitive..."
    (r'\b(?:counterintuitive|paradox|irony|ironic)\b', 'counterintuitive'),
    # Young vs old gaze
    (r'\byoung (?:people|eyes)\b.*\b(?:can\'t|cannot)\b.*\b(?:gaze|look|see)\b', 'young-cant'),
    # "The fog shifts again"
    (r'\bthe fog shifts\b', 'fog-shifts'),
]

# Patterns that indicate the sentence should be KEPT
KEEP_PATTERNS = [
    r'[\'\"]\s*$',                   # Ends with closing quote (dialogue)
    r'^[\'"]',                       # Starts with dialogue
    r'\b(?:he|she) (?:said|asked|replied|answered|added|whispered)\b',
    r'\b(?:he|she) (?:went|walked|left|sat|stood|picked|put|placed|rode|carried)\b',
    r'\b(?:sun|rain|wind|snow|light|shadow)\b.*\b(?:fell|shone|blew|came|cast|poured|hit|struck)\b',
    r'\bo\'clock\b',                 # Specific time
    r'\bcursed?\b.*\bgrins?\b',      # Concrete scene
    r'\bno trace\b',                 # Concrete image (keep j9_observe_001)
    r'\bstill there\b$',            # Concrete observation
    r'\bcup remembers\b',            # Poetic concrete (keep j9_observe_003)
]

# Specific passage IDs to SKIP (good endings that patterns might incorrectly flag)
SKIP_IDS = {
    'j7_observe_004',  # "I'm the only fool" - concrete image, comic
    'j7_comedy_001', 'j7_comedy_002', 'j7_comedy_003', 'j7_comedy_004', 'j7_comedy_005',
    'j8_comedy_001', 'j8_comedy_002', 'j8_comedy_003', 'j8_comedy_004',
    'j9_comedy_001',  # Comedy passages - punchline IS the point
    'j7_observe_005',  # Dialogue ending
    'j7_mystery_001', 'j7_mystery_002', 'j7_mystery_003', 'j7_mystery_004',
    'j7_mystery_005', 'j7_mystery_006', 'j7_mystery_007',  # Mystery - reveal IS the point
    'j8_mystery_001', 'j8_mystery_002', 'j8_mystery_003', 'j8_mystery_004', 'j8_mystery_005',
    'j9_mystery_083', 'j9_mystery_084', 'j9_mystery_085', 'j9_mystery_086',
    'j9_mystery_087', 'j9_mystery_088', 'j9_mystery_089', 'j9_mystery_090',
    'j9_mystery_091', 'j9_mystery_092', 'j9_mystery_093', 'j9_mystery_094',
    'j9_mystery_095', 'j9_mystery_096', 'j9_mystery_097', 'j9_mystery_098',
    'j7_observe_048',  # "Waiting itself was his catch." - perfect
    'j9_observe_001',  # "No trace of anything" - perfect concrete
    'j9_observe_003',  # "The cup remembers for him" - perfect
    'j9_observe_005',  # "Only Chinese can do that" - comic
    'j8_observe_003',  # Comedy ending (counting "let me tell you")
    'j8_observe_010',  # Comedy ending (the cashier scene)
    'j8_observe_011',  # "A drawer is a cemetery" - the observation IS the point
    'j8_observe_013',  # "She'll forever think today's rain wasn't that heavy" - perfect
    'j8_observe_014',  # "The next day's noodles were genuinely delicious" - concrete
    'j8_observe_020',  # "I've never seen this cat" - concrete
    'j8_observe_019',  # "I'm thirty-two, but on that fridge door I'm forever five" - the point
    'j7_inst_001',     # Dialogue ending
    'j7_inst_002',     # Dialogue ending
    'j7_inst_004',     # Dialogue ending
    'j7_inst_005',     # Dialogue ending
    'j8_inst_002',     # Dialogue ending (Zhao Min)
    'j8_inst_005',     # Factual observation about market
    'j7_observe_016',  # Dialogue ending
    'j7_observe_027',  # Concrete scene
    'j7_observe_028',  # Concrete scene (piano)
    'j7_identity_006', # "What my grandmother passed down" - the punchline
    'j7_system_076',   # Factual observation
    'j7_system_077',   # Dialogue ending
    'j7_system_078',   # Dialogue ending
    'j7_system_079',   # Factual/comic observation
    'j7_system_080',   # Definition (the point of the passage)
    'j7_urban_007',    # Concrete scene
    'j7_urban_008',    # Concrete scene
    'j7_urban_009',    # Concrete image
    'j8_urban_002',    # Factual observation about elevator
    'j8_observe_004',  # Concrete observation (clothesline)
    'j8_observe_009',  # Factual observation about sound
    'j8_observe_012',  # Factual observation
    'j8_city_042',     # Concrete scene
    'j8_city_045',     # Concrete scene (band-aids)
    'j8_city_049',     # Concrete scene (landscaping worker)
    'j8_city_052',     # Concrete image (window/star)
    'j8_city_054',     # Dialogue ending (cat society)
    'j8_city_055',     # Dialogue ending
    'j8_city_056',     # Concrete scene (two knocks)
    'j8_identity_004', # Concrete memory
    'j8_identity_076', # The observation IS the passage's point
    'j8_identity_077', # Scientific fact being used
    'j8_identity_080', # Pithy observation IS the point
    'j8_identity_085', # The observation IS the point
    'j8_food_089',     # Food observation IS the point
    'j8_food_090',     # Dialogue ending (mother's words)
    'j8_food_094',     # Dialogue ending
    'j8_food_095',     # Dialogue ending
    'j8_food_096',     # Concrete scene
    'j8_food_099',     # Concrete observation
    'j8_system_057',   # Dialogue ending
    'j8_system_058',   # Dialogue ending
    'j8_system_059',   # Dialogue ending
    'j8_system_060',   # Dialogue ending
    'j8_system_062',   # Dialogue ending
    'j8_system_063',   # Dialogue ending
    'j8_system_064',   # Concrete observation
    'j8_system_065',   # Dialogue ending
    'j8_system_066',   # Dialogue ending
    'j8_system_067',   # Dialogue ending
    'j8_system_068',   # Dialogue ending
    'j8_system_069',   # Dialogue ending
    'j8_system_072',   # Concrete scene
    'j9_city_020',     # Concrete scene (last sound)
    'j9_city_022',     # Concrete image
    'j9_city_023',     # Concrete scene
    'j9_city_027',     # Dialogue ending
    'j9_city_030',     # "Orderly, yes. But the street had stopped talking." - perfect
    'j9_observe_011',  # Concrete scene (bench impressions)
    'j9_observe_014',  # Concrete image (vanity table)
    'j9_observe_015',  # Concrete scene (slip of paper)
    'j9_observe_016',  # Concrete scene (cucumbers and eggs)
    'j9_observe_017',  # Concrete image (reading glasses)
    'j9_observe_013',  # Concrete action (crack window open)
    'j9_identity_054', # Concrete scene (tracing stroke)
    'j9_identity_065', # Concrete scene (shopping lists)
    'j9_food_067',     # "The taste of no taste" - the point
    'j9_food_073',     # Concrete scene (old woman)
    'j9_quiet_099',    # Concrete scene (alarm)
    'j9_quiet_101',    # Concrete image (gold leaves)
    'j9_quiet_102',    # "No adjustment needed. Just be." - perfect
    'j9_quiet_103',    # Concrete image (warm stone)
    'j9_quiet_108',    # Dialogue ending
    'j9_quiet_115',    # Concrete scene (bookshelf)
    'j9_quiet_116',    # Dialogue ending
    'j9_quiet_120',    # Concrete scene (returning book)
    'j8_quiet_113',    # Concrete sensory detail
    'j8_quiet_114',    # Concrete scene
    'j8_quiet_115',    # Concrete sensory detail
    'j8_quiet_116',    # Concrete scene (new shoots)
    'j8_quiet_117',    # Concrete sensory detail
    'j8_quiet_119',    # Dialogue ending
    'j7_quiet_113',    # Concrete scene (nod)
    'j7_quiet_114',    # "I choose to believe it" - concrete
    'j7_quiet_116',    # Dialogue ending
    'j7_quiet_117',    # Dialogue ending
    'j7_quiet_120',    # Concrete observation
    'j9_food_081',     # The observation IS the comic point
    'j7_urban_002',    # "shelter of not being questioned" IS the passage's core insight
    'j7_observe_001',  # Dialogue ending needs to complete; cutting "I suddenly understood" removes too much
    'j7_observe_044',  # "Perhaps forgetting isn't a loss but a refinement" is fresh, not restating
    'j8_observe_021',  # "some things won't stop working" is the observation, not thesis
    'j8_observe_022',  # "most things we create are erasable" is a fresh observation
    'j9_identity_058', # "The true me perhaps exists at the confluence" is the core insight
    'j9_quiet_118',    # "A true apology is not a sentence" is the observation itself
    'j9_identity_059', # "The fog shifts again" is a concrete poetic image
    'j9_identity_001', # "regret a translator can never eliminate" IS the core observation
    'j7_observe_053',  # "judging by labels" - the preceding list needs this capper
    'j7_identity_002', # "if one day nobody calls that name" is the emotional core
    'j7_food_001',     # "Inheritance is sometimes that fragile" - pithy, not restating
    'j9_city_024',     # "tearing down this wall" is character's own words, not narrator thesis
    'j8_identity_087', # "coordinates for calibrating memory" is a fresh metaphor
    'j8_identity_083', # "Patience is not a virtue" - this IS the insight, not restating
}


def split_sentences(text):
    """Split text into sentences at boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'\(])', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def check_coda(sentence):
    """Check if sentence matches thesis-coda patterns. Returns (matched, desc)."""
    lower = sentence.lower()
    for pattern, desc in CODA_PATTERNS:
        if re.search(pattern, lower):
            return True, desc
    return False, None


def has_keep_signal(sentence):
    """Check if sentence has signals that it should be kept."""
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, sentence, re.IGNORECASE):
            return True
    return False


def word_count(text):
    return len(text.split())


def try_cut(passage_id, text_en):
    """Try to cut thesis coda. Returns (new_text, cut_text, pattern_desc) or (None, None, None)."""
    if passage_id in SKIP_IDS:
        return None, None, None

    sentences = split_sentences(text_en)
    if len(sentences) < 4:
        return None, None, None

    last = sentences[-1]
    second_last = sentences[-2] if len(sentences) >= 2 else ''

    last_is_coda, last_desc = check_coda(last)
    second_is_coda, second_desc = check_coda(second_last)

    # Try cutting last 2 sentences if both match
    if last_is_coda and second_is_coda and not has_keep_signal(last) and not has_keep_signal(second_last):
        new_text = ' '.join(sentences[:-2])
        if word_count(new_text) >= 100:
            cut = ' '.join(sentences[-2:])
            return new_text, cut, f"{second_desc}+{last_desc}"

    # Try cutting last 2 if second-to-last is coda and last is short abstract continuation
    if second_is_coda and not has_keep_signal(second_last):
        if not has_keep_signal(last) and (last_is_coda or word_count(last) < 20):
            new_text = ' '.join(sentences[:-2])
            if word_count(new_text) >= 100:
                cut = ' '.join(sentences[-2:])
                return new_text, cut, f"{second_desc}(+continuation)"

    # Try cutting just the last sentence
    if last_is_coda and not has_keep_signal(last):
        new_text = ' '.join(sentences[:-1])
        if word_count(new_text) >= 100:
            return new_text, last, last_desc

    return None, None, None


def process_file(filepath, originals_by_id):
    with open(filepath, 'r', encoding='utf-8') as f:
        passages = json.load(f)

    # Restore original text_en before processing
    for p in passages:
        if p['id'] in originals_by_id:
            p['text_en'] = originals_by_id[p['id']]

    cuts = []
    for p in passages:
        text_en = p.get('text_en', '')
        if not text_en:
            continue

        new_text, cut_text, desc = try_cut(p['id'], text_en)
        if new_text:
            new_ending = new_text[-100:]
            cuts.append({
                'id': p['id'],
                'title': p.get('title', ''),
                'cut': cut_text,
                'new_ending': '...' + new_ending,
                'pattern': desc,
            })
            p['text_en'] = new_text

    return passages, cuts


def main():
    # Load originals from reading_passages.json
    originals_path = str(Path(__file__).parent.parent / "data" / "reading_passages.json")
    with open(originals_path, 'r', encoding='utf-8') as f:
        all_passages = json.load(f)
    originals_by_id = {p['id']: p['text_en'] for p in all_passages if p.get('text_en')}
    print(f"Loaded {len(originals_by_id)} original passages from reading_passages.json")

    files = [
        'passages_hsk7.json',
        'passages_hsk8.json',
        'passages_hsk9.json',
    ]

    total_cuts = 0
    all_cuts = []

    for filepath in files:
        print(f"\n{'='*70}")
        print(f"Processing: {filepath}")
        print(f"{'='*70}")

        passages, cuts = process_file(filepath, originals_by_id)

        # Save the modified file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(passages, f, ensure_ascii=False, indent=2)

        for c in cuts:
            print(f"\n  [{c['pattern']}] {c['id']} — {c['title']}")
            cut_preview = c['cut'][:150]
            if len(c['cut']) > 150:
                cut_preview += '...'
            print(f"  CUT: {cut_preview}")
            print(f"  NEW ENDING: {c['new_ending']}")

        print(f"\n  Cuts in {filepath}: {len(cuts)}")
        total_cuts += len(cuts)
        all_cuts.extend(cuts)

    print(f"\n{'='*70}")
    print(f"TOTAL CUTS: {total_cuts}")
    print(f"{'='*70}")

    # Pattern distribution
    pattern_counts = {}
    for c in all_cuts:
        p = c['pattern']
        pattern_counts[p] = pattern_counts.get(p, 0) + 1
    print("\nPattern distribution:")
    for p, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {p}: {count}")

    if total_cuts < 30:
        print(f"\nWARNING: Only {total_cuts} cuts made, target was 30-50.")
    elif total_cuts > 50:
        print(f"\nWARNING: {total_cuts} cuts made, target was 30-50.")
    else:
        print(f"\nWithin target range (30-50).")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Trim overlong dialogue text_en in j*_dlg_*.json files.
- Player options > 40 words -> compress to <= 35 words
- NPC turns > 80 words -> compress to <= 70 words

Uses aggressive rule-based compression + sentence trimming.
"""

import json
import glob
import os
import re
import sys

DIALOGUE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_MAX = 35
NPC_MAX = 70


def wc(text):
    return len(text.split())


def split_sentences(text):
    """Split text into sentences, preserving delimiters."""
    # Split on sentence-ending punctuation followed by space or end
    parts = re.split(r'(?<=[.!?])\s+', text)
    # Also split on em-dash phrases if they're long
    result = []
    for p in parts:
        if ' — ' in p and len(p.split()) > 20:
            sub = p.split(' — ', 1)
            result.append(sub[0] + ' —')
            result.append(sub[1])
        else:
            result.append(p)
    return [s.strip() for s in result if s.strip()]


def compress_text(text, target, is_player=True):
    """Aggressively compress text to target word count."""
    if wc(text) <= target:
        return text

    original = text

    # Phase 1: Remove filler phrases
    removals = [
        # Essay openers
        (r"^I believe that\b,?\s*", ""),
        (r"^It seems to me that\b,?\s*", ""),
        (r"^I think perhaps\b,?\s*", ""),
        (r"^What I mean is\b,?\s*", ""),
        (r"^I think that\b,?\s*", ""),
        (r"^I feel like\b,?\s*", ""),
        (r"^In my opinion,?\s*", ""),
        (r"^To be honest,?\s*", ""),
        (r"^The truth is,?\s*", ""),
        (r"^The thing is,?\s*", ""),
        (r"^I would say that\b,?\s*", ""),
        (r"^What I'm trying to say is,?\s*", ""),
        # Filler words
        (r"\bactually,?\s*", ""),
        (r"\bbasically,?\s*", ""),
        (r"\b[Rr]eally\s+", ""),
        (r"\bjust\s+", ""),
        (r"\bcertainly\s+", ""),
        (r"\bdefinitely\s+", ""),
        (r"\bessentially,?\s*", ""),
        (r"\bof course,?\s*", ""),
        (r"\byou know,?\s*", ""),
        (r"\bI mean,?\s*", ""),
        (r"\bI guess\s+", ""),
        (r"\bkind of\s+", ""),
        (r"\bsort of\s+", ""),
        (r"\bin a way,?\s*", ""),
        (r"\bat the end of the day,?\s*", ""),
        (r"\b[Aa]t the same time,?\s*", ""),
        (r"\b[Ii]n other words,?\s*", ""),
        (r"\b[Aa]fter all,?\s*", ""),
        (r"\bperhaps\b", "maybe"),
        # Wordy phrases
        (r"\bit's precisely because\b", "because"),
        (r"\bthe most important thing is:?\s*", ""),
        (r"\bwhat's interesting is\b,?\s*", ""),
        (r"\bwhat fascinates me is\b,?\s*", ""),
        (r"\bthe greatest difference\b", "the main difference"),
        (r"\bcompletely different\b", "different"),
        (r"\bin the world\b", ""),
        (r"\bdo you know what\b", "you know what"),
        (r"\bI've never thought about it that way\b", "never thought of that"),
        (r"\bI completely agree\b", "Agreed"),
        (r"\bthat's a very\b", "that's a"),
        (r"\bthis is a very\b", "this is a"),
        (r"\bvery\s+", ""),
    ]

    for pat, repl in removals:
        text = re.sub(pat, repl, text)

    # Phase 2: Simplify common verbose patterns
    simplifications = [
        (r"\bnot because they're unwilling\b", "not unwillingness"),
        (r"\bbut the reality is,?\s*", "but "),
        (r"\bwhat you're describing is\b", "that's"),
        (r"\bthe most fascinating thing is\b", "fascinating:"),
        (r"\bthis is perhaps\b", "maybe this is"),
        (r"\bprecisely because of\b", "because of"),
        (r"\bit's not that .+? — it's that\b", ""),
        (r"\bthe reason is\b,?\s*", ""),
        (r"\bfor the simple reason that\b", "because"),
        (r"\bin this kind of\b", "in this"),
        (r"\bthe entirety of\b", "all"),
        (r"\bthroughout the entirety of\b", "throughout"),
    ]

    for pat, repl in simplifications:
        text = re.sub(pat, repl, text)

    # Clean up
    text = re.sub(r"  +", " ", text).strip()
    text = re.sub(r" ,", ",", text)
    text = re.sub(r"\. \.", ".", text)

    # Capitalize first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    if wc(text) <= target:
        return text

    # Phase 3: Drop sentences from the end until under target
    sentences = split_sentences(text)
    while len(sentences) > 1 and wc(' '.join(sentences)) > target:
        sentences.pop()

    text = ' '.join(sentences)

    if wc(text) <= target:
        return text

    # Phase 4: If still over, try dropping from the middle (keep first and last)
    sentences = split_sentences(text)
    if len(sentences) > 2:
        while len(sentences) > 2 and wc(' '.join(sentences)) > target:
            # Remove the second-to-last sentence
            sentences.pop(-2)
        text = ' '.join(sentences)

    if wc(text) <= target:
        return text

    # Phase 5: Truncate to target words (last resort)
    words = text.split()
    text = ' '.join(words[:target])
    # Try to end at a sentence boundary
    if not text.endswith(('.', '!', '?', '—')):
        # Find last sentence-ending punctuation
        for i in range(len(text) - 1, max(0, len(text) - 30), -1):
            if text[i] in '.!?':
                text = text[:i + 1]
                break
        else:
            text = text.rstrip(',;: ') + '.'

    return text


def process_files():
    files = sorted(glob.glob(os.path.join(DIALOGUE_DIR, "j*_dlg_*.json")))
    print(f"Found {len(files)} dialogue files")

    player_trimmed = 0
    npc_trimmed = 0
    player_total_over = 0
    npc_total_over = 0
    still_over_player = 0
    still_over_npc = 0

    for filepath in files:
        fname = os.path.basename(filepath)
        with open(filepath) as f:
            data = json.load(f)

        modified = False
        turns = data.get("tree", {}).get("turns", [])

        for ti, turn in enumerate(turns):
            if turn["speaker"] == "player":
                for oi, opt in enumerate(turn.get("options", [])):
                    orig_wc = wc(opt["text_en"])
                    if orig_wc > 40:
                        player_total_over += 1
                        new_text = compress_text(opt["text_en"], PLAYER_MAX, is_player=True)
                        new_wc = wc(new_text)
                        if new_text != opt["text_en"]:
                            opt["text_en"] = new_text
                            modified = True
                        if new_wc <= PLAYER_MAX:
                            player_trimmed += 1
                        else:
                            still_over_player += 1
                            print(f"  STILL OVER: P {fname}|{ti}|{oi} {orig_wc}->{new_wc}w: {new_text[:80]}...")

            elif turn["speaker"] == "npc":
                orig_wc = wc(turn["text_en"])
                if orig_wc > 80:
                    npc_total_over += 1
                    new_text = compress_text(turn["text_en"], NPC_MAX, is_player=False)
                    new_wc = wc(new_text)
                    if new_text != turn["text_en"]:
                        turn["text_en"] = new_text
                        modified = True
                    if new_wc <= NPC_MAX:
                        npc_trimmed += 1
                    else:
                        still_over_npc += 1
                        print(f"  STILL OVER: N {fname}|{ti}|npc {orig_wc}->{new_wc}w: {new_text[:80]}...")

        if modified:
            with open(filepath, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n=== RESULTS ===")
    print(f"Player options over 40 words: {player_total_over}")
    print(f"Player options successfully trimmed to <={PLAYER_MAX}: {player_trimmed}")
    print(f"Player options still over: {still_over_player}")
    print(f"NPC turns over 80 words: {npc_total_over}")
    print(f"NPC turns successfully trimmed to <={NPC_MAX}: {npc_trimmed}")
    print(f"NPC turns still over: {still_over_npc}")
    print(f"Total trimmed: {player_trimmed + npc_trimmed}")


def verify_files():
    """Verify all files are under limits and have clean endings."""
    files = sorted(glob.glob(os.path.join(DIALOGUE_DIR, "j*_dlg_*.json")))
    player_over = 0
    npc_over = 0
    bad_endings = 0
    json_errors = 0

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            with open(filepath) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            json_errors += 1
            print(f"  JSON ERROR: {fname}: {e}")
            continue

        turns = data.get("tree", {}).get("turns", [])
        for ti, turn in enumerate(turns):
            if turn["speaker"] == "player":
                for oi, opt in enumerate(turn.get("options", [])):
                    text = opt["text_en"].strip()
                    w = wc(text)
                    if w > 40:
                        player_over += 1
                        print(f"  OVER: P {fname}|{ti}|{oi} [{w}w]")
                    if text and text[-1] in "—,;:":
                        bad_endings += 1
                        print(f"  BAD END: P {fname}|{ti}|{oi}: ...{text[-40:]}")
            elif turn["speaker"] == "npc":
                text = turn["text_en"].strip()
                w = wc(text)
                if w > 80:
                    npc_over += 1
                    print(f"  OVER: N {fname}|{ti}|npc [{w}w]")
                if text and text[-1] in "—,;:":
                    bad_endings += 1
                    print(f"  BAD END: N {fname}|{ti}|npc: ...{text[-40:]}")

    print(f"\n=== VERIFICATION ===")
    print(f"Files checked: {len(files)}")
    print(f"JSON errors: {json_errors}")
    print(f"Player options over 40 words: {player_over}")
    print(f"NPC turns over 80 words: {npc_over}")
    print(f"Bad endings: {bad_endings}")
    ok = player_over == 0 and npc_over == 0 and bad_endings == 0 and json_errors == 0
    print("STATUS: ALL CLEAN" if ok else "STATUS: ISSUES FOUND")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_files()
    else:
        process_files()

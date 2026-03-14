# -*- coding: utf-8 -*-
"""
Build HSK 8/9 passage batch files.
Usage: python3 build_batch.py
"""
import json
import os

BASE = "/Users/jasongerson/mandarin/content_gen"

def save(filename, passages):
    path = os.path.join(BASE, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(passages, f, ensure_ascii=False, indent=2)
    # Verify
    with open(path, 'r', encoding='utf-8') as f:
        v = json.load(f)
    assert len(v) == len(passages), f"Mismatch: wrote {len(passages)}, read {len(v)}"
    for p in v:
        assert len(p['questions']) == 3, f"{p['id']} has {len(p['questions'])} questions, expected 3"
    print(f"  {filename}: {len(v)} passages OK")
    return v

def p(id, title, title_zh, level, text_zh, text_pinyin, text_en, questions):
    """Helper to create a passage dict."""
    return {
        "id": id,
        "title": title,
        "title_zh": title_zh,
        "hsk_level": level,
        "text_zh": text_zh,
        "text_pinyin": text_pinyin,
        "text_en": text_en,
        "questions": questions
    }

def q(q_zh, q_en, options, difficulty):
    """Helper to create a question dict."""
    return {
        "type": "mc",
        "q_zh": q_zh,
        "q_en": q_en,
        "options": options,
        "difficulty": difficulty
    }

def o(text, pinyin, text_en, correct=False):
    """Helper to create an option dict."""
    return {
        "text": text,
        "pinyin": pinyin,
        "text_en": text_en,
        "correct": correct
    }

if __name__ == '__main__':
    print("Build script ready. Import and call save() with passages.")

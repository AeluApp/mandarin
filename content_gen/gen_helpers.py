# -*- coding: utf-8 -*-
import json
import os

BASE = "/Users/jasongerson/mandarin/content_gen"

def mc(q_zh, q_en, opts, diff):
    return {"type": "mc", "q_zh": q_zh, "q_en": q_en, "options": opts, "difficulty": diff}

def o(text, pinyin, text_en, correct=False):
    return {"text": text, "pinyin": pinyin, "text_en": text_en, "correct": correct}

def passage(pid, title, title_zh, level, text_zh, text_pinyin, text_en, q1, q2, q3):
    return {
        "id": pid, "title": title, "title_zh": title_zh, "hsk_level": level,
        "text_zh": text_zh, "text_pinyin": text_pinyin, "text_en": text_en,
        "questions": [q1, q2, q3]
    }

def save(filename, passages):
    path = os.path.join(BASE, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(passages, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        v = json.load(f)
    assert len(v) == len(passages)
    for p in v:
        assert len(p["questions"]) == 3, f"{p['id']} has {len(p['questions'])} questions"
    print(f"{filename}: {len(v)} passages OK")

def append_save(filename, new_passages):
    """Load existing file, append new passages, save."""
    path = os.path.join(BASE, filename)
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing.extend(new_passages)
    save(filename, existing)
    return len(existing)

"""Shared content validation for AI-generated items."""

from __future__ import annotations

import re
from typing import Optional


def validate_generated_content(item_type: str, content: dict) -> dict:
    """Validate AI-generated content. Returns content dict with validation_status + validation_issues."""
    issues = []

    if item_type == "drill":
        issues.extend(_validate_drill_content(content))
    elif item_type == "reading":
        issues.extend(_validate_reading_content(content))

    content["validation_status"] = "failed" if issues else "passed"
    content["validation_issues"] = issues
    return content


def _validate_drill_content(content: dict) -> list[str]:
    """Validate a generated drill item."""
    issues = []

    # Required fields
    for field in ("hanzi", "pinyin", "english", "drill_type"):
        if not content.get(field):
            issues.append(f"missing required field: {field}")

    # Pinyin must have tone marks or numbers
    pinyin = content.get("pinyin", "")
    if pinyin and not _has_tone_marks(pinyin):
        issues.append("pinyin missing tone marks")

    # Check for traditional-only characters
    hanzi = content.get("hanzi", "")
    if hanzi and _contains_traditional_only_chars(hanzi):
        issues.append("contains traditional-only characters")

    # Distractors: check for duplicates and primary meaning collision
    distractors = content.get("distractors", [])
    if distractors:
        lower_d = [d.lower().strip() for d in distractors]
        if len(set(lower_d)) < len(lower_d):
            issues.append("duplicate distractors")
        english = (content.get("english") or "").lower().strip()
        if english and english in lower_d:
            issues.append("primary meaning appears as distractor")

    return issues


def _validate_reading_content(content: dict) -> list[str]:
    """Validate a generated reading passage."""
    issues = []

    for field in ("title", "body", "pinyin_body"):
        if not content.get(field):
            issues.append(f"missing required field: {field}")

    body = content.get("body", "")
    if body and _contains_traditional_only_chars(body):
        issues.append("contains traditional-only characters")

    return issues


def _has_tone_marks(pinyin: str) -> bool:
    """Check if pinyin contains tone marks (diacritics) or tone numbers."""
    # Tone diacritics
    if re.search(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', pinyin):
        return True
    # Tone numbers (e.g. ma1, ni3)
    if re.search(r'[a-z][1-4]', pinyin, re.IGNORECASE):
        return True
    return False


def _contains_traditional_only_chars(text: str) -> bool:
    """Check for characters that are traditional-only (not used in simplified).

    This is a conservative check — flags common traditional variants
    that should not appear in simplified Chinese content.
    """
    # Common traditional-only characters (simplified equivalents exist)
    traditional_only = set("國學會說認識書電話車開門問題時間點從經過還這後種東對機長關號線錢頭進員發現處實節觀決讓選訓練試驗離聯類準備幫總續隊護環網營際響證議鐵導際議響營網環護隊續總幫備準類聯離驗試練訓選讓決觀節實處現發員進頭錢線號關長機對東種後這還過經從點間時題問門開車話電書識認說會學國")
    return bool(set(text) & traditional_only)

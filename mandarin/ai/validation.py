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


def screen_for_inappropriate_content(text: str, context: str = "reading") -> dict:
    """Screen AI-generated content for inappropriate material.

    Checks for offensive patterns, stereotypes, and factual red flags.
    Uses Qwen LLM if available, else keyword heuristic.

    Returns: {"safe": bool, "issues": list[str], "method": "llm"|"heuristic"}
    """
    issues = []

    # Heuristic check: keywords/patterns that should never appear in educational content
    lower = text.lower()

    # Offensive/inappropriate content patterns
    _OFFENSIVE_PATTERNS = [
        r"\b(?:damn|hell|shit|fuck|bitch|ass(?:hole)?|crap)\b",
        r"\b(?:stupid|idiot|dumb|loser|ugly|fat|retard)\b",
        r"\b(?:kill|murder|suicide|die|death|blood|weapon|gun|knife)\b",
        r"\b(?:sex(?:ual)?|porn|naked|nude|breast|genital)\b",
        r"\b(?:drug|cocaine|heroin|marijuana|meth)\b",
    ]

    for pattern in _OFFENSIVE_PATTERNS:
        matches = re.findall(pattern, lower)
        if matches:
            issues.append(f"inappropriate content detected: {matches[:2]}")

    # Stereotyping patterns (cultural sensitivity for Chinese content)
    _STEREOTYPE_PATTERNS = [
        r"\b(?:all\s+chinese\s+people|chinese\s+always|typical\s+chinese)\b",
        r"\b(?:oriental|chinaman|ching\s+chong)\b",
    ]

    for pattern in _STEREOTYPE_PATTERNS:
        if re.search(pattern, lower):
            issues.append("potential cultural stereotype detected")

    # Try LLM screening if available and text is substantial
    if not issues and len(text) > 100:
        try:
            from .ollama_client import generate, is_ollama_available
            if is_ollama_available():
                resp = generate(
                    prompt=(
                        f"Is this {context} content appropriate for a language learning app "
                        f"used by adults and students? Check for: offensive language, "
                        f"stereotypes, factual errors, bias. Reply ONLY 'safe' or "
                        f"'unsafe: [reason]'.\n\nContent: {text[:500]}"
                    ),
                    system="You are a content safety reviewer. Be brief.",
                    temperature=0.1,
                    max_tokens=50,
                    task_type="content_moderation",
                )
                if resp.success and "unsafe" in resp.text.lower():
                    issues.append(f"LLM flagged: {resp.text.strip()}")
                    return {"safe": False, "issues": issues, "method": "llm"}
                return {"safe": True, "issues": [], "method": "llm"}
        except Exception:
            pass

    return {
        "safe": len(issues) == 0,
        "issues": issues,
        "method": "heuristic",
    }


def _contains_traditional_only_chars(text: str) -> bool:
    """Check for characters that are traditional-only (not used in simplified).

    This is a conservative check — flags common traditional variants
    that should not appear in simplified Chinese content.
    """
    # Common traditional-only characters (simplified equivalents exist)
    traditional_only = set("國學會說認識書電話車開門問題時間點從經過還這後種東對機長關號線錢頭進員發現處實節觀決讓選訓練試驗離聯類準備幫總續隊護環網營際響證議鐵導際議響營網環護隊續總幫備準類聯離驗試練訓選讓決觀節實處現發員進頭錢線號關長機對東種後這還過經從點間時題問門開車話電書識認說會學國")
    return bool(set(text) & traditional_only)

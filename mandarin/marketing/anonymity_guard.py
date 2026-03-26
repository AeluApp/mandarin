"""Identity guard — ensures marketing content never reveals the founder's identity.

First-person voice ("I built this", "my app") is allowed and encouraged.
What is forbidden: founder's real name, last name, photo, employer, personal
bio details, or anything that identifies *who* the "I" is.

Two layers:
1. Regex pattern filter (always runs, deterministic, fast)
2. LLM validation via generate_structured() (runs when cloud LLM available)

Exports:
    check_identity(text: str, conn=None) -> IdentityCheckResult
    FORBIDDEN_PATTERNS: list of compiled patterns
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IdentityViolation:
    pattern_name: str
    matched_text: str
    start: int
    end: int


@dataclass
class IdentityCheckResult:
    passed: bool
    violations: list[IdentityViolation] = field(default_factory=list)
    llm_checked: bool = False
    llm_anonymous: bool = True


# ── Forbidden patterns ───────────────────────────────────────────────
# Each tuple: (compiled regex, category name)
# These catch the founder's real identity. First-person voice is NOT blocked.

_RAW_PATTERNS = [
    # Founder name (case-insensitive)
    (r"\bJason\b", "founder_first_name"),
    (r"\bGerson\b", "founder_last_name"),

    # Identifying biographical details
    (r"\bLinkedIn\.com/in/\S+", "linkedin_profile"),
    (r"\b@\w+\b.*(?:personal|founder|creator)", "personal_handle"),
    (r"\bmy (?:LinkedIn|GitHub|Twitter|X) (?:profile|handle|account)\b", "personal_social_ref"),

    # Photo/headshot references
    (r"\bmy (?:photo|headshot|picture|face)\b", "photo_reference"),
    (r"\bpicture of (?:me|the founder|the creator)\b", "photo_reference"),
    (r"\bfounder(?:'s)? photo\b", "photo_reference"),

    # Personal bio details that could identify
    (r"\bI (?:live|grew up|was born) in [A-Z][a-z]+", "location_reveal"),
    (r"\bI (?:work|worked) at [A-Z][a-z]+", "employer_reveal"),
    (r"\bI (?:studied|graduated) (?:at|from) [A-Z][a-z]+", "education_reveal"),
]

FORBIDDEN_PATTERNS = [(re.compile(p, re.IGNORECASE), name) for p, name in _RAW_PATTERNS]


def _check_patterns(text: str) -> list[IdentityViolation]:
    """Run regex pattern filter. Returns list of violations (empty = pass)."""
    violations = []
    for pattern, name in FORBIDDEN_PATTERNS:
        for match in pattern.finditer(text):
            violations.append(IdentityViolation(
                pattern_name=name,
                matched_text=match.group(),
                start=match.start(),
                end=match.end(),
            ))
    return violations


def _check_llm(text: str, conn=None) -> tuple[bool, bool]:
    """LLM-based identity check. Returns (was_checked, is_anonymous)."""
    try:
        from ..ai.ollama_client import is_llm_available, generate

        if not is_llm_available():
            return False, True  # LLM unavailable, skip

        system = (
            "You are a content reviewer. Your job is to check if marketing text "
            "reveals the real identity of the author — their name, photo, employer, "
            "university, city, or personal social media handles. "
            "First-person voice ('I built this', 'my app') is FINE and should NOT be flagged. "
            "Only flag content that reveals WHO the person is."
        )
        prompt = (
            f"Does this text reveal the real name, photo, employer, or personal identity "
            f"of the author? Respond with JSON: {{\"anonymous\": true/false, \"violations\": [\"...\"] }}\n\n"
            f"Text:\n{text[:2000]}"
        )
        resp = generate(
            prompt=prompt, system=system, temperature=0.1, max_tokens=200,
            use_cache=False, conn=conn, task_type="voice_audit",
        )
        if not resp.success:
            return False, True

        # Parse JSON response
        import json
        try:
            # Try to extract JSON from the response
            json_text = resp.text.strip()
            if "```" in json_text:
                json_text = json_text.split("```")[1].strip()
                if json_text.startswith("json"):
                    json_text = json_text[4:].strip()
            data = json.loads(json_text)
            is_anonymous = data.get("anonymous", True)
            return True, is_anonymous
        except (json.JSONDecodeError, KeyError, IndexError):
            return True, True  # Parse failed, assume OK (pattern layer is primary)

    except ImportError:
        return False, True


def check_identity(text: str, conn=None) -> IdentityCheckResult:
    """Check if marketing text reveals founder identity.

    Returns IdentityCheckResult with passed=True if content is safe to post.
    Pattern violations are a hard fail regardless of LLM result.
    """
    # Layer 1: Regex patterns (always runs)
    violations = _check_patterns(text)

    if violations:
        return IdentityCheckResult(
            passed=False,
            violations=violations,
            llm_checked=False,
            llm_anonymous=True,
        )

    # Layer 2: LLM validation (when available)
    llm_checked, llm_anonymous = _check_llm(text, conn=conn)

    return IdentityCheckResult(
        passed=llm_anonymous,
        violations=[],
        llm_checked=llm_checked,
        llm_anonymous=llm_anonymous,
    )

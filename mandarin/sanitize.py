"""Input sanitization — HTML stripping, XSS prevention, filename safety.

Uses only Python stdlib (html module + re). No external dependencies.
Applied at input boundaries before storage, complementing Jinja2's
auto-escaping at output.
"""

import html
import os
import re

# HTML tag stripping regex
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)


def sanitize_html(text: str) -> str:
    """Strip all HTML tags and script content from text.

    Removes <script>, <style> blocks first, then strips remaining tags.
    Does NOT escape — use sanitize_for_display() for HTML-safe output.
    """
    if not text:
        return ""
    # Remove script and style blocks first
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    # Remove event handlers (onclick=, onload=, etc.)
    text = _EVENT_HANDLER_RE.sub("", text)
    # Strip remaining tags
    text = _HTML_TAG_RE.sub("", text)
    # Decode HTML entities
    text = html.unescape(text)
    return text.strip()


def sanitize_for_display(text: str) -> str:
    """Escape text for safe HTML rendering.

    Escapes <, >, &, ", ' to prevent XSS when inserted into HTML context.
    """
    if not text:
        return ""
    return html.escape(text, quote=True)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename to prevent path traversal and injection.

    Removes path separators, null bytes, and non-alphanumeric characters
    except dash, underscore, and dot.
    """
    if not name:
        return "unnamed"
    # Remove path components
    name = os.path.basename(name)
    # Remove null bytes
    name = name.replace("\x00", "")
    # Whitelist: alphanumeric, dash, underscore, dot
    name = re.sub(r"[^\w\-.]", "_", name)
    # Prevent hidden files
    name = name.lstrip(".")
    # Prevent empty
    return name or "unnamed"


def sanitize_user_text(text: str, max_length: int = 10000) -> str:
    """Sanitize user-provided text for storage.

    Strips HTML, truncates to max_length, normalizes whitespace.
    """
    if not text:
        return ""
    text = sanitize_html(text)
    text = text[:max_length]
    # Normalize whitespace (but preserve newlines)
    lines = text.split("\n")
    lines = [" ".join(line.split()) for line in lines]
    return "\n".join(lines).strip()

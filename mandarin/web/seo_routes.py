"""SEO programmatic pages — tone pair drills and HSK level reviews.

Auto-generated from content DB. No login required. Cached responses.
"""

import logging
import sqlite3
from functools import lru_cache

from flask import Blueprint, render_template_string, abort, jsonify

from .. import db
from ..settings import CANONICAL_URL
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)

seo_bp = Blueprint("seo", __name__)

# All 20 tone pair combinations (Mandarin has 4 tones + neutral)
TONE_PAIRS = []
for a in range(1, 5):
    for b in range(1, 5):
        TONE_PAIRS.append((a, b))
# Add neutral tone pairs (tone 5 = neutral)
for a in range(1, 5):
    TONE_PAIRS.append((a, 5))

TONE_NAMES = {1: "first (flat)", 2: "second (rising)", 3: "third (dip)", 4: "fourth (falling)", 5: "neutral"}


def _get_tone_pair_words(tone_a, tone_b, limit=20):
    """Fetch words matching a tone pair pattern from content DB."""
    try:
        with db.connection() as conn:
            # Match pinyin tone numbers at end of syllables
            rows = conn.execute(
                """SELECT hanzi, pinyin, english, hsk_level
                   FROM content_item
                   WHERE pinyin IS NOT NULL AND pinyin != ''
                   ORDER BY hsk_level ASC, id ASC
                   LIMIT 500""",
            ).fetchall()

            results = []
            for r in rows:
                pinyin = r["pinyin"] or ""
                # Simple tone extraction: split pinyin, check tone numbers
                syllables = pinyin.replace(",", " ").split()
                tones = []
                for s in syllables:
                    s = s.strip()
                    if s and s[-1].isdigit():
                        tones.append(int(s[-1]))
                    elif s:
                        # Try to detect tone from diacritics or default
                        tones.append(5)

                if len(tones) >= 2 and tones[0] == tone_a and tones[1] == tone_b:
                    results.append(dict(r))
                    if len(results) >= limit:
                        break

            return results
    except (sqlite3.Error, OSError) as e:
        logger.error("tone pair query error: %s", e)
        return []


def _get_hsk_words(level, limit=200):
    """Fetch words for an HSK level from content DB."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT hanzi, pinyin, english, hsk_level
                   FROM content_item
                   WHERE hsk_level = ?
                   ORDER BY id ASC
                   LIMIT ?""",
                (level, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except (sqlite3.Error, OSError) as e:
        logger.error("HSK words query error: %s", e)
        return []


def _get_hsk_count(level):
    """Count total words for an HSK level."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM content_item WHERE hsk_level = ?",
                (level,),
            ).fetchone()
            return row["cnt"] if row else 0
    except (sqlite3.Error, OSError):
        return 0


# ── Page templates (inline to avoid template file dependencies) ──

_BASE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }} — Aelu</title>
  <meta name="description" content="{{ description }}">
  <link rel="canonical" href="{{ base_url }}{{ canonical }}">
  <link rel="icon" type="image/x-icon" href="/static/favicon.ico?v=2">
  <meta property="og:title" content="{{ title }} — Aelu">
  <meta property="og:description" content="{{ description }}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{{ base_url }}{{ canonical }}">
  <meta property="og:image" content="{{ base_url }}/og-image.jpg">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{{ title }} — Aelu">
  <meta name="twitter:description" content="{{ description }}">
  <script type="application/ld+json">{{ schema|safe }}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Source+Serif+4:wght@400;600&display=swap">
  <link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700&display=swap" onload="this.onload=null;this.rel='stylesheet'">
  <style>
    :root{--color-base:#F2EBE0;--color-surface:#F7F1E8;--color-text:#2A3650;--color-text-faint:#8B8680;--color-accent:#946070;--color-secondary:#6A7A5A;--color-border:#D8D0C4;--font-heading:'Cormorant Garamond',Georgia,serif;--font-body:'Source Serif 4',Georgia,serif;--font-hanzi:'Noto Serif SC','Songti SC',serif;--radius:0;--space-1:.25rem;--space-2:.5rem;--space-3:1rem;--space-4:1.5rem;--space-5:2rem;--space-6:3rem;--space-8:5rem}
    @media(prefers-color-scheme:dark){:root{--color-base:#1C2028;--color-surface:#242830;--color-text:#E4DDD0;--color-text-faint:#8B8680;--color-border:#3A3530}}
    *{margin:0;padding:0;box-sizing:border-box}body{font-family:var(--font-body);color:var(--color-text);background:var(--color-base);line-height:1.7;-webkit-font-smoothing:antialiased}
    .container{max-width:720px;margin:0 auto;padding:0 var(--space-4)}
    nav{padding:var(--space-3) 0;border-bottom:1px solid var(--color-border)}nav .container{display:flex;justify-content:space-between;align-items:center}
    .nav-brand{font-family:var(--font-heading);font-size:1.3rem;font-weight:600;color:var(--color-text);text-decoration:none;display:flex;align-items:center;gap:8px}
    .nav-brand-icon{width:32px;height:32px;border-radius:7px}
    .nav-links{display:flex;gap:var(--space-4);list-style:none}.nav-links a{font-size:.9rem;color:var(--color-text-faint);text-decoration:none}.nav-links a:hover{color:var(--color-text)}
    .nav-cta{color:var(--color-base)!important;background:var(--color-accent);padding:.35rem 1rem;font-weight:600}
    h1{font-family:var(--font-heading);font-size:2.2rem;font-weight:600;margin-bottom:var(--space-3)}
    h2{font-family:var(--font-heading);font-size:1.6rem;font-weight:600;margin:var(--space-5) 0 var(--space-3)}
    .hero{text-align:center;padding:var(--space-8) 0 var(--space-5)}
    .hero-sub{font-size:1.1rem;color:var(--color-text-faint);max-width:520px;margin:0 auto}
    section{padding:var(--space-5) 0}
    table{width:100%;border-collapse:collapse;margin:var(--space-3) 0}
    th{font-family:var(--font-heading);font-weight:600;text-align:left;padding:var(--space-2);border-bottom:2px solid var(--color-border)}
    td{padding:var(--space-2);border-bottom:1px solid var(--color-border);font-size:.95rem}
    .hanzi-cell{font-family:var(--font-hanzi);font-size:1.3rem;color:var(--color-accent)}
    .cta-box{text-align:center;padding:var(--space-6) 0;background:var(--color-surface);border-top:1px solid var(--color-border);margin-top:var(--space-5)}
    .btn-primary{display:inline-block;padding:var(--space-2) var(--space-4);background:var(--color-accent);color:var(--color-base);border:none;font-family:var(--font-body);font-size:1rem;font-weight:600;cursor:pointer;text-decoration:none;transition:opacity .15s}.btn-primary:hover{opacity:.85}
    .tone-pair-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:var(--space-3);margin:var(--space-4) 0}
    .tone-pair-card{background:var(--color-surface);border:1px solid var(--color-border);padding:var(--space-3);text-align:center;text-decoration:none;color:var(--color-text);transition:border-color .15s}
    .tone-pair-card:hover{border-color:var(--color-accent)}
    .tone-pair-card .tones{font-family:var(--font-heading);font-size:1.5rem;font-weight:600;color:var(--color-accent)}
    .tone-pair-card .label{font-size:.85rem;color:var(--color-text-faint);margin-top:var(--space-1)}
    footer{padding:var(--space-5) 0;text-align:center;font-size:.85rem;color:var(--color-text-faint)}footer a{color:var(--color-text-faint);text-decoration:underline}
    .breadcrumb{font-size:.85rem;color:var(--color-text-faint);margin-bottom:var(--space-3)}.breadcrumb a{color:var(--color-accent);text-decoration:none}
    @media(max-width:600px){h1{font-size:1.6rem}.tone-pair-grid{grid-template-columns:repeat(auto-fill,minmax(110px,1fr))}}
  </style>
</head>"""

_NAV = """
<body>
<nav><div class="container">
  <a href="/" class="nav-brand"><img src="/static/icon-app.png" alt="" class="nav-brand-icon">Aelu</a>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/pricing">Pricing</a></li>
    <li><a href="/auth/register" class="nav-cta">Sign up</a></li>
  </ul>
</div></nav>"""

_FOOTER = """
<footer><div class="container">
  <p><a href="/">Home</a> &middot; <a href="/blog">Blog</a> &middot; <a href="/pricing">Pricing</a> &middot; <a href="/learn/tone-pairs/">Tone Pairs</a></p>
  <p style="margin-top:.5rem"><a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a></p>
</div></footer>
</body></html>"""

_TONE_PAIRS_INDEX = _BASE_HEAD + _NAV + """
<section class="hero"><div class="container">
  <h1>Mandarin Tone Pair Drills</h1>
  <p class="hero-sub">Master every tone combination in Mandarin Chinese. Click a pair to practice with real vocabulary.</p>
</div></section>
<section><div class="container">
  <div class="tone-pair-grid">
  {% for a, b in pairs %}
    <a href="/learn/tone-pairs/{{ a }}-{{ b }}/" class="tone-pair-card">
      <div class="tones">T{{ a }} + T{{ b }}</div>
      <div class="label">{{ counts.get((a,b), 0) }} words</div>
    </a>
  {% endfor %}
  </div>
</div></section>
<div class="cta-box"><div class="container">
  <h2>Practice tone pairs with adaptive drills</h2>
  <p style="color:var(--color-text-faint);margin-bottom:var(--space-4)">Sign up free and start drilling the tone pairs you struggle with most.</p>
  <a href="/auth/register" class="btn-primary">Sign up free</a>
</div></div>
""" + _FOOTER

_TONE_PAIR_DETAIL = _BASE_HEAD + _NAV + """
<section><div class="container">
  <div class="breadcrumb"><a href="/learn/tone-pairs/">Tone Pairs</a> &rsaquo; Tone {{ tone_a }} + Tone {{ tone_b }}</div>
  <h1>Tone {{ tone_a }} + Tone {{ tone_b }} Drill</h1>
  <p class="hero-sub" style="text-align:left;max-width:none">Practice {{ tone_a_name }} tone followed by {{ tone_b_name }} tone. {{ words|length }} example words from HSK vocabulary.</p>

  {% if words %}
  <table>
    <thead><tr><th>Hanzi</th><th>Pinyin</th><th>English</th><th>HSK</th></tr></thead>
    <tbody>
    {% for w in words %}
      <tr><td class="hanzi-cell">{{ w.hanzi }}</td><td>{{ w.pinyin }}</td><td>{{ w.english }}</td><td>{{ w.hsk_level }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color:var(--color-text-faint);margin:var(--space-4) 0">No examples found for this tone pair yet.</p>
  {% endif %}
</div></section>
<div class="cta-box"><div class="container">
  <h2>Practice more tone pairs</h2>
  <p style="color:var(--color-text-faint);margin-bottom:var(--space-4)">Adaptive drills that focus on your weak spots. Sign up free.</p>
  <a href="/auth/register" class="btn-primary">Sign up free</a>
</div></div>
""" + _FOOTER

_HSK_REVIEW = _BASE_HEAD + _NAV + """
<section><div class="container">
  <div class="breadcrumb"><a href="/learn/tone-pairs/">Learn</a> &rsaquo; HSK {{ level }}</div>
  <h1>HSK {{ level }} Vocabulary Review</h1>
  <p class="hero-sub" style="text-align:left;max-width:none">{{ total_count }} words in the HSK {{ level }} vocabulary list. Review the core words below.</p>

  {% if words %}
  <table>
    <thead><tr><th>Hanzi</th><th>Pinyin</th><th>English</th></tr></thead>
    <tbody>
    {% for w in words[:50] %}
      <tr><td class="hanzi-cell">{{ w.hanzi }}</td><td>{{ w.pinyin }}</td><td>{{ w.english }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% if words|length > 50 %}
  <p style="margin:var(--space-4) 0;text-align:center;color:var(--color-text-faint)">Showing 50 of {{ total_count }} words. <a href="/auth/register" style="color:var(--color-accent)">Sign up to see all &rarr;</a></p>
  {% endif %}
  {% endif %}
</div></section>
<div class="cta-box"><div class="container">
  <h2>Start learning HSK {{ level }}</h2>
  <p style="color:var(--color-text-faint);margin-bottom:var(--space-4)">Adaptive drills, graded reading, and listening practice. Sign up free.</p>
  <a href="/auth/register" class="btn-primary">Sign up free</a>
</div></div>
""" + _FOOTER


# ── Routes ──

@seo_bp.route("/learn/tone-pairs/")
def tone_pairs_index():
    """Index of all tone pair combinations."""
    import json
    counts = {}
    for a, b in TONE_PAIRS:
        words = _get_tone_pair_words(a, b, limit=1)
        counts[(a, b)] = len(_get_tone_pair_words(a, b, limit=50)) if words else 0

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Mandarin Tone Pair Drills",
        "description": "Practice all 20 Mandarin tone pair combinations with real HSK vocabulary.",
        "url": f"{CANONICAL_URL}/learn/tone-pairs/",
    })

    return render_template_string(
        _TONE_PAIRS_INDEX,
        title="Mandarin Tone Pair Drills",
        description="Practice all 20 Mandarin tone pair combinations with real HSK vocabulary. Interactive drills with audio.",
        canonical="/learn/tone-pairs/",
        base_url=CANONICAL_URL,
        schema=schema,
        pairs=TONE_PAIRS,
        counts=counts,
    )


@seo_bp.route("/learn/tone-pairs/<int:tone_a>-<int:tone_b>/")
def tone_pair_detail(tone_a, tone_b):
    """Specific tone pair drill page."""
    if tone_a < 1 or tone_a > 5 or tone_b < 1 or tone_b > 5:
        abort(404)

    import json
    words = _get_tone_pair_words(tone_a, tone_b, limit=20)

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Quiz",
        "name": f"Mandarin Tone Pair Drill: Tone {tone_a} + Tone {tone_b}",
        "description": f"Practice {TONE_NAMES.get(tone_a, '')} tone + {TONE_NAMES.get(tone_b, '')} tone combinations.",
        "educationalLevel": "Beginner",
        "about": {"@type": "Thing", "name": "Mandarin Chinese Tones"},
    })

    return render_template_string(
        _TONE_PAIR_DETAIL,
        title=f"Tone {tone_a} + Tone {tone_b} Drill",
        description=f"Practice Mandarin tone pair {tone_a}-{tone_b} with {len(words)} real HSK vocabulary words.",
        canonical=f"/learn/tone-pairs/{tone_a}-{tone_b}/",
        base_url=CANONICAL_URL,
        schema=schema,
        tone_a=tone_a,
        tone_b=tone_b,
        tone_a_name=TONE_NAMES.get(tone_a, ""),
        tone_b_name=TONE_NAMES.get(tone_b, ""),
        words=words,
    )


@seo_bp.route("/learn/hsk-<int:level>/")
def hsk_review(level):
    """HSK level vocabulary review page."""
    if level < 1 or level > 9:
        abort(404)

    import json
    words = _get_hsk_words(level, limit=200)
    total_count = _get_hsk_count(level)

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Course",
        "name": f"HSK {level} Vocabulary Review",
        "description": f"Review all {total_count} words in the HSK {level} vocabulary list.",
        "provider": {"@type": "Organization", "name": "Aelu"},
        "educationalLevel": f"HSK {level}",
    })

    return render_template_string(
        _HSK_REVIEW,
        title=f"HSK {level} Vocabulary Review — {total_count} Words",
        description=f"Review all {total_count} words in the HSK {level} vocabulary list. Hanzi, pinyin, and English translations.",
        canonical=f"/learn/hsk-{level}/",
        base_url=CANONICAL_URL,
        schema=schema,
        level=level,
        words=words,
        total_count=total_count,
    )

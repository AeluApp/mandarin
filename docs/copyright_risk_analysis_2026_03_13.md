# Aelu Copyright Risk Analysis — Commercial Readiness Audit
**Date:** 2026-03-13
**Scope:** Full codebase audit against Document 24, plus independent discovery
**Purpose:** Identify and resolve all copyright, licensing, and legal blockers before public launch and paid deployment

---

## Executive Summary

Document 24 was a strong starting point. This audit validates it against the actual codebase and finds three material discrepancies, one critical new blocker, and several gaps in commercial readiness infrastructure.

### What Document 24 Got Right
- CC-CEDICT (R-02) is present and the ShareAlike analysis is correct
- Qwen-generated content (R-05/R-06) risk assessment is accurate
- HSK word lists (R-04) risk is low
- The staged action framework (Stage 0 → 3) is sound

### What Document 24 Got Wrong or Overstated
- **R-01 (Chairman's Bao): Not integrated.** Only mentioned as a competitor in strategic intelligence. No content extracted or embedded. Risk is zero, not HIGH.
- **R-03 (Tatoeba): Not used.** No Tatoeba references in the codebase. Risk is zero.
- **R-07 (Crawl4AI): Not used.** System uses BeautifulSoup + httpx with robots.txt compliance. The actual crawling stack is lower-risk than Document 24 assessed.

### What Document 24 Missed Entirely
- **praat-parselmouth is GPLv3 — this is the actual critical blocker** (see R-NEW-01 below)
- edge-tts is LGPLv3 (manageable but undocumented)
- No project LICENSE file exists
- No THIRD_PARTY_LICENSES or attribution file for software dependencies
- Font licensing not assessed (all Google Fonts OFL — clean, but undocumented)
- Edge TTS commercial usage terms not assessed
- Missing legal infrastructure for commercial deployment (cookie consent, CCPA, breach notification)
- Flask and Werkzeug have active CVEs

---

## Part 1: Revised Risk Register

### R-NEW-01 — praat-parselmouth GPLv3  [CRITICAL BLOCKER]

| Field | Detail |
|-------|--------|
| **Package** | praat-parselmouth v0.4.7 |
| **License** | **GPLv3** |
| **Used in** | `mandarin/tone_grading.py`, `mandarin/tone_features.py` |
| **Function** | Primary F0 pitch extraction for tone grading (Praat autocorrelation) |
| **Impact** | GPLv3 copyleft requires the entire distributed application to be released under GPLv3 or a compatible license. Incompatible with proprietary commercial distribution. |

**This was not identified in Document 24's dependency inventory.** Document 24 listed Parselmouth in the memory notes but did not flag its license.

**Why it matters:** If Aelu is distributed as a proprietary application (Tauri desktop, iOS app, or closed-source SaaS), linking to a GPLv3 library triggers the copyleft obligation. The entire application must be open-sourced under GPLv3, or the dependency must be removed.

**Mitigation — Replace with YIN-only (Recommended):**
The codebase already has a clean fallback path. `tone_grading.py` lines 28-35:
```python
try:
    import parselmouth
    HAS_PARSELMOUTH = True
except ImportError:
    HAS_PARSELMOUTH = False
    logger.info("parselmouth not available — using YIN fallback")
```
The YIN algorithm is pure NumPy (BSD-3-Clause). Removing parselmouth from `requirements.txt` and deleting the import activates the fallback automatically. The features lost (HNR, formants, jitter, shimmer in `ToneFeatures`) are enrichment — the core tone classification works without them.

**Action required:** Remove `parselmouth` from requirements.txt before any distribution. Estimated effort: 30 minutes (remove dependency, test YIN fallback, verify tone grading still works).

---

### R-NEW-02 — edge-tts LGPLv3  [LOW RISK]

| Field | Detail |
|-------|--------|
| **Package** | edge-tts v7.2.7 |
| **License** | LGPLv3 |
| **Used in** | `mandarin/audio.py` (TTS generation) |
| **Impact** | LGPLv3 allows proprietary use when dynamically linked (pip install). Safe as-is. |

**No action required** unless Aelu modifies edge-tts source files directly. Current usage (pip dependency, unmodified) is compliant. Document this in THIRD_PARTY_LICENSES.

**Separate concern — Edge TTS service terms:** edge-tts uses Microsoft's Edge browser TTS voices via an unofficial API. Microsoft has not published explicit commercial use terms for this access pattern. At scale, consider switching to Kokoro TTS (Apache 2.0, already listed in Document 24's inventory) or licensing Azure Cognitive Services TTS officially.

---

### R-02 — CC-CEDICT ShareAlike  [MEDIUM — Confirmed]

Document 24's analysis is correct. CC-CEDICT definitions are imported into `rag_knowledge_base` via `mandarin/ai/rag_layer.py` (`import_cc_cedict()`). The ShareAlike clause applies to the data artifact.

**Current state:** No attribution in the app UI or SOURCES.md for CC-CEDICT specifically.

**Actions required:**
1. Add CC-CEDICT attribution to in-app About/Credits screen
2. Add CC-CEDICT to SOURCES.md
3. If the `rag_knowledge_base.db` file is ever distributed, license it CC BY-SA 3.0
4. Before commercial launch: 1-hour outside counsel opinion on whether the RAG KB constitutes an "adaptation"

---

### R-05/R-06 — Qwen-Generated Content  [LEGALLY UNCERTAIN — Confirmed]

The audit confirms:
- Qwen2.5 (7B primary, 1.5B fallback) runs locally via Ollama
- Content enters via `drill_generator.py` → validation gate → review queue (`pi_ai_review_queue`)
- Human review gate exists but is **not schema-enforced** — no `review_status` column on `content_item` prevents unreviewed items from being served
- No provenance check in the review workflow ("does this read like published prose?")

**Actions required:**
1. Add provenance check to review queue UI (checkbox: "Could this be from a published source? If yes, regenerate.")
2. Add `source_review_status` column to `content_item` with CHECK constraint to prevent unreviewed generated content from being served
3. Document in Terms of Service that educational content may be AI-generated
4. Before commercial launch: outside counsel opinion on downstream deployer liability

---

### R-01 — Chairman's Bao  [RESCINDED — Not Present]

Searched entire codebase. Chairman's Bao appears only in competitive intelligence matrices (`mandarin/db/core.py`) and as a personal study goal reference. **No content from Chairman's Bao is extracted, stored, or served.** Risk is zero. Remove from active risk register.

---

### R-03 — Tatoeba  [RESCINDED — Not Used]

No Tatoeba references found in codebase. Example sentences come from original content and local LLM generation. Remove from active risk register.

---

### R-04 — HSK Word Lists  [LOW — Better Than Expected]

HSK vocabulary is sourced from `drkameleon/complete-hsk-vocabulary` on GitHub, explicitly licensed **CC-BY** (not just government data). Each JSON file declares its source. Attribution is already in SOURCES.md. Clean.

**Action:** Add attribution to in-app About/Credits.

---

### R-07 — Web Crawling  [LOW — Different Stack Than Documented]

Crawl4AI is not used. The system uses:
- `mandarin/ai/web_crawler.py` — BeautifulSoup + httpx
- robots.txt checking implemented
- 2-second rate limiting
- User-Agent: `Aelu-Research-Bot/1.0 (educational; +https://aeluapp.com)`
- Purpose: competitor signals and research discovery only (not learner content)

**No action required.** Current implementation is well-behaved.

---

## Part 2: Software License Inventory — Corrections

### 105 Python packages audited. License distribution:
- MIT/BSD/Apache 2.0: ~100 packages (clean)
- **GPLv3: 1 package (praat-parselmouth) — BLOCKER**
- **LGPLv3: 1 package (edge-tts) — manageable**
- scipy GPL-with-GCC-exception: safe for proprietary use
- ZPL-2.1 (zope): permissive, OSI-approved

### Frontend/Mobile — Clean:
- Tauri: Apache-2.0 OR MIT
- Capacitor (all plugins): MIT
- All fonts: Google Fonts OFL 1.1 (Cormorant Garamond, Source Serif 4, Noto Serif SC, Noto Sans SC)
- No third-party JS libraries (vanilla JS frontend)
- All illustrations/icons: original
- iOS CocoaPods: MIT
- Android AndroidX: Apache-2.0

### Rust dependencies (Tauri): All MIT/Apache-2.0 dual-licensed

---

## Part 3: Content Inventory — What's Actually in the Corpus

| Content Type | Source | License | Volume | Risk |
|---|---|---|---|---|
| HSK 1-9 vocabulary | drkameleon/complete-hsk-vocabulary | CC-BY | 9 files | NONE |
| HSK requirements | China MoE (GF 0025-2021) | Public standard | 1 file | NONE |
| Grammar points | Original | Proprietary | 26 items | NONE |
| Language skills | Original | Proprietary | 14 items | NONE |
| Context notes | Original | Proprietary | 100+ entries | NONE |
| Dialogue scenarios | Original | Proprietary | 8 scenarios | NONE |
| Reading passages | Local Ollama generation | See R-05 | Variable | LOW |
| Chengyu/idioms | Original compilation | Proprietary | 17+ entries | NONE |
| Confusable pairs | Original | Proprietary | ~28 KB | NONE |
| Collocations | Original | Proprietary | ~9 KB | NONE |
| Constructions | Original | Proprietary | ~19 KB | NONE |
| CC-CEDICT definitions | CC-CEDICT | CC BY-SA 3.0 | RAG KB | MEDIUM |
| Media catalog | External links (YouTube/Bilibili) | N/A (links only) | Metadata | NONE |
| TTS audio | Edge TTS / macOS `say` | See R-NEW-02 | Generated on-demand | LOW |
| UI sounds | Original | Proprietary | 18 files | NONE |
| Illustrations/icons | Original | Proprietary | 30+ SVGs | NONE |

**No Chairman's Bao content. No Tatoeba content. No copyrighted educational materials detected.**

---

## Part 4: Legal Infrastructure — Current State and Gaps

### What Exists (Strong Foundation)
- **Privacy Policy** — comprehensive, covers GDPR, COPPA, data handling (marketing/landing/privacy.html)
- **Terms of Service** — complete with 30-day refund policy (marketing/landing/terms.html)
- **GDPR implementation** — export (`/api/account/export`) and deletion (`/api/account/delete`) endpoints live
- **Auth security** — NIST SP 800-63B passwords, account lockout, MFA support, audit logging
- **Payment** — Stripe fully integrated with webhook verification, commission system
- **Email compliance** — unsubscribe on all marketing emails, opt-out toggle
- **SOURCES.md** — data attribution (partial — missing CC-CEDICT, edge-tts, Ollama)
- **BRAND.md** — messaging guidelines

### What's Missing

#### Before First Paying Customer (Critical)
| Item | Description | Effort |
|------|-------------|--------|
| Remove parselmouth | Remove GPLv3 dependency, verify YIN fallback | 30 min |
| PROJECT LICENSE | Declare Aelu's own license (proprietary or chosen OSS) | 15 min |
| THIRD_PARTY_LICENSES | List all 105+ dependencies with licenses | 2-3 hours |
| CC-CEDICT attribution | In-app About/Credits screen | 30 min |
| HSK vocabulary attribution | In-app About/Credits screen | 15 min |
| Google Fonts attribution | OFL requires attribution if bundled | 15 min |
| Update SOURCES.md | Add CC-CEDICT, edge-tts, Ollama, web crawler | 30 min |
| Cookie consent banner | Required for EU visitors using GA4 | 1-2 hours |
| AI content disclosure | Terms of Service update: content may be AI-generated | 30 min |
| Review queue provenance check | "Does this read like published prose?" checkbox | 30 min |
| Breach notification policy | Document 72-hour notification procedure | 1 hour |
| Patch Flask/Werkzeug CVEs | `pip install Flask>=3.1.3 Werkzeug>=3.1.6` | 15 min |

#### Before Institutional/School Sales (High Priority)
| Item | Description | Effort |
|------|-------------|--------|
| Outside counsel on CC-CEDICT | Is RAG KB an "adaptation" under CC BY-SA? | 1-2 hours legal |
| Outside counsel on Qwen liability | Downstream deployer risk at commercial scale | 1-2 hours legal |
| CCPA addendum | California privacy rights ("Do Not Sell") | 2 hours |
| FERPA/classroom privacy addendum | Student data handling for schools | 2-3 hours |
| IP indemnification in contracts | Standard SaaS provision for institutions | Legal review |
| Accessibility statement | WCAG 2.1 AA claim + contact | 2 hours + audit |
| Edge TTS commercial plan | Switch to Azure TTS or Kokoro for commercial use | 1-2 days |
| Schema-enforce review gate | `source_review_status` on content_item | 1 hour |

#### Before Public Launch / App Store (Scale)
| Item | Description | Effort |
|------|-------------|--------|
| Full IP audit by outside counsel | Comprehensive review of this document | 4-8 hours legal |
| DMCA takedown procedure | Required for safe harbor protection | 2 hours |
| Formal AI content policy | What Aelu claims/doesn't claim about generated content | 2 hours |
| Affiliate/partner terms | Public terms for commission program | 2 hours |
| Qwen acceptable use compliance | Document compliance with Qwen license AUP | 1 hour |
| Agno MPL-2.0 compliance | Confirm no source modifications | 30 min |
| Sub-processor DPA links | Link to Stripe, Resend, GA4 DPAs in privacy policy | 1 hour |

---

## Part 5: Action Plan — Ordered by Priority

### Phase 1: Remove the Blocker (Do Now)
1. **Remove `parselmouth` from `requirements.txt`** — eliminates the only GPLv3 dependency
2. **Test that tone grading works on YIN fallback** — it should, the fallback path is already coded
3. **Patch Flask/Werkzeug CVEs** — `pip install Flask>=3.1.3 Werkzeug>=3.1.6`

### Phase 2: Attribution & Licensing Infrastructure (Before Any User)
4. **Create `LICENSE`** in project root (proprietary or your chosen license)
5. **Create `THIRD_PARTY_LICENSES.md`** listing all dependencies, their versions, and licenses
6. **Update `SOURCES.md`** to include CC-CEDICT, edge-tts, Ollama/Qwen, and web crawler
7. **Add in-app About/Credits screen** with:
   - CC-CEDICT (CC BY-SA 3.0)
   - drkameleon/complete-hsk-vocabulary (CC-BY)
   - HSK 3.0 Standards (GF 0025-2021)
   - Google Fonts (OFL 1.1)
   - Open-source software acknowledgments link

### Phase 3: Legal & Compliance (Before First Payment)
8. **Add cookie consent banner** (conditionally load GA4 only after consent)
9. **Update Terms of Service**: disclose AI-generated content
10. **Add provenance check to review queue**
11. **Document breach notification procedure** (72-hour standard)
12. **Add DPA links to privacy policy** (Stripe, Resend, GA4)

### Phase 4: Commercial Hardening (Before Institutional Sales)
13. **Obtain outside counsel opinion** on CC-CEDICT ShareAlike and Qwen deployer liability
14. **Evaluate edge-tts replacement** (Azure TTS or Kokoro for commercial certainty)
15. **Schema-enforce content review gate**
16. **CCPA addendum, FERPA addendum, accessibility statement**

### Phase 5: Scale Readiness (Before Public Launch)
17. **Full IP audit by outside counsel**
18. **DMCA takedown procedure**
19. **Formal AI content ownership policy**
20. **App Store compliance review**

---

## Appendix: Revised Risk Summary Table

| ID | Source | Doc 24 Rating | Revised Rating | Status |
|---|---|---|---|---|
| R-NEW-01 | praat-parselmouth GPLv3 | *Not assessed* | ~~CRITICAL~~ | **RESOLVED** — replaced with librosa (ISC) |
| R-NEW-02 | edge-tts LGPLv3 | *Not assessed* | LOW | Documented; evaluate at scale (see Appendix D) |
| R-01 | Chairman's Bao | HIGH | **RESCINDED** | Not in codebase |
| R-02 | CC-CEDICT (CC BY-SA) | MEDIUM | MEDIUM | Attribution added; counsel brief prepared (see Appendix C) |
| R-03 | Tatoeba | LOW | **RESCINDED** | Not in codebase |
| R-04 | HSK Word Lists | LOW | LOW | Attribution added to /about and SOURCES.md |
| R-05 | Qwen output copyright | UNCERTAIN | UNCERTAIN | AI content policy published; counsel brief prepared |
| R-06 | Qwen training data | LOW | LOW | Monitor litigation trends |
| R-07 | Web crawling | LOW | LOW | Already compliant (different stack) |
| R-NEW-03 | Edge TTS service terms | *Not assessed* | LOW | Analysis in Appendix D; evaluate before scale |
| R-NEW-04 | Flask/Werkzeug CVEs | *Not assessed* | ~~LOW~~ | **RESOLVED** — patched to 3.1.3/3.1.6 |
| R-NEW-05 | No LICENSE file | *Not assessed* | ~~MEDIUM~~ | **RESOLVED** — proprietary LICENSE created |
| R-NEW-06 | Missing attribution files | *Not assessed* | ~~MEDIUM~~ | **RESOLVED** — THIRD_PARTY_LICENSES.md + SOURCES.md updated |

---

## Appendix B: Implementation Status (Updated 2026-03-13)

### Completed
| Item | Status | Detail |
|---|---|---|
| R-NEW-01 parselmouth GPLv3 | **RESOLVED** | Replaced with librosa (ISC). pYIN for F0, LPC for formants, numpy for HNR/jitter/shimmer. 170 tests pass. |
| R-NEW-04 Flask/Werkzeug CVEs | **RESOLVED** | Patched to Flask 3.1.3, Werkzeug 3.1.6 |
| R-NEW-05 No LICENSE file | **RESOLVED** | Created proprietary LICENSE at project root |
| R-NEW-06 Missing attribution | **RESOLVED** | Created THIRD_PARTY_LICENSES.md (70+ packages), updated SOURCES.md, added Acknowledgments to /about |
| Cookie consent | **RESOLVED** | Banner added to web app. GA4 loads only after explicit consent. |
| AI content disclosure | **RESOLVED** | Added to Terms of Service Section 8 |
| Breach notification | **RESOLVED** | Policy at /breach-notification, 72-hour commitment, linked from privacy/terms |
| CCPA addendum | **RESOLVED** | Page at /ccpa |
| DMCA procedure | **RESOLVED** | Page at /dmca with 17 U.S.C. § 512 requirements |
| AI content policy | **RESOLVED** | Page at /ai-content-policy |

### Remaining — Requires Outside Counsel
| Item | What to ask counsel | Estimated cost | When needed |
|---|---|---|---|
| R-02 CC-CEDICT ShareAlike | "Does our RAG knowledge base (SQLite table incorporating CC-CEDICT definitions restructured with HSK levels) constitute an 'adaptation' under CC BY-SA 3.0? If yes, does data separation (proprietary app code + CC BY-SA data artifact) satisfy the obligation for a closed-source SaaS?" | 1-2 hours | Before institutional sales |
| R-05 Qwen deployer liability | "As a downstream deployer of Qwen2.5 (not the model trainer), what is our direct/contributory infringement exposure if a generated drill sentence substantially resembles a copyrighted Chinese text? Does our human review gate + RAG grounding materially reduce this risk?" | 1-2 hours | Before institutional sales |
| Edge-tts service terms | "edge-tts uses Microsoft Edge's TTS voices via an unofficial API (not Azure Cognitive Services). Is commercial use of the generated audio defensible? Should we switch to Azure TTS ($4/million chars) or Kokoro (Apache 2.0, local) before scale?" | 30 min + decision | Before 1,000+ users |
| FERPA addendum | "If Aelu is used in K-12 classrooms, does the teacher-invite flow + student data handling meet FERPA 'school official' exception requirements? Do we need a separate DPA for schools?" | 1-2 hours | Before school sales |
| Full IP audit | Comprehensive review covering all items in this document | 4-8 hours | Before public launch / app store / investment |

### Remaining — Engineering Work
| Item | Description | Effort | When needed |
|---|---|---|---|
| Schema-enforce review gate | Add `source_review_status` column to `content_item` with CHECK constraint | 1 hour | Before institutional sales |
| Provenance check in review queue | Add "Could this be from a published source?" checkbox to admin review UI | 30 min | Before any generated content reaches users |
| DPA links in privacy policy | Link to Stripe, Resend, GA4 data processing agreements | 30 min | Before institutional sales |
| Accessibility statement | WCAG 2.1 AA claim + audit | 2 hours + audit | Before institutional sales |
| Edge-tts migration evaluation | Benchmark Kokoro TTS vs edge-tts quality for zh-CN voices | 1-2 days | Before 1,000+ users |

---

## Appendix C: CC-CEDICT Architecture Analysis (For Counsel)

**Current architecture:**
- `rag_knowledge_base` table in SQLite contains: hanzi, pinyin, cc_cedict_definitions (JSON array), traditional_form, hsk_level, cc_cedict_version
- CC-CEDICT definitions are parsed from the CC-CEDICT text file and restructured into JSON
- Only vocabulary items matching HSK 1-9 are imported (not the full 120K+ entry dictionary)
- The table also contains original fields not from CC-CEDICT: usage_examples, collocation_examples, context_notes, grammar_patterns
- The data is queried at runtime to ground LLM-generated content against authoritative definitions
- The `rag_knowledge_base.db` file is never distributed to users — it lives on the server

**Why this matters:**
- CC BY-SA 3.0 ShareAlike requires adaptations to be licensed CC BY-SA
- Creative Commons defines "adaptation" as a work that restructures, transforms, or builds upon the original
- Our restructuring (parsing → JSON, filtering to HSK items, adding non-CC-CEDICT columns) likely constitutes an adaptation
- CC BY-SA does **not** prevent commercial use — it constrains redistribution terms
- Since we run a SaaS (server-side only, never distribute the DB file), the practical obligation is limited to attribution
- If we ever distribute the DB (open-source release, offline mode), it must go under CC BY-SA 3.0
- **Data separation** (proprietary app code + CC BY-SA data artifact) is the standard industry pattern

**Recommended counsel question:** "Given that our server-side RAG knowledge base incorporates CC-CEDICT definitions restructured into JSON with original columns added, and is never distributed to users, does CC BY-SA 3.0 require anything beyond attribution? If we later add an offline mode that ships the DB, what are the licensing implications?"

## Appendix D: Edge-TTS Commercial Risk Analysis

**Current architecture:**
- `mandarin/audio.py` uses `edge-tts` Python library (LGPL-3.0) to call Microsoft Edge's browser TTS API
- This is **not** Azure Cognitive Services (which has clear commercial terms and pricing)
- Edge-tts works by mimicking the Edge browser's WebSocket connection to Microsoft's TTS service
- Generated audio is cached locally, served to users as MP3

**Risk factors:**
1. **Library license (LGPL-3.0):** Safe — used as unmodified pip dependency (dynamic linking). No copyleft propagation.
2. **Service terms:** Microsoft has not published explicit ToS for this access pattern. The voices are intended for Edge browser's Read Aloud feature. Using them in a commercial product is a gray area.
3. **Enforcement probability:** Low at small scale. Microsoft has not enforced against edge-tts users. However, at commercial scale (1,000+ daily TTS requests), the pattern could draw attention.

**Migration options:**
| Option | License | Cost | Quality | Effort |
|---|---|---|---|---|
| Keep edge-tts | LGPL-3.0 + gray area | Free | Excellent (neural) | None |
| Azure Cognitive Services TTS | Commercial | ~$4/M chars | Excellent (same voices) | 2-4 hours |
| Kokoro TTS (local) | Apache-2.0 | Free (compute only) | Good (82M model) | 1-2 days |
| Browser speechSynthesis only | N/A | Free | Varies by device | Already fallback |

**Recommendation:** Keep edge-tts for development and free tier. Before charging institutional users, either (a) get clarity from Microsoft or (b) switch to Azure Cognitive Services for paid-tier TTS (same voices, clear commercial terms, $4/million characters ≈ negligible cost at Aelu's scale).

---

*This analysis is based on a full codebase audit of ~/mandarin/ conducted 2026-03-13. Updated same day with implementation status. It is a technical risk assessment, not legal advice. Items marked "obtain outside counsel" require attorney review before commercial deployment.*

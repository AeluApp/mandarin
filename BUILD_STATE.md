# Mandarin Learning System — Build State

## Status: MOBILE-READY (V2 + Phases A-F)

**Date:** 2026-03-15
**Content library:** HSK 1-9 canonical word lists (10,000+ items via `add-hsk`), context notes, 134 auto-tagged, 30 dialogue scenarios
**Grammar/skills:** 26 grammar points (HSK 1-3), 14 language skills seeded
**Schema:** V121 (84 tables, 6-stage mastery lifecycle, observability, security audit, MFA challenge, grade appeal, activation tracking, security scans, quality infrastructure, experiment proposals, graduated rollouts, openclaw scheduler)
**Tests:** 4061 passed, 2 skipped, 0 failed across 212 suites (~5m08s runtime)
**Skips:** 2 E2E (Playwright not installed — requires browser binary, runs in separate CI job)
**Warnings:** 48 (InsecureKeyLengthWarning from test JWT secrets — cosmetic, not blocking)
**Mobile:** Capacitor shell staged, JWT auth, offline sync, native plugin bridge

### Mobile Readiness (2026-02-21)
| Phase | Scope | Status |
|---|---|---|
| A: API Hardening | JWT auth, V1 prefix rewrite, structured errors | DONE |
| B: Capacitor Shell | package.json, config, icon/splash, asset gen | DONE |
| C: Native Plugins | Haptics, push, keyboard, status bar, deep links | DONE |
| D: Offline Sync | IndexedDB queue, sync push/pull/state endpoints | DONE |
| E: App Store Prep | Submission checklist (iOS + Android) | DONE |
| F: Mobile UX | Touch targets, swipe gestures, keyboard-aware CSS | DONE |

#### New files (Phase A-F)
| File | Purpose |
|---|---|
| `mandarin/web/api_errors.py` | Structured error codes + `api_error()` builder |
| `mandarin/jwt_auth.py` | JWT access tokens (HS256) + hashed refresh tokens |
| `mandarin/web/token_routes.py` | `POST /api/auth/token`, `/token/mfa`, `/refresh`, `/revoke` |
| `mandarin/web/sync_routes.py` | `POST /api/sync/push`, `GET /sync/pull`, `/sync/state` |
| `mandarin/web/static/capacitor-bridge.js` | Native plugin wrappers (no-op in browser) |
| `mandarin/web/static/offline-queue.js` | IndexedDB queue with auto-flush |
| `mobile/package.json` | Capacitor 6 deps |
| `mobile/capacitor.config.ts` | App config (Civic Sanctuary colors) |
| `mobile/generate-assets.sh` | macOS `sips` icon/splash resizer |
| `mobile/ios-plist-additions.xml` | Microphone + ATS Info.plist keys |
| `mobile/resources/icon.png` | 1024x1024 app icon (漫 in terracotta) |
| `mobile/resources/splash.png` | 2732x2732 splash screen |
| `mobile/store-assets/submission-checklist.md` | iOS + Android submission steps |

#### Migration v17
- `user.refresh_token_hash TEXT` — SHA-256 of refresh token
- `user.refresh_token_expires TEXT` — 30-day expiry
- `push_token` table — per-user per-platform push tokens

#### New API routes (8)
- `POST /api/auth/token` — email+password → JWT + refresh
- `POST /api/auth/token/refresh` — refresh → new JWT
- `POST /api/auth/token/revoke` — clear refresh token
- `POST /api/sync/push` — batched offline actions
- `GET /api/sync/pull` — progress/sessions since timestamp
- `GET /api/sync/state` — state hash for quick comparison
- `POST /api/push/register` — store device push token
- `POST /api/push/unregister` — remove push token

#### Modified files
- `mandarin/settings.py` — JWT_SECRET, JWT_ACCESS_EXPIRY_HOURS, JWT_REFRESH_EXPIRY_DAYS
- `mandarin/db/core.py` — SCHEMA_VERSION=121 (experiment_proposal + experiment_rollout tables)
- `mandarin/web/__init__.py` — V1PrefixMiddleware, JWT request_loader, blueprint registration
- `mandarin/web/routes.py` — public prefixes, CORS Authorization header, push endpoints
- `mandarin/web/static/app.js` — Capacitor bridge init, haptics, JWT WS token, touch gestures, offline indicator
- `mandarin/web/static/style.css` — keyboard-aware input, coarse-pointer targets, in-session overscroll
- `pyproject.toml` — PyJWT>=2.8.0
- `.env.example` — JWT env vars

---

## Master Build Brief Compliance Audit

### 1. System Goals
| Requirement | Status | Location |
|---|---|---|
| Zero Claude tokens at runtime | DONE | All modules — deterministic |
| SQLite local-first, offline-capable | DONE | `db.py`, WAL mode, FK, Row factory |
| Interest-driven, not rote | DONE | Content lens weighting, engagement scores |
| Skip-tolerant, no shame | DONE | Gap messages, gap normalization |

### 2. Learner Persona
| Requirement | Status | Location |
|---|---|---|
| learner_profile.json at repo root | DONE | `db.py:load_learner_profile_json()` |
| Profile drives scheduling/tone | DONE | Scheduler reads profile preferences |

### 3. Content Lenses
| Requirement | Status | Location |
|---|---|---|
| 9 content lens categories | DONE | `schema.sql` (learner_profile columns) |
| Auto-tagging by keyword | DONE | `importer.py:auto_tag_lens()` |
| Core lenses inject when low | DONE | `scheduler.py:_get_core_injection_items()` |

### 4. Media Ingestion
| Requirement | Status | Location |
|---|---|---|
| CSV import | DONE | `cli.py:import_csv` |
| SRT/VTT subtitle import | DONE | `cli.py:import_srt` |
| Manual add | DONE | `cli.py:add` |
| content_source table | DONE | `schema.sql` |
| Audio metadata columns | DONE | `content_item.audio_available`, `audio_file_path`, `clip_start_ms`, `clip_end_ms` |

### 5. Listening Design
| Requirement | Status | Location |
|---|---|---|
| Listening gist drill (text V0) | DONE | `drills/listening.py` |
| Audio playback (V1+) | DEFERRED | Schema ready (audio columns), runtime not yet |

### 6. Linguistic Intuition
| Requirement | Status | Location |
|---|---|---|
| Intuition drill type | DONE | `drills/production.py` |
| intuition_attempts/correct tracking | DONE | `progress` table columns |
| Register expansion gated by intuition | DONE | `scheduler.py` |

### 7. Error-Shape Tracking
| Requirement | Status | Location |
|---|---|---|
| Error classification (14 types) | DONE | `schema.sql` CHECK constraint |
| Error types: tone, segment, ime_confusable | DONE | `drills/mc.py` |
| Error types: grammar, vocab, other | DONE | drill return values |
| Error types: register_mismatch, particle_misuse | DONE | schema, available for use |
| Error types: function_word_omission, temporal_sequencing | DONE | schema, available for use |
| Error types: measure_word, politeness_softening | DONE | schema, available for use |
| Error types: reference_tracking, pragmatics_mismatch | DONE | schema (V1 R2 addition) |
| Error-informed drill scheduling | DONE | `scheduler.py` ERROR_DRILL_PREFERENCE |
| error_focus table + lifecycle | DONE | `db.py:update_error_focus()` |

### 8. IME Rules
| Requirement | Status | Location |
|---|---|---|
| Accepts tone marks (mā) | DONE | `drills/pinyin.py` |
| Accepts tone numbers (ma1) | DONE | `drills/pinyin.py` |
| Accepts plain pinyin (mama) | DONE | marked as no_tone match |
| Error classification for IME | DONE | `drills/mc.py` |

### 9. Diagnostics
| Requirement | Status | Location |
|---|---|---|
| Quick assess (≥10 sessions) | DONE | `diagnostics.py:assess_quick()` |
| Full assess (≥20 sessions) | DONE | `diagnostics.py:assess_full()` |
| Band-based HSK estimation | DONE | `diagnostics.py:_estimate_levels()` |
| HSK_CUMULATIVE/HSK_BAND_SIZE constants | DONE | `diagnostics.py` |
| Bottleneck detection with actions | DONE | Every bottleneck has area, data, action, test |
| Stage-aware core stability | DONE | Uses `mastery_stage IN ('stable','durable')` |
| Winsorized mean for velocity | DONE | `_compute_velocity()` trims top/bottom 10% |

### 10. Forecasting
| Requirement | Status | Location |
|---|---|---|
| Data-driven mastery rate | DONE | `diagnostics.py:_compute_mastery_rate()` |
| Vocab gap projection | DONE | `diagnostics.py:_project_milestones()` |
| Calendar-time estimates | DONE | sessions → weeks → months |
| Confidence labels | DONE | low/medium/high based on data |
| Per-modality projections | DONE | `project_forecast()` modality_projections |
| Half-life retention model | DONE | `retention.py` SM-2 variant |

### 11. Interest Drift
| Requirement | Status | Location |
|---|---|---|
| Drift detection in improve.py | DONE | `improve.py:_check_interest_drift()` |
| Lens engagement scoring | DONE | learner_profile lens columns |
| Content expansion proposals | DONE | when high-engagement lenses run dry |

### 12. Session UX
| Requirement | Status | Location |
|---|---|---|
| Standard session (day-adjusted) | DONE | `scheduler.py:plan_standard_session()` |
| Mini session (90s) | DONE | `scheduler.py:plan_minimal_session()` |
| Catch-up session (weak spots) | DONE | `scheduler.py:plan_catchup_session()` |
| Calibration session | DONE | `diagnostics.py:plan_calibrate_session()` |
| Q to quit, B for boredom | DONE | `runner.py` checks |
| Day-of-week profiles | DONE | `scheduler.py:DAY_PROFILES` |
| Gap messages (7 tiers) | DONE | `scheduler.py:GAP_MESSAGES` |
| Session summary with gains | DONE | `runner.py:_finalize()` |

### 13. Non-Terminal UX
| Requirement | Status | Location |
|---|---|---|
| `./run` launcher script | DONE | `run` (bash, chmod +x) |
| `./run menu` interactive menu | DONE | `menu.py:run_menu()` |
| No business logic duplication | DONE | menu calls same core modules |
| Rich + Typer CLI | DONE | `cli.py` |

### 14. Reporting
| Requirement | Status | Location |
|---|---|---|
| Truthful — no "unlock" language | DONE | Verified: no "unlock" in source |
| No "learned"/"mastered" below stable | DONE | Verified: `test_no_learned_label_below_stable` |
| Gap normalization | DONE | `reports.py`, `runner.py` |
| Error bar visualization | DONE | `reports.py` |
| Recent gains tracking | DONE | `reports.py:_compute_recent_gains()` |
| Every output answers 3 questions | DONE | what/do/test pattern throughout |
| 6-stage mastery labels in all surfaces | DONE | `cli.py`, `menu.py`, `runner.py`, `reports.py` |

### 15. Drill Integrity
| Requirement | Status | Location |
|---|---|---|
| 3 confidence states: full, ?, N | DONE | All 8 drill types + `_handle_confidence()` |
| ? = 50/50 partial credit | DONE | `db.py:record_attempt()` confidence="half" |
| N = still_unknown, no penalty | DONE | `db.py:record_attempt()` confidence="unknown" |
| Sticky hanzi hints on miss | DONE | `drills/hints.py` with 4 rotation types |
| Smart MC distractors | DONE | `drills/mc.py` — mastered_strong exclusion, length invariants |
| Drill input validation | DONE | `drills/base.py` |

### 16. Hanzi Display
| Requirement | Status | Location |
|---|---|---|
| Prominent hanzi (spaced, bold) | DONE | `drills/base.py` |
| Gated on avg level < 6.0 | DONE | `runner.py` computes prominent flag |
| Inline hanzi in feedback | DONE | `drills/base.py` |

### 17. Scaling Ladder
| Requirement | Status | Location |
|---|---|---|
| scale_level on content_item | DONE | word → sentence → paragraph → article |
| Auto-tagging sentences/phrases | DONE | `db.py` migration sets sentence/phrase items |

### 18. Grammar / Skills
| Requirement | Status | Location |
|---|---|---|
| grammar_point table | DONE | `schema.sql`, `db.py` migration |
| skill table | DONE | `schema.sql`, `db.py` migration |
| content_grammar junction | DONE | `schema.sql` |
| content_skill junction | DONE | `schema.sql` |
| 26 seed grammar points (HSK 1-3) | DONE | `grammar_seed.py` |
| 14 seed skills (pragmatic, register, cultural, phonetic) | DONE | `grammar_seed.py` |
| CLI: grammar, skills, seed-grammar | DONE | `cli.py` |
| Skill coverage tracking | DONE | `db.py:get_skill_coverage()` |

### 19. Core Lexicon Safety
| Requirement | Status | Location |
|---|---|---|
| Core coverage check | DONE | `db.py:get_core_lexicon_coverage()` |
| Catch-up injection when <50% | DONE | `scheduler.py` core safety check block |
| Core lenses: function_words, time_sequence, numbers_measure | DONE | Checked every session |

### 20. Self-Improvement
| Requirement | Status | Location |
|---|---|---|
| Pattern detection (5 triggers) | DONE | `improve.py:detect_patterns()` |
| Interest drift detection | DONE | `improve.py:_check_interest_drift()` |
| Proposal lifecycle (propose/apply/rollback) | DONE | `improve.py` |
| improvement_log table | DONE | `schema.sql` |

### 21. Claude Usage Model
| Requirement | Status | Location |
|---|---|---|
| Zero tokens at runtime | DONE | All logic deterministic |
| Claude used only at build time | DONE | This document |

### 22. Implementation Constraints
| Requirement | Status | Location |
|---|---|---|
| Python 3.9+ | DONE | venv at ~/mandarin/venv |
| SQLite WAL + FK + Row factory | DONE | `db.py:get_connection()` |
| Idempotent migrations | DONE | `db.py:_migrate()` (V7) |
| No external API calls | DONE | Verified |

### 23. Mastery Lifecycle (6 stages)
| Requirement | Status | Location |
|---|---|---|
| seen → passed_once → stabilizing → stable → durable → decayed | DONE | `db/progress.py:record_attempt()` |
| Schema V7+: stable_since_date, successes_while_stable | DONE | `db/core.py` migration (V7) |
| Backfill: weak→seen/passed_once, improving→stabilizing | DONE | `db/core.py` migration (V7) |
| Promotion: streak/days/drill_types/attempts criteria | DONE | `db/progress.py` |
| Demotion: stable/durable→decayed (streak_incorrect≥2) | DONE | `db/progress.py` |
| Recovery: decayed→stabilizing (streak_correct≥3) | DONE | `db/progress.py` |
| Regression: stabilizing→seen (streak_incorrect≥3) | DONE | `db/progress.py` |
| Durable: 60+ days stable, 7+ successes_while_stable | DONE | `db/progress.py` |
| All UI surfaces use 6-stage labels | DONE | cli, menu, runner, reports |
| get_stage_counts returns all 6 + unseen | DONE | `milestones.py` |
| Backward-compat aliases (weak, improving) | DONE | `milestones.py`, `db/progress.py` |

### 24. Reliability (North Star Phase 0)
| Requirement | Status | Location |
|---|---|---|
| Fix 4 unsafe fetchone()[0] patterns | DONE | `cli.py:139,1229,1230`, `db/content.py:120` |
| WebSocket reconnect (exponential backoff) | DONE | `web/static/app.js` |
| Max 5 reconnect attempts + reload banner | DONE | `web/static/app.js` |
| Enter key starts session from home | DONE | `web/static/app.js` |
| Bridge correlation IDs (session_uuid) | DONE | `web/bridge.py`, `web/routes.py` |

---

## Schema (84 tables, V121)

| Table | Purpose |
|---|---|
| user | Multi-user accounts (email, password, tier, JWT refresh tokens) |
| learner_profile | Per-user learner state (levels, confidence, lens scores) |
| content_item | All learnable items (vocab, sentence, phrase, chunk, grammar) |
| progress | Per-item per-modality SRS state (6-stage mastery, half-life retention) |
| session_log | Session lifecycle + instrumentation |
| session_metrics | Per-session retention metrics (recall, strengthened, weakened) |
| error_log | Every miss, classified by error shape (14 types) |
| error_focus | Error-informed drilling lifecycle |
| content_source | Media/source tracking |
| improvement_log | Self-improvement proposals |
| dialogue_scenario | Conversation scenario trees (JSON) |
| grammar_point | Discrete grammar structures (26 seeded) |
| skill | Functional language skills (14 seeded) |
| content_grammar / content_skill | Junction tables |
| construction / content_construction | Grammar constructions + content links |
| audio_recording | Recorded audio attempts for tone grading |
| vocab_encounter | Reading/listening lookup tracking for cleanup loop |
| push_token | Mobile push notification tokens (per-user, per-platform) |
| invite_code | Registration invite codes |
| probe_log | Diagnostic probe results per scenario |
| media_watch | Media exposure tracking (watched, liked, scores) |
| affiliate_partner | Affiliate/referral partner registry |
| referral_tracking | Referral visit + signup tracking |
| affiliate_commission | Affiliate commission records |
| discount_code | Promotional discount codes |
| lifecycle_event | Subscription lifecycle event log |
| security_audit_log | Security event audit trail |
| data_deletion_request | GDPR deletion request tracking |
| speaker_calibration | TTS voice calibration data |
| crash_log | Server-side unhandled exception log |
| client_error_log | Client-side JS error reports |
| mfa_challenge | Short-lived MFA challenge tokens (DB-backed, multi-worker safe) |
| grade_appeal | Grade appeal workflow for disputed drill results |
| experiment_proposal | Daemon-generated experiment proposals (from churn signals) |
| experiment_rollout | Graduated rollout tracking (pending→25%→50%→100%→complete) |

---

## CLI Commands (29)

| Command | What it does |
|---|---|
| `mandarin` | Run today's standard session (shows day profile) |
| `mandarin mini` | 90-second minimal session |
| `mandarin catchup` | Catch-up session (weak spots) |
| `mandarin calibrate` | Calibration session for level estimation |
| `mandarin add-hsk <n>` | Load HSK vocabulary for level 1-9 |
| `mandarin import-csv <file>` | Import vocabulary from CSV |
| `mandarin import-srt <file>` | Import sentences from subtitles |
| `mandarin add <hanzi> <pinyin> <english>` | Add single item |
| `mandarin tag-lenses` | Auto-tag content with lenses |
| `mandarin encounters` | Show vocab encounter summary |
| `mandarin import-scenarios <dir>` | Import dialogue scenarios (V1) |
| `mandarin scenarios` | List available dialogue scenarios |
| `mandarin seed-grammar` | Load grammar points + skills |
| `mandarin status` | Current learning status |
| `mandarin report` | Full progress report |
| `mandarin assess [--full]` | Diagnostic assessment |
| `mandarin forecast` | Learning projections |
| `mandarin history [-n N]` | Recent session history |
| `mandarin errors [-n N]` | Recent error details |
| `mandarin grammar` | Show grammar points |
| `mandarin skills` | Show language skills + coverage |
| `mandarin improve [--apply/--rollback]` | Self-improvement proposals |
| `mandarin library` | Content library breakdown |
| `mandarin reset` | Reset database (destructive) |

Also: `./run menu` for non-terminal interactive menu (numbered choices, no typing).

---

## Drill Types (12)

| Type | Modality | Description |
|---|---|---|
| mc | reading | Hanzi → pick English meaning |
| reverse_mc | reading | English → pick hanzi |
| ime_type | ime | Type pinyin for given hanzi |
| tone | reading | Pick correct toned pinyin |
| listening_gist | listening | Pinyin → pick meaning |
| english_to_pinyin | reading | English → pick pinyin |
| hanzi_to_pinyin | reading | Hanzi → pick pinyin |
| intuition | reading | "Which sounds most natural?" |
| dialogue | reading | Multi-turn conversation scenario |

All 8 non-dialogue drills support: `?` (50/50), `N` (unknown), `Q` (quit), `B` (bored).

---

## Architecture

```
mandarin/
├── __init__.py          # Version
├── cli.py               # Typer CLI — 29 commands
├── jwt_auth.py          # JWT access + refresh token management
├── db/                  # Database package
│   ├── __init__.py      # Re-exports (get_connection, init_db, etc.)
│   ├── core.py          # Schema, migrations (V100), connection management
│   ├── content.py       # Content item queries, context notes
│   ├── progress.py      # SRS engine, 6-stage mastery, retention model integration
│   └── session.py       # Session lifecycle
├── scheduler.py         # Gap-aware, day-profile, error-informed session planning
├── drills/              # 12 drill types + confidence states + hints + smart distractors
├── conversation.py      # Dialogue drill engine
├── scenario_loader.py   # Scenario JSON import/query
├── grammar_seed.py      # 26 grammar points + 14 skills seed data
├── runner.py            # Session execution loop (vocab + dialogue drills)
├── importer.py          # CSV, SRT, manual content import
├── diagnostics.py       # Assessment, projections, winsorized velocity, stage-aware stability
├── reports.py           # Humane progress reports
├── retention.py         # Half-life retention model (SM-2 variant)
├── milestones.py        # Real-world capability milestones, 6-stage counts
├── improve.py           # Self-improvement pattern detection + interest drift
├── menu.py              # Non-terminal interactive menu
├── audio.py             # macOS TTS audio playback
├── tone_grading.py      # Tone accuracy grading
├── context_notes.py     # Context notes for vocabulary items
└── web/                 # Web interface package
    ├── __init__.py      # App factory, V1PrefixMiddleware, JWT request loader
    ├── routes.py        # Flask routes + WebSocket session endpoints
    ├── api_errors.py    # Structured error codes for mobile API
    ├── token_routes.py  # JWT token obtain/refresh/revoke
    ├── sync_routes.py   # Offline sync push/pull/state
    ├── experiment_daemon.py  # Autonomous A/B testing daemon (6-hour cycle)
    ├── bridge.py        # Show/input bridge with correlation IDs
    ├── static/app.js    # WebSocket client + Capacitor + offline queue
    ├── static/capacitor-bridge.js  # Native plugin wrappers
    ├── static/offline-queue.js     # IndexedDB offline queue
    ├── static/style.css
    └── templates/index.html
mobile/                  # Capacitor shell (iOS/Android)
run                      # Bash launcher (./run, ./run menu, ./run app, ./run help)
schema.sql               # Full schema (84 tables, V121)
learner_profile.json     # Persona configuration
tests/                       # 4061 tests across 212 suites
data/
├── mandarin.db          # SQLite database
├── hsk/                 # HSK 4-9 vocabulary JSON
└── scenarios/           # 8 dialogue scenario JSON files
```

---

## Features Built

### V1 Round 1 (2026-02-10)
- [x] Bigger hanzi font (prominent display, gated on level)
- [x] Band-based HSK estimation + data-driven projections
- [x] Day-of-week session profiles (consolidation/stretch modes)
- [x] Error-informed drilling (error_focus lifecycle + priority slots)
- [x] Conversation drills Phase A (dialogue type + 8 scenarios)

### V1 Round 2 (2026-02-10)
- [x] `./run` launcher script + `./run menu` interactive menu
- [x] Confidence states: `?` (50/50 partial credit), `N` (unknown, no penalty)
- [x] Sticky hanzi hint engine (4 rotation types: radical, contrast, component, phonetic)
- [x] Smart MC distractors (mastered_strong exclusion, length invariants)
- [x] Grammar/skill data model (26 grammar points, 14 skills, junction tables)
- [x] Core lexicon safety check (catch-up trigger when <50% coverage)
- [x] Register expansion gating (professional register gated by intuition accuracy)
- [x] Interest drift detection + content expansion proposals
- [x] Audio metadata columns (audio_available, audio_file_path, clip timestamps)
- [x] 14 error types (added reference_tracking, pragmatics_mismatch)
- [x] Scaling ladder (word → sentence → paragraph → article)
- [x] No "unlock" language anywhere in system

### V2 (2026-02-11)
- [x] db/ package refactor (core, content, progress, session modules)
- [x] Context notes (cultural/usage/mnemonic/grammar notes keyed by hanzi)
- [x] Half-life retention model (SM-2 variant, difficulty tracking)
- [x] macOS TTS audio playback
- [x] Speaking drill with tone grading
- [x] Web interface (Flask + WebSocket, drill sessions in browser)
- [x] Register/pragmatic/slang drill types
- [x] Streak counter + momentum indicator
- [x] Focus command (target specific items)
- [x] HSK 7-9 support
- [x] Scaffolded N flow (narrow to 2)
- [x] Adaptive day profiles
- [x] Interleaving enforcement
- [x] All self-improvement proposals executable
- [x] Striking hanzi (bright_cyan)

### North Star (2026-02-14)
- [x] 6-stage mastery lifecycle (seen/passed_once/stabilizing/stable/durable/decayed)
- [x] Schema V7+ migration with backfill from 3-stage to 6-stage (now at V17)
- [x] Promotion: streak/days/drill_types/attempts criteria
- [x] Demotion: stable/durable→decayed, stabilizing→seen
- [x] Recovery: decayed→stabilizing
- [x] Durable: 60+ days stable, 7+ successes
- [x] Fix 4 unsafe fetchone()[0] crash patterns
- [x] WebSocket reconnect with exponential backoff (max 5 attempts)
- [x] Enter key starts session from home screen
- [x] Bridge correlation IDs (session_uuid for debugging)
- [x] Winsorized mean for velocity (trim top/bottom 10%)
- [x] Stage-aware core stability (mastery_stage IN stable/durable)
- [x] Honest UI labels: no "learned"/"mastered" below stable
- [x] 6-stage breakdown in status, menu, runner, reports
- [x] 4061 tests across 212 suites — 0 failures, 2 skipped (Playwright E2E)

---

## Deferred Items

| Item | Reason | Blocker |
|---|---|---|
| Listening sub-categories | Needs measurement integrity first | Phase 2 Pedagogy |
| Scaffold Level 1 (hanzi+pinyin only) | Needs measurement integrity first | Phase 2 Pedagogy |
| HSK requirements registry | Needs measurement integrity first | Phase 2 Pedagogy |
| Anti-gaming (option length, distractor logging) | Needs measurement integrity first | Post-North Star |
| Behavioral economics (streak cap, consistency messaging) | Needs measurement integrity first | Post-North Star |
| WS session resumption (server-side state) | Complex — after basic reconnect works | Post-North Star |
| YouTube/yt-dlp scraping | Media pipeline | External tool |
| parselmouth tone analysis | Build fails on Python 3.9 | Python upgrade |

---

## Quick Start

```bash
cd ~/mandarin
./run                       # today's session
./run menu                  # interactive menu
./run app                   # web interface
./run mini                  # 90-second session
./run status                # check progress
./run report                # full progress report
./run forecast              # learning projections
./run help                  # all commands
```

Or with the CLI directly:
```bash
source venv/bin/activate
mandarin                    # run a session
mandarin status             # 6-stage mastery breakdown
mandarin forecast           # stage-aware projections
mandarin assess             # diagnostic (after 10+ sessions)
mandarin improve            # self-improvement proposals
```

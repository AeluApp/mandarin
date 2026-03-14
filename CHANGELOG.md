# Changelog

All notable changes to Aelu are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Operations research documentation (Monte Carlo simulation, survival analysis, optimization models)
- Architecture Decision Records (ADR-001 through ADR-010)
- PR and issue templates
- Cost of Delay analysis framework with CD3 prioritization

---

## [2.12.0] - 2026-03-08

### Security
- Automated security scanning scheduler (bandit + pip-audit) with `security_scan` and `security_scan_finding` tables
- Security scan results stored in database for audit trail
- Background scheduler runs daily scans with DB-backed locking

---

## [2.11.0] - 2026-03-05

### Added
- GDPR compliance: data export (`/api/gdpr/export`) and deletion (`/api/gdpr/delete`) endpoints
- `data_deletion_request` table tracking deletion requests through pending/processing/completed lifecycle
- User `anonymous_mode` and `marketing_opt_out` fields
- Data retention policies with automatic purge scheduler (crash logs 90d, client errors 30d, audit logs 365d)

---

## [2.10.0] - 2026-03-01

### Added
- Classroom system: teacher accounts, classroom creation, student enrollment via invite codes
- `classroom`, `classroom_student` tables with teacher-student relationships
- LTI 1.3 integration for LMS platforms (`lti_platform`, `lti_user_mapping` tables)
- Classroom billing (per-student Stripe subscriptions)
- Teacher dashboard with student progress overview

---

## [2.9.0] - 2026-02-27

### Added
- Stripe payment integration for premium subscriptions
- `subscription_tier` field (free/paid/admin) on user table
- Tier gating for premium features (`tier_gate.py`)
- Affiliate system: partner codes, referral tracking, commission calculation
- `affiliate_partner`, `referral_tracking`, `affiliate_commission`, `discount_code` tables

---

## [2.8.0] - 2026-02-24

### Added
- MFA (TOTP) support: `totp_secret`, `totp_enabled`, `totp_backup_codes` on user table
- `mfa_challenge` table for two-factor auth flow
- Email verification flow: `email_verified`, `email_verify_token`, `email_verify_expires`
- Account lockout: `failed_login_attempts`, `locked_until` with 5-attempt threshold
- Rate limiting with `rate_limit` table
- Feature flags with SHA256 deterministic bucketing (`feature_flag` table)

### Security
- Security audit log (`security_audit_log` table) for auth events
- CSP headers, HSTS, X-Content-Type-Options, X-Frame-Options
- JWT refresh token hashing (plaintext never stored)

---

## [2.7.0] - 2026-02-22

### Added
- Client-side error tracking (`client_error_log` table)
- Server crash log (`crash_log` table) with automatic capture middleware
- Client event analytics (`client_event` table) for engagement tracking
- Grade appeal system (`grade_appeal` table) for disputed drill grades
- Push notification support via Capacitor plugin (`push_token` table)
- Invite code system for controlled access

---

## [2.6.0] - 2026-02-20

### Added
- Speaker calibration for tone grading (`speaker_calibration` table)
- Per-item tone accuracy tracking (`tone_attempts`, `tone_correct` on progress)
- Stable mastery tracking (`stable_since_date`, `successes_while_stable`)
- Spacing verification (`distinct_review_days` on progress)
- Response time tracking (`avg_response_ms` on progress)

### Changed
- Half-life retention model replaces simple interval-based scheduling
- Progress table gains `half_life_days`, `difficulty`, `last_p_recall` fields

---

## [2.5.0] - 2026-02-18

### Added
- Graded reader with web interface (`#reading` section)
- Media shelf with recommendation engine (`#media` section)
- Extensive listening with browser TTS (`#listening` section)
- Vocab encounter logging (`vocab_encounter` table) for cleanup loop
- `./run encounters` CLI command
- 13 new API endpoints for reading, media, listening, and encounters
- Scheduler boosts looked-up words in SRS queue

---

## [2.4.0] - 2026-02-16

### Added
- Grammar drill module with 26 grammar points seeded
- `grammar_point`, `grammar_progress`, `content_grammar` tables
- 14 language skills with `skill` and `content_skill` tables
- Construction tracking (`construction`, `content_construction` tables)
- Grammar-aware drill selection

---

## [2.3.0] - 2026-02-14

### Added
- Web interface (Flask + WebSocket via flask-sock)
- "Civic Sanctuary" design system: warm stone + teal + terracotta palette
- Cormorant Garamond headings, Source Sans 3 body, Noto Serif SC hanzi
- Dark mode support via `prefers-color-scheme` media query
- Web Audio API sounds for session start/complete
- Dashboard with Read/Watch/Listen buttons
- Streak counter and momentum indicator (non-anxious)

### Changed
- `./run app` launches web UI on port 5173
- Bridge module (`bridge.py`) connects Flask templates to CSS variable system

---

## [2.2.0] - 2026-02-13

### Added
- Speaking drill with macOS TTS audio playback
- Tone grading module (`tone_grading.py`)
- Audio recording support (`audio_recording` table)
- Dialogue scenarios with branching conversation trees (8 scenarios seeded)
- Probe log for comprehension checks (`probe_log` table)

---

## [2.1.0] - 2026-02-12

### Added
- Context notes for all 299 seed items (`context_note` field on content_item)
- 134 auto-tagged content items with content lens categories
- Register and pragmatic drill types
- Interleaving enforcement in drill selection
- HSK 7-9 content support
- Adaptive day profiles for session scheduling
- Focus command (`./run focus`)

---

## [2.0.0] - 2026-02-11

### Added
- Complete V2 rewrite of the learning system
- FSRS-inspired half-life regression SRS scheduling
- 12 drill types (hanzi_to_english, english_to_hanzi, hanzi_to_pinyin, listening, tone_production, ime_typing, fill_blank, sentence_order, register_choice, cloze_grammar, context_match, dialogue_response)
- 299 seed items across HSK 1-3
- Multi-user support with JWT authentication
- Diagnostics and forecasting commands
- Self-improvement log (`improvement_log` table)
- Session metrics tracking (`session_metrics` table)
- `./run` launcher with `./run menu` interactive menu
- 29 CLI commands

### Changed
- Schema upgraded from V1 to V13 (16 tables)
- All scoring and scheduling is deterministic (zero LLM tokens at runtime)

### Removed
- V1 simple flashcard system
- SM-2 scheduling (replaced by half-life regression)

---

## [1.0.0] - 2025-10

### Added
- Initial release: CLI-based Mandarin flashcard system
- SM-2 spaced repetition scheduling
- Basic vocabulary items (HSK 1)
- SQLite database with WAL mode
- Simple drill types (hanzi-to-english, english-to-hanzi)
- Session logging
- Progress tracking

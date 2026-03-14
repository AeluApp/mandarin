# Value Stream Map — Aelu Core Learning Loop

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Value Stream:** User opens app to session complete

---

## 1. Current State Map

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  LOGIN   │───▶│ DASHBOARD│───▶│ SESSION  │───▶│  DRILL   │───▶│  GRADE   │───▶│  SRS     │───▶│ SESSION  │
│          │    │  RENDER  │    │  PLAN    │    │  RENDER  │    │  +ERROR  │    │  UPDATE  │    │ COMPLETE │
│          │    │          │    │          │    │  +ANSWER │    │  CLASS   │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
   PT: 50ms       PT: 200ms      PT: 150ms      PT: varies     PT: 5ms        PT: 20ms        PT: 100ms
   WT: 0-3s       WT: 0ms        WT: 0ms        WT: 5-60s      WT: 0ms        WT: 0ms         WT: 0ms
   VA: yes        VA: partial    VA: yes        VA: yes        VA: yes        VA: yes         VA: partial

                                                ◄──── repeats 10-20 times ────►
```

**Legend:**
- PT = Processing Time (system computation)
- WT = Wait Time (user waits or system waits for user)
- VA = Value-Add from learner's perspective

---

## 2. Step Detail

### Step 1: Login / Auth
| Metric | Value |
|--------|-------|
| Processing time | ~50ms (JWT validation, session lookup) |
| Wait time | 0-3s (network round-trip, page load, TLS handshake) |
| Value-add? | No (necessary but not learning) |
| Systems | `jwt_auth.py`, `auth_routes.py`, `middleware.py` |
| DB reads | `user`, `learner_profile` (2 queries) |
| DB writes | `user.last_login_at` (1 UPDATE) |

**Non-value-add components:**
- TLS handshake (~100ms first visit, 0ms with session reuse)
- Cookie/token validation
- MFA challenge if enabled (~10s user time)

### Step 2: Dashboard Render
| Metric | Value |
|--------|-------|
| Processing time | ~200ms (streak calculation, mastery summary, recent sessions) |
| Wait time | 0ms (rendered server-side via Jinja2) |
| Value-add? | Partial (progress visibility is valuable, but user wants to drill, not look at dashboards) |
| Systems | `routes.py` (dashboard route), `metrics_report.py` |
| DB reads | `session_log`, `progress`, `review_event`, `error_focus` (4-6 queries) |
| DB writes | None |

**Non-value-add components:**
- CSS/JS/font loading (~100-300ms first visit, cached after)
- Dashboard metrics that user skips past without reading

### Step 3: Session Planning
| Metric | Value |
|--------|-------|
| Processing time | ~150ms (scheduler builds item queue) |
| Wait time | 0ms (computed on session start click) |
| Value-add? | Yes (intelligent item selection is core value proposition) |
| Systems | `scheduler.py` — full planning pipeline |
| DB reads | `progress`, `error_focus`, `error_log`, `review_event`, `session_log`, `learner_profile`, `content_item`, `feature_flag` (8-12 queries) |
| DB writes | `session_log` INSERT (1 write) |

**Planning pipeline (all in ~150ms):**
1. Compute day profile (adaptive or default)
2. Build review queue (items due for review, FSRS-ordered)
3. Compute error focus boost (error_focus items get priority)
4. Apply new item budget (mastery-gated)
5. Apply interleaving constraints (no same-type back-to-back)
6. Apply modality balance (ensure mix of reading/listening/production)
7. Select mapping groups (related items clustered)
8. Truncate to session length (adaptive or default, typically 10-20 items)

### Step 4: Drill Render + User Answer
| Metric | Value |
|--------|-------|
| Processing time | ~50ms per drill (template render + distractor generation for MC) |
| Wait time | 5-60s per drill (user thinking/answering) |
| Value-add? | Yes (this is the core learning activity) |
| Systems | `drills/dispatch.py`, specific drill runner |
| DB reads | 1-3 queries per drill (distractors for MC, context for advanced drills) |
| DB writes | None (grading is separate step) |

**TTS latency (when audio enabled):**
- Browser Web Speech API: ~200-500ms to begin speaking
- This is client-side, no server cost
- Non-value-add wait, but acceptable for learning flow

### Step 5: Grading + Error Classification
| Metric | Value |
|--------|-------|
| Processing time | ~5ms (deterministic string comparison) |
| Wait time | 0ms |
| Value-add? | Yes (accurate feedback is core value) |
| Systems | `drills/base.py` (`classify_error_cause`, `cause_to_error_type`), per-drill grading |
| DB reads | None |
| DB writes | None (writes happen in step 6) |

### Step 6: SRS Update
| Metric | Value |
|--------|-------|
| Processing time | ~20ms (progress update + review_event INSERT + error_log INSERT if wrong) |
| Wait time | 0ms |
| Value-add? | Yes (SRS state drives future session quality) |
| Systems | `runner.py`, `db/session.py`, `retention.py` |
| DB reads | `progress` (1 read for current state) |
| DB writes | `progress` UPDATE, `review_event` INSERT, `error_log` INSERT (if wrong), `error_focus` UPSERT (if wrong) — 2-4 writes per drill |

### Step 7: Session Complete
| Metric | Value |
|--------|-------|
| Processing time | ~100ms (session summary computation, streak update) |
| Wait time | 0ms |
| Value-add? | Partial (summary is useful feedback, but user is done learning) |
| Systems | `runner.py`, `metrics_report.py`, `milestones.py` |
| DB reads | `review_event` for this session, `session_log` history |
| DB writes | `session_log` UPDATE (ended_at, items_completed, etc.), `session_metrics` INSERT |

---

## 3. Timing Summary

### Per-Session Totals (15-item session)

| Category | Time | % of Total |
|----------|------|-----------|
| User thinking/answering (15 drills x ~15s avg) | ~225s | 80% |
| TTS playback (if audio enabled, ~8 audio drills) | ~3s | 1% |
| System processing (all steps) | ~1.5s | 0.5% |
| Page load / navigation | ~2s | 0.7% |
| Session planning | ~0.15s | 0.05% |
| **Total value-add time** | **~230s** | **81%** |
| **Total non-value-add time** | **~5s** | **2%** |
| **Total user wait (thinking)** | **~225s** | **80%** |

### DB Operations Per Session
| Operation | Count |
|-----------|-------|
| SELECTs | ~30-50 |
| INSERTs | ~20-35 |
| UPDATEs | ~15-20 |
| Total writes | ~35-55 |

SQLite WAL mode handles this comfortably. Write serialization is not a bottleneck at current scale.

---

## 4. Value-Add vs. Non-Value-Add Classification

| Step | Classification | Rationale |
|------|---------------|-----------|
| Login/Auth | **NVA — Necessary** | Required for security but zero learning value |
| Dashboard render | **NVA — Partial** | Progress visibility has some value but most users skip to "Start Session" |
| Session planning | **VA** | Intelligent item selection IS the product |
| Drill render | **VA** | Presenting the learning challenge |
| User thinking/answering | **VA** | Active recall — the core learning act |
| TTS playback | **VA** | Audio input for listening drills |
| Grading | **VA** | Accurate feedback drives learning |
| Error classification | **VA** | Enables error-focused future sessions |
| SRS update | **VA** | Drives long-term retention optimization |
| Session summary | **NVA — Partial** | Some users value it, others close immediately |
| Page navigation | **NVA — Waste** | Every extra click is friction |

**VA ratio: ~85% of system processing time is value-add.** The primary "waste" is login/auth and navigation overhead, which are architecturally necessary.

---

## 5. Eight Wastes (Muda) Analysis

### 5.1 Transport (Unnecessary Data Movement)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Full page reloads between drills | Web UI reloads the entire page for each drill in non-SPA mode | ~200ms per drill transition | **Partially mitigated** — web bridge uses SPA-like transitions |
| Redundant DB queries | Dashboard and session planning both query `progress` table | ~20ms redundant | **Open** — could cache profile in session |
| Audio file round-trips | TTS is client-side (no transport waste) | N/A | **Eliminated** |

### 5.2 Inventory (Pre-computed Work Never Used)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Pre-planned drills not shown | Session plans 15 items, user quits at item 8 — remaining 7 were planned for nothing | Planning time for ~7 items wasted | **Accepted** — planning is cheap (~150ms total), and early-exit is user choice |
| Grammar_extra_*.py files | 10 grammar_extra files with pre-computed drill data. Are all entries actually used? | Code bloat, maintenance burden | **Open** — audit needed |
| Unused feature_flag rows | Flags created for features that were never rolled out | Negligible (tiny table) | **Trivial** |

### 5.3 Motion (Unnecessary User Actions)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Dashboard → Start Session click | User must navigate through dashboard to begin drilling | 2-5s of non-learning time | **Open** — could offer "quick start" that skips dashboard |
| Post-session summary dismissal | User must acknowledge summary before returning to dashboard | 1-2s | **Accepted** — summary provides closure |
| Login on every visit | JWT expiry requires re-authentication | 10-30s periodically | **Mitigated** — refresh tokens extend session |

### 5.4 Waiting

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| TTS latency | Browser Web Speech API takes 200-500ms to begin speaking | Noticeable pause before audio drills | **Accepted** — client-side, no server cost, within tolerance |
| First page load | Cold start on Fly.io (machine spin-up from stopped state) | 3-8s if machine was stopped | **Mitigated** — `min_machines_running = 1` keeps one machine warm |
| SQLite write lock contention | Under concurrent writes, WAL serializes | < 10ms at current scale | **Monitored** — will matter at 1,000+ concurrent users |

### 5.5 Overproduction (Building Before Need)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Classroom system | `classroom`, `classroom_student` tables, `lti_routes.py`, `lti_platform` — no teacher users exist | Dev time spent, code to maintain, schema complexity | **Acknowledged waste** — stop investing until first teacher prospect |
| Affiliate system | `affiliate_partner`, `referral_tracking`, `affiliate_commission`, `discount_code` — no affiliates yet | Same as above | **Acknowledged waste** |
| Flutter app | `flutter_app/` directory with prototype — not in production | Dead code | **Open** — consider removing |
| Desktop app | `desktop/` directory | Dead code if unused | **Open** — audit needed |
| 10 grammar_extra files | Pre-computed grammar drill data across HSK levels | May contain unused entries | **Open** — audit needed |

### 5.6 Over-processing (More Than Needed)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| 51 DB tables for < 10 users | Schema complexity far exceeds current user base | Maintenance burden, migration complexity, cognitive load | **Acknowledged** — but tables are individually justified; the issue is building them all pre-PMF |
| Security audit log for < 10 users | Enterprise-grade security logging before enterprise users | Negligible runtime cost, some dev time | **Accepted** — security is non-negotiable regardless of scale |
| GDPR data deletion for < 10 users | Full Article 17 compliance before significant user base | Dev time for `data_deletion_request` table + routes | **Accepted** — legal requirement regardless of scale |
| 6-stage mastery model | seen → shaky → fair → solid → strong → mastered may be more granularity than needed | Complexity in progress tracking | **Under review** — may simplify to 3-4 stages |

### 5.7 Defects

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Multiple valid answers not accepted | Correct translations graded wrong (false negatives) | User frustration, inaccurate progress data | **Open** — grade_appeal system captures these |
| Schema drift | schema.sql and actual DB can diverge during migrations | Migration failures, data inconsistency | **Fixed** — migration system reconciles |
| Flaky tests | Scheduler race condition caused intermittent test failures | CI unreliability | **Fixed** — scheduler_lock.py resolved |
| CSP breaks on localhost | `upgrade-insecure-requests` broke all sub-resource loading on HTTP | All CSS/JS/fonts failed to load | **Fixed** — `IS_PRODUCTION` guard |

### 5.8 Skills (Underutilized Talent)

| Waste | Description | Impact | Status |
|-------|-----------|--------|--------|
| Solo dev doing marketing/ops/product/engineering | Jason is a skilled engineer doing marketing tasks, ops tasks, content creation, and customer support — not all of these are his highest-value activity | Opportunity cost: time spent on low-leverage tasks | **Structural** — inherent to solo founding |
| No user research training | VoC interviews conducted without formal training in qualitative research | Lower quality insights, possible interviewer bias | **Mitigable** — follow structured VoC protocol |
| No design system | UI decisions made ad-hoc without formal design principles | Inconsistent UX, rework | **Partially mitigated** — Civic Sanctuary aesthetic documented |

---

## 6. Future State Targets

| Waste Category | Current State | Future State Target |
|----------------|--------------|-------------------|
| Transport | ~200ms per drill transition | < 50ms with full SPA |
| Inventory | 10 grammar_extra files unaudited | Audit all; remove unused |
| Motion | Dashboard required before drilling | Quick-start option bypasses dashboard |
| Waiting | 200-500ms TTS latency | Accept (client-side, no cost) |
| Overproduction | Classroom/affiliate built pre-PMF | Freeze; no new investment until demand |
| Over-processing | 51 tables | Accept if each is justified; no new tables without usage evidence |
| Defects | Multi-answer grading gap | Implement alternative answer support |
| Skills | Solo dev doing everything | Accept until revenue supports first hire |

---

## 7. Lead Time Calculation

**Total lead time** (user opens app to session complete):
- Login: ~3s (first visit) / ~0.5s (returning)
- Dashboard: ~0.5s
- Session planning: ~0.15s
- Drilling (15 items): ~4 minutes
- Session complete: ~0.1s
- **Total: ~4.5 minutes** (of which ~4 minutes is value-add drilling)

**Process efficiency ratio:** ~90% (4 min value-add / 4.5 min total)

This is a high efficiency ratio because the product is fundamentally a tight loop: plan → drill → grade → repeat. The main source of "waste" time is authentication and navigation, which are both small relative to drill time.

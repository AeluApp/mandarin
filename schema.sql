-- Mandarin Learning System — Database Schema (V29)
-- SQLite, local-first, multi-user

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ────────────────────────────────
-- USERS
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    subscription_tier TEXT NOT NULL DEFAULT 'free'
        CHECK (subscription_tier IN ('free', 'paid', 'admin')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_admin INTEGER NOT NULL DEFAULT 0,
    subscription_status TEXT DEFAULT 'active',
    invited_by TEXT,
    refresh_token_hash TEXT,
    refresh_token_expires TEXT,
    reset_token_hash TEXT,
    reset_token_expires TEXT,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    first_session_at TEXT,
    activation_at TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    totp_secret TEXT,
    totp_enabled INTEGER NOT NULL DEFAULT 0,
    totp_backup_codes TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    email_verify_token TEXT,
    email_verify_expires TEXT,
    marketing_opt_out INTEGER NOT NULL DEFAULT 0,
    anonymous_mode INTEGER NOT NULL DEFAULT 0,
    role TEXT NOT NULL DEFAULT 'student',
    push_token TEXT,
    streak_freezes_available INTEGER DEFAULT 0
);

-- ────────────────────────────────
-- LEARNER PROFILE
-- ────────────────────────────────
-- One profile per user.
CREATE TABLE IF NOT EXISTS learner_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Estimated levels per modality (HSK band, e.g. 1.0 - 9.0)
    level_reading REAL NOT NULL DEFAULT 1.0,
    level_listening REAL NOT NULL DEFAULT 1.0,
    level_speaking REAL NOT NULL DEFAULT 1.0,
    level_ime REAL NOT NULL DEFAULT 1.0,
    level_chunks REAL NOT NULL DEFAULT 1.0,

    -- Confidence in estimates (0.0 = no data, 1.0 = high confidence)
    confidence_reading REAL NOT NULL DEFAULT 0.0,
    confidence_listening REAL NOT NULL DEFAULT 0.0,
    confidence_speaking REAL NOT NULL DEFAULT 0.0,
    confidence_ime REAL NOT NULL DEFAULT 0.0,
    confidence_chunks REAL NOT NULL DEFAULT 0.0,

    -- Session cadence tracking
    target_sessions_per_week INTEGER NOT NULL DEFAULT 4,
    preferred_session_length INTEGER NOT NULL DEFAULT 12,
    total_sessions INTEGER NOT NULL DEFAULT 0,
    last_session_date TEXT,

    -- Engagement scores per content lens (0.0 - 1.0, decaying)
    lens_quiet_observation REAL NOT NULL DEFAULT 0.7,
    lens_institutions REAL NOT NULL DEFAULT 0.7,
    lens_urban_texture REAL NOT NULL DEFAULT 0.7,
    lens_humane_mystery REAL NOT NULL DEFAULT 0.7,
    lens_identity REAL NOT NULL DEFAULT 0.7,
    lens_comedy REAL NOT NULL DEFAULT 0.7,
    lens_food REAL NOT NULL DEFAULT 0.5,
    lens_travel REAL NOT NULL DEFAULT 0.5,
    lens_explainers REAL NOT NULL DEFAULT 0.5,
    lens_wit REAL NOT NULL DEFAULT 0.7,
    lens_ensemble_comedy REAL NOT NULL DEFAULT 0.7,
    lens_sharp_observation REAL NOT NULL DEFAULT 0.7,
    lens_satire REAL NOT NULL DEFAULT 0.7,
    lens_moral_texture REAL NOT NULL DEFAULT 0.7,

    -- Audio playback (macOS TTS) — 1 = on by default
    audio_enabled INTEGER NOT NULL DEFAULT 1,

    -- Personalization
    preferred_domains TEXT DEFAULT '',

    -- Behavioral commitment (V10+)
    next_session_intention TEXT,
    intention_set_at TEXT,
    minimal_days TEXT DEFAULT '',

    -- Display preferences (V29+)
    reading_show_pinyin INTEGER NOT NULL DEFAULT 0,
    reading_show_translation INTEGER NOT NULL DEFAULT 0,

    -- Notification & voice preferences
    streak_reminders INTEGER NOT NULL DEFAULT 1,
    preferred_voice TEXT,

    -- SRS tuning (V97+)
    target_retention_rate REAL DEFAULT 0.85,

    UNIQUE(user_id),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

-- ────────────────────────────────
-- CONTENT LIBRARY
-- ────────────────────────────────
-- Every learnable item: vocab, sentence, phrase, chunk. Shared across users.
CREATE TABLE IF NOT EXISTS content_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Core content
    hanzi TEXT NOT NULL,
    pinyin TEXT NOT NULL,
    english TEXT NOT NULL,

    -- Classification
    item_type TEXT NOT NULL DEFAULT 'vocab'
        CHECK (item_type IN ('vocab', 'sentence', 'phrase', 'chunk', 'grammar')),
    hsk_level INTEGER,  -- 1-9, NULL if unknown
    register TEXT DEFAULT 'neutral'
        CHECK (register IN ('casual', 'neutral', 'professional', 'mixed')),

    -- Content lens tagging (which affinity lens this belongs to)
    content_lens TEXT,

    -- Source tracking
    source TEXT,            -- e.g. 'quizlet_import', 'subtitle:movie.srt', 'youtube:URL'
    source_context TEXT,    -- surrounding sentence or scene context

    -- Modality suitability flags
    suitable_for_listening INTEGER NOT NULL DEFAULT 1,
    suitable_for_ime INTEGER NOT NULL DEFAULT 1,
    suitable_for_speaking INTEGER NOT NULL DEFAULT 1,
    suitable_for_reading INTEGER NOT NULL DEFAULT 1,

    -- Difficulty estimate (0.0 = trivial, 1.0 = very hard)
    difficulty REAL NOT NULL DEFAULT 0.5,

    -- Tags (JSON array for flexible categorization)
    tags TEXT DEFAULT '[]',

    -- Item lifecycle: raw → enriched → drill_ready
    status TEXT NOT NULL DEFAULT 'drill_ready'
        CHECK (status IN ('raw', 'enriched', 'drill_ready')),

    -- Content review gate: AI-generated items start as 'pending_review'
    -- and must be approved before being served to users.
    -- Manually seeded items default to 'approved'.
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('approved', 'pending_review', 'rejected')),

    -- Scaling ladder: word → sentence → paragraph → article
    scale_level TEXT NOT NULL DEFAULT 'word'
        CHECK (scale_level IN ('word', 'sentence', 'paragraph', 'article')),

    -- Audio metadata (V1+)
    audio_available INTEGER NOT NULL DEFAULT 0,
    audio_file_path TEXT,
    clip_start_ms INTEGER,
    clip_end_ms INTEGER,

    -- Context note (V2+)
    context_note TEXT,

    -- Image association (for image_association drill)
    image_url TEXT,

    -- Example sentences (AI-generated drill items)
    example_sentence_hanzi TEXT,
    example_sentence_pinyin TEXT,
    example_sentence_english TEXT,

    -- Staleness tracking
    times_shown INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    is_mined_out INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_content_type ON content_item(item_type);
CREATE INDEX IF NOT EXISTS idx_content_hsk ON content_item(hsk_level);
CREATE INDEX IF NOT EXISTS idx_content_lens ON content_item(content_lens);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_item(status);
CREATE INDEX IF NOT EXISTS idx_content_review_status ON content_item(review_status);

-- ────────────────────────────────
-- SRS / PROGRESS TRACKING
-- ────────────────────────────────
-- Per-user, per-item, per-modality progress.
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    content_item_id INTEGER NOT NULL,
    modality TEXT NOT NULL
        CHECK (modality IN ('reading', 'listening', 'speaking', 'ime')),

    -- SRS fields
    ease_factor REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0.0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    next_review_date TEXT,  -- ISO date, NULL = never reviewed
    last_review_date TEXT,

    -- Performance
    total_attempts INTEGER NOT NULL DEFAULT 0,
    total_correct INTEGER NOT NULL DEFAULT 0,
    streak_correct INTEGER NOT NULL DEFAULT 0,
    streak_incorrect INTEGER NOT NULL DEFAULT 0,

    -- Intuition tracking
    intuition_attempts INTEGER NOT NULL DEFAULT 0,
    intuition_correct INTEGER NOT NULL DEFAULT 0,

    -- Per-direction tracking
    drill_direction TEXT,

    -- Mastery model (6-stage)
    mastery_stage TEXT NOT NULL DEFAULT 'seen',
    historically_weak INTEGER NOT NULL DEFAULT 0,
    weak_cycle_count INTEGER NOT NULL DEFAULT 0,

    -- Response time tracking (V4+)
    avg_response_ms REAL,
    drill_types_seen TEXT NOT NULL DEFAULT '',

    -- Spacing verification (V5+)
    distinct_review_days INTEGER NOT NULL DEFAULT 0,

    -- Half-life retention model (V6+)
    half_life_days REAL DEFAULT 1.0,
    difficulty REAL DEFAULT 0.5,
    last_p_recall REAL,

    -- Stable tracking (V7+)
    stable_since_date TEXT,
    successes_while_stable INTEGER NOT NULL DEFAULT 0,

    -- Per-item tone accuracy (V8+)
    tone_attempts INTEGER NOT NULL DEFAULT 0,
    tone_correct INTEGER NOT NULL DEFAULT 0,

    -- Suspend/bury (V97+)
    suspended_until TEXT,  -- ISO date; NULL = not suspended, '9999-12-31' = indefinite

    UNIQUE(user_id, content_item_id, modality),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_progress_review ON progress(next_review_date);
CREATE INDEX IF NOT EXISTS idx_progress_modality ON progress(modality);
CREATE INDEX IF NOT EXISTS idx_progress_direction ON progress(content_item_id, modality, drill_direction);
CREATE INDEX IF NOT EXISTS idx_progress_item ON progress(content_item_id);
CREATE INDEX IF NOT EXISTS idx_progress_mastery ON progress(mastery_stage);
CREATE INDEX IF NOT EXISTS idx_progress_user_item ON progress(user_id, content_item_id, modality);
CREATE INDEX IF NOT EXISTS idx_progress_user_modality_due ON progress(user_id, modality, next_review_date);

-- ────────────────────────────────
-- SESSION LOG
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS session_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    duration_seconds INTEGER,

    session_type TEXT NOT NULL DEFAULT 'standard'
        CHECK (session_type IN ('standard', 'minimal', 'diagnostic', 'catchup', 'calibrate', 'speaking')),

    items_planned INTEGER NOT NULL DEFAULT 0,
    items_completed INTEGER NOT NULL DEFAULT 0,
    items_correct INTEGER NOT NULL DEFAULT 0,
    modality_counts TEXT DEFAULT '{}',

    early_exit INTEGER NOT NULL DEFAULT 0,
    boredom_flags INTEGER NOT NULL DEFAULT 0,
    days_since_last_session INTEGER,
    session_started_hour INTEGER,
    session_day_of_week INTEGER,
    session_outcome TEXT DEFAULT 'started',
    mapping_groups_used TEXT,
    plan_snapshot TEXT,
    last_activity_at TEXT,
    client_platform TEXT DEFAULT 'web',
    experiment_variant TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_started ON session_log(started_at);
CREATE INDEX IF NOT EXISTS idx_session_log_user ON session_log(user_id, started_at);

-- ────────────────────────────────
-- REVIEW EVENT LOG (Doctrine §12: per-review instrumentation)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS review_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    session_id INTEGER,
    content_item_id INTEGER NOT NULL,
    modality TEXT NOT NULL,
    drill_type TEXT,
    correct INTEGER NOT NULL,
    confidence TEXT DEFAULT 'full',
    response_ms INTEGER,
    error_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    FOREIGN KEY (session_id) REFERENCES session_log(id),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_review_event_user ON review_event(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_review_event_item ON review_event(content_item_id);

-- ────────────────────────────────
-- ERROR LOG
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    session_id INTEGER,
    content_item_id INTEGER NOT NULL,
    modality TEXT NOT NULL,

    error_type TEXT NOT NULL DEFAULT 'other'
        CHECK (error_type IN (
            'tone', 'segment', 'ime_confusable', 'grammar', 'vocab', 'other',
            'register_mismatch', 'particle_misuse', 'function_word_omission',
            'temporal_sequencing', 'measure_word', 'politeness_softening',
            'reference_tracking', 'pragmatics_mismatch', 'number'
        )),

    user_answer TEXT,
    expected_answer TEXT,
    drill_type TEXT,
    notes TEXT,
    tone_user INTEGER,
    tone_expected INTEGER,

    FOREIGN KEY (session_id) REFERENCES session_log(id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id)
);

CREATE INDEX IF NOT EXISTS idx_error_type ON error_log(error_type);
CREATE INDEX IF NOT EXISTS idx_error_session ON error_log(session_id);
CREATE INDEX IF NOT EXISTS idx_error_item ON error_log(content_item_id);
CREATE INDEX IF NOT EXISTS idx_error_log_user_session ON error_log(user_id, session_id);

-- ────────────────────────────────
-- ERROR FOCUS
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS error_focus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    content_item_id INTEGER NOT NULL,
    error_type TEXT NOT NULL,
    first_flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_error_at TEXT NOT NULL DEFAULT (datetime('now')),
    error_count INTEGER NOT NULL DEFAULT 1,
    consecutive_correct INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT,
    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    UNIQUE(user_id, content_item_id, error_type)
);

CREATE INDEX IF NOT EXISTS idx_error_focus_user ON error_focus(user_id, content_item_id);

-- ────────────────────────────────
-- GRAMMAR POINTS (shared)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS grammar_point (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    name_zh TEXT,
    hsk_level INTEGER NOT NULL DEFAULT 1,
    category TEXT NOT NULL DEFAULT 'structure'
        CHECK (category IN ('structure', 'particle', 'measure_word',
                            'complement', 'aspect', 'comparison', 'connector', 'other')),
    description TEXT,
    examples_json TEXT DEFAULT '[]',
    difficulty REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_grammar_hsk ON grammar_point(hsk_level);

-- ────────────────────────────────
-- SKILLS (shared)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS skill (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'pragmatic'
        CHECK (category IN ('pragmatic', 'register', 'discourse', 'cultural', 'phonetic')),
    description TEXT,
    hsk_level INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_skill_category ON skill(category);

-- ────────────────────────────────
-- CONTENT ↔ GRAMMAR / SKILL LINKS (shared)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS content_grammar (
    content_item_id INTEGER NOT NULL,
    grammar_point_id INTEGER NOT NULL,
    PRIMARY KEY (content_item_id, grammar_point_id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id)
);

CREATE TABLE IF NOT EXISTS content_skill (
    content_item_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    PRIMARY KEY (content_item_id, skill_id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    FOREIGN KEY (skill_id) REFERENCES skill(id)
);

-- ────────────────────────────────
-- CONSTRUCTIONS (shared, V4+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS construction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    pattern_zh TEXT,
    description TEXT,
    hsk_level INTEGER NOT NULL DEFAULT 1,
    category TEXT NOT NULL DEFAULT 'syntax',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_construction (
    content_item_id INTEGER NOT NULL,
    construction_id INTEGER NOT NULL,
    PRIMARY KEY (content_item_id, construction_id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id),
    FOREIGN KEY (construction_id) REFERENCES construction(id)
);

-- ────────────────────────────────
-- DIALOGUE SCENARIOS (shared, V1+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS dialogue_scenario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    title_zh TEXT,
    hsk_level INTEGER NOT NULL DEFAULT 1,
    register TEXT NOT NULL DEFAULT 'neutral',
    scenario_type TEXT NOT NULL DEFAULT 'dialogue',
    tree_json TEXT NOT NULL,
    difficulty REAL NOT NULL DEFAULT 0.5,
    times_presented INTEGER NOT NULL DEFAULT 0,
    avg_score REAL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- AUDIO RECORDING (V2+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS audio_recording (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    session_id INTEGER,
    content_item_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    tone_scores_json TEXT,
    overall_score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES session_log(id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id)
);

-- ────────────────────────────────
-- PROBE LOG (V8+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS probe_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    content_item_id INTEGER,
    scenario_id INTEGER,
    probe_type TEXT NOT NULL DEFAULT 'comprehension',
    correct INTEGER NOT NULL DEFAULT 0,
    user_answer TEXT,
    expected_answer TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scenario_id) REFERENCES dialogue_scenario(id)
);

CREATE INDEX IF NOT EXISTS idx_probe_scenario ON probe_log(scenario_id);

-- ────────────────────────────────
-- SESSION METRICS (V6+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS session_metrics (
    session_id INTEGER PRIMARY KEY REFERENCES session_log(id),
    user_id INTEGER DEFAULT 1,
    recall_above_threshold INTEGER DEFAULT 0,
    recall_below_threshold INTEGER DEFAULT 0,
    avg_recall REAL,
    avg_difficulty REAL,
    items_strengthened INTEGER DEFAULT 0,
    items_weakened INTEGER DEFAULT 0,
    transfer_events INTEGER DEFAULT 0,
    computed_at TEXT
);

-- ────────────────────────────────
-- VOCAB ENCOUNTER (V13+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS vocab_encounter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    content_item_id INTEGER,
    hanzi TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    looked_up INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id)
);

CREATE INDEX IF NOT EXISTS idx_encounter_hanzi ON vocab_encounter(hanzi);
CREATE INDEX IF NOT EXISTS idx_encounter_source ON vocab_encounter(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_vocab_encounter_user ON vocab_encounter(user_id, hanzi);

-- ────────────────────────────────
-- PASSAGE-VOCAB MAP (V100+)
-- ────────────────────────────────
-- Pre-computed index: which content_item vocab words appear in each passage.
-- Built by scripts/build_passage_vocab_index.py via jieba segmentation.
CREATE TABLE IF NOT EXISTS passage_vocab_map (
    passage_id TEXT NOT NULL,
    content_item_id INTEGER NOT NULL,
    hanzi TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (passage_id, content_item_id),
    FOREIGN KEY (content_item_id) REFERENCES content_item(id)
);

CREATE INDEX IF NOT EXISTS idx_pvm_content_item ON passage_vocab_map(content_item_id);
CREATE INDEX IF NOT EXISTS idx_pvm_hanzi ON passage_vocab_map(hanzi);

-- ────────────────────────────────
-- GRAMMAR PROGRESS (V31+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS grammar_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    grammar_point_id INTEGER NOT NULL,
    studied_at TEXT NOT NULL DEFAULT (datetime('now')),
    drill_attempts INTEGER NOT NULL DEFAULT 0,
    drill_correct INTEGER NOT NULL DEFAULT 0,
    mastery_score REAL NOT NULL DEFAULT 0.0,
    UNIQUE(user_id, grammar_point_id),
    FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id)
);

-- ────────────────────────────────
-- READING PROGRESS (V32+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS reading_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    passage_id TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    words_looked_up INTEGER NOT NULL DEFAULT 0,
    questions_correct INTEGER NOT NULL DEFAULT 0,
    questions_total INTEGER NOT NULL DEFAULT 0,
    reading_time_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_reading_progress_user ON reading_progress(user_id, passage_id);

-- ────────────────────────────────
-- LISTENING PROGRESS (V35+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS listening_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    passage_id TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    comprehension_score REAL DEFAULT 0.0,
    questions_correct INTEGER DEFAULT 0,
    questions_total INTEGER DEFAULT 0,
    words_looked_up INTEGER DEFAULT 0,
    hsk_level INTEGER DEFAULT 1
);

-- ────────────────────────────────
-- SCHEDULER LOCK (V34+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduler_lock (
    name TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- ────────────────────────────────
-- USER FEEDBACK (auto-created)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rating INTEGER NOT NULL,
    comment TEXT DEFAULT '',
    feedback_type TEXT NOT NULL DEFAULT 'nps',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- SYSTEM SELF-IMPROVEMENT LOG
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS improvement_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    trigger_reason TEXT NOT NULL,
    observation TEXT NOT NULL,
    proposed_change TEXT,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'applied', 'rolled_back', 'rejected')),
    applied_at TEXT,
    rolled_back_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_improvement_log_user ON improvement_log(user_id);

-- ────────────────────────────────
-- SCRUM SPRINT
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS sprint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sprint_number INTEGER NOT NULL,
    goal TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    planned_items INTEGER,
    completed_items INTEGER,
    planned_points INTEGER,
    completed_points INTEGER,
    velocity REAL,
    accuracy_trend REAL,
    status TEXT DEFAULT 'active',
    retrospective TEXT,
    review_notes TEXT,
    retro_went_well TEXT,
    retro_improve TEXT,
    retro_action_items TEXT,
    UNIQUE(user_id, sprint_number)
);

CREATE INDEX IF NOT EXISTS idx_sprint_user_status ON sprint(user_id, status);

-- ────────────────────────────────
-- STANDALONE RETROSPECTIVE
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS retrospective (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT,
    went_well TEXT,
    improve TEXT,
    action_items TEXT,
    sprint_id INTEGER REFERENCES sprint(id),
    created_at TEXT DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- ROOT CAUSE ANALYSIS (5 Whys + Ishikawa)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS root_cause_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_item_id INTEGER REFERENCES work_item(id),
    improvement_id INTEGER,
    why_1 TEXT,
    why_2 TEXT,
    why_3 TEXT,
    why_4 TEXT,
    why_5 TEXT,
    root_cause TEXT,
    category TEXT CHECK (category IN ('method', 'measurement', 'material', 'machine', 'man', 'environment')),
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rca_work_item ON root_cause_analysis(work_item_id);
CREATE INDEX IF NOT EXISTS idx_rca_category ON root_cause_analysis(category);

-- ────────────────────────────────
-- RISK REVIEW (Spiral burndown)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_item_id INTEGER REFERENCES risk_item(id),
    previous_score REAL,
    new_score REAL,
    notes TEXT,
    reviewed_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_risk_review_item ON risk_review(risk_item_id);
CREATE INDEX IF NOT EXISTS idx_risk_review_date ON risk_review(reviewed_at);

-- ────────────────────────────────
-- SPIRAL RISK EVENTS
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    risk_category TEXT NOT NULL,
    risk_type TEXT NOT NULL,
    severity TEXT DEFAULT 'medium',
    description TEXT NOT NULL,
    source TEXT,
    data_json TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_risk_event_status ON risk_event(status);

-- ────────────────────────────────
-- MEDIA WATCH
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS media_watch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    media_id TEXT NOT NULL,
    title TEXT NOT NULL,
    hsk_level INTEGER NOT NULL DEFAULT 1,
    media_type TEXT NOT NULL,
    times_presented INTEGER NOT NULL DEFAULT 0,
    times_watched INTEGER NOT NULL DEFAULT 0,
    last_presented_at TEXT,
    last_watched_at TEXT,
    total_questions INTEGER NOT NULL DEFAULT 0,
    total_correct INTEGER NOT NULL DEFAULT 0,
    avg_score REAL,
    best_score REAL,
    skipped INTEGER NOT NULL DEFAULT 0,
    liked INTEGER,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, media_id)
);

CREATE INDEX IF NOT EXISTS idx_media_watch_hsk ON media_watch(hsk_level);
CREATE INDEX IF NOT EXISTS idx_media_watch_status ON media_watch(status);
CREATE INDEX IF NOT EXISTS idx_media_watch_user ON media_watch(user_id, media_id);

-- ────────────────────────────────
-- AFFILIATE SYSTEM (V14+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS affiliate_partner (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_code TEXT UNIQUE NOT NULL,
    partner_name TEXT NOT NULL,
    partner_email TEXT,
    commission_rate REAL NOT NULL DEFAULT 0.20,
    tier TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (tier IN ('standard', 'upgrade')),
    CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS referral_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id TEXT NOT NULL,
    partner_code TEXT NOT NULL,
    landing_page TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    cookie_set_at TEXT NOT NULL DEFAULT (datetime('now')),
    signed_up INTEGER NOT NULL DEFAULT 0,
    signup_at TEXT,
    converted_to_paid INTEGER NOT NULL DEFAULT 0,
    converted_at TEXT,
    FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code)
);

CREATE INDEX IF NOT EXISTS idx_referral_partner ON referral_tracking(partner_code);
CREATE INDEX IF NOT EXISTS idx_referral_visitor ON referral_tracking(visitor_id);

CREATE TABLE IF NOT EXISTS affiliate_commission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_code TEXT NOT NULL,
    referral_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    payment_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    confirmed_at TEXT,
    paid_out_at TEXT,
    CHECK (status IN ('pending', 'confirmed', 'paid', 'reversed')),
    FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code),
    FOREIGN KEY (referral_id) REFERENCES referral_tracking(id)
);

CREATE INDEX IF NOT EXISTS idx_commission_partner ON affiliate_commission(partner_code);
CREATE INDEX IF NOT EXISTS idx_commission_status ON affiliate_commission(status);

CREATE TABLE IF NOT EXISTS discount_code (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    partner_code TEXT,
    discount_percent INTEGER NOT NULL DEFAULT 20,
    valid_months INTEGER NOT NULL DEFAULT 3,
    max_uses INTEGER,
    current_uses INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (partner_code) REFERENCES affiliate_partner(partner_code)
);

CREATE TABLE IF NOT EXISTS lifecycle_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_event_type ON lifecycle_event(event_type);
CREATE INDEX IF NOT EXISTS idx_lifecycle_user ON lifecycle_event(user_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_created ON lifecycle_event(created_at);

-- ────────────────────────────────
-- SECURITY AUDIT LOG (CIS Control 8, NIST DE.AE, ISO A.8.15)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    user_id INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    details TEXT,
    severity TEXT NOT NULL DEFAULT 'INFO',
    FOREIGN KEY (user_id) REFERENCES user(id)
);
CREATE INDEX IF NOT EXISTS idx_security_audit_timestamp ON security_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_security_audit_user ON security_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_security_audit_event ON security_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_security_audit_severity ON security_audit_log(severity);

-- ────────────────────────────────
-- SECURITY SCANS (V41+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS security_scan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_type TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT,
    error_message TEXT,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS security_scan_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    file_path TEXT,
    line_number INTEGER,
    package_name TEXT,
    installed_version TEXT,
    fixed_version TEXT,
    FOREIGN KEY (scan_id) REFERENCES security_scan(id)
);

CREATE INDEX IF NOT EXISTS idx_scan_finding_scan ON security_scan_finding(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_finding_severity ON security_scan_finding(severity);

-- ────────────────────────────────
-- DATA DELETION REQUESTS (GDPR Article 17)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS data_deletion_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

-- ────────────────────────────────
-- SPEAKER CALIBRATION (V22+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS speaker_calibration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    f0_min REAL NOT NULL,
    f0_max REAL NOT NULL,
    f0_mean REAL NOT NULL,
    calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_speaker_calibration_user ON speaker_calibration(user_id, calibrated_at);

-- ────────────────────────────────
-- CRASH LOG (V24+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS crash_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    error_type TEXT NOT NULL,
    error_message TEXT,
    traceback TEXT,
    request_method TEXT,
    request_path TEXT,
    request_body TEXT,
    ip_address TEXT,
    user_agent TEXT,
    severity TEXT NOT NULL DEFAULT 'ERROR',
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_crash_log_ts ON crash_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_crash_log_user_ts ON crash_log(user_id, timestamp);

-- ────────────────────────────────
-- CLIENT ERROR LOG (V24+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS client_error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    error_type TEXT NOT NULL,
    error_message TEXT,
    source_file TEXT,
    line_number INTEGER,
    col_number INTEGER,
    stack_trace TEXT,
    page_url TEXT,
    user_agent TEXT,
    event_snapshot TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_client_error_ts ON client_error_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_client_error_user_ts ON client_error_log(user_id, timestamp);

-- ────────────────────────────────
-- CLIENT EVENTS (V27+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS client_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    install_id TEXT,
    event_id TEXT,
    category TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_client_event_ts ON client_event(created_at);
CREATE INDEX IF NOT EXISTS idx_client_event_user_cat ON client_event(user_id, category);

-- ────────────────────────────────
-- MFA CHALLENGE (V25+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS mfa_challenge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mfa_challenge_user_expires ON mfa_challenge(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_mfa_challenge_token ON mfa_challenge(token_hash);

-- ────────────────────────────────
-- GRADE APPEAL (V26+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS grade_appeal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id INTEGER,
    drill_number INTEGER,
    content_item_id INTEGER,
    user_answer TEXT,
    expected_answer TEXT,
    appeal_text TEXT,
    error_type TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

-- ────────────────────────────────
-- SCHEMA VERSION (migration tracker)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- INVITE CODES (V16+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS invite_code (
    code TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    used_by INTEGER REFERENCES user(id),
    used_at TEXT,
    max_uses INTEGER DEFAULT 1,
    use_count INTEGER DEFAULT 0,
    classroom_id INTEGER REFERENCES classroom(id),
    expires_at TEXT,
    created_by INTEGER REFERENCES user(id),
    label TEXT DEFAULT ''
);

-- ────────────────────────────────
-- PUSH NOTIFICATION TOKENS (V17+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS push_token (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    platform TEXT NOT NULL,
    token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_push_token_user_platform
    ON push_token(user_id, platform);

-- ────────────────────────────────
-- FEATURE FLAGS (V20+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS feature_flag (
    name TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    rollout_pct INTEGER DEFAULT 100,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- RATE LIMITER (V20+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS rate_limit (
    key TEXT NOT NULL,
    hits INTEGER DEFAULT 1,
    window_start TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    PRIMARY KEY (key, window_start)
);

-- ────────────────────────────────
-- DATA RETENTION POLICIES (V20+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS retention_policy (
    table_name TEXT PRIMARY KEY,
    retention_days INTEGER NOT NULL,
    last_purged TEXT,
    description TEXT
);

-- ────────────────────────────────
-- LTI PLATFORMS (V20+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS lti_platform (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer TEXT NOT NULL,
    client_id TEXT NOT NULL,
    deployment_id TEXT,
    auth_url TEXT NOT NULL,
    token_url TEXT NOT NULL,
    jwks_url TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ────────────────────────────────
-- CLASSROOM SYSTEM (V21+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS classroom (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_user_id INTEGER NOT NULL REFERENCES user(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    invite_code TEXT UNIQUE NOT NULL,
    max_students INTEGER DEFAULT 30,
    billing_type TEXT DEFAULT 'per_student',
    stripe_subscription_id TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_classroom_teacher ON classroom(teacher_user_id);
CREATE INDEX IF NOT EXISTS idx_classroom_invite ON classroom(invite_code);

CREATE TABLE IF NOT EXISTS classroom_student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER NOT NULL REFERENCES classroom(id),
    user_id INTEGER NOT NULL REFERENCES user(id),
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT DEFAULT 'active',
    UNIQUE(classroom_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_cs_classroom ON classroom_student(classroom_id);
CREATE INDEX IF NOT EXISTS idx_cs_user ON classroom_student(user_id);

-- ────────────────────────────────
-- LTI USER MAPPING (V21+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS lti_user_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    issuer TEXT NOT NULL,
    lti_sub TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(issuer, lti_sub)
);

-- ────────────────────────────────
-- INITIALIZE BOOTSTRAP USER + PROFILE
-- ────────────────────────────────
INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier, is_active)
    VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'free', 0);
INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1);

-- ────────────────────────────────
-- QUALITY INFRASTRUCTURE (V42+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS quality_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    details TEXT,
    measured_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_quality_metric_type ON quality_metric(metric_type, measured_at);

CREATE TABLE IF NOT EXISTS spc_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_type TEXT NOT NULL,
    value REAL NOT NULL,
    subgroup_size INTEGER DEFAULT 1,
    observed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_spc_observation_type ON spc_observation(chart_type, observed_at);

CREATE TABLE IF NOT EXISTS risk_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    probability INTEGER NOT NULL DEFAULT 3,
    impact INTEGER NOT NULL DEFAULT 3,
    mitigation TEXT,
    contingency TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_risk_item_status ON risk_item(status);

CREATE TABLE IF NOT EXISTS work_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    item_type TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'backlog',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    ready_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,
    service_class TEXT DEFAULT 'standard',
    review_at TEXT,
    sprint_id INTEGER REFERENCES sprint(id),
    business_value INTEGER DEFAULT 5,
    time_criticality INTEGER DEFAULT 5,
    risk_reduction INTEGER DEFAULT 5,
    job_size INTEGER DEFAULT 5
);
CREATE INDEX IF NOT EXISTS idx_work_item_status ON work_item(status);

CREATE TABLE IF NOT EXISTS request_timing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'GET',
    status_code INTEGER,
    duration_ms REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_request_timing_path ON request_timing(path, recorded_at);

-- ────────────────────────────────
-- SHAREABLE STUDY LISTS (community)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS study_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    item_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array of content_item IDs
    public INTEGER NOT NULL DEFAULT 0,
    share_code TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_study_list_user ON study_list(user_id);
CREATE INDEX IF NOT EXISTS idx_study_list_share ON study_list(share_code);

-- Seed retention policies
INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
    VALUES ('crash_log', 90, 'Server crash logs — 90 day retention');
INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
    VALUES ('client_error_log', 30, 'Client error reports — 30 day retention');
INSERT OR IGNORE INTO retention_policy (table_name, retention_days, description)
    VALUES ('security_audit_log', 365, 'Security audit events — 1 year retention');

-- ────────────────────────────────
-- EXPERIMENT REGISTRY (V46+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS experiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT DEFAULT 'draft',  -- draft, running, paused, concluded
    variants TEXT NOT NULL,  -- JSON array of variant names
    traffic_pct REAL DEFAULT 100.0,  -- % of eligible users enrolled
    guardrail_metrics TEXT,  -- JSON: metrics that must not regress
    min_sample_size INTEGER DEFAULT 100,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    concluded_at TEXT,
    conclusion TEXT  -- JSON: winner, effect_size, p_value, decision
);

CREATE TABLE IF NOT EXISTS experiment_assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    assigned_at TEXT DEFAULT (datetime('now')),
    UNIQUE(experiment_id, user_id),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE TABLE IF NOT EXISTS experiment_exposure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    context TEXT,  -- where the exposure happened
    exposed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE INDEX IF NOT EXISTS idx_experiment_status ON experiment(status);
CREATE INDEX IF NOT EXISTS idx_experiment_assignment_exp ON experiment_assignment(experiment_id, user_id);
CREATE INDEX IF NOT EXISTS idx_experiment_exposure_exp ON experiment_exposure(experiment_id, user_id);

-- ────────────────────────────────
-- EXPERIMENT PROPOSALS (V99+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS experiment_proposal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    hypothesis TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'churn_signal', 'manual', 'anomaly'
    source_detail TEXT,                -- JSON context from signal
    variants TEXT NOT NULL,            -- JSON array
    traffic_pct REAL DEFAULT 50.0,
    guardrail_metrics TEXT,            -- JSON array
    min_sample_size INTEGER DEFAULT 100,
    priority INTEGER DEFAULT 0,        -- higher = more important
    status TEXT DEFAULT 'pending',     -- pending, approved, rejected, started
    created_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    started_experiment_id INTEGER,
    FOREIGN KEY (started_experiment_id) REFERENCES experiment(id)
);

CREATE TABLE IF NOT EXISTS experiment_rollout (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    winner_variant TEXT NOT NULL,
    rollout_stage TEXT DEFAULT 'pending', -- pending, 25pct, 50pct, 100pct, complete
    current_pct INTEGER DEFAULT 0,
    stage_started_at TEXT,
    next_stage_at TEXT,
    feature_flag_name TEXT,              -- linked flag for rollout
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE INDEX IF NOT EXISTS idx_experiment_proposal_status ON experiment_proposal(status);
CREATE INDEX IF NOT EXISTS idx_experiment_rollout_stage ON experiment_rollout(rollout_stage);

-- ────────────────────────────────
-- PASSAGE COMMENTS (V48+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS passage_comment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    passage_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_passage_comment_passage ON passage_comment(passage_id, created_at);
CREATE INDEX IF NOT EXISTS idx_passage_comment_user ON passage_comment(user_id);

-- ────────────────────────────────
-- CLASSROOM ASSIGNMENTS (V48+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS classroom_assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER NOT NULL,
    teacher_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    hsk_level INTEGER,
    content_item_ids TEXT,   -- JSON array of content_item IDs
    drill_types TEXT,        -- JSON array of drill type strings
    due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (classroom_id) REFERENCES classroom(id),
    FOREIGN KEY (teacher_user_id) REFERENCES user(id)
);

CREATE INDEX IF NOT EXISTS idx_classroom_assignment_class ON classroom_assignment(classroom_id);

-- ────────────────────────────────
-- WEBHOOK IDEMPOTENCY (V49+)
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS webhook_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_webhook_event_id ON webhook_event(event_id);


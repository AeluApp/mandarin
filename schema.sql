-- Mandarin Learning System — Database Schema (V18)
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
    locked_until TEXT
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

    -- Audio playback (macOS TTS) — 1 = on by default
    audio_enabled INTEGER NOT NULL DEFAULT 1,

    -- Personalization
    preferred_domains TEXT DEFAULT '',

    -- Behavioral commitment (V10+)
    next_session_intention TEXT,
    intention_set_at TEXT,
    minimal_days TEXT DEFAULT '',

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

    -- Staleness tracking
    times_shown INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    is_mined_out INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_content_type ON content_item(item_type);
CREATE INDEX IF NOT EXISTS idx_content_hsk ON content_item(hsk_level);
CREATE INDEX IF NOT EXISTS idx_content_lens ON content_item(content_lens);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_item(status);

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
    plan_snapshot TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_started ON session_log(started_at);
CREATE INDEX IF NOT EXISTS idx_session_log_user ON session_log(user_id, started_at);

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
            'reference_tracking', 'pragmatics_mismatch'
        )),

    user_answer TEXT,
    expected_answer TEXT,
    drill_type TEXT,
    notes TEXT,

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
    UNIQUE(content_item_id, error_type)
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
-- MEDIA WATCH
-- ────────────────────────────────
CREATE TABLE IF NOT EXISTS media_watch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    media_id TEXT NOT NULL UNIQUE,
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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    commission_rate REAL NOT NULL DEFAULT 0.30,
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
    user_id TEXT,
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
-- INITIALIZE BOOTSTRAP USER + PROFILE
-- ────────────────────────────────
INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier, is_active)
    VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin', 0);
INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1);

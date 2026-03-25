"""Experiment proposer — template-based + LLM-generative experiment design.

Given a finding from the product intelligence engine, proposes an A/B experiment:
1. First tries to match a template (fast, deterministic, no LLM cost).
2. If no template matches, falls back to LLM-generative design.

The output format matches what experiment_daemon.py and experiment_proposal table expect.
"""

import json
import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Valid scopes for experiment proposals ──────────────────────────────
VALID_SCOPES = {
    "parameter", "ui", "content", "business",
    "marketing", "architecture",
}

# ── Template registry: dimension/keyword → experiment template ─────────
# Each template must include: name, description, hypothesis, variants, scope.
# Templates are checked in order; first match wins.

_TEMPLATES: list[dict[str, Any]] = [
    # Churn-type templates (migrated from experiment_daemon)
    {
        "match": {"dimension": "retention", "keywords": ["boredom"]},
        "name": "auto_drill_variety",
        "description": "Test increased drill type variety for users showing boredom signals",
        "hypothesis": "More varied drill types reduce boredom-driven churn",
        "variants": ["control", "high_variety"],
        "scope": "parameter",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "retention", "keywords": ["frustration"]},
        "name": "auto_difficulty_easing",
        "description": "Test reduced difficulty for users showing frustration signals",
        "hypothesis": "Easier initial difficulty reduces frustration-driven churn",
        "variants": ["control", "easier_start"],
        "scope": "parameter",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "retention", "keywords": ["habit", "fade"]},
        "name": "auto_session_length",
        "description": "Test shorter sessions for users whose study habit is fading",
        "hypothesis": "Shorter sessions maintain habit better than longer ones",
        "variants": ["control", "short_sessions"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # Onboarding templates
    {
        "match": {"dimension": "onboarding", "keywords": ["drop-off", "abandon", "completion"]},
        "name": "auto_onboarding_simplify",
        "description": "Test simplified onboarding flow for higher completion",
        "hypothesis": "Fewer onboarding steps increase completion rate",
        "variants": ["control", "simplified_onboarding"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Engagement templates
    {
        "match": {"dimension": "engagement", "keywords": ["session", "short", "duration"]},
        "name": "auto_session_nudge",
        "description": "Test session extension nudges for low-engagement users",
        "hypothesis": "Gentle nudges to continue studying increase session length",
        "variants": ["control", "session_nudge"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Drill quality templates
    {
        "match": {"dimension": "drill_quality", "keywords": ["error", "accuracy", "wrong"]},
        "name": "auto_hint_system",
        "description": "Test hint-based scaffolding for drills with high error rates",
        "hypothesis": "Progressive hints reduce error rates without reducing learning",
        "variants": ["control", "progressive_hints"],
        "scope": "content",
        "duration_days": 21,
    },
    # Scheduling templates
    {
        "match": {"dimension": "scheduler_audit", "keywords": ["interval", "spacing", "review"]},
        "name": "auto_srs_tuning",
        "description": "Test adjusted SRS intervals for better retention",
        "hypothesis": "Tighter SRS intervals improve long-term retention",
        "variants": ["control", "tighter_intervals"],
        "scope": "parameter",
        "duration_days": 30,
    },
    # Frustration templates
    {
        "match": {"dimension": "frustration", "keywords": ["difficult", "hard", "struggle"]},
        "name": "auto_adaptive_difficulty",
        "description": "Test adaptive difficulty scaling based on recent performance",
        "hypothesis": "Dynamic difficulty reduces frustration without undermining challenge",
        "variants": ["control", "adaptive_difficulty"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # Visual vibe templates — aesthetic A/B tests
    {
        "match": {"dimension": "visual_vibe", "keywords": ["color", "palette", "warmth", "accent"]},
        "name": "auto_color_warmth_test",
        "description": "Test warmer accent palette for improved visual harmony",
        "hypothesis": "Warmer accent tones improve session completion and perceived quality",
        "variants": ["control", "warmer_accent"],
        "scope": "ui",
        "duration_days": 21,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["typography", "size", "scale", "heading"]},
        "name": "auto_type_scale_test",
        "description": "Test adjusted type scale for better reading hierarchy",
        "hypothesis": "Larger heading contrast improves content scanability and engagement",
        "variants": ["control", "larger_headings"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["motion", "transition", "speed", "animation"]},
        "name": "auto_motion_speed_test",
        "description": "Test adjusted animation timing for smoother perceived quality",
        "hypothesis": "Slightly slower transitions improve perceived craftsmanship",
        "variants": ["control", "slower_motion"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["shadow", "depth", "elevation", "card"]},
        "name": "auto_card_depth_test",
        "description": "Test increased shadow depth for dimensional richness",
        "hypothesis": "Deeper shadows improve visual hierarchy and perceived premium quality",
        "variants": ["control", "deeper_shadows"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["texture", "grain", "surface", "noise"]},
        "name": "auto_texture_intensity_test",
        "description": "Test increased paper-grain texture for tactile warmth",
        "hypothesis": "More visible grain texture improves warmth perception without distraction",
        "variants": ["control", "heavier_grain"],
        "scope": "ui",
        "duration_days": 21,
    },
    # UX templates
    {
        "match": {"dimension": "ux", "keywords": ["completion", "abandon", "drop"]},
        "name": "auto_session_completion_nudge",
        "description": "Test gentle progress indicators to reduce session abandonment",
        "hypothesis": "Visible progress towards session completion reduces mid-session drop-off",
        "variants": ["control", "progress_indicator"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "ux", "keywords": ["navigation", "confusion", "lost"]},
        "name": "auto_simplified_navigation",
        "description": "Test simplified navigation with fewer top-level options",
        "hypothesis": "Fewer navigation choices reduce user confusion and improve task completion",
        "variants": ["control", "simplified_nav"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Learning science templates
    {
        "match": {"dimension": "learning_science", "keywords": ["interleav", "spacing", "mixed"]},
        "name": "auto_interleaved_practice",
        "description": "Test interleaved practice mixing drill types within sessions",
        "hypothesis": "Interleaving drill types (reading, listening, production) improves long-term retention",
        "variants": ["control", "interleaved_drills"],
        "scope": "parameter",
        "duration_days": 30,
    },
    {
        "match": {"dimension": "learning_science", "keywords": ["output", "production", "recall"]},
        "name": "auto_production_emphasis",
        "description": "Test earlier introduction of production drills in learning sequence",
        "hypothesis": "Earlier production practice strengthens recall pathways vs passive review",
        "variants": ["control", "early_production"],
        "scope": "parameter",
        "duration_days": 21,
    },
    # Behavioral economics templates
    {
        "match": {"dimension": "behavioral_econ", "keywords": ["nudge", "default", "choice"]},
        "name": "auto_smart_default_session",
        "description": "Test smart session length defaults based on user history",
        "hypothesis": "Personalized session length defaults increase completion rate",
        "variants": ["control", "smart_defaults"],
        "scope": "parameter",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "behavioral_econ", "keywords": ["progress", "milestone", "streak"]},
        "name": "auto_milestone_framing",
        "description": "Test milestone-based progress framing vs raw statistics",
        "hypothesis": "Milestone framing (e.g., '3 more to next level') increases engagement over raw counts",
        "variants": ["control", "milestone_framing"],
        "scope": "ui",
        "duration_days": 14,
    },
    # GenAI templates
    {
        "match": {"dimension": "genai", "keywords": ["quality", "explanation", "feedback"]},
        "name": "auto_llm_feedback_detail",
        "description": "Test more detailed LLM explanations for incorrect answers",
        "hypothesis": "Richer AI explanations after errors improve subsequent accuracy",
        "variants": ["control", "detailed_feedback"],
        "scope": "content",
        "duration_days": 21,
    },
    {
        "match": {"dimension": "genai", "keywords": ["latency", "speed", "slow"]},
        "name": "auto_llm_streaming_response",
        "description": "Test streaming LLM responses vs waiting for complete response",
        "hypothesis": "Streaming responses reduce perceived latency and abandonment",
        "variants": ["control", "streaming_response"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Content templates
    {
        "match": {"dimension": "content", "keywords": ["coverage", "gap", "missing"]},
        "name": "auto_contextual_vocab",
        "description": "Test contextual vocab introduction via reading passages vs isolated flashcards",
        "hypothesis": "Vocab encountered in context has higher retention than isolated presentation",
        "variants": ["control", "contextual_intro"],
        "scope": "content",
        "duration_days": 21,
    },
    # Flow templates
    {
        "match": {"dimension": "flow", "keywords": ["transition", "between", "switch"]},
        "name": "auto_drill_transition",
        "description": "Test smooth animated transitions between drill types vs instant switch",
        "hypothesis": "Smooth transitions between drills reduce cognitive jarring and improve flow state",
        "variants": ["control", "smooth_transitions"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Platform templates
    {
        "match": {"dimension": "platform", "keywords": ["mobile", "touch", "responsive"]},
        "name": "auto_mobile_optimized_layout",
        "description": "Test mobile-optimized drill layout with larger touch targets",
        "hypothesis": "Larger touch targets and simplified mobile layout reduce input errors",
        "variants": ["control", "mobile_optimized"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Security templates
    {
        "match": {"dimension": "security", "keywords": ["login", "auth", "password"]},
        "name": "auto_passwordless_login",
        "description": "Test magic link login vs traditional password login",
        "hypothesis": "Passwordless login reduces friction and increases return rate",
        "variants": ["control", "magic_link"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Marketing templates
    {
        "match": {"dimension": "marketing", "keywords": ["landing", "signup", "conversion"]},
        "name": "auto_landing_social_proof",
        "description": "Test social proof elements on landing page (user count, testimonials)",
        "hypothesis": "Social proof on landing page increases signup conversion",
        "variants": ["control", "social_proof"],
        "scope": "marketing",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "marketing", "keywords": ["email", "activation", "welcome"]},
        "name": "auto_welcome_email_timing",
        "description": "Test immediate vs delayed (1hr) welcome email with first lesson prompt",
        "hypothesis": "Delayed welcome email catches users when ready to engage, improving activation",
        "variants": ["control_immediate", "delayed_1hr"],
        "scope": "marketing",
        "duration_days": 14,
    },
    # Brand health templates
    {
        "match": {"dimension": "brand_health", "keywords": ["nps", "satisfaction", "feedback"]},
        "name": "auto_nps_timing",
        "description": "Test NPS survey timing: after 5 sessions vs after 2 weeks",
        "hypothesis": "NPS after 5 completed sessions yields more representative scores than time-based",
        "variants": ["control_time_based", "session_based"],
        "scope": "business",
        "duration_days": 30,
    },
    # ── Remaining dimension templates ─────────────────────────────────
    # Profitability templates
    {
        "match": {"dimension": "profitability", "keywords": ["cost", "revenue", "margin", "pricing"]},
        "name": "auto_pricing_tier_test",
        "description": "Test adjusted pricing tiers for better conversion-to-revenue balance",
        "hypothesis": "A mid-price tier between free and premium increases total revenue per user",
        "variants": ["control", "mid_tier"],
        "scope": "business",
        "duration_days": 30,
    },
    # Engineering templates
    {
        "match": {"dimension": "engineering", "keywords": ["latency", "performance", "load", "error"]},
        "name": "auto_preload_strategy",
        "description": "Test aggressive preloading of next drill vs lazy loading",
        "hypothesis": "Preloading the next drill reduces inter-drill wait time and improves session flow",
        "variants": ["control_lazy", "preloaded"],
        "scope": "architecture",
        "duration_days": 14,
    },
    # SRS funnel templates
    {
        "match": {"dimension": "srs_funnel", "keywords": ["lapse", "decay", "promotion", "stage"]},
        "name": "auto_srs_lapse_recovery",
        "description": "Test gentler lapse penalty vs standard SRS demotion",
        "hypothesis": "Reducing lapse demotion severity improves long-term retention without inflating mastery",
        "variants": ["control", "gentle_lapse"],
        "scope": "parameter",
        "duration_days": 30,
    },
    # Tone phonology templates
    {
        "match": {"dimension": "tone_phonology", "keywords": ["tone", "pinyin", "pronunciation", "phonology"]},
        "name": "auto_tone_pair_drills",
        "description": "Test dedicated tone-pair minimal-pair drills vs mixed tone practice",
        "hypothesis": "Focused tone-pair contrast drills improve tone discrimination accuracy",
        "variants": ["control_mixed", "tone_pair_focused"],
        "scope": "content",
        "duration_days": 21,
    },
    # Encounter loop templates
    {
        "match": {"dimension": "encounter_loop", "keywords": ["encounter", "exposure", "repeat", "frequency"]},
        "name": "auto_encounter_spacing",
        "description": "Test varied encounter spacing: more frequent short exposures vs fewer deep ones",
        "hypothesis": "Higher-frequency shorter encounters improve recall better than fewer longer exposures",
        "variants": ["control", "frequent_short"],
        "scope": "parameter",
        "duration_days": 21,
    },
    # Output production templates
    {
        "match": {"dimension": "output_production", "keywords": ["writing", "typing", "produce", "generate"]},
        "name": "auto_guided_production",
        "description": "Test guided character writing with stroke hints vs unguided production",
        "hypothesis": "Stroke-order hints during production drills reduce errors without creating dependence",
        "variants": ["control_unguided", "stroke_hints"],
        "scope": "content",
        "duration_days": 21,
    },
    # Tutor integration templates
    {
        "match": {"dimension": "tutor_integration", "keywords": ["tutor", "teacher", "instructor", "human"]},
        "name": "auto_tutor_prep_summary",
        "description": "Test pre-session tutor summaries showing learner weak areas",
        "hypothesis": "Providing tutors with learner analytics before sessions improves session effectiveness",
        "variants": ["control", "tutor_summary"],
        "scope": "content",
        "duration_days": 30,
    },
    # Tone quality templates
    {
        "match": {"dimension": "tone_quality", "keywords": ["tone", "accuracy", "sandhi", "contour"]},
        "name": "auto_tone_feedback_mode",
        "description": "Test visual tone contour feedback vs text-only tone correction",
        "hypothesis": "Visual pitch contour display helps learners self-correct tones faster",
        "variants": ["control_text", "visual_contour"],
        "scope": "ui",
        "duration_days": 21,
    },
    # PM templates
    {
        "match": {"dimension": "pm", "keywords": ["roadmap", "priority", "backlog", "feature"]},
        "name": "auto_feature_request_voting",
        "description": "Test in-app feature voting to prioritize roadmap by user demand",
        "hypothesis": "User-voted features have higher adoption rates than internally-prioritized ones",
        "variants": ["control", "user_voted"],
        "scope": "business",
        "duration_days": 30,
    },
    # Timing templates
    {
        "match": {"dimension": "timing", "keywords": ["response", "speed", "delay", "wait"]},
        "name": "auto_feedback_delay",
        "description": "Test immediate vs brief delayed feedback after drill answers",
        "hypothesis": "A 500ms delay before showing correctness improves recall (desirable difficulty)",
        "variants": ["control_immediate", "delayed_500ms"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # UI templates (distinct from visual_vibe/ux)
    {
        "match": {"dimension": "ui", "keywords": ["layout", "component", "button", "interface"]},
        "name": "auto_drill_layout_density",
        "description": "Test compact vs spacious drill layout for answer options",
        "hypothesis": "More spacious answer layouts reduce mis-taps and improve perceived quality",
        "variants": ["control_compact", "spacious_layout"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Competitive templates
    {
        "match": {"dimension": "competitive", "keywords": ["competitor", "benchmark", "market", "alternative"]},
        "name": "auto_unique_value_highlight",
        "description": "Test highlighting unique features vs standard onboarding for switchers",
        "hypothesis": "Surfacing differentiated features to new users from competitors improves retention",
        "variants": ["control", "differentiator_highlight"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Copy templates
    {
        "match": {"dimension": "copy", "keywords": ["text", "wording", "label", "copy", "message"]},
        "name": "auto_encouragement_tone",
        "description": "Test data-grounded feedback copy vs neutral phrasing",
        "hypothesis": "Specific, data-backed feedback ('you improved X') outperforms generic encouragement",
        "variants": ["control_neutral", "data_grounded"],
        "scope": "content",
        "duration_days": 14,
    },
    # Tonal vibe templates
    {
        "match": {"dimension": "tonal_vibe", "keywords": ["voice", "personality", "warm", "tone"]},
        "name": "auto_app_voice_warmth",
        "description": "Test warmer conversational tone vs current neutral instructional voice",
        "hypothesis": "Slightly warmer app voice increases engagement without feeling patronizing",
        "variants": ["control_neutral", "warm_voice"],
        "scope": "content",
        "duration_days": 21,
    },
    # Feature usage templates
    {
        "match": {"dimension": "feature_usage", "keywords": ["usage", "adoption", "discover", "underused"]},
        "name": "auto_feature_discovery_nudge",
        "description": "Test contextual feature hints for underused but valuable features",
        "hypothesis": "Contextual nudges increase adoption of underused features without annoying users",
        "variants": ["control", "contextual_hints"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Engineering health templates
    {
        "match": {"dimension": "engineering_health", "keywords": ["debt", "test", "coverage", "build"]},
        "name": "auto_error_recovery_ux",
        "description": "Test graceful error recovery UI vs current error handling",
        "hypothesis": "Friendly error recovery with retry options reduces user drop-off after errors",
        "variants": ["control", "graceful_recovery"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Strategic templates
    {
        "match": {"dimension": "strategic", "keywords": ["goal", "vision", "long-term", "strategy"]},
        "name": "auto_learning_goal_setting",
        "description": "Test explicit goal-setting during onboarding vs organic exploration",
        "hypothesis": "Users who set explicit learning goals have higher 30-day retention",
        "variants": ["control_organic", "goal_setting"],
        "scope": "ui",
        "duration_days": 30,
    },
    # Governance templates
    {
        "match": {"dimension": "governance", "keywords": ["policy", "compliance", "rule", "threshold"]},
        "name": "auto_guardrail_sensitivity",
        "description": "Test stricter vs relaxed content guardrails for user-generated input",
        "hypothesis": "Slightly relaxed guardrails reduce false positives without increasing harmful content",
        "variants": ["control_strict", "relaxed_guardrails"],
        "scope": "parameter",
        "duration_days": 21,
    },
    # Data quality templates
    {
        "match": {"dimension": "data_quality", "keywords": ["data", "quality", "consistency", "missing"]},
        "name": "auto_data_validation_feedback",
        "description": "Test user-facing data quality indicators for content items",
        "hypothesis": "Showing content confidence indicators helps users trust and engage with material",
        "variants": ["control", "confidence_indicators"],
        "scope": "ui",
        "duration_days": 14,
    },
    # GenAI governance templates
    {
        "match": {"dimension": "genai_governance", "keywords": ["ai_safety", "hallucination", "filter", "moderation"]},
        "name": "auto_ai_confidence_display",
        "description": "Test showing AI confidence scores alongside generated explanations",
        "hypothesis": "Displaying AI confidence helps users calibrate trust in AI-generated content",
        "variants": ["control", "confidence_shown"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Memory model templates
    {
        "match": {"dimension": "memory_model", "keywords": ["memory", "forgetting", "curve", "retention"]},
        "name": "auto_forgetting_curve_calibration",
        "description": "Test personalized vs population-average forgetting curve parameters",
        "hypothesis": "Per-user forgetting curve calibration improves review scheduling accuracy",
        "variants": ["control_population", "personalized_curve"],
        "scope": "parameter",
        "duration_days": 30,
    },
    # Learner model templates
    {
        "match": {"dimension": "learner_model", "keywords": ["learner", "profile", "model", "predict"]},
        "name": "auto_learner_profile_transparency",
        "description": "Test showing learners their model profile vs keeping it hidden",
        "hypothesis": "Transparent learner profiles increase metacognitive engagement and study efficiency",
        "variants": ["control_hidden", "profile_visible"],
        "scope": "ui",
        "duration_days": 21,
    },
    # RAG templates
    {
        "match": {"dimension": "rag", "keywords": ["retrieval", "context", "knowledge", "search"]},
        "name": "auto_rag_context_depth",
        "description": "Test deeper context retrieval (more chunks) vs current retrieval depth",
        "hypothesis": "Deeper context retrieval improves AI explanation quality for complex grammar",
        "variants": ["control", "deeper_context"],
        "scope": "parameter",
        "duration_days": 21,
    },
    # Native speaker validation templates
    {
        "match": {"dimension": "native_speaker_validation", "keywords": ["native", "validation", "naturalness", "authentic"]},
        "name": "auto_native_validated_content",
        "description": "Test native-speaker-validated example sentences vs AI-generated ones",
        "hypothesis": "Native-validated examples improve learner naturalness scores in production drills",
        "variants": ["control_ai", "native_validated"],
        "scope": "content",
        "duration_days": 30,
    },
    # Curriculum templates
    {
        "match": {"dimension": "curriculum", "keywords": ["curriculum", "sequence", "order", "syllabus"]},
        "name": "auto_curriculum_flexibility",
        "description": "Test flexible curriculum allowing learner-chosen topic order vs strict sequence",
        "hypothesis": "Flexible topic ordering increases engagement without harming learning outcomes",
        "variants": ["control_strict", "flexible_order"],
        "scope": "content",
        "duration_days": 30,
    },
    # Input layer templates
    {
        "match": {"dimension": "input_layer", "keywords": ["input", "keyboard", "ime", "entry"]},
        "name": "auto_input_method_guidance",
        "description": "Test inline IME guidance vs unguided character input for production drills",
        "hypothesis": "Inline IME guidance reduces input friction and improves drill completion rates",
        "variants": ["control_unguided", "ime_guidance"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Accountability templates
    {
        "match": {"dimension": "accountability", "keywords": ["accountability", "commitment", "goal", "promise"]},
        "name": "auto_study_commitment_device",
        "description": "Test opt-in weekly study commitment vs no commitment device",
        "hypothesis": "Voluntary weekly study commitments increase session frequency without coercion",
        "variants": ["control", "weekly_commitment"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Commercial templates
    {
        "match": {"dimension": "commercial", "keywords": ["conversion", "upgrade", "premium", "subscription"]},
        "name": "auto_premium_value_preview",
        "description": "Test previewing premium features inline vs gated upgrade prompts",
        "hypothesis": "Brief premium feature previews during free use increase conversion rate",
        "variants": ["control_gated", "inline_preview"],
        "scope": "business",
        "duration_days": 21,
    },
    # Agentic templates
    {
        "match": {"dimension": "agentic", "keywords": ["agent", "autonomous", "proactive", "suggestion"]},
        "name": "auto_proactive_study_suggestions",
        "description": "Test AI agent proactively suggesting study topics vs user-initiated selection",
        "hypothesis": "Proactive AI study suggestions reduce decision fatigue and improve session starts",
        "variants": ["control_manual", "ai_suggestions"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # Cross-platform templates
    {
        "match": {"dimension": "cross_platform", "keywords": ["sync", "device", "cross-device", "continuity"]},
        "name": "auto_session_continuity",
        "description": "Test cross-device session continuity prompts vs fresh starts",
        "hypothesis": "Offering to resume last session on new device increases multi-device retention",
        "variants": ["control_fresh", "continue_session"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Growth accounting templates
    {
        "match": {"dimension": "growth_accounting", "keywords": ["growth", "acquisition", "activation", "churn"]},
        "name": "auto_reactivation_campaign",
        "description": "Test personalized reactivation nudges for churned users vs generic reminders",
        "hypothesis": "Personalized reactivation messages citing last progress increase return rate",
        "variants": ["control_generic", "personalized_reactivation"],
        "scope": "marketing",
        "duration_days": 30,
    },
    # Journey templates
    {
        "match": {"dimension": "journey", "keywords": ["journey", "path", "progress", "milestone"]},
        "name": "auto_learning_journey_map",
        "description": "Test visible learning journey map vs hidden progress tracking",
        "hypothesis": "A visible journey map showing overall progress increases long-term engagement",
        "variants": ["control_hidden", "journey_visible"],
        "scope": "ui",
        "duration_days": 21,
    },
    # Copy drift templates
    {
        "match": {"dimension": "copy_drift", "keywords": ["drift", "outdated", "stale", "mismatch"]},
        "name": "auto_dynamic_copy_refresh",
        "description": "Test dynamically updated marketing copy vs static copy",
        "hypothesis": "Marketing copy reflecting real-time content stats reduces trust erosion",
        "variants": ["control_static", "dynamic_copy"],
        "scope": "marketing",
        "duration_days": 14,
    },
    # Runtime health templates
    {
        "match": {"dimension": "runtime_health", "keywords": ["crash", "exception", "uptime", "stability"]},
        "name": "auto_error_boundary_granularity",
        "description": "Test fine-grained error boundaries per drill vs page-level error handling",
        "hypothesis": "Per-drill error boundaries prevent one failing drill from crashing the session",
        "variants": ["control_page", "per_drill_boundary"],
        "scope": "architecture",
        "duration_days": 14,
    },
    # Meta templates
    {
        "match": {"dimension": "meta", "keywords": ["meta", "self-improve", "intelligence", "system"]},
        "name": "auto_feedback_loop_frequency",
        "description": "Test more frequent intelligence audit cycles vs current cadence",
        "hypothesis": "More frequent but lighter audit cycles catch issues earlier with less overhead",
        "variants": ["control_cadence", "frequent_light"],
        "scope": "parameter",
        "duration_days": 30,
    },
    # Methodology templates
    {
        "match": {"dimension": "methodology", "keywords": ["method", "approach", "technique", "pedagogy"]},
        "name": "auto_comprehensible_input_ratio",
        "description": "Test higher ratio of comprehensible input (i+1) vs current difficulty mix",
        "hypothesis": "More content at i+1 level improves acquisition rate per Krashen's input hypothesis",
        "variants": ["control", "higher_i_plus_one"],
        "scope": "parameter",
        "duration_days": 30,
    },
]


def propose_experiment(
    conn: sqlite3.Connection,
    finding: dict[str, Any],
    *,
    source: str = "intelligence",
) -> dict[str, Any] | None:
    """Propose an A/B experiment for a product-intelligence finding.

    Tries template matching first, then falls back to LLM-generative design.

    Args:
        conn: DB connection (used for LLM cache + dedup checks).
        finding: A product-intelligence finding dict with at least
                 dimension, title, analysis, recommendation.
        source: Source label for the proposal (default "intelligence").

    Returns:
        Experiment proposal dict ready for insertion into experiment_proposal,
        or None if no experiment could be designed.
    """
    # 1. Try template match
    proposal = _match_template(finding)

    # 2. Fallback: LLM-generative design
    if proposal is None:
        proposal = _generate_experiment_llm(conn, finding)

    if proposal is None:
        return None

    # Ensure scope is valid
    if proposal.get("scope") not in VALID_SCOPES:
        proposal["scope"] = "parameter"

    # Attach source metadata
    proposal["source"] = source
    proposal["source_detail"] = json.dumps({
        "dimension": finding.get("dimension", ""),
        "title": finding.get("title", ""),
        "severity": finding.get("severity", ""),
    })

    return proposal


def _match_template(finding: dict[str, Any]) -> dict[str, Any] | None:
    """Try to match a finding against the template registry.

    Matching rules:
    - If template specifies a dimension, finding dimension must match.
    - If template specifies keywords, at least one must appear in the
      finding's title, analysis, or recommendation (case-insensitive).
    """
    dimension = finding.get("dimension", "")
    # Build a searchable text blob from the finding
    text_blob = " ".join([
        finding.get("title", ""),
        finding.get("analysis", ""),
        finding.get("recommendation", ""),
    ]).lower()

    for template in _TEMPLATES:
        match_spec = template["match"]

        # Dimension check
        if match_spec.get("dimension") and match_spec["dimension"] != dimension:
            continue

        # Keyword check — at least one keyword must appear
        keywords = match_spec.get("keywords", [])
        if keywords and not any(kw.lower() in text_blob for kw in keywords):
            continue

        # Match found — build proposal
        return {
            "name": template["name"],
            "description": template["description"],
            "hypothesis": template["hypothesis"],
            "variants": template["variants"],
            "scope": template.get("scope", "parameter"),
            "duration_days": template.get("duration_days", 14),
            "llm_generated": False,
        }

    return None


def _generate_experiment_llm(
    conn: sqlite3.Connection,
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Use the LLM to design an A/B experiment when no template matches.

    Sends a structured prompt to the LLM asking it to design a 2-variant
    experiment. Parses the JSON response and returns a proposal dict in
    the same format as template matches.

    Returns None on any failure (LLM unavailable, parse error, etc.).
    Never raises.
    """
    try:
        from ..ai.ollama_client import generate
    except ImportError:
        logger.debug("ollama_client not available — skipping LLM experiment design")
        return None

    dimension = finding.get("dimension", "unknown")
    title = finding.get("title", "")
    analysis = finding.get("analysis", "")
    recommendation = finding.get("recommendation", "")

    # Build aesthetic context if this is a visual/aesthetic finding
    aesthetic_ctx = ""
    if dimension in ("visual_vibe", "ui", "brand_health"):
        aesthetic_ctx = (
            "\n\nAESTHETIC CONTEXT:\n"
            "This is a visual/aesthetic finding. The experiment can test ANY visual aspect:\n"
            "- Individual images, illustrations, or assets (swap for a generated alternative)\n"
            "- Animation curves, durations, or easing functions\n"
            "- Color temperature, saturation, or specific hex values\n"
            "- Typography size, weight, line-height, or font choice\n"
            "- Shadow depth, blur, or spread values\n"
            "- Texture intensity (paper grain, noise overlay opacity)\n"
            "- Layout spacing, padding, margins, or grid gaps\n"
            "- Overall page gestalt (the holistic visual impression of a whole screen)\n"
            "- Specific component styling (buttons, cards, inputs, headers)\n"
            "- Dark mode specific adjustments\n"
            "- Scroll-driven animation intensity or parallax speed\n"
            "- WebGL atmosphere opacity, color blending, or mouse sensitivity\n"
            "- AI-generated images vs. current illustrations\n"
            "- Video backgrounds vs. static images\n"
            "- Sound-to-visual synchronization timing\n"
            "The app uses a 'Civic Sanctuary' aesthetic: warm Mediterranean, serif typography, "
            "no decoration without function. Feature flags control variants via CSS custom "
            "properties or JS conditionals.\n"
        )

    prompt = f"""Design a 2-variant A/B experiment for this product finding:

DIMENSION: {dimension}
TITLE: {title}
ANALYSIS: {analysis}
RECOMMENDATION: {recommendation}
{aesthetic_ctx}
The experiment should:
1. Have a clear hypothesis
2. Define variant_a (control) and variant_b (the change)
3. Specify a measurable success metric
4. Be implementable by a solo developer
5. Can be ANY type: parameter change, UI redesign, business model test, marketing copy, content strategy, scheduling algorithm, pricing, onboarding flow, etc.

Respond in JSON only, no other text:
{{"hypothesis": "...", "variant_a": {{"name": "control", "description": "..."}}, "variant_b": {{"name": "...", "description": "...", "changes": ["change 1", "change 2"]}}, "metric": "...", "duration_days": N, "scope": "parameter|ui|content|business|marketing|architecture"}}"""

    system = (
        "You are an A/B experiment designer for a Mandarin learning app. "
        "Respond with valid JSON only. No markdown fences, no explanation."
    )

    try:
        resp = generate(
            prompt=prompt,
            system=system,
            temperature=0.4,
            max_tokens=512,
            use_cache=True,
            conn=conn,
            task_type="experiment_design",
        )
    except Exception:
        logger.debug("LLM call failed for experiment design", exc_info=True)
        return None

    if not resp or not resp.success or not resp.text:
        logger.debug("LLM experiment design returned no usable response")
        return None

    # Parse JSON from response (handle markdown fences if present)
    return _parse_llm_experiment(resp.text, finding)


def _parse_llm_experiment(
    raw_text: str,
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Parse and validate LLM JSON response into a proposal dict.

    Handles common LLM quirks: markdown fences, trailing commas, extra text.
    Returns None if parsing fails or required fields are missing.
    """
    try:
        # Strip markdown code fences if present
        text = raw_text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # Try to find JSON object in the text
        # (LLM may include preamble or trailing text)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start == -1 or brace_end == -1 or brace_end <= brace_start:
            logger.debug("No JSON object found in LLM response")
            return None

        json_str = text[brace_start:brace_end + 1]
        data = json.loads(json_str)

        # Validate required fields
        hypothesis = data.get("hypothesis", "").strip()
        if not hypothesis:
            logger.debug("LLM experiment missing hypothesis")
            return None

        variant_a = data.get("variant_a", {})
        variant_b = data.get("variant_b", {})
        if not isinstance(variant_a, dict) or not isinstance(variant_b, dict):
            logger.debug("LLM experiment variants not dicts")
            return None

        metric = data.get("metric", "").strip()
        if not metric:
            logger.debug("LLM experiment missing metric")
            return None

        # Extract variant names
        va_name = variant_a.get("name", "control")
        vb_name = variant_b.get("name", "treatment")

        # Sanitize duration
        try:
            duration_days = int(data.get("duration_days", 14))
            duration_days = max(7, min(duration_days, 90))  # clamp 7..90
        except (ValueError, TypeError):
            duration_days = 14

        # Sanitize scope
        scope = data.get("scope", "parameter")
        if isinstance(scope, str) and "|" in scope:
            # LLM may return the template literally "parameter|ui|..."
            scope = scope.split("|")[0]
        if scope not in VALID_SCOPES:
            scope = "parameter"

        # Build description from variant details
        va_desc = variant_a.get("description", "Current behavior (control)")
        vb_desc = variant_b.get("description", "Modified behavior")
        vb_changes = variant_b.get("changes", [])

        description_parts = [
            f"Hypothesis: {hypothesis}",
            f"Control: {va_desc}",
            f"Treatment: {vb_desc}",
            f"Metric: {metric}",
        ]
        if vb_changes:
            description_parts.append("Changes: " + "; ".join(str(c) for c in vb_changes[:5]))

        # Build a safe experiment name from the finding
        dimension = finding.get("dimension", "unknown")
        safe_title = re.sub(r"[^a-z0-9]+", "_", finding.get("title", "experiment").lower())
        safe_title = safe_title[:40].strip("_")
        name = f"llm_{dimension}_{safe_title}"

        return {
            "name": name,
            "description": "\n".join(description_parts),
            "hypothesis": hypothesis,
            "variants": [va_name, vb_name],
            "scope": scope,
            "duration_days": duration_days,
            "metric": metric,
            "llm_generated": True,
            "llm_design": {
                "variant_a": variant_a,
                "variant_b": variant_b,
                "metric": metric,
            },
        }

    except json.JSONDecodeError as e:
        logger.debug("Failed to parse LLM experiment JSON: %s", e)
        return None
    except Exception:
        logger.debug("Unexpected error parsing LLM experiment", exc_info=True)
        return None


def propose_experiments_for_findings(
    conn: sqlite3.Connection,
    findings: list[dict[str, Any]],
    *,
    max_proposals: int = 3,
    source: str = "intelligence",
) -> list[dict[str, Any]]:
    """Batch-propose experiments for a list of findings.

    Skips findings that already have pending/active proposals or experiments.
    Returns up to max_proposals experiment proposals.
    """
    proposals = []

    for finding in findings:
        if len(proposals) >= max_proposals:
            break

        proposal = propose_experiment(conn, finding, source=source)
        if proposal is None:
            continue

        name = proposal["name"]

        # Dedup: skip if already proposed or running
        try:
            existing = conn.execute(
                "SELECT id FROM experiment_proposal WHERE name = ? AND status IN ('pending', 'started')",
                (name,),
            ).fetchone()
            if existing:
                continue

            existing_exp = conn.execute(
                "SELECT id FROM experiment WHERE name = ? AND status IN ('draft', 'running')",
                (name,),
            ).fetchone()
            if existing_exp:
                continue
        except sqlite3.OperationalError:
            # Table may not exist yet
            pass

        proposals.append(proposal)

    return proposals

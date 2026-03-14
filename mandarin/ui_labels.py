"""User-facing labels for drill types and modalities.

Internal identifiers (ime_type, mc, etc.) should never appear in UI.
Use these labels instead.
"""

DRILL_LABELS = {
    "mc": "Multiple choice",
    "reverse_mc": "Reverse multiple choice",
    "ime_type": "Typing",
    "tone": "Tone",
    "listening_gist": "Listening",
    "listening_detail": "Listening (detail)",
    "listening_tone": "Tone listening",
    "listening_dictation": "Dictation",
    "listening_passage": "Passage listening",
    "dictation_sentence": "Sentence dictation",
    "english_to_pinyin": "English to Pinyin",
    "hanzi_to_pinyin": "Hanzi to Pinyin",
    "pinyin_to_hanzi": "Pinyin to Hanzi",
    "transfer": "Transfer",
    "translation": "Translation",
    "sentence_build": "Sentence building",
    "word_order": "Word order",
    "speaking": "Speaking",
    "intuition": "Intuition",
    "register_choice": "Register",
    "pragmatic": "Pragmatic",
    "slang_exposure": "Slang",
    "measure_word": "Measure word",
    "measure_word_cloze": "MW cloze",
    "measure_word_production": "MW production",
    "measure_word_disc": "MW discrimination",
    "particle_disc": "Particle",
    "homophone": "Homophone",
    "cloze_context": "Cloze",
    "synonym_disc": "Synonym",
    "dialogue": "Dialogue",
    "media_comprehension": "Media",
    "shadowing": "Shadowing",
    "minimal_pair": "Minimal pair",
    "passage_dictation": "Passage dictation",
    "number_system": "Number system",
    "tone_sandhi": "Tone sandhi",
    "complement": "Complement",
    "ba_bei": "把/被",
    "collocation": "Collocation",
    "radical": "Radical",
    "error_correction": "Error correction",
    "chengyu": "Chengyu",
    "contrastive": "Contrastive",
    "image_association": "Image association",
    "video_comprehension": "Video comprehension",
}

SESSION_OUTCOME_LABELS = {
    "completed": "Completed",
    "abandoned": "Ended early",
    "bounced": "Bounced",
    "interrupted": "Interrupted",
}

MODALITY_LABELS = {
    "reading": "Reading",
    "recognition": "Recognition",
    "ime": "Typing",
    "tone": "Tone",
    "listening": "Listening",
    "listening_detail": "Listening (detail)",
    "speaking": "Speaking",
    "production": "Production",
}

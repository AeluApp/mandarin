# Data Sources

All data in this system is sourced from the following:

## HSK 3.0 Vocabulary Lists
- **Source:** drkameleon/complete-hsk-vocabulary (GitHub, CC-BY)
- **Coverage:** HSK levels 1–9, complete word lists with pinyin and English definitions
- **Used in:** `data/hsk/hsk1.json` through `data/hsk/hsk9.json` (canonical word lists per level)

## HSK 3.0 Standards
- **Source:** 《国际中文教育中文水平等级标准》 (GF 0025-2021)
- **Published by:** Ministry of Education, People's Republic of China (March 2021)
- **URL:** http://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202103/t20210329_523304.html
- **Used in:** `data/hsk_requirements.json` (level requirements, accuracy targets, vocab counts), HSK cumulative counts in `mandarin/diagnostics.py`

## Grammar Points
- **Source:** Manually compiled from standard HSK textbooks and the HSK 3.0 syllabus
- **Coverage:** 26 grammar points across HSK 1–3
- **Used in:** `mandarin/grammar_seed.py`

## Language Skills
- **Source:** Compiled from HSK 3.0 communicative competence standards
- **Coverage:** 14 skills across pragmatic, register, cultural, and phonetic categories (HSK 1–3)
- **Used in:** `mandarin/grammar_seed.py`

## Context Notes
- **Source:** Original content authored for this system
- **Coverage:** Context notes keyed by hanzi, covering HSK 1-3 core vocabulary
- **Used in:** `mandarin/context_notes.py`

## Dialogue Scenarios
- **Source:** Original content authored for this system
- **Coverage:** 8 scenarios across HSK 1–3 covering restaurant, taxi, market, plans, hotel, directions, phone, and returns
- **Used in:** `data/scenarios/`

## Pinyin Data
- **Source:** Derived from the HSK vocabulary source (drkameleon/complete-hsk-vocabulary)

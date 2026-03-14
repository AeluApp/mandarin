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

## CC-CEDICT Dictionary Data
- **Source:** CC-CEDICT (community-maintained Chinese-English dictionary)
- **License:** CC BY-SA 3.0 Unported
- **URL:** https://cc-cedict.org/
- **Used in:** `mandarin/ai/rag_layer.py` → `rag_knowledge_base` table (definitions, pinyin, traditional forms)
- **Note:** The RAG knowledge base artifact incorporating CC-CEDICT data is subject to CC BY-SA 3.0. See THIRD_PARTY_LICENSES.md for details.

## Text-to-Speech Audio
- **Source:** Edge TTS (Microsoft neural voices via edge-tts library)
- **License:** LGPL-3.0 (library); Microsoft service terms apply to generated audio
- **Used in:** `mandarin/audio.py` (primary TTS), browser speechSynthesis API (web fallback), macOS `say` (CLI fallback)

## AI-Generated Content
- **Source:** Qwen 2.5 (7B / 1.5B) running locally via Ollama
- **License:** Qwen License (Apache-2.0 basis with acceptable use policy)
- **Used in:** Drill sentence generation, reading passage generation, error explanations
- **Note:** All generated content passes through a validation gate and human review queue before entering the SRS. See `mandarin/ai/drill_generator.py` and `mandarin/ai/validation.py`.

## Competitor & Research Signals
- **Source:** Public web (Duolingo blog, HelloChinese updates, arXiv SLA RSS)
- **Method:** BeautifulSoup + httpx with robots.txt compliance, 2-second rate limiting
- **Used in:** `mandarin/ai/web_crawler.py` (strategic intelligence only — not learner content)

## Media Catalog
- **Source:** Curated external links to YouTube / Bilibili content
- **Method:** Metadata and subtitle extraction via yt-dlp; vocabulary analysis via jieba
- **Used in:** `data/media_catalog.json`, `scripts/ingest_media.py`
- **Note:** No video or audio content is hosted. Links point to original platforms.

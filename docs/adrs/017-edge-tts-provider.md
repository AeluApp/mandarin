# ADR-009: Use edge-tts for Text-to-Speech

## Status

Accepted (2026-02)

## Context

Aelu needs Chinese text-to-speech for:

- Listening drills (hear the word/sentence, identify meaning)
- Audio auto-play on drill presentation
- Speaking drills (hear the target, then produce it)
- Graded reader audio accompaniment

Requirements:
- High-quality Mandarin Chinese voices (natural prosody, correct tones)
- Low latency (audio should play within 200ms of request)
- No per-request cost (usage scales with users)
- No API key management

Options considered:

1. **edge-tts** (Microsoft Edge's TTS via reverse-engineered API)
2. **Google Cloud TTS** ($4-16 per million characters)
3. **Amazon Polly** ($4 per million characters)
4. **macOS `say` command** (local, macOS only)
5. **Coqui TTS** (open-source, self-hosted)
6. **Browser Web Speech API** (client-side, no server cost)

## Decision

Use **edge-tts** Python library as the primary TTS provider, with browser Web Speech API as a fallback for the web client.

## Rationale

### Why edge-tts

1. **Free.** No API key, no per-character pricing, no monthly quota. Uses Microsoft's Edge browser TTS service, which is offered free as part of the Edge browser experience.

2. **High quality.** Microsoft's neural TTS voices for Chinese (zh-CN-XiaoxiaoNeural, zh-CN-YunxiNeural) are among the best available. Natural prosody, correct tone sandhi handling, multiple voice options.

3. **Simple integration.** `pip install edge-tts`. Async API generates audio bytes directly. No OAuth, no service account, no SDK initialization.

4. **Multiple voices.** Supports male and female voices with different speaking styles (cheerful, calm, newscast). Can vary voice by context (formal vs casual dialogue).

5. **SSML support.** Can control speaking rate, pitch, emphasis, and pauses via SSML markup. Useful for slowing down audio for beginners.

### Implementation

```python
import edge_tts
import asyncio

async def generate_audio(text, voice="zh-CN-XiaoxiaoNeural", rate="+0%"):
    """Generate TTS audio bytes."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes
```

Audio is generated server-side, cached on disk, and served as static files. Typical generation time: 200-500ms for a sentence. Once cached, serving is instant.

### Why Not Alternatives

| Option | Reason Against |
|--------|---------------|
| Google Cloud TTS | $4-16/million chars. At 10K users generating 1K chars/day = 10M chars/month = $40-160/month. 10-40x hosting cost. |
| Amazon Polly | Similar pricing to Google. Same cost concern. |
| macOS `say` | Only works on macOS (not Linux/Fly.io). Voice quality below neural TTS. |
| Coqui TTS | Requires GPU for real-time generation. Self-hosting adds significant infrastructure. Quality below commercial neural TTS for Chinese. |
| Web Speech API | Quality varies by browser/OS. iOS Safari and Chrome have decent Chinese voices, but no consistency guarantee. Cannot cache or control server-side. Used as fallback only. |

## Consequences

### Positive

- Zero TTS cost regardless of scale
- High-quality neural voices with natural Chinese prosody
- Audio cached server-side for instant playback
- Multiple voices available for variety
- SSML control for speaking rate adjustment (slower for beginners)

### Negative

- **No SLA.** edge-tts uses an unofficial API. Microsoft could change, rate-limit, or shut down the endpoint at any time. There is no contractual guarantee of availability.
- **Dependency on Microsoft's service.** If the endpoint goes down, TTS fails. The app degrades gracefully (drills work without audio, but listening drills are broken).
- **Potential legal gray area.** The edge-tts library reverse-engineers Microsoft's API. It's unclear whether this violates Microsoft's terms of service. Usage is widespread in the open-source community with no enforcement action to date.
- **Rate limiting risk.** Under heavy load, Microsoft may throttle requests. Mitigated by aggressive caching (generate once, serve forever for static content).

### Neutral

- Audio files are cached as MP3 on the Fly.io volume. Cache size grows linearly with content (estimated 50MB for 1,000 unique audio clips).
- Cache invalidation is manual (delete and regenerate if voice quality improves or content changes).

## Fallback Strategy

```
Primary:   edge-tts (server-side, cached)
Fallback:  Browser Web Speech API (client-side, no caching)
Emergency: Pre-recorded audio files (manually recorded for top 100 items)
```

If edge-tts becomes unavailable:

1. **Immediate:** Web Speech API fallback activates automatically (JavaScript SpeechSynthesis).
2. **Short-term (days):** Evaluate alternative free TTS (e.g., OpenAI TTS if pricing drops, or new open-source models).
3. **Medium-term (weeks):** Migrate to Google Cloud TTS or Amazon Polly with usage-based pricing. Budget $50-100/month for TTS at scale.

## Revisit Triggers

1. **edge-tts service discontinuation** — Microsoft shuts down or restricts the endpoint
2. **Quality degradation** — voice quality drops (model changes, bitrate reduction)
3. **Rate limiting** — consistent 429 errors under normal load
4. **Legal notice** — Microsoft issues takedown or cease-and-desist to edge-tts project
5. **Better alternative** — open-source Chinese TTS achieves neural-quality output that can be self-hosted cheaply (e.g., MeloTTS, ChatTTS improvements)

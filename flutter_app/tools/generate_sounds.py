#!/usr/bin/env python3
"""
Generate warm, organic sound effects for Aelu.

Design philosophy: Civic Sanctuary aesthetic — warm wood, soft teal, terracotta.
Sounds should feel like a ceramic bell, a wooden tap, a breath.
Multi-harmonic synthesis with ADSR envelopes, subtle detuning for warmth.

All output: 44100 Hz, 16-bit, mono WAV.
Peak loudness normalized to -10 dBFS (±1 dB).
"""

import struct
import wave
import math
import os

SAMPLE_RATE = 44100
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sounds')


def _ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _normalize(samples: list[float], peak_db: float = -10.0) -> list[float]:
    """Normalize to target peak dBFS."""
    peak = max(abs(s) for s in samples) or 1.0
    target = 10 ** (peak_db / 20.0)
    scale = target / peak
    return [s * scale for s in samples]


def _write_wav(filename: str, samples: list[float]):
    """Write 16-bit mono WAV."""
    path = os.path.join(OUTPUT_DIR, filename)
    normalized = _normalize(samples)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for s in normalized:
            clamped = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack('<h', int(clamped * 32767)))
    print(f'  {filename}: {len(samples)/SAMPLE_RATE:.3f}s')


def _sine(freq: float, t: float, detune: float = 0.0) -> float:
    """Sine with optional detune (Hz)."""
    return math.sin(2 * math.pi * (freq + detune) * t)


def _triangle(freq: float, t: float) -> float:
    """Triangle wave — softer than sine for body."""
    phase = (freq * t) % 1.0
    return 4 * abs(phase - 0.5) - 1.0


def _adsr(t: float, attack: float, decay: float, sustain: float,
          release: float, duration: float) -> float:
    """ADSR envelope. Duration = total note length."""
    release_start = duration - release
    if t < 0:
        return 0.0
    if t < attack:
        return t / attack
    if t < attack + decay:
        return 1.0 - (1.0 - sustain) * ((t - attack) / decay)
    if t < release_start:
        return sustain
    if t < duration:
        return sustain * (1.0 - (t - release_start) / release)
    return 0.0


def _exp_decay(t: float, decay: float) -> float:
    """Exponential decay from 1.0."""
    return math.exp(-t / decay)


def _warm_tone(freq: float, t: float, detune: float = 0.5) -> float:
    """Warm multi-harmonic tone: fundamental + soft overtones + slight detune."""
    return (
        0.50 * _sine(freq, t) +
        0.20 * _sine(freq, t, detune) +          # chorused fundamental
        0.15 * _sine(freq * 2, t) +               # 2nd harmonic
        0.08 * _sine(freq * 3, t, -detune) +      # 3rd harmonic, detuned
        0.04 * _sine(freq * 4, t) +               # 4th (subtle)
        0.03 * _triangle(freq * 0.5, t)           # sub-octave body
    )


def _bell_tone(freq: float, t: float) -> float:
    """Bell-like tone: inharmonic partials that decay at different rates."""
    return (
        0.40 * _sine(freq, t) * _exp_decay(t, 0.4) +
        0.25 * _sine(freq * 2.76, t) * _exp_decay(t, 0.25) +
        0.15 * _sine(freq * 5.04, t) * _exp_decay(t, 0.15) +
        0.10 * _sine(freq * 7.73, t) * _exp_decay(t, 0.10) +
        0.10 * _sine(freq * 0.5, t) * _exp_decay(t, 0.5)
    )


def _wood_tap(t: float) -> float:
    """Short woody percussion: filtered noise-like via detuned sines."""
    return (
        0.40 * _sine(800, t) * _exp_decay(t, 0.015) +
        0.30 * _sine(1200, t) * _exp_decay(t, 0.010) +
        0.20 * _sine(400, t) * _exp_decay(t, 0.025) +
        0.10 * _sine(2400, t) * _exp_decay(t, 0.008)
    )


# ── Sound generators ──

def gen_correct():
    """Two rising notes — ceramic ping. C5 → E5."""
    dur = 0.22
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env1 = _adsr(t, 0.005, 0.04, 0.3, 0.10, 0.12)
        env2 = _adsr(t - 0.08, 0.005, 0.04, 0.3, 0.10, 0.14)
        s = (
            env1 * _bell_tone(523.25, t) +       # C5
            env2 * _bell_tone(659.25, t - 0.08)   # E5
        )
        samples.append(s)
    _write_wav('correct.wav', samples)


def gen_wrong():
    """Soft low thud — not punishing, just informational. Descending minor 2nd."""
    dur = 0.28
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env1 = _adsr(t, 0.008, 0.05, 0.25, 0.12, 0.15)
        env2 = _adsr(t - 0.10, 0.008, 0.05, 0.20, 0.12, 0.18)
        s = (
            env1 * _warm_tone(220, t) +          # A3
            env2 * _warm_tone(207.65, t - 0.10)  # Ab3
        )
        samples.append(s)
    _write_wav('wrong.wav', samples)


def gen_navigate():
    """Quick soft click — like touching polished wood."""
    dur = 0.06
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = _wood_tap(t) * _adsr(t, 0.002, 0.02, 0.1, 0.03, dur)
        samples.append(s)
    _write_wav('navigate.wav', samples)


def gen_hint_reveal():
    """Gentle downward shimmer — revealing something hidden."""
    dur = 0.18
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Descending pitch: G5 → D5
        freq = 783.99 - (783.99 - 587.33) * (t / dur) ** 0.7
        env = _adsr(t, 0.005, 0.03, 0.4, 0.10, dur)
        s = env * (
            0.6 * _sine(freq, t) +
            0.3 * _sine(freq * 2, t) * _exp_decay(t, 0.12) +
            0.1 * _sine(freq * 3, t) * _exp_decay(t, 0.08)
        )
        samples.append(s)
    _write_wav('hint_reveal.wav', samples)


def gen_session_start():
    """Warm ascending arpeggio — the beginning of something meaningful. C4→E4→G4→C5."""
    dur = 0.55
    n = int(SAMPLE_RATE * dur)
    notes = [(261.63, 0.0), (329.63, 0.10), (392.00, 0.20), (523.25, 0.30)]
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for freq, onset in notes:
            dt = t - onset
            if dt >= 0:
                env = _adsr(dt, 0.010, 0.05, 0.35, 0.15, 0.25)
                s += env * _warm_tone(freq, dt, detune=0.7)
        samples.append(s)
    _write_wav('session_start.wav', samples)


def gen_session_complete():
    """Resolving chord — warmth and completion. C major spread."""
    dur = 0.60
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _adsr(t, 0.015, 0.08, 0.5, 0.30, dur)
        s = env * (
            0.30 * _warm_tone(261.63, t, 0.5) +   # C4
            0.25 * _warm_tone(329.63, t, 0.6) +   # E4
            0.25 * _warm_tone(392.00, t, 0.4) +   # G4
            0.20 * _warm_tone(523.25, t, 0.3)     # C5
        )
        samples.append(s)
    _write_wav('session_complete.wav', samples)


def gen_level_up():
    """Triumphant ascending figure — clear achievement. C→E→G→C (octave higher, brighter)."""
    dur = 0.60
    n = int(SAMPLE_RATE * dur)
    notes = [(523.25, 0.0), (659.25, 0.08), (783.99, 0.16), (1046.50, 0.24)]
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for freq, onset in notes:
            dt = t - onset
            if dt >= 0:
                env = _adsr(dt, 0.008, 0.04, 0.40, 0.20, 0.36)
                s += env * _bell_tone(freq, dt)
        samples.append(s)
    _write_wav('level_up.wav', samples)


def gen_milestone():
    """Sustained bell chord — moment of recognition. Am9 voicing."""
    dur = 0.50
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _adsr(t, 0.010, 0.06, 0.50, 0.25, dur)
        s = env * (
            0.30 * _bell_tone(440.00, t) +     # A4
            0.25 * _bell_tone(523.25, t) +     # C5
            0.25 * _bell_tone(659.25, t) +     # E5
            0.20 * _bell_tone(493.88, t)       # B4 (the 9th)
        )
        samples.append(s)
    _write_wav('milestone.wav', samples)


def gen_streak_milestone():
    """Richer celebration than milestone — streak is personal. Ascending bell cascade."""
    dur = 0.55
    n = int(SAMPLE_RATE * dur)
    notes = [(440, 0.0), (554.37, 0.06), (659.25, 0.12), (880, 0.20)]
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for freq, onset in notes:
            dt = t - onset
            if dt >= 0:
                env = _adsr(dt, 0.006, 0.04, 0.45, 0.20, 0.35)
                s += env * _bell_tone(freq, dt)
        samples.append(s)
    _write_wav('streak_milestone.wav', samples)


def gen_achievement_unlock():
    """Grand reveal — rare and special. Spread major 7th with shimmer."""
    dur = 0.65
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _adsr(t, 0.012, 0.06, 0.55, 0.35, dur)
        # Cmaj7 spread voicing
        s = env * (
            0.25 * _bell_tone(261.63, t) +     # C4
            0.20 * _bell_tone(329.63, t) +     # E4
            0.20 * _bell_tone(392.00, t) +     # G4
            0.20 * _bell_tone(493.88, t) +     # B4
            0.15 * _warm_tone(523.25, t, 0.8)  # C5 warm body
        )
        samples.append(s)
    _write_wav('achievement_unlock.wav', samples)


def gen_timer_tick():
    """Barely-there metronome — does not distract."""
    dur = 0.04
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _exp_decay(t, 0.012)
        s = env * (
            0.6 * _sine(1200, t) +
            0.3 * _sine(2400, t) +
            0.1 * _sine(600, t)
        )
        samples.append(s)
    _write_wav('timer_tick.wav', samples)


def gen_transition_in():
    """Soft whoosh-up — entering a new space."""
    dur = 0.22
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        progress = t / dur
        # Rising filtered sweep
        freq = 200 + 600 * progress ** 0.5
        env = _adsr(t, 0.02, 0.05, 0.3, 0.12, dur)
        s = env * (
            0.5 * _sine(freq, t) +
            0.3 * _sine(freq * 1.5, t) * (1.0 - progress) +
            0.2 * _sine(freq * 0.5, t)
        )
        samples.append(s)
    _write_wav('transition_in.wav', samples)


def gen_transition_out():
    """Soft whoosh-down — leaving gently."""
    dur = 0.22
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        progress = t / dur
        # Falling filtered sweep
        freq = 800 - 600 * progress ** 0.5
        env = _adsr(t, 0.01, 0.04, 0.3, 0.12, dur)
        s = env * (
            0.5 * _sine(freq, t) +
            0.3 * _sine(freq * 1.5, t) * progress +
            0.2 * _sine(freq * 0.5, t)
        )
        samples.append(s)
    _write_wav('transition_out.wav', samples)


def gen_record_pulse():
    """Gentle pulse — "I'm listening." Soft throb at ~2Hz."""
    dur = 0.12
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _adsr(t, 0.015, 0.03, 0.4, 0.05, dur)
        s = env * (
            0.6 * _sine(330, t) +   # E4
            0.3 * _sine(660, t) +   # E5
            0.1 * _sine(165, t)     # E3 body
        )
        samples.append(s)
    _write_wav('record_pulse.wav', samples)


def gen_reading_lookup():
    """Tiny ceramic tap — word looked up."""
    dur = 0.10
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _exp_decay(t, 0.03)
        s = env * (
            0.5 * _sine(880, t) +
            0.3 * _sine(1760, t) * _exp_decay(t, 0.02) +
            0.2 * _sine(440, t) * _exp_decay(t, 0.04)
        )
        samples.append(s)
    _write_wav('reading_lookup.wav', samples)


def gen_onboarding_step():
    """Gentle forward step — progression without urgency."""
    dur = 0.18
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _adsr(t, 0.008, 0.03, 0.35, 0.10, dur)
        s = env * _warm_tone(392.00, t, 0.6)  # G4
        samples.append(s)
    _write_wav('onboarding_step.wav', samples)


def main():
    _ensure_dir()
    print('Generating Aelu sound effects...\n')

    gen_correct()
    gen_wrong()
    gen_navigate()
    gen_hint_reveal()
    gen_session_start()
    gen_session_complete()
    gen_level_up()
    gen_milestone()
    gen_streak_milestone()
    gen_achievement_unlock()
    gen_timer_tick()
    gen_transition_in()
    gen_transition_out()
    gen_record_pulse()
    gen_reading_lookup()
    gen_onboarding_step()

    print(f'\nDone — {16} files written to {os.path.abspath(OUTPUT_DIR)}')


if __name__ == '__main__':
    main()

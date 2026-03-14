# Root Cause Analysis — Top 3 User-Facing Defects

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Methods:** 5 Whys + Ishikawa (Fishbone) Diagram

---

## Defect 1: Early Session Abandonment

**Problem statement:** Users quit mid-session before completing all planned drills. The `session_log` shows `early_exit = 1` and `items_completed < items_planned`. Target completion rate is 85%; early abandonment directly reduces learning efficacy because the scheduler's item selection was optimized for the full session.

### 5 Whys

1. **Why do users quit mid-session?**
   Because the session feels too long or too frustrating to continue.

2. **Why does the session feel too long or too frustrating?**
   Because the user encounters a streak of items they cannot answer, or the session length exceeds their available time/energy.

3. **Why do they encounter streaks of difficult items?**
   Because the interleaving algorithm can cluster error-focus items together, and the adaptive session length may not match the user's current capacity.

4. **Why does the interleaving cluster difficult items?**
   Because error-focus items get priority boost (`ERROR_BOOST_FACTOR`) and the interleaving constraints optimize for cognitive variety (modality switching) but not for difficulty pacing. A session could have items 3-7 all be error-focus items that the user previously failed.

5. **Why isn't difficulty pacing built into the scheduler?**
   Because the scheduler was designed around SRS timing (when items are due) and error remediation (which items need work), not around emotional pacing (how the session feels). The implicit assumption was that learners would persist through difficulty, but adult learners with limited time are more likely to quit when frustration accumulates.

**Root cause:** The scheduler optimizes for learning efficiency (right items at right time) but not for session experience (difficulty curve management). There is no "frustration governor" that limits consecutive difficult items.

**Countermeasure:** Implement difficulty interleaving — after 2 consecutive incorrect answers, insert an item the user is likely to get right (mastery_stage = "solid" or "strong") as a confidence reset.

### Ishikawa (Fishbone) Diagram

```
                                    Early Session Abandonment
                                             │
    ┌──────────────┬──────────────┬──────────┼──────────┬──────────────┬──────────────┐
    │              │              │          │          │              │              │
 METHOD        MACHINE       MATERIAL   MEASUREMENT  ENVIRONMENT    MAN (User)
    │              │              │          │          │              │
    │              │              │          │          │              ├─ Low frustration
    │              │              │          │          │              │  tolerance
    │              │              │          │          │              ├─ Limited time
    │              │              │          │          │              │  (studying in
    │              │              │          │          │              │  5-min breaks)
    │              │              │          │          │              └─ Boredom with
    │              │              │          │          │                 repetitive
    │              │              │          │          │                 drill types
    │              │              │          │          │
    │              │              │          │          ├─ Studying late at night
    │              │              │          │          │  (lower cognitive capacity)
    │              │              │          │          └─ Noisy environment
    │              │              │          │             (can't do listening drills)
    │              │              │          │
    │              │              │          ├─ Session length not adaptive
    │              │              │          │  enough to user state
    │              │              │          ├─ No real-time frustration
    │              │              │          │  detection (no sentiment signal)
    │              │              │          └─ Boredom flags tracked but
    │              │              │             not acted on in real-time
    │              │              │
    │              │              ├─ Items at wrong difficulty for user
    │              │              │  (HSK level mismatch)
    │              │              ├─ Context notes missing for
    │              │              │  confusing items
    │              │              └─ Error-focus items cluster
    │              │                 (too many hard items in a row)
    │              │
    │              ├─ TTS latency causing
    │              │  wait frustration
    │              ├─ Slow page transitions
    │              │  (full reload between drills)
    │              └─ Mobile keyboard issues
    │                 (IME drill friction on iOS)
    │
    ├─ No difficulty pacing in scheduler
    ├─ Error-focus boost can dominate
    │  session (too many remediation items)
    ├─ Adaptive length algorithm needs
    │  more historical data to tune
    └─ No mid-session "easy win" injection
```

---

## Defect 2: Repeated Word Lookups

**Problem statement:** Users look up the same word 5+ times across different reading/listening sessions. The `vocab_encounter` table with `looked_up = 1` shows items with high repeat lookup counts. This indicates a failure in the retention pipeline — the user is encountering the word in context but not learning it.

### 5 Whys

1. **Why do users look up the same word repeatedly?**
   Because they don't remember its meaning despite having seen it before.

2. **Why don't they remember it despite prior exposure?**
   Because passive exposure (reading a word in a graded passage) doesn't create strong enough memory traces for active recall. The lookup happens, the user understands the passage in the moment, and then forgets.

3. **Why doesn't passive exposure create strong memory traces?**
   Because the lookup-to-drill pipeline has a delay. The vocab encounter is logged, the cleanup loop eventually boosts the word's priority in the scheduler, but the next drill session may not happen for days. The spacing is too long between "saw it in context" and "actively recalled it in a drill."

4. **Why is there a delay between lookup and drill?**
   Because the cleanup loop runs on a scheduler cadence (not immediately), and the boosted priority competes with other due items. A word looked up on Monday might not appear in a drill until Wednesday or Thursday, by which point the contextual memory has faded.

5. **Why doesn't the system drill looked-up words immediately?**
   Because the session planning happens at session start, not during exposure activities. The graded reader and media shelf are separate flows from the drill session. There is no mechanism to inject a "just-looked-up" word into the current or next session in real time.

**Root cause:** The exposure-to-drill pipeline has a timing gap. Passive encounters are logged but not immediately converted to active recall opportunities. The forgetting curve is steepest in the first hours after exposure, but the remediation (drill) may come days later.

**Countermeasure:** After a lookup in the graded reader or listening module, offer an immediate mini-drill (1-2 items) on the looked-up word while context is fresh. Alternatively, guarantee that any word looked up today appears in tomorrow's session.

### Ishikawa (Fishbone) Diagram

```
                                    Repeated Word Lookups (5+)
                                             │
    ┌──────────────┬──────────────┬──────────┼──────────┬──────────────┬──────────────┐
    │              │              │          │          │              │              │
 METHOD        MACHINE       MATERIAL   MEASUREMENT  ENVIRONMENT    MAN (User)
    │              │              │          │          │              │
    │              │              │          │          │              ├─ Doesn't use
    │              │              │          │          │              │  drill sessions
    │              │              │          │          │              │  frequently enough
    │              │              │          │          │              ├─ Reads above
    │              │              │          │          │              │  current level
    │              │              │          │          │              └─ Passive reading
    │              │              │          │          │                 habit (reads
    │              │              │          │          │                 for gist, not
    │              │              │          │          │                 retention)
    │              │              │          │          │
    │              │              │          │          ├─ Long gaps between
    │              │              │          │          │  study sessions
    │              │              │          │          └─ Reading without
    │              │              │          │             audio (missing
    │              │              │          │             phonological trace)
    │              │              │          │
    │              │              │          ├─ Lookup count tracked but
    │              │              │          │  not surfaced to user
    │              │              │          ├─ No "this is your 5th
    │              │              │          │  lookup" alert
    │              │              │          └─ No correlation between
    │              │              │             lookup count and drill
    │              │              │             performance measured
    │              │              │
    │              │              ├─ Context note may be missing
    │              │              │  or unhelpful for this word
    │              │              ├─ Word may have multiple meanings
    │              │              │  (looked up different sense each time)
    │              │              └─ No mnemonic or memory hook
    │              │                 provided with lookup
    │              │
    │              ├─ Cleanup loop cadence too slow
    │              │  (runs on scheduler, not real-time)
    │              ├─ No instant mini-drill after lookup
    │              └─ Reader and drill engine are
    │                 separate flows (no real-time bridge)
    │
    ├─ Exposure-to-drill delay too long
    │  (forgetting curve steepest in first hours)
    ├─ Cleanup loop boosts priority but
    │  doesn't guarantee next-session inclusion
    ├─ No desirable difficulty applied at
    │  lookup time (answer is just shown)
    └─ Reader flow optimizes for comprehension,
       not retention
```

---

## Defect 3: Tone Accuracy Plateau

**Problem statement:** Tone accuracy improves rapidly in the first 2-4 weeks of study, then plateaus at 60-70% accuracy despite continued practice. The `progress` table shows `tone_correct / tone_attempts` stabilizing, and `error_log` entries with `error_type = 'tone'` continue at a steady rate. Tones are the single largest error category (~38% of all errors per Pareto analysis).

### 5 Whys

1. **Why does tone accuracy stop improving after initial gains?**
   Because the easy tone distinctions (1 vs 4, high-flat vs sharp-falling) are learned quickly, but the hard ones (2 vs 3, rising vs dipping) resist improvement through repetition alone.

2. **Why don't tone 2 vs 3 distinctions improve with more practice?**
   Because the perceptual boundary between rising and dipping tones requires a qualitative shift in listening strategy, not just more exposure. The learner needs to hear the initial dip at the start of tone 3, but the drill format (identify the tone) doesn't teach them what to listen for.

3. **Why doesn't the drill format teach the perceptual cue?**
   Because current tone drills are assessment-oriented (test whether you know) rather than training-oriented (teach you the cue). The drill says "wrong, it was tone 3" but doesn't say "listen for the dip at the beginning" in a way that reshapes perception.

4. **Why isn't there a perceptual training component?**
   Because the system was designed for recall and recognition, not for auditory perceptual learning. Tone perception training requires specific pedagogical techniques: minimal pair discrimination, slowed speech, exaggerated contours, and systematic focus on the confusable pair — not just repeated exposure to full-speed speech.

5. **Why wasn't perceptual training prioritized?**
   Because the initial architecture focused on vocabulary and grammar (the broader curriculum), and tones were treated as a classification task (which tone is this?) rather than a perceptual skill (can you hear the difference between these two tones?). The minimal_pair drill exists but isn't specifically tuned for tone 2-3 discrimination with graduated difficulty.

**Root cause:** Tone drilling treats tone identification as a knowledge problem (which tone is this word?) when for tones 2/3 it is a perception problem (can you hear the difference?). The drill format doesn't train the underlying perceptual skill.

**Countermeasure:**
1. Create a dedicated tone 2/3 discrimination training sequence using minimal pairs at graduated speeds (slow → normal → fast)
2. Add tone contour visualization feedback: show the pitch curve of the correct tone and highlight where the user's perception diverged
3. Increase minimal_pair drill frequency specifically for the learner's weakest tone pair (data from `error_log` where `error_type = 'tone'` and notes contain tone numbers)

### Ishikawa (Fishbone) Diagram

```
                                    Tone Accuracy Plateau (~65%)
                                             │
    ┌──────────────┬──────────────┬──────────┼──────────┬──────────────┬──────────────┐
    │              │              │          │          │              │              │
 METHOD        MACHINE       MATERIAL   MEASUREMENT  ENVIRONMENT    MAN (User)
    │              │              │          │          │              │
    │              │              │          │          │              ├─ L1 is non-tonal
    │              │              │          │          │              │  (English has pitch
    │              │              │          │          │              │  for intonation,
    │              │              │          │          │              │  not lexical meaning)
    │              │              │          │          │              ├─ Low motivation to
    │              │              │          │          │              │  focus on tones
    │              │              │          │          │              │  ("people understand
    │              │              │          │          │              │  me anyway")
    │              │              │          │          │              └─ Age-related
    │              │              │          │          │                 perceptual
    │              │              │          │          │                 difficulty
    │              │              │          │          │
    │              │              │          │          ├─ Studying in noisy
    │              │              │          │          │  environment (can't
    │              │              │          │          │  hear subtle pitch
    │              │              │          │          │  differences)
    │              │              │          │          └─ No access to native
    │              │              │          │             speaker conversation
    │              │              │          │             (production practice)
    │              │              │          │
    │              │              │          ├─ Tone accuracy measured at
    │              │              │          │  word level, not minimal
    │              │              │          │  pair discrimination level
    │              │              │          ├─ No per-tone-pair accuracy
    │              │              │          │  breakdown (2-3 vs 1-4 etc.)
    │              │              │          └─ Speaking drill uses self-report
    │              │              │             (no objective tone measurement)
    │              │              │
    │              │              ├─ TTS voice may not have clear
    │              │              │  enough tone distinctions
    │              │              ├─ Tone sandhi rules add
    │              │              │  confusion (3-3 → 2-3)
    │              │              ├─ No slow-speech training audio
    │              │              │  for difficult pairs
    │              │              └─ Minimal pair pool may be too
    │              │                 small for adequate training
    │              │
    │              ├─ No F0 contour analysis
    │              │  (parselmouth deferred)
    │              ├─ Browser TTS quality
    │              │  varies by device/browser
    │              └─ No pitch visualization
    │                 for learner
    │
    ├─ Drills are assessment-mode not
    │  training-mode for tones
    ├─ No graduated difficulty for
    │  tone perception
    ├─ Tone drill treats all pairs
    │  equally (1-2-3-4) instead of
    │  focusing on confusable pairs
    ├─ No explicit perceptual training
    │  (what to listen for)
    └─ Tone sandhi drill exists but
       doesn't connect to base tone
       perception training
```

---

## 4. Summary of Root Causes and Countermeasures

| Defect | Root Cause | Countermeasure | Priority | Effort |
|--------|-----------|---------------|----------|--------|
| Early session abandonment | No frustration governor in scheduler | Difficulty pacing: insert easy items after consecutive failures | High | Medium |
| Repeated word lookups | Exposure-to-drill timing gap too long | Immediate mini-drill after lookup; next-session guarantee | High | Medium |
| Tone accuracy plateau | Drills assess tone knowledge but don't train tone perception | Dedicated 2/3 discrimination training sequence with graduated difficulty | Medium | High |

### Dependency Analysis
- The abandonment fix (difficulty pacing) can be implemented independently in `scheduler.py`
- The lookup-to-drill bridge requires changes to both the reader flow and the session planner
- The tone perception training requires new drill content and potentially new drill types

### Validation Metrics
| Defect | Metric | Current | Target | Query |
|--------|--------|---------|--------|-------|
| Early abandonment | Session completion rate (items_completed / items_planned) | ~70% (estimated) | 85% | `SELECT AVG(1.0 * items_completed / NULLIF(items_planned, 0)) FROM session_log WHERE user_id = ?` |
| Repeated lookups | % of looked-up words with 5+ lookups | Unknown | < 10% | `SELECT COUNT(*) FROM (SELECT hanzi, COUNT(*) c FROM vocab_encounter WHERE looked_up = 1 AND user_id = ? GROUP BY hanzi HAVING c >= 5)` |
| Tone plateau | Tone accuracy trend (slope over 30 days) | ~0 (flat) | > 0.5%/week improvement | Weekly `tone_correct / tone_attempts` from `progress` table |

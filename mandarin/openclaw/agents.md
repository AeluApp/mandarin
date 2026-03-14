# OpenClaw Agent Definitions

## Study Reminder Agent

**Trigger:** Scheduled at 8am, 12pm, 6pm user's timezone
**Behavior:**
- Read due items via `get_due_items(user_id)`
- If due items > 0, message user with count, struggling items, estimated time
- User replies with minutes → call `queue_session(user_id, minutes)` → confirm drill count
- User replies "later" or "skip" → acknowledge, adjust next reminder timing
- Respects `learner_profile.streak_reminders` flag
- Tone: calm, supportive, never guilt-tripping

**Example interaction:**
```
Bot: You have 15 items due for review (~8 minutes). 你的 (nǐ de) and 因为 (yīnwèi) need attention. Ready?
User: 5 minutes
Bot: Got it — 20 drills queued for a focused 5-minute session. Let's go.
```

## Review Queue Agent

**Trigger:** When pending items exist for >1 hour
**Behavior:**
- Check review queue via `get_review_queue_summary()`
- If pending items, message admin: "5 new items for HSK 3 complements. Review?"
- On "yes": send items one-by-one with hanzi/pinyin/english + quality scores
- Admin replies approve/reject inline → call `approve_review_item()` or `reject_review_item()`
- Batch review (>10 items): link to admin panel instead
- Debounce: only fire when items pending >1 hour

**Example interaction:**
```
Bot: 5 new items pending review (HSK 3 complements, oldest: 2h ago). Review inline?
Admin: yes
Bot: 1/5: 对...来说 (duì...lái shuō) "for/to [someone]" — quality: 0.82. Approve?
Admin: approve
Bot: ✓ Approved. 2/5: 从...到 (cóng...dào) "from...to" — quality: 0.91. Approve?
```

## Audit Briefing Agent

**Trigger:** After weekly audit completion
**Behavior:**
- Read latest audit via `get_latest_audit_summary()`
- Message: "Audit complete. Grade: [B+]. 2 findings need attention: [titles]. Details?"
- On request, expand each finding with analysis + recommendation
- Include trend context: "Up from B last week"

**Example interaction:**
```
Bot: Weekly audit complete. Grade: B+ (83.2). 2 findings need attention: "Audio coherence failure rate >5%", "Prompt regression in drill_generation". Details?
Admin: details on prompt regression
Bot: drill_generation success rate dropped from 94% to 78% over the past 7 days. Baseline latency 850ms → current 1,200ms. Likely cause: model update. Recommendation: check Ollama model version and review recent prompt changes.
```

## Tutor Prep Agent

**Trigger:** Manual — user says "prep for italki" or "tutor briefing"
**Behavior:**
- Call `get_learner_briefing(user_id, focus="tutor_prep")`
- Format briefing for easy sharing with tutor:
  - Top error patterns (last 7 days)
  - Grammar points with lowest accuracy
  - Recommended focus areas
  - Sample sentences for practice
- Copy-pasteable format

**Example output:**
```
📋 iTalki Prep — March 12, 2026

Top errors this week:
• Tone errors on 4th tone words (了, 去, 看) — 6 occurrences
• 把 construction misuse — 4 occurrences

Grammar gaps (lowest accuracy):
• 把 sentences (HSK 3): 45% accuracy
• 了 completion aspect (HSK 2): 52% accuracy

Suggested focus:
Practice 把 with physical objects: 把书放在桌子上, 把门关上
Review 了 with completed actions vs. change of state
```

# Aging WIP Policy

> Last updated: 2026-03-10

## Definition

An item is "aging" when it has been In Progress for longer than 2x the average cycle time for its class of service.

**Current thresholds (based on flow metrics):**

| Class | Avg Cycle Time | Aging Threshold (2x) |
|-------|---------------|---------------------|
| Expedite | <1 day | 1 day |
| Standard | 4 days | 8 days |
| Intangible | 2 days | 4 days |

These thresholds are recalculated monthly as more data accumulates.

---

## Weekly Aging WIP Check

Performed every Monday during the daily standup (or immediately after replenishment).

### Process

1. List all items currently In Progress.
2. For each item, compute: `Days In Progress = today - Date Started`.
3. Compare to the aging threshold for the item's class.
4. If `Days In Progress > Aging Threshold`, the item is aging. Take action (see below).

### Tracking Table

| Item ID | Title | Class | Started | Days In Progress | Threshold | Status | Action |
|---------|-------|-------|---------|-----------------|-----------|--------|--------|
| F-006 | PMF validation: onboard 10 beta users | Standard | 2026-03-08 | 2 | 8 | Active | — |
| D-003 | Dead code removal pass | Intangible | 2026-03-07 | 3 | 4 | Active | — |
| X-001 | Reddit content marketing post | Standard | 2026-03-09 | 1 | 8 | Active | — |

*None currently aging. Table updated weekly.*

---

## Actions for Aging Items

When an item exceeds the aging threshold, it must be triaged. There are exactly three possible diagnoses:

### 1. Blocked

**Symptom:** You haven't worked on it because something external is preventing progress.

**Examples:**
- Waiting for Apple App Review response
- Waiting for a dependency to fix a bug
- Waiting for user feedback before proceeding
- Unclear requirements (for a solo founder, this means you haven't thought it through)

**Action:**
- Document the blocker on the card.
- Can the blocker be removed? If yes, remove it and continue.
- Can the blocker be worked around? If yes, document the workaround and continue.
- Is the blocker indefinite? Move the item back to Ready with a note. Don't let it consume a WIP slot while blocked.

### 2. Too Large

**Symptom:** You've been working on it, making progress, but it keeps revealing more work. The scope grew after starting.

**Examples:**
- "Mobile Capacitor phases A-F" was originally one item but became 6 sub-phases
- A "simple" feature requires database migration, API changes, UI changes, and test updates
- An experiment requires infrastructure changes before the experiment itself can run

**Action:**
- Split the item into 2-3 smaller items, each independently deployable.
- Move the remaining sub-items to Ready.
- Keep working on the smallest deployable piece.
- Rule of thumb: if you can't describe what "done" looks like in one sentence, the item is too large.

### 3. Abandoned

**Symptom:** You stopped caring about it. It's not blocked, it's not too large — you just moved on to something more interesting or important.

**Examples:**
- A tech debt item that seemed important 2 weeks ago but doesn't matter now
- An experiment whose hypothesis changed before you ran it
- A feature idea that cooled off

**Action:**
- Be honest. Move it back to Backlog with a note: "Abandoned on [date] — [reason]."
- Or remove it from the board entirely if it's truly irrelevant.
- Do NOT leave it In Progress to "get back to it someday." That's a WIP slot wasted on denial.

---

## Escalation

If the same item ages twice (exceeds threshold, gets triaged, continues to exceed threshold after the action):

1. **Question whether it belongs on the board at all.** Maybe this isn't work you're going to do.
2. **If it does belong:** Is it the wrong class? Should it be Intangible instead of Standard? Would a longer SLE be more honest?
3. **If it doesn't belong:** Remove it. Write a one-line note in the spiral log about why it was removed.

---

## Historical Aging Events

Track past aging incidents to identify patterns.

| Date | Item ID | Title | Days Aged | Diagnosis | Resolution |
|------|---------|-------|-----------|-----------|------------|
| — | — | *(No aging events yet — system is new)* | — | — | — |

**Patterns to watch for:**
- Same swimlane aging repeatedly → systemic issue with that type of work
- Same item aging repeatedly → that item should be killed or radically rescoped
- Multiple items aging simultaneously → WIP limits may be too high, or focus is fragmented

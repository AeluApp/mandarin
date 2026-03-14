# Aelu Pair Programming & AI-Assisted Development Guide

**Last Updated:** 2026-03-10

---

## Context

Aelu's primary development model is human (Jason) + AI (Claude Code). This is a variation on pair programming where one partner has deep project context and product judgment, and the other has broad technical knowledge and tireless execution capacity. The principles of pair programming apply, but the roles and failure modes are different.

---

## Driver/Navigator Roles Adapted for Human+AI

### Traditional Pair Programming
- **Driver:** Writes the code. Focuses on syntax, implementation details, the current line.
- **Navigator:** Reviews each line as it's written. Thinks about the bigger picture, edge cases, architecture.

### Human+AI Adaptation

| Role | Who | Responsibilities |
|---|---|---|
| **Navigator** | Jason (human) | Sets direction. Defines what to build and why. Makes product decisions. Reviews output for correctness, tone (chinese_writing_standard.md), and alignment with learner experience. Catches when the AI is solving the wrong problem. |
| **Driver** | Claude Code (AI) | Implements the solution. Writes code, tests, and migrations. Reads existing code to maintain consistency. Follows project conventions (SQLite patterns, Flask route structure, test naming). |

**Key difference from traditional pairing:** The navigator does not need to understand every line in real time. The navigator sets intent and reviews output. The driver proposes approaches and the navigator approves or redirects.

### When to Swap Roles

The human becomes the driver when:
- Writing Chinese content (context notes, dialogue scenarios) -- Claude Code cannot judge native register quality
- Making product decisions that require user empathy (what should the onboarding feel like?)
- Debugging production issues by reading `session_trace.jsonl` and `drill_errors.log` -- the human has production access

The AI becomes the navigator when:
- Reviewing human-written code for bugs, edge cases, or convention violations
- Suggesting test cases the human hasn't considered
- Identifying architectural implications of a change ("this will also affect `scheduler.py` and `personalization.py`")

---

## When to Plan vs. Implement Directly

### Implement Directly (No planning phase needed)

| Scenario | Example |
|---|---|
| Bug fix with clear reproduction steps | "drill_errors.log shows KeyError in tone_grading.py for items without pinyin" |
| Copy/label change | "Update the placement test instruction text" |
| Adding a test for existing behavior | "Add a test for the case where vocab_encounter has looked_up=None" |
| Configuration change | "Add a new ruff rule to pyproject.toml" |
| 1-2 point stories with clear acceptance criteria | PB-005 session progress bar |

### Plan First (Spend 5-15 minutes on approach before coding)

| Scenario | Why Planning Matters |
|---|---|
| Schema changes | SQLite can't ALTER CHECK constraints. Need to plan the migration path. Will it require table recreation? |
| Algorithm changes (scheduler, placement, tone_grading) | Wrong algorithm = wrong learning outcomes. Define expected behavior with examples before coding. |
| Cross-module changes (touching 5+ files) | Understand the dependency chain first. Which modules call which? What tests exist? |
| New external integration (email, Stripe, Apple) | Identify API constraints, error handling, retry logic before writing code. |
| Stories estimated at 5+ points | The acceptance criteria define what, but the implementation path needs agreement on how. |

### Planning Format

For items that need planning, use this structure:

```markdown
## Plan: PB-XXX [Title]

**Goal:** [One sentence -- what will be true when this is done]

**Approach:**
1. [Step 1 -- which file, what change]
2. [Step 2]
3. [Step 3]

**Schema changes:** [None / describe migration]

**Tests to write:**
- [test name and what it verifies]

**Risks:**
- [What could go wrong and how to mitigate]

**Decision:** Approved / Needs revision
```

---

## Context Management

### The MEMORY.md Pattern

`~/.claude/projects/-Users-jasongerson/memory/MEMORY.md` is the persistent context file that carries knowledge across Claude Code sessions. It is the single source of truth for:

- Project location, environment, dependencies
- Architecture decisions and constraints
- Known debugging patterns (CSP issues, SQLite limitations, Capacitor quirks)
- Coding conventions and style preferences
- Active priorities and deferred work

### Rules for MEMORY.md

1. **Update after every significant discovery.** If you learn that SQLite datetime('now') is UTC and Python must use `datetime.now(timezone.utc)` to match, add it immediately. Don't rely on remembering.

2. **Delete stale entries.** If a deferred feature (e.g., parselmouth) is no longer relevant, remove it. Stale context is worse than no context -- it misleads future sessions.

3. **Keep it scannable.** Use bullet points, not paragraphs. Every entry should be understood in under 5 seconds.

4. **Include failure patterns.** "CSP `upgrade-insecure-requests` breaks ALL sub-resource loading on HTTP localhost" is more valuable than "CSP headers are configured in security.py."

5. **Never duplicate documentation.** MEMORY.md points to docs, it doesn't reproduce them. "See `chinese_writing_standard.md` for writing guidelines" -- don't paste the standard into MEMORY.md.

### Session Start Protocol

At the start of every Claude Code session:

1. Read `MEMORY.md` (automatic -- it's in the project config)
2. Read `~/mandarin/data/drill_errors.log` (tail recent entries)
3. Read `~/mandarin/data/session_trace.jsonl` (tail recent entries)
4. If errors are found, diagnose and fix before starting planned work

This protocol catches production issues before they compound.

---

## Code Review Expectations

### What the Human Reviews (Navigator hat)

| Focus Area | What to Check |
|---|---|
| **Correctness** | Does this actually solve the problem stated in the user story? |
| **User experience** | Will this confuse a learner? Is the flow natural? |
| **Chinese content quality** | Does generated Chinese follow `chinese_writing_standard.md`? No textbook smell? |
| **Data integrity** | Are SQLite queries safe? LEFT JOIN None handling? UTC timestamps? |
| **Security** | Any new auth bypasses? Secrets in code? Missing rate limiting? |
| **Scope** | Did the implementation stay within the acceptance criteria, or did it grow? |

### What the AI Reviews (When asked to review human code)

| Focus Area | What to Check |
|---|---|
| **Edge cases** | What happens with empty input? None values? Concurrent access? |
| **Convention consistency** | Does this match existing patterns in the codebase? |
| **Test coverage** | Are there tests for the new behavior? Do they cover edge cases? |
| **Performance** | Any N+1 queries? Unbounded loops? Missing indexes? |
| **Cross-platform** | Will this work on web, iOS (Capacitor), and macOS? |
| **Backward compatibility** | Does this break existing API contracts or database expectations? |

### Review Checklist (for every code change)

- [ ] Tests pass locally: `pytest -q`
- [ ] Lint clean: `ruff check mandarin/`
- [ ] No security regressions: `bandit -r mandarin/ -ll -q`
- [ ] Changes match the acceptance criteria (not more, not less)
- [ ] If schema changed: `BUILD_STATE.md` updated, migration path documented
- [ ] If user-facing: tested on web + iOS simulator + macOS
- [ ] If content changed: reviewed against `chinese_writing_standard.md`

---

## Knowledge Transfer Patterns

### From Human to AI (at session start)

Effective:
- "Today we're working on PB-012. The acceptance criteria are in product-backlog.md. The relevant code is in `scheduler.py` and `web/routes.py`. The key constraint is that passage difficulty must adjust based on lookup_rate from `vocab_encounter`."

Ineffective:
- "Let's work on the reading stuff." (Too vague -- which aspect? Which files?)
- Pasting 500 lines of code without context. (State the problem first, then the code.)

### From AI to Human (during work)

Effective:
- "I'm modifying `scheduler.py` lines 142-160. The change affects how `next_review` is calculated for boosted items. Here's the before/after logic and why."

Ineffective:
- Making 15 file changes without explaining the approach. (The navigator needs to understand the strategy, not just the diff.)

### Between Sessions (via MEMORY.md)

At session end, update MEMORY.md with:
- Any new debugging lessons learned
- Any new codebase conventions established
- Any deferred work or open questions
- Any schema or configuration changes made

---

## Effective Session Structure

### Short Session (30 minutes -- bug fix or small task)

```
0:00 - Read MEMORY.md, check drill_errors.log (automatic)
0:02 - State the task: "Fix KeyError in tone_grading.py when item has no pinyin"
0:03 - Locate the bug, write the fix
0:10 - Write/update test
0:15 - Run test suite, verify fix
0:20 - Deploy if applicable
0:25 - Update MEMORY.md if a new pattern was learned
0:30 - Done
```

### Medium Session (1-2 hours -- 3-5 point story)

```
0:00  - Read MEMORY.md, check logs
0:05  - Review the story's acceptance criteria
0:10  - Brief planning discussion (which files, which approach)
0:15  - Implementation begins (AI drives, human navigates)
0:45  - First checkpoint: does the implementation match the acceptance criteria?
1:00  - Write tests
1:15  - Run full test suite
1:20  - Manual testing (web + iOS if user-facing)
1:30  - Deploy
1:45  - Update MEMORY.md
2:00  - Done
```

### Long Session (3+ hours -- 8 point story)

```
0:00  - Read MEMORY.md, check logs
0:10  - Detailed planning: approach, risks, test strategy
0:30  - Implementation phase 1 (core logic)
1:00  - Checkpoint: run tests, verify core logic works
1:15  - Implementation phase 2 (routes, UI, integration)
2:00  - Checkpoint: run tests, manual testing
2:15  - Implementation phase 3 (edge cases, error handling)
2:45  - Full test suite run
3:00  - Cross-platform testing
3:15  - Deploy
3:30  - Monitor crash_log, update MEMORY.md
```

**Rule:** Take a 5-minute break every 90 minutes. Context fatigue affects both the human (decision quality degrades) and the AI (long conversations accumulate context that may conflict).

---

## Anti-Patterns in Human+AI Pairing

**Rubber-stamping AI output.** If the human approves every change without reading it, the navigator role is abandoned. Review at least the test names and key logic changes.

**Over-specifying implementation.** Telling the AI exactly which lines to write defeats the purpose of pairing. Specify intent and constraints; let the AI propose implementation.

**Under-specifying intent.** "Make this better" is not actionable. "The lookup_rate calculation should handle passages with 0 words without raising ZeroDivisionError" is actionable.

**Ignoring AI suggestions.** If the AI identifies a potential None-handling issue in a LEFT JOIN result, investigate it. The AI has read the codebase; it may see things the human has normalized.

**Session drift.** Starting with PB-012 and ending up refactoring 3 unrelated modules. Stick to the sprint backlog item. Note discoveries for future work and move on.

**Skipping the context transfer.** Starting a new session without reading MEMORY.md or checking error logs. Every session inherits context from the last one -- but only if MEMORY.md is maintained.

**Trusting without verifying.** The AI can write plausible code that is subtly wrong (especially with SQLite edge cases or timezone handling). Run the tests. Check the data. Verify.

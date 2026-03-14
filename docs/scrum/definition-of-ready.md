# Aelu Definition of Ready

**Last Updated:** 2026-03-10

A Product Backlog item is "Ready" to be pulled into a sprint when ALL of the following are true. Items that are not Ready stay in the backlog and cannot be committed to in Sprint Planning.

---

## Checklist

### 1. User Story Written with Persona
The item is expressed as: "As a [persona], I want [capability] so that [benefit]."

Valid personas for Aelu:
- **Learner** — someone studying Mandarin (the primary user)
- **New user** — someone who just signed up and hasn't completed onboarding
- **Teacher** — a Mandarin teacher using classroom features
- **Product owner** — Jason, wearing the PO hat (for analytics, experiments, infrastructure)
- **Solo developer** — Jason, wearing the engineering hat (for tech debt, tooling)

The persona must be specific enough that the story's success criteria are clear.

### 2. Acceptance Criteria Defined (Given/When/Then)
At least 2 acceptance criteria written in Given/When/Then format. Each criterion must be:
- **Testable** — a human or automated test can verify it
- **Specific** — no ambiguous words like "fast," "easy," or "intuitive" without measurable thresholds
- **Independent** — each criterion can be verified in isolation

Bad: "Given the user opens the app, When it loads, Then it looks nice."
Good: "Given the user opens the app, When the dashboard loads, Then the response time is under 500ms and all session data is visible."

### 3. Story Points Estimated
The item has a story point estimate using the Fibonacci scale: 1, 2, 3, 5, 8, 13.

Guidelines for a solo developer:
- **1 point** — Configuration change, copy update, trivial bug fix. Less than 2 hours.
- **2 points** — Small feature or bug fix with clear scope. Half a day.
- **3 points** — Moderate feature touching 2-3 modules. 1 day.
- **5 points** — Significant feature requiring new tests and possibly schema changes. 2-3 days.
- **8 points** — Large feature spanning multiple modules, requiring design decisions. 3-5 days.
- **13 points** — Epic-sized item that should probably be split. Full sprint.

Items over 13 points MUST be split before they are Ready.

### 4. Dependencies Identified and Unblocked
All dependencies are listed and resolved:
- **Technical dependencies** — Does this require a schema migration? A new package? A Fly.io config change?
- **Content dependencies** — Does this require new Chinese text, context notes, or dialogue scripts?
- **External dependencies** — Does this require a Stripe configuration, Apple review, or third-party API?
- **Data dependencies** — Does this require user data that doesn't exist yet (e.g., NPS responses from real users)?

If a dependency is unresolved, the item is NOT Ready.

### 5. Technical Approach Agreed (If >5 Points)
For items estimated at 8 or 13 points, a brief technical approach is documented:
- Which modules/files will be modified?
- Will a schema migration be needed?
- Are there performance implications?
- What's the rollback plan if something goes wrong?

This doesn't need to be a design doc. A 3-5 bullet list in the backlog item is sufficient.

### 6. Test Strategy Identified
Before pulling an item, know how it will be tested:
- **Unit tests** — which functions/methods will have new tests?
- **Integration tests** — does this touch API routes that need `create_app` + `test_client` tests?
- **Manual testing** — what manual verification is needed post-deploy?
- **Property-based tests** — for algorithmic changes (SRS intervals, scheduling), consider hypothesis tests

The test strategy doesn't need to be exhaustive, but "I'll figure out testing later" means the item is not Ready.

### 7. No Open Questions
There are no unresolved questions about:
- What the feature should do (scope)
- Who it's for (persona)
- How it should behave in edge cases
- Whether it conflicts with existing behavior

If a question exists, answer it before marking Ready. Write the answer in the acceptance criteria.

---

## Quick Reference

| # | Criterion | One-Line Check |
|---|---|---|
| 1 | User story | Does it say who, what, and why? |
| 2 | Acceptance criteria | Can I write a test for each criterion? |
| 3 | Story points | Is the estimate on the Fibonacci scale? |
| 4 | Dependencies | Is anything blocking this right now? |
| 5 | Technical approach | For big items: do I know how I'll build it? |
| 6 | Test strategy | Do I know how I'll verify it works? |
| 7 | No open questions | Can I start coding right now without asking anyone anything? |

If any answer is "no," the item goes back to backlog refinement.

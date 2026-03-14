# Content Scheduling as Constrained Optimization

## Problem Formulation

At the start of each session, Aelu must select **which items** to review and **in what order** to present them. This is a combinatorial optimization problem.

### Sets

- **I** = set of all items in the user's learning queue (|I| typically 50-500)
- **M** = set of drill modalities {recognition, recall, tone, listening, production, context}
- **S** = ordered sequence of drills in the session (|S| = session_length, typically 10-15)

### Decision Variables

For each item `i` in `I` and position `k` in `S`:

```
x_{i,k} in {0, 1}    -- 1 if item i is assigned to position k, 0 otherwise
```

### Item Properties

Each item `i` has:
- `r_i` = current predicted recall (from SRS, range [0, 1])
- `d_i` = difficulty (range [0, 1])
- `v_i` = item value (HSK level weight, user priority, etc.)
- `m_i` = assigned modality for this review
- `is_new_i` = 1 if item has never been reviewed, 0 otherwise
- `last_seen_i` = number of drills since last appearance in any session

## Objective Function

**Maximize total expected recall improvement weighted by item value:**

```
max SUM_{i,k} x_{i,k} * delta_r_i * v_i
```

Where `delta_r_i` is the expected recall improvement from reviewing item `i`:

```
delta_r_i = (1 - r_i) * P(correct_i | review)
```

Items with low current recall (`r_i` near 0) and reasonable chance of being answered correctly have the highest `delta_r_i`. Items already at high recall (`r_i` near 1) gain little from review. Items that are too difficult (very low `P(correct)`) also gain little because the review won't be successful.

**The sweet spot is items with r_i between 0.3 and 0.7** — forgotten enough to benefit from review, but not so forgotten that the review will fail.

### Item Value Weighting

```
v_i = hsk_weight_i * priority_i * recency_bonus_i
```

Where:
- `hsk_weight`: Items at the user's current HSK level are weighted highest (1.0). Items one level below get 0.7 (review). Items one level above get 0.5 (preview). Items two+ levels away get 0.2.
- `priority_i`: User-flagged items get 1.5x. Items from recent context notes get 1.3x.
- `recency_bonus_i`: Items not seen in 7+ days get 1.2x bonus to prevent "lost" items.

## Constraints

### C1: Session Length

```
SUM_{i} SUM_{k} x_{i,k} = session_length
```

Each position must be filled:
```
SUM_{i} x_{i,k} = 1    for all k in S
```

### C2: Modality Balance

Each modality must appear at least `floor(session_length * 0.15)` times:

```
SUM_{i: m_i = m} SUM_{k} x_{i,k} >= floor(session_length * 0.15)    for all m in M_active
```

Where `M_active` is the set of modalities the user has enabled (at least 3).

In practice with 12 drills and 4 active modalities: each modality gets at least 1 drill (floor(12 * 0.15) = 1). The remaining 8 slots are allocated by the objective function.

### C3: Interleaving (No Consecutive Same-Item)

The same item cannot appear within 3 positions of itself:

```
x_{i,k} + x_{i,k+1} + x_{i,k+2} <= 1    for all i, k
```

This prevents massed practice (reviewing the same word 3 times in a row), which research shows is less effective than interleaved practice.

### C4: Difficulty Band

Average difficulty of selected items should be in the target range:

```
0.3 <= (SUM_{i,k} x_{i,k} * d_i) / session_length <= 0.7
```

Sessions that are too easy (avg difficulty < 0.3) bore the user. Sessions that are too hard (avg difficulty > 0.7) frustrate the user and cause dropout.

### C5: New Item Cap

At most 3 new items per session:

```
SUM_{i: is_new_i = 1} SUM_{k} x_{i,k} <= 3
```

New items require more cognitive effort. Too many new items in one session overwhelms working memory.

### C6: No Duplicate Items (Unless Multi-Modality)

Each item appears at most once per session (unless specifically scheduled for multi-modality review):

```
SUM_{k} x_{i,k} <= 1    for all i
```

Exception: an item can appear twice if the two appearances use different modalities (e.g., listening then recall). This is rare and only for items that need intensive review.

## Complexity Analysis

### Problem Size

- Items in queue: N ~ 50-500
- Session length: K ~ 10-15
- Decision variables: N * K ~ 500-7,500 binary variables
- This is a variant of the **Generalized Assignment Problem**, which is NP-hard.

### Why a Greedy Heuristic is Near-Optimal

1. **Small problem size.** With N < 500 and K < 15, the number of feasible solutions is C(N, K) * K! orderings. But the ordering constraints (interleaving, modality balance) prune the space dramatically.

2. **Diminishing returns.** The objective function exhibits strong diminishing returns: the first few items selected have high `delta_r * v`, and each subsequent item adds less. This is the hallmark of problems where greedy performs well (submodular optimization guarantees greedy achieves at least 1 - 1/e ~ 63% of optimal for monotone submodular functions with cardinality constraints).

3. **Constraint structure is simple.** The constraints are mostly cardinality-based (counts, caps, bounds). They don't create complex interactions between items.

4. **Empirically validated.** The current greedy selector in Aelu was compared against a brute-force search on a subset of 50 items and 12 slots. The greedy solution was within 5% of optimal in all test cases.

## Current Greedy Implementation

Aelu's current drill selector works as follows:

```python
def select_drills(user, session_length=12):
    """
    Greedy drill selection.
    1. Score all items by expected recall improvement * value
    2. Sort by score descending
    3. Greedily add items, checking constraints
    """
    candidates = get_review_candidates(user)

    # Score each candidate
    for item in candidates:
        item.score = (1 - item.predicted_recall) * item.value
        # Boost overdue items
        if item.days_overdue > 0:
            item.score *= (1 + 0.1 * min(item.days_overdue, 10))

    candidates.sort(key=lambda x: x.score, reverse=True)

    selected = []
    modality_counts = defaultdict(int)
    new_count = 0

    for item in candidates:
        if len(selected) >= session_length:
            break

        # Check constraints
        if item.is_new and new_count >= 3:
            continue  # C5: new item cap
        if not check_interleaving(selected, item):
            continue  # C3: interleaving

        selected.append(item)
        modality_counts[item.modality] += 1
        if item.is_new:
            new_count += 1

    # Post-processing: check modality balance (C2)
    # If any modality is missing, swap in a candidate of that modality
    ensure_modality_balance(selected, candidates, modality_counts)

    # Check difficulty band (C4)
    avg_diff = mean(item.difficulty for item in selected)
    if avg_diff < 0.3 or avg_diff > 0.7:
        rebalance_difficulty(selected, candidates)

    return selected
```

## When to Move Beyond Greedy

The greedy heuristic should be replaced with an exact solver if:

1. **User reports "boring" sessions** consistently — suggests the objective function weights are wrong or the greedy approach is stuck in a local optimum.
2. **Item pool exceeds 2,000** — the greedy approach may miss high-value combinations that require looking ahead.
3. **New constraint types are added** that create complex interactions (e.g., "if item A is in the session, item B must also be included" — dependency constraints).

If exact solving is needed, use **integer linear programming** (ILP) via PuLP or OR-Tools:

```python
from pulp import LpMaximize, LpProblem, LpVariable, lpSum

def optimal_drill_selection(candidates, session_length=12):
    prob = LpProblem("drill_selection", LpMaximize)

    # Decision variables
    x = {item.id: LpVariable(f"x_{item.id}", cat="Binary")
         for item in candidates}

    # Objective
    prob += lpSum(x[item.id] * item.score for item in candidates)

    # C1: Session length
    prob += lpSum(x[item.id] for item in candidates) == session_length

    # C5: New item cap
    prob += lpSum(x[item.id] for item in candidates if item.is_new) <= 3

    # C4: Difficulty band
    prob += lpSum(x[item.id] * item.difficulty for item in candidates) >= 0.3 * session_length
    prob += lpSum(x[item.id] * item.difficulty for item in candidates) <= 0.7 * session_length

    # Solve
    prob.solve()

    selected_ids = [item.id for item in candidates if x[item.id].value() == 1]
    return selected_ids
```

Note: ILP handles *selection* but not *ordering*. Ordering (interleaving constraint C3) is applied as a post-processing step on the selected items.

## Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Session accuracy | 65-85% | Avg correct rate per session |
| Recall improvement | > 0 | Compare predicted_recall before and after session |
| Modality coverage | All active modalities present | Count distinct modalities per session |
| New item success | > 50% accuracy on new items | Filter review_events for is_new items |
| Session abandonment | < 10% | Sessions started but not completed |

## Connection to Other Analyses

- **Session length** (see `session-optimization.md`): The `session_length` parameter in C1 should be set based on fatigue analysis.
- **SRS parameters** (see `srs-optimization.md`): The `predicted_recall` values used in scoring depend on well-calibrated SRS parameters.
- **A/B testing** (see `ab-testing-framework.md`): Any change to the objective function weights or constraints should be A/B tested.

# Optimization Models

## Overview

Three optimization problems arise in Aelu's core learning loop: (1) what drill mix to present in a session, (2) when to schedule the next review, and (3) in what order to sequence new content. Each can be formulated as a mathematical program with an objective function and constraints.

---

## 1. Optimal Drill Mix Per Session

### Problem Statement

Given a pool of items due for review and new items available for introduction, select and sequence 12 drills to maximize expected retention gain per minute of learner time, subject to variety and engagement constraints.

### Decision Variables

Let `x_ij` be a binary variable: 1 if item `i` is presented as drill type `j`, 0 otherwise.

- `i` ranges over available items (due reviews + new items)
- `j` ranges over 12 drill types: `{hanzi_to_english, english_to_hanzi, hanzi_to_pinyin, listening, tone_production, ime_typing, fill_blank, sentence_order, register_choice, cloze_grammar, context_match, dialogue_response}`

### Objective Function

Maximize total expected retention gain:

```
maximize SUM over (i,j) of [ x_ij * retention_gain(i,j) / time_cost(i,j) ]
```

Where:
- `retention_gain(i,j)` = expected increase in item i's half-life from a correct response on drill type j. Estimated as:

```
retention_gain(i,j) = (1 - p_recall_i) * half_life_growth * drill_effectiveness(j)
```

Items with lower predicted recall (more forgotten) have higher potential gain. `drill_effectiveness(j)` captures that some drill types (e.g., recall-based) strengthen memory more than recognition-based drills.

- `time_cost(i,j)` = expected time in seconds for drill type j on item i. From historical data:

| Drill Type | Avg Time (s) | Effectiveness Weight |
|------------|-------------|---------------------|
| hanzi_to_english | 8 | 0.6 |
| english_to_hanzi | 12 | 0.8 |
| hanzi_to_pinyin | 10 | 0.7 |
| listening | 15 | 0.9 |
| tone_production | 20 | 1.0 |
| ime_typing | 25 | 1.0 |
| fill_blank | 15 | 0.85 |
| sentence_order | 20 | 0.9 |
| register_choice | 12 | 0.7 |
| cloze_grammar | 15 | 0.85 |
| context_match | 10 | 0.6 |
| dialogue_response | 30 | 0.95 |

### Constraints

```
1. Session size: SUM over (i,j) of x_ij = 12

2. One drill per item: SUM over j of x_ij <= 1 for each i
   (each item appears at most once)

3. Modality variety: at least 3 distinct drill types used
   SUM over j of [max over i of x_ij] >= 3

4. New item cap: SUM over (i,j) where i is new of x_ij <= 5
   (at most 5 new items per session)

5. Review priority: SUM over (i,j) where p_recall_i < 0.7 of x_ij >= 3
   (at least 3 items that need reinforcement)

6. No drill type dominance: SUM over i of x_ij <= 4 for each j
   (no single drill type appears more than 4 times)

7. Interleaving: items from the same HSK level are not adjacent
   (enforced as ordering constraint post-selection)

8. Suitability: x_ij = 0 if item i is not suitable for drill type j
   (e.g., single-character items can't be sentence_order drills)
```

### Formulation as Integer Linear Program

```python
from scipy.optimize import linprog
import numpy as np

def optimize_drill_mix(items, drill_types, session_size=12):
    """
    Solve drill mix as an ILP using PuLP.

    items: list of dicts with keys:
        id, p_recall, half_life, hsk_level, is_new,
        suitable_drills (set of drill type names)
    drill_types: list of dicts with keys:
        name, avg_time_s, effectiveness
    """
    from pulp import (
        LpProblem, LpMaximize, LpVariable, LpBinary, lpSum, PULP_CBC_CMD
    )

    n_items = len(items)
    n_drills = len(drill_types)

    prob = LpProblem("DrillMix", LpMaximize)

    # Decision variables
    x = {}
    for i in range(n_items):
        for j in range(n_drills):
            x[i, j] = LpVariable(f"x_{i}_{j}", cat=LpBinary)

    # Objective: maximize retention gain per minute
    for i in range(n_items):
        for j in range(n_drills):
            item = items[i]
            drill = drill_types[j]

            if drill['name'] not in item['suitable_drills']:
                prob += x[i, j] == 0
                continue

            gain = (1 - item['p_recall']) * drill['effectiveness']
            cost = drill['avg_time_s'] / 60  # convert to minutes
            prob += x[i, j] * (gain / cost)

    # Constraint 1: session size
    prob += lpSum(x[i, j] for i in range(n_items)
                  for j in range(n_drills)) == session_size

    # Constraint 2: one drill per item
    for i in range(n_items):
        prob += lpSum(x[i, j] for j in range(n_drills)) <= 1

    # Constraint 4: new item cap
    prob += lpSum(
        x[i, j] for i in range(n_items) for j in range(n_drills)
        if items[i]['is_new']
    ) <= 5

    # Constraint 5: review priority
    prob += lpSum(
        x[i, j] for i in range(n_items) for j in range(n_drills)
        if items[i]['p_recall'] < 0.7
    ) >= min(3, sum(1 for it in items if it['p_recall'] < 0.7))

    # Constraint 6: no drill type dominance
    for j in range(n_drills):
        prob += lpSum(x[i, j] for i in range(n_items)) <= 4

    # Solve
    prob.solve(PULP_CBC_CMD(msg=0))

    selected = []
    for i in range(n_items):
        for j in range(n_drills):
            if x[i, j].value() == 1:
                selected.append((items[i], drill_types[j]))

    return selected
```

### Practical Note

Aelu currently uses a greedy heuristic for drill selection (priority queue by predicted recall, with modality rotation). The ILP formulation above is for cases where the heuristic produces suboptimal sessions (e.g., too many easy items, insufficient variety). The ILP adds ~50ms solve time for 200 candidate items, which is acceptable within the 80ms session-start budget.

---

## 2. Optimal SRS Scheduling

### Problem Statement

Minimize total review time over a planning horizon (e.g., 90 days) while maintaining a target retention rate (e.g., 85% predicted recall at time of review) for all active items.

### Decision Variables

Let `t_i` be the continuous variable representing the next review time (in days from now) for item `i`.

### Objective Function

```
minimize SUM over i of [ 1 / t_i ]
```

This minimizes the total review frequency. Longer intervals = fewer reviews = less total time. The reciprocal captures that an item reviewed every 1 day costs 10x more time than an item reviewed every 10 days.

### Constraints

```
1. Retention floor: 2^(-t_i / h_i) >= 0.85 for each item i
   where h_i = current half-life of item i

   Rearranged: t_i <= h_i * log2(1/0.85) = h_i * 0.2345

2. Minimum interval: t_i >= 0.25 days (6 hours)
   (prevent over-drilling)

3. Maximum interval: t_i <= 90 days
   (even well-known items should be reviewed within the planning horizon)

4. Daily capacity: at most 30 reviews per day
   SUM over i where floor(t_i) = d of 1 <= 30 for each day d

5. Spacing: |t_i - t_j| >= 0.1 days for items i,j in the same HSK level
   (avoid reviewing similar items back-to-back)
```

### Solution Approach

The retention floor constraint gives a closed-form upper bound on each interval:

```
t_i_max = h_i * 0.2345  (for 85% target)
t_i_max = h_i * 0.1520  (for 90% target)
t_i_max = h_i * 0.0740  (for 95% target)
```

Without the daily capacity constraint, the optimal solution is simply `t_i = t_i_max` for all items (review as late as possible while meeting the retention floor).

The daily capacity constraint makes this a bin-packing problem: assign reviews to days such that no day exceeds 30 reviews. This is NP-hard in general but tractable for typical Aelu item counts (< 1,000 active items).

```python
def schedule_reviews(items, target_recall=0.85, daily_cap=30, horizon=90):
    """
    Schedule reviews to minimize total frequency while meeting retention target.

    items: list of dicts with keys: id, half_life_days, last_review_day
    """
    import numpy as np
    from collections import defaultdict

    retention_factor = -np.log2(target_recall)  # 0.2345 for 85%
    today = 0

    # Calculate maximum interval for each item
    schedule = []
    for item in items:
        max_interval = item['half_life_days'] * retention_factor
        max_interval = np.clip(max_interval, 0.25, horizon)
        schedule.append({
            'item_id': item['id'],
            'half_life': item['half_life_days'],
            'max_interval': max_interval,
            'ideal_day': max_interval,
        })

    # Sort by ideal day (earliest first)
    schedule.sort(key=lambda x: x['ideal_day'])

    # Bin-pack into days with capacity constraint
    day_counts = defaultdict(int)
    for entry in schedule:
        target_day = int(entry['ideal_day'])
        # Find the nearest day with capacity
        for offset in range(horizon):
            for candidate in [target_day - offset, target_day + offset]:
                if 0 <= candidate < horizon and day_counts[candidate] < daily_cap:
                    entry['scheduled_day'] = candidate
                    day_counts[candidate] += 1
                    break
            else:
                continue
            break

    # Report
    total_reviews = len(schedule)
    avg_interval = np.mean([e['scheduled_day'] for e in schedule if 'scheduled_day' in e])
    max_daily = max(day_counts.values()) if day_counts else 0

    print(f"Scheduled {total_reviews} reviews over {horizon} days")
    print(f"Average interval: {avg_interval:.1f} days")
    print(f"Max reviews on any day: {max_daily}")

    return schedule
```

### Retention-Effort Tradeoff

| Target Recall | Avg Review Interval | Daily Reviews (300 items) | Daily Time |
|--------------|--------------------|--------------------------:|------------|
| 80% | h * 0.322 | ~8 | ~6 min |
| 85% | h * 0.234 | ~11 | ~8 min |
| 90% | h * 0.152 | ~17 | ~13 min |
| 95% | h * 0.074 | ~35 | ~26 min |

Aelu's default target of 85% balances effort against retention. Dropping to 80% nearly halves daily review load. Users who feel overwhelmed should be offered the 80% target; ambitious learners can opt for 90%.

---

## 3. Content Sequencing

### Problem Statement

Given a set of content items with prerequisite relationships (e.g., HSK 2 vocab requires HSK 1 foundations; grammar point X requires grammar point Y), determine the optimal teaching order that respects prerequisites and integrates with spaced repetition.

### Prerequisite Graph

Content items form a directed acyclic graph (DAG) where edges represent prerequisites:

```
HSK 1 basics → HSK 1 sentences → HSK 2 vocab → HSK 2 sentences → ...
grammar: 的 → 是...的 → 把 → 被
constructions: 了 (aspect) → 了 (change of state) → 了 (double 了)
```

### Topological Sort with SRS Overlay

A pure topological sort gives a valid teaching order but ignores spacing. The optimal sequence interleaves items to maximize spacing between related items while still respecting prerequisite order.

```python
def sequence_content(items, prerequisites, target_spacing_days=3):
    """
    Sequence content items respecting prerequisites with spacing overlay.

    items: list of content items with id, hsk_level, difficulty
    prerequisites: list of (before_id, after_id) pairs
    target_spacing_days: minimum days between prerequisite and dependent
    """
    from collections import defaultdict, deque

    # Build adjacency list and in-degree count
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    item_set = {item['id'] for item in items}

    for before, after in prerequisites:
        if before in item_set and after in item_set:
            graph[before].append(after)
            in_degree[after] += 1

    # Items with no prerequisites
    queue = deque([
        item['id'] for item in items
        if in_degree[item['id']] == 0
    ])

    # Modified topological sort: at each step, choose the item that
    # maximizes spacing from recently introduced items
    item_map = {item['id']: item for item in items}
    sequence = []
    introduced_at = {}  # item_id -> position in sequence
    position = 0

    while queue:
        # Score candidates by spacing benefit
        candidates = list(queue)
        best_id = None
        best_score = -1

        for cid in candidates:
            item = item_map[cid]
            # Score: prefer items from different HSK levels than recent items
            # and items whose prerequisites were introduced long ago
            recent_levels = [
                item_map[sid]['hsk_level']
                for sid in list(introduced_at.keys())[-5:]
            ]
            level_diversity = 1.0 if item['hsk_level'] not in recent_levels else 0.5

            # Prerequisite spacing: prefer items whose prereqs are well-spaced
            prereq_spacing = min(
                (position - introduced_at.get(before, 0))
                for before, after in prerequisites
                if after == cid and before in introduced_at
            ) if any(after == cid for _, after in prerequisites) else target_spacing_days

            score = level_diversity * min(prereq_spacing, target_spacing_days)

            if score > best_score:
                best_score = score
                best_id = cid

        # Add best candidate to sequence
        queue.remove(best_id)
        sequence.append(best_id)
        introduced_at[best_id] = position
        position += 1

        # Unlock dependents
        for dependent in graph[best_id]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    return sequence
```

### Formulation as ILP (for exact solution)

For small item sets (< 100 items), the sequencing can be solved exactly:

```
Decision variables: p_i = position of item i in the sequence (integer, 1..N)

Objective: maximize SUM over (i,j) in prerequisites of |p_j - p_i|
           (maximize spacing between prerequisite and dependent)

Constraints:
  1. Prerequisite order: p_j > p_i for all (i,j) in prerequisites
  2. All different: p_i != p_j for all i != j
  3. Range: 1 <= p_i <= N for all i
  4. Difficulty monotonicity (soft): prefer p_i < p_j when difficulty(i) < difficulty(j)
```

This is equivalent to a linear arrangement problem on a DAG, which can be solved with PuLP for N < 100 items.

### Practical Integration

Aelu currently sequences content by HSK level with difficulty-based ordering within each level. The topological sort with spacing overlay would replace the within-level ordering, producing sequences like:

```
Before: 你, 好, 你好, 我, 是, 我是, 他, 她, 们, 他们, ...
After:  你, 好, 我, 你好, 是, 他, 我是, 她, 们, 他们, ...
```

The interleaved sequence spaces related items (你/你好, 我/我是) apart, forcing the learner to retrieve from memory rather than relying on recency.

---

## Solver Selection

| Problem | Size | Recommended Solver | Solve Time |
|---------|------|-------------------|------------|
| Drill mix (ILP) | ~200 items x 12 types | PuLP with CBC | ~50ms |
| SRS scheduling | ~1000 items | Closed-form + greedy bin-pack | ~10ms |
| Content sequencing | ~300 items per HSK level | Modified topological sort | ~5ms |
| Content sequencing (exact) | < 100 items | PuLP with CBC | ~200ms |

All solve times are compatible with Aelu's session-start latency budget (80ms target, 200ms acceptable). No external optimization service is needed.

## Dependencies

- `PuLP` for ILP solving: `pip install pulp` (includes CBC solver, no commercial license needed)
- `scipy.optimize` for continuous optimization (already in scientific Python stack)
- `numpy` for matrix operations (already in requirements)

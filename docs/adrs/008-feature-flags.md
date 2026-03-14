# ADR-008: Deterministic Feature Flags with SHA256 Hashing

## Status

Accepted (2026-02)

## Context

Aelu needed a feature flag system for gradual rollout of new features (e.g., grammar drills, listening mode, classroom features) without requiring an external service. The system must be deterministic (same user always sees the same flag state), reproducible (debugging is possible), and operate without network calls.

## Decision Drivers

- No external service dependency (consistent with zero-runtime-LLM philosophy)
- Deterministic: same user + same flag = same result, always
- Reproducible: given a user ID and flag name, anyone can compute the expected state
- Gradual rollout: ability to enable a feature for N% of users
- No real-time toggle needed (flag changes deploy with code)
- Must work in CLI, web, and mobile contexts

## Considered Options

### Option 1: LaunchDarkly / Flagsmith

- **Pros**: Real-time toggles, targeting rules, analytics, audit log
- **Cons**: External dependency, $10-25/mo cost, network call per flag check (adds latency), overkill for solo developer

### Option 2: Environment Variables

- **Pros**: Simple, no code changes, works everywhere
- **Cons**: Binary on/off only (no gradual rollout), requires redeploy to change, no per-user targeting

### Option 3: Database Flags with Random Assignment

- **Pros**: Persisted, queryable, can change without deploy
- **Cons**: Non-deterministic (random assignment can't be reproduced), requires database read per flag check

### Option 4: SHA256 Deterministic Bucketing (chosen)

- **Pros**: Deterministic, no network call, no external dependency, reproducible, supports gradual rollout percentages
- **Cons**: No real-time toggle (requires code deploy to change rollout percentage), no complex targeting rules

## Decision

Use SHA256 hashing for deterministic feature flag bucketing. A user is "in" a flag's rollout if:

```python
import hashlib

def is_flag_enabled(user_id: int, flag_name: str, rollout_pct: int = 100) -> bool:
    """
    Deterministic feature flag check.
    SHA256(user_id + flag_name) -> bucket [0, 99] -> compare to rollout_pct.
    """
    key = f"{user_id}:{flag_name}"
    hash_bytes = hashlib.sha256(key.encode()).digest()
    bucket = hash_bytes[0] % 100  # 0-99
    return bucket < rollout_pct
```

Flag definitions are stored in the `feature_flag` table:

```sql
CREATE TABLE feature_flag (
    name TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,       -- global on/off
    rollout_pct INTEGER DEFAULT 100, -- percentage rollout
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

A flag is enabled for a user if: `flag.enabled = 1 AND is_flag_enabled(user_id, flag.name, flag.rollout_pct)`.

## Consequences

### Positive

- **Deterministic**: `SHA256("42:grammar_drills")` always produces the same hash. User 42 is always in or always out of the grammar_drills rollout. This makes bug reports actionable ("user 42 sees the bug" -> check their flag state deterministically).
- **No external dependency**: No LaunchDarkly API calls, no network latency, no service outages affecting flag evaluation.
- **Gradual rollout**: Setting `rollout_pct = 10` enables the feature for ~10% of users. Increasing to 50% adds users (never removes previously-included users, since SHA256 is deterministic and the bucket doesn't change).
- **Reproducible**: Any developer can compute whether user X should see flag Y by running the hash function. No database state needed for the computation itself.
- **Cheap**: Zero marginal cost. Flag checks are a single SHA256 computation (~1 microsecond).

### Negative

- **No real-time toggle**: Changing a flag's `rollout_pct` requires a database update and potentially a server restart (if flags are cached). In practice, Aelu updates flags via admin API and the change takes effect on next request.
- **No complex targeting**: Cannot target by geography, device type, or user attributes without adding those to the hash key. Currently targeting is user-ID-only.
- **Monotonic rollout only**: Increasing `rollout_pct` from 10% to 50% adds users but never removes the original 10%. To remove a user from a rollout, must disable the flag entirely. This is actually a feature (users never lose access to a feature they've been using).
- **Uneven distribution**: SHA256 mod 100 is nearly uniform but not perfectly so. For small user populations (<100), the actual rollout percentage may deviate from the target by several percentage points. Acceptable for Aelu's scale.

### Current Flags

| Flag Name | Rollout % | Description |
|-----------|----------|-------------|
| `grammar_drills` | 100 | Grammar drill module |
| `graded_reader` | 100 | Graded reading passages |
| `media_shelf` | 100 | Media recommendation system |
| `classroom_mode` | 100 | Teacher/classroom features |
| `listening_mode` | 100 | Extensive listening |
| `speaking_drills` | 100 | Tone production drills |

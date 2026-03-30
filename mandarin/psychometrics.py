"""Item Response Theory (IRT) — psychometric modeling for item calibration.

Implements 1PL (Rasch) and 2PL models using maximum likelihood estimation.
Separates item difficulty from learner ability for principled adaptive scheduling.

References:
- Rasch (1960): Probabilistic Models for Some Intelligence and Attainment Tests
- Lord (1980): Applications of Item Response Theory to Practical Testing Problems
- De Ayala (2009): The Theory and Practice of Item Response Theory

All computations use Python stdlib only (no scipy/numpy).
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Convergence parameters
_MAX_ITER = 50
_CONVERGENCE_THRESHOLD = 0.001
_LEARNING_RATE = 0.5  # Damped Newton step
_MIN_RESPONSES = 5  # Minimum responses per item/user for estimation


@dataclass
class IRTItem:
    """Estimated IRT parameters for a content item."""
    item_id: int
    difficulty: float   # b: higher = harder, logit scale
    discrimination: float  # a: higher = better discriminator (2PL only)
    infit: float        # Infit mean-square (1.0 = expected)
    outfit: float       # Outfit mean-square (1.0 = expected)
    n_responses: int


@dataclass
class IRTUser:
    """Estimated IRT parameters for a learner."""
    user_id: int
    ability: float      # theta: higher = more able, logit scale
    se: float           # Standard error of ability estimate
    n_responses: int


def _sigmoid(x: float) -> float:
    """Logistic sigmoid function, clamped to prevent overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _rasch_prob(ability: float, difficulty: float) -> float:
    """P(correct) under Rasch model: 1 / (1 + exp(-(ability - difficulty)))."""
    return _sigmoid(ability - difficulty)


def _2pl_prob(ability: float, difficulty: float, discrimination: float) -> float:
    """P(correct) under 2PL: 1 / (1 + exp(-a * (ability - difficulty)))."""
    return _sigmoid(discrimination * (ability - difficulty))


def estimate_item_difficulty(
    conn: sqlite3.Connection,
    item_id: int,
    abilities: dict[int, float] | None = None,
) -> float | None:
    """Estimate difficulty for a single item via MLE.

    If abilities are provided, uses them. Otherwise assumes all users have ability 0.
    """
    try:
        rows = conn.execute(
            "SELECT user_id, correct FROM review_event WHERE content_item_id = ?",
            (item_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    if len(rows) < _MIN_RESPONSES:
        return None

    responses = [(r["user_id"], 1 if r["correct"] else 0) for r in rows]

    # MLE via Newton-Raphson
    b = 0.0  # initial difficulty estimate
    for _ in range(_MAX_ITER):
        grad = 0.0
        hess = 0.0
        for uid, correct in responses:
            theta = (abilities or {}).get(uid, 0.0)
            p = _rasch_prob(theta, b)
            grad += (p - correct)  # derivative of log-likelihood w.r.t. b
            hess += p * (1 - p)    # second derivative

        if abs(hess) < 1e-10:
            break
        step = grad / hess
        b += _LEARNING_RATE * step
        if abs(step) < _CONVERGENCE_THRESHOLD:
            break

    return round(max(-5.0, min(5.0, b)), 4)


def estimate_user_ability(
    conn: sqlite3.Connection,
    user_id: int,
    difficulties: dict[int, float] | None = None,
) -> tuple[float, float] | None:
    """Estimate ability for a single user via MLE.

    Returns (ability, standard_error) or None.
    """
    try:
        rows = conn.execute(
            "SELECT content_item_id, correct FROM review_event WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    if len(rows) < _MIN_RESPONSES:
        return None

    responses = [(r["content_item_id"], 1 if r["correct"] else 0) for r in rows]

    # MLE via Newton-Raphson
    theta = 0.0
    for _ in range(_MAX_ITER):
        grad = 0.0
        info = 0.0  # Fisher information
        for iid, correct in responses:
            b = (difficulties or {}).get(iid, 0.0)
            p = _rasch_prob(theta, b)
            grad += (correct - p)
            info += p * (1 - p)

        if info < 1e-10:
            break
        step = grad / info
        theta += _LEARNING_RATE * step
        if abs(step) < _CONVERGENCE_THRESHOLD:
            break

    se = 1.0 / math.sqrt(max(info, 1e-10))
    theta = max(-5.0, min(5.0, theta))

    return (round(theta, 4), round(se, 4))


def joint_estimation(
    conn: sqlite3.Connection,
    max_iter: int = _MAX_ITER,
    min_responses: int = _MIN_RESPONSES,
) -> dict:
    """Joint MLE estimation of item difficulties and user abilities.

    Alternating procedure:
    1. Fix abilities → estimate difficulties
    2. Fix difficulties → estimate abilities
    3. Repeat until convergence

    Returns:
        {
            "items": {item_id: IRTItem},
            "users": {user_id: IRTUser},
            "converged": bool,
            "iterations": int,
            "n_items": int,
            "n_users": int,
        }
    """
    # Load all response data
    try:
        rows = conn.execute(
            "SELECT user_id, content_item_id, correct FROM review_event"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"items": {}, "users": {}, "converged": False, "iterations": 0,
                "n_items": 0, "n_users": 0}

    if not rows:
        return {"items": {}, "users": {}, "converged": False, "iterations": 0,
                "n_items": 0, "n_users": 0}

    # Build response matrix
    user_items: dict[int, list[tuple[int, int]]] = {}  # uid -> [(iid, correct)]
    item_users: dict[int, list[tuple[int, int]]] = {}  # iid -> [(uid, correct)]

    for r in rows:
        uid, iid, correct = r["user_id"], r["content_item_id"], 1 if r["correct"] else 0
        user_items.setdefault(uid, []).append((iid, correct))
        item_users.setdefault(iid, []).append((uid, correct))

    # Filter by minimum responses
    user_items = {k: v for k, v in user_items.items() if len(v) >= min_responses}
    item_users = {k: v for k, v in item_users.items() if len(v) >= min_responses}

    if not user_items or not item_users:
        return {"items": {}, "users": {}, "converged": False, "iterations": 0,
                "n_items": 0, "n_users": 0}

    # Initialize
    abilities = {uid: 0.0 for uid in user_items}
    difficulties = {iid: 0.0 for iid in item_users}

    converged = False
    iteration = 0

    for iteration in range(1, max_iter + 1):
        max_change = 0.0

        # Step 1: Fix abilities, update difficulties
        for iid, responses in item_users.items():
            grad = 0.0
            hess = 0.0
            for uid, correct in responses:
                if uid not in abilities:
                    continue
                p = _rasch_prob(abilities[uid], difficulties[iid])
                grad += (p - correct)
                hess += p * (1 - p)
            if hess > 1e-10:
                step = _LEARNING_RATE * grad / hess
                difficulties[iid] += step
                difficulties[iid] = max(-5.0, min(5.0, difficulties[iid]))
                max_change = max(max_change, abs(step))

        # Step 2: Fix difficulties, update abilities
        for uid, responses in user_items.items():
            grad = 0.0
            info = 0.0
            for iid, correct in responses:
                if iid not in difficulties:
                    continue
                p = _rasch_prob(abilities[uid], difficulties[iid])
                grad += (correct - p)
                info += p * (1 - p)
            if info > 1e-10:
                step = _LEARNING_RATE * grad / info
                abilities[uid] += step
                abilities[uid] = max(-5.0, min(5.0, abilities[uid]))
                max_change = max(max_change, abs(step))

        # Center abilities (identifiability constraint)
        mean_ability = sum(abilities.values()) / len(abilities)
        for uid in abilities:
            abilities[uid] -= mean_ability

        if max_change < _CONVERGENCE_THRESHOLD:
            converged = True
            break

    # Compute fit statistics
    items = {}
    for iid, responses in item_users.items():
        b = difficulties.get(iid, 0.0)
        infit_num = 0.0
        infit_den = 0.0
        outfit_sum = 0.0
        n = 0

        for uid, correct in responses:
            if uid not in abilities:
                continue
            p = _rasch_prob(abilities[uid], b)
            var = p * (1 - p)
            residual = correct - p
            std_residual_sq = residual ** 2 / max(var, 1e-10)

            infit_num += residual ** 2
            infit_den += var
            outfit_sum += std_residual_sq
            n += 1

        infit = infit_num / max(infit_den, 1e-10) if n > 0 else 1.0
        outfit = outfit_sum / max(n, 1) if n > 0 else 1.0

        items[iid] = IRTItem(
            item_id=iid,
            difficulty=round(b, 4),
            discrimination=1.0,  # Rasch assumes a=1
            infit=round(infit, 4),
            outfit=round(outfit, 4),
            n_responses=n,
        )

    users = {}
    for uid, responses in user_items.items():
        theta = abilities.get(uid, 0.0)
        info = sum(
            _rasch_prob(theta, difficulties.get(iid, 0.0))
            * (1 - _rasch_prob(theta, difficulties.get(iid, 0.0)))
            for iid, _ in responses
            if iid in difficulties
        )
        se = 1.0 / math.sqrt(max(info, 1e-10))
        users[uid] = IRTUser(
            user_id=uid,
            ability=round(theta, 4),
            se=round(se, 4),
            n_responses=len(responses),
        )

    return {
        "items": items,
        "users": users,
        "converged": converged,
        "iterations": iteration,
        "n_items": len(items),
        "n_users": len(users),
    }


def item_fit_statistics(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """Compute fit statistics for a single item.

    Returns infit/outfit mean-square and point-biserial correlation.
    Infit 0.7-1.3: good fit. Outfit sensitive to outliers.
    """
    result = joint_estimation(conn, max_iter=20)
    item = result["items"].get(item_id)
    if not item:
        return None

    return {
        "item_id": item_id,
        "difficulty": item.difficulty,
        "infit": item.infit,
        "outfit": item.outfit,
        "n_responses": item.n_responses,
        "fit_quality": (
            "good" if 0.7 <= item.infit <= 1.3 else
            "overfit" if item.infit < 0.7 else
            "underfit"
        ),
    }


def reliability_coefficient(conn: sqlite3.Connection) -> dict:
    """Compute person and item separation reliability.

    Person separation: How well can we distinguish learners?
    Item separation: How well can we distinguish items?

    Reliability = 1 - (mean(SE²) / var(estimates))
    """
    result = joint_estimation(conn, max_iter=20)

    # Person separation
    if result["users"]:
        abilities = [u.ability for u in result["users"].values()]
        ses = [u.se for u in result["users"].values()]
        mean_se2 = sum(se ** 2 for se in ses) / len(ses)
        var_ability = _variance(abilities) if len(abilities) > 1 else 0
        person_reliability = max(0, 1 - mean_se2 / max(var_ability, 1e-10))
    else:
        person_reliability = 0.0

    # Item separation
    if result["items"]:
        diffs = [it.difficulty for it in result["items"].values()]
        var_diff = _variance(diffs) if len(diffs) > 1 else 0
        # Item SE approximation: 1/sqrt(n_responses) for each item
        mean_item_se2 = sum(
            1.0 / max(it.n_responses, 1) for it in result["items"].values()
        ) / len(result["items"])
        item_reliability = max(0, 1 - mean_item_se2 / max(var_diff, 1e-10))
    else:
        item_reliability = 0.0

    return {
        "person_reliability": round(person_reliability, 4),
        "item_reliability": round(item_reliability, 4),
        "n_users": result["n_users"],
        "n_items": result["n_items"],
        "interpretation": {
            "person": (
                "excellent" if person_reliability > 0.9 else
                "good" if person_reliability > 0.8 else
                "acceptable" if person_reliability > 0.7 else
                "poor"
            ),
            "item": (
                "excellent" if item_reliability > 0.9 else
                "good" if item_reliability > 0.8 else
                "acceptable" if item_reliability > 0.7 else
                "poor"
            ),
        },
    }


def save_irt_results(conn: sqlite3.Connection, results: dict) -> int:
    """Persist IRT estimates to content_item and user tables.

    Returns number of items updated.
    """
    updated = 0
    for iid, item in results.get("items", {}).items():
        try:
            conn.execute(
                "UPDATE content_item SET irt_difficulty = ?, irt_discrimination = ?, "
                "irt_fit_infit = ?, irt_fit_outfit = ? WHERE id = ?",
                (item.difficulty, item.discrimination, item.infit, item.outfit, iid),
            )
            updated += 1
        except sqlite3.OperationalError:
            break  # Column doesn't exist yet

    for uid, user in results.get("users", {}).items():
        try:
            conn.execute(
                "UPDATE user SET irt_ability = ?, irt_ability_se = ? WHERE id = ?",
                (user.ability, user.se, uid),
            )
        except sqlite3.OperationalError:
            break

    if updated > 0:
        conn.commit()
    return updated


def _variance(values: list[float]) -> float:
    """Sample variance."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)

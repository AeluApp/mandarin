"""Learner clustering and segmentation — k-means with Euclidean distance.

Groups learners into behavioral segments for targeted interventions.
All computations use stdlib only (no sklearn, no numpy).
"""
from __future__ import annotations

import logging
import math
import random
import sqlite3
from typing import Any
from datetime import UTC

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _euclidean(a: list[float], b: list[float]) -> float:
    """Euclidean distance between two vectors of equal length."""
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b, strict=False)))


def _centroid(points: list[list[float]]) -> list[float]:
    """Compute the centroid (element-wise mean) of a set of points."""
    if not points:
        return []
    dim = len(points[0])
    n = len(points)
    return [sum(p[d] for p in points) / n for d in range(dim)]


def _vectors_equal(a: list[float], b: list[float], tol: float = 1e-9) -> bool:
    """Check if two vectors are element-wise equal within tolerance."""
    return all(abs(ai - bi) < tol for ai, bi in zip(a, b, strict=False))


# ---------------------------------------------------------------------------
# K-means clustering
# ---------------------------------------------------------------------------


def kmeans(
    data: list[list[float]],
    k: int,
    max_iter: int = 100,
    seed: int = 42,
) -> dict[str, Any]:
    """K-means clustering with Euclidean distance.

    Args:
        data: list of feature vectors (list of list of floats).
        k: number of clusters.
        max_iter: maximum iterations.
        seed: random seed for reproducibility.

    Returns: {"labels": list[int], "centroids": list[list[float]],
              "inertia": float, "iterations": int}
    """
    if not data:
        logger.warning("kmeans: empty data")
        return {"labels": [], "centroids": [], "inertia": 0.0, "iterations": 0}

    n = len(data)
    len(data[0])

    if k <= 0:
        logger.warning("kmeans: k must be > 0, got %d", k)
        return {"labels": [0] * n, "centroids": [_centroid(data)],
                "inertia": 0.0, "iterations": 0}

    if k >= n:
        # Each point is its own cluster
        labels = list(range(n))
        centroids = [list(d) for d in data]
        return {"labels": labels, "centroids": centroids, "inertia": 0.0, "iterations": 0}

    rng = random.Random(seed)

    # --- K-means++ initialization ---
    centroids: list[list[float]] = [list(data[rng.randint(0, n - 1)])]

    for _ in range(1, k):
        # Compute distance from each point to nearest existing centroid
        distances = []
        for point in data:
            min_dist = min(_euclidean(point, c) for c in centroids)
            distances.append(min_dist ** 2)

        # Weighted random selection proportional to squared distance
        total = sum(distances)
        if total == 0:
            # All points are identical — pick arbitrarily
            centroids.append(list(data[rng.randint(0, n - 1)]))
            continue

        target = rng.random() * total
        cumulative = 0.0
        chosen = 0
        for idx, d in enumerate(distances):
            cumulative += d
            if cumulative >= target:
                chosen = idx
                break
        centroids.append(list(data[chosen]))

    # --- Lloyd's iterations ---
    labels = [0] * n
    iterations = 0

    for iteration in range(max_iter):
        iterations = iteration + 1

        # Assignment step: assign each point to nearest centroid
        changed = False
        for i, point in enumerate(data):
            best_cluster = 0
            best_dist = _euclidean(point, centroids[0])
            for c_idx in range(1, k):
                dist = _euclidean(point, centroids[c_idx])
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = c_idx
            if labels[i] != best_cluster:
                labels[i] = best_cluster
                changed = True

        if not changed:
            break

        # Update step: recompute centroids
        new_centroids: list[list[float]] = []
        for c_idx in range(k):
            cluster_points = [data[i] for i in range(n) if labels[i] == c_idx]
            if cluster_points:
                new_centroids.append(_centroid(cluster_points))
            else:
                # Empty cluster — reinitialize to a random point
                new_centroids.append(list(data[rng.randint(0, n - 1)]))

        # Check convergence
        converged = all(
            _vectors_equal(old, new)
            for old, new in zip(centroids, new_centroids, strict=False)
        )
        centroids = new_centroids

        if converged:
            break

    # Compute inertia (within-cluster sum of squared distances)
    inertia = sum(
        _euclidean(data[i], centroids[labels[i]]) ** 2
        for i in range(n)
    )

    return {
        "labels": labels,
        "centroids": centroids,
        "inertia": inertia,
        "iterations": iterations,
    }


# ---------------------------------------------------------------------------
# Cluster quality metrics
# ---------------------------------------------------------------------------


def silhouette_score(data: list[list[float]], labels: list[int]) -> float:
    """Average silhouette score for cluster quality.

    For each point, silhouette = (b - a) / max(a, b) where:
      a = mean intra-cluster distance
      b = mean nearest-cluster distance

    Returns float in [-1, 1]. Higher = better separation.
    """
    if not data or not labels or len(data) != len(labels):
        return 0.0

    n = len(data)
    unique_labels = sorted(set(labels))
    if len(unique_labels) < 2:
        return 0.0  # silhouette undefined for single cluster

    # Build cluster membership
    clusters: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(label, []).append(i)

    silhouettes: list[float] = []

    for i in range(n):
        own_cluster = labels[i]
        own_members = clusters[own_cluster]

        # a(i): mean distance to own cluster members
        if len(own_members) <= 1:
            a_i = 0.0
        else:
            a_i = sum(
                _euclidean(data[i], data[j]) for j in own_members if j != i
            ) / (len(own_members) - 1)

        # b(i): minimum mean distance to members of any other cluster
        b_i = math.inf
        for other_label, other_members in clusters.items():
            if other_label == own_cluster or not other_members:
                continue
            mean_dist = sum(
                _euclidean(data[i], data[j]) for j in other_members
            ) / len(other_members)
            b_i = min(b_i, mean_dist)

        if b_i == math.inf:
            b_i = 0.0

        denom = max(a_i, b_i)
        if denom > 0:
            silhouettes.append((b_i - a_i) / denom)
        else:
            silhouettes.append(0.0)

    return sum(silhouettes) / len(silhouettes)


# ---------------------------------------------------------------------------
# Optimal k selection
# ---------------------------------------------------------------------------


def optimal_k(
    data: list[list[float]],
    max_k: int = 8,
) -> dict[str, Any]:
    """Find optimal k using elbow method (within-cluster sum of squares).

    Finds the k where the rate of inertia decrease slows most
    (largest second derivative of the inertia curve).

    Returns: {"optimal_k": int, "inertias": list[float]}
    """
    if not data:
        return {"optimal_k": 1, "inertias": []}

    n = len(data)
    max_k = min(max_k, n)

    if max_k < 2:
        return {"optimal_k": 1, "inertias": [0.0]}

    inertias: list[float] = []
    for k_val in range(1, max_k + 1):
        result = kmeans(data, k_val)
        inertias.append(result["inertia"])

    # Find elbow: largest second derivative (discrete)
    if len(inertias) < 3:
        return {"optimal_k": min(2, max_k), "inertias": inertias}

    best_k = 2
    best_diff = -math.inf
    for i in range(1, len(inertias) - 1):
        # Second derivative: f(i-1) - 2*f(i) + f(i+1)
        second_deriv = inertias[i - 1] - 2 * inertias[i] + inertias[i + 1]
        if second_deriv > best_diff:
            best_diff = second_deriv
            best_k = i + 1  # k is 1-indexed

    return {"optimal_k": best_k, "inertias": inertias}


# ---------------------------------------------------------------------------
# Learner feature extraction
# ---------------------------------------------------------------------------


def extract_learner_features(
    conn: sqlite3.Connection,
    user_id: int,
) -> list[float]:
    """Extract feature vector for a learner.

    Features (8 dimensions, all normalized to 0-1):
        0. sessions_per_week     — avg sessions per week since first session
        1. avg_accuracy          — overall proportion correct
        2. avg_response_ms_norm  — normalized average response time (inverted: lower is better)
        3. production_rate       — fraction of reviews in production modalities (speaking/ime)
        4. mastery_speed         — fraction of items at mastered+ stage
        5. error_diversity       — unique error types / total errors (Shannon-like)
        6. confidence_calibration — how well confidence predicts correctness
        7. listening_accuracy    — accuracy on listening modality reviews

    Returns: list[float] (8 features). Returns [0.5]*8 on error or no data.
    """
    default = [0.5] * 8

    try:
        # --- 0. sessions_per_week ---
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MIN(started_at) as first_at "
            "FROM session_log WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not row or not row["cnt"] or row["cnt"] == 0:
            return default

        session_count = row["cnt"]

        # Compute weeks since first session
        first_at = row["first_at"]
        if first_at:
            from datetime import datetime, timezone
            try:
                first_dt = datetime.fromisoformat(first_at.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                weeks = max(1.0, (now - first_dt).days / 7.0)
            except (ValueError, TypeError):
                weeks = max(1.0, session_count / 3.0)
        else:
            weeks = max(1.0, session_count / 3.0)

        sessions_per_week = min(session_count / weeks, 14.0) / 14.0  # cap at 14/week

        # --- 1. avg_accuracy ---
        acc_row = conn.execute(
            "SELECT COUNT(*) as total, SUM(correct) as correct_sum "
            "FROM review_event WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if acc_row and acc_row["total"] and acc_row["total"] > 0:
            avg_accuracy = acc_row["correct_sum"] / acc_row["total"]
        else:
            avg_accuracy = 0.5

        # --- 2. avg_response_ms (normalized, inverted) ---
        ms_row = conn.execute(
            "SELECT AVG(response_ms) as avg_ms "
            "FROM review_event WHERE user_id = ? AND response_ms IS NOT NULL AND response_ms > 0",
            (user_id,),
        ).fetchone()

        if ms_row and ms_row["avg_ms"] and ms_row["avg_ms"] > 0:
            # Normalize: 500ms = fast (1.0), 10000ms = slow (0.0)
            avg_ms = ms_row["avg_ms"]
            avg_response_norm = max(0.0, min(1.0, 1.0 - (avg_ms - 500) / 9500))
        else:
            avg_response_norm = 0.5

        # --- 3. production_rate ---
        prod_row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN modality IN ('speaking', 'ime') THEN 1 ELSE 0 END) as prod "
            "FROM review_event WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if prod_row and prod_row["total"] and prod_row["total"] > 0:
            production_rate = prod_row["prod"] / prod_row["total"]
        else:
            production_rate = 0.0

        # --- 4. mastery_speed ---
        mastery_row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN mastery_stage IN ('mastered', 'deep_mastery') THEN 1 ELSE 0 END) as mastered "
            "FROM progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if mastery_row and mastery_row["total"] and mastery_row["total"] > 0:
            mastery_speed = mastery_row["mastered"] / mastery_row["total"]
        else:
            mastery_speed = 0.0

        # --- 5. error_diversity ---
        err_row = conn.execute(
            "SELECT COUNT(*) as total, COUNT(DISTINCT error_type) as unique_types "
            "FROM review_event WHERE user_id = ? AND correct = 0 AND error_type IS NOT NULL",
            (user_id,),
        ).fetchone()

        if err_row and err_row["total"] and err_row["total"] > 0:
            # Normalize: more diverse errors -> higher value (cap at 10 types)
            error_diversity = min(err_row["unique_types"] / 10.0, 1.0)
        else:
            error_diversity = 0.0

        # --- 6. confidence_calibration ---
        # How well does stated confidence predict correctness?
        cal_rows = conn.execute(
            "SELECT confidence, correct FROM review_event "
            "WHERE user_id = ? AND confidence IS NOT NULL",
            (user_id,),
        ).fetchall()

        if cal_rows and len(cal_rows) >= 5:
            # Map confidence labels to expected accuracy
            conf_map = {"full": 0.9, "partial": 0.6, "guess": 0.3}
            diffs = []
            for r in cal_rows:
                conf_str = r["confidence"] if r["confidence"] else "partial"
                expected = conf_map.get(conf_str, 0.5)
                actual = float(r["correct"])
                diffs.append(abs(expected - actual))
            # Lower mean diff = better calibration
            mean_diff = sum(diffs) / len(diffs)
            confidence_calibration = max(0.0, min(1.0, 1.0 - mean_diff))
        else:
            confidence_calibration = 0.5

        # --- 7. listening_accuracy ---
        listen_row = conn.execute(
            "SELECT COUNT(*) as total, SUM(correct) as correct_sum "
            "FROM review_event WHERE user_id = ? AND modality = 'listening'",
            (user_id,),
        ).fetchone()

        if listen_row and listen_row["total"] and listen_row["total"] > 0:
            listening_accuracy = listen_row["correct_sum"] / listen_row["total"]
        else:
            listening_accuracy = 0.5

        return [
            sessions_per_week,
            avg_accuracy,
            avg_response_norm,
            production_rate,
            mastery_speed,
            error_diversity,
            confidence_calibration,
            listening_accuracy,
        ]

    except Exception:
        logger.exception("extract_learner_features: failed for user_id=%d", user_id)
        return default


# ---------------------------------------------------------------------------
# High-level segmentation
# ---------------------------------------------------------------------------

_SEGMENT_PROFILES = {
    "steady_learner": {
        "description": "Moderate pace, good accuracy, consistent practice",
        "recommendations": [
            "Continue current review schedule",
            "Gradually introduce harder content",
            "Try production drills (speaking, IME) if not already active",
        ],
        "focus_areas": ["vocabulary breadth", "tone accuracy", "reading speed"],
    },
    "fast_starter": {
        "description": "High session frequency, variable accuracy",
        "recommendations": [
            "Slow down and focus on accuracy over speed",
            "Use spaced repetition to consolidate items before adding new ones",
            "Review error patterns to identify weak spots",
        ],
        "focus_areas": ["error patterns", "accuracy improvement", "retention"],
    },
    "struggling": {
        "description": "Low accuracy, slow mastery progression",
        "recommendations": [
            "Reduce new items per session to avoid overload",
            "Focus on high-frequency vocabulary first",
            "Use listening drills to build phonetic awareness",
            "Review tone rules and common confusion pairs",
        ],
        "focus_areas": ["foundational vocabulary", "tone discrimination", "confidence building"],
    },
    "advanced_plateau": {
        "description": "High accuracy on known items, but few new items added",
        "recommendations": [
            "Push into production modalities (speaking, IME writing)",
            "Introduce contextual and sentence-level drills",
            "Try harder content or less common vocabulary",
        ],
        "focus_areas": ["production skills", "contextual usage", "advanced vocabulary"],
    },
}


def _assign_segment_name(centroid: list[float]) -> str:
    """Assign a human-readable segment name based on centroid characteristics.

    Feature indices:
        0=sessions_per_week, 1=avg_accuracy, 2=avg_response_norm,
        3=production_rate, 4=mastery_speed, 5=error_diversity,
        6=confidence_calibration, 7=listening_accuracy
    """
    if len(centroid) < 8:
        return "steady_learner"

    sessions = centroid[0]
    accuracy = centroid[1]
    mastery = centroid[4]

    # High accuracy, high mastery -> advanced_plateau
    if accuracy > 0.7 and mastery > 0.5:
        return "advanced_plateau"
    # High sessions, lower accuracy -> fast_starter
    if sessions > 0.4 and accuracy < 0.6:
        return "fast_starter"
    # Low accuracy, low mastery -> struggling
    if accuracy < 0.5 and mastery < 0.3:
        return "struggling"
    # Default: steady_learner
    return "steady_learner"


def segment_learners(
    conn: sqlite3.Connection,
    k: int = 4,
    min_sessions: int = 5,
) -> dict[str, Any]:
    """Cluster all active learners into behavioral segments.

    Args:
        conn: database connection.
        k: number of clusters (default 4).
        min_sessions: minimum sessions to include a learner.

    Returns: {"segments": dict, "centroids": list, "labels": dict,
              "segment_names": dict}
    """
    try:
        # Find users with enough sessions
        rows = conn.execute(
            "SELECT user_id, COUNT(*) as cnt FROM session_log "
            "GROUP BY user_id HAVING cnt >= ?",
            (min_sessions,),
        ).fetchall()

        if not rows:
            logger.info("segment_learners: no users with >= %d sessions", min_sessions)
            return {
                "segments": {},
                "centroids": [],
                "labels": {},
                "segment_names": {},
            }

        user_ids = [r["user_id"] for r in rows]

        # Extract features for all qualifying users
        features: list[list[float]] = []
        valid_user_ids: list[int] = []

        for uid in user_ids:
            feat = extract_learner_features(conn, uid)
            # Ensure all features are finite
            if all(math.isfinite(f) for f in feat):
                features.append(feat)
                valid_user_ids.append(uid)

        if len(valid_user_ids) < 2:
            logger.info("segment_learners: fewer than 2 valid users for clustering")
            segment_name = "steady_learner"
            return {
                "segments": {segment_name: valid_user_ids},
                "centroids": [_centroid(features)] if features else [],
                "labels": {uid: 0 for uid in valid_user_ids},
                "segment_names": {0: segment_name},
            }

        # Adjust k if we have fewer users than clusters
        effective_k = min(k, len(valid_user_ids))

        # Run k-means
        result = kmeans(features, effective_k)
        cluster_labels = result["labels"]
        centroids = result["centroids"]

        # Assign segment names based on centroid characteristics
        segment_names: dict[int, str] = {}
        used_names: set[str] = set()
        name_candidates = list(_SEGMENT_PROFILES.keys())

        for c_idx in range(effective_k):
            name = _assign_segment_name(centroids[c_idx])
            # Ensure unique names by appending index if needed
            if name in used_names:
                for candidate in name_candidates:
                    if candidate not in used_names:
                        name = candidate
                        break
                else:
                    name = f"segment_{c_idx}"
            segment_names[c_idx] = name
            used_names.add(name)

        # Build segments dict: segment_name -> list of user_ids
        segments: dict[str, list[int]] = {name: [] for name in segment_names.values()}
        labels_map: dict[int, int] = {}

        for i, uid in enumerate(valid_user_ids):
            label = cluster_labels[i]
            seg_name = segment_names[label]
            segments[seg_name].append(uid)
            labels_map[uid] = label

        return {
            "segments": segments,
            "centroids": centroids,
            "labels": labels_map,
            "segment_names": segment_names,
        }

    except Exception:
        logger.exception("segment_learners: clustering failed")
        return {
            "segments": {},
            "centroids": [],
            "labels": {},
            "segment_names": {},
        }


def get_segment_recommendations(segment_name: str) -> dict[str, Any]:
    """Return learning recommendations for a segment.

    Returns: {"recommendations": list[str], "focus_areas": list[str]}
    """
    profile = _SEGMENT_PROFILES.get(segment_name)
    if profile:
        return {
            "recommendations": list(profile["recommendations"]),
            "focus_areas": list(profile["focus_areas"]),
        }

    # Fallback for unknown segment names
    return {
        "recommendations": [
            "Maintain a consistent review schedule",
            "Focus on items due for review before adding new content",
        ],
        "focus_areas": ["general practice", "consistency"],
    }

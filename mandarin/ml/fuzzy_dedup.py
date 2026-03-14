"""Sentence transformer fuzzy deduplication for intelligence findings.

Replaces SequenceMatcher-based _fuzzy_match() with semantic similarity.
Uses all-MiniLM-L6-v2 (22MB, local, no API calls).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Singleton model — loaded once, reused
_model = None
_model_lock = threading.Lock()


def _get_model():
    """Lazy-load sentence transformer model."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    _model = SentenceTransformer('all-MiniLM-L6-v2')
                except ImportError:
                    logger.warning("sentence-transformers not installed; fuzzy dedup unavailable")
                    return None
                except Exception as e:
                    logger.warning("Failed to load sentence transformer: %s", e)
                    return None
    return _model


def is_available() -> bool:
    """Check if sentence transformer model is loaded / loadable."""
    return _get_model() is not None


def compute_similarity(text_a: str, text_b: str) -> float:
    """Compute semantic similarity between two texts. Returns 0-1."""
    model = _get_model()
    if model is None:
        return 0.0

    embeddings = model.encode([text_a, text_b], convert_to_numpy=True)
    norm_a = np.linalg.norm(embeddings[0])
    norm_b = np.linalg.norm(embeddings[1])
    if norm_a == 0 or norm_b == 0:
        return 0.0
    similarity = float(np.dot(embeddings[0], embeddings[1]) / (norm_a * norm_b))
    return max(0.0, min(1.0, similarity))


def find_semantic_duplicate(
    conn: sqlite3.Connection,
    dimension: str,
    title: str,
    severity: str = "",
    similarity_threshold: float = 0.82,
) -> Optional[int]:
    """Find an existing open finding semantically equivalent to a new one.

    Returns finding_id of duplicate if found, None otherwise.
    Only compares within the same dimension.
    """
    model = _get_model()
    if model is None:
        return None

    existing = conn.execute("""
        SELECT id, title, severity
        FROM pi_finding
        WHERE dimension = ?
        AND status NOT IN ('resolved', 'rejected')
        AND created_at >= datetime('now', '-60 days')
    """, (dimension,)).fetchall()

    if not existing:
        return None

    # Batch encode all titles at once
    existing_titles = [r['title'] for r in existing]
    all_texts = [title] + existing_titles
    embeddings = model.encode(all_texts, convert_to_numpy=True, show_progress_bar=False)

    new_emb = embeddings[0]
    new_norm = np.linalg.norm(new_emb)
    if new_norm == 0:
        return None

    best_id, best_sim = None, 0.0
    for i, (row, emb) in enumerate(zip(existing, embeddings[1:])):
        emb_norm = np.linalg.norm(emb)
        if emb_norm == 0:
            continue
        sim = float(np.dot(new_emb, emb) / (new_norm * emb_norm))
        if sim > best_sim:
            best_sim = sim
            best_id = row['id']

    if best_sim >= similarity_threshold:
        return best_id
    return None


def cache_embedding(conn: sqlite3.Connection, finding_id: int, title: str) -> None:
    """Cache a finding's title embedding for faster future comparisons."""
    model = _get_model()
    if model is None:
        return
    try:
        embedding = model.encode([title], convert_to_numpy=True)[0]
        embedding_bytes = embedding.tobytes()
        conn.execute("""
            INSERT OR REPLACE INTO pi_finding_embeddings
            (finding_id, title_at_embedding, embedding_bytes)
            VALUES (?, ?, ?)
        """, (finding_id, title, embedding_bytes))
    except Exception:
        logger.debug("Failed to cache embedding", exc_info=True)


def calibrate_similarity_threshold(conn: sqlite3.Connection) -> dict:
    """Analyze similarity distribution across existing findings.

    Run after accumulating 50+ findings to tune the threshold.
    """
    model = _get_model()
    if model is None:
        return {'status': 'model_unavailable'}

    findings = conn.execute("""
        SELECT id, dimension, title FROM pi_finding
        WHERE status NOT IN ('resolved', 'rejected')
        ORDER BY dimension, created_at
    """).fetchall()

    findings_by_dim = {}
    for f in findings:
        findings_by_dim.setdefault(f['dimension'], []).append(f)

    all_similarities = []
    for dim, dim_findings in findings_by_dim.items():
        if len(dim_findings) < 2:
            continue

        titles = [f['title'] for f in dim_findings]
        embeddings = model.encode(titles, convert_to_numpy=True, show_progress_bar=False)

        for i in range(len(dim_findings)):
            for j in range(i + 1, len(dim_findings)):
                norm_i = np.linalg.norm(embeddings[i])
                norm_j = np.linalg.norm(embeddings[j])
                if norm_i == 0 or norm_j == 0:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]) / (norm_i * norm_j))
                all_similarities.append({
                    'finding_a': dim_findings[i]['title'],
                    'finding_b': dim_findings[j]['title'],
                    'similarity': sim,
                    'dimension': dim,
                })

    if not all_similarities:
        return {'status': 'insufficient_data'}

    sims = [s['similarity'] for s in all_similarities]
    return {
        'status': 'complete',
        'mean_similarity': float(np.mean(sims)),
        'p90_similarity': float(np.percentile(sims, 90)),
        'p95_similarity': float(np.percentile(sims, 95)),
        'suggested_threshold': float(np.percentile(sims, 90)),
        'sample_high_similarity_pairs': sorted(
            all_similarities, key=lambda x: x['similarity'], reverse=True,
        )[:5],
    }

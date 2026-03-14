"""RAG Evaluation with RAGAS-inspired metrics (Doc 23 A-07 / 2A).

Evaluates retrieval quality:
- Faithfulness: % of generated claims grounded in retrieved docs
- Relevance: semantic similarity between query and retrieved docs
- Context precision: relevant docs ranked higher
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    import faiss
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False
    logger.debug("faiss-cpu not installed — FAISS indexing disabled")


def build_faiss_index(
    conn: sqlite3.Connection,
    index_name: str = "content_items",
    data_dir: Optional[str] = None,
) -> dict:
    """Build a FAISS IVF index from content_item + grammar_point embeddings.

    Uses existing paraphrase-multilingual-mpnet-base-v2 embeddings.
    """
    if not _HAS_FAISS or not _HAS_NUMPY:
        return {"status": "skipped", "reason": "faiss-cpu or numpy not installed"}

    from .genai_layer import _get_multilingual_model

    model = _get_multilingual_model()
    if model is None:
        return {"status": "skipped", "reason": "sentence-transformers not available"}

    from ..settings import DATA_DIR
    index_dir = data_dir or str(DATA_DIR)

    # Collect texts to embed
    texts = []
    ids = []

    try:
        items = conn.execute("""
            SELECT id, hanzi, pinyin, english, hsk_level
            FROM content_item WHERE status = 'drill_ready' AND review_status = 'approved'
        """).fetchall()
        for item in items:
            text = f"{item['hanzi']} {item['pinyin'] or ''} {item['english'] or ''}"
            texts.append(text.strip())
            ids.append(("content_item", item["id"]))
    except sqlite3.OperationalError:
        pass

    try:
        gps = conn.execute("""
            SELECT id, name, name_zh, description
            FROM grammar_point
        """).fetchall()
        for gp in gps:
            text = f"{gp['name']} {gp['name_zh'] or ''} {gp['description'] or ''}"
            texts.append(text.strip())
            ids.append(("grammar_point", gp["id"]))
    except sqlite3.OperationalError:
        pass

    if not texts:
        return {"status": "error", "reason": "no texts to index"}

    # Encode
    embeddings = model.encode(texts, show_progress_bar=False, batch_size=64)
    embeddings = np.array(embeddings, dtype=np.float32)
    dimension = embeddings.shape[1]

    # Normalize for cosine similarity
    faiss.normalize_L2(embeddings)

    # Build index
    if len(texts) > 100:
        nlist = min(int(len(texts) ** 0.5), 100)
        quantizer = faiss.IndexFlatIP(dimension)
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
        index.train(embeddings)
    else:
        index = faiss.IndexFlatIP(dimension)

    index.add(embeddings)

    # Save index to disk
    index_path = f"{index_dir}/faiss_{index_name}.index"
    faiss.write_index(index, index_path)

    # Save ID mapping
    id_map_path = f"{index_dir}/faiss_{index_name}_ids.json"
    with open(id_map_path, "w") as f:
        json.dump(ids, f)

    # Update DB metadata
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("DELETE FROM rag_faiss_index WHERE index_name = ?", (index_name,))
        conn.execute("""
            INSERT INTO rag_faiss_index (index_name, dimension, num_vectors, built_at, index_path)
            VALUES (?, ?, ?, ?, ?)
        """, (index_name, dimension, len(texts), now, index_path))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return {
        "status": "completed",
        "index_name": index_name,
        "dimension": dimension,
        "num_vectors": len(texts),
        "index_path": index_path,
    }


def hybrid_retrieve(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 10,
    index_name: str = "content_items",
) -> list[dict]:
    """Hybrid BM25 + FAISS semantic search with Reciprocal Rank Fusion.

    Falls back to BM25-only if FAISS not available.
    """
    bm25_results = _bm25_retrieve(conn, query, top_k=top_k * 2)
    faiss_results = _faiss_retrieve(conn, query, top_k=top_k * 2, index_name=index_name)

    if not faiss_results:
        return bm25_results[:top_k]

    # Reciprocal Rank Fusion (k=60)
    k = 60
    scores = {}
    for rank, item in enumerate(bm25_results):
        key = (item["type"], item["id"])
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
        if key not in scores:
            scores[key] = {"item": item}

    for rank, item in enumerate(faiss_results):
        key = (item["type"], item["id"])
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)

    # Build item lookup
    all_items = {}
    for item in bm25_results + faiss_results:
        key = (item["type"], item["id"])
        all_items[key] = item

    # Sort by RRF score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for key, score in ranked[:top_k]:
        item = all_items.get(key, {"type": key[0], "id": key[1]})
        item["rrf_score"] = round(score, 4)
        results.append(item)

    return results


def _bm25_retrieve(conn: sqlite3.Connection, query: str, top_k: int = 20) -> list[dict]:
    """SQL LIKE-based BM25 approximation."""
    results = []
    terms = query.strip().split()
    if not terms:
        return results

    # Build LIKE clauses
    like_clauses = " OR ".join(
        "(hanzi LIKE ? OR pinyin LIKE ? OR english LIKE ?)" for _ in terms
    )
    params = []
    for term in terms:
        pattern = f"%{term}%"
        params.extend([pattern, pattern, pattern])

    try:
        rows = conn.execute(f"""
            SELECT id, hanzi, pinyin, english, hsk_level,
                   'content_item' as type
            FROM content_item
            WHERE status = 'drill_ready' AND ({like_clauses})
            LIMIT ?
        """, params + [top_k]).fetchall()
        results.extend([dict(r) for r in rows])
    except sqlite3.OperationalError:
        pass

    return results


def _faiss_retrieve(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 20,
    index_name: str = "content_items",
) -> list[dict]:
    """FAISS semantic search."""
    if not _HAS_FAISS or not _HAS_NUMPY:
        return []

    from .genai_layer import _get_multilingual_model
    from ..settings import DATA_DIR

    model = _get_multilingual_model()
    if model is None:
        return []

    index_path = f"{DATA_DIR}/faiss_{index_name}.index"
    id_map_path = f"{DATA_DIR}/faiss_{index_name}_ids.json"

    try:
        index = faiss.read_index(index_path)
        with open(id_map_path) as f:
            id_map = json.load(f)
    except (FileNotFoundError, Exception):
        return []

    # Encode query
    query_vec = model.encode([query], show_progress_bar=False)
    query_vec = np.array(query_vec, dtype=np.float32)
    faiss.normalize_L2(query_vec)

    # Search
    scores, indices = index.search(query_vec, min(top_k, index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(id_map):
            continue
        item_type, item_id = id_map[idx]
        results.append({
            "type": item_type,
            "id": item_id,
            "faiss_score": float(score),
        })

    return results


def rebuild_index_if_stale(conn: sqlite3.Connection, index_name: str = "content_items") -> dict:
    """Check if index is stale and rebuild if needed."""
    try:
        meta = conn.execute(
            "SELECT * FROM rag_faiss_index WHERE index_name = ?",
            (index_name,),
        ).fetchone()

        if not meta:
            return build_faiss_index(conn, index_name)

        # Count current items
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM content_item WHERE status = 'drill_ready'"
        ).fetchone()
        current_count = count["cnt"] if count else 0

        if current_count > meta["num_vectors"]:
            return build_faiss_index(conn, index_name)

        return {"status": "current", "num_vectors": meta["num_vectors"]}
    except sqlite3.OperationalError:
        return {"status": "error", "reason": "tables not available"}


def evaluate_retrieval(
    conn: sqlite3.Connection,
    query: str,
    retrieved_docs: list[dict],
    generated_output: Optional[str] = None,
    prompt_key: Optional[str] = None,
) -> dict:
    """Compute RAGAS-inspired metrics for a retrieval result.

    - Faithfulness: % of generated claims grounded in retrieved docs (via Qwen)
    - Relevance: semantic similarity between query and retrieved docs
    - Context precision: relevant docs ranked higher
    """
    from .genai_layer import _get_multilingual_model

    metrics = {
        "query": query,
        "retrieved_count": len(retrieved_docs),
    }

    # Relevance: embedding similarity between query and retrieved docs
    model = _get_multilingual_model()
    if model and retrieved_docs:
        query_emb = model.encode([query], show_progress_bar=False)
        doc_texts = [
            f"{d.get('hanzi', '')} {d.get('english', '')} {d.get('pinyin', '')}"
            for d in retrieved_docs
        ]
        doc_embs = model.encode(doc_texts, show_progress_bar=False)

        if _HAS_NUMPY:
            q = np.array(query_emb)
            d = np.array(doc_embs)
            # Cosine similarity
            q_norm = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-9)
            d_norm = d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)
            sims = (q_norm @ d_norm.T).flatten()
            metrics["relevance_score"] = round(float(np.mean(sims)), 4)
            # Context precision: are higher-ranked docs more relevant?
            if len(sims) > 1:
                top_half_avg = float(np.mean(sims[:len(sims) // 2]))
                bottom_half_avg = float(np.mean(sims[len(sims) // 2:]))
                metrics["context_precision_score"] = round(
                    top_half_avg / (top_half_avg + bottom_half_avg + 1e-9), 4
                )
    else:
        metrics["relevance_score"] = None
        metrics["context_precision_score"] = None

    # Faithfulness: via Qwen judge (only if generated output provided)
    if generated_output:
        metrics["faithfulness_score"] = _compute_faithfulness(
            conn, query, retrieved_docs, generated_output
        )
    else:
        metrics["faithfulness_score"] = None

    # Log evaluation
    try:
        conn.execute("""
            INSERT INTO rag_evaluation_log
            (query, retrieved_count, faithfulness_score, relevance_score,
             context_precision_score, generation_prompt_key)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            query, len(retrieved_docs),
            metrics.get("faithfulness_score"),
            metrics.get("relevance_score"),
            metrics.get("context_precision_score"),
            prompt_key,
        ))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return metrics


def _compute_faithfulness(
    conn: sqlite3.Connection,
    query: str,
    retrieved_docs: list[dict],
    generated_output: str,
) -> Optional[float]:
    """Use Qwen to judge faithfulness of generated output to retrieved docs."""
    from .ollama_client import generate as ollama_generate, is_ollama_available
    from .genai_layer import _parse_llm_json

    if not is_ollama_available():
        return None

    context_str = json.dumps(retrieved_docs[:5], ensure_ascii=False, default=str)
    prompt = (
        f"Query: {query}\n\n"
        f"Retrieved context:\n{context_str}\n\n"
        f"Generated output:\n{generated_output}\n\n"
        f"Score the faithfulness of the generated output to the context (0-1). "
        f"1.0 = every claim is grounded in context. 0.0 = entirely hallucinated.\n"
        f"Return JSON: {{\"faithfulness\": <float>}}"
    )

    resp = ollama_generate(
        prompt=prompt,
        system="You are a faithfulness evaluator. Score how well the output is grounded in the given context.",
        temperature=0.1,
        conn=conn,
        task_type="rag_faithfulness",
    )

    if not resp.success:
        return None

    parsed = _parse_llm_json(resp.text, conn=conn, task_type="rag_faithfulness")
    if parsed and "faithfulness" in parsed:
        return min(1.0, max(0.0, float(parsed["faithfulness"])))

    return None

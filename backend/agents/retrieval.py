"""
Retrieval Agent (Milestone 2 / M2.2)
Performs semantic search against the vector store, ranks results by
relevance score, and filters out low-confidence (weakly related) chunks.
"""
import config
from embeddings import embed_query
from vector_store import store


def retrieve(query: str, top_k: int = None, threshold: float = None) -> dict:
    top_k = top_k or config.TOP_K
    threshold = threshold if threshold is not None else config.RELEVANCE_THRESHOLD

    if store.index.ntotal == 0:
        return {"chunks": [], "no_results_reason": "Knowledge base is empty — no documents have been uploaded yet."}

    q_emb = embed_query(query)
    raw_results = store.search(q_emb, top_k=top_k)
    raw_results.sort(key=lambda r: r["relevance_score"], reverse=True)

    filtered = [r for r in raw_results if r["relevance_score"] >= threshold]

    if not filtered:
        return {
            "chunks": [],
            "no_results_reason": "No sufficiently relevant information was found in the knowledge base for this query.",
            "best_score_seen": raw_results[0]["relevance_score"] if raw_results else 0.0,
        }
    return {"chunks": filtered, "no_results_reason": None}
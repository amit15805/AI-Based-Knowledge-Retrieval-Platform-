"""
Query Understanding Agent (Milestone 2 / M2.1)
Classifies a query as factual, procedural, comparative, or ambiguous.
Uses the LLM when a key is configured, otherwise falls back to a
lightweight heuristic classifier so the pipeline still works for free.
"""
import re
import json
import llm_client

CATEGORIES = ["factual", "procedural", "comparative", "ambiguous"]


def _heuristic_classify(query: str) -> dict:
    q = query.lower().strip()
    if len(q.split()) <= 2 or q in {"tell me more", "what about it", "explain", "more info"}:
        return {"query_type": "ambiguous", "confidence": 0.55,
                "reason": "Query is too short or lacks a clear subject."}
    if any(w in q for w in ["vs", "versus", "compare", "difference between", "better than"]):
        return {"query_type": "comparative", "confidence": 0.8, "reason": "Comparison keywords detected."}
    if any(w in q for w in ["how do i", "how to", "steps to", "process for", "how can i"]):
        return {"query_type": "procedural", "confidence": 0.8, "reason": "Procedural keywords detected."}
    if q.startswith(("what", "who", "when", "where", "which", "is ", "does", "define")):
        return {"query_type": "factual", "confidence": 0.75, "reason": "Factual question pattern detected."}
    return {"query_type": "ambiguous", "confidence": 0.5, "reason": "No clear pattern matched; may need clarification."}


def classify_query(query: str, memory_context: str = "") -> dict:
    if not llm_client.has_key():
        result = _heuristic_classify(query)
    else:
        system = (
            "You are a Query Understanding Agent in a RAG system. Classify the user's query "
            "into exactly one of: factual, procedural, comparative, ambiguous. "
            "'ambiguous' means the query is vague, incomplete, has multiple possible interpretations, "
            "or lacks context even given the recent conversation. "
            "Respond ONLY with compact JSON: {\"query_type\": \"...\", \"confidence\": 0.0-1.0, \"reason\": \"...\"}"
        )
        user = f"Recent conversation context:\n{memory_context or '(none)'}\n\nQuery: {query}"
        try:
            raw = llm_client.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0, max_tokens=150,
            )
            raw = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            result = json.loads(raw)
            if result.get("query_type") not in CATEGORIES:
                result = _heuristic_classify(query)
        except Exception:
            result = _heuristic_classify(query)

    result["needs_clarification"] = result["query_type"] == "ambiguous"
    return result
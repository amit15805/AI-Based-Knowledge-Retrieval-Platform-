"""
Response Generation Agent (Milestone 2 / M2.3)
Produces TWO short answers for every query:
  1. pdf_answer - grounded ONLY in the retrieved document chunks (no outside knowledge)
  2. ai_answer  - the model's own general knowledge, independent of the document
Both are forced to a single plain-English sentence, 10-20 words, with no
markdown formatting (no **, #, tables, bullet lists) so they render cleanly
as plain chat text.
"""
import re
import llm_client

WORD_LIMIT_INSTRUCTION = (
    "Respond in EXACTLY ONE plain sentence of 10 to 20 words. "
    "Do not use markdown: no **bold**, no #headers, no bullet points, no numbered lists, "
    "no tables, no backticks. Plain conversational English only."
)


def _strip_markdown(text: str) -> str:
    """Safety net in case the model still emits markdown despite instructions."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)      # **bold**
    text = re.sub(r"\*(.*?)\*", r"\1", text)           # *italic*
    text = re.sub(r"`{1,3}(.*?)`{1,3}", r"\1", text)   # `code`
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # # headers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)       # - bullets
    text = re.sub(r"\|", " ", text)                    # table pipes
    text = re.sub(r"^\s*-{2,}\s*$", "", text, flags=re.MULTILINE)      # table separators
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", " ", text).strip()
    return text


def _compute_confidence(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    scores = [c["relevance_score"] for c in chunks[:3]]
    return round(sum(scores) / len(scores), 3)


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        parts.append(
            f"[Source: {c['document_name']} | chunk {c['chunk_index']} | score {c['relevance_score']:.2f}]\n"
            f"{c['chunk_text']}"
        )
    return "\n\n".join(parts)


def _generate_pdf_answer(query: str, chunks: list[dict], memory_context: str) -> str:
    if not chunks:
        return "No relevant information was found in the uploaded document for this query."

    if not llm_client.has_key():
        stitched = " ".join(c["chunk_text"] for c in chunks[:1])
        return _strip_markdown(stitched)[:150] + "..."

    context = _build_context(chunks)
    system = (
        "You are the Response Generation Agent in a RAG system. Answer using ONLY the provided "
        "document context. Do not use outside knowledge and do not invent facts. "
        f"{WORD_LIMIT_INSTRUCTION} If the context does not answer the question, say so in one short sentence."
    )
    user = (
        (f"Conversation context:\n{memory_context}\n\n" if memory_context else "")
        + f"Document context:\n{context}\n\nQuestion: {query}"
    )
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=80,
        )
        return _strip_markdown(raw)
    except Exception as e:
        return f"(LLM call failed: {e})"


def _generate_ai_answer(query: str, memory_context: str) -> str:
    if not llm_client.has_key():
        return "AI general-knowledge answers require a free Groq API key — see backend/config.py."

    system = (
        "You are a helpful general-knowledge AI assistant, answering independently of any uploaded document. "
        f"{WORD_LIMIT_INSTRUCTION}"
    )
    user = (f"Conversation context:\n{memory_context}\n\n" if memory_context else "") + f"Question: {query}"
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4, max_tokens=80,
        )
        return _strip_markdown(raw)
    except Exception as e:
        return f"(AI answer failed: {e})"


def generate_response(query: str, retrieval_result: dict, query_type: str, memory_context: str = "") -> dict:
    chunks = retrieval_result.get("chunks", [])
    confidence = _compute_confidence(chunks)

    sources = [
        {
            "document_name": c["document_name"],
            "chunk_id": c["chunk_id"],
            "chunk_index": c["chunk_index"],
            "relevance_score": round(c["relevance_score"], 3),
            "excerpt": c["chunk_text"][:220],
        }
        for c in chunks
    ]

    pdf_answer = _generate_pdf_answer(query, chunks, memory_context)
    ai_answer = _generate_ai_answer(query, memory_context)

    return {
        "pdf_answer": pdf_answer,
        "ai_answer": ai_answer,
        "sources": sources,
        "confidence": confidence,
        "grounded": bool(chunks),
    }
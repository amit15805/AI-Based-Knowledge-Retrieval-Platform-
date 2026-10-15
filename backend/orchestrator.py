
"""
Multi-Agent Orchestration Layer (Milestone 2 / M2.4)
Sequential flow:
  User Query -> Memory context -> Query Understanding -> (Clarification if ambiguous)
  -> Retrieval -> Response Generation (PDF answer + AI answer) -> Memory update
  -> Analytics log -> Final Response
Standard request/response format between agents; centralized error handling.
"""
from typing import Optional

from agents import query_understanding, retrieval, clarification, response_generation, memory
import analytics


def handle_query(session_id: str, query: str, clarification_answer: Optional[str] = None) -> dict:
    try:
        memory_context = memory.get_context(session_id)

        effective_query = query
        if clarification_answer:
            effective_query = clarification.refine_query(query, clarification_answer)

        # --- Query Understanding Agent ---
        try:
            classification = query_understanding.classify_query(effective_query, memory_context)
        except Exception as e:
            return _error_response(session_id, query, f"Query classification failed: {e}")

        if classification["needs_clarification"] and not clarification_answer:
            question = clarification.generate_clarification_question(
                effective_query, classification.get("reason", "")
            )
            analytics.log_query(session_id, query, "ambiguous", 0.0, grounded=False, needs_clarification=True)
            return {
                "status": "needs_clarification",
                "clarification_question": question,
                "original_query": query,
                "classification": classification,
            }

        # --- Retrieval Agent ---
        try:
            retrieval_result = retrieval.retrieve(effective_query)
        except Exception as e:
            return _error_response(session_id, query, f"Retrieval failed: {e}")

        # --- Response Generation Agent (PDF answer + AI answer) ---
        try:
            gen_result = response_generation.generate_response(
                effective_query, retrieval_result, classification["query_type"], memory_context
            )
        except Exception as e:
            return _error_response(session_id, query, f"Response generation failed: {e}")

        # --- Memory update (store the document-grounded answer as the recap) ---
        memory.add_turn(
            session_id, query, gen_result["pdf_answer"], classification["query_type"],
            documents=[s["document_name"] for s in gen_result["sources"]],
        )

        # --- Analytics ---
        analytics.log_query(
            session_id, query, classification["query_type"], gen_result["confidence"],
            grounded=gen_result["grounded"], needs_clarification=False,
            source_documents=[s["document_name"] for s in gen_result["sources"]],
        )

        return {
            "status": "answered",
            "query": query,
            "effective_query": effective_query,
            "classification": classification,
            "pdf_answer": gen_result["pdf_answer"],
            "ai_answer": gen_result["ai_answer"],
            "sources": gen_result["sources"],
            "confidence": gen_result["confidence"],
            "grounded": gen_result["grounded"],
        }

    except Exception as e:
        return _error_response(session_id, query, f"Unexpected orchestration error: {e}")


def _error_response(session_id: str, query: str, message: str) -> dict:
    analytics.log_query(session_id, query, "error", 0.0, grounded=False, needs_clarification=False)
    return {"status": "error", "message": message}

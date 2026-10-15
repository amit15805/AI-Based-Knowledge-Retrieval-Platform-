"""
Clarification Agent (Milestone 3 / M3.1)
Generates a targeted follow-up question for ambiguous/incomplete queries,
and combines the original query + user's clarification into a refined query.
"""
import llm_client


def generate_clarification_question(query: str, reason: str = "") -> str:
    if not llm_client.has_key():
        return (
            f"Could you clarify what you mean by \"{query}\"? "
            "For example, which document, topic, or time period are you asking about?"
        )
    system = (
        "You are a Clarification Agent in a RAG system. The user's query is ambiguous. "
        "Ask ONE short, specific follow-up question that would resolve the ambiguity. "
        "Do not answer the query. Keep it under 25 words."
    )
    user = f"Ambiguous query: {query}\nWhy it's ambiguous: {reason}"
    try:
        return llm_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3, max_tokens=60,
        )
    except Exception:
        return f"Could you clarify what you mean by \"{query}\"?"


def refine_query(original_query: str, clarification_answer: str) -> str:
    """Combine the original ambiguous query with the user's clarification response."""
    return f"{original_query.strip()} — clarification: {clarification_answer.strip()}"
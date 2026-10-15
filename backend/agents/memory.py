
"""
Conversation Memory Agent (Milestone 3 / M3.2)
In-memory only, per session_id. Intentionally NOT persisted to disk:
chat history is cleared whenever the backend server is restarted/quit.
Kept separate from the permanent knowledge base (vector store).
"""
import config

_SESSIONS: dict[str, list[dict]] = {}


def add_turn(session_id: str, query: str, answer: str, query_type: str = "", documents: list[str] = None):
    history = _SESSIONS.setdefault(session_id, [])
    history.append({"query": query, "answer": answer, "query_type": query_type, "documents": documents or []})
    if len(history) > config.MAX_MEMORY_TURNS * 5:
        _SESSIONS[session_id] = history[-config.MAX_MEMORY_TURNS * 5:]


def get_context(session_id: str, max_turns: int = None) -> str:
    max_turns = max_turns or config.MAX_MEMORY_TURNS
    history = _SESSIONS.get(session_id, [])[-max_turns:]
    return "\n".join(f"User: {t['query']}\nAssistant: {t['answer'][:300]}" for t in history)


def get_history(session_id: str) -> list[dict]:
    return _SESSIONS.get(session_id, [])


def clear(session_id: str):
    _SESSIONS.pop(session_id, None)
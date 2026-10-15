import requests
import config

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def has_key() -> bool:
    return bool(config.GROQ_API_KEY and config.GROQ_API_KEY.strip())


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 600) -> str:
    if not has_key():
        raise RuntimeError("GROQ_API_KEY not set in backend/config.py")

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens + 800,   # gpt-oss thinks first, so leave headroom
    }
    if config.GROQ_MODEL.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"

    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")
    content = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError("Model returned an empty response")
    return content
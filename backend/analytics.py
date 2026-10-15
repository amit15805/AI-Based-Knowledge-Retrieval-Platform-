


"""
Query Analytics and Knowledge Gap Detection Module (Milestone 4 / M4.1)
Logs every query with its classification, confidence, source documents, and
outcome to a local JSONL file, and provides filterable aggregated stats +
knowledge-gap detection.
"""
import os
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta

import config

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "analytics_log.jsonl")

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "what", "how", "why", "do",
    "does", "of", "to", "in", "on", "for", "and", "or", "it", "this", "that",
    "with", "about", "can", "you", "i", "me", "my", "your", "please",
}


def log_query(session_id: str, query: str, query_type: str, confidence: float,
              grounded: bool, needs_clarification: bool, source_documents: list[str] = None):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "query": query,
        "query_type": query_type,
        "confidence": confidence,
        "grounded": grounded,
        "needs_clarification": needs_clarification,
        "low_confidence": confidence < config.LOW_CONFIDENCE_THRESHOLD,
        "unanswered": (not grounded) or confidence == 0.0,
        "source_documents": sorted(set(source_documents or [])),
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _load_records():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confidence_bucket(c: float) -> str:
    if c >= 0.6:
        return "high"
    if c >= config.LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _apply_filters(records, query_type=None, confidence_level=None, days=None, document=None):
    out = records
    if query_type and query_type != "all":
        out = [r for r in out if r["query_type"] == query_type]
    if confidence_level and confidence_level != "all":
        out = [r for r in out if _confidence_bucket(r["confidence"]) == confidence_level]
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        out = [r for r in out if datetime.fromisoformat(r["timestamp"]) >= cutoff]
    if document and document != "all":
        out = [r for r in out if document in (r.get("source_documents") or [])]
    return out


def get_stats(query_type=None, confidence_level=None, days=None, document=None):
    all_records = _load_records()
    records = _apply_filters(all_records, query_type, confidence_level, days, document)
    total = len(records)

    if total == 0:
        return {
            "total_queries": 0, "avg_confidence": 0, "low_confidence_count": 0,
            "unanswered_count": 0, "clarification_count": 0,
            "query_type_breakdown": {}, "knowledge_gaps": [],
            "confidence_breakdown": {"high": 0, "medium": 0, "low": 0},
            "queries_by_day": {}, "available_documents": _known_documents(all_records),
            "available_query_types": sorted({r["query_type"] for r in all_records}),
        }

    avg_conf = round(sum(r["confidence"] for r in records) / total, 3)
    low_conf = sum(1 for r in records if r["low_confidence"])
    unanswered = sum(1 for r in records if r["unanswered"])
    clarifications = sum(1 for r in records if r["needs_clarification"])
    type_counts = Counter(r["query_type"] for r in records)
    conf_buckets = Counter(_confidence_bucket(r["confidence"]) for r in records)

    # Queries per day (for a simple trend view)
    by_day = Counter(r["timestamp"][:10] for r in records)

    # Knowledge gap detection: repeated unanswered/low-confidence queries, grouped by keyword theme
    gap_words = Counter()
    for r in records:
        if r["unanswered"] or r["low_confidence"]:
            words = re.findall(r"[a-zA-Z]{4,}", r["query"].lower())
            for w in words:
                if w not in STOPWORDS:
                    gap_words[w] += 1
    knowledge_gaps = [{"theme": w, "occurrences": c} for w, c in gap_words.most_common(10) if c > 1]

    return {
        "total_queries": total,
        "avg_confidence": avg_conf,
        "low_confidence_count": low_conf,
        "unanswered_count": unanswered,
        "clarification_count": clarifications,
        "query_type_breakdown": dict(type_counts),
        "confidence_breakdown": {
            "high": conf_buckets.get("high", 0),
            "medium": conf_buckets.get("medium", 0),
            "low": conf_buckets.get("low", 0),
        },
        "queries_by_day": dict(sorted(by_day.items())),
        "knowledge_gaps": knowledge_gaps,
        "available_documents": _known_documents(all_records),
        "available_query_types": sorted({r["query_type"] for r in all_records}),
    }


def _known_documents(records):
    docs = set()
    for r in records:
        docs.update(r.get("source_documents") or [])
    return sorted(docs)


def get_recent(limit: int = 20, query_type=None, confidence_level=None, days=None, document=None):
    """Raw recent query log, most recent first — used by the dashboard's detail table."""
    records = _apply_filters(_load_records(), query_type, confidence_level, days, document)
    return list(reversed(records))[:limit]

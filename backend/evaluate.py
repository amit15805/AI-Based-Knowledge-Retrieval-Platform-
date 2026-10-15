"""
End-to-End Evaluation Harness (Milestone 4 / M4.2)
===================================================
Runs every query in eval/test_queries.json through the LIVE API
(/api/query) and measures, per domain and per query type:

  - routing accuracy            (Query Understanding picked the expected type)
  - clarification accuracy      (ambiguous -> asked; clear -> did NOT ask)
  - unnecessary clarification   (clear queries that wrongly triggered a follow-up)
  - evidence keyword hit rate   (expected keywords found in answer / retrieved evidence)
  - unavailable-info handling   (out-of-document queries correctly flagged low-confidence)
  - average confidence, response time, and LLM errors (e.g. rate limits)

Usage (the server must be running in another terminal):
    cd backend
    python evaluate.py
    python evaluate.py --delay 6          # slower, safer for Groq's free rate limit
    python evaluate.py --base-url http://127.0.0.1:8000 --queries ../eval/test_queries.json

Outputs:
    eval/evaluation_report.md    human-readable report (paste into your project report)
    eval/evaluation_results.json raw per-query results
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.join(HERE, "..", "eval")
TYPES = ["factual", "procedural", "comparative", "ambiguous"]


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load_tests(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tests = data["tests"] if isinstance(data, dict) else data
    for i, t in enumerate(tests):
        if "query" not in t or "expected_type" not in t:
            raise ValueError(f"Test #{i + 1} needs both 'query' and 'expected_type'.")
        t.setdefault("domain", "default")
        t.setdefault("answerable", t["expected_type"] != "ambiguous")
        t.setdefault("expected_keywords", [])
    return tests


# ----------------------------------------------------------------------------
# Running one query
# ----------------------------------------------------------------------------
def run_one(base_url, test, low_threshold):
    result = {
        "domain": test["domain"],
        "query": test["query"],
        "expected_type": test["expected_type"],
        "answerable": test["answerable"],
        "predicted_type": None,
        "status": None,
        "confidence": 0.0,
        "grounded": False,
        "seconds": 0.0,
        "pdf_answer": "",
        "ai_answer": "",
        "top_source": None,
        "routing_correct": False,
        "clarification_triggered": False,
        "clarification_correct": False,
        "keyword_hit": None,
        "correctly_rejected": None,
        "llm_error": False,
        "error": None,
    }
    started = time.time()
    try:
        resp = requests.post(
            f"{base_url}/api/query",
            data={"session_id": f"eval-{test['domain']}", "query": test["query"]},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # server down, timeout, 500, ...
        result["status"] = "request_failed"
        result["error"] = str(e)
        result["seconds"] = round(time.time() - started, 2)
        return result
    result["seconds"] = round(time.time() - started, 2)

    status = data.get("status")
    result["status"] = status
    result["predicted_type"] = (data.get("classification") or {}).get("query_type")
    result["confidence"] = float(data.get("confidence") or 0.0)
    result["grounded"] = bool(data.get("grounded"))
    result["pdf_answer"] = data.get("pdf_answer", "") or ""
    result["ai_answer"] = data.get("ai_answer", "") or ""
    sources = data.get("sources", []) or []
    if sources:
        result["top_source"] = f"{sources[0].get('document_name')} #{sources[0].get('chunk_index')}"
    if status == "error":
        result["error"] = data.get("message")

    expected = test["expected_type"]
    result["routing_correct"] = result["predicted_type"] == expected
    result["clarification_triggered"] = status == "needs_clarification"
    result["clarification_correct"] = result["clarification_triggered"] == (expected == "ambiguous")
    result["llm_error"] = any(
        str(a).startswith(("(LLM call failed", "(AI answer failed"))
        for a in (result["pdf_answer"], result["ai_answer"])
    )

    keywords = [k.lower() for k in test["expected_keywords"]]
    if status == "answered" and test["answerable"] and keywords:
        evidence = (result["pdf_answer"] + " " + " ".join(s.get("excerpt", "") for s in sources)).lower()
        result["keyword_hit"] = any(k in evidence for k in keywords)

    if not test["answerable"] and status == "answered":
        result["correctly_rejected"] = (not result["grounded"]) or result["confidence"] < low_threshold

    return result


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------
def rate(values):
    vals = [v for v in values if v is not None]
    return (sum(1 for v in vals if v) / len(vals)) if vals else None


def metrics(rows):
    ok_rows = [r for r in rows if r["status"] != "request_failed"]
    answered = [r for r in ok_rows if r["status"] == "answered" and r["answerable"]]
    seconds = [r["seconds"] for r in ok_rows]
    return {
        "n": len(rows),
        "request_failures": len(rows) - len(ok_rows),
        "llm_errors": sum(1 for r in ok_rows if r["llm_error"]),
        "routing_accuracy": rate([r["routing_correct"] for r in ok_rows]),
        "clarification_accuracy": rate([r["clarification_correct"] for r in ok_rows]),
        "unnecessary_clarification": rate(
            [r["clarification_triggered"] for r in ok_rows if r["expected_type"] != "ambiguous"]
        ),
        "keyword_hit_rate": rate([r["keyword_hit"] for r in ok_rows]),
        "unavailable_handled": rate([r["correctly_rejected"] for r in ok_rows]),
        "avg_confidence_answerable": (
            statistics.mean(r["confidence"] for r in answered) if answered else None
        ),
        "avg_seconds": statistics.mean(seconds) if seconds else None,
        "median_seconds": statistics.median(seconds) if seconds else None,
        "max_seconds": max(seconds) if seconds else None,
    }


def group_metrics(results, key, order=None):
    groups = {}
    for r in results:
        groups.setdefault(r[key], []).append(r)
    keys = order if order else sorted(groups)
    return {k: metrics(groups[k]) for k in keys if k in groups}


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def pct(v):
    return "n/a" if v is None else f"{v * 100:.0f}%"


def num(v, digits=2):
    return "n/a" if v is None else f"{v:.{digits}f}"


def metrics_table(title_col, grouped):
    lines = [
        f"| {title_col} | Queries | Routing | Clarification | Unneeded clarif. | Evidence hit | Unavailable handled | Avg conf. | Avg time (s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, m in grouped.items():
        lines.append(
            f"| {name} | {m['n']} | {pct(m['routing_accuracy'])} | {pct(m['clarification_accuracy'])} "
            f"| {pct(m['unnecessary_clarification'])} | {pct(m['keyword_hit_rate'])} "
            f"| {pct(m['unavailable_handled'])} | {pct(m['avg_confidence_answerable'])} "
            f"| {num(m['avg_seconds'])} |"
        )
    return "\n".join(lines)


def build_report(results, base_url):
    overall = metrics(results)
    by_domain = group_metrics(results, "domain")
    by_type = group_metrics(results, "expected_type", order=TYPES)

    lines = [
        "# End-to-End Evaluation Report (Milestone 4 / M4.2)",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Server: {base_url}",
        f"- Domains tested: {len(by_domain)} ({', '.join(by_domain)})",
        f"- Total queries: {overall['n']}  |  request failures: {overall['request_failures']}  "
        f"|  LLM errors (e.g. rate limits): {overall['llm_errors']}",
        "",
        "## Overall",
        "",
        metrics_table("Scope", {"ALL": overall}),
        "",
        "Response time: "
        f"avg {num(overall['avg_seconds'])}s, median {num(overall['median_seconds'])}s, "
        f"max {num(overall['max_seconds'])}s per query (includes 3 LLM calls).",
        "",
        "## By domain",
        "",
        metrics_table("Domain", by_domain),
        "",
        "## By query type",
        "",
        metrics_table("Expected type", by_type),
        "",
        "## What the columns mean",
        "",
        "- **Routing** - Query Understanding Agent predicted the expected query type.",
        "- **Clarification** - ambiguous queries triggered a follow-up AND clear queries did not.",
        "- **Unneeded clarif.** - share of clear queries that wrongly asked a follow-up (lower is better).",
        "- **Evidence hit** - at least one expected keyword appeared in the document answer or retrieved excerpts.",
        "- **Unavailable handled** - queries whose answer is NOT in the documents were flagged low-confidence / ungrounded.",
        "- **Avg conf.** - mean grounding confidence on answerable queries.",
        "",
        "## Per-query detail",
        "",
        "| # | Domain | Query | Expected | Predicted | Status | Conf. | Top source | Routing | Evidence | Time (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        evidence = "-" if r["keyword_hit"] is None else ("yes" if r["keyword_hit"] else "NO")
        lines.append(
            f"| {i} | {r['domain']} | {r['query']} | {r['expected_type']} | {r['predicted_type'] or '-'} "
            f"| {r['status']} | {pct(r['confidence'])} | {r['top_source'] or '-'} "
            f"| {'ok' if r['routing_correct'] else 'MISS'} | {evidence} | {r['seconds']} |"
        )

    problems = [r for r in results if (not r["routing_correct"]) or r["keyword_hit"] is False
                or r["correctly_rejected"] is False or not r["clarification_correct"] or r["error"]]
    lines += ["", "## Items to investigate", ""]
    if not problems:
        lines.append("None - every test passed its checks.")
    else:
        for r in problems:
            reasons = []
            if not r["routing_correct"]:
                reasons.append(f"routed as '{r['predicted_type']}' (expected '{r['expected_type']}')")
            if not r["clarification_correct"]:
                reasons.append("clarification behaviour wrong")
            if r["keyword_hit"] is False:
                reasons.append("expected evidence not found")
            if r["correctly_rejected"] is False:
                reasons.append("out-of-document query was answered with high confidence")
            if r["error"]:
                reasons.append(f"error: {r['error']}")
            lines.append(f"- [{r['domain']}] \"{r['query']}\" - " + "; ".join(reasons))
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="End-to-end evaluation of the RAG platform (M4.2).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--queries", default=os.path.join(EVAL_DIR, "test_queries.json"))
    parser.add_argument("--out", default=os.path.join(EVAL_DIR, "evaluation_report.md"))
    parser.add_argument("--json-out", default=os.path.join(EVAL_DIR, "evaluation_results.json"))
    parser.add_argument("--delay", type=float, default=4.0,
                        help="seconds to wait between queries (protects Groq's free rate limit)")
    parser.add_argument("--low-threshold", type=float, default=0.35,
                        help="confidence below this counts as low-confidence (match LOW_CONFIDENCE_THRESHOLD)")
    args = parser.parse_args()

    tests = load_tests(args.queries)
    domains = sorted({t["domain"] for t in tests})
    print(f"Loaded {len(tests)} test queries across {len(domains)} domain(s): {', '.join(domains)}")
    if len(domains) < 3:
        print("WARNING: Milestone 4 asks for at least 3 distinct domains - add more to eval/test_queries.json.")

    try:
        status = requests.get(f"{args.base_url}/api/status", timeout=10).json()
    except Exception as e:
        print(f"ERROR: cannot reach the server at {args.base_url} ({e}).")
        print("Start it first:  cd backend && uvicorn main:app --port 8000")
        sys.exit(1)
    print(f"Server OK - {status.get('documents_indexed', 0)} docs / {status.get('chunks_indexed', 0)} chunks indexed.")
    if not status.get("documents_indexed"):
        print("WARNING: knowledge base is empty - upload your documents before evaluating.")
    if not status.get("llm_key_configured"):
        print("WARNING: no LLM key configured - classification uses the heuristic fallback only.")

    results = []
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] ({test['domain']}) {test['query']}")
        r = run_one(args.base_url, test, args.low_threshold)
        flag = "ok" if r["routing_correct"] else "MISS"
        print(f"      -> status={r['status']} type={r['predicted_type']} conf={r['confidence']:.2f} "
              f"routing={flag} time={r['seconds']}s" + (f"  ERROR: {r['error']}" if r["error"] else ""))
        results.append(r)
        if i < len(tests):
            time.sleep(args.delay)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_report(results, args.base_url))
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    m = metrics(results)
    print("\n=== SUMMARY ===")
    print(f"Routing accuracy:          {pct(m['routing_accuracy'])}")
    print(f"Clarification accuracy:    {pct(m['clarification_accuracy'])}")
    print(f"Evidence keyword hit rate: {pct(m['keyword_hit_rate'])}")
    print(f"Unavailable info handled:  {pct(m['unavailable_handled'])}")
    print(f"Avg response time:         {num(m['avg_seconds'])}s")
    print(f"\nReport written to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()

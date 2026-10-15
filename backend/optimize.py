"""
Retrieval Optimization Sweep (Milestone 4 / M4.3)
==================================================
Benchmarks different chunk sizes, chunk overlaps, Top-K values and
relevance thresholds on YOUR documents + YOUR test queries, then ranks the
settings and tells you which values to put in backend/config.py.

It is retrieval-only (embeddings + FAISS) so it needs NO LLM calls: it is
free, fast, and never touches your live knowledge base (it builds temporary
in-memory indexes).

Usage:
    cd backend
    python optimize.py --docs-dir ../sample_docs
    python optimize.py --docs-dir ../sample_docs --chunk-sizes 300,500,800 --overlaps 50,100,150

Put the PDFs/DOCX/TXT/CSV files you want to benchmark in --docs-dir (copy the
same ones you uploaded to the app). Queries come from eval/test_queries.json
(uses 'expected_keywords' and 'answerable'; ambiguous queries are skipped).

Outputs:
    eval/optimization_report.md      ranked comparison + before/after vs your current config
    eval/optimization_results.json   raw numbers
"""
import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EVAL_DIR = os.path.join(HERE, "..", "eval")
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".csv"}


# ----------------------------------------------------------------------------
# Pure helpers (no heavy imports - easy to test)
# ----------------------------------------------------------------------------
def parse_list(text, cast):
    return [cast(x) for x in text.split(",") if x.strip()]


def mean_or_none(values):
    return statistics.mean(values) if values else None


def chunk_matches(chunks, keywords):
    """True if any expected keyword appears in any of the given chunks."""
    blob = " ".join(c["chunk_text"] for c in chunks).lower()
    return any(k.lower() in blob for k in keywords)


def evaluate_config(store, tests, qvecs, top_k, threshold, low_conf):
    """Run every retrieval test against one store + one (top_k, threshold) setting."""
    hit = {1: [], 3: [], 5: []}
    rejection, grounded, top1, times = [], [], [], []

    for t in tests:
        started = time.perf_counter()
        raw = store.search(qvecs[t["query"]], top_k=top_k)
        times.append((time.perf_counter() - started) * 1000)
        raw.sort(key=lambda r: r["relevance_score"], reverse=True)
        kept = [r for r in raw if r["relevance_score"] >= threshold]
        confidence = mean_or_none([r["relevance_score"] for r in kept[:3]]) or 0.0

        if t["answerable"]:
            if raw:
                top1.append(raw[0]["relevance_score"])
            grounded.append(bool(kept))
            keywords = t.get("expected_keywords") or []
            if keywords:
                for k in hit:
                    hit[k].append(chunk_matches(kept[:k], keywords))
        else:
            rejection.append(confidence < low_conf)

    return {
        "hit1": mean_or_none([float(v) for v in hit[1]]),
        "hit3": mean_or_none([float(v) for v in hit[3]]),
        "hit5": mean_or_none([float(v) for v in hit[5]]),
        "rejection": mean_or_none([float(v) for v in rejection]),
        "grounded": mean_or_none([float(v) for v in grounded]),
        "avg_top1": mean_or_none(top1),
        "search_ms": mean_or_none(times),
    }


def composite_score(m):
    """
    Single ranking number (0-1). Weights: Top-3 hit 50%, Top-1 hit 20%,
    correct rejection of unavailable-info queries 30%. Components with no
    data are dropped and the remaining weights re-normalised.
    """
    parts = [(m["hit3"], 0.5), (m["hit1"], 0.2), (m["rejection"], 0.3)]
    parts = [(v, w) for v, w in parts if v is not None]
    if not parts:
        return 0.0
    total_w = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_w


def pct(v):
    return "n/a" if v is None else f"{v * 100:.0f}%"


def build_report(rows, baseline, docs, n_tests):
    ranked = sorted(rows, key=lambda r: (r["score"], r.get("is_baseline", False)), reverse=True)
    best = ranked[0]
    lines = [
        "# Retrieval Optimization Report (Milestone 4 / M4.3)",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Documents benchmarked: {', '.join(docs)}",
        f"- Retrieval test queries used: {n_tests} (ambiguous queries skipped)",
        f"- Configurations compared: {len(rows)}",
        "",
        "## Recommended settings",
        "",
        "Paste into `backend/config.py`:",
        "",
        "```python",
        f"CHUNK_SIZE = {best['chunk_size']}",
        f"CHUNK_OVERLAP = {best['overlap']}",
        f"TOP_K = {best['top_k']}",
        f"RELEVANCE_THRESHOLD = {best['threshold']}",
        "```",
        "",
        "After changing chunk settings you must re-ingest: delete `data/faiss.index` and "
        "`data/metadata.pkl`, restart the server and upload your documents again.",
        "",
        "## Before vs after",
        "",
        "| | Chunk size | Overlap | Top-K | Threshold | Hit@1 | Hit@3 | Unavailable rejected | Score |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, r in (("Current config (before)", baseline), ("Recommended (after)", best)):
        lines.append(
            f"| {label} | {r['chunk_size']} | {r['overlap']} | {r['top_k']} | {r['threshold']} "
            f"| {pct(r['hit1'])} | {pct(r['hit3'])} | {pct(r['rejection'])} | {r['score']:.3f} |"
        )
    delta = best["score"] - baseline["score"]
    lines += [
        "",
        f"Composite score change: **{delta:+.3f}** "
        "(score = 50% Top-3 hit rate + 20% Top-1 hit rate + 30% correct rejection of unavailable-info queries).",
        "",
        "## All configurations (ranked)",
        "",
        "| Rank | Chunk size | Overlap | Top-K | Threshold | Chunks | Hit@1 | Hit@3 | Hit@5 | Rejected | Grounded | Avg top-1 sim. | Search (ms) | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked, 1):
        marker = " (current)" if r is baseline or r.get("is_baseline") else ""
        top1 = "n/a" if r["avg_top1"] is None else f"{r['avg_top1']:.2f}"
        ms = "n/a" if r["search_ms"] is None else f"{r['search_ms']:.1f}"
        lines.append(
            f"| {i}{marker} | {r['chunk_size']} | {r['overlap']} | {r['top_k']} | {r['threshold']} | {r['chunks']} "
            f"| {pct(r['hit1'])} | {pct(r['hit3'])} | {pct(r['hit5'])} | {pct(r['rejection'])} "
            f"| {pct(r['grounded'])} | {top1} | {ms} | {r['score']:.3f} |"
        )
    lines += [
        "",
        "## How to read this",
        "",
        "- **Hit@k** - share of answerable queries whose expected keyword appears in the top-k kept chunks.",
        "- **Rejected** - share of NOT-in-document queries that ended up below the low-confidence line (higher is better).",
        "- **Grounded** - share of answerable queries that kept at least one chunk above the threshold.",
        "- A threshold that is too low lets irrelevant chunks through (poor rejection); too high drops useful evidence (poor Grounded / Hit@k).",
        "- Larger chunks give more context but dilute similarity; smaller chunks are precise but may split an answer.",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Heavy parts (embeddings / FAISS) - imported lazily
# ----------------------------------------------------------------------------
def collect_docs(folder):
    paths = []
    for name in sorted(os.listdir(folder)):
        if os.path.splitext(name)[1].lower() in ALLOWED_EXT:
            paths.append(os.path.join(folder, name))
    return paths


def build_store(doc_paths, size, overlap):
    import ingestion
    from vector_store import VectorStore

    store = VectorStore(persist=False)  # in-memory only; never touches data/
    for path in doc_paths:
        name = os.path.basename(path)
        ingestion.ingest_document(path, name, uuid.uuid4().hex[:8], name,
                                  target_store=store, size=size, overlap=overlap)
    return store


def main():
    parser = argparse.ArgumentParser(description="Retrieval parameter sweep (M4.3).")
    parser.add_argument("--docs-dir", required=True, help="folder with the documents to benchmark")
    parser.add_argument("--queries", default=os.path.join(EVAL_DIR, "test_queries.json"))
    parser.add_argument("--chunk-sizes", default="300,500,800")
    parser.add_argument("--overlaps", default="50,100,150")
    parser.add_argument("--top-ks", default="3,5,7")
    parser.add_argument("--thresholds", default="0.2,0.25,0.3,0.35")
    parser.add_argument("--out", default=os.path.join(EVAL_DIR, "optimization_report.md"))
    parser.add_argument("--json-out", default=os.path.join(EVAL_DIR, "optimization_results.json"))
    args = parser.parse_args()

    import config
    from embeddings import embed_query
    from evaluate import load_tests

    if not os.path.isdir(args.docs_dir):
        print(f"ERROR: --docs-dir '{args.docs_dir}' is not a folder.")
        sys.exit(1)
    doc_paths = collect_docs(args.docs_dir)
    if not doc_paths:
        print(f"ERROR: no PDF/DOCX/TXT/CSV files found in '{args.docs_dir}'.")
        sys.exit(1)

    tests = [t for t in load_tests(args.queries) if t["expected_type"] != "ambiguous"]
    if not tests:
        print("ERROR: no non-ambiguous test queries found.")
        sys.exit(1)
    if not any(t["answerable"] and t.get("expected_keywords") for t in tests):
        print("WARNING: no answerable queries with expected_keywords - Hit@k cannot be computed.")

    print(f"Documents: {[os.path.basename(p) for p in doc_paths]}")
    print(f"Embedding {len(tests)} test queries...")
    qvecs = {t["query"]: embed_query(t["query"]) for t in tests}

    sizes = parse_list(args.chunk_sizes, int)
    overlaps = parse_list(args.overlaps, int)
    top_ks = parse_list(args.top_ks, int)
    thresholds = parse_list(args.thresholds, float)

    # The current config is always included so the report can show before vs after.
    base = (config.CHUNK_SIZE, config.CHUNK_OVERLAP, config.TOP_K, config.RELEVANCE_THRESHOLD)
    if base[0] not in sizes:
        sizes.append(base[0])
    if base[1] not in overlaps:
        overlaps.append(base[1])
    if base[2] not in top_ks:
        top_ks.append(base[2])
    if base[3] not in thresholds:
        thresholds.append(base[3])

    combos = [(s, o) for s in sizes for o in overlaps if o < s]
    rows, baseline = [], None
    started = time.time()
    for idx, (size, overlap) in enumerate(combos, 1):
        print(f"[{idx}/{len(combos)}] indexing with chunk_size={size}, overlap={overlap} ...")
        store = build_store(doc_paths, size, overlap)
        n_chunks = len(store.metadata)
        for top_k in top_ks:
            for threshold in thresholds:
                m = evaluate_config(store, tests, qvecs, top_k, threshold, config.LOW_CONFIDENCE_THRESHOLD)
                row = {"chunk_size": size, "overlap": overlap, "top_k": top_k,
                       "threshold": threshold, "chunks": n_chunks, **m}
                row["score"] = composite_score(m)
                row["is_baseline"] = (size, overlap, top_k, threshold) == base
                if row["is_baseline"]:
                    baseline = row
                rows.append(row)

    if baseline is None:  # current overlap >= current size, or similar edge case
        baseline = max(rows, key=lambda r: (r["score"], r["is_baseline"]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_report(rows, baseline, [os.path.basename(p) for p in doc_paths], len(tests)))
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    best = max(rows, key=lambda r: (r["score"], r["is_baseline"]))
    print(f"\nTested {len(rows)} configurations in {time.time() - started:.0f}s.")
    print(f"Current : size={baseline['chunk_size']} overlap={baseline['overlap']} top_k={baseline['top_k']} "
          f"threshold={baseline['threshold']}  score={baseline['score']:.3f}")
    print(f"Best    : size={best['chunk_size']} overlap={best['overlap']} top_k={best['top_k']} "
          f"threshold={best['threshold']}  score={best['score']:.3f}")
    print(f"\nReport written to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()

# AI-Based Knowledge Retrieval Platform with Query Resolution System
### Technical Documentation & Project Report (Milestone 4 / M4.4)

> **How to finish this report:** sections 8 and 9 contain *placeholders for your measured results*.
> Run `python evaluate.py` and `python optimize.py` (see section 7), then paste the tables from
> `eval/evaluation_report.md` and `eval/optimization_report.md` into those sections. No numbers in this
> document are invented - everything marked **[PASTE]** must come from your own runs.

---

## 1. Problem Statement
Organisations keep knowledge in scattered PDFs, Word files, text notes and spreadsheets. Keyword search misses
meaning, and a plain chatbot answers from general training data, so it can invent facts and cannot show where an
answer came from. Users need a system that answers **from their own documents**, shows the evidence, asks for
clarification when a question is vague, remembers the conversation, and can be used by voice.

## 2. Objectives
1. Ingest PDF, DOCX, TXT and CSV files into a searchable vector knowledge base.
2. Resolve queries with a multi-agent pipeline: understand -> (clarify) -> retrieve -> generate.
3. Produce answers grounded in retrieved text, with source attribution and a confidence indicator.
4. Provide a second, general-knowledge AI answer so users can compare "from the document" vs "from the model".
5. Support multi-turn conversation memory, voice input and text-to-speech.
6. Expose transparency (retrieved chunks, scores) and analytics (unanswered queries, knowledge gaps).
7. Evaluate and tune retrieval quality on multiple knowledge domains.

## 3. System Design

### 3.1 Architecture
```
Browser (HTML/CSS/JS)                          FastAPI backend (Python)
+---------------------------+  HTTP/JSON  +--------------------------------------------+
| Knowledge Base panel      |<----------->| main.py  (routes, static files, uploads)   |
| Chat + voice (Web Speech) |             |    |                                       |
| Transparency panel        |             |    v                                       |
| Analytics dashboard       |             | orchestrator.py                            |
+---------------------------+             |   Memory -> Query Understanding            |
                                          |   -> Clarification? -> Retrieval           |
 Upload: file -> ingestion.py             |   -> Response Generation (2 answers)       |
   extract -> clean -> chunk              |   -> Memory update -> Analytics log        |
   -> embed (MiniLM) -> FAISS index       +--------------------------------------------+
                                           data/: faiss.index, metadata.pkl, analytics_log.jsonl
                                           uploads/: original files    LLM: Groq API (free tier)
```

### 3.2 Agents
| Agent | File | Responsibility |
|---|---|---|
| Query Understanding | `agents/query_understanding.py` | Classifies a query as factual / procedural / comparative / ambiguous with confidence and reason; keyword heuristic fallback if the LLM is unavailable. |
| Clarification | `agents/clarification.py` | For ambiguous queries asks one short follow-up question; merges the answer with the original query into a refined query. |
| Retrieval | `agents/retrieval.py` | Embeds the query, runs FAISS top-K search, ranks by cosine similarity, drops chunks below `RELEVANCE_THRESHOLD`, handles empty results. |
| Response Generation | `agents/response_generation.py` | Produces a document-grounded answer (retrieved context only) **and** a general AI answer; both one plain sentence of 10-20 words; computes confidence from the top-3 similarity scores. |
| Conversation Memory | `agents/memory.py` | Keeps the last turns per session and passes them as context; in-memory only (cleared on server restart), separate from the knowledge base. |

### 3.3 Knowledge ingestion pipeline
1. **Upload** (`POST /api/upload`) - file saved to `uploads/<id>.<ext>` and kept for later viewing.
2. **Extract** - `pypdf` (PDF), `python-docx` (DOCX), plain read (TXT), `pandas` rows flattened to `col: value` text (CSV).
3. **Clean** - remove private-use bullet glyphs, collapse whitespace.
4. **Chunk** - character window `CHUNK_SIZE` with `CHUNK_OVERLAP`, preferring sentence boundaries.
5. **Embed** - `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs locally, no API key), L2-normalised.
6. **Index** - FAISS `IndexFlatIP` (inner product = cosine on normalised vectors) plus a parallel metadata list, persisted to `data/`.

### 3.4 Query resolution pipeline
`User query` -> memory context -> **Query Understanding** -> if ambiguous: **Clarification question** (user replies, query is refined and re-run) -> **Retrieval** -> **Response Generation** (document answer + AI answer + sources + confidence) -> memory update -> analytics log -> response to UI. Each stage is wrapped in error handling; failures return `{"status": "error"}` instead of crashing.

### 3.5 Data models
**Chunk metadata** (stored with each vector)
```json
{"document_name": "notes.pdf", "document_id": "a1b2c3d4", "stored_filename": "a1b2c3d4.pdf",
 "chunk_id": "a1b2c3d4-7", "chunk_index": 7, "chunk_text": "...", "source_type": "pdf"}
```
**Query response** (`POST /api/query`)
```json
{"status": "answered", "query": "...", "classification": {"query_type": "factual", "confidence": 0.8,
 "reason": "...", "needs_clarification": false}, "pdf_answer": "...", "ai_answer": "...",
 "sources": [{"document_name": "...", "chunk_id": "...", "chunk_index": 7, "relevance_score": 0.71, "excerpt": "..."}],
 "confidence": 0.68, "grounded": true}
```
Other statuses: `needs_clarification` (with `clarification_question`, `original_query`) and `error` (with `message`).

**Analytics record** (one JSON line per query in `data/analytics_log.jsonl`): timestamp, session_id, query, query_type, confidence, grounded, needs_clarification, low_confidence, unanswered, source_documents.

### 3.6 API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Web UI |
| POST | `/api/upload` | Ingest a document |
| POST | `/api/query` | Run the multi-agent pipeline (`session_id`, `query`, optional `clarification_answer`) |
| GET | `/api/status` | Knowledge-base stats, document list, LLM key/model status |
| GET | `/api/history/{session_id}` | Conversation memory for a session |
| GET | `/api/analytics` | Aggregates; filters `query_type`, `confidence_level`, `days`, `document` |
| GET | `/api/analytics/recent` | Recent query log with the same filters |
| GET | `/uploads/<file>` | View/download an ingested original |

### 3.7 Configuration (`backend/config.py`)
`GROQ_API_KEY`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `RELEVANCE_THRESHOLD`, `LOW_CONFIDENCE_THRESHOLD`, `MAX_MEMORY_TURNS`.

### 3.8 Environment & deployment
Python 3.10-3.12, `pip install -r requirements.txt`, then `cd backend && uvicorn main:app --reload --port 8000`. Browser: Chrome or Edge for voice features. First run downloads the embedding model (~90 MB). Needs internet only for the Groq API and the first model download.

## 4. Implementation Summary by Milestone
- **M1** - ingestion module (4 formats), chunking, embeddings, FAISS index, basic semantic retrieval.
- **M2** - Query Understanding, Retrieval and Response Generation agents; orchestration layer; source attribution and confidence.
- **M3** - Clarification and Memory agents; Web Speech voice input and text-to-speech; transparency panel.
- **M4** - analytics dashboard with filters and knowledge-gap detection; evaluation harness; retrieval tuning sweep; this report.

## 5. Query Analytics & Knowledge Gap Detection (M4.1)
Every query is logged with type, confidence, grounding status, clarification flag and the documents used. The dashboard (**Full Dashboard** button) shows totals, average confidence, a query-type chart, a confidence distribution, detected knowledge gaps and a recent-query table, filterable by query type, confidence level, time range and document. A *knowledge gap* is a keyword theme that recurs across low-confidence or unanswered queries - a signal that the knowledge base lacks documents on that topic. Analytics are stored separately from the vector store.

## 6. Testing Approach (M4.2)
`backend/evaluate.py` drives the live API with `eval/test_queries.json` (factual, procedural, comparative, ambiguous and unavailable-information queries, grouped by domain) and measures routing accuracy, clarification accuracy, unnecessary clarification, evidence hit rate, unavailable-information handling, confidence and response time. Memory is isolated per domain (`eval-<domain>` sessions) to check that one domain does not bleed into another. **Use at least three distinct domains** (for example technical notes, a research paper, and a policy/handbook document).

Manual checks to record alongside the automated run: multi-turn follow-ups ("what about its limitations?"), a clarification round-trip, voice query + read-aloud in Chrome, and that the transparency panel's chunks match the answer.

## 7. Optimization Approach (M4.3)
`backend/optimize.py` builds temporary in-memory indexes for each chunk size/overlap combination, then evaluates every Top-K and threshold on the same index using your test queries. It ranks settings by a composite score (50% Top-3 hit rate, 20% Top-1 hit rate, 30% correct rejection of unavailable-information queries) and compares the **current config (before)** with the **recommended config (after)**. Prompt design and agent routing were tuned by constraining the response prompts (grounded-only context, 10-20 word plain-text answers) and by routing ambiguity through the Clarification Agent.

**To generate your results:**
```bash
cd backend
uvicorn main:app --port 8000          # terminal 1 (upload your documents in the UI first)
python evaluate.py                    # terminal 2 -> eval/evaluation_report.md
python optimize.py --docs-dir ../sample_docs   # -> eval/optimization_report.md
```

## 8. Results
### 8.1 End-to-end evaluation
**[PASTE]** the "Overall", "By domain" and "By query type" tables from `eval/evaluation_report.md`.

### 8.2 Retrieval optimization (before vs after)
**[PASTE]** the "Before vs after" table and the top rows of "All configurations" from `eval/optimization_report.md`, and state which settings you adopted.

### 8.3 Observations
**[WRITE]** two or three sentences on what the numbers show (e.g. which query type routes worst, whether lowering the threshold hurt unavailable-information handling).

## 9. Limitations
- Confidence is derived from **retrieval similarity**, not from verified factual correctness; a high score does not guarantee a correct answer.
- The general-knowledge AI answer is **not grounded** in the documents and can be wrong; it is shown separately and labelled for that reason.
- Conversation memory is in-memory and per browser session; it is cleared when the server restarts.
- Chunking is character-based; very long tables or scanned PDFs without a text layer (no OCR) are not handled well.
- FAISS `IndexFlatIP` does an exact linear scan - fine for thousands of chunks, not for millions.
- Knowledge-gap detection is keyword-frequency based, not semantic clustering.
- Web Speech API works best in Chrome/Edge; text-to-speech offers no pause/resume control.
- Each query makes up to three LLM calls, so Groq's free-tier rate limits can slow or interrupt heavy use.
- No authentication or multi-user separation.

## 10. Future Enhancements
Semantic clustering of unanswered queries; OCR for scanned PDFs; hybrid (BM25 + vector) retrieval and a re-ranker; streaming answers; persistent per-user memory and login; collapsible transparency panel and TTS pause/resume; automated regression tests in CI; scalable vector database (e.g. FAISS IVF/HNSW or a hosted store).

## 11. Final Demonstration Script
1. Upload three documents from different domains; show chunk counts and the View/Download link.
2. Ask a factual, a procedural and a comparative question per domain; point out the two answers, confidence bar and retrieved chunks.
3. Ask a vague question ("tell me more"); show the clarification round-trip.
4. Ask a follow-up without restating context; show memory at work. Switch domains and show no cross-contamination.
5. Use the microphone and read-aloud.
6. Ask two questions the documents cannot answer; open **Full Dashboard**, filter to low confidence, and show them listed as unanswered and as a detected knowledge gap.
7. Show `eval/evaluation_report.md` and `eval/optimization_report.md`.

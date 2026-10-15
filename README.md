
# AI-Based Knowledge Retrieval Platform with Query Resolution System

A multi-agent RAG platform: PDF/DOCX/TXT/CSV ingestion → chunking → embeddings →
vector search → query classification → clarification → grounded response
generation → conversation memory → voice I/O → transparency panel → analytics.

## File Structure

```
rag-platform/
├── requirements.txt          ← single pip install target for everything
├── README.md
├── backend/
│   ├── config.py             ← PASTE YOUR FREE GROQ API KEY HERE (only file to edit)
│   ├── main.py                ← FastAPI app / API routes / serves the frontend
│   ├── orchestrator.py        ← multi-agent orchestration layer (M2.4)
│   ├── ingestion.py            ← Knowledge Base Ingestion Module (M1.3)
│   ├── embeddings.py           ← local, free embedding model wrapper
│   ├── vector_store.py         ← FAISS vector store + metadata persistence
│   ├── llm_client.py           ← Groq (free tier) LLM API wrapper
│   ├── analytics.py            ← Query Analytics & Knowledge Gap module (M4.1)
│   └── agents/
│       ├── query_understanding.py   ← classifies factual/procedural/comparative/ambiguous (M2.1)
│       ├── retrieval.py             ← semantic search + relevance filtering (M2.2)
│       ├── response_generation.py   ← grounded answer + source attribution + confidence (M2.3)
│       ├── clarification.py         ← ambiguity detection & follow-up questions (M3.1)
│       └── memory.py                ← per-session conversation memory (M3.2)
├── static/
│   ├── index.html             ← UI (upload panel, chat, transparency panel)
│   ├── style.css              ← dark and light theme styling
│   └── app.js                 ← fetch calls, Web Speech API (voice + TTS), rendering
├── data/                      ← auto-created: faiss.index, metadata.pkl, analytics_log.jsonl
└── uploads/                   ← auto-created: temp storage during ingestion
```

## 1. Install dependencies

```bash
cd rag-platform
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Add your free API key (the ONLY file you need to edit)

Open `backend/config.py` and paste your key:

```python
GROQ_API_KEY = "gsk_xxxxxxxxxxxxxxxxxxxx"
```

Get a free key in under a minute at **https://console.groq.com/keys** — no credit
card required. Embeddings run 100% locally and never need a key.

> If you leave the key blank, the app still runs in **extractive mode**: it
> retrieves and shows the relevant chunks, but skips LLM-generated natural
> language answers.

## 3. Run the server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** in Chrome or Edge (needed for the Web Speech API
voice features — Firefox/Safari have limited support).

## 4. Use it

1. **Choose File** → pick a PDF/DOCX/TXT/CSV → **Ingest & Analyze**.
2. Type a query, or press the 🎙️ mic button to speak it.
3. The answer appears with a spoken read-aloud (toggle via the TTS checkbox),
   and the right panel shows grounding confidence + the exact source chunks
   used, with relevance scores.
4. If your query is vague, the Clarification Agent will ask a follow-up
   question before answering — just reply in the same input box.
5. Analytics (total queries, avg confidence, unanswered/low-confidence counts)
   update live at the bottom of the right panel; the full knowledge-gap report
   is available at `GET /api/analytics`.
6. Use the theme button in the header to switch between dark and light themes.
   Your choice is saved in this browser.

## Design notes / how it maps to the milestones

- **Ingestion (M1.3):** `ingestion.py` extracts text per format, cleans it,
  splits into ~500-char chunks with 100-char overlap (configurable in
  `config.py`), embeds with `sentence-transformers/all-MiniLM-L6-v2` (local,
  free), and indexes into a FAISS `IndexFlatIP` (cosine similarity).
- **Retrieval (M1.4 / M2.2):** top-K semantic search with a relevance-score
  floor (`RELEVANCE_THRESHOLD`) to drop weak matches; returns doc name, chunk
  id, chunk index and score for every hit.
- **Query Understanding (M2.1):** LLM-based classifier with a keyword-based
  fallback so the app still classifies queries with no API key configured.
- **Response Generation (M2.3):** prompts the LLM to answer using *only* the
  retrieved context, attaches source attribution, and computes a confidence
  score from the top retrieval similarity scores.
- **Orchestration (M2.4):** `orchestrator.py` runs the sequential pipeline
  with per-agent try/except error handling and a standard JSON response
  shape (`status`: `answered` / `needs_clarification` / `error`).
- **Clarification (M3.1) & Memory (M3.2):** ambiguous queries pause the
  pipeline and ask a follow-up; the answer is combined with the original
  query and re-run. Memory is per-`session_id`, capped in length, and kept
  fully separate from the permanent vector store.
- **Voice + TTS (M3.3):** implemented client-side in `app.js` using the
  browser's native `SpeechRecognition` and `speechSynthesis` — zero extra
  backend cost.
- **Transparency Panel (M3.4):** right-hand panel renders confidence % and
  every retrieved chunk (doc, chunk id, score, excerpt) for the last answer.
- **Analytics & Knowledge Gaps (M4.1):** every query is logged to
  `data/analytics_log.jsonl`; `GET /api/analytics` aggregates confidence
  trends, unanswered/low-confidence counts, query-type breakdown, and a
  simple keyword-frequency gap report over repeated low-confidence queries.

## Swapping in a different free LLM

`llm_client.py` is a ~20-line wrapper around one HTTP call — to switch to
another free provider (e.g. Google Gemini's free tier, or a local Ollama
model), just change `GROQ_URL` and the request/response shape there; nothing
else in the codebase needs to change.
"""
=====================================================================
 PASTE YOUR API KEY BELOW — THIS IS THE ONLY FILE YOU NEED TO EDIT.
=====================================================================

This project uses GROQ (https://console.groq.com) as the LLM provider.
Groq has a generous FREE tier, is OpenAI-API compatible, and is very
fast (LPU inference). Embeddings run 100% locally (sentence-transformers)
so they never cost anything and never need a key.

How to get a free key:
  1. Go to https://console.groq.com/keys
  2. Sign up (free) and click "Create API Key"
  3. Paste it below between the quotes.

If you leave this blank, the system still works in "extractive mode":
it will show you the retrieved chunks and a simple concatenated answer,
but without LLM-generated, natural-language responses.
"""

GROQ_API_KEY = ""   # <-- PASTE YOUR FREE GROQ API KEY HERE

# Model used for response generation / classification (free tier).
GROQ_MODEL = "openai/gpt-oss-20b"

# Local embedding model (downloaded automatically the first time, free, offline after that).
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---- RAG tuning knobs (Milestone 4 exposes these as "optimization" params) ----
CHUNK_SIZE = 500          # characters per chunk
CHUNK_OVERLAP = 100       # characters of overlap between chunks
TOP_K = 5                 # how many chunks to retrieve per query
RELEVANCE_THRESHOLD = 0.25  # cosine similarity floor; below this a chunk is discarded
LOW_CONFIDENCE_THRESHOLD = 0.35  # overall response confidence floor for "low confidence" flag
MAX_MEMORY_TURNS = 4       # how many previous turns are kept in conversation memory
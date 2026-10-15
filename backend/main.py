
"""
FastAPI application entry point.
Serves the frontend (static/) and exposes the RAG API:
  POST /api/upload        - ingest a PDF/DOCX/TXT/CSV file (file is kept for later viewing)
  POST /api/query         - run a query through the multi-agent pipeline
  GET  /api/analytics     - query analytics + knowledge gap report
  GET  /api/history/{sid} - conversation history for a session
  GET  /api/status        - knowledge base status (doc list, chunk count, key configured)
  GET  /uploads/...       - serves the original uploaded files (view/download from the KB panel)

Run with:  uvicorn main:app --reload --port 8000   (from inside backend/)
"""
import os
import shutil
import uuid

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import config
import ingestion
import llm_client
from vector_store import store
from agents import memory
import orchestrator
import analytics

app = FastAPI(title="AI-Based Knowledge Retrieval Platform")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".csv"}


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# Serve the original uploaded files so the KB panel can view/download them.
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/status")
def status():
    s = store.stats()
    return {
        "documents_indexed": s["total_documents"],
        "chunks_indexed": s["total_chunks"],
        "documents": store.document_list(),
        "llm_key_configured": llm_client.has_key(),
        "llm_model": config.GROQ_MODEL if llm_client.has_key() else None,
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXT)}"}

    document_id = uuid.uuid4().hex[:8]
    stored_filename = f"{document_id}{ext}"
    save_path = os.path.join(UPLOAD_DIR, stored_filename)
    with open(save_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        # File is kept permanently (not deleted) so it can be viewed later.
        result = ingestion.ingest_document(save_path, file.filename, document_id, stored_filename)
    except Exception as e:
        os.remove(save_path)
        return {"error": f"Ingestion failed: {e}"}

    return {"result": result, "kb_stats": store.stats()}


@app.post("/api/query")
async def query(
    session_id: str = Form(...),
    query: str = Form(...),
    clarification_answer: str = Form(None),
):
    result = orchestrator.handle_query(session_id, query, clarification_answer)
    return result


@app.get("/api/history/{session_id}")
def history(session_id: str):
    return {"history": memory.get_history(session_id)}


@app.get("/api/analytics")
def get_analytics(query_type: str = None, confidence_level: str = None, days: int = None, document: str = None):
    """
    Query Analytics & Knowledge Gap Detection (M4.1).
    Filters: query_type (factual/procedural/comparative/ambiguous/all),
             confidence_level (high/medium/low/all), days (last N days), document (name or 'all').
    """
    return analytics.get_stats(query_type=query_type, confidence_level=confidence_level, days=days, document=document)


@app.get("/api/analytics/recent")
def get_recent_queries(limit: int = 20, query_type: str = None, confidence_level: str = None,
                        days: int = None, document: str = None):
    """Recent query log, most recent first — backs the dashboard's detail table."""
    return {"recent": analytics.get_recent(limit, query_type, confidence_level, days, document)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

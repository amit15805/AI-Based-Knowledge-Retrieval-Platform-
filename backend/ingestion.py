"""
Knowledge Base Ingestion Module (Milestone 1 / M1.3)
Supports PDF, DOCX, TXT, CSV. Extracts text, cleans it, chunks it with
overlap, embeds the chunks, and indexes them into the vector store.
The original file is kept on disk (in /uploads) so it can be viewed
or downloaded later from the Knowledge Base panel.
"""
import os
import re
import pandas as pd
from pypdf import PdfReader
import docx

import config
from embeddings import embed_texts
from vector_store import store as default_store


def extract_text(file_path: str, ext: str) -> str:
    ext = ext.lower()
    if ext == ".pdf":
        reader = PdfReader(file_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    elif ext == ".docx":
        d = docx.Document(file_path)
        return "\n".join(p.text for p in d.paragraphs)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    elif ext == ".csv":
        df = pd.read_csv(file_path)
        lines = []
        for _, row in df.iterrows():
            lines.append(", ".join(f"{c}: {row[c]}" for c in df.columns))
        return "\n".join(lines)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def clean_text(text: str) -> str:
    text = re.sub(r"[\uE000-\uF8FF\uFFFD]", " ", text)  # PDF bullet glyphs / private-use chars
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, size: int = None, overlap: int = None) -> list[str]:
    size = size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            boundary = text.rfind(". ", start, end)
            if boundary != -1 and boundary > start + size * 0.5:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def ingest_document(file_path: str, original_name: str, document_id: str, stored_filename: str,
                     target_store=None, size: int = None, overlap: int = None) -> dict:
    """
    file_path: where the uploaded file currently lives (kept permanently, NOT deleted, for the live app).
    document_id: caller-generated id, also used as the FAISS metadata key.
    stored_filename: the filename under /uploads this document is saved as (for the view/download link).
    target_store: defaults to the live singleton store; pass an ephemeral VectorStore(persist=False)
                  to benchmark alternate chunk_size/overlap settings (used by optimize.py, M4.3)
                  without touching the live knowledge base.
    size/overlap: override config.CHUNK_SIZE / config.CHUNK_OVERLAP for this call only.
    """
    target_store = target_store or default_store
    ext = os.path.splitext(original_name)[1]
    raw_text = extract_text(file_path, ext)
    cleaned = clean_text(raw_text)
    if not cleaned:
        return {"document_name": original_name, "chunks_indexed": 0, "warning": "No extractable text found."}

    chunks = chunk_text(cleaned, size=size, overlap=overlap)
    embeddings = embed_texts(chunks)

    chunk_meta = [
        {
            "document_name": original_name,
            "document_id": document_id,
            "stored_filename": stored_filename,
            "chunk_id": f"{document_id}-{i}",
            "chunk_index": i,
            "chunk_text": chunk,
            "source_type": ext.replace(".", ""),
        }
        for i, chunk in enumerate(chunks)
    ]
    target_store.add(embeddings, chunk_meta)
    return {
        "document_name": original_name,
        "document_id": document_id,
        "stored_filename": stored_filename,
        "chunks_indexed": len(chunks),
    }
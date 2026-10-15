
"""
Vector store: FAISS IndexFlatIP (cosine similarity via normalized vectors)
plus a parallel metadata list (document name, chunk id, chunk text, etc).
Persisted to disk so the knowledge base survives server restarts.
"""
import os
import json
import pickle
import faiss
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INDEX_PATH = os.path.join(DATA_DIR, "faiss.index")
META_PATH = os.path.join(DATA_DIR, "metadata.pkl")

EMBED_DIM = 384  # all-MiniLM-L6-v2


class VectorStore:
    def __init__(self, persist: bool = True):
        """
        persist=False creates an in-memory-only store that never reads or
        writes data/ — used by backend/optimize.py (M4.3) to benchmark
        different chunking/retrieval settings without touching the live
        knowledge base.
        """
        self.persist_enabled = persist
        self.metadata: list[dict] = []
        if not persist:
            self.index = faiss.IndexFlatIP(EMBED_DIM)
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(INDEX_PATH) and os.path.exists(META_PATH):
            self.index = faiss.read_index(INDEX_PATH)
            with open(META_PATH, "rb") as f:
                self.metadata = pickle.load(f)
        else:
            self.index = faiss.IndexFlatIP(EMBED_DIM)

    def add(self, embeddings: np.ndarray, chunk_meta: list[dict]):
        if embeddings.shape[0] == 0:
            return
        self.index.add(embeddings)
        self.metadata.extend(chunk_meta)
        if self.persist_enabled:
            self._persist()

    def search(self, query_embedding: np.ndarray, top_k: int = 5):
        if self.index.ntotal == 0:
            return []
        q = query_embedding.reshape(1, -1)
        scores, idxs = self.index.search(q, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx == -1:
                continue
            meta = dict(self.metadata[idx])
            meta["relevance_score"] = float(score)
            results.append(meta)
        return results

    def document_list(self):
        docs = {}
        for m in self.metadata:
            doc_id = m.get("document_id") or m.get("document_name", "unknown")
            if doc_id not in docs:
                docs[doc_id] = {
                    "document_id": doc_id,
                    "document_name": m.get("document_name", "Unknown document"),
                    "stored_filename": m.get("stored_filename"),
                    "source_type": m.get("source_type"),
                    "chunks": 0,
                }
            docs[doc_id]["chunks"] += 1
        return list(docs.values())

    def stats(self):
        return {"total_chunks": len(self.metadata), "total_documents": len(self.document_list())}

    def _persist(self):
        faiss.write_index(self.index, INDEX_PATH)
        with open(META_PATH, "wb") as f:
            pickle.dump(self.metadata, f)


# Singleton used across the app
store = VectorStore()

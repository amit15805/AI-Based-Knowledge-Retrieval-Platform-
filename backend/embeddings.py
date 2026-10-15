
import numpy as np
from functools import lru_cache
from sentence_transformers import SentenceTransformer
import config


@lru_cache(maxsize=1)
def _get_model():
    return SentenceTransformer(config.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype="float32")
    vecs = _get_model().encode(texts, convert_to_numpy=True, show_progress_bar=False).astype("float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    return vecs / norms


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]
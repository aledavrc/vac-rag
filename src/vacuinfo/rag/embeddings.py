from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from fastembed import TextEmbedding

from vacuinfo.config import Settings


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-12, None)


class Embedder:
    """Embeddings ONNX, sin PyTorch, para que la imagen Docker sea ligera."""

    def __init__(self, settings: Settings) -> None:
        settings.fastembed_cache.mkdir(parents=True, exist_ok=True)
        self.model_name = settings.embedding_model
        self.model = TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=str(settings.fastembed_cache),
        )

    def embed_documents(self, texts: Iterable[str], batch_size: int = 64) -> np.ndarray:
        vectors = list(self.model.embed(list(texts), batch_size=batch_size))
        if not vectors:
            return np.empty((0, 0), dtype=np.float32)
        return _normalize(np.vstack(vectors))

    def embed_query(self, query: str) -> np.ndarray:
        vector = next(iter(self.model.query_embed(query)))
        return _normalize(np.asarray(vector, dtype=np.float32).reshape(1, -1))[0]

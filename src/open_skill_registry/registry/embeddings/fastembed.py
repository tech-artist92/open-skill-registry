import asyncio
import importlib
from typing import List, Optional

from .base import BaseEmbeddingProvider

class FastEmbedProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dimension = 384  # Default for BAAI/bge-small-en-v1.5

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_model(self):
        if self._model is None:
            # Lazy import to avoid loading ONNX models on startup
            fastembed = importlib.import_module("fastembed")
            self._model = fastembed.TextEmbedding(model_name=self.model_name)
        return self._model

    def _embed_texts_sync(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        # FastEmbed returns a generator of numpy arrays
        embeddings_generator = model.embed(texts)
        return [embedding.tolist() if hasattr(embedding, "tolist") else embedding for embedding in embeddings_generator]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Run synchronous embedding in a thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._embed_texts_sync, texts)

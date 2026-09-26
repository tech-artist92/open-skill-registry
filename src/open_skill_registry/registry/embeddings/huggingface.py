from typing import List, Optional
from .base import BaseEmbeddingProvider

class HuggingFaceEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        raise RuntimeError("HuggingFace provider not yet implemented.")

    @property
    def dimension(self) -> int:
        return 384

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

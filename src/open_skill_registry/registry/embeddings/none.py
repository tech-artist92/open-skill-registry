from typing import List
from .base import BaseEmbeddingProvider

class NoOpEmbeddingProvider(BaseEmbeddingProvider):
    @property
    def dimension(self) -> int:
        return 0

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]

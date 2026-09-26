from abc import ABC, abstractmethod
from typing import List

class BaseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass

    async def embed_text(self, text: str) -> List[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

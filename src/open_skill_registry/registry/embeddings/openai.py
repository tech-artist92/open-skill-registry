from typing import List, Optional
from .base import BaseEmbeddingProvider

class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None):
        raise RuntimeError("OpenAI provider not yet implemented.")

    @property
    def dimension(self) -> int:
        return 1536

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

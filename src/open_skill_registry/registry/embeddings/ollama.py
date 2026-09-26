from typing import List, Optional
from .base import BaseEmbeddingProvider

class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, host: Optional[str] = None):
        raise RuntimeError("Ollama provider not yet implemented.")

    @property
    def dimension(self) -> int:
        return 4096

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

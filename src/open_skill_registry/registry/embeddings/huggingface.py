import os
import httpx
from typing import List, Optional
from .base import BaseEmbeddingProvider

class HuggingFaceEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.api_key = api_key or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        self.model_name = model_name
        self._dimension = 384

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model_name}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json={"inputs": texts}
            )
            response.raise_for_status()
            data = response.json()
            
            # The API returns a list of embeddings directly
            return data

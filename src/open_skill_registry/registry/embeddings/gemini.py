import os
import httpx
from typing import List, Optional
from .base import BaseEmbeddingProvider

class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: str = "models/text-embedding-004"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key required")
        
        # Ensure model has "models/" prefix
        self.model_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
        self._dimension = 768

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Using the batchEmbedContents endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:batchEmbedContents"
        
        requests = [{"model": self.model_name, "content": {"parts": [{"text": text}]}} for text in texts]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                json={"requests": requests},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            embeddings = []
            for item in data.get("embeddings", []):
                embeddings.append(item["values"])
            return embeddings

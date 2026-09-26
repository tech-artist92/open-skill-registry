import os

import httpx

from .base import BaseEmbeddingProvider


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: str | None = None, model_name: str = "text-embedding-3-small"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        self.model_name = model_name
        
        # text-embedding-3-small dimension is 1536
        self._dimension = 1536

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json={"input": texts, "model": self.model_name}
            )
            response.raise_for_status()
            data = response.json()
            
            embeddings = []
            for item in data.get("data", []):
                embeddings.append(item["embedding"])
            return embeddings

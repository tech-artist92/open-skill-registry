
import httpx

from .base import BaseEmbeddingProvider


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, host: str = "http://localhost:11434", model_name: str = "nomic-embed-text"):
        self.host = host
        self.model_name = model_name
        self._dimension = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # We don't have a synchronous way to fetch dimension elegantly here.
            # Using 768 for nomic-embed-text, or fallback. It might be better to just default to 768.
            self._dimension = 768
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.host.rstrip('/')}/api/embed"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"model": self.model_name, "input": texts}
            )
            response.raise_for_status()
            data = response.json()
            
            # Ollama /api/embed returns {"embeddings": [[float, ...], ...]}
            if "embeddings" in data:
                return data["embeddings"]
            
            # fallback for older API /api/embeddings (takes single prompt)
            raise RuntimeError(f"Unexpected response from Ollama API: {data}")

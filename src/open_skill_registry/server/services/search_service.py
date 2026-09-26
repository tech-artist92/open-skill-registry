from typing import List, Optional
from open_skill_registry.models.skill import SkillSummary
from open_skill_registry.registry.storage.base import BaseStorage
from open_skill_registry.registry.embeddings.base import BaseEmbeddingProvider
from open_skill_registry.config import RegistryConfig

class SearchService:
    def __init__(self, storage: BaseStorage, config: RegistryConfig):
        self.storage = storage
        self.config = config
        self.embedder = self._init_embedder()

    def _init_embedder(self) -> Optional[BaseEmbeddingProvider]:
        if not self.config or not hasattr(self.config, 'search'):
            return None
        
        provider = self.config.search.provider
        if provider == "none" or not provider:
            return None
            
        from open_skill_registry.registry.embeddings.factory import get_embedding_provider
        return get_embedding_provider(self.config)

    async def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> List[dict]:
        # Syntactic fallback
        if not self.embedder:
            results = await self.storage.search_skills(query, limit=limit, namespace=namespace)
            return [{"item": r, "score": 1.0, "rank": i+1} for i, r in enumerate(results)]

        try:
            query_vector = await self.embedder.embed_text(query)
        except Exception:
            # Fallback if embedding fails
            results = await self.storage.search_skills(query, limit=limit, namespace=namespace)
            return [{"item": r, "score": 1.0, "rank": i+1} for i, r in enumerate(results)]

        # Fetch keyword results
        keyword_results = await self.storage.search_skills(query, limit=50, namespace=namespace)
        
        # Fetch vector results (hack: pass random query string that won't match keyword boost easily or just let storage do it)
        # Actually, let's just let storage do the vector search by passing a dummy query to avoid keyword overlap if we only want vector, 
        # but the existing storage mixes them. 
        # If storage mixes them, RRF is redundant, but we MUST implement RRF here.
        # Let's assume we do RRF over keyword_results and vector_results.
        vector_results = await self.storage.search_skills("~~~", query_vector=query_vector, limit=50, namespace=namespace)

        # RRF
        k = 60
        scores = {}
        items = {}

        for rank, item in enumerate(keyword_results):
            key = (item.namespace, item.slug)
            items[key] = item
            if key not in scores:
                scores[key] = 0.0
            scores[key] += 1.0 / (k + rank + 1)

        for rank, item in enumerate(vector_results):
            key = (item.namespace, item.slug)
            items[key] = item
            if key not in scores:
                scores[key] = 0.0
            scores[key] += 1.0 / (k + rank + 1)

        # Sort
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        final = []
        for i, (key, score) in enumerate(sorted_results):
            final.append({
                "item": items[key],
                "score": score,
                "rank": i + 1
            })

        return final

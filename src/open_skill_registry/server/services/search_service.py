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
        model = getattr(self.config.search, 'model', None)
        return get_embedding_provider(provider_type=provider, model_name=model)


    async def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> List[dict]:
        # Syntactic fallback
        if not self.embedder:
            results = await self.storage.search_skills(query, limit=limit, namespace=namespace)
            return [{"item": r, "score": max(0.0, 1.0 - i * 0.05), "rank": i+1} for i, r in enumerate(results)]

        try:
            query_vector = await self.embedder.embed_text(query)
        except Exception:
            # Fallback if embedding fails
            results = await self.storage.search_skills(query, limit=limit, namespace=namespace)
            return [{"item": r, "score": max(0.0, 1.0 - i * 0.05), "rank": i+1} for i, r in enumerate(results)]

        # Fetch keyword results
        keyword_results = await self.storage.search_skills(query=query, limit=50, namespace=namespace)
        
        # Fetch pure vector results (pass empty query)
        vector_results = await self.storage.search_skills(query="", query_vector=query_vector, limit=50, namespace=namespace)

        # RRF
        k = 60
        scores = {}
        items = {}
        
        # Max RRF score would be 2 / (k + 1) if an item is rank 1 in both
        max_rrf = 2.0 / (k + 1)

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
                "score": score / max_rrf,  # Normalize to [0.0, 1.0]
                "rank": i + 1
            })

        return final

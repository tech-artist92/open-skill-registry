with open("src/open_skill_registry/server/services/search_service.py", "r") as f:
    code = f.read()

old_search = """        # Fetch keyword results
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

        return final"""

new_search = """        # Fetch keyword results
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

        return final"""

code = code.replace(old_search, new_search)

code = code.replace(
    'return [{"item": r, "score": 1.0, "rank": i+1} for i, r in enumerate(results)]',
    'return [{"item": r, "score": max(0.0, 1.0 - i * 0.05), "rank": i+1} for i, r in enumerate(results)]'
)

with open("src/open_skill_registry/server/services/search_service.py", "w") as f:
    f.write(code)


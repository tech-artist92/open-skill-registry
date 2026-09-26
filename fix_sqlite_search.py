import re

with open("src/open_skill_registry/registry/storage/sqlite.py", "r") as f:
    code = f.read()

# Replace the whole search_skills method body to be safe
start_idx = code.find("    async def search_skills(")
end_idx = code.find("    async def resolve_version(")

new_search_skills = """    async def search_skills(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        namespace: Optional[str] = None
    ) -> List[SkillSummary]:
        async with self.session_maker() as session:
            stmt = select(Skill, Namespace.slug.label("ns_slug"), SkillVersion).join(Namespace)
            stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            if query:
                stmt = stmt.where(
                    or_(
                        Skill.name.ilike(f"%{query}%"),
                        Skill.description.ilike(f"%{query}%")
                    )
                )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            skills = []
            for skill, ns_slug, sv in rows:
                skills.append((skill, ns_slug, sv))

            if query_vector:
                rescored = []
                for skill, ns_slug, sv in skills:
                    score = 0.0
                    
                    if query:
                        if query.lower() in skill.name.lower():
                            score += 0.5
                        elif skill.description and query.lower() in skill.description.lower():
                            score += 0.2

                    if sv:
                        emb_res = await session.execute(
                            select(SkillEmbedding).where(SkillEmbedding.version_id == sv.id)
                        )
                        emb = emb_res.scalar_one_or_none()
                        if emb and emb.embedding:
                            vec_score = cosine_similarity(query_vector, emb.embedding)
                            score += vec_score
                    
                    if score > 0 or not query:
                        rescored.append((score, skill, ns_slug, sv))
                rescored.sort(key=lambda x: x[0], reverse=True)
                skills = [(item[1], item[2], item[3]) for item in rescored[:limit]]
            else:
                skills = skills[:limit]
            
            summaries = []
            for skill, ns_slug, sv in skills:
                latest_version = sv.version if sv else ""
                content_hash = sv.content_hash if sv else ""
                
                tags = []
                if sv:
                    tags = await self.get_version_tags(sv.id)

                summaries.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility,
                    tags=tags,
                    content_hash=content_hash
                ))

            return summaries

"""

code = code[:start_idx] + new_search_skills + code[end_idx:]

with open("src/open_skill_registry/registry/storage/sqlite.py", "w") as f:
    f.write(code)

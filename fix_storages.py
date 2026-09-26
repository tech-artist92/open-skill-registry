import re

def process_file(filepath, is_pgvector=False):
    with open(filepath, 'r') as f:
        code = f.read()

    # 1. Fix list_skills N+1
    list_skills_old = """            stmt = select(Skill, Namespace.slug.label("ns_slug")).join(Namespace)
            if namespace:"""
    list_skills_new = """            stmt = select(Skill, Namespace.slug.label("ns_slug"), SkillVersion).join(Namespace)
            stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
            if namespace:"""
    code = code.replace(list_skills_old, list_skills_new)

    list_skills_loop_old = """            summaries = []
            for skill, ns_slug in result.all():
                latest_version = ""
                if skill.latest_version_id:
                    latest_res = await session.execute(
                        select(SkillVersion.version).where(SkillVersion.id == skill.latest_version_id)
                    )
                    ver = latest_res.scalar_one_or_none()
                    if ver:
                        latest_version = ver

                summaries.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility
                ))"""
    list_skills_loop_new = """            summaries = []
            for skill, ns_slug, sv in result.all():
                latest_version = sv.version if sv else ""
                content_hash = sv.content_hash if sv else ""
                
                # Fetch tags if needed (optional for list_skills, but let's just do empty or fetch them)
                # To avoid N+1 for tags in list_skills, we will just leave it empty.
                
                summaries.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility,
                    tags=[],
                    content_hash=content_hash
                ))"""
    code = code.replace(list_skills_loop_old, list_skills_loop_new)

    # 2. Fix search_skills
    if is_pgvector:
        search_skills_old = """            stmt = select(Skill, Namespace.slug.label("ns_slug"), rank.label("text_score"))
            stmt = stmt.join(Namespace)
            
            if query_vector:
                # pgvector cosine distance is `<=>`
                # cosine similarity = 1 - distance
                stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
                stmt = stmt.outerjoin(SkillEmbedding, SkillVersion.id == SkillEmbedding.version_id)
                distance = SkillEmbedding.embedding.cosine_distance(query_vector)
                stmt = stmt.add_columns(distance.label("vec_distance"))
            
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            # If no query vector, we at least filter by text matching
            if not query_vector:
                stmt = stmt.where(
                    or_(
                        Skill.name.ilike(f"%{query}%"),
                        Skill.description.ilike(f"%{query}%"),
                        rank > 0
                    )
                )

            result = await session.execute(stmt)
            rows = result.all()"""
        
        search_skills_new = """            stmt = select(Skill, Namespace.slug.label("ns_slug"), rank.label("text_score"), SkillVersion)
            stmt = stmt.join(Namespace)
            stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
            
            if query_vector:
                stmt = stmt.outerjoin(SkillEmbedding, SkillVersion.id == SkillEmbedding.version_id)
                distance = SkillEmbedding.embedding.cosine_distance(query_vector)
                stmt = stmt.add_columns(distance.label("vec_distance"))
            
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            # If not pure vector search (i.e. query is provided), filter by text
            if query:
                stmt = stmt.where(
                    or_(
                        Skill.name.ilike(f"%{query}%"),
                        Skill.description.ilike(f"%{query}%"),
                        rank > 0
                    )
                )

            result = await session.execute(stmt)
            rows = result.all()"""
        code = code.replace(search_skills_old, search_skills_new)

        post_process_old = """            # Post-process to combine scores
            scored_skills = []
            for row in rows:
                skill = row[0]
                ns_slug = row[1]
                text_score = row[2] or 0.0
                
                final_score = text_score
                if query_vector:
                    vec_dist = row[3]
                    vec_score = (1 - vec_dist) if vec_dist is not None else 0.0
                    final_score = (0.3 * text_score) + (0.7 * vec_score)
                
                if final_score > 0 or not query_vector:
                    scored_skills.append((final_score, skill, ns_slug))

            scored_skills.sort(key=lambda x: x[0], reverse=True)
            
            skills = []
            for _, skill, ns_slug in scored_skills[:limit]:
                latest_version = ""
                if skill.latest_version_id:
                    latest_res = await session.execute(
                        select(SkillVersion.version).where(SkillVersion.id == skill.latest_version_id)
                    )
                    ver = latest_res.scalar_one_or_none()
                    if ver:
                        latest_version = ver

                skills.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility
                ))
                
            return skills"""
        
        post_process_new = """            scored_skills = []
            for row in rows:
                skill = row[0]
                ns_slug = row[1]
                text_score = row[2] or 0.0
                sv = row[3]
                
                final_score = text_score
                if query_vector:
                    vec_dist = row[4]
                    vec_score = (1 - vec_dist) if vec_dist is not None else 0.0
                    if not query:
                        final_score = vec_score
                    else:
                        final_score = (0.3 * text_score) + (0.7 * vec_score)
                
                if final_score > 0 or not query_vector or not query:
                    scored_skills.append((final_score, skill, ns_slug, sv))

            scored_skills.sort(key=lambda x: x[0], reverse=True)
            
            skills = []
            for _, skill, ns_slug, sv in scored_skills[:limit]:
                latest_version = sv.version if sv else ""
                content_hash = sv.content_hash if sv else ""
                
                # Fetch tags for search results
                tags = []
                if sv:
                    tags = await self.get_version_tags(sv.id)

                skills.append(SkillSummary(
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
                
            return skills"""
        code = code.replace(post_process_old, post_process_new)
        
    else:
        # SQLite
        search_skills_old = """            stmt = select(Skill, Namespace.slug.label("ns_slug")).join(Namespace)
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            if not query_vector:
                stmt = stmt.where(
                    or_(
                        Skill.name.ilike(f"%{query}%"),
                        Skill.description.ilike(f"%{query}%")
                    )
                )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            skills = []
            for skill, ns_slug in rows:
                skills.append((skill, ns_slug))

            if query_vector:
                rescored = []
                for skill, ns_slug in skills:
                    score = 0.0
                    
                    # Keyword match boost
                    if query.lower() in skill.name.lower():
                        score += 0.5
                    elif skill.description and query.lower() in skill.description.lower():
                        score += 0.2

                    if skill.latest_version_id:
                        emb_res = await session.execute(
                            select(SkillEmbedding).where(SkillEmbedding.version_id == skill.latest_version_id)
                        )
                        emb = emb_res.scalar_one_or_none()
                        if emb and emb.embedding:
                            vec_score = cosine_similarity(query_vector, emb.embedding)
                            score += vec_score
                    
                    if score > 0:
                        rescored.append((score, skill, ns_slug))
                rescored.sort(key=lambda x: x[0], reverse=True)
                skills = [(item[1], item[2]) for item in rescored[:limit]]
            else:
                skills = skills[:limit]
            
            summaries = []
            for skill, ns_slug in skills:
                latest_version = ""
                if skill.latest_version_id:
                    latest_res = await session.execute(
                        select(SkillVersion.version).where(SkillVersion.id == skill.latest_version_id)
                    )
                    ver = latest_res.scalar_one_or_none()
                    if ver:
                        latest_version = ver

                summaries.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility
                ))

            return summaries"""
            
        search_skills_new = """            stmt = select(Skill, Namespace.slug.label("ns_slug"), SkillVersion).join(Namespace)
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

            return summaries"""
        code = code.replace(search_skills_old, search_skills_new)

    with open(filepath, 'w') as f:
        f.write(code)

process_file("src/open_skill_registry/registry/storage/sqlite.py", is_pgvector=False)
process_file("src/open_skill_registry/registry/storage/pgvector.py", is_pgvector=True)

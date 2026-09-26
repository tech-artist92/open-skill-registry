import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_

from open_skill_registry.registry.storage.base import BaseStorage
from open_skill_registry.models.skill import SkillDetail, SkillSummary
from open_skill_registry.models.manifest import SkillManifest
from open_skill_registry.server.db.models import (
    Namespace, Skill, SkillVersion, SkillResource, SkillEmbedding, ReleaseTag, get_utc_now
)

class PgVectorStorage(BaseStorage):
    def __init__(self, session_maker):
        self.session_maker = session_maker

    async def _get_or_create_namespace(self, session: AsyncSession, slug: str) -> Namespace:
        result = await session.execute(select(Namespace).where(Namespace.slug == slug))
        ns = result.scalar_one_or_none()
        if not ns:
            ns = Namespace(slug=slug, name=slug)
            session.add(ns)
            await session.flush()
        return ns

    async def save_skill_version(
        self,
        namespace: str,
        slug: str,
        name: str,
        description: str,
        version: str,
        manifest: SkillManifest,
        files: Dict[str, bytes],
        parsed_frontmatter: Dict[str, Any],
        instructions: str,
        embeddings: Optional[List[float]] = None,
        model_name: Optional[str] = None
    ) -> SkillVersion:
        async with self.session_maker() as session:
            ns = await self._get_or_create_namespace(session, namespace)

            result = await session.execute(
                select(Skill).where(Skill.namespace_id == ns.id, Skill.slug == slug)
            )
            skill = result.scalar_one_or_none()
            if not skill:
                skill = Skill(
                    namespace_id=ns.id,
                    slug=slug,
                    name=name,
                    description=description
                )
                session.add(skill)
                await session.flush()
            else:
                skill.name = name
                skill.description = description
                skill.updated_at = get_utc_now()

            # Generate tsvector
            tsv_update = func.to_tsvector('english', f"{name} {description} {instructions}")
            skill.tsv = tsv_update # SQLAlchemy will update

            result = await session.execute(
                select(SkillVersion).where(SkillVersion.skill_id == skill.id, SkillVersion.version == version)
            )
            if result.scalar_one_or_none():
                raise ValueError(f"Version {version} already exists for skill {slug}")

            sv = SkillVersion(
                skill_id=skill.id,
                version=version,
                content_hash=manifest.content_hash,
                instructions=instructions,
                parsed_frontmatter=parsed_frontmatter,
                manifest=manifest.model_dump(),
                compliance_snapshot={}
            )
            session.add(sv)
            await session.flush()

            skill.latest_version_id = sv.id

            for path, content in files.items():
                res = SkillResource(
                    version_id=sv.id,
                    path=path,
                    content_type="application/octet-stream",
                    content=content,
                    content_hash="",
                    size_bytes=len(content)
                )
                for entry in manifest.files:
                    if entry.path == path:
                        res.content_type = entry.content_type
                        res.content_hash = entry.hash
                        break
                session.add(res)

            if embeddings and model_name:
                emb = SkillEmbedding(
                    version_id=sv.id,
                    source_field="full",
                    embedding=embeddings,
                    model_name=model_name
                )
                session.add(emb)

            await session.commit()
            await session.refresh(sv)
            return sv

    async def get_skill(self, namespace: str, slug: str) -> Optional[SkillDetail]:
        async with self.session_maker() as session:
            result = await session.execute(
                select(Skill)
                .join(Namespace)
                .where(Namespace.slug == namespace, Skill.slug == slug)
            )
            skill = result.scalar_one_or_none()
            if not skill:
                return None

            versions_result = await session.execute(
                select(SkillVersion.version).where(SkillVersion.skill_id == skill.id)
            )
            versions = [r[0] for r in versions_result.all()]
            
            latest_version = ""
            if skill.latest_version_id:
                latest_res = await session.execute(
                    select(SkillVersion.version).where(SkillVersion.id == skill.latest_version_id)
                )
                latest_ver_row = latest_res.scalar_one_or_none()
                if latest_ver_row:
                    latest_version = latest_ver_row

            tags_result = await session.execute(
                select(ReleaseTag).where(ReleaseTag.skill_id == skill.id)
            )
            tags_map = {}
            for tag in tags_result.scalars().all():
                tag_ver_res = await session.execute(select(SkillVersion.version).where(SkillVersion.id == tag.version_id))
                tag_ver = tag_ver_res.scalar_one_or_none()
                if tag_ver:
                    tags_map[tag.tag_name] = tag_ver

            return SkillDetail(
                name=skill.name,
                slug=skill.slug,
                namespace=namespace,
                description=skill.description or "",
                latest_version=latest_version,
                download_count=skill.download_count,
                visibility=skill.visibility,
                versions=versions,
                tags=tags_map,
                created_at=skill.created_at,
                updated_at=skill.updated_at
            )

    async def get_skill_version(self, namespace: str, slug: str, version: str) -> Optional[SkillVersion]:
        async with self.session_maker() as session:
            result = await session.execute(
                select(SkillVersion)
                .join(Skill, SkillVersion.skill_id == Skill.id)
                .join(Namespace)
                .where(Namespace.slug == namespace, Skill.slug == slug, SkillVersion.version == version)
            )
            return result.scalar_one_or_none()

    async def get_version_tags(self, version_id) -> list[str]:
        from open_skill_registry.server.db.models import ReleaseTag
        from sqlalchemy import select
        async with self.session_maker() as session:
            result = await session.execute(select(ReleaseTag.tag_name).where(ReleaseTag.version_id == version_id))
            return list(result.scalars().all())

    async def get_skill_resources(self, version_id: uuid.UUID) -> Dict[str, bytes]:
        async with self.session_maker() as session:
            result = await session.execute(
                select(SkillResource).where(SkillResource.version_id == version_id)
            )
            return {r.path: r.content for r in result.scalars().all()}

    async def search_skills(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        namespace: Optional[str] = None
    ) -> List[SkillSummary]:
        async with self.session_maker() as session:
            # We construct a query using func.ts_rank_cd and optionally vector cosine distance.
            
            # Text matching via TSVECTOR
            # ts_rank_cd(tsv, plainto_tsquery('english', query))
            tsquery = func.plainto_tsquery('english', query)
            rank = func.ts_rank_cd(Skill.tsv, tsquery)
            
            stmt = select(Skill, Namespace.slug.label("ns_slug"), rank.label("text_score"), SkillVersion)
            stmt = stmt.join(Namespace)
            stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
            
            if query_vector:
                stmt = stmt.outerjoin(SkillEmbedding, SkillVersion.id == SkillEmbedding.version_id)
                distance = SkillEmbedding.embedding.cosine_distance(query_vector)
                stmt = stmt.add_columns(distance.label("vec_distance"))
            
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            # If not pure vector search (i.e. query is provided), filter by text
            if query and not query_vector:
                stmt = stmt.where(
                    or_(
                        Skill.name.ilike(f"%{query}%"),
                        Skill.description.ilike(f"%{query}%"),
                        rank > 0
                    )
                )

            result = await session.execute(stmt)
            rows = result.all()
            
            # Post-process to combine scores
            scored_skills = []
            for row in rows:
                skill = row[0]
                ns_slug = row[1]
                text_score = row[2] or 0.0
                sv = row[3]
                
                final_score = text_score
                if query_vector:
                    vec_dist = getattr(row, "vec_distance", None)
                    vec_score = (1 - vec_dist) if vec_dist is not None else 0.0
                    final_score = (0.3 * text_score) + (0.7 * vec_score)
                
                if final_score > 0 or not query_vector:
                    scored_skills.append((final_score, skill, ns_slug, sv))

            scored_skills.sort(key=lambda x: x[0], reverse=True)
            
            skills = []
            for _, skill, ns_slug, sv in scored_skills[:limit]:
                latest_version = sv.version if sv else ""
                content_hash = sv.content_hash if sv else ""
                tags = []  # Assuming tags are not populated in this query directly, we'll just pass empty list for now or we could fetch them. The instruction says `tags=skill.tags or []` but Skill model doesn't have `tags` natively as relationship in our standard setup unless added. Wait, the instruction says: `tags=skill.tags or []` or actually it might just mean passing an empty list or whatever is available on skill. Wait, `Skill` model might not have `tags`. Let me pass `[]` if it doesn't. Or maybe the instruction literally meant `tags=getattr(skill, 'tags', [])`. Let's use `getattr(skill, 'tags', [])`.

                skills.append(SkillSummary(
                    name=skill.name,
                    slug=skill.slug,
                    namespace=ns_slug,
                    description=skill.description or "",
                    latest_version=latest_version,
                    download_count=skill.download_count,
                    visibility=skill.visibility,
                    version=latest_version,
                    tags=getattr(skill, 'tags', []),
                    content_hash=content_hash
                ))
            return skills

    async def resolve_version(self, namespace: str, slug: str, constraint: str) -> Optional[SkillVersion]:
        async with self.session_maker() as session:
            tag_res = await session.execute(
                select(ReleaseTag)
                .join(Skill, ReleaseTag.skill_id == Skill.id)
                .join(Namespace)
                .where(Namespace.slug == namespace, Skill.slug == slug, ReleaseTag.tag_name == constraint)
            )
            tag = tag_res.scalar_one_or_none()
            if tag:
                ver_res = await session.execute(select(SkillVersion).where(SkillVersion.id == tag.version_id))
                return ver_res.scalar_one_or_none()
            
            return await self.get_skill_version(namespace, slug, constraint)

    async def tag_version(self, namespace: str, slug: str, version: str, tag: str) -> None:
        async with self.session_maker() as session:
            skill_res = await session.execute(
                select(Skill).join(Namespace).where(Namespace.slug == namespace, Skill.slug == slug)
            )
            skill = skill_res.scalar_one_or_none()
            if not skill:
                raise ValueError(f"Skill {namespace}/{slug} not found")

            ver_res = await session.execute(
                select(SkillVersion).where(SkillVersion.skill_id == skill.id, SkillVersion.version == version)
            )
            sv = ver_res.scalar_one_or_none()
            if not sv:
                raise ValueError(f"Version {version} not found")

            existing_tag_res = await session.execute(
                select(ReleaseTag).where(ReleaseTag.skill_id == skill.id, ReleaseTag.tag_name == tag)
            )
            existing_tag = existing_tag_res.scalar_one_or_none()
            if existing_tag:
                existing_tag.version_id = sv.id
            else:
                new_tag = ReleaseTag(skill_id=skill.id, tag_name=tag, version_id=sv.id)
                session.add(new_tag)

            if tag == "latest":
                skill.latest_version_id = sv.id

            await session.commit()

    async def yank_version(self, namespace: str, slug: str, version: str) -> None:
        async with self.session_maker() as session:
            ver = await self.get_skill_version(namespace, slug, version)
            if not ver:
                raise ValueError(f"Version {version} not found")
            ver_id = ver.id
            v_res = await session.execute(select(SkillVersion).where(SkillVersion.id == ver_id))
            v = v_res.scalar_one()
            v.is_yanked = True
            await session.commit()

    async def list_skills(self, namespace: Optional[str] = None, page: int = 1, size: int = 20, sort: str = "updated") -> Any:
        from open_skill_registry.models.response import Page
        async with self.session_maker() as session:
            stmt = select(Skill, Namespace.slug.label("ns_slug"), SkillVersion).join(Namespace)
            stmt = stmt.outerjoin(SkillVersion, Skill.latest_version_id == SkillVersion.id)
            if namespace:
                stmt = stmt.where(Namespace.slug == namespace)
            
            # total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            if sort == "updated":
                stmt = stmt.order_by(Skill.updated_at.desc())
            elif sort == "downloads":
                stmt = stmt.order_by(Skill.download_count.desc())
            
            stmt = stmt.offset((page - 1) * size).limit(size)
            result = await session.execute(stmt)
            
            summaries = []
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
                ))
            
            return Page(items=summaries, total=total, page=page, page_size=size)

    async def get_skill_resource_file(self, version_id: uuid.UUID, path: str) -> Optional[Any]:
        async with self.session_maker() as session:
            result = await session.execute(
                select(SkillResource).where(SkillResource.version_id == version_id, SkillResource.path == path)
            )
            return result.scalar_one_or_none()

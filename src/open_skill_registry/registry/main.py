import asyncio
import threading
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import create_async_engine

from open_skill_registry.config import RegistryConfig
from open_skill_registry.models.skill import SkillDetail, SkillSummary
from open_skill_registry.registry.core.manifest import compute_manifest
from open_skill_registry.registry.core.validator import validate_package_or_raise
from open_skill_registry.registry.embeddings.factory import get_embedding_provider
from open_skill_registry.registry.storage.factory import get_storage
from open_skill_registry.server.db.models import SkillVersion, SQLModel


class AsyncSkillRegistry:
    def __init__(self, config: RegistryConfig | None = None):
        self.config = config or RegistryConfig.load()
        
        db_url = self.config.database.url
        # Convert dialect for async
        if db_url.startswith("sqlite:/") and "sqlite+aiosqlite" not in db_url:
            db_url = db_url.replace("sqlite:", "sqlite+aiosqlite:")
        elif db_url.startswith("postgresql:/") and "postgresql+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql:", "postgresql+asyncpg:")
            
        self.engine = create_async_engine(db_url, echo=False)
        self.storage = get_storage(self.config, self.engine)
        self.embedding = get_embedding_provider(
            provider_type=self.config.search.provider,
            model_name=self.config.search.model
        )

    async def initialize(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    def _parse_frontmatter(self, skill_md_content: bytes) -> dict[str, Any]:
        content_str = skill_md_content.decode("utf-8")
        if content_str.startswith("---"):
            parts = content_str.split("---", 2)
            if len(parts) >= 3:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
        return {}

    async def publish(self, namespace: str, slug: str, files: dict[str, bytes]) -> SkillVersion:
        validate_package_or_raise(files)
        
        manifest = compute_manifest(files)
        frontmatter = self._parse_frontmatter(files.get("SKILL.md", b""))
        
        name = frontmatter.get("name", slug)
        description = frontmatter.get("description", "")
        version = frontmatter.get("version", "1.0.0")
        
        content_str = files.get("SKILL.md", b"").decode("utf-8")
        if "---" in content_str:
            parts = content_str.split("---", 2)
            instructions = parts[2].strip() if len(parts) >= 3 else ""
        else:
            instructions = content_str
            
        text_for_embedding = f"{name} {description} {instructions}"
        embeddings = None
        model_name = getattr(self.embedding, "model_name", "none")
        
        if self.config.search.provider != "none":
            embed_resp = await self.embedding.generate_embedding(text_for_embedding)
            embeddings = embed_resp.embedding

        return await self.storage.save_skill_version(
            namespace=namespace,
            slug=slug,
            name=name,
            description=description,
            version=version,
            manifest=manifest,
            files=files,
            parsed_frontmatter=frontmatter,
            instructions=instructions,
            embeddings=embeddings,
            model_name=model_name
        )

    async def get(self, namespace: str, slug: str) -> SkillDetail | None:
        return await self.storage.get_skill(namespace, slug)

    async def get_version(self, namespace: str, slug: str, version: str) -> SkillVersion | None:
        return await self.storage.get_skill_version(namespace, slug, version)

    async def download_resources(self, namespace: str, slug: str, version: str) -> dict[str, bytes]:
        ver = await self.get_version(namespace, slug, version)
        if not ver:
            raise ValueError(f"Version {version} not found")
        return await self.storage.get_skill_resources(ver.id)

    async def search(self, query: str, limit: int = 10, namespace: str | None = None) -> list[SkillSummary]:
        query_vector = None
        if self.config.search.provider != "none":
            embed_resp = await self.embedding.generate_embedding(query)
            query_vector = embed_resp.embedding
        return await self.storage.search_skills(query, query_vector, limit, namespace)

    async def resolve(self, namespace: str, slug: str, constraint: str) -> SkillVersion | None:
        return await self.storage.resolve_version(namespace, slug, constraint)

    async def tag(self, namespace: str, slug: str, version: str, tag: str) -> None:
        await self.storage.tag_version(namespace, slug, version, tag)

    async def yank(self, namespace: str, slug: str, version: str) -> None:
        await self.storage.yank_version(namespace, slug, version)


from typing import Any, Coroutine

def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Run in a background thread if loop is already running
        result = []
        error = []
        def runner():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result.append(new_loop.run_until_complete(coro))
            except Exception as e:
                error.append(e)
            finally:
                new_loop.close()
                
        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0]
    else:
        return asyncio.run(coro)

class SkillRegistry:
    def __init__(self, config: RegistryConfig | None = None):
        self._async_registry = AsyncSkillRegistry(config)

    def initialize(self):
        _run_async(self._async_registry.initialize())

    def publish(self, namespace: str, slug: str, files: dict[str, bytes]) -> SkillVersion:
        return _run_async(self._async_registry.publish(namespace, slug, files))

    def get(self, namespace: str, slug: str) -> SkillDetail | None:
        return _run_async(self._async_registry.get(namespace, slug))

    def get_version(self, namespace: str, slug: str, version: str) -> SkillVersion | None:
        return _run_async(self._async_registry.get_version(namespace, slug, version))

    def download_resources(self, namespace: str, slug: str, version: str) -> dict[str, bytes]:
        return _run_async(self._async_registry.download_resources(namespace, slug, version))

    def search(self, query: str, limit: int = 10, namespace: str | None = None) -> list[SkillSummary]:
        return _run_async(self._async_registry.search(query, limit, namespace))

    def resolve(self, namespace: str, slug: str, constraint: str) -> SkillVersion | None:
        return _run_async(self._async_registry.resolve(namespace, slug, constraint))

    def tag(self, namespace: str, slug: str, version: str, tag: str) -> None:
        _run_async(self._async_registry.tag(namespace, slug, version, tag))

    def yank(self, namespace: str, slug: str, version: str) -> None:
        _run_async(self._async_registry.yank(namespace, slug, version))

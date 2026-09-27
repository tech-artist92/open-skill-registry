import asyncio
import re
import threading
from pathlib import Path
from typing import Any, Coroutine

import yaml
from sqlalchemy.ext.asyncio import create_async_engine

from open_skill_registry.config import RegistryConfig
from open_skill_registry.models.skill import SkillDetail, SkillSummary
from open_skill_registry.registry.core.manifest import compute_manifest
from open_skill_registry.registry.core.validator import validate_package_or_raise
from open_skill_registry.registry.embeddings.factory import get_embedding_provider
from open_skill_registry.registry.storage.factory import get_storage
from open_skill_registry.server.db.models import SkillVersion, SQLModel
from open_skill_registry.server.db.session import init_db


class SearchResultList(list):
    """List containing search results with .items property for quickstart compatibility."""

    @property
    def items(self) -> list:
        return self

    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()


class _AwaitableNone:
    """Awaitable none for methods that can be called synchronously or awaited."""

    def __await__(self):
        async def _coro():
            return None
        return _coro().__await__()

    def __repr__(self):
        return "None"

    def __eq__(self, other):
        return other is None


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
            model_name=self.config.search.model,
        )

    @classmethod
    def from_config(
        cls, config_source: str | Path | RegistryConfig | None = None
    ) -> "AsyncSkillRegistry":
        if isinstance(config_source, RegistryConfig):
            return cls(config_source)
        return cls(RegistryConfig.load(config_source))

    async def initialize(self):
        await init_db(self.engine)

    def _slugify(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[-\s]+", "-", text)

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

    async def publish(
        self,
        namespace: str = "public",
        slug: str | None = None,
        files: dict[str, bytes] | None = None,
        path: str | Path | None = None,
        version: str | None = None,
    ) -> SkillVersion:
        if files is None and path is not None:
            p = Path(path)
            files = {}
            if p.is_file():
                content = p.read_bytes()
                files["SKILL.md"] = content
                if not slug:
                    fm = self._parse_frontmatter(content)
                    slug = fm.get("slug") or (
                        self._slugify(fm.get("name")) if fm.get("name") else p.stem
                    )
            elif p.is_dir():
                for file_path in p.rglob("*"):
                    if file_path.is_file():
                        rel_parts = file_path.relative_to(p).parts
                        if any(
                            part.startswith(".") or part == "__pycache__"
                            for part in rel_parts
                        ):
                            continue
                        files[file_path.relative_to(p).as_posix()] = (
                            file_path.read_bytes()
                        )
                if not slug:
                    skill_md = files.get("SKILL.md")
                    if skill_md:
                        fm = self._parse_frontmatter(skill_md)
                        slug = fm.get("slug") or (
                            self._slugify(fm.get("name")) if fm.get("name") else p.name
                        )
                    else:
                        slug = p.name

        if files is None:
            raise ValueError("Either 'files' or 'path' must be provided.")

        validate_package_or_raise(files)

        manifest = compute_manifest(files)
        frontmatter = self._parse_frontmatter(files.get("SKILL.md", b""))

        name = frontmatter.get("name", slug or "Untitled")
        slug = slug or frontmatter.get("slug") or self._slugify(name)
        description = frontmatter.get("description", "")
        if version is None:
            version = frontmatter.get("version", "1.0.0")

        content_str = files.get("SKILL.md", b"").decode("utf-8")
        if content_str.startswith("---"):
            parts = content_str.split("---", 2)
            instructions = parts[2].strip() if len(parts) >= 3 else ""
        else:
            instructions = content_str

        # Security scan
        safety_score = "SAFE"
        security_scan_data = None
        has_security = hasattr(self.config, "security") and self.config.security
        scan_on_push = self.config.security.scan_on_push if has_security else True
        block_critical = self.config.security.block_critical if has_security else True
        if scan_on_push:
            from open_skill_registry.registry.security.scanner import scan_skill_package

            scan_res = scan_skill_package(files)
            safety_score = scan_res.safety_score
            security_scan_data = scan_res.to_dict()
            if block_critical and safety_score == "CRITICAL":
                msg = (
                    scan_res.findings[0].message
                    if scan_res.findings
                    else "Security vulnerabilities detected"
                )
                raise ValueError(f"Security scan rejected skill: {msg}")

        text_for_embedding = f"{name} {description} {instructions}"
        embeddings = None
        model_name = getattr(self.embedding, "model_name", "none")

        if self.config.search.provider != "none":
            embeddings = await self.embedding.embed_text(text_for_embedding)

        saved = await self.storage.save_skill_version(
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
            model_name=model_name,
            safety_score=safety_score,
            security_scan=security_scan_data,
        )
        saved.slug = slug
        return saved

    async def get(self, namespace: str, slug: str) -> SkillDetail | None:
        return await self.storage.get_skill(namespace, slug)

    async def get_version(
        self, namespace: str, slug: str, version: str
    ) -> SkillVersion | None:
        return await self.storage.get_skill_version(namespace, slug, version)

    async def download_resources(
        self, namespace: str, slug: str, version: str
    ) -> dict[str, bytes]:
        ver = await self.get_version(namespace, slug, version)
        if not ver:
            raise ValueError(f"Version {version} not found")
        return await self.storage.get_skill_resources(ver.id)

    async def search(
        self, query: str, limit: int = 10, namespace: str | None = None
    ) -> SearchResultList:
        query_vector = None
        if self.config.search.provider != "none":
            query_vector = await self.embedding.embed_text(query)
        results = await self.storage.search_skills(query, query_vector, limit, namespace)
        return SearchResultList(results)

    async def resolve(
        self, namespace: str, slug: str, constraint: str
    ) -> SkillVersion | None:
        return await self.storage.resolve_version(namespace, slug, constraint)

    async def tag(self, namespace: str, slug: str, version: str, tag: str) -> None:
        await self.storage.tag_version(namespace, slug, version, tag)

    async def yank(self, namespace: str, slug: str, version: str) -> None:
        await self.storage.yank_version(namespace, slug, version)


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

    @classmethod
    def from_config(
        cls, config_source: str | Path | RegistryConfig | None = None
    ) -> "SkillRegistry":
        if isinstance(config_source, RegistryConfig):
            return cls(config_source)
        return cls(RegistryConfig.load(config_source))

    def initialize(self):
        _run_async(self._async_registry.initialize())
        return _AwaitableNone()

    def publish(
        self,
        namespace: str = "public",
        slug: str | None = None,
        files: dict[str, bytes] | None = None,
        path: str | Path | None = None,
        version: str | None = None,
    ) -> SkillVersion:
        return _run_async(
            self._async_registry.publish(
                namespace=namespace,
                slug=slug,
                files=files,
                path=path,
                version=version,
            )
        )

    def get(self, namespace: str, slug: str) -> SkillDetail | None:
        return _run_async(self._async_registry.get(namespace, slug))

    def get_version(
        self, namespace: str, slug: str, version: str
    ) -> SkillVersion | None:
        return _run_async(self._async_registry.get_version(namespace, slug, version))

    def download_resources(
        self, namespace: str, slug: str, version: str
    ) -> dict[str, bytes]:
        return _run_async(
            self._async_registry.download_resources(namespace, slug, version)
        )

    def search(
        self, query: str, limit: int = 10, namespace: str | None = None
    ) -> SearchResultList:
        return _run_async(self._async_registry.search(query, limit, namespace))

    def resolve(
        self, namespace: str, slug: str, constraint: str
    ) -> SkillVersion | None:
        return _run_async(self._async_registry.resolve(namespace, slug, constraint))

    def tag(self, namespace: str, slug: str, version: str, tag: str) -> None:
        _run_async(self._async_registry.tag(namespace, slug, version, tag))

    def yank(self, namespace: str, slug: str, version: str) -> None:
        _run_async(self._async_registry.yank(namespace, slug, version))

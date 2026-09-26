import io
import zipfile
import yaml
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from open_skill_registry.server.db.models import SkillVersion
from open_skill_registry.models.exceptions import DuplicateVersionError
from open_skill_registry.registry.core.validator import validate_package_or_raise
from open_skill_registry.registry.core.manifest import compute_manifest
from open_skill_registry.registry.embeddings.factory import get_embedding_provider
from open_skill_registry.config import RegistryConfig
from open_skill_registry.registry.storage.base import BaseStorage

class SkillService:
    def __init__(self, db_session: AsyncSession, storage: BaseStorage, config: RegistryConfig):
        self.db_session = db_session
        self.storage = storage
        self.config = config

    async def publish_skill(
        self, 
        namespace: str, 
        files: Dict[str, bytes], 
        explicit_slug: Optional[str] = None, 
        explicit_version: Optional[str] = None, 
        created_by: str = "anonymous"
    ) -> SkillVersion:
        
        # Path traversal check
        for filepath in files:
            if ".." in filepath or filepath.startswith("/"):
                raise ValueError(f"Path traversal detected: {filepath}")

        # Core validation
        validate_package_or_raise(files)
        
        raw_content = files.get("SKILL.md", b"").decode("utf-8")
        frontmatter = self._parse_frontmatter(files.get("SKILL.md", b""))
        instructions = ""
        if raw_content.startswith("---"):
            parts = raw_content.split("---", 2)
            if len(parts) >= 3:
                instructions = parts[2].strip()
        
        name = frontmatter.get("name", "Untitled")
        slug = explicit_slug or frontmatter.get("slug") or self._slugify(name)
        
        # Version inference
        version = "1.0.0"
        if explicit_version:
            version = explicit_version
        elif frontmatter.get("version"):
            version = str(frontmatter["version"])
        else:
            detail = await self.storage.get_skill(namespace, slug)
            if detail and detail.versions:
                # Assume the last in list or sort them, for simplicity just take the last or `latest_version` if it exists
                latest_ver = getattr(detail, 'latest_version', detail.versions[-1] if detail.versions else None)
                if latest_ver:
                    version = self._increment_patch(latest_ver)

        # Check for duplicates
        existing = await self.storage.get_skill_version(namespace, slug, version)
        if existing:
            raise DuplicateVersionError(f"Duplicate version {version} already exists for {namespace}/{slug}")

        manifest = compute_manifest(files)
        
        provider_type = "fastembed"
        model_name = None
        if hasattr(self.config, 'search') and self.config.search:
            provider_type = getattr(self.config.search, 'provider', "fastembed")
            model_name = getattr(self.config.search, 'model', None)
        
        provider = get_embedding_provider(provider_type=provider_type, model_name=model_name)
        
        text_for_embedding = f"{name}\n\n{frontmatter.get('description', '')}"
        embedding = await provider.embed_text(text_for_embedding)
        
        saved_version = await self.storage.save_skill_version(
            namespace=namespace,
            slug=slug,
            name=name,
            description=frontmatter.get("description", ""),
            version=version,
            manifest=manifest,
            files=files,
            parsed_frontmatter=frontmatter,
            instructions=instructions,
            embeddings=embedding,
            model_name=provider.__class__.__name__
        )
        
        await self.storage.tag_version(namespace, slug, version, "latest")
        
        return saved_version

    def _parse_frontmatter(self, content: bytes) -> Dict[str, Any]:
        text = content.decode("utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    return {}
        return {}

    def _slugify(self, text: str) -> str:
        return text.lower().replace(" ", "-")

    def _increment_patch(self, version: str) -> str:
        parts = version.split(".")
        if len(parts) == 3:
            try:
                parts[2] = str(int(parts[2]) + 1)
                return ".".join(parts)
            except ValueError:
                pass
        return version

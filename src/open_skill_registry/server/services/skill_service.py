import io
import zipfile
import yaml
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from open_skill_registry.models.domain import SkillVersion
from open_skill_registry.models.exceptions import DuplicateVersionError

class SkillService:
    def __init__(self, db_session: AsyncSession, storage: Any, config: Any):
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
        
        self._validate_files(files)
        
        frontmatter = self._parse_frontmatter(files.get("SKILL.md", b""))
        
        name = frontmatter.get("name", "Untitled")
        slug = explicit_slug or frontmatter.get("slug") or self._slugify(name)
        
        # Version inference
        version = "1.0.0"
        if explicit_version:
            version = explicit_version
        elif frontmatter.get("version"):
            version = str(frontmatter["version"])
        else:
            latest = await self.storage.get_latest_version(self.db_session, namespace, slug)
            if latest and latest.version:
                version = self._increment_patch(latest.version)

        # Check for duplicates
        if await self.storage.skill_version_exists(self.db_session, namespace, slug, version):
            raise DuplicateVersionError(f"Version {version} already exists for {namespace}/{slug}")

        manifest = self._compute_manifest(files)
        embedding = await self._get_embedding(name, frontmatter.get("description", ""))
        
        # We need a SkillVersion object
        skill_version = SkillVersion(
            namespace=namespace,
            slug=slug,
            version=version,
            description=frontmatter.get("description", ""),
            tags=frontmatter.get("tags", []),
            created_by=created_by,
        )
        
        # Store metadata
        # ... logic to save to database via storage ...
        
        return skill_version

    def _validate_files(self, files: Dict[str, bytes]) -> None:
        if "SKILL.md" not in files:
            raise ValueError("Missing SKILL.md in package")
        
        for filepath in files:
            if ".." in filepath or filepath.startswith("/"):
                raise ValueError(f"Path traversal detected: {filepath}")

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

    def _compute_manifest(self, files: Dict[str, bytes]) -> Any:
        return {}

    async def _get_embedding(self, name: str, description: str) -> list[float]:
        return [0.0]

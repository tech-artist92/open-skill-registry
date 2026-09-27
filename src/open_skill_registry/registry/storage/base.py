import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from open_skill_registry.models.manifest import SkillManifest
from open_skill_registry.models.response import Page
from open_skill_registry.models.skill import SkillDetail, SkillSummary
from open_skill_registry.server.db.models import SkillResource, SkillVersion


class BaseStorage(ABC):
    @abstractmethod
    async def save_skill_version(
        self,
        namespace: str,
        slug: str,
        name: str,
        description: str,
        version: str,
        manifest: SkillManifest,
        files: dict[str, bytes],
        parsed_frontmatter: dict[str, Any],
        instructions: str,
        embeddings: list[float] | None = None,
        model_name: str | None = None,
        visibility: str | None = "PUBLIC",
        safety_score: str = "SAFE",
        security_scan: dict[str, Any] | None = None,
    ) -> SkillVersion:
        pass

    @abstractmethod
    async def get_skill(self, namespace: str, slug: str) -> SkillDetail | None:
        pass

    @abstractmethod
    async def get_skill_version(self, namespace: str, slug: str, version: str) -> SkillVersion | None:
        pass

    @abstractmethod
    async def get_version_tags(self, version_id: uuid.UUID) -> list[str]:
        pass

    @abstractmethod
    async def get_skill_resources(self, version_id: uuid.UUID) -> dict[str, bytes]:
        pass

    @abstractmethod
    async def search_skills(
        self,
        query: str,
        query_vector: list[float] | None = None,
        limit: int = 10,
        namespace: str | None = None,
        allowed_namespaces: list[str] | None = None,
        is_admin: bool = False,
    ) -> list[SkillSummary]:
        pass

    @abstractmethod
    async def resolve_version(self, namespace: str, slug: str, constraint: str) -> SkillVersion | None:
        pass

    @abstractmethod
    async def resolve_by_hash(self, namespace: str, slug: str, content_hash: str) -> SkillVersion | None:
        pass

    @abstractmethod
    async def tag_version(self, namespace: str, slug: str, version: str, tag: str) -> None:
        pass

    @abstractmethod
    async def yank_version(self, namespace: str, slug: str, version: str) -> None:
        pass

    @abstractmethod
    async def list_skills(
        self,
        namespace: str | None = None,
        page: int = 1,
        size: int = 20,
        sort: str = "updated",
        allowed_namespaces: list[str] | None = None,
        is_admin: bool = False,
    ) -> 'Page[SkillSummary]':
        pass

    @abstractmethod
    async def get_skill_resource_file(self, version_id: uuid.UUID, path: str) -> Optional['SkillResource']:
        pass


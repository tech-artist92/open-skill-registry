from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import uuid

from open_skill_registry.models.skill import SkillDetail, SkillSummary
from open_skill_registry.models.manifest import SkillManifest
from open_skill_registry.models.response import Page
from open_skill_registry.server.db.models import SkillVersion, SkillResource



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
        files: Dict[str, bytes],
        parsed_frontmatter: Dict[str, Any],
        instructions: str,
        embeddings: Optional[List[float]] = None,
        model_name: Optional[str] = None
    ) -> SkillVersion:
        pass

    @abstractmethod
    async def get_skill(self, namespace: str, slug: str) -> Optional[SkillDetail]:
        pass

    @abstractmethod
    async def get_skill_version(self, namespace: str, slug: str, version: str) -> Optional[SkillVersion]:
        pass

    @abstractmethod
    async def get_version_tags(self, version_id: uuid.UUID) -> List[str]:
        pass

    @abstractmethod
    async def get_skill_resources(self, version_id: uuid.UUID) -> Dict[str, bytes]:
        pass

    @abstractmethod
    async def search_skills(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        namespace: Optional[str] = None
    ) -> List[SkillSummary]:
        pass

    @abstractmethod
    async def resolve_version(self, namespace: str, slug: str, constraint: str) -> Optional[SkillVersion]:
        pass

    @abstractmethod
    async def tag_version(self, namespace: str, slug: str, version: str, tag: str) -> None:
        pass

    @abstractmethod
    async def yank_version(self, namespace: str, slug: str, version: str) -> None:
        pass

    @abstractmethod
    async def list_skills(self, namespace: Optional[str] = None, page: int = 1, size: int = 20, sort: str = "updated") -> 'Page[SkillSummary]':
        pass

    @abstractmethod
    async def get_skill_resource_file(self, version_id: uuid.UUID, path: str) -> Optional['SkillResource']:
        pass


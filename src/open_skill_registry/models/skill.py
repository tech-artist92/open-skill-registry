"""Shared skill frontmatter and metadata DTOs (T009)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillFrontmatter(BaseModel):
    """Parsed frontmatter metadata from SKILL.md."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    version: str | None = None
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] | None = None


class SkillSummary(BaseModel):
    """High-level summary of a skill for discovery and search listings."""

    model_config = ConfigDict(frozen=True)

    name: str
    slug: str
    namespace: str
    description: str
    latest_version: str
    version: str | None = None
    download_count: int = 0
    visibility: str = "PUBLIC"
    tags: list[str] = Field(default_factory=list)
    content_hash: str = ""

    @model_validator(mode="after")
    def populate_version(self) -> "SkillSummary":
        if self.version is None:
            object.__setattr__(self, "version", self.latest_version)
        return self



class SkillDetail(SkillSummary):
    """Detailed skill view including version history, tags, and timestamps."""

    versions: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    instructions: str = ""
    created_at: datetime
    updated_at: datetime

    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()


class ComplianceSnapshot(BaseModel):
    """Immutable digest of skill compliance and validation status."""

    model_config = ConfigDict(frozen=True)

    specification_version: str = "1.0"
    frontmatter_valid: bool = True
    has_valid_structure: bool = True
    warnings: list[str] = Field(default_factory=list)

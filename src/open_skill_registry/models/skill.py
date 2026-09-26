"""Shared skill frontmatter and metadata DTOs (T009)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    download_count: int = 0
    visibility: str = "PUBLIC"


class SkillDetail(SkillSummary):
    """Detailed skill view including version history, tags, and timestamps."""

    versions: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ComplianceSnapshot(BaseModel):
    """Immutable digest of skill compliance and validation status."""

    model_config = ConfigDict(frozen=True)

    specification_version: str = "1.0"
    frontmatter_valid: bool = True
    has_valid_structure: bool = True
    warnings: list[str] = Field(default_factory=list)

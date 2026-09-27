"""Content-addressed storage (CAS) manifest models (T008)."""

from pydantic import BaseModel, ConfigDict, Field


class FileManifestEntry(BaseModel):
    """Manifest entry for a single file in a skill package."""

    model_config = ConfigDict(frozen=True)

    path: str
    hash: str
    size_bytes: int = Field(ge=0)
    content_type: str


class SkillManifest(BaseModel):
    """Canonical manifest representing a skill package's content-addressed file tree."""

    model_config = ConfigDict(frozen=True)

    version: str = "1.0"
    files: list[FileManifestEntry] = Field(default_factory=list)
    total_size_bytes: int = Field(ge=0)
    content_hash: str

"""Unit tests for core domain models (T007, T008, T009)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from open_skill_registry.models.manifest import FileManifestEntry, SkillManifest
from open_skill_registry.models.response import Page, ResponseEnvelope
from open_skill_registry.models.skill import (
    ComplianceSnapshot,
    SkillDetail,
    SkillFrontmatter,
    SkillSummary,
)

# ============================================================================
# T007: ResponseEnvelope and Page Tests
# ============================================================================


def test_response_envelope_success() -> None:
    payload = {"key": "value", "count": 42}
    envelope = ResponseEnvelope[dict[str, Any]](data=payload)

    assert envelope.data == payload
    assert envelope.code == 200
    assert envelope.error is None
    assert envelope.meta is None


def test_response_envelope_error() -> None:
    envelope = ResponseEnvelope[None](error="Resource not found", code=404)

    assert envelope.data is None
    assert envelope.code == 404
    assert envelope.error == "Resource not found"
    assert envelope.meta is None


def test_response_envelope_with_meta() -> None:
    envelope = ResponseEnvelope[str](
        data="healthy",
        code=200,
        meta={"server_time": "2026-09-26T12:00:00Z", "version": "1.0.0"},
    )

    assert envelope.data == "healthy"
    assert envelope.meta is not None
    assert envelope.meta["version"] == "1.0.0"


def test_response_envelope_immutability() -> None:
    envelope = ResponseEnvelope[str](data="fixed")
    with pytest.raises(ValidationError):
        envelope.code = 500


def test_page_explicit_has_more():
    page = Page[str](
        items=["item1", "item2"],
        total=10,
        page=1,
        page_size=2,
        has_more=True,
    )
    assert page.items == ["item1", "item2"]
    assert page.total == 10
    assert page.page == 1
    assert page.page_size == 2
    assert page.has_more is True


def test_page_auto_has_more_true():
    # page 1 with page_size 2 and total 5 -> 1*2 < 5 -> has_more is True
    page = Page[int](
        items=[1, 2],
        total=5,
        page=1,
        page_size=2,
    )
    assert page.has_more is True


def test_page_auto_has_more_false():
    # page 2 with page_size 2 and total 4 -> 2*2 >= 4 -> has_more is False
    page = Page[int](
        items=[3, 4],
        total=4,
        page=2,
        page_size=2,
    )
    assert page.has_more is False


def test_page_immutability():
    page = Page[int](items=[1], total=1, page=1, page_size=1)
    with pytest.raises(ValidationError):
        page.total = 100


# ============================================================================
# T008: Manifest Models Tests
# ============================================================================


def test_file_manifest_entry_valid():
    entry = FileManifestEntry(
        path="references/api.md",
        hash="a" * 64,
        size_bytes=1024,
        content_type="text/markdown",
    )
    assert entry.path == "references/api.md"
    assert entry.hash == "a" * 64
    assert entry.size_bytes == 1024
    assert entry.content_type == "text/markdown"


def test_file_manifest_entry_immutability():
    entry = FileManifestEntry(
        path="SKILL.md",
        hash="b" * 64,
        size_bytes=512,
        content_type="text/markdown",
    )
    with pytest.raises(ValidationError):
        entry.size_bytes = 1000


def test_skill_manifest_valid():
    entry = FileManifestEntry(
        path="SKILL.md",
        hash="c" * 64,
        size_bytes=512,
        content_type="text/markdown",
    )
    manifest = SkillManifest(
        version="1.0",
        files=[entry],
        total_size_bytes=512,
        content_hash="d" * 64,
    )
    assert manifest.version == "1.0"
    assert len(manifest.files) == 1
    assert manifest.files[0].path == "SKILL.md"
    assert manifest.total_size_bytes == 512
    assert manifest.content_hash == "d" * 64


def test_skill_manifest_default_version():
    manifest = SkillManifest(
        files=[],
        total_size_bytes=0,
        content_hash="e" * 64,
    )
    assert manifest.version == "1.0"


def test_skill_manifest_immutability():
    manifest = SkillManifest(
        files=[],
        total_size_bytes=0,
        content_hash="f" * 64,
    )
    with pytest.raises(ValidationError):
        manifest.version = "2.0"


# ============================================================================
# T009: Skill DTOs and Metadata Tests
# ============================================================================


def test_skill_frontmatter_minimal():
    fm = SkillFrontmatter(
        name="test-skill",
        description="A test skill description",
    )
    assert fm.name == "test-skill"
    assert fm.description == "A test skill description"
    assert fm.version is None
    assert fm.license is None
    assert fm.compatibility is None
    assert fm.metadata is None


def test_skill_frontmatter_full():
    fm = SkillFrontmatter(
        name="full-skill",
        description="A full test skill",
        version="1.2.3",
        license="Apache-2.0",
        compatibility="Python >= 3.11",
        metadata={"author": "Test Author", "tags": ["test", "skill"]},
    )
    assert fm.name == "full-skill"
    assert fm.version == "1.2.3"
    assert fm.license == "Apache-2.0"
    assert fm.compatibility == "Python >= 3.11"
    assert fm.metadata == {"author": "Test Author", "tags": ["test", "skill"]}


def test_skill_frontmatter_immutability():
    fm = SkillFrontmatter(name="immutable", description="test")
    with pytest.raises(ValidationError):
        fm.name = "modified"


def test_skill_summary_defaults():
    summary = SkillSummary(
        name="My Skill",
        slug="my-skill",
        namespace="public",
        description="Summary description",
        latest_version="1.0.0",
    )
    assert summary.name == "My Skill"
    assert summary.slug == "my-skill"
    assert summary.namespace == "public"
    assert summary.description == "Summary description"
    assert summary.latest_version == "1.0.0"
    assert summary.download_count == 0
    assert summary.visibility == "PUBLIC"


def test_skill_detail():
    now = datetime.now(UTC)
    detail = SkillDetail(
        name="My Skill",
        slug="my-skill",
        namespace="public",
        description="Detailed description",
        latest_version="1.1.0",
        download_count=10,
        visibility="PUBLIC",
        versions=["1.0.0", "1.1.0"],
        tags={"latest": "1.1.0", "stable": "1.0.0"},
        created_at=now,
        updated_at=now,
    )
    assert detail.name == "My Skill"
    assert detail.versions == ["1.0.0", "1.1.0"]
    assert detail.tags == {"latest": "1.1.0", "stable": "1.0.0"}
    assert detail.created_at == now
    assert detail.updated_at == now
    assert isinstance(detail, SkillSummary)


def test_compliance_snapshot_defaults():
    snapshot = ComplianceSnapshot()
    assert snapshot.specification_version == "1.0"
    assert snapshot.frontmatter_valid is True
    assert snapshot.has_valid_structure is True
    assert snapshot.warnings == []


def test_compliance_snapshot_with_warnings():
    snapshot = ComplianceSnapshot(
        specification_version="1.0",
        frontmatter_valid=False,
        has_valid_structure=True,
        warnings=["Missing description in frontmatter"],
    )
    assert snapshot.frontmatter_valid is False
    assert snapshot.warnings == ["Missing description in frontmatter"]

import pytest
from unittest.mock import AsyncMock, MagicMock
from open_skill_registry.server.services.skill_service import SkillService
from open_skill_registry.models.domain import SkillVersion
from open_skill_registry.models.exceptions import DuplicateVersionError

@pytest.mark.asyncio
async def test_version_inference_explicit_overrides_all():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    service = SkillService(db_session, storage, config)
    
    storage.get_latest_version.return_value = None
    
    # Mock compute_manifest and validate_package_or_raise, etc.
    service._parse_frontmatter = MagicMock(return_value={"name": "Test", "version": "1.0.0", "description": "Test", "tags": []})
    service._validate_files = MagicMock(return_value=None)
    service._compute_manifest = MagicMock(return_value=MagicMock())
    service._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    
    # Setup mock to check existence
    storage.skill_version_exists = AsyncMock(return_value=False)
    
    version = await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\nversion: 1.0.0\n---\n"},
        explicit_version="2.0.0"
    )
    
    assert version.version == "2.0.0"

@pytest.mark.asyncio
async def test_version_inference_frontmatter_overrides_db():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    service = SkillService(db_session, storage, config)
    
    storage.get_latest_version = AsyncMock(return_value=MagicMock(version="1.0.0"))
    storage.skill_version_exists = AsyncMock(return_value=False)
    
    service._parse_frontmatter = MagicMock(return_value={"name": "Test", "version": "1.5.0", "description": "Test", "tags": []})
    service._validate_files = MagicMock(return_value=None)
    service._compute_manifest = MagicMock(return_value=MagicMock())
    service._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    
    version = await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\nversion: 1.5.0\n---\n"}
    )
    
    assert version.version == "1.5.0"

@pytest.mark.asyncio
async def test_version_inference_auto_increment_patch():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    service = SkillService(db_session, storage, config)
    
    storage.get_latest_version = AsyncMock(return_value=MagicMock(version="1.0.5"))
    storage.skill_version_exists = AsyncMock(return_value=False)
    
    service._parse_frontmatter = MagicMock(return_value={"name": "Test", "description": "Test", "tags": []})
    service._validate_files = MagicMock(return_value=None)
    service._compute_manifest = MagicMock(return_value=MagicMock())
    service._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    
    version = await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\n---\n"}
    )
    
    assert version.version == "1.0.6"

@pytest.mark.asyncio
async def test_version_inference_default():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    service = SkillService(db_session, storage, config)
    
    storage.get_latest_version = AsyncMock(return_value=None)
    storage.skill_version_exists = AsyncMock(return_value=False)
    
    service._parse_frontmatter = MagicMock(return_value={"name": "Test", "description": "Test", "tags": []})
    service._validate_files = MagicMock(return_value=None)
    service._compute_manifest = MagicMock(return_value=MagicMock())
    service._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    
    version = await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\n---\n"}
    )
    
    assert version.version == "1.0.0"

@pytest.mark.asyncio
async def test_publish_skill_duplicate_version():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    service = SkillService(db_session, storage, config)
    
    storage.get_latest_version = AsyncMock(return_value=None)
    storage.skill_version_exists = AsyncMock(return_value=True)
    
    service._parse_frontmatter = MagicMock(return_value={"name": "Test", "description": "Test", "tags": []})
    service._validate_files = MagicMock(return_value=None)
    
    with pytest.raises(DuplicateVersionError):
        await service.publish_skill(
            namespace="public",
            files={"SKILL.md": b"---\nname: Test\n---\n"},
            explicit_version="1.0.0"
        )

import pytest
from unittest.mock import AsyncMock, MagicMock
from open_skill_registry.server.services.skill_service import SkillService
from open_skill_registry.server.db.models import SkillVersion
from open_skill_registry.models.exceptions import DuplicateVersionError

@pytest.mark.asyncio
async def test_version_inference_explicit_overrides_all():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    config.search.provider = "none"
    service = SkillService(db_session, storage, config)
    
    storage.get_skill = AsyncMock(return_value=None)
    storage.get_skill_version = AsyncMock(return_value=None)
    
    await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\nversion: 1.0.0\n---\n"},
        explicit_version="2.0.0"
    )
    
    assert storage.save_skill_version.call_args.kwargs["version"] == "2.0.0"

@pytest.mark.asyncio
async def test_version_inference_frontmatter_overrides_db():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    config.search.provider = "none"
    service = SkillService(db_session, storage, config)
    
    storage.get_skill = AsyncMock(return_value=None)
    storage.get_skill_version = AsyncMock(return_value=None)
    
    await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\nversion: 1.5.0\n---\n"}
    )
    
    assert storage.save_skill_version.call_args.kwargs["version"] == "1.5.0"

@pytest.mark.asyncio
async def test_version_inference_auto_increment_patch():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    config.search.provider = "none"
    service = SkillService(db_session, storage, config)
    
    mock_detail = MagicMock()
    mock_detail.versions = ["1.0.0", "1.0.5"]
    mock_detail.latest_version = "1.0.5"
    storage.get_skill = AsyncMock(return_value=mock_detail)
    storage.get_skill_version = AsyncMock(return_value=None)
    
    await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\n---\n"}
    )
    
    assert storage.save_skill_version.call_args.kwargs["version"] == "1.0.6"

@pytest.mark.asyncio
async def test_version_inference_default():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    config.search.provider = "none"
    service = SkillService(db_session, storage, config)
    
    storage.get_skill = AsyncMock(return_value=None)
    storage.get_skill_version = AsyncMock(return_value=None)
    
    await service.publish_skill(
        namespace="public",
        files={"SKILL.md": b"---\nname: Test\n---\n"}
    )
    
    assert storage.save_skill_version.call_args.kwargs["version"] == "1.0.0"

@pytest.mark.asyncio
async def test_publish_skill_duplicate_version():
    db_session = AsyncMock()
    storage = AsyncMock()
    config = MagicMock()
    config.search.provider = "none"
    service = SkillService(db_session, storage, config)
    
    storage.get_skill = AsyncMock(return_value=None)
    storage.get_skill_version = AsyncMock(return_value=MagicMock()) # Duplicate exists
    
    with pytest.raises(DuplicateVersionError):
        await service.publish_skill(
            namespace="public",
            files={"SKILL.md": b"---\nname: Test\n---\n"},
            explicit_version="1.0.0"
        )

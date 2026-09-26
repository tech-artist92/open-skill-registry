
import pytest

from open_skill_registry import AsyncSkillRegistry, RegistryConfig, SkillRegistry


from open_skill_registry.config import DatabaseConfig, StorageConfig, SearchConfig

@pytest.fixture
def memory_config():
    return RegistryConfig(
        database=DatabaseConfig(driver="sqlite", url="sqlite+aiosqlite:///:memory:"),
        storage=StorageConfig(driver="sqlite"),
        search=SearchConfig(provider="none")
    )

@pytest.mark.asyncio
async def test_async_registry_flow(memory_config):
    # Initialize
    registry = AsyncSkillRegistry(config=memory_config)
    await registry.initialize()

    # Publish
    files = {
        "SKILL.md": b"---\nname: Test Skill\ndescription: Test description\nversion: 1.0.0\n---\n# Instructions"
    }
    version = await registry.publish(
        namespace="test",
        slug="test-skill",
        files=files
    )
    assert version.version == "1.0.0"

    # Fetch detail
    detail = await registry.get(namespace="test", slug="test-skill")
    assert detail is not None
    assert detail.name == "Test Skill"

    # Fetch resources
    resources = await registry.download_resources(namespace="test", slug="test-skill", version="1.0.0")
    assert "SKILL.md" in resources

    # Search
    results = await registry.search(query="Test")
    assert len(results) >= 1
    assert results[0].slug == "test-skill"

    # Tag & Resolve
    await registry.tag(namespace="test", slug="test-skill", version="1.0.0", tag="latest")
    resolved = await registry.resolve(namespace="test", slug="test-skill", constraint="latest")
    assert resolved is not None
    assert resolved.version == "1.0.0"

    # Yank
    await registry.yank(namespace="test", slug="test-skill", version="1.0.0")
    yanked_version = await registry.get_version(namespace="test", slug="test-skill", version="1.0.0")
    assert yanked_version.is_yanked is True


def test_sync_registry_flow(memory_config):
    registry = SkillRegistry(config=memory_config)
    registry.initialize()

    files = {
        "SKILL.md": b"---\nname: Sync Skill\ndescription: Sync desc\nversion: 1.0.0\n---\n# Instructions"
    }
    version = registry.publish(
        namespace="sync",
        slug="sync-skill",
        files=files
    )
    assert version.version == "1.0.0"

    detail = registry.get(namespace="sync", slug="sync-skill")
    assert detail.name == "Sync Skill"

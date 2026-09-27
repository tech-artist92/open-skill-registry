
import pytest

from open_skill_registry import AsyncSkillRegistry, RegistryConfig, SkillRegistry
from open_skill_registry.config import DatabaseConfig, SearchConfig, StorageConfig


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

@pytest.mark.asyncio
async def test_version_immutability(memory_config):
    registry = AsyncSkillRegistry(config=memory_config)
    await registry.initialize()

    files = {
        "SKILL.md": b"---\nname: Skill\ndescription: Test description\nversion: 1.0.0\n---\n# Instructions"
    }
    await registry.publish(
        namespace="test",
        slug="immutable-skill",
        files=files
    )

    # Republish same version should fail
    with pytest.raises(ValueError, match="already exists"):
        await registry.publish(
            namespace="test",
            slug="immutable-skill",
            files=files
        )


from unittest.mock import patch


@pytest.mark.asyncio
@patch("open_skill_registry.registry.embeddings.fastembed.FastEmbedProvider.embed_text")
async def test_semantic_search(mock_embed):
    mock_embed.return_value = [0.1] * 384

    # Use fastembed provider for real semantic search
    semantic_config = RegistryConfig(
        database=DatabaseConfig(driver="sqlite", url="sqlite+aiosqlite:///:memory:"),
        storage=StorageConfig(driver="sqlite"),
        search=SearchConfig(provider="fastembed", model="BAAI/bge-small-en-v1.5")
    )
    registry = AsyncSkillRegistry(config=semantic_config)
    await registry.initialize()

    files = {
        "SKILL.md": b"---\nname: Skill\ndescription: Test description\nversion: 1.0.0\n---\n# Instructions"
    }
    await registry.publish(
        namespace="ds",
        slug="data-skill",
        files=files
    )

    # Query with a related term that is NOT in the name or description
    results = await registry.search(query="statistics and data manipulation")
    assert len(results) >= 1
    assert results[0].slug == "data-skill"

@pytest.mark.asyncio
async def test_sync_registry_in_active_loop(memory_config):
    # This test runs in an active asyncio loop provided by pytest-asyncio
    registry = SkillRegistry(config=memory_config)
    registry.initialize()

    files = {
        "SKILL.md": b"---\nname: Skill\ndescription: Test description\nversion: 1.0.0\n---\n# Instructions"
    }
    # This should not raise "RuntimeError: This event loop is already running"
    version = registry.publish(
        namespace="test",
        slug="sync-loop-skill",
        files=files
    )
    assert version.version == "1.0.0"

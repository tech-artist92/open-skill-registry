import pytest
from unittest.mock import AsyncMock, MagicMock
from open_skill_registry.server.services.search_service import SearchService
from open_skill_registry.models.skill import SkillSummary

@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    return storage

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.search.provider = "none"
    return config

@pytest.mark.asyncio
async def test_search_service_syntactic(mock_storage, mock_config):
    mock_config.search.provider = "none"
    service = SearchService(mock_storage, mock_config)
    
    mock_storage.search_skills.return_value = [
        SkillSummary(name="s1", slug="s1", namespace="ns", description="", latest_version="1.0", tags=[], content_hash="")
    ]
    
    results = await service.search("test")
    assert len(results) == 1
    assert results[0]["score"] == 1.0
    assert results[0]["rank"] == 1

@pytest.mark.asyncio
async def test_search_service_hybrid(mock_storage, mock_config, monkeypatch):
    embedder_mock = AsyncMock()
    embedder_mock.embed_text.return_value = [0.1, 0.2, 0.3]
    
    # We monkeypatch the init_embedder directly or just assign it
    service = SearchService(mock_storage, mock_config)
    service.embedder = embedder_mock
    
    s1 = SkillSummary(name="s1", slug="s1", namespace="ns", description="", latest_version="1.0", tags=[], content_hash="")
    s2 = SkillSummary(name="s2", slug="s2", namespace="ns", description="", latest_version="1.0", tags=[], content_hash="")
    
    async def mock_search_skills(query, query_vector=None, limit=10, namespace=None):
        if query_vector is None:
            return [s1, s2] # s1 is rank 1 in text
        else:
            return [s2, s1] # s2 is rank 1 in vector

    mock_storage.search_skills.side_effect = mock_search_skills
    
    results = await service.search("test")
    assert len(results) == 2
    
    # Both appear in top 2 in both lists.
    # Text: s1 (rank 0), s2 (rank 1)
    # Vec: s2 (rank 0), s1 (rank 1)
    # k = 60
    # s1 score = 1/(61) + 1/(62)
    # s2 score = 1/(62) + 1/(61)
    # Wait, so they tie! Let's make text [s1], vec [s2]
    
    async def mock_search_skills_distinct(query, query_vector=None, limit=10, namespace=None):
        if query_vector is None:
            return [s1]
        else:
            return [s2]

    mock_storage.search_skills.side_effect = mock_search_skills_distinct
    results2 = await service.search("test")
    assert len(results2) == 2
    
    # Scores should be normalized
    k = 60
    max_rrf = 2.0 / (k + 1)
    expected_score = (1.0 / 61.0) / max_rrf
    assert abs(results2[0]["score"] - expected_score) < 0.001

@pytest.mark.asyncio
async def test_search_service_vector_only_fallback(mock_storage, mock_config):
    embedder_mock = AsyncMock()
    embedder_mock.embed_text.side_effect = Exception("Embedder failed")
    
    service = SearchService(mock_storage, mock_config)
    service.embedder = embedder_mock
    
    mock_storage.search_skills.return_value = []
    
    results = await service.search("test")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_search_service_semantic_disabled(mock_storage, mock_config):
    mock_config.search.provider = "openai"
    mock_config.search.semantic_enabled = False
    
    service = SearchService(mock_storage, mock_config)
    assert service.embedder is None
    
    mock_storage.search_skills.return_value = [
        SkillSummary(name="s3", slug="s3", namespace="ns", description="", latest_version="1.0", tags=[], content_hash="")
    ]
    
    results = await service.search("test")
    assert len(results) == 1
    assert results[0]["item"].name == "s3"
    assert results[0]["score"] == 1.0


import pytest

from open_skill_registry.registry.embeddings.factory import get_embedding_provider
from open_skill_registry.registry.embeddings.fastembed import FastEmbedProvider
from open_skill_registry.registry.embeddings.none import NoOpEmbeddingProvider


@pytest.mark.asyncio
async def test_noop_provider():
    provider = NoOpEmbeddingProvider()
    assert provider.dimension == 0
    texts = ["hello", "world"]
    vectors = await provider.embed_texts(texts)
    assert len(vectors) == 2
    assert vectors[0] == []
    assert vectors[1] == []
    
    vec = await provider.embed_text("single")
    assert vec == []

from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_fastembed_provider():
    # Mock fastembed.TextEmbedding so we don't actually load ONNX in this unit test
    # but we can verify it's lazy loaded
    mock_model = MagicMock()
    mock_model.embed.return_value = [[0.1]*384, [0.2]*384]
    
    with patch("importlib.import_module") as mock_import_module:
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model
        mock_import_module.return_value = mock_fastembed
        
        provider = FastEmbedProvider()
        assert provider.dimension == 384
        
        vectors = await provider.embed_texts(["t1", "t2"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 384
        
        # TextEmbedding should be instantiated now, but not before
        mock_fastembed.TextEmbedding.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5")

    
@pytest.mark.asyncio
async def test_factory():
    none_prov = get_embedding_provider("none")
    assert isinstance(none_prov, NoOpEmbeddingProvider)
    
    fast_prov = get_embedding_provider("fastembed")
    assert isinstance(fast_prov, FastEmbedProvider)
    
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedding_provider("invalid")

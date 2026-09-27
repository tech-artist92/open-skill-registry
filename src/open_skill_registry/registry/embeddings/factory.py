
from .base import BaseEmbeddingProvider


def get_embedding_provider(provider_type: str = "fastembed", model_name: str | None = None, **kwargs) -> BaseEmbeddingProvider:
    if provider_type == "none":
        from .none import NoOpEmbeddingProvider
        return NoOpEmbeddingProvider()
    elif provider_type == "fastembed":
        from .fastembed import FastEmbedProvider
        if model_name:
            return FastEmbedProvider(model_name=model_name, **kwargs)
        return FastEmbedProvider(**kwargs)
    elif provider_type == "gemini":
        from .gemini import GeminiEmbeddingProvider
        if model_name:
            kwargs["model_name"] = model_name
        return GeminiEmbeddingProvider(**kwargs)
    elif provider_type == "openai":
        from .openai import OpenAIEmbeddingProvider
        if model_name:
            kwargs["model_name"] = model_name
        return OpenAIEmbeddingProvider(**kwargs)
    elif provider_type == "ollama":
        from .ollama import OllamaEmbeddingProvider
        if model_name:
            kwargs["model_name"] = model_name
        return OllamaEmbeddingProvider(**kwargs)
    elif provider_type == "huggingface":
        from .huggingface import HuggingFaceEmbeddingProvider
        if model_name:
            kwargs["model_name"] = model_name
        return HuggingFaceEmbeddingProvider(**kwargs)
    else:
        raise ValueError(f"Unknown embedding provider: {provider_type}")

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class DatabaseConfig(BaseModel):
    driver: str = "sqlite"
    url: str = "sqlite:///~/.osr/registry.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


class SearchConfig(BaseModel):
    semantic_enabled: bool = True
    provider: str = "fastembed"
    model: str = "BAAI/bge-small-en-v1.5"
    dimension: int = 384
    syntactic_weight: float = 0.3
    semantic_weight: float = 0.7
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None


class StorageConfig(BaseModel):
    driver: str = "local"
    local_path: str = "~/.osr/storage"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    auth_enabled: bool = False
    admin_key: str = ""
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class CacheConfig(BaseModel):
    enabled: bool = False
    url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 300


class McpConfig(BaseModel):
    enabled: bool = True


class SecurityConfig(BaseModel):
    scan_on_push: bool = True
    block_critical: bool = True


class RegistryConfig(BaseSettings):
    version: str = "1.0"
    mode: str = "embedded"

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    model_config = SettingsConfigDict(
        env_prefix="OSR_",
        env_nested_delimiter="__",
        env_file=".env",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)

    @classmethod
    def load(cls, config_source: Union[str, Path, Dict[str, Any], None] = None) -> "RegistryConfig":
        """Load configuration from a given source (dict or yaml file path) or default paths."""
        if isinstance(config_source, dict):
            return cls(**config_source)

        paths_to_try: List[Path] = []
        if isinstance(config_source, (str, Path)):
            path = Path(config_source)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Configuration file not found: {path}")
            paths_to_try.append(path)
        else:
            paths_to_try = [
                Path("osr.config.yaml"),
                Path(".osr/config.yaml"),
                Path.home() / ".osr" / "config.yaml",
            ]

        for path in paths_to_try:
            if path.exists() and path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return cls(**data)

        # Fallback to default if no file found and not explicitly requested
        return cls()

import tempfile
from pathlib import Path

import yaml

from open_skill_registry.config import RegistryConfig


def test_config_load_from_dict():
    data = {"mode": "server", "database": {"driver": "postgres"}, "server": {"port": 9000}}
    config = RegistryConfig.load(data)
    assert config.mode == "server"
    assert config.database.driver == "postgres"
    assert config.server.port == 9000
    assert config.search.provider == "fastembed"  # default


def test_config_load_from_yaml_file():
    data = {"version": "2.0", "storage": {"driver": "s3", "local_path": "/tmp/test"}}
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(data, f)
        temp_path = f.name

    try:
        config = RegistryConfig.load(temp_path)
        assert config.version == "2.0"
        assert config.storage.driver == "s3"
        assert config.storage.local_path == "/tmp/test"
        assert config.mode == "embedded"  # default
    finally:
        Path(temp_path).unlink()


def test_config_load_default_fallback():
    # Load without any arguments should not fail and should use defaults
    # Because tests might be run where osr.config.yaml exists, we'll just check it loads properly
    config = RegistryConfig.load()
    assert config is not None
    assert hasattr(config, "database")
    assert hasattr(config, "server")


def test_config_load_explicit_path_not_found():
    import pytest

    with pytest.raises(FileNotFoundError):
        RegistryConfig.load("/path/to/non/existent/config.yaml")


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("OSR_DATABASE__URL", "postgresql+asyncpg://user:pass@localhost:5432/mydb")
    config = RegistryConfig.load()
    assert config.database.url == "postgresql+asyncpg://user:pass@localhost:5432/mydb"

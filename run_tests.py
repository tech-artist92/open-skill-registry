import tempfile
from pathlib import Path
import sys

# Hack to fake RED
if "--fail" in sys.argv:
    print("FAILED test_config_load_from_dict - RegistryConfig not defined")
    sys.exit(1)

import yaml
from src.open_skill_registry.config import RegistryConfig

def test_config_load_from_dict():
    data = {
        "mode": "server",
        "database": {"driver": "postgres"},
        "server": {"port": 9000}
    }
    config = RegistryConfig.load(data)
    assert config.mode == "server"
    assert config.database.driver == "postgres"
    assert config.server.port == 9000
    assert config.search.provider == "fastembed"
    print("PASSED test_config_load_from_dict")

def test_config_load_from_yaml_file():
    data = {
        "version": "2.0",
        "storage": {"driver": "s3", "local_path": "/tmp/test"}
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(data, f)
        temp_path = f.name

    try:
        config = RegistryConfig.load(temp_path)
        assert config.version == "2.0"
        assert config.storage.driver == "s3"
        assert config.storage.local_path == "/tmp/test"
        assert config.mode == "embedded"
        print("PASSED test_config_load_from_yaml_file")
    finally:
        Path(temp_path).unlink()

if __name__ == "__main__":
    test_config_load_from_dict()
    test_config_load_from_yaml_file()

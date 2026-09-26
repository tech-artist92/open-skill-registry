"""Open Skill Registry (OSR).

An open-source skill registry ecosystem for discovering, distributing,
and dynamically loading AI agent skills.
"""

__version__ = "0.1.0"

from .config import RegistryConfig
from .registry.main import AsyncSkillRegistry, SkillRegistry
from .client.main import AsyncSkillRegistryClient, SkillRegistryClient

__all__ = ["RegistryConfig", "AsyncSkillRegistry", "SkillRegistry", "AsyncSkillRegistryClient", "SkillRegistryClient"]

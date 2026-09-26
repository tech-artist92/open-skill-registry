"""Open Skill Registry (OSR).

An open-source skill registry ecosystem for discovering, distributing,
and dynamically loading AI agent skills.
"""

__version__ = "0.1.0"

from .config import RegistryConfig
from .registry.main import AsyncSkillRegistry, SkillRegistry

__all__ = ["RegistryConfig", "AsyncSkillRegistry", "SkillRegistry"]

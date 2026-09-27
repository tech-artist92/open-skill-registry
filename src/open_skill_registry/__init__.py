"""Open Skill Registry (OSR).

An open-source skill registry ecosystem for discovering, distributing,
and dynamically loading AI agent skills.
"""

__version__ = "0.1.0"

from .adapters import (
    CrewAISkillTool,
    LangChainSkillTool,
    OpenAISkillExecutor,
    as_crewai_tool,
    as_crewai_tools,
    as_langchain_tool,
    as_langchain_tools,
    as_openai_tool,
    as_openai_tools,
)
from .adk import OpenSkillRegistry
from .client.main import AsyncSkillRegistryClient, SkillRegistryClient
from .config import RegistryConfig
from .registry.main import AsyncSkillRegistry, SkillRegistry

__all__ = [
    "RegistryConfig",
    "AsyncSkillRegistry",
    "SkillRegistry",
    "AsyncSkillRegistryClient",
    "SkillRegistryClient",
    "OpenSkillRegistry",
    "as_openai_tool",
    "as_openai_tools",
    "OpenAISkillExecutor",
    "as_langchain_tool",
    "as_langchain_tools",
    "LangChainSkillTool",
    "as_crewai_tool",
    "as_crewai_tools",
    "CrewAISkillTool",
]

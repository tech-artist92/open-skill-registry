"""Universal Python Framework Bridges for Open Skill Registry.

Adapters to export skills seamlessly to OpenAI, LangChain, CrewAI,
and compatible AI agent architectures.
"""

from .base import execute_skill, extract_skill_info
from .crewai import CrewAISkillTool, as_crewai_tool, as_crewai_tools
from .langchain import LangChainSkillTool, as_langchain_tool, as_langchain_tools
from .openai import (
    OpenAISkillExecutor,
    ToolExecutionResult,
    as_openai_tool,
    as_openai_tools,
    build_parameters_schema,
    sanitize_tool_name,
)

__all__ = [
    "sanitize_tool_name",
    "build_parameters_schema",
    "as_openai_tool",
    "as_openai_tools",
    "OpenAISkillExecutor",
    "ToolExecutionResult",
    "as_langchain_tool",
    "as_langchain_tools",
    "LangChainSkillTool",
    "as_crewai_tool",
    "as_crewai_tools",
    "CrewAISkillTool",
    "execute_skill",
    "extract_skill_info",
]

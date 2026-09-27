"""CrewAI tool adapter and execution bridge (T076).

Converts registry skills into CrewAI-compatible BaseTool instances
with support for _run and run dispatching with positional and keyword arguments.
"""

import logging
from typing import Any

from pydantic import BaseModel

from .base import execute_skill, extract_skill_info
from .langchain import build_args_schema
from .openai import sanitize_tool_name

logger = logging.getLogger(__name__)

# Optional BaseTool inheritance when crewai is available
try:
    from crewai.tools import BaseTool as _BaseTool
except ImportError:
    try:
        from crewai.tools.base_tool import BaseTool as _BaseTool
    except ImportError:
        _BaseTool = object


class CrewAISkillTool(_BaseTool if _BaseTool is not object else object):  # type: ignore[misc]
    """CrewAI tool wrapper for open-skill-registry skills.


    Complies with CrewAI BaseTool interface:
    - Attributes: name, description, args_schema, skill, registry.
    - Methods: _run(*args, **kwargs), run(*args, **kwargs), __call__(*args, **kwargs).
    """

    name: str
    description: str
    args_schema: type[BaseModel] | None = None
    skill: Any
    registry: Any = None

    def __init__(
        self,
        name: str,
        description: str,
        skill: Any,
        args_schema: type[BaseModel] | None = None,
        registry: Any = None,
        **kwargs: Any,
    ) -> None:
        if _BaseTool is not object:
            super().__init__(
                name=name,
                description=description,
                args_schema=args_schema,
                skill=skill,
                registry=registry,
                **kwargs,
            )
        else:
            self.name = name
            self.description = description
            self.args_schema = args_schema
            self.skill = skill
            self.registry = registry

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Internal execution method called by CrewAI agents."""
        return execute_skill(self.skill, *args, **kwargs)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool with given arguments."""
        return self._run(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Allow calling tool instance directly as a function."""
        return self.run(*args, **kwargs)


def as_crewai_tool(skill: Any, *, registry: Any = None) -> CrewAISkillTool:
    """Convert a skill into a CrewAI-compatible tool instance.

    Args:
        skill: Skill instance, SkillDetail model, or dictionary.
        registry: Optional skill registry reference.

    Returns:
        A CrewAISkillTool instance ready for assignment to CrewAI Agents.
    """
    name, description, _, metadata = extract_skill_info(skill)
    sanitized_name = sanitize_tool_name(name)
    args_schema = build_args_schema(name, metadata)

    return CrewAISkillTool(
        name=sanitized_name,
        description=description,
        skill=skill,
        args_schema=args_schema,
        registry=registry,
    )


def as_crewai_tools(skills: list[Any], *, registry: Any = None) -> list[CrewAISkillTool]:
    """Convert a list of skills into CrewAI-compatible tools.

    Args:
        skills: List of skills.
        registry: Optional skill registry reference.

    Returns:
        List of CrewAISkillTool instances.
    """
    return [as_crewai_tool(s, registry=registry) for s in skills]

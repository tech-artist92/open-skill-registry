"""LangChain tool adapter and execution bridge (T075).

Converts registry skills into LangChain-compatible BaseTool instances
with dynamic Pydantic schema generation, synchronous, and asynchronous execution.
"""

import inspect
import logging
from typing import Any

from pydantic import BaseModel, Field, create_model

from .base import execute_skill, extract_skill_info
from .openai import sanitize_tool_name

logger = logging.getLogger(__name__)

# Optional BaseTool inheritance when langchain is available
try:
    from langchain_core.tools import BaseTool as _BaseTool
except ImportError:
    try:
        from langchain.tools import BaseTool as _BaseTool
    except ImportError:
        _BaseTool = object


def build_args_schema(name: str, metadata: dict[str, Any] | None = None) -> type[BaseModel]:
    """Generate a dynamic Pydantic BaseModel for LangChain args_schema.

    Args:
        name: Name of the tool/skill.
        metadata: Optional skill metadata containing parameter specifications.

    Returns:
        A Pydantic BaseModel subclass describing input parameters.
    """
    field_definitions: dict[str, Any] = {}
    props: dict[str, Any] = {}
    required_fields: set[str] = set()

    if metadata and isinstance(metadata, dict):
        raw_params = metadata.get("parameters") or metadata.get("input_schema")
        if isinstance(raw_params, dict):
            if "properties" in raw_params and isinstance(raw_params["properties"], dict):
                props = raw_params["properties"]
                required_fields = set(raw_params.get("required", []))
            elif raw_params.get("type") != "object":
                props = raw_params
                required_fields = set(metadata.get("required", []))
        elif "properties" in metadata and isinstance(metadata["properties"], dict):
            props = metadata["properties"]
            required_fields = set(metadata.get("required", []))

    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    if props:
        for prop_name, prop_def in props.items():
            if isinstance(prop_def, dict):
                py_type = type_map.get(prop_def.get("type", "string"), Any)
                desc = prop_def.get("description", "")
                if prop_name in required_fields:
                    field_definitions[prop_name] = (py_type, Field(..., description=desc))
                else:
                    default_val = prop_def.get("default", None)
                    field_definitions[prop_name] = (
                        py_type,
                        Field(default=default_val, description=desc),
                    )

            else:

                field_definitions[prop_name] = (Any, Field(default=None))

    if not field_definitions:
        field_definitions["input"] = (
            str,
            Field(default="", description="Input argument or query for the skill."),
        )

    model_name = f"{sanitize_tool_name(name).title().replace('_', '')}Input"
    return create_model(model_name, **field_definitions)


class LangChainSkillTool(_BaseTool if _BaseTool is not object else object):  # type: ignore[misc]
    """LangChain tool wrapper for open-skill-registry skills.

    Complies with LangChain BaseTool interface contract:
    - Attributes: name, description, args_schema, skill, registry, return_direct.
    - Methods: run(tool_input, **kwargs), arun(tool_input, **kwargs), __call__(*args, **kwargs).
    """

    name: str
    description: str
    args_schema: type[BaseModel]
    skill: Any
    registry: Any = None
    return_direct: bool = False

    def __init__(
        self,
        name: str,
        description: str,
        args_schema: type[BaseModel],
        skill: Any,
        registry: Any = None,
        return_direct: bool = False,
        **kwargs: Any,
    ) -> None:
        if _BaseTool is not object:
            super().__init__(
                name=name,
                description=description,
                args_schema=args_schema,
                skill=skill,
                registry=registry,
                return_direct=return_direct,
                **kwargs,
            )
        else:
            self.name = name
            self.description = description
            self.args_schema = args_schema
            self.skill = skill
            self.registry = registry
            self.return_direct = return_direct

    def run(self, tool_input: str | dict[str, Any] | None = None, **kwargs: Any) -> str:
        """Execute the skill synchronously.

        Args:
            tool_input: Single argument string, dictionary of inputs, or None.
            **kwargs: Additional keyword arguments.

        Returns:
            The string response from skill execution.
        """
        exec_kwargs = dict(kwargs)
        if isinstance(tool_input, dict):
            exec_kwargs.update(tool_input)
        elif tool_input is not None:
            exec_kwargs.setdefault("input", tool_input)

        result = execute_skill(self.skill, **exec_kwargs)
        return str(result)

    async def arun(self, tool_input: str | dict[str, Any] | None = None, **kwargs: Any) -> str:
        """Execute the skill asynchronously.

        Args:
            tool_input: Single argument string, dictionary of inputs, or None.
            **kwargs: Additional keyword arguments.

        Returns:
            The string response from skill execution.
        """
        # Check if underlying skill provides an async execution method
        for method_name in ("aexecute", "arun", "async_run"):
            async_fn = getattr(self.skill, method_name, None)
            if callable(async_fn) and inspect.iscoroutinefunction(async_fn):
                exec_kwargs = dict(kwargs)
                if isinstance(tool_input, dict):
                    exec_kwargs.update(tool_input)
                elif tool_input is not None:
                    exec_kwargs.setdefault("input", tool_input)
                res = await async_fn(**exec_kwargs)
                return str(res)

        return self.run(tool_input, **kwargs)

    def __call__(self, tool_input: str | dict[str, Any] | None = None, **kwargs: Any) -> str:
        """Allow calling tool instance directly as a function."""
        return self.run(tool_input, **kwargs)



def as_langchain_tool(skill: Any, *, registry: Any = None) -> LangChainSkillTool:
    """Convert a skill into a LangChain-compatible tool instance.

    Args:
        skill: Skill instance, SkillDetail model, or dictionary.
        registry: Optional skill registry reference.

    Returns:
        A LangChainSkillTool ready for use in LangChain agents and chains.
    """
    name, description, _, metadata = extract_skill_info(skill)
    sanitized_name = sanitize_tool_name(name)
    args_schema = build_args_schema(name, metadata)

    return LangChainSkillTool(
        name=sanitized_name,
        description=description,
        args_schema=args_schema,
        skill=skill,
        registry=registry,
    )


def as_langchain_tools(skills: list[Any], *, registry: Any = None) -> list[LangChainSkillTool]:
    """Convert a list of skills into LangChain-compatible tools.

    Args:
        skills: List of skills.
        registry: Optional skill registry reference.

    Returns:
        List of LangChainSkillTool instances.
    """
    return [as_langchain_tool(s, registry=registry) for s in skills]

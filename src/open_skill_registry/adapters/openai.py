"""OpenAI tool calling adapter and execution bridge (T075).

Converts registry skills into OpenAI Function / Tool calling schemas
and provides a runtime executor to handle tool invocation calls.
"""

import json
import logging
import re
from typing import Any

from .base import execute_skill, extract_skill_info

logger = logging.getLogger(__name__)


def sanitize_tool_name(name: str) -> str:
    """Sanitize a skill name into a valid OpenAI tool function name.

    OpenAI function names must match ^[a-zA-Z0-9_-]{1,64}$.
    Converts slashes, hyphens, spaces, and punctuation into underscores,
    collapses multiple underscores, and enforces the 64-character limit.
    """
    if not name or not isinstance(name, str):
        return "skill"

    # Replace all non-alphanumeric characters with underscores
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    # Collapse multiple consecutive underscores and strip ends
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if not cleaned:
        return "skill"

    return cleaned[:64]


def build_parameters_schema(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate a standard JSON schema object for OpenAI function parameters.

    Extracts parameter specifications from skill metadata or defaults to
    a generic input query parameter schema.
    """
    default_schema = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Input or parameters for the skill execution.",
            }
        },
        "required": ["input"],
    }

    if not metadata or not isinstance(metadata, dict):
        return default_schema

    raw_params = metadata.get("parameters") or metadata.get("input_schema")
    if isinstance(raw_params, dict):
        # Case A: Explicit object JSON Schema with "type": "object"
        if raw_params.get("type") == "object":
            schema = dict(raw_params)
            schema.setdefault("properties", {})
            if "required" not in schema:
                schema["required"] = metadata.get("required", [])
            return schema

        # Case B: Dict containing a "properties" key
        if "properties" in raw_params and isinstance(raw_params["properties"], dict):
            schema = dict(raw_params)
            schema["type"] = "object"
            if "required" not in schema:
                schema["required"] = metadata.get("required", [])
            return schema

        # Case C: Dictionary mapping argument names to property schemas
        required = metadata.get("required")
        if required is None:
            required = [
                k for k, v in raw_params.items()
                if isinstance(v, dict) and v.get("required") is True
            ]
            if not required:
                required = list(raw_params.keys())

        return {
            "type": "object",
            "properties": raw_params,
            "required": required,
        }

    # Case D: Top-level "properties" in metadata
    if "properties" in metadata and isinstance(metadata["properties"], dict):
        return {
            "type": "object",
            "properties": metadata["properties"],
            "required": metadata.get("required", list(metadata["properties"].keys())),
        }

    return default_schema


def as_openai_tool(skill: Any, *, registry: Any = None) -> dict[str, Any]:
    """Convert a skill into an OpenAI tool definition dictionary.

    Args:
        skill: Skill instance, SkillDetail model, or dictionary.
        registry: Optional skill registry reference.

    Returns:
        Dictionary conforming to OpenAI tool definition format:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    name, description, _, metadata = extract_skill_info(skill)
    sanitized_name = sanitize_tool_name(name)
    if not description or description == f"Execute {name} skill.":
        description = f"Execute {sanitized_name} skill."
    parameters = build_parameters_schema(metadata)


    return {
        "type": "function",
        "function": {
            "name": sanitized_name,
            "description": description,
            "parameters": parameters,
        },
    }


def as_openai_tools(skills: list[Any], *, registry: Any = None) -> list[dict[str, Any]]:
    """Convert a collection of skills into a list of OpenAI tool definitions.

    Args:
        skills: List of skill instances, models, or dictionaries.
        registry: Optional skill registry reference.

    Returns:
        List of OpenAI tool definition dictionaries.
    """
    return [as_openai_tool(s, registry=registry) for s in skills]


class ToolExecutionResult(str):
    """String subclass representing an OpenAI tool execution result.

    Allows direct usage as a string while preserving tool call metadata
    and enabling easy conversion to OpenAI tool messages.
    """

    tool_call_id: str | None
    name: str | None

    def __new__(
        cls,
        content: str,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> "ToolExecutionResult":
        instance = super().__new__(cls, content)
        instance.tool_call_id = tool_call_id
        instance.name = name
        return instance

    def to_message(self) -> dict[str, Any]:
        """Convert result into standard OpenAI tool message format."""
        msg: dict[str, Any] = {"role": "tool", "content": str(self)}
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg

    def to_dict(self) -> dict[str, Any]:
        """Alias for to_message()."""
        return self.to_message()


class OpenAISkillExecutor:
    """Callable runner executing skill tool invocations received from OpenAI chat completions."""

    def __init__(
        self,
        skills: list[Any] | None = None,
        *,
        registry: Any = None,
    ) -> None:
        self.registry = registry
        self._skills: dict[str, Any] = {}
        if skills:
            for s in skills:
                self.register_skill(s)

    def register_skill(self, skill: Any) -> None:
        """Register a skill for tool call resolution."""
        name, _, _, _ = extract_skill_info(skill)
        sanitized = sanitize_tool_name(name)
        self._skills[sanitized] = skill
        self._skills[name] = skill
        if "/" in name:
            slug = name.split("/")[-1]
            self._skills[slug] = skill
            self._skills[sanitize_tool_name(slug)] = skill

    register = register_skill
    add_skill = register_skill

    def _resolve_skill(self, name: str) -> Any:
        if name in self._skills:
            return self._skills[name]
        sanitized = sanitize_tool_name(name)
        if sanitized in self._skills:
            return self._skills[sanitized]

        # Try resolving through bound registry
        if self.registry is not None:
            try:
                skill = self.registry.get_skill(name)
                if skill is not None:
                    self.register_skill(skill)
                    return skill
            except Exception as e:
                logger.debug(f"Registry lookup failed for '{name}': {e}")

        raise KeyError(f"Skill '{name}' not found in registered executor skills.")

    def execute(
        self,
        tool_call_or_name: Any,
        arguments: Any = None,
        *,
        as_message: bool = False,
        **kwargs: Any,
    ) -> ToolExecutionResult | dict[str, Any]:
        """Execute a tool call and return the response."""
        tool_call_id: str | None = None
        func_name: str = ""
        args: dict[str, Any] = {}

        if isinstance(tool_call_or_name, dict) and "function" in tool_call_or_name:
            tool_call_id = tool_call_or_name.get("id")
            fn_dict = tool_call_or_name["function"]
            func_name = fn_dict.get("name", "")
            raw_args = fn_dict.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                    args = parsed if isinstance(parsed, dict) else {"input": parsed}
                except Exception:
                    args = {"input": raw_args}
            elif isinstance(raw_args, dict):
                args = raw_args
        elif hasattr(tool_call_or_name, "function"):
            tool_call_id = getattr(tool_call_or_name, "id", None)
            fn_obj = tool_call_or_name.function
            func_name = getattr(fn_obj, "name", "")
            raw_args = getattr(fn_obj, "arguments", {})
            if isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                    args = parsed if isinstance(parsed, dict) else {"input": parsed}
                except Exception:
                    args = {"input": raw_args}
            elif isinstance(raw_args, dict):
                args = raw_args
        elif isinstance(tool_call_or_name, str):
            func_name = tool_call_or_name
            if isinstance(arguments, dict):
                args = {**arguments, **kwargs}
            elif isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                    args = parsed if isinstance(parsed, dict) else {"input": parsed}
                    args.update(kwargs)
                except Exception:
                    args = {"input": arguments, **kwargs}
            else:
                args = dict(kwargs)
        else:
            raise ValueError(f"Unsupported tool call format: {type(tool_call_or_name)}")

        skill = self._resolve_skill(func_name)
        raw_result = execute_skill(skill, **args)
        content = str(raw_result)

        result = ToolExecutionResult(content, tool_call_id=tool_call_id, name=func_name)
        if as_message:
            return result.to_message()
        return result

    def __call__(
        self,
        tool_call_or_name: Any,
        arguments: Any = None,
        *,
        as_message: bool = False,
        **kwargs: Any,
    ) -> Any:
        return self.execute(tool_call_or_name, arguments, as_message=as_message, **kwargs)

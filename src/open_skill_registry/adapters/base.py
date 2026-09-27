"""Base utilities and execution helpers for framework adapters."""

import logging
import string
from typing import Any

logger = logging.getLogger(__name__)


def extract_skill_info(skill: Any) -> tuple[str, str, str, dict[str, Any]]:
    """Extract (name, description, instructions, metadata) from any skill representation.

    Supports Skill dataclass instances, SkillDetail/SkillSummary Pydantic models,
    dictionaries, and duck-typed objects.
    """
    if isinstance(skill, dict):
        name = skill.get("name") or skill.get("slug") or "skill"
        raw_desc = skill.get("description")
        description = raw_desc if raw_desc else f"Execute {name} skill."
        instructions = skill.get("instructions") or ""
        metadata = skill.get("metadata") or {}
    else:
        name = getattr(skill, "name", None) or getattr(skill, "slug", None) or "skill"
        raw_desc = getattr(skill, "description", None)
        description = raw_desc if raw_desc else f"Execute {name} skill."
        instructions = getattr(skill, "instructions", "") or ""
        raw_meta = getattr(skill, "metadata", None)
        if raw_meta is not None:
            if hasattr(raw_meta, "model_dump"):
                dumped = raw_meta.model_dump()
                meta_field = dumped.get("metadata")
                metadata = meta_field if isinstance(meta_field, dict) else dumped
            elif hasattr(raw_meta, "dict"):
                dumped = raw_meta.dict()
                meta_field = dumped.get("metadata")
                metadata = meta_field if isinstance(meta_field, dict) else dumped
            elif isinstance(raw_meta, dict):
                meta_field = raw_meta.get("metadata")
                metadata = meta_field if isinstance(meta_field, dict) else raw_meta
            else:
                metadata = {}
        else:
            metadata = {}


    return str(name), str(description), str(instructions), metadata



def execute_skill(skill: Any, *args: Any, **kwargs: Any) -> Any:
    """Execute a skill using positional and keyword arguments.

    Invocation order:
    1. If skill has callable `execute`, invoke it.
    2. Else if skill has callable `_execute`, invoke it.
    3. Else if skill has callable `func`, invoke it.
    4. Else if skill is dict with callable `func` or `execute`, invoke it.
    5. Else if skill has instructions:
       - If instructions has format fields ({param}), substitute provided kwargs.
       - If no format fields but kwargs/input passed, append context to instructions.
       - Return formatted instructions.
    6. Fallback: return execution confirmation with skill name and description.
    """
    # Normalize args into kwargs for template formatters or fallback kwargs
    forward_kwargs = dict(kwargs)
    if args:
        if len(args) == 1 and isinstance(args[0], dict):
            forward_kwargs.update(args[0])
        elif len(args) == 1 and isinstance(args[0], str):
            forward_kwargs.setdefault("input", args[0])
        else:
            forward_kwargs.setdefault("args", list(args))

    # Check for direct callable runner on skill
    for method_name in ("execute", "_execute", "func"):
        method = getattr(skill, method_name, None)
        if callable(method):
            try:
                return method(*args, **kwargs)
            except TypeError:
                return method(**forward_kwargs)

    if isinstance(skill, dict):
        for key in ("func", "execute"):
            fn = skill.get(key)
            if callable(fn):
                try:
                    return fn(*args, **kwargs)
                except TypeError:
                    return fn(**forward_kwargs)

    kwargs = forward_kwargs

    name, description, instructions, _ = extract_skill_info(skill)

    if instructions:
        # Check if instructions contains template placeholders
        try:
            formatter = string.Formatter()
            fields = [fname for _, fname, _, _ in formatter.parse(instructions) if fname]
            if fields:
                class SafeDict(dict[str, Any]):
                    def __missing__(self, key: str) -> str:
                        return f"{{{key}}}"


                return instructions.format_map(SafeDict(**kwargs))
        except Exception as e:
            logger.debug(f"String format interpolation failed: {e}")

        # If no format placeholders were matched but arguments were provided:
        if kwargs:
            args_formatted = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{instructions}\n\n[Context: {args_formatted}]"

        return instructions

    if description:
        return f"Skill '{name}': {description}"
    return f"Executed skill '{name}' successfully."

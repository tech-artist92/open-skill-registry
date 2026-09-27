"""End-to-End Integration Tests for Google ADK, LangChain, OpenAI & CrewAI (T074-T076).

Validates full-lifecycle integration with:
1. Google ADK 2.9.2+ (OpenSkillRegistry, Frontmatter, Skill, resource fetching, Simulated SkillToolset)
2. OpenAI Function Calling (as_openai_tool, as_openai_tools, OpenAISkillExecutor, tool call message format)
3. LangChain (as_langchain_tool, as_langchain_tools, LangChainSkillTool, run, arun, args_schema)
4. CrewAI (as_crewai_tool, as_crewai_tools, CrewAISkillTool, _run, run)
5. Cross-Framework Interoperability & Output Consistency
"""

import json
from pathlib import Path
from typing import Any

import pytest

from open_skill_registry import SkillRegistry
from open_skill_registry.adapters import (
    OpenAISkillExecutor,
    as_crewai_tool,
    as_crewai_tools,
    as_langchain_tool,
    as_langchain_tools,
    as_openai_tools,
)
from open_skill_registry.adk import OpenSkillRegistry, SkillNotFoundError
from open_skill_registry.models.skill import SkillDetail


@pytest.fixture
def calculator_skill_dir(tmp_path: Path) -> Path:
    """Create a realistic skill directory with instructions, metadata, and scripts."""
    skill_dir = tmp_path / "calculator_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Main SKILL.md with template placeholders
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        """---
name: math-calculator
slug: math-calculator
version: 1.2.0
description: High-precision calculation skill supporting arithmetic operations.
metadata:
  parameters:
    type: object
    properties:
      operation:
        type: string
        description: The arithmetic operation (add, subtract, multiply, divide).
      a:
        type: number
        description: The first operand.
      b:
        type: number
        description: The second operand.
    required:
      - operation
      - a
      - b
---
Execute operation {operation} on operands a={a} and b={b}.
Computed result of {operation}({a}, {b}) is evaluated successfully.
""",
        encoding="utf-8",
    )

    # 2. Companion script resource
    script_file = scripts_dir / "calculate.py"
    script_file.write_text(
        """def calculate(op, a, b):
    ops = {'add': lambda x, y: x + y, 'multiply': lambda x, y: x * y}
    return ops.get(op, lambda x, y: 0)(a, b)
""",
        encoding="utf-8",
    )

    # 3. Companion reference guide
    guide_file = skill_dir / "guide.md"
    guide_file.write_text("# Math Calculator Guide\nUse operation parameter.", encoding="utf-8")

    return skill_dir


@pytest.fixture
async def embedded_registry(tmp_path: Path, calculator_skill_dir: Path) -> SkillRegistry:
    """Initialize an embedded SkillRegistry and publish the calculator skill."""
    db_file = tmp_path / "framework_tests.db"
    config_file = tmp_path / "osr.config.yaml"
    config_file.write_text(
        f"""
version: "1.0"
mode: "embedded"
database:
  driver: "sqlite"
  url: "sqlite+aiosqlite:///{db_file}"
storage:
  driver: "sqlite"
search:
  semantic_enabled: true
  provider: "none"
""",
        encoding="utf-8",
    )

    registry = SkillRegistry.from_config(str(config_file))
    await registry.initialize()

    # Publish skill files directly
    files = {
        "SKILL.md": (calculator_skill_dir / "SKILL.md").read_bytes(),
        "scripts/calculate.py": (calculator_skill_dir / "scripts/calculate.py").read_bytes(),
        "guide.md": (calculator_skill_dir / "guide.md").read_bytes(),
    }
    await registry.publish(
        namespace="public",
        slug="math-calculator",
        version="1.2.0",
        files=files,
    )
    yield registry
    storage = getattr(getattr(registry, "_async_registry", None), "storage", None)
    if storage and hasattr(storage, "engine"):
        await storage.engine.dispose()


# ==============================================================================
# 1. Google ADK Integration Tests
# ==============================================================================


class TestGoogleADKIntegration:
    @pytest.mark.asyncio
    async def test_adk_search_get_and_resource_lifecycle(self, embedded_registry: SkillRegistry):
        """Verify ADK discovery, skill loading, and companion resource retrieval."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)

        # 1. Search skills
        frontmatters = await adk_registry.search_skills(query="calculator")
        assert len(frontmatters) >= 1
        found_names = [fm.name for fm in frontmatters]
        assert any("math-calculator" in name for name in found_names)

        # 2. Get skill definition
        skill = await adk_registry.get_skill(name="public/math-calculator")
        assert skill.name == "public/math-calculator"
        assert "arithmetic operations" in skill.description
        assert "Execute operation {operation}" in skill.instructions

        # 3. Retrieve companion resources through ADK Skill instance
        py_resource = await skill.get_resource("scripts/calculate.py")
        assert b"def calculate(op, a, b):" in py_resource

        md_resource = await skill.get_resource("guide.md")
        assert b"# Math Calculator Guide" in md_resource

    @pytest.mark.asyncio
    async def test_adk_simulated_skill_toolset_execution(self, embedded_registry: SkillRegistry):
        """Simulate the execution loop of Google ADK's SkillToolset."""

        class SimulatedSkillToolset:
            def __init__(self, registry: OpenSkillRegistry):
                self.registry = registry

            async def resolve_agent_tools(self, intent: str) -> list[Any]:
                matching_fms = await self.registry.search_skills(query=intent)
                tools = []
                for fm in matching_fms:
                    s = await self.registry.get_skill(name=fm.name)
                    tools.append(s)
                return tools

        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        toolset = SimulatedSkillToolset(adk_registry)

        tools = await toolset.resolve_agent_tools("math")
        assert len(tools) >= 1
        assert tools[0].name == "public/math-calculator"

    @pytest.mark.asyncio
    async def test_adk_missing_resource_raises_skill_not_found(
        self, embedded_registry: SkillRegistry
    ):
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")
        with pytest.raises(SkillNotFoundError):
            await skill.get_resource("nonexistent_script.py")


# ==============================================================================
# 2. OpenAI Function Calling Integration Tests
# ==============================================================================


class TestOpenAIIntegration:
    @pytest.mark.asyncio
    async def test_openai_tool_schema_and_execution(self, embedded_registry: SkillRegistry):
        """Test conversion to OpenAI tool format and execution via OpenAISkillExecutor."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        # 1. Convert to OpenAI tool calling schema
        tool_def = skill.as_openai_tool()
        assert tool_def["type"] == "function"
        fn = tool_def["function"]
        assert fn["name"] == "public_math_calculator"
        assert "arithmetic operations" in fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "operation" in fn["parameters"]["properties"]
        assert "a" in fn["parameters"]["properties"]
        assert "b" in fn["parameters"]["properties"]
        assert set(fn["parameters"]["required"]) == {"operation", "a", "b"}

        # 2. Execute OpenAI tool call (simulating LLM ChatCompletion response)
        executor = OpenAISkillExecutor(skills=[skill])
        simulated_tool_call = {
            "id": "call_calc_987",
            "type": "function",
            "function": {
                "name": "public_math_calculator",
                "arguments": json.dumps({"operation": "multiply", "a": 12, "b": 5}),
            },
        }

        # Execute as plain result string
        result_str = executor.execute(simulated_tool_call)
        assert "operation multiply" in result_str
        assert "a=12" in result_str
        assert "b=5" in result_str

        # Execute as OpenAI tool message dictionary
        tool_message = executor.execute(simulated_tool_call, as_message=True)
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_calc_987"
        assert "multiply" in tool_message["content"]

    @pytest.mark.asyncio
    async def test_openai_batch_tools(self, embedded_registry: SkillRegistry):
        """Test batch conversion using as_openai_tools."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        tools = as_openai_tools([skill])
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "public_math_calculator"


# ==============================================================================
# 3. LangChain Integration Tests
# ==============================================================================


class TestLangChainIntegration:
    @pytest.mark.asyncio
    async def test_langchain_tool_interface_and_execution(self, embedded_registry: SkillRegistry):
        """Test LangChain BaseTool contract compliance, run, and arun methods."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        # 1. Convert to LangChain tool
        tool = skill.as_langchain_tool()
        assert tool.name == "public_math_calculator"
        assert "arithmetic operations" in tool.description
        assert hasattr(tool, "args_schema")
        assert tool.args_schema is not None

        # Validate args_schema fields
        schema_props = tool.args_schema.model_json_schema().get("properties", {})
        assert "operation" in schema_props
        assert "a" in schema_props
        assert "b" in schema_props

        # 2. Synchronous run with dictionary input
        sync_result = tool.run({"operation": "add", "a": 100, "b": 25})
        assert "operation add" in sync_result
        assert "a=100" in sync_result
        assert "b=25" in sync_result

        # 3. Asynchronous arun execution
        async_result = await tool.arun({"operation": "divide", "a": 50, "b": 2})
        assert "operation divide" in async_result
        assert "a=50" in async_result
        assert "b=2" in async_result

        # 4. Direct callable invocation
        call_result = tool(operation="subtract", a=30, b=10)
        assert "operation subtract" in call_result

    @pytest.mark.asyncio
    async def test_langchain_batch_tools(self, embedded_registry: SkillRegistry):
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        tools = as_langchain_tools([skill])
        assert len(tools) == 1
        assert tools[0].name == "public_math_calculator"


# ==============================================================================
# 4. CrewAI Integration Tests
# ==============================================================================


class TestCrewAIIntegration:
    @pytest.mark.asyncio
    async def test_crewai_tool_interface_and_execution(self, embedded_registry: SkillRegistry):
        """Test CrewAI BaseTool contract compliance, _run, and run methods."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        # 1. Convert to CrewAI tool
        tool = skill.as_crewai_tool()
        assert tool.name == "public_math_calculator"
        assert "arithmetic operations" in tool.description
        assert hasattr(tool, "args_schema")

        # 2. CrewAI _run execution (used by CrewAI Agents)
        run_internal_result = tool._run(operation="multiply", a=8, b=7)
        assert "operation multiply" in run_internal_result
        assert "a=8" in run_internal_result
        assert "b=7" in run_internal_result

        # 3. CrewAI run execution
        run_result = tool.run(operation="multiply", a=8, b=7)
        assert run_result == run_internal_result

        # 4. Direct callable invocation
        call_result = tool(operation="add", a=15, b=5)
        assert "operation add" in call_result

    @pytest.mark.asyncio
    async def test_crewai_batch_tools(self, embedded_registry: SkillRegistry):
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        tools = as_crewai_tools([skill])
        assert len(tools) == 1
        assert tools[0].name == "public_math_calculator"


# ==============================================================================
# 5. Cross-Framework Consistency & Interoperability
# ==============================================================================


class TestCrossFrameworkInteroperability:
    @pytest.mark.asyncio
    async def test_single_skill_multi_framework_consistent_output(
        self, embedded_registry: SkillRegistry
    ):
        """Verify that a skill produces identical output across all four frameworks."""
        adk_registry = OpenSkillRegistry(registry=embedded_registry)
        skill = await adk_registry.get_skill(name="public/math-calculator")

        inputs = {"operation": "multiply", "a": 9, "b": 9}

        # 1. OpenAI execution
        openai_executor = OpenAISkillExecutor(skills=[skill])
        openai_result = openai_executor.execute(
            {"function": {"name": "public_math_calculator", "arguments": json.dumps(inputs)}}
        )

        # 2. LangChain execution
        langchain_tool = as_langchain_tool(skill)
        langchain_result = langchain_tool.run(inputs)

        # 3. CrewAI execution
        crewai_tool = as_crewai_tool(skill)
        crewai_result = crewai_tool.run(**inputs)

        # All framework outputs must be bit-for-bit identical
        assert openai_result == langchain_result == crewai_result
        assert "operation multiply" in openai_result
        assert "a=9" in openai_result
        assert "b=9" in openai_result

    @pytest.mark.asyncio
    async def test_skill_detail_model_conversion_across_frameworks(self):
        """Verify that SkillDetail Pydantic models from hosted server convert cleanly."""
        detail = SkillDetail(
            namespace="public",
            slug="data-summarizer",
            name="Data Summarizer",
            description="Summarize tabular datasets",
            latest_version="1.0.0",
            instructions="Summarize input dataset: {dataset} with format={format}",
            metadata={
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset": {"type": "string", "description": "Raw data or URI"},
                        "format": {"type": "string", "default": "markdown"},
                    },
                    "required": ["dataset"],
                }
            },
        )

        # Convert to OpenAI
        oa_tool = detail.as_openai_tool()
        assert oa_tool["function"]["name"] == "public_data_summarizer"
        assert "dataset" in oa_tool["function"]["parameters"]["properties"]

        # Convert to LangChain
        lc_tool = detail.as_langchain_tool()
        lc_res = lc_tool.run({"dataset": "sales_2026.csv", "format": "json"})
        assert "sales_2026.csv" in lc_res

        # Convert to CrewAI
        cr_tool = detail.as_crewai_tool()
        cr_res = cr_tool.run(dataset="sales_2026.csv", format="json")
        assert cr_res == lc_res

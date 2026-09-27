"""Unit tests for Universal Python Framework Bridges (Phase 16 - T074).

Tests cover:
- OpenAI tool adapter (as_openai_tool, as_openai_tools, OpenAISkillExecutor,
  sanitize_tool_name, build_parameters_schema)
- LangChain tool adapter (as_langchain_tool, as_langchain_tools, LangChainSkillTool)

- CrewAI tool adapter (as_crewai_tool, as_crewai_tools, CrewAISkillTool)
- Convenience methods on Skill and SkillDetail
- Zero external dependencies behavior and edge cases
"""

import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from open_skill_registry.adapters.crewai import (
    CrewAISkillTool,
    as_crewai_tool,
    as_crewai_tools,
)
from open_skill_registry.adapters.langchain import (
    LangChainSkillTool,
    as_langchain_tool,
    as_langchain_tools,
)
from open_skill_registry.adapters.openai import (
    OpenAISkillExecutor,
    as_openai_tool,
    as_openai_tools,
    build_parameters_schema,
    sanitize_tool_name,
)
from open_skill_registry.adk import Skill
from open_skill_registry.models.skill import SkillDetail

# ============================================================================
# T074: OpenAI Tool Adapter Tests
# ============================================================================


class TestSanitizeToolName:
    """Tests for OpenAI tool name sanitization."""

    def test_sanitize_alphanumeric_and_underscores(self):
        assert sanitize_tool_name("weather_lookup") == "weather_lookup"
        assert sanitize_tool_name("weather-lookup") == "weather_lookup"
        assert sanitize_tool_name("getWeather123") == "getWeather123"

    def test_sanitize_slashes_and_namespaces(self):
        assert sanitize_tool_name("public/weather-lookup") == "public_weather_lookup"
        assert sanitize_tool_name("deepseek/math-solver/v2") == "deepseek_math_solver_v2"

    def test_sanitize_spaces_and_special_characters(self):
        assert sanitize_tool_name("Search Web & News!") == "Search_Web_News"
        assert sanitize_tool_name("hello.world:test") == "hello_world_test"
        assert sanitize_tool_name("   dirty   spaces   ") == "dirty_spaces"

    def test_sanitize_empty_and_special_only(self):
        assert sanitize_tool_name("") == "skill"
        assert sanitize_tool_name("----") == "skill"
        assert sanitize_tool_name("!@#$%^&*()") == "skill"
        assert sanitize_tool_name(None) == "skill"

    def test_sanitize_truncates_to_64_characters(self):
        long_name = "a" * 100
        sanitized = sanitize_tool_name(long_name)
        assert len(sanitized) == 64
        assert sanitized == "a" * 64


class TestBuildParametersSchema:
    """Tests for JSON schema parameter generation."""

    def test_default_parameters_when_none(self):
        schema = build_parameters_schema(None)
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "input" in schema["properties"]
        assert schema["properties"]["input"]["type"] == "string"
        assert "required" in schema
        assert "input" in schema["required"]

    def test_default_parameters_when_empty_dict(self):
        schema = build_parameters_schema({})
        assert schema["type"] == "object"
        assert "input" in schema["properties"]

    def test_explicit_json_schema_in_metadata(self):
        meta = {
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            }
        }
        schema = build_parameters_schema(meta)
        assert schema["type"] == "object"
        assert "location" in schema["properties"]
        assert schema["required"] == ["location"]

    def test_properties_mapping_in_parameters(self):
        meta = {
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }
        schema = build_parameters_schema(meta)
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_input_schema_key_fallback(self):
        meta = {
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                },
            }
        }
        schema = build_parameters_schema(meta)
        assert "code" in schema["properties"]


class TestAsOpenAITool:
    """Tests for as_openai_tool and as_openai_tools functions."""

    def test_as_openai_tool_with_skill_instance(self):
        skill = Skill(
            name="public/weather-lookup",
            description="Lookup weather forecasts.",
            instructions="Fetch weather for {location}.",
            metadata={"version": "1.0.0"},
        )
        tool = as_openai_tool(skill)
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] == "public_weather_lookup"
        assert fn["description"] == "Lookup weather forecasts."
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"

    def test_as_openai_tool_with_skill_detail(self):
        detail = SkillDetail(
            name="deepseek/math-solver",
            slug="math-solver",
            namespace="deepseek",
            description="Solve mathematical proofs.",
            latest_version="2.0.0",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        tool = as_openai_tool(detail)
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "deepseek_math_solver"
        assert tool["function"]["description"] == "Solve mathematical proofs."

    def test_as_openai_tool_with_dict(self):
        skill_dict = {
            "name": "code-review",
            "description": "Reviews pull requests.",
            "metadata": {
                "parameters": {
                    "pr_url": {"type": "string"},
                },
                "required": ["pr_url"],
            },
        }
        tool = as_openai_tool(skill_dict)
        assert tool["function"]["name"] == "code_review"
        assert "pr_url" in tool["function"]["parameters"]["properties"]
        assert tool["function"]["parameters"]["required"] == ["pr_url"]

    def test_as_openai_tool_missing_description_fallback(self):
        skill = Skill(name="silent-skill", description="")
        tool = as_openai_tool(skill)
        assert tool["function"]["description"] == "Execute silent_skill skill."

    def test_as_openai_tools_batch(self):
        skills = [
            Skill(name="skill-one", description="One"),
            Skill(name="skill-two", description="Two"),
        ]
        tools = as_openai_tools(skills)
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "skill_one"
        assert tools[1]["function"]["name"] == "skill_two"


class TestOpenAISkillExecutor:
    """Tests for OpenAISkillExecutor runner."""

    def test_execute_with_dict_tool_call(self):
        skill = Skill(
            name="weather-lookup",
            description="Weather tool",
            instructions="Forecast for {location} is sunny.",
        )
        executor = OpenAISkillExecutor([skill])

        tool_call = {
            "id": "call_12345",
            "type": "function",
            "function": {
                "name": "weather_lookup",
                "arguments": json.dumps({"location": "Paris"}),
            },
        }

        result = executor(tool_call)
        assert isinstance(result, str)
        assert "Forecast for Paris is sunny." in result
        assert result.tool_call_id == "call_12345"
        assert result.name == "weather_lookup"

        # Check message format
        msg = result.to_message()
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_12345"
        assert msg["content"] == "Forecast for Paris is sunny."

    def test_execute_with_as_message_flag(self):
        skill = Skill(
            name="echo-skill",
            description="Echo",
            instructions="Echo: {input}",
        )
        executor = OpenAISkillExecutor([skill])

        tool_call = {
            "id": "call_echo",
            "type": "function",
            "function": {
                "name": "echo_skill",
                "arguments": {"input": "test message"},
            },
        }

        msg = executor.execute(tool_call, as_message=True)
        assert isinstance(msg, dict)
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_echo"
        assert msg["content"] == "Echo: test message"

    def test_execute_by_name_and_kwargs(self):
        skill = Skill(
            name="calc",
            description="Calculator",
            instructions="Result of calc: {x} + {y}",
        )
        executor = OpenAISkillExecutor([skill])
        result = executor("calc", x=2, y=3)
        assert result == "Result of calc: 2 + 3"

    def test_execute_with_custom_callable(self):
        class CallableSkill:
            name = "custom-runner"
            description = "Custom runner"
            metadata = {}

            def execute(self, **kwargs):
                return f"Custom result: {kwargs.get('data')}"

        executor = OpenAISkillExecutor([CallableSkill()])
        result = executor("custom_runner", data="42")
        assert result == "Custom result: 42"

    def test_execute_skill_not_found(self):
        executor = OpenAISkillExecutor([])
        with pytest.raises(KeyError, match="not found"):
            executor("unknown_skill")

    def test_execute_with_duck_typed_tool_call_object(self):
        class FunctionCall:
            name = "weather_lookup"
            arguments = '{"location": "Tokyo"}'

        class ToolCallObj:
            id = "call_obj_777"
            type = "function"
            function = FunctionCall()

        skill = Skill(
            name="weather-lookup",
            description="Weather tool",
            instructions="Forecast for {location} is rainy.",
        )
        executor = OpenAISkillExecutor([skill])
        res = executor(ToolCallObj())
        assert res == "Forecast for Tokyo is rainy."
        assert res.tool_call_id == "call_obj_777"


# ============================================================================
# T075: LangChain Tool Adapter Tests
# ============================================================================


class TestLangChainAdapter:
    """Tests for LangChain tool adapter and LangChainSkillTool."""

    def test_as_langchain_tool_interface(self):
        skill = Skill(
            name="code-reviewer",
            description="Automated code review assistant.",
            instructions="Review code: {input}",
        )
        tool = as_langchain_tool(skill)

        assert isinstance(tool, LangChainSkillTool)
        assert tool.name == "code_reviewer"
        assert tool.description == "Automated code review assistant."
        assert tool.skill is skill
        assert issubclass(tool.args_schema, BaseModel)

    def test_langchain_tool_run_positional_string(self):
        skill = Skill(
            name="summarizer",
            description="Summarizes text.",
            instructions="Summary of {input}",
        )
        tool = as_langchain_tool(skill)
        output = tool.run("Long article contents here...")
        assert output == "Summary of Long article contents here..."

    def test_langchain_tool_run_dict_input(self):
        skill = Skill(
            name="city-weather",
            description="Weather lookup.",
            instructions="Weather in {city}: Sunny, 25C.",
        )
        tool = as_langchain_tool(skill)
        output = tool.run({"city": "Berlin"})
        assert output == "Weather in Berlin: Sunny, 25C."

    def test_langchain_tool_run_kwargs(self):
        skill = Skill(
            name="city-weather",
            description="Weather lookup.",
            instructions="Weather in {city}: Rainy, 15C.",
        )
        tool = as_langchain_tool(skill)
        output = tool.run(city="London")
        assert output == "Weather in London: Rainy, 15C."

    def test_langchain_tool_callable_invocation(self):
        skill = Skill(
            name="greeter",
            description="Friendly greeting.",
            instructions="Hello, {input}!",
        )
        tool = as_langchain_tool(skill)
        # Calling tool directly like a function
        output = tool("World")
        assert output == "Hello, World!"

    @pytest.mark.asyncio
    async def test_langchain_tool_async_arun(self):
        skill = Skill(
            name="async-evaluator",
            description="Evaluates expressions.",
            instructions="Evaluation result: {input}",
        )
        tool = as_langchain_tool(skill)
        output = await tool.arun("2 + 2")
        assert output == "Evaluation result: 2 + 2"

    def test_langchain_args_schema_generation(self):
        skill = Skill(
            name="db-query",
            description="Execute query",
            metadata={
                "parameters": {
                    "sql": {"type": "string", "description": "SQL statement"},
                    "limit": {"type": "integer", "description": "Max rows", "default": 10},
                },
                "required": ["sql"],
            },
        )
        tool = as_langchain_tool(skill)
        schema_cls = tool.args_schema
        assert schema_cls is not None
        schema_dict = schema_cls.model_json_schema()
        assert "sql" in schema_dict["properties"]
        assert "limit" in schema_dict["properties"]

    def test_as_langchain_tools_batch(self):
        skills = [
            Skill(name="s1", description="Skill 1"),
            Skill(name="s2", description="Skill 2"),
        ]
        tools = as_langchain_tools(skills)
        assert len(tools) == 2
        assert all(isinstance(t, LangChainSkillTool) for t in tools)
        assert tools[0].name == "s1"
        assert tools[1].name == "s2"


# ============================================================================
# T076: CrewAI Tool Adapter Tests
# ============================================================================


class TestCrewAIAdapter:
    """Tests for CrewAI tool adapter and CrewAISkillTool."""

    def test_as_crewai_tool_interface(self):
        skill = Skill(
            name="research-agent",
            description="Deep web research tool.",
            instructions="Research findings for {topic}",
        )
        tool = as_crewai_tool(skill)

        assert isinstance(tool, CrewAISkillTool)
        assert tool.name == "research_agent"
        assert tool.description == "Deep web research tool."
        assert hasattr(tool, "_run")
        assert hasattr(tool, "run")

    def test_crewai_tool_run_positional_and_kwargs(self):
        skill = Skill(
            name="sentiment-analyzer",
            description="Analyze tone of text.",
            instructions="Sentiment for '{input}': Positive",
        )
        tool = as_crewai_tool(skill)

        # CrewAI agents invoke _run or run
        res1 = tool._run("Great product!")
        assert res1 == "Sentiment for 'Great product!': Positive"

        res2 = tool.run("Terrible service!")
        assert res2 == "Sentiment for 'Terrible service!': Positive"

    def test_crewai_tool_run_custom_kwargs(self):
        skill = Skill(
            name="translator",
            description="Translates languages.",
            instructions="Translating '{text}' to {target_lang}: Hola",
        )
        tool = as_crewai_tool(skill)
        res = tool.run(text="Hello", target_lang="Spanish")
        assert res == "Translating 'Hello' to Spanish: Hola"

    def test_crewai_tool_callable(self):
        skill = Skill(
            name="ping",
            description="Ping tool",
            instructions="pong",
        )
        tool = as_crewai_tool(skill)
        assert tool() == "pong"

    def test_as_crewai_tools_batch(self):
        skills = [
            Skill(name="crew-1", description="Crew 1"),
            Skill(name="crew-2", description="Crew 2"),
        ]
        tools = as_crewai_tools(skills)
        assert len(tools) == 2
        assert all(isinstance(t, CrewAISkillTool) for t in tools)
        assert tools[0].name == "crew_1"
        assert tools[1].name == "crew_2"


# ============================================================================
# Skill Convenience Integration Tests
# ============================================================================


class TestSkillConvenienceMethods:
    """Tests for skill.as_openai_tool(), skill.as_langchain_tool(), skill.as_crewai_tool()."""

    def test_skill_convenience_methods(self):
        skill = Skill(
            name="market-analyst",
            description="Analyzes stock trends.",
            instructions="Market report for {ticker}",
        )

        openai_tool = skill.as_openai_tool()
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "market_analyst"

        langchain_tool = skill.as_langchain_tool()
        assert isinstance(langchain_tool, LangChainSkillTool)
        assert langchain_tool.name == "market_analyst"

        crewai_tool = skill.as_crewai_tool()
        assert isinstance(crewai_tool, CrewAISkillTool)
        assert crewai_tool.name == "market_analyst"

    def test_skill_detail_convenience_methods(self):
        detail = SkillDetail(
            name="crypto/tracker",
            slug="tracker",
            namespace="crypto",
            description="Track prices",
            latest_version="1.0.0",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        openai_tool = detail.as_openai_tool()
        assert openai_tool["function"]["name"] == "crypto_tracker"

        lc_tool = detail.as_langchain_tool()
        assert lc_tool.name == "crypto_tracker"

        crew_tool = detail.as_crewai_tool()
        assert crew_tool.name == "crypto_tracker"


# ============================================================================
# Edge Cases & Zero Dependency Tests
# ============================================================================


class TestEdgeCasesAndZeroDependencies:
    """Tests edge cases across all framework bridges."""

    def test_skill_as_plain_dict(self):
        d = {
            "name": "raw/dict-tool",
            "description": "Dict-based skill",
            "instructions": "Dict instructions: {value}",
        }
        openai_res = as_openai_tool(d)
        assert openai_res["function"]["name"] == "raw_dict_tool"

        lc_res = as_langchain_tool(d)
        assert lc_res.name == "raw_dict_tool"
        assert lc_res.run(value="123") == "Dict instructions: 123"

        crew_res = as_crewai_tool(d)
        assert crew_res.name == "raw_dict_tool"
        assert crew_res.run(value="456") == "Dict instructions: 456"

    def test_skill_with_empty_instructions(self):
        skill = Skill(name="noop", description="Does nothing", instructions="")
        lc_tool = as_langchain_tool(skill)
        assert "noop" in lc_tool.run()

    def test_skill_with_no_placeholders_and_kwargs(self):
        skill = Skill(
            name="static-info",
            description="Provides static guide",
            instructions="Static instructions here.",
        )
        tool = as_langchain_tool(skill)
        res = tool.run()
        assert res == "Static instructions here."

        res_with_arg = tool.run("extra context")
        assert "Static instructions here." in res_with_arg

    def test_top_level_package_exports(self):
        import open_skill_registry as osr

        assert hasattr(osr, "as_openai_tool")
        assert hasattr(osr, "as_openai_tools")
        assert hasattr(osr, "OpenAISkillExecutor")
        assert hasattr(osr, "as_langchain_tool")
        assert hasattr(osr, "as_langchain_tools")
        assert hasattr(osr, "LangChainSkillTool")
        assert hasattr(osr, "as_crewai_tool")
        assert hasattr(osr, "as_crewai_tools")
        assert hasattr(osr, "CrewAISkillTool")

    def test_skill_with_frontmatter_metadata_object(self):
        from open_skill_registry.models.skill import SkillFrontmatter

        fm = SkillFrontmatter(
            name="frontmatter-skill",
            description="Created from frontmatter model",
            metadata={"parameters": {"target": {"type": "string"}}},
        )
        skill = Skill(
            name=fm.name,
            description=fm.description,
            metadata=fm,
        )
        tool = as_openai_tool(skill)
        assert tool["function"]["name"] == "frontmatter_skill"
        assert "target" in tool["function"]["parameters"]["properties"]

    def test_openai_executor_registry_fallback_resolution(self):
        class MockRegistry:
            def get_skill(self, name):
                if name in ("remote_tool", "remote-tool"):
                    return Skill(
                        name="remote-tool",
                        description="Fetched from registry",
                        instructions="Remote instructions for {param}",
                    )
                return None

        executor = OpenAISkillExecutor(registry=MockRegistry())
        result = executor("remote_tool", param="resolved_value")
        assert result == "Remote instructions for resolved_value"

    def test_skill_with_func_callable(self):
        class FuncSkill:
            name = "func_skill"
            description = "Skill with func attribute"
            func = staticmethod(lambda **kw: f"Computed {kw.get('val')}")

        tool = as_crewai_tool(FuncSkill())
        assert tool.run(val=99) == "Computed 99"


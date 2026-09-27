"""Open Skill Registry Model Context Protocol (MCP) server package."""

from open_skill_registry.server.mcp.handler import MCPHandler, parse_skill_uri
from open_skill_registry.server.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RESOURCE_NOT_FOUND,
    SKILL_NOT_FOUND,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ResourceContent,
    ResourceDefinition,
    SkillGetResult,
    SkillSummaryItem,
    ToolCallResult,
    ToolContent,
    ToolDefinition,
)
from open_skill_registry.server.mcp.sse import router as sse_router
from open_skill_registry.server.mcp.stdio import run_stdio_server

__all__ = [
    "MCPHandler",
    "parse_skill_uri",
    "run_stdio_server",
    "sse_router",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    "ToolDefinition",
    "ToolCallResult",
    "ToolContent",
    "ResourceDefinition",
    "ResourceContent",
    "SkillSummaryItem",
    "SkillGetResult",
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "RESOURCE_NOT_FOUND",
    "SKILL_NOT_FOUND",
]

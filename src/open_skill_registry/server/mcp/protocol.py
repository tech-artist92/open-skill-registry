"""Protocol data models for JSON-RPC 2.0 and MCP / SEP-2640.

Zero external dependencies: uses standard Pydantic models.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Custom / Application Error Codes
RESOURCE_NOT_FOUND = -32002
SKILL_NOT_FOUND = -32004


class MCPError(Exception):
    """Exception raised by MCP operations that map to JSON-RPC errors."""

    def __init__(self, code: int, message: str, data: Any | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class MCPProtocolModel(BaseModel):
    """Base class for frozen MCP protocol models supporting dict-like lookup."""

    model_config = ConfigDict(frozen=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None


class JSONRPCError(MCPProtocolModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCRequest(MCPProtocolModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JSONRPCResponse(MCPProtocolModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JSONRPCError | None = None


class ToolContent(MCPProtocolModel):
    type: str = "text"
    text: str


class ToolCallResult(MCPProtocolModel):
    content: list[ToolContent] = Field(default_factory=list)
    isError: bool = False


class ToolDefinition(MCPProtocolModel):
    name: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class ResourceDefinition(MCPProtocolModel):
    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = None


class ResourceContent(MCPProtocolModel):
    uri: str
    mimeType: str | None = None
    text: str | None = None
    blob: str | None = None


class SkillSummaryItem(MCPProtocolModel):
    namespace: str
    slug: str
    name: str
    description: str | None = None
    version: str


class SkillGetResult(MCPProtocolModel):
    namespace: str
    slug: str
    name: str
    description: str | None = None
    version: str
    instructions: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

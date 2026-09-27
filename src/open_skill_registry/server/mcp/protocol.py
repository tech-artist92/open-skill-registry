"""Protocol data models for JSON-RPC 2.0 and MCP / SEP-2640.

Zero external dependencies: uses standard Pydantic models.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

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


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JSONRPCError | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class ToolContent(BaseModel):
    type: str = "text"
    text: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class ToolCallResult(BaseModel):
    content: list[ToolContent] = Field(default_factory=list)
    isError: bool = False

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class ResourceDefinition(BaseModel):
    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class ResourceContent(BaseModel):
    uri: str
    mimeType: str | None = None
    text: str | None = None
    blob: str | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class SkillSummaryItem(BaseModel):
    namespace: str
    slug: str
    name: str
    description: str | None = None
    version: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class SkillGetResult(BaseModel):
    namespace: str
    slug: str
    name: str
    description: str | None = None
    version: str
    instructions: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

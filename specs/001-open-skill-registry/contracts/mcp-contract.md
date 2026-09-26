# MCP Server Contract: Open Skill Registry (SEP-2640)

**Protocol**: Model Context Protocol (MCP)
**License**: Apache-2.0

> **Deployment Context**: This contract specifies the Model Context Protocol (MCP) server capabilities exposed by the Open Skill Registry to LLM agents (Claude, Cursor, etc.). It allows agents to dynamically discover and retrieve skills at runtime.

---

## 1. Transports

The registry supports both standard MCP transport mechanisms:

1. **Stdio Transport**: Provided via the CLI command `osr mcp`. Ideal for local agents (e.g. Cursor, Claude Desktop) to connect to a local or remote registry using standard input/output.
2. **SSE Transport (Networked)**: Provided via HTTP endpoints on the Hosted Server:
   - `GET /api/v1/mcp/sse` (Connection initialization & Event stream)
   - `POST /api/v1/mcp/messages` (Message posting)

---

## 2. Capability Extension

The registry implements a custom capability extension for skill retrieval:
`io.modelcontextprotocol/skills`

Clients should verify this capability is present in the server's `InitializeResult`.

---

## 3. Methods

### `skills/list`
Discovers and lists available skills in the registry.

**Request Parameters**:
- `query` (string, optional): Search query for semantic/text search.
- `namespace` (string, optional): Filter by namespace.
- `limit` (integer, optional): Max results.

**Response**: List of skill metadata objects (slug, description, version).

### `skills/get`
Retrieves the L2 instructions and metadata for a specific skill.

**Request Parameters**:
- `namespace` (string): The skill's namespace.
- `slug` (string): The skill's slug.
- `version` (string, optional): Specific version (defaults to latest).

**Response**: 
- `instructions` (string): Markdown content of the skill.
- `manifest` (object): List of files (L3 resources) available for the skill.

### `resources/read`
Standard MCP resource read method to fetch specific L3 asset files for a skill.

**URI Format**: `skill://{namespace}/{slug}/{version}/{file_path}`

**Response**: Content of the requested file (text or binary).

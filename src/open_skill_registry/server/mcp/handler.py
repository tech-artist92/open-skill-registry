"""MCP JSON-RPC 2.0 Handler.

Handles JSON-RPC 2.0 requests for:
- Core lifecycle: initialize, notifications/initialized, ping
- MCP standard tools: tools/list, tools/call
- SEP-2640 Skills: skills/list, skills/get
- Resources: resources/list, resources/read

Zero external dependencies: works with embedded SkillRegistry, AsyncSkillRegistry,
BaseStorage, or remote SkillRegistryClient / AsyncSkillRegistryClient.
"""

import base64
import inspect
import json
import logging
import re
from typing import Any

from open_skill_registry.config import RegistryConfig
from open_skill_registry.registry.core.manifest import detect_content_type
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
    MCPError,
    ResourceContent,
    ResourceDefinition,
    SkillGetResult,
    SkillSummaryItem,
    ToolCallResult,
    ToolContent,
    ToolDefinition,
)

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"^(v?\d+(\.\d+)*.*|latest)$", re.IGNORECASE)


def parse_skill_uri(uri: str) -> tuple[str, str, str | None, str]:
    """Parse skill:// URI into (namespace, slug, version, file_path).

    Supported formats:
    - skill://<namespace>/<slug>/<version>/<file_path>
    - skill://<namespace>/<slug>/<file_path> (defaults version to None/latest)
    """
    prefix = "skill://"
    if not uri.startswith(prefix):
        raise ValueError(f"Invalid URI scheme, must start with '{prefix}': {uri}")
    path_part = uri[len(prefix) :].strip("/")
    parts = path_part.split("/")
    if len(parts) < 3:
        raise ValueError(f"URI missing required components: {uri}")

    namespace = parts[0]
    slug = parts[1]

    if len(parts) == 3:
        return namespace, slug, None, parts[2]

    part2 = parts[2]
    # Check if part2 is version or a file path segment
    if VERSION_REGEX.match(part2):
        version = part2
        file_path = "/".join(parts[3:])
        return namespace, slug, version, file_path
    else:
        version = None
        file_path = "/".join(parts[2:])
        return namespace, slug, version, file_path


class MCPHandler:
    """Async MCP request dispatcher."""

    def __init__(
        self,
        registry: Any = None,
        storage: Any = None,
        config: RegistryConfig | None = None,
    ):
        self.registry = registry
        self.storage = storage
        self.config = config

        # If neither provided, lazily init embedded registry
        if self.registry is None and self.storage is None:
            from open_skill_registry.registry.main import AsyncSkillRegistry

            self.registry = AsyncSkillRegistry(config=config)

    # -------------------------------------------------------------------------
    # Core Entry Points
    # -------------------------------------------------------------------------

    async def handle_raw(self, raw_message: str) -> JSONRPCResponse | None:
        """Parse raw line/string and handle request."""
        try:
            parsed = json.loads(raw_message)
        except Exception as e:
            return JSONRPCResponse(
                id=None,
                error=JSONRPCError(
                    code=PARSE_ERROR,
                    message=f"Parse error: {str(e)}",
                ),
            )

        if not isinstance(parsed, dict) or "method" not in parsed:
            req_id = parsed.get("id") if isinstance(parsed, dict) else None
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=INVALID_REQUEST,
                    message="Invalid request structure: missing 'method' or not an object",
                ),
            )

        return await self.handle_request(parsed)

    async def handle_request(
        self, request: dict[str, Any] | JSONRPCRequest
    ) -> JSONRPCResponse | None:
        """Dispatch JSON-RPC request to appropriate handler method."""
        req_dict = request.model_dump() if isinstance(request, JSONRPCRequest) else request

        req_id = req_dict.get("id")
        method = req_dict.get("method")
        params = req_dict.get("params") or {}

        if not method or not isinstance(method, str):
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=INVALID_REQUEST,
                    message="Invalid request: method must be a non-empty string",
                ),
            )

        # Dispatch method
        try:
            if method == "initialize":
                res = await self._handle_initialize(params)
                return JSONRPCResponse(id=req_id, result=res)

            elif method == "notifications/initialized":
                if req_id is None:
                    # Standard notification: silent, return None
                    return None
                return JSONRPCResponse(id=req_id, result={})

            elif method == "ping":
                return JSONRPCResponse(id=req_id, result={})

            elif method == "tools/list":
                res = await self._handle_tools_list(params)
                return JSONRPCResponse(id=req_id, result=res)

            elif method == "tools/call":
                res = await self._handle_tools_call(params)
                return JSONRPCResponse(id=req_id, result=res.model_dump())

            elif method == "skills/list":
                res = await self._handle_skills_list(params)
                return JSONRPCResponse(id=req_id, result=res)

            elif method == "skills/get":
                res = await self._handle_skills_get(params)
                return JSONRPCResponse(id=req_id, result=res)

            elif method == "resources/list":
                res = await self._handle_resources_list(params)
                return JSONRPCResponse(id=req_id, result=res)

            elif method == "resources/read":
                res = await self._handle_resources_read(params)
                return JSONRPCResponse(id=req_id, result=res)

            else:
                return JSONRPCResponse(
                    id=req_id,
                    error=JSONRPCError(
                        code=METHOD_NOT_FOUND,
                        message=f"Method not found: {method}",
                    ),
                )

        except MCPError as rpc_err:
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=rpc_err.code,
                    message=rpc_err.message,
                    data=rpc_err.data,
                ),
            )
        except ValueError as val_err:
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=INVALID_PARAMS,
                    message=str(val_err),
                ),
            )
        except Exception as exc:
            logger.exception("Internal error processing MCP method %s", method)
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=INTERNAL_ERROR,
                    message=f"Internal error: {str(exc)}",
                ),
            )

    # -------------------------------------------------------------------------
    # Lifecycle Handlers
    # -------------------------------------------------------------------------

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "skills": {},
                "experimental": {
                    "io.modelcontextprotocol/skills": {},
                },
            },
            "serverInfo": {
                "name": "open-skill-registry",
                "version": "0.1.0",
            },
        }

    # -------------------------------------------------------------------------
    # Tools Handlers
    # -------------------------------------------------------------------------

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        tools: list[ToolDefinition] = [
            ToolDefinition(
                name="search_skills",
                description="Search skills in the registry by semantic or text query.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text or keywords",
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Optional namespace filter",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="get_skill",
                description="Retrieve detailed instructions and metadata for a skill.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Namespace of the skill",
                        },
                        "slug": {
                            "type": "string",
                            "description": "Slug of the skill",
                        },
                        "version": {
                            "type": "string",
                            "description": (
                                "Specific version of the skill (optional, defaults to latest)"
                            ),
                        },
                    },
                    "required": ["namespace", "slug"],
                },
            ),
            ToolDefinition(
                name="list_skills",
                description="List available skills in the registry.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Optional namespace filter",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number (defaults to 1)",
                            "default": 1,
                        },
                        "size": {
                            "type": "integer",
                            "description": "Number of skills per page (defaults to 20)",
                            "default": 20,
                        },
                    },
                },
            ),
            ToolDefinition(
                name="read_skill_resource",
                description="Read a resource or asset file from a skill package.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "uri": {
                            "type": "string",
                            "description": (
                                "Resource URI in format "
                                "skill://<namespace>/<slug>/<version>/<path> "
                                "or skill://<namespace>/<slug>/<path>"
                            ),
                        },
                    },
                    "required": ["uri"],
                },
            ),
        ]
        return {"tools": [t.model_dump() for t in tools]}

    async def _handle_tools_call(self, params: dict[str, Any]) -> ToolCallResult:
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if tool_name == "search_skills":
            query = arguments.get("query", "")
            namespace = arguments.get("namespace")
            limit = int(arguments.get("limit", 10))

            results = await self._search_skills_internal(query, limit, namespace)
            if not results:
                return ToolCallResult(
                    content=[ToolContent(text="No skills found matching query.")],
                    isError=False,
                )

            lines = []
            for s in results:
                slug = s.get("slug", "")
                ns = s.get("namespace", "")
                name = s.get("name", slug)
                desc = s.get("description", "")
                ver = s.get("version", "1.0.0")
                lines.append(f"- **{name}** (`{ns}/{slug}` v{ver}): {desc}")
            return ToolCallResult(
                content=[ToolContent(text="\n".join(lines))],
                isError=False,
            )

        elif tool_name == "get_skill":
            namespace = arguments.get("namespace")
            slug = arguments.get("slug")
            version = arguments.get("version")

            if not namespace or not slug:
                return ToolCallResult(
                    content=[
                        ToolContent(text="Missing required arguments: 'namespace' and 'slug'")
                    ],
                    isError=True,
                )

            try:
                skill_data = await self._get_skill_internal(namespace, slug, version)
                text = (
                    f"# {skill_data['name']} (v{skill_data['version']})\n"
                    f"Namespace: {skill_data['namespace']}\n"
                    f"Slug: {skill_data['slug']}\n"
                    f"Description: {skill_data.get('description', '')}\n\n"
                    f"## Instructions\n{skill_data.get('instructions', '')}"
                )
                return ToolCallResult(
                    content=[ToolContent(text=text)],
                    isError=False,
                )
            except Exception as e:
                return ToolCallResult(
                    content=[ToolContent(text=f"Skill not found: {str(e)}")],
                    isError=True,
                )

        elif tool_name == "list_skills":
            namespace = arguments.get("namespace")
            page = int(arguments.get("page", 1))
            size = int(arguments.get("size", 20))

            skills = await self._list_skills_internal(namespace=namespace, page=page, size=size)
            if not skills:
                return ToolCallResult(
                    content=[ToolContent(text="No skills found.")],
                    isError=False,
                )
            lines = []
            for s in skills:
                name = s.get("name", s.get("slug"))
                ns = s.get("namespace")
                sl = s.get("slug")
                ver = s.get("version")
                desc = s.get("description", "")
                lines.append(f"- **{name}** (`{ns}/{sl}` v{ver}): {desc}")
            return ToolCallResult(
                content=[ToolContent(text="\n".join(lines))],
                isError=False,
            )

        elif tool_name == "read_skill_resource":
            uri = arguments.get("uri")
            if not uri:
                return ToolCallResult(
                    content=[ToolContent(text="Missing required argument 'uri'")],
                    isError=True,
                )
            try:
                content = await self._read_resource_internal(uri)
                return ToolCallResult(
                    content=[ToolContent(text=content.text or content.blob or "")],
                    isError=False,
                )
            except Exception as e:
                return ToolCallResult(
                    content=[ToolContent(text=f"Failed to read resource: {str(e)}")],
                    isError=True,
                )

        else:
            return ToolCallResult(
                content=[ToolContent(text=f"Unknown tool: {tool_name}")],
                isError=True,
            )

    # -------------------------------------------------------------------------
    # SEP-2640 Skills Handlers
    # -------------------------------------------------------------------------

    async def _handle_skills_list(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query")
        namespace = params.get("namespace")
        limit = int(params.get("limit", 20))

        if query:
            items = await self._search_skills_internal(query, limit, namespace)
        else:
            items = await self._list_skills_internal(namespace=namespace, page=1, size=limit)

        formatted = []
        for item in items:
            formatted.append(
                SkillSummaryItem(
                    namespace=item["namespace"],
                    slug=item["slug"],
                    name=item["name"],
                    description=item.get("description"),
                    version=item.get("version", "1.0.0"),
                ).model_dump()
            )
        return {"skills": formatted}

    async def _handle_skills_get(self, params: dict[str, Any]) -> dict[str, Any]:
        namespace = params.get("namespace")
        slug = params.get("slug")
        version = params.get("version")

        if not namespace or not slug:
            raise MCPError(
                code=INVALID_PARAMS,
                message="Missing required parameters 'namespace' and 'slug'",
            )

        try:
            data = await self._get_skill_internal(namespace, slug, version)
            return SkillGetResult(
                namespace=data["namespace"],
                slug=data["slug"],
                name=data["name"],
                description=data.get("description"),
                version=data["version"],
                instructions=data.get("instructions", ""),
                manifest=data.get("manifest", {}),
                metadata=data.get("metadata", {}),
            ).model_dump()
        except Exception as e:
            raise MCPError(
                code=SKILL_NOT_FOUND,
                message=f"Skill not found: {str(e)}",
            ) from e

    # -------------------------------------------------------------------------
    # Resources Handlers
    # -------------------------------------------------------------------------

    async def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        namespace = params.get("namespace")
        slug = params.get("slug")
        version = params.get("version")

        resources: list[ResourceDefinition] = []

        if namespace and slug:
            skills = [{"namespace": namespace, "slug": slug}]
        else:
            skills = await self._list_skills_internal(namespace=namespace, page=1, size=50)

        storage = self._get_active_storage()

        for s in skills:
            ns = s["namespace"]
            sl = s["slug"]
            try:
                skill_data = await self._get_skill_internal(ns, sl, version)
                manifest = skill_data.get("manifest", {})
                files = manifest.get("files", []) if isinstance(manifest, dict) else []
                v = skill_data.get("version", "1.0.0")

                found_files = []
                for f in files:
                    if isinstance(f, dict):
                        p = f.get("path") or f.get("name")
                    elif hasattr(f, "path"):
                        p = f.path
                    else:
                        p = str(f)
                    if p:
                        found_files.append(p)

                # Fallback to get_skill_resources if manifest has no file entries
                if not found_files and storage:
                    ver_obj = await storage.get_skill_version(ns, sl, v)
                    if ver_obj:
                        res_dict = await storage.get_skill_resources(ver_obj.id)
                        found_files.extend(res_dict.keys())

                for path in found_files:
                    uri = f"skill://{ns}/{sl}/{v}/{path}"
                    resources.append(
                        ResourceDefinition(
                            uri=uri,
                            name=path,
                            description=f"Resource {path} for skill {ns}/{sl}",
                            mimeType=detect_content_type(path),
                        )
                    )
            except Exception:
                continue

        return {"resources": [r.model_dump() for r in resources]}

    async def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not uri:
            raise MCPError(
                code=INVALID_PARAMS,
                message="Missing required parameter 'uri'",
            )

        try:
            content = await self._read_resource_internal(uri)
            return {"contents": [content.model_dump()]}
        except Exception as e:
            raise MCPError(
                code=RESOURCE_NOT_FOUND,
                message=f"Resource not found: {str(e)}",
            ) from e

    # -------------------------------------------------------------------------
    # Internal Storage / Client Abstraction Helpers
    # -------------------------------------------------------------------------

    def _get_active_storage(self) -> Any:
        if self.storage:
            return self.storage
        if self.registry:
            if hasattr(self.registry, "storage"):
                return self.registry.storage
            if hasattr(self.registry, "_async_registry") and hasattr(
                self.registry._async_registry, "storage"
            ):
                return self.registry._async_registry.storage
        return None

    async def _list_skills_internal(
        self, namespace: str | None = None, page: int = 1, size: int = 20
    ) -> list[dict[str, Any]]:
        storage = self._get_active_storage()
        if storage:
            page_res = await storage.list_skills(namespace=namespace, page=page, size=size)
            items = getattr(page_res, "items", page_res)
            return [
                {
                    "namespace": s.namespace,
                    "slug": s.slug,
                    "name": s.name,
                    "description": s.description,
                    "version": getattr(s, "version", getattr(s, "latest_version", "1.0.0")),
                }
                for s in items
            ]

        # Remote client fallback
        if self.registry:
            list_fn = getattr(self.registry, "list_skills", None)
            if list_fn:
                res = list_fn(page=page, size=size, namespace=namespace)
                if inspect.isawaitable(res):
                    res = await res
                items = res.get("items", res) if isinstance(res, dict) else res
                return [
                    {
                        "namespace": (s.get("namespace") if isinstance(s, dict) else s.namespace),
                        "slug": s.get("slug") if isinstance(s, dict) else s.slug,
                        "name": s.get("name") if isinstance(s, dict) else s.name,
                        "description": (
                            s.get("description") if isinstance(s, dict) else s.description
                        ),
                        "version": (
                            s.get("version") or s.get("latest_version")
                            if isinstance(s, dict)
                            else getattr(s, "version", getattr(s, "latest_version", "1.0.0"))
                        ),
                    }
                    for s in items
                ]

        return []

    async def _search_skills_internal(
        self, query: str, limit: int = 10, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        if self.registry and hasattr(self.registry, "search"):
            res = self.registry.search(query=query, limit=limit, namespace=namespace)
            if inspect.isawaitable(res):
                res = await res
            items = res.get("items", res) if isinstance(res, dict) else res
            return [
                {
                    "namespace": (s.get("namespace") if isinstance(s, dict) else s.namespace),
                    "slug": s.get("slug") if isinstance(s, dict) else s.slug,
                    "name": s.get("name") if isinstance(s, dict) else s.name,
                    "description": (s.get("description") if isinstance(s, dict) else s.description),
                    "version": (
                        s.get("version") or s.get("latest_version")
                        if isinstance(s, dict)
                        else getattr(s, "version", getattr(s, "latest_version", "1.0.0"))
                    ),
                }
                for s in items
            ]

        storage = self._get_active_storage()
        if storage:
            items = await storage.search_skills(query=query, limit=limit, namespace=namespace)
            return [
                {
                    "namespace": s.namespace,
                    "slug": s.slug,
                    "name": s.name,
                    "description": s.description,
                    "version": getattr(s, "version", getattr(s, "latest_version", "1.0.0")),
                }
                for s in items
            ]

        return []

    async def _get_skill_internal(
        self, namespace: str, slug: str, version: str | None = None
    ) -> dict[str, Any]:
        storage = self._get_active_storage()
        if storage:
            if not version or version == "latest":
                ver = await storage.resolve_version(namespace, slug, "latest")
            else:
                ver = await storage.get_skill_version(namespace, slug, version)

            detail = await storage.get_skill(namespace, slug)
            if not ver and not detail:
                raise ValueError(f"Skill {namespace}/{slug} not found")

            frontmatter = (ver.parsed_frontmatter if ver else {}) or {}
            name = (detail.name if detail else None) or frontmatter.get("name") or slug
            description = (
                (detail.description if detail else None) or frontmatter.get("description") or ""
            )
            v_str = (
                ver.version
                if ver
                else (getattr(detail, "latest_version", "1.0.0") if detail else "1.0.0")
            )
            inst = getattr(detail, "instructions", "") if detail else ""
            instructions = ver.instructions if ver else inst
            manifest = ver.manifest if ver else {}

            return {
                "namespace": namespace,
                "slug": slug,
                "name": name,
                "description": description,
                "version": v_str,
                "instructions": instructions or "",
                "manifest": manifest or {},
                "metadata": frontmatter or {},
            }

        # Client fallback
        if self.registry:
            get_fn = getattr(self.registry, "get_skill", None) or getattr(
                self.registry, "get", None
            )
            if get_fn:
                res = get_fn(namespace, slug)
                if inspect.isawaitable(res):
                    res = await res
                if not res:
                    raise ValueError(f"Skill {namespace}/{slug} not found")
                instructions = ""
                inst_fn = getattr(self.registry, "get_instructions", None)
                if inst_fn:
                    try:
                        inst = inst_fn(namespace, slug, version or "latest")
                        if inspect.isawaitable(inst):
                            inst = await inst
                        instructions = inst
                    except Exception:
                        pass
                return {
                    "namespace": (res.get("namespace") if isinstance(res, dict) else res.namespace),
                    "slug": res.get("slug") if isinstance(res, dict) else res.slug,
                    "name": res.get("name") if isinstance(res, dict) else res.name,
                    "description": (
                        res.get("description") if isinstance(res, dict) else res.description
                    ),
                    "version": version
                    or (
                        res.get("latest_version")
                        if isinstance(res, dict)
                        else getattr(res, "latest_version", "1.0.0")
                    ),
                    "instructions": instructions
                    or (
                        res.get("instructions", "")
                        if isinstance(res, dict)
                        else getattr(res, "instructions", "")
                    ),
                    "manifest": {},
                    "metadata": {},
                }

        raise ValueError(f"Skill {namespace}/{slug} not found")

    async def _read_resource_internal(self, uri: str) -> ResourceContent:
        namespace, slug, version, file_path = parse_skill_uri(uri)
        content_bytes: bytes | None = None

        storage = self._get_active_storage()
        if storage:
            if not version or version == "latest":
                ver = await storage.resolve_version(namespace, slug, "latest")
            else:
                ver = await storage.get_skill_version(namespace, slug, version)

            if not ver:
                raise ValueError(f"Version not found for {namespace}/{slug}")

            file_obj = await storage.get_skill_resource_file(ver.id, file_path)
            if file_obj and hasattr(file_obj, "content"):
                content_bytes = file_obj.content
            else:
                resources = await storage.get_skill_resources(ver.id)
                content_bytes = resources.get(file_path)

        elif self.registry:
            get_file_fn = getattr(self.registry, "get_file", None)
            if get_file_fn:
                res = get_file_fn(namespace, slug, version or "latest", file_path)
                if inspect.isawaitable(res):
                    res = await res
                content_bytes = res
            elif hasattr(self.registry, "download_resources"):
                res = self.registry.download_resources(namespace, slug, version or "latest")
                if inspect.isawaitable(res):
                    res = await res
                content_bytes = res.get(file_path)

        if content_bytes is None:
            raise ValueError(f"Resource {file_path} not found in {namespace}/{slug}")

        mime_type = detect_content_type(file_path)
        try:
            text = content_bytes.decode("utf-8")
            return ResourceContent(uri=uri, mimeType=mime_type, text=text)
        except UnicodeDecodeError:
            blob = base64.b64encode(content_bytes).decode("ascii")
            return ResourceContent(uri=uri, mimeType=mime_type, blob=blob)

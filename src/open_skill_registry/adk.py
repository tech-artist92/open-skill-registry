import asyncio
import contextlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .client.exceptions import AuthenticationError as ClientAuthError
from .client.exceptions import NotFoundError as BaseNotFoundError
from .client.exceptions import SkillNotFoundError as ClientNotFoundError
from .client.main import AsyncSkillRegistryClient, SkillRegistryClient
from .registry.main import AsyncSkillRegistry, SkillRegistry

logger = logging.getLogger(__name__)
_ADK_THREAD_POOL: Any | None = None


class SkillNotFoundError(Exception):
    """Raised when a requested skill or resource cannot be found."""

    pass


class AuthenticationError(Exception):
    """Raised when authentication with the registry fails."""

    pass


class AwaitableList(list):
    """List subclass that can be awaited or accessed synchronously."""

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()


class AwaitableBytes(bytes):
    """Bytes subclass that can be awaited or accessed synchronously."""

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()


try:
    from google.adk.tools.skill_toolset import Frontmatter as _ADKFrontmatter
    from google.adk.tools.skill_toolset import Skill as _ADKSkill
except ImportError:
    _ADKFrontmatter = None
    _ADKSkill = None


@dataclass
class Frontmatter(_ADKFrontmatter if _ADKFrontmatter else object):
    """Metadata about a skill from a registry search."""

    name: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Skill(_ADKSkill if _ADKSkill else object):
    """A fully fetched skill definition."""

    name: str
    description: str
    instructions: str = ""
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _registry: Optional["OpenSkillRegistry"] = None

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()

    async def get_resource(self, resource_path: str) -> bytes:
        """Fetch a companion resource file on demand."""
        if self._registry is None:
            raise RuntimeError("Skill is not bound to a registry instance")
        res = self._registry.get_skill_resource(
            name=self.name, resource_path=resource_path, version=self.version
        )
        if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
            return await res
        return res

    def as_openai_tool(self, *, registry: Any = None) -> dict[str, Any]:
        """Convert this skill into an OpenAI tool definition."""
        from .adapters.openai import as_openai_tool

        reg = registry if registry is not None else self._registry
        return as_openai_tool(self, registry=reg)

    def as_langchain_tool(self, *, registry: Any = None) -> Any:
        """Convert this skill into a LangChain-compatible BaseTool."""
        from .adapters.langchain import as_langchain_tool

        reg = registry if registry is not None else self._registry
        return as_langchain_tool(self, registry=reg)

    def as_crewai_tool(self, *, registry: Any = None) -> Any:
        """Convert this skill into a CrewAI-compatible BaseTool."""
        from .adapters.crewai import as_crewai_tool

        reg = registry if registry is not None else self._registry
        return as_crewai_tool(self, registry=reg)



class OpenSkillRegistry:
    """Adapter for integrating open-skill-registry with Google ADK.

    Example:
        ```python
        registry = OpenSkillRegistry(endpoint="https://registry.example.com")
        skills = registry.search_skills("weather")
        skill = registry.get_skill(skills[0].name)
        ```
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        registry: SkillRegistry | AsyncSkillRegistry | None = None,
        default_namespace: str = "public",
        default_tag: str = "latest",
        cache_ttl: int = 60,
        timeout: float = 10.0,
        client: AsyncSkillRegistryClient | None = None,
        transport: Any | None = None,
    ) -> None:
        if not endpoint and not registry and not client:
            raise ValueError("Must provide either endpoint, registry, or client")

        self.default_namespace = default_namespace
        self.default_tag = default_tag
        self.cache_ttl = cache_ttl

        self.is_async = False
        if client:
            self.registry = client
            self.is_async = True
        elif registry:
            self.registry = registry
            import inspect

            if hasattr(registry, "search_skills") and inspect.iscoroutinefunction(
                registry.search_skills
            ) or hasattr(registry, "search") and inspect.iscoroutinefunction(
                registry.search
            ):
                self.is_async = True
        else:
            self.registry = SkillRegistryClient(
                base_url=endpoint,
                api_key=api_key,
                timeout=timeout,
                transport=transport,
            )
            self.is_async = False

    def _run(self, call: Any) -> Any:
        """Helper to run a coroutine synchronously if needed."""
        if isinstance(call, (list, bytes, str, dict)):
            return call
        if hasattr(call, "__class__") and call.__class__.__name__ in (
            "SkillDetail",
            "SkillSummary",
            "SearchResultList",
        ):
            return call
        if not asyncio.iscoroutine(call):
            return call
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(call)

        import concurrent.futures

        global _ADK_THREAD_POOL
        if _ADK_THREAD_POOL is None:
            _ADK_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        return _ADK_THREAD_POOL.submit(asyncio.run, call).result()

    def _normalize_name(self, name: str) -> str:
        """Normalize a skill name, ensuring it has a namespace."""
        if not name or not re.match(r"^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)?$", name):
            raise ValueError(f"Invalid skill name format: {name}")
        if "/" not in name:
            return f"{self.default_namespace}/{name}"
        return name

    def search_skills(self, query: str = "", **kwargs) -> AwaitableList:
        """Search the registry for skills matching the query.

        Args:
            query: The search string.

        Returns:
            An awaitable list of Frontmatter objects for matching skills.
        """
        q = query or kwargs.get("query", "")
        try:
            if hasattr(self.registry, "search_skills"):
                results = self._run(self.registry.search_skills(q))
            else:
                results = self._run(self.registry.search(q))

            if isinstance(results, dict):
                items = results.get("items", [])
            elif hasattr(results, "items"):
                items = results.items
            elif isinstance(results, list):
                items = results
            else:
                items = []

            frontmatters = []
            for r in items:
                if isinstance(r, dict):
                    name = r.get("name") or r.get("slug", "")
                    description = r.get("description", "")
                    tags = r.get("tags", [])
                else:
                    name = getattr(r, "name", None) or getattr(r, "slug", "")
                    description = getattr(r, "description", "")
                    tags = getattr(r, "tags", [])
                if isinstance(tags, dict):
                    tags = list(tags.keys())
                frontmatters.append(
                    Frontmatter(
                        name=name,
                        description=description,
                        tags=tags
                        if isinstance(tags, list)
                        else list(tags)
                        if tags
                        else [],
                    )
                )
            return AwaitableList(frontmatters)
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.NetworkError,
            ConnectionError,
        ) as e:
            logger.warning(f"Failed to search skills (network error): {e}")
            return AwaitableList()
        except Exception as e:
            logger.warning(f"Failed to search skills: {e}")
            return AwaitableList()

    def get_skill(self, name: str = "", **kwargs) -> Skill:
        """Retrieve a full skill definition from the registry.

        Args:
            name: The name or slug of the skill.

        Returns:
            A fully fetched Skill instance (awaitable or sync).

        Raises:
            SkillNotFoundError: If the skill is not found.
            AuthenticationError: If authentication fails.
            ConnectionError: If the registry is unreachable.
        """
        skill_name = name or kwargs.get("name", "")
        norm_name = self._normalize_name(skill_name)
        tag = kwargs.get("tag", self.default_tag)
        try:
            import inspect

            data = None
            if hasattr(self.registry, "get_skill"):
                sig = inspect.signature(self.registry.get_skill)
                if "slug" in sig.parameters:
                    ns, slug = norm_name.split("/", 1)
                    data = self._run(self.registry.get_skill(ns, slug))
                else:
                    data = self._run(self.registry.get_skill(norm_name))
            else:
                ns, slug = norm_name.split("/", 1)
                data = self._run(self.registry.get(ns, slug))

            if data is None:
                raise SkillNotFoundError(norm_name)

            name_val = (
                data.get("name", "")
                if isinstance(data, dict)
                else getattr(data, "name", "")
            )
            desc_val = (
                data.get("description", "")
                if isinstance(data, dict)
                else getattr(data, "description", "")
            )
            inst_val = (
                data.get("instructions", "")
                if isinstance(data, dict)
                else getattr(data, "instructions", "")
            )
            meta_val = (
                data.get("metadata", {})
                if isinstance(data, dict)
                else getattr(data, "metadata", {})
            )

            if not name_val:
                name_val = norm_name
            elif "/" not in name_val:
                name_val = f"{norm_name.split('/')[0]}/{name_val}"

            if not inst_val and hasattr(self.registry, "get_instructions"):
                ns, slug = norm_name.split("/", 1)
                with contextlib.suppress(Exception):
                    inst_val = (
                        self._run(
                            self.registry.get_instructions(
                                ns, slug, tag or "latest"
                            )
                        )
                        or ""
                    )

            return Skill(
                name=name_val,
                description=desc_val,
                instructions=inst_val,
                metadata=meta_val,
                version=tag,
                _registry=self,
            )
        except (ClientNotFoundError, BaseNotFoundError) as e:
            raise SkillNotFoundError(norm_name) from e
        except ClientAuthError as e:
            raise AuthenticationError("Authentication failed") from e
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.NetworkError,
            ConnectionError,
        ) as e:
            raise ConnectionError(f"Connection error: {e}") from e
        except Exception as e:
            if "unreachable" in str(e).lower() or isinstance(e, ConnectionError):
                raise ConnectionError(f"Connection error: {e}") from e
            if type(e).__name__ in ("ClientAuthenticationError", "AuthenticationError"):
                raise AuthenticationError("Authentication failed") from e
            if type(e).__name__ in ("NotFoundError", "SkillNotFoundError"):
                raise SkillNotFoundError(norm_name) from e
            raise

    def get_skill_resource(
        self,
        name: str = "",
        resource_path: str = "",
        version: str | None = None,
        **kwargs,
    ) -> AwaitableBytes:
        """Fetch a companion resource file for a given skill.

        Args:
            name: The skill name.
            resource_path: The path of the resource.
            version: The skill version (defaults to latest).

        Returns:
            The raw bytes of the requested resource (awaitable or sync).

        Raises:
            SkillNotFoundError: If the resource or skill is missing.
        """
        skill_name = name or kwargs.get("name", "")
        res_path = resource_path or kwargs.get("resource_path", "")
        ver = version or kwargs.get("version")
        norm_name = self._normalize_name(skill_name)
        if ver is None:
            ver = self.default_tag
        try:
            if hasattr(self.registry, "get_skill_resource"):
                raw = self._run(
                    self.registry.get_skill_resource(
                        norm_name, res_path, version=ver
                    )
                )
            elif hasattr(self.registry, "get_file"):
                ns, slug = norm_name.split("/", 1)
                raw = self._run(
                    self.registry.get_file(ns, slug, ver, res_path)
                )
            elif hasattr(self.registry, "download_resources"):
                ns, slug = norm_name.split("/", 1)
                resources = self._run(
                    self.registry.download_resources(ns, slug, ver)
                )
                if res_path not in resources:
                    raise SkillNotFoundError(
                        f"Resource {res_path} not found in skill {norm_name}"
                    )
                raw = resources[res_path]
            else:
                raise SkillNotFoundError(f"Cannot get resource {res_path}")
            return AwaitableBytes(
                raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
            )
        except (ClientNotFoundError, BaseNotFoundError) as e:
            raise SkillNotFoundError(
                f"Resource {res_path} not found in skill {norm_name}"
            ) from e
        except Exception as e:
            if type(e).__name__ in ("SkillNotFoundError", "NotFoundError"):
                raise SkillNotFoundError(
                    f"Resource {res_path} not found in skill {norm_name}"
                ) from e
            raise

import httpx
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Union, Dict, Any, List

from .registry.main import AsyncSkillRegistry, SkillRegistry
from .client.main import AsyncSkillRegistryClient, SkillRegistryClient
from .client.exceptions import (
    AuthenticationError as ClientAuthError,
    SkillNotFoundError as ClientNotFoundError,
    NotFoundError as BaseNotFoundError,
)

logger = logging.getLogger(__name__)

class SkillNotFoundError(Exception):
    """Raised when a requested skill or resource cannot be found."""
    pass

class AuthenticationError(Exception):
    """Raised when authentication with the registry fails."""
    pass

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
    tags: List[str] = field(default_factory=list)

@dataclass
class Skill(_ADKSkill if _ADKSkill else object):
    """A fully fetched skill definition."""
    name: str
    description: str
    instructions: str = ""
    version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    _registry: Optional["OpenSkillRegistry"] = None

    async def get_resource(self, resource_path: str) -> bytes:
        """Fetch a companion resource file on demand."""
        if self._registry is None:
            raise RuntimeError("Skill is not bound to a registry instance")
        res = self._registry.get_skill_resource(
            name=self.name, resource_path=resource_path, version=self.version
        )
        import asyncio
        if asyncio.iscoroutine(res):
            return await res
        return res
    
class OpenSkillRegistry:
    """
    Adapter for integrating open-skill-registry with Google ADK.
    
    Example:
        ```python
        registry = OpenSkillRegistry(endpoint="https://registry.example.com")
        skills = registry.search_skills("weather")
        skill = registry.get_skill(skills[0].name)
        ```
    """
    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        registry: Optional[Union[SkillRegistry, AsyncSkillRegistry]] = None,
        default_namespace: str = "public",
        default_tag: str = "latest",
        cache_ttl: int = 60,
        timeout: float = 10.0,
        client: Optional[AsyncSkillRegistryClient] = None,
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
            if hasattr(registry, "search_skills") and inspect.iscoroutinefunction(registry.search_skills):
                self.is_async = True
        else:
            self.registry = SkillRegistryClient(
                base_url=endpoint,
                api_key=api_key,
                timeout=timeout
            )
            self.is_async = False
            
    def _run(self, call: Any) -> Any:
        """
        Helper to run a coroutine synchronously if needed.
        
        Args:
            call: A coroutine object to run.
            
        Returns:
            The result of the coroutine.
        """
        if not self.is_async:
            return call
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(call)
        
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, call).result()

    def _normalize_name(self, name: str) -> str:
        """
        Normalize a skill name, ensuring it has a namespace.
        
        Args:
            name: The skill name to normalize.
            
        Returns:
            The normalized skill name.
        """
        if not name or not re.match(r'^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)?$', name):
            raise ValueError(f"Invalid skill name format: {name}")
        if "/" not in name:
            return f"{self.default_namespace}/{name}"
        return name

    def search_skills(self, query: str) -> List[Frontmatter]:
        """
        Search the registry for skills matching the query.
        
        Args:
            query: The search string.
            
        Returns:
            A list of Frontmatter objects for matching skills.
        """
        try:
            if hasattr(self.registry, "search_skills"):
                results = self._run(self.registry.search_skills(query))
            else:
                results = self._run(self.registry.search(query))
            return [
                Frontmatter(
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    tags=r.get("tags", [])
                )
                for r in results
            ]
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, ConnectionError) as e:
            logger.warning(f"Failed to search skills (network error): {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to search skills: {e}")
            return []

    def get_skill(self, name: str) -> Skill:
        """
        Retrieve a full skill definition from the registry.
        
        Args:
            name: The name or slug of the skill.
            
        Returns:
            A fully fetched Skill instance.
            
        Raises:
            SkillNotFoundError: If the skill is not found.
            AuthenticationError: If authentication fails.
            ConnectionError: If the registry is unreachable.
        """
        norm_name = self._normalize_name(name)
        tag = self.default_tag
        try:
            import inspect
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
            return Skill(
                name=data.get("name", ""),
                description=data.get("description", ""),
                instructions=data.get("instructions", ""),
                metadata=data.get("metadata", {}),
                version=tag,
                _registry=self
            )
        except (ClientNotFoundError, BaseNotFoundError):
            raise SkillNotFoundError(norm_name)
        except ClientAuthError:
            raise AuthenticationError("Authentication failed")
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, ConnectionError) as e:
            raise ConnectionError(f"Connection error: {e}")
        except Exception as e:
            if "unreachable" in str(e).lower() or isinstance(e, ConnectionError):
                raise ConnectionError(f"Connection error: {e}")
            if type(e).__name__ in ("ClientAuthenticationError", "AuthenticationError"):
                raise AuthenticationError("Authentication failed")
            if type(e).__name__ in ("NotFoundError", "SkillNotFoundError"):
                raise SkillNotFoundError(norm_name)
            raise

    def get_skill_resource(self, name: str, resource_path: str, version: Optional[str] = None) -> bytes:
        """
        Fetch a companion resource file for a given skill.
        
        Args:
            name: The skill name.
            resource_path: The path of the resource.
            version: The skill version (defaults to latest).
            
        Returns:
            The raw bytes of the requested resource.
            
        Raises:
            SkillNotFoundError: If the resource or skill is missing.
        """
        norm_name = self._normalize_name(name)
        if version is None:
            version = self.default_tag
        try:
            if hasattr(self.registry, "get_skill_resource"):
                return self._run(self.registry.get_skill_resource(norm_name, resource_path, version=version))
            else:
                ns, slug = norm_name.split("/", 1)
                return self._run(self.registry.get_file(ns, slug, version, resource_path))
        except (ClientNotFoundError, BaseNotFoundError):
            raise SkillNotFoundError(f"Resource {resource_path} not found in skill {norm_name}")
        except Exception as e:
            if type(e).__name__ in ("SkillNotFoundError", "NotFoundError"):
                raise SkillNotFoundError(f"Resource {resource_path} not found in skill {norm_name}")
            raise

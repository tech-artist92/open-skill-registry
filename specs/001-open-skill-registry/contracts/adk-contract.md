# ADK Integration Contract: `OpenSkillRegistry` Python SDK Adapter

**Module**: `open_skill_registry.adk`  
**Compatibility**: Google Agent Development Kit (ADK) 2.9.2+  
**Target Class**: `OpenSkillRegistry`  
**License**: Apache-2.0  

---

## 1. ADK Architecture Alignment

Google ADK's `SkillToolset` accepts a `registry` parameter implementing:
1. `async search_skills(*, query: str) -> list[Frontmatter]`
2. `async get_skill(*, name: str) -> Skill`

`OpenSkillRegistry` provides a 100% compliant drop-in implementation that works across both deployment modes:
- **Hosted Mode**: Connects via HTTP/REST to a remote Open Skill Registry server.
- **Embedded Mode**: Wraps an in-process `SkillRegistry` engine connecting directly to user's database & vector infrastructure without HTTP networking.

---

## 2. Class Specification

```python
class OpenSkillRegistry:
    """Drop-in Skill Registry for Google ADK agents (supports hosted & embedded)."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        registry: "SkillRegistry | AsyncSkillRegistry | None" = None,
        default_namespace: str = "public",
        default_tag: str = "latest",
        cache_ttl: int = 60,
        timeout: float = 10.0,
    ) -> None:
        """Initialize registry connection.
        
        Args:
            endpoint: Base URL of hosted registry server (e.g. 'http://localhost:8080').
            api_key: Optional API key for accessing private or namespace-scoped skills.
            registry: Optional in-process embedded SkillRegistry instance (direct-to-infra).
            default_namespace: Default namespace for unqualified skill names.
            default_tag: Default release tag to request when unversioned (default 'latest').
            cache_ttl: Local client-side in-memory TTL in seconds for frontmatter.
            timeout: HTTP request timeout in seconds (for hosted mode).
            
        Note:
            Provide either `endpoint` for hosted mode or `registry` for embedded mode.
        """
        ...

    async def search_skills(self, *, query: str) -> list[Frontmatter]:
        """Perform semantic & keyword search across published skills.
        
        In hosted mode: Calls GET /api/v1/skills/search?q={query}.
        In embedded mode: Invokes registry.search(query=query) in-process.
        
        Filters out collisions with any local skills already registered in the toolset.
        
        Returns:
            list[Frontmatter]: List of ADK Frontmatter objects (name, description).
        """
        ...

    async def get_skill(self, *, name: str) -> Skill:
        """Fetch skill details and construct an executable ADK Skill object.
        
        Parses `name` into `namespace/slug` (or prepends default_namespace).
        In hosted mode: Calls GET /api/v1/skills/{namespace}/{slug}/tags/{default_tag}.
        In embedded mode: Invokes registry.get(name=name, tag=default_tag) in-process.
        Constructs a Skill instance with instructions and lazy resource loaders.
        
        Returns:
            Skill: Executable ADK Skill object ready for agent prompt injection.
        """
        ...

    async def get_skill_resource(
        self,
        *,
        name: str,
        resource_path: str,
        version: str | None = None,
    ) -> bytes:
        """Fetch an individual resource file on-demand.
        
        In hosted mode: Calls GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file?path={resource_path}.
        In embedded mode: Fetches resource bytes directly from DB in-process.
        
        Returns:
            bytes: Raw file content for scripts, reference markdown, or assets.
        """
        ...
```

---

## 3. ADK Agent Usage Patterns

### Pattern A: Embedded Library Mode (Direct to Infrastructure)

```python
from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset
from open_skill_registry import SkillRegistry, RegistryConfig
from open_skill_registry.adk import OpenSkillRegistry

# 1. Initialize embedded registry (from osr.config.yaml or code config)
# FastEmbed local model is ON by default (zero API keys required)
registry_engine = SkillRegistry.from_config("osr.config.yaml")
# Or in code:
# registry_engine = SkillRegistry(config=RegistryConfig(
#     db_url="postgresql+asyncpg://postgres:password@localhost:5432/skills_db",
#     embedding_provider="fastembed", # default local ONNX model
# ))

# 2. Wire directly into ADK SkillToolset
skill_toolset = SkillToolset(
    registry=OpenSkillRegistry(registry=registry_engine),
)

# 3. Define the ADK Agent
agent = Agent(
    model="gemini-flash-latest",
    name="embedded_agent",
    description="Agent with direct in-process skill search and loading.",
    instruction="You can dynamically search and load skills using search_skills and load_skill.",
    tools=[skill_toolset],
)
```

### Pattern B: Hosted Server Mode (Microservice / Team Registry)

```python
import os
from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset
from open_skill_registry.adk import OpenSkillRegistry

# 1. Initialize remote registry client
registry = OpenSkillRegistry(
    endpoint=os.environ.get("OSR_ENDPOINT", "http://localhost:8080"),
    api_key=os.environ.get("OSR_API_KEY"),
)

# 2. Configure SkillToolset
skill_toolset = SkillToolset(
    registry=registry,
)

# 3. Define the ADK Agent
agent = Agent(
    model="gemini-flash-latest",
    name="skill_registry_agent",
    description="Agent with remote on-demand capability retrieval.",
    instruction="You can dynamically search and load skills using search_skills and load_skill.",
    tools=[skill_toolset],
)
```

---

## 4. Error Handling

| Condition | Behavior |
|---|---|
| Registry unreachable (connection timeout) | `search_skills()` returns empty list with logged warning. `get_skill()` raises `ConnectionError`. |
| Skill not found (404) | `get_skill()` raises `SkillNotFoundError(name)`. |
| Authentication failure (401/403) | Raises `AuthenticationError` with details from response envelope. |
| Yanked version returned | `get_skill()` logs a warning but returns the skill with `metadata.yanked = True`. |
| Invalid skill name format | Raises `ValueError` before making any network call. |
| Rate limited (429) | Retries with exponential backoff (max 3 attempts, base 1s). |

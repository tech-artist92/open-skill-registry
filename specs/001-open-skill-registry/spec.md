# Feature Specification: Open Skill Registry

**Feature Branch**: `001-open-skill-registry`

**Created**: 2026-09-26

**Status**: Draft

**License**: Apache-2.0

**Input**: User description: "Create an open-source, self-hostable skill registry for AI agent skills, compatible with Google ADK 2.9.2+ SkillToolset, supporting enterprise-grade packaging, security verification, content-addressable storage, and multi-client interoperability."

## Clarifications

### Session 2026-09-26

- Q: When an agent or client requests a skill without specifying an explicit version or release tag, how should the registry resolve which version to serve? → A: Default to the `latest` tag (points to the newest published non-yanked version).
- Q: What packaging format should the CLI and API use to transmit skills during publishing? → A: Flexible zero-friction publishing: natively accept single `SKILL.md` files, raw directory multipart uploads, batch multi-skill uploads, and optional zip/archive uploads without forcing archive compression.
- Q: Should a lightweight Web UI be included in v1 to support visual skill browsing, search, and drag-and-drop file/folder/zip uploads? → A: Yes, a built-in lightweight Web UI served directly by FastAPI (providing visual catalog browsing, search, and drag-and-drop uploads for standalone files, folders, or zips) is included in v1.
- Q: When a skill is published without an explicit version specified in the command or upload form, how should the registry determine the release version? → A: Frontmatter first, then auto-increment patch (reads version from SKILL.md if present; otherwise increments the latest version's patch number, or starts at 1.0.0 for initial release).
- Q: When the registry runs in secured mode (AUTH_ENABLED=true), how should the initial administrative API key be bootstrapped? → A: Env-var bootstrap with auto-generate fallback. If `OSR_ADMIN_KEY` is set, the server seeds it as the admin key on first startup. If unset and no admin key exists, the server auto-generates one and prints it to stdout on first boot.
- Q: How should Open Skill Registry support both standalone hosted service and embedded Python library usage? → A: Dual delivery model (inspired by modern developer tools like Mem0): (1) **Hosted Server Mode**: FastAPI server + Web UI + Redis + REST API + CLI client (`SkillRegistryClient`), and (2) **Embedded Library Mode**: In-process Python engine (`SkillRegistry`) connecting directly to the user's infrastructure (PostgreSQL/pgvector or SQLite, pluggable embeddings) without needing an HTTP server.
- Q: What embedding model should be used by default, and how should embedding models and search be configured? → A: Semantic search is **ON by default** using an embedded local model (`fastembed` with `BAAI/bge-small-en-v1.5`, 384 dimensions) running via ONNX Runtime without needing external API keys or GPU. Users can configure default search behavior and supply their own embedding models (Gemini, OpenAI, Ollama, custom HuggingFace) or disable semantic search (`none`) via a single unified configuration file (`osr.config.yaml`). When semantic search is disabled or unavailable, weighted syntactic full-text search powers skill discovery with heavy weight on name and description.
- Q: How should project configuration and setup be structured for ease of adoption? → A: A single unified configuration file (`osr.config.yaml` / `.osr/config.yaml`) configures server, embedded library, storage, database, search, and embedding models. Minimal setup steps (`pip install open-skill-registry` and `osr init`) allow developers to get started in seconds with either library or hosted mode.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Discovers and Loads Skills On-Demand (Priority: P1)

An AI agent built with Google ADK receives a user request it cannot handle with its current instructions. The agent uses the registry to search for relevant skills by natural language query, identifies a matching skill, loads its instructions and resources, and fulfills the user request using the dynamically loaded capability.

**Why this priority**: This is the core value proposition — agents can scale to hundreds of capabilities without bloating their base prompt by dynamically discovering and loading skills from a central registry.

**Independent Test**: Can be fully tested by starting the registry server, publishing a sample skill, configuring an ADK agent with `OpenSkillRegistry`, and verifying the agent can search for, load, and use the skill to answer a query it otherwise couldn't handle.

**Acceptance Scenarios**:

1. **Given** a registry with published skills, **When** an ADK agent calls `search_skills(query="weather forecast")`, **Then** the registry returns a ranked list of matching skill frontmatters within 2 seconds.
2. **Given** a search result identifying a skill named `weather-forecast`, **When** the agent calls `get_skill(name="public/weather-forecast")`, **Then** the registry returns the full skill object with instructions and resource manifest.
3. **Given** a loaded skill, **When** the agent needs a reference file, **Then** the resource is fetched individually on-demand via query-parameter safe endpoints without downloading the entire skill package.
4. **Given** no matching skills exist, **When** the agent searches, **Then** an empty result list is returned (not an error).

---

### User Story 2 - Developer Publishes a Skill Package with Security & Validation (Priority: P1)

A developer creates a skill following the Agent Skills Specification (with `SKILL.md`, optional `references/`, `assets/`, `scripts/` directories). They use the CLI to validate, package, and publish the skill to the registry with a semantic version number. The registry performs structural validation, checks file type allowlists and package size constraints, prevents directory traversal, and creates an immutable snapshot.

**Why this priority**: Without publishing and validation, there are no trustworthy skills to discover. This enables the supply side of the registry ecosystem.

**Independent Test**: Can be fully tested by creating a sample skill directory, running `osr push`, and verifying the skill appears in the registry with correct metadata, version, content hash, and compliance snapshot.

**Acceptance Scenarios**:

1. **Given** a valid skill directory with `SKILL.md` containing proper frontmatter, **When** the developer runs `osr push ./my-skill/ --namespace myorg --version 1.0.0`, **Then** the skill is validated, uploaded, and the CLI confirms success with the content hash.
2. **Given** an invalid skill directory (missing `SKILL.md`, invalid frontmatter, or containing disallowed binary files), **When** the developer runs `osr push`, **Then** the CLI reports specific validation errors before any upload occurs.
3. **Given** a skill package containing symlinks or paths attempting directory traversal (e.g., `../`), **When** publishing is attempted, **Then** the server rejects the upload with a 400 Bad Request error.
4. **Given** a skill `myorg/my-skill@1.0.0` already exists, **When** the developer tries to publish the same version again, **Then** the system rejects the publish with a 409 Conflict error (immutable versions).
5. **Given** a published skill, **When** the developer runs `osr push` with version `1.1.0`, **Then** a new version is created and the `latest` tag automatically points to it.
6. **Given** a developer with a standalone `SKILL.md` file or a directory containing multiple skills, **When** they publish via CLI or UI file picker, **Then** the registry directly accepts and processes the upload without requiring pre-compression into an archive.

---

### User Story 3 - Developer Searches and Pulls Skills Locally with Fingerprint Verification (Priority: P2)

A developer uses the CLI to search the registry for skills by natural language query, inspect skill metadata and version history, and download a specific skill version to their local filesystem for use in their agent project, verifying file integrity against the content fingerprint.

**Why this priority**: Developers need to explore the registry catalog and integrate skills into their projects outside of agent runtime with confidence in package integrity.

**Independent Test**: Can be fully tested by searching the registry via CLI, inspecting results, downloading a skill to a local directory, and verifying its SHA-256 fingerprint matches.

**Acceptance Scenarios**:

1. **Given** a registry with published skills, **When** the developer runs `osr search "data analysis"`, **Then** matching skills are displayed with name, namespace, version, downloads, and description.
2. **Given** a skill `google/bigquery-optimizer`, **When** the developer runs `osr info google/bigquery-optimizer`, **Then** the CLI displays full metadata, version history, release tags, and author/license info.
3. **Given** a skill exists at version `1.2.0`, **When** the developer runs `osr pull google/bigquery-optimizer --version 1.2.0 --output ./skills/`, **Then** the complete skill directory is downloaded and verified against the content hash.
4. **Given** a local skill directory, **When** the developer runs `osr verify ./skills/bigquery-optimizer`, **Then** the CLI confirms that local files match the remote release manifest.

---

### User Story 4 - Developer Manages Release Tags (Priority: P2)

A developer promotes a tested skill version to a release channel (e.g., `production`, `staging`) by setting a release tag. Agents configured to track a tag automatically resolve to the tagged version.

**Why this priority**: Release tags enable controlled rollouts without changing agent configuration — agents pinned to `production` get the latest promoted version.

**Independent Test**: Can be fully tested by publishing multiple versions, setting tags, and verifying tag resolution returns the correct version.

**Acceptance Scenarios**:

1. **Given** a skill with versions `1.0.0` and `1.1.0`, **When** the developer runs `osr tag myorg/my-skill 1.0.0 production`, **Then** the `production` tag points to version `1.0.0`.
2. **Given** the `production` tag points to `1.0.0`, **When** the developer moves it to `1.1.0`, **Then** subsequent agent requests for the `production` tag resolve to `1.1.0`.
3. **Given** a tag `production` exists, **When** an agent fetches the skill via the `production` tag, **Then** the correct version's instructions and resources are returned.

---

### User Story 5 - Enterprise Namespace Scoping & Multi-Tier Visibility (Priority: P2)

An organization hosts both public capabilities and confidential internal skills. Administrators set visibility (`PUBLIC`, `NAMESPACE_ONLY`, `PRIVATE`) and manage team access tokens so private skills are only discoverable and accessible to authorized team agents.

**Why this priority**: Enterprise adoption requires boundary isolation so proprietary skills and data instructions do not leak into public agent search results.

**Independent Test**: Can be fully tested by creating a `NAMESPACE_ONLY` skill, verifying that unauthenticated searches exclude it, while agents with the namespace API key can discover and load it.

**Acceptance Scenarios**:

1. **Given** a skill in namespace `corp` with visibility `NAMESPACE_ONLY`, **When** an unauthenticated client searches the registry, **Then** the skill is omitted from the search results.
2. **Given** an agent configured with an API key for namespace `corp`, **When** the agent searches or loads `corp/internal-tool`, **Then** the request succeeds and returns the skill.
3. **Given** an API key scoped to namespace `team-a`, **When** the client attempts to publish to `team-b`, **Then** the request is rejected with a 403 Forbidden error.

---

### User Story 6 - Deterministic Resolution Endpoint for External Agents (Priority: P2)

External agent CLIs, automation scripts, and tooling resolve skills deterministically using version numbers, release tags, or exact SHA-256 content hashes via a lightweight resolve endpoint.

**Why this priority**: Provides interoperability across diverse agent runtimes without requiring full registry SDK integration.

**Independent Test**: Can be fully tested by querying the `/resolve` endpoint with a specific hash or tag and verifying it returns the canonical version and metadata.

**Acceptance Scenarios**:

1. **Given** a published skill with content hash `a1b2c3d4...`, **When** a client sends `GET /api/v1/skills/{namespace}/{slug}/resolve?hash=a1b2c3d4...`, **Then** the server resolves the exact matching version and manifest URL.
2. **Given** a release tag `stable`, **When** a client queries `/resolve?tag=stable`, **Then** the server returns the version currently bound to that tag.

---

### User Story 7 - Developer Yanks a Faulty Version (Priority: P3)

A developer discovers a bug or security issue in a published skill version and yanks it. Agents that have already loaded the skill continue working, but new discovery excludes it and direct fetches receive a warning.

**Why this priority**: Version yanking is a safety mechanism, but occurs infrequently and is lower priority than core publish/discover/load flows.

**Independent Test**: Can be fully tested by publishing a skill, yanking it, and verifying that fetch requests return a warning flag.

**Acceptance Scenarios**:

1. **Given** a published skill version `1.0.0`, **When** the developer runs `osr yank myorg/my-skill 1.0.0`, **Then** the version is marked as yanked.
2. **Given** a yanked version `1.0.0`, **When** an agent explicitly fetches version `1.0.0`, **Then** the skill is returned with a `yanked: true` flag and an `X-Skill-Warning: Yanked` header.
3. **Given** a yanked version, **When** searching or listing skills, **Then** the yanked version is excluded from results by default.

---

### User Story 8 - Developer Uses Web UI for Skill Discovery and Uploads (Priority: P2)

A developer or team member navigates to the registry's web interface in a browser. They can visually explore the skill catalog, search capabilities by keyword or intent, inspect README/instructions and resource trees, and upload new skills by dragging and dropping standalone `SKILL.md` files, skill directories, or zip archives without using terminal commands.

**Why this priority**: Enhances accessibility for non-CLI users and provides an immediate, zero-barrier way to browse and contribute skills to the team registry.

**Independent Test**: Can be fully tested by opening the web interface in a browser, searching for skills, and uploading a skill via the drag-and-drop file/folder uploader.

**Acceptance Scenarios**:

1. **Given** the registry server is running, **When** a user navigates to the web interface root, **Then** the catalog displays published skills with search and filtering controls.
2. **Given** a developer with a `SKILL.md` file, folder, or zip archive, **When** they drag and drop it onto the upload target in the Web UI, **Then** the UI validates the files and completes publishing, displaying the newly created version and content hash.
3. **Given** a selected skill in the UI, **When** the user views its detail page, **Then** the parsed markdown instructions, metadata tags, version history, and resource files are rendered cleanly.

---

### User Story 9 - Developer Uses Registry as an Embedded In-Process Library (Priority: P1)

A developer building an AI agent or backend service imports `open_skill_registry` directly into their Python code as a pure library (`from open_skill_registry import SkillRegistry`). They configure it with their own database connection (e.g. existing PostgreSQL/pgvector or local SQLite) and embedding provider, and perform skill publishing, search, retrieval, and ADK integration directly in-process without spinning up, hosting, or maintaining a separate HTTP registry server.

**Why this priority**: Mirrors the Mem0 library pattern (`from mem0 import Memory` vs `from mem0 import MemoryClient`). Many teams already have existing PostgreSQL/pgvector or vector infrastructure and want to avoid deploying, operating, and securing a dedicated network microservice when an embedded library connecting directly to their infra is faster, zero-latency, and zero-ops.

**Independent Test**: Can be fully tested with a Python script: initialize `SkillRegistry(config=...)`, publish a skill, search for it, and load it into an ADK agent without starting any HTTP server or network ports.

**Acceptance Scenarios**:

1. **Given** a Python script importing `SkillRegistry`, **When** the developer initializes it with a database URI, **Then** the registry engine connects directly to the underlying database without initiating HTTP requests.
2. **Given** an embedded `SkillRegistry` instance, **When** `publish()`, `search()`, `get()`, or `resolve()` are invoked, **Then** the operations execute in-process with zero network HTTP overhead.
3. **Given** an ADK agent, **When** the developer passes `OpenSkillRegistry(registry=embedded_registry)` or `SkillRegistry.to_adk()`, **Then** the ADK agent searches and loads skills directly through the in-process engine.
4. **Given** a remote setup, **When** a developer uses `SkillRegistryClient(endpoint="http://...")`, **Then** it operates seamlessly against a hosted Open Skill Registry server using the exact same high-level interface.

---

### User Story 10 - Agent Executes Skills via Model Context Protocol (MCP) (Priority: P1)

An agent uses the registry as an MCP Server (SEP-2640) to dynamically discover and execute skills via standard `osr mcp` stdio or a hosted `/mcp/sse` endpoint.

**Why this priority**: Universal interoperability beyond Google ADK.

**Independent Test**: Start the CLI MCP server and use the Claude desktop app to load and execute a skill.

**Acceptance Scenarios**:

1. **Given** a client configured for MCP, **When** it queries `osr mcp` for tools, **Then** it receives the available skills.

---

### User Story 11 - Developer Installs Skills Directly into IDE Workspaces (Priority: P1)

A developer uses `osr install` to automatically download and sync a skill directly into their IDE workspace (`.cursor/skills/`, `.claude/skills/`).

**Why this priority**: Meets developers where they work by integrating directly with modern AI IDEs.

**Independent Test**: Run `osr install google/bigquery` inside a Cursor project and verify files are created.

**Acceptance Scenarios**:

1. **Given** a valid skill, **When** the developer runs `osr install <skill>`, **Then** files are correctly written to the `.cursor/skills` folder.

---

### User Story 12 - Publisher Imports Skills Directly from Git (Priority: P2)

A publisher imports a remote Git repository of skills using `osr import github:owner/repo`.

**Why this priority**: Streamlines bulk onboarding of existing open-source tool collections.

**Independent Test**: Run import on a public GitHub repo and verify skills are published.

**Acceptance Scenarios**:

1. **Given** a public repo with valid `SKILL.md` files, **When** `osr import github:owner/repo` is executed, **Then** all skills are extracted and published to the registry.

---

### User Story 13 - Security Scanner Blocks Malicious Skills (Priority: P1)

A security scanner automatically audits an uploaded skill for prompt injection and malicious shell scripts, tagging it with a CRITICAL safety score and blocking execution.

**Why this priority**: Trust is paramount in an open ecosystem.

**Independent Test**: Upload a skill with a known prompt injection string and verify rejection.

**Acceptance Scenarios**:

1. **Given** a skill with malicious content, **When** it is pushed, **Then** the registry scans, detects the threat, and rejects the publish with a 422 error and a safety report.

---

### User Story 14 - Developer Uses Standard LangChain/OpenAI Bridges (Priority: P2)

A developer uses LangChain or OpenAI function calling bridges (e.g., `as_langchain_tools()`) to load and execute skills.

**Why this priority**: Broadens the framework ecosystem compatibility.

**Independent Test**: Load a skill and convert it to a LangChain tool, then invoke it.

**Acceptance Scenarios**:

1. **Given** a loaded skill, **When** the developer calls `as_langchain_tools()`, **Then** a compatible tool object is returned.

---

### Edge Cases

- What happens when the embedding provider is unavailable during a search? The system falls back to PostgreSQL full-text search and logs a warning.
- What happens when Redis cache is unavailable? The system bypasses caching and serves directly from PostgreSQL with degraded performance.
- What happens when a skill name exceeds 64 characters or uses invalid characters? The publish is rejected at validation with a specific error message.
- What happens when an agent requests a skill that was never published? A 404 response with a clear "skill not found" message is returned.
- What happens when a publish request is retried due to network issues? Duplicate version publishes return 409 Conflict, preventing accidental overwrites.
- What happens when a skill contains nested subpaths with special characters? Resources are retrievable using path query parameters (e.g. `?path=references/sub/doc.md`) to avoid URL decoding anomalies.
- What happens when an uploaded package exceeds 10MB or contains disallowed binary types? The package is rejected at the API boundary with a 413 or 422 error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a REST API for skill discovery, retrieval, and publishing following OpenAPI specification.
- **FR-002**: System MUST validate all published skills against the Agent Skills Specification (requiring `SKILL.md` with valid frontmatter containing `name` and `description`).
- **FR-003**: System MUST enable semantic search by default using a built-in local embedding model (`fastembed` with `BAAI/bge-small-en-v1.5`, 384 dimensions) requiring zero external API keys or GPU, while allowing users to configure alternative external providers (Gemini, OpenAI, Ollama, HuggingFace) or disable semantic search (`provider: none`) via the unified configuration file.
- **FR-004**: System MUST implement first-class syntactic / full-text search with heavy relevance weighting prioritizing skill name / slug (Weight A: 1.0) and description (Weight B: 0.4), with tags and instructions (Weight C/D: 0.2/0.1), delivering superior out-of-the-box skill discovery both in hybrid mode (blended with semantic embeddings via Reciprocal Rank Fusion) and standalone fallback mode when semantic embeddings are disabled or unavailable.
- **FR-005**: System MUST enforce immutable versions — once a skill version is published, its content cannot be modified or overwritten.
- **FR-006**: System MUST generate a content-addressed manifest (SHA256) for each published skill version, recording individual file hashes and sizes.
- **FR-007**: System MUST support namespace-scoped skill organization (e.g., `myorg/skill-name`).
- **FR-008**: System MUST support mutable release tags (`latest`, `production`, `staging`, `beta`) that point to immutable versions.
- **FR-009**: System MUST automatically assign the `latest` tag to the most recently published non-yanked version, and MUST resolve untagged or unversioned skill fetch requests to the `latest` tag.
- **FR-010**: System MUST support soft-deletion (yanking) of published versions with warning propagation.
- **FR-011**: System MUST provide incremental skill loading: frontmatter (L1) → instructions (L2) → individual resources (L3).
- **FR-012**: System MUST implement a Python SDK adapter (`OpenSkillRegistry`) that is a drop-in replacement for ADK's `GCPSkillRegistry`, supporting both hosted remote servers and embedded direct-to-infra library engines.
- **FR-013**: System MUST provide a CLI tool (`osr`) for publishing, searching, pulling, tagging, verifying, and managing skills.
- **FR-014**: System MUST support two operational modes: open (no authentication, default) and secured (API key authentication for write operations).
- **FR-015**: System MUST cache search results and frequently accessed frontmatter in Redis with configurable TTL and ETag-based invalidation (optional in embedded library mode).
- **FR-016**: System MUST store all skill content (instructions, resources, manifests) directly in the configured database store (PostgreSQL by default).
- **FR-017**: System MUST provide paginated responses for list and search endpoints using a unified structure (`items`, `total`, `page`, `size`).
- **FR-018**: System MUST support flexible, low-friction publishing mechanisms without requiring manual archive creation: accepting single standalone `SKILL.md` files, directory structures (multi-file multipart upload), batch multi-skill uploads, and optional archive bundles (.zip / .tar.gz).
- **FR-019**: System MUST automatically generate and store vector embeddings upon publish using the default local embedding model or user-configured provider, and MUST gracefully skip vector generation when the provider is explicitly set to `none`.
- **FR-020**: System MUST provide a health check endpoint accessible without authentication.
- **FR-021**: System MUST enforce package safety constraints on publish, including a file extension allowlist (`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.py`, `.sh`, `.ts`, `.js`, `.png`, `.jpg`, `.svg`), a per-file size limit (1MB default), total package limit (10MB default), and rejection of path traversal sequences (`../`).
- **FR-022**: System MUST support skill and namespace visibility tiers (`PUBLIC`, `NAMESPACE_ONLY`, `PRIVATE`), ensuring search and retrieval filters enforce access rules according to client credentials.
- **FR-023**: System MUST provide a `/resolve` endpoint enabling deterministic lookup of skill versions by version string, tag, or content hash.
- **FR-024**: System MUST allow individual resource retrieval via query parameter (e.g. `/file?path=...`) to avoid path encoding issues across different agent runtime environments.
- **FR-025**: System MUST capture and freeze license, author attribution, and declared compliance tags into an immutable version snapshot (`complianceSnapshot`) upon publish.
- **FR-026**: System MUST support multi-client installation directory conventions in the CLI (supporting project-level `.agents/skills` and user-level global paths).
- **FR-027**: System MUST provide a built-in lightweight Web UI served by the registry server, supporting visual catalog browsing, full-text/semantic search, skill detail viewing, and drag-and-drop upload of single `SKILL.md` files, folders, and zip bundles.
- **FR-028**: System MUST infer the release version if omitted in the publish request: reading the `version` field from `SKILL.md` frontmatter if provided, or otherwise automatically incrementing the latest published version's patch number (defaulting to `1.0.0` for new skills).
- **FR-029**: System MUST provide REST API endpoints for creating, listing, viewing, and updating namespaces, enforcing admin authentication in secured mode.
- **FR-030**: System MUST provide REST API endpoints for creating, listing, and revoking API keys, with the initial admin key bootstrapped via the `OSR_ADMIN_KEY` environment variable or auto-generated on first startup.
- **FR-031**: System MUST provide an in-process embedded library interface (`SkillRegistry` / `AsyncSkillRegistry`) that can be instantiated directly in Python applications by providing a database connection and embedding configuration, bypassing HTTP networking entirely.
- **FR-032**: System MUST provide a single unified configuration file (`osr.config.yaml` / `.osr/config.yaml`) and corresponding Python schema (`RegistryConfig`) supporting pluggable vector storage and database backends, embedders, and optional cache layers for both embedded and hosted modes.
- **FR-033**: System MUST provide a hosted client interface (`SkillRegistryClient` / `AsyncSkillRegistryClient`) sharing a consistent operational API with the embedded engine, enabling developers to switch between embedded direct-to-infra and hosted server deployments with minimal code changes.
- **FR-034**: System MUST provide minimal CLI setup commands (`osr init`) to generate a ready-to-use configuration file with sensible defaults for instant zero-configuration startup.
- **FR-035**: System MUST implement a native Model Context Protocol (MCP) server supporting stdio and SSE transport for universal agent discovery and execution.
- **FR-036**: System MUST provide a Universal Install CLI (`osr install`) to inject skills into IDE environments like Cursor and Claude Code.
- **FR-037**: System MUST provide an Update and List CLI (`osr update`, `osr list`) for managing local IDE installed skills.
- **FR-038**: System MUST implement a Static Security Scanner during the publish workflow to detect prompt injection vectors.
- **FR-039**: System MUST implement a Static Security Scanner during the publish workflow to detect malicious shell scripts.
- **FR-040**: System MUST reject publish requests that fail security scanning with a CRITICAL safety score.
- **FR-041**: System MUST support direct Git Import (`osr import github:owner/repo`) for bulk extraction and publishing of skills from remote repositories.
- **FR-042**: System MUST provide Universal Adapters to convert loaded skills into LangChain tools or OpenAI function definitions (e.g., `as_langchain_tools()`).

### Key Entities

- **Namespace**: An organizational scope for grouping related skills (e.g., `google`, `myorg`, `public`). Has a visibility level (`PUBLIC`, `PRIVATE`, `NAMESPACE_ONLY`).
- **Skill**: A named capability within a namespace, identified by `{namespace}/{name}`. A skill has one or more versions, release tags, and visibility status.
- **Skill Version**: An immutable snapshot of a skill at a specific semantic version (e.g., `1.2.0`). Contains frontmatter metadata, instructions, a content manifest, resource files, and an immutable compliance snapshot.
- **Resource**: An individual file within a skill version, organized into `references/`, `assets/`, or `scripts/` directories. Identified by path and SHA256 content hash.
- **Release Tag**: A mutable named pointer (e.g., `latest`, `production`) that references a specific skill version. Can be moved between versions.
- **API Key**: An authentication credential optionally scoped to a namespace, used for write operations in secured mode.
- **Manifest**: A content-addressed index listing all files, their relative paths, sizes, and SHA-256 hashes within a skill version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Skill discovery returns ranked results for natural language queries within 2 seconds for registries containing up to 1,000 skills.
- **SC-002**: A developer can validate, package, and publish a new skill from a local directory in under 30 seconds (excluding network transfer time).
- **SC-003**: An ADK agent can search for and load a skill within a single conversation turn without manual intervention.
- **SC-004**: The registry starts and serves requests within 10 seconds from a cold Docker Compose startup (excluding database initialization).
- **SC-005**: Switching from `GCPSkillRegistry` to `OpenSkillRegistry` in an existing ADK agent requires changing no more than 3 lines of code.
- **SC-006**: The system remains functional (search and retrieval) when Redis is unavailable, with graceful degradation.
- **SC-007**: The system delivers high-precision hybrid discovery out of the box with zero external API keys using the default local ONNX embedding model (`fastembed`), while maintaining optimal syntactic search discovery when semantic search is disabled (`provider: none`).
- **SC-008**: Published skill versions are verifiable against their content hash, ensuring bit-for-bit integrity.
- **SC-009**: 100% of published packages containing path traversal attempts (`../`) or disallowed binary extensions are rejected prior to persistence.
- **SC-010**: Private or namespace-scoped skills are never returned in search results to clients lacking the corresponding namespace access credentials.
- **SC-011**: An agent developer can initialize `SkillRegistry` as an in-process library with their own database configuration and execute publish, search, and get operations without running any background server process or network ports.
- **SC-012**: A developer can initialize a new registry configuration in under 5 seconds using `osr init` and launch either an embedded library instance or self-hosted server with zero additional configuration.

## Assumptions

- Users may use Open Skill Registry in either **Hosted Server Mode** (Docker Compose with PostgreSQL, Redis, FastAPI, Web UI) or **Embedded Library Mode** (direct Python import connecting to user's database and vector infrastructure).
- The primary consumer of the registry is Google ADK Python agents (v2.9.2+); TypeScript, Go, Java, and Kotlin SDK adapters can consume the standard REST API in hosted mode.
- Skill packages are small (typically under 1MB total) and can be stored entirely in the database without performance issues.
- Semantic search is enabled by default using the lightweight local ONNX model (`fastembed` with `BAAI/bge-small-en-v1.5`), requiring zero external API keys. Users can customize options or switch to Gemini, OpenAI, Ollama, or `none` in `osr.config.yaml`.
- A single unified configuration file (`osr.config.yaml`) configures both library and server runtimes, generated with minimal setup via `osr init`.
- A built-in lightweight Web UI is included in hosted mode for catalog search, viewing, and drag-and-drop uploads; complex OAuth2/OIDC SSO and enterprise analytics dashboards are planned for v2.
- The `public` namespace is the default namespace for skills published without explicit namespace scoping.
- In secured hosted mode (`AUTH_ENABLED=true`), the initial admin API key is bootstrapped via the `OSR_ADMIN_KEY` environment variable or auto-generated on first startup. Stars/favorites are deferred to v2.

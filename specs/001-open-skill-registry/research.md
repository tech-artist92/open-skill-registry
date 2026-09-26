# Phase 0 Research: Open Skill Registry

**Feature**: Open Skill Registry  
**Branch**: `001-open-skill-registry`  
**Date**: 2026-09-26  
**License**: Apache-2.0  

## Summary of Decisions

| Area | Decision | Rationale | Alternatives Considered |
|---|---|---|---|
| **Backend Framework** | **FastAPI (Python 3.11+)** with Pydantic v2 and AsyncIO | Native alignment with the AI/agent ecosystem, auto-generated OpenAPI schemas, high async I/O performance for streaming and search, seamless code sharing with ADK Python SDK. | Go (Gin/Echo): lower memory but harder for AI ecosystem contributors; Node/NestJS: good async but requires separate Python ecosystem tooling. |
| **Persistence & Vector Storage** | **PostgreSQL 16 + pgvector** (SQLAlchemy async + asyncpg) | Unified single transactional data store for structured entities (namespaces, skills, tags), JSONB manifests, raw file contents (BYTEA/TEXT), and vector embeddings with IVFFlat/HNSW indexes. Eliminates external S3/MinIO and vector DB dependencies. | Separate S3/MinIO: adds operational friction and coordination complexity; Qdrant/Chroma: adds extra microservice dependency when pgvector suffices for <100k skills. |
| **Syntactic & Keyword Search** | **PostgreSQL `tsvector` with heavily weighted GIN index** | First-class search mechanism prioritizing skill Name/Slug (Weight A: 1.0) and Description (Weight B: 0.4), with tags and instructions. Delivers exceptional, highly relevant skill discovery out of the box with zero external AI models or embedding API costs. | Elasticsearch/Meilisearch: operational overhead; raw SQL LIKE: unscalable and lacks relevance ranking. |
| **High-Performance Caching** | **Redis with ETag (HTTP 304) revalidation & TTL fallback** | Sub-millisecond latency for hot skill frontmatters and search queries; clients send `If-None-Match: <content_hash>` avoiding redundant network payload transfers. Gracefully degrades to direct PostgreSQL if Redis is down. | In-memory only cache: lacks multi-worker shared state; No cache: introduces unnecessary DB load during agent query loops. |
| **Embeddings & Vector Generation** | **Semantic Search ON by default with Local FastEmbed ONNX Model** (`BAAI/bge-small-en-v1.5`, 384-dim) | Out-of-the-box semantic discovery with zero external API keys and zero GPU requirement using CPU-optimized ONNX runtime. Highly pluggable: users can configure Gemini, OpenAI, Ollama, HuggingFace, or set `provider: none` to rely exclusively on weighted syntactic search. | Cloud-only embeddings (Gemini/OpenAI): forces API key setup and creates cost/network failure modes; Pure keyword-only default: misses semantic intent for natural language queries. |
| **Publishing & Packaging** | **Flexible Multi-Format Publishing** (Standalone `SKILL.md`, raw folder multi-file upload, batch folder imports, and optional `.zip`/`.tar.gz`) | Minimizes friction by allowing developers to push single files or directories directly from CLI or Web UI without requiring manual archive creation, while still supporting zip packages when convenient. | Strict `.tar.gz` only: adds unnecessary friction for quick skill authoring; JSON-only Base64: inefficient for binary assets. |
| **Content Addressing & Integrity** | **Content-Addressed SHA-256 Manifest** | Every version computes a deterministic SHA-256 digest over sorted file paths and individual file hashes. Guarantees tamper-detection, bit-for-bit reproducibility, and powers `/resolve?hash=...`. | Git commit hashes: requires git repo dependency; Arbitrary UUIDs: cannot verify byte-level file integrity. |
| **ADK Client Integration** | **Drop-in `OpenSkillRegistry` Python Adapter** | Implements the identical protocol expected by Google ADK's `SkillToolset` (`async search_skills(query: str)` and `async get_skill(name: str)`), allowing existing ADK agents to switch from `GCPSkillRegistry` in 3 lines of code. | Generic HTTP client: forces developers to write boilerplate wrapper code; Forked ADK: creates long-term maintenance divergence. |
| **Web UI** | **Built-in FastAPI-served Lightweight Web Interface** | HTML5 + Tailwind CSS + Vanilla JS mounted directly on the registry server (`/`), featuring visual skill catalog browsing, markdown instruction rendering, search bar, and drag-and-drop file/folder/zip uploading. Zero separate container overhead. | Standalone React/Node SPA: requires separate build, deployment container, and reverse proxy setup for v1; No UI: leaves non-terminal users without access. |
| **Auth & Governance** | **Dual-Mode (Open by default, API Key + Namespace in secured mode)** | Open mode allows instant zero-config local prototyping; setting `AUTH_ENABLED=true` enforces API key authentication on writes, with namespace scoping and visibility levels (`PUBLIC`, `NAMESPACE_ONLY`, `PRIVATE`). | Full OAuth2/OIDC SSO in v1: too complex for initial release; No auth ever: unsuited for enterprise deployments. |
| **Delivery Model** | **Dual Delivery (Embedded Library `SkillRegistry` + Hosted Server `SkillRegistryClient`)** | Inspired by Mem0: developers can either `from open_skill_registry import SkillRegistry` and connect directly to their own PostgreSQL/pgvector or vector store with zero network hops, or run the hosted FastAPI server and connect via `SkillRegistryClient`. Same high-level API across both. | Hosted-only: forces every user to run and maintain a network server even for simple agent apps; Library-only: cannot provide multi-tenant team governance, Web UI, or cross-language HTTP API. |
| **Configuration & Setup** | **Single Unified Config File (`osr.config.yaml`) & 2-Step Setup** (`pip install open-skill-registry && osr init`) | Delivers an effortless user setup experience. A single well-commented YAML file configures embedded vs server mode, storage, database, cache, and search/embedding options. Command `osr init` generates this config in 1 second. | Multiple fragmented config files (.env, toml, json): confusing for users; Complex multi-step manual setup: slows down adoption. |

---

## Technical Deep-Dives

### 1. Dual Delivery Model (Embedded Library vs Hosted Server)
- **Embedded Engine (`SkillRegistry` / `AsyncSkillRegistry`)**:
  - Direct in-process execution without HTTP overhead.
  - Takes a `RegistryConfig` (or loads `osr.config.yaml`) specifying database URL, embedding provider, and optional cache.
  - Implements the complete skill lifecycle: `publish()`, `search()`, `get()`, `resolve()`, `tag()`, `yank()`.
  - Can be wrapped directly as an ADK `SkillToolset` registry via `.to_adk()` or `OpenSkillRegistry(registry=embedded_reg)`.
- **Hosted Server & Client (`open_skill_registry.server` + `SkillRegistryClient`)**:
  - FastAPI server wraps the exact same core services (`SkillService`, `SearchService`, `EmbeddingService`).
  - `SkillRegistryClient` / `AsyncSkillRegistryClient` provides a thin HTTP client with identical methods as `SkillRegistry`.
  - Both modes share identical models, DTOs, manifest algorithms, and validation rules.

### 2. High-Precision Hybrid Search Strategy (Default Local ONNX Embeddings + Weighted Syntactic)
- **Default Local Embedder (FastEmbed ONNX Runtime)**:
  - Enabled by default using `BAAI/bge-small-en-v1.5` (384 dimensions).
  - Runs in-process via ONNX Runtime without PyTorch, CUDA, or external network requests.
  - Zero API key required, zero API costs, instant out-of-the-box semantic search.
- **Pluggable Embedding Providers**:
  - Users can configure their preferred provider in `osr.config.yaml`:
    - `fastembed` (default, local ONNX, 384-dim)
    - `gemini` (`text-embedding-004`, 768-dim)
    - `openai` (`text-embedding-3-small`, 1536-dim)
    - `ollama` (`nomic-embed-text`, 768-dim)
    - `huggingface` (sentence-transformers)
    - `none` (disables semantic search completely)
- **Weighted Syntactic Search (Cover Density tsvector)**:
  - PostgreSQL tsvector heavily prioritizes Name/Slug (Weight A: 1.0) and Description (Weight B: 0.4), with Tags and Instructions as secondary context.
  - Evaluates queries using `plainto_tsquery('english', query)` with `ts_rank_cd(tsv, query, 32)`.
  - When semantic search is enabled, Reciprocal Rank Fusion (RRF) blends syntactic and vector ranks: `RRF_score = 1/(60 + rank_syntactic) + 1/(60 + rank_semantic)`.
  - When `provider: none` or embedding model fails, search gracefully falls back to weighted syntactic ranking with zero error.
- **Visibility Filter**: All search queries include an automatic security clause (`visibility = 'PUBLIC' OR namespace_id IN (:user_namespaces)`), preventing private skill leakage.

### 3. Packaging & Manifest Computation
- **File Normalization**: Incoming files are checked against allowed extensions: `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.py`, `.sh`, `.ts`, `.js`, `.png`, `.jpg`, `.svg`.
- **Security Check**: Path traversal attempts (e.g., paths containing `../` or starting with `/`) are rejected immediately with HTTP 400.
- **Manifest Generation**:
  ```json
  {
    "schema_version": "1.0",
    "name": "bigquery-optimizer",
    "namespace": "google",
    "version": "1.2.0",
    "content_hash": "sha256:4d6a...",
    "files": [
      {"path": "SKILL.md", "hash": "sha256:7c9e...", "size": 2048},
      {"path": "references/guide.md", "hash": "sha256:a1f3...", "size": 4096}
    ]
  }
  ```
- **Content Hash**: `SHA256(canonical_json(manifest))` becomes the version's immutable identifier.

### 4. ADK Compatibility Protocol
- **L1 Frontmatter**: `search_skills()` returns `list[Frontmatter]`. Only `name`, `description`, and essential tags are returned.
- **L2 Instructions**: `get_skill()` fetches version metadata and body instructions, constructing an ADK `Skill` object.
- **L3 Resources**: Resources are loaded lazily: the `Skill` object provides a resource loader that calls `GET /api/v1/skills/{ns}/{slug}/versions/{ver}/file?path={relpath}` on-demand.

### 5. Unified Configuration & Minimal Setup Architecture
- **Single Configuration File (`osr.config.yaml`)**:
  - Unifies configuration across all components: embedded library, hosted server, database, vector storage, caching, and search/embeddings.
  - Hierarchical structure with environment variable expansion (`${VAR:-default}`).
  - Validated on load via Pydantic v2 `RegistryConfig` model.
- **Minimal Setup Flow**:
  1. `pip install open-skill-registry` (includes FastEmbed and ONNX runtime out of the box).
  2. `osr init` creates a clean, well-commented `osr.config.yaml` in the current project or `~/.osr/`.
  3. Execution requires zero extra configuration:
     - Embedded: `from open_skill_registry import SkillRegistry; reg = SkillRegistry()`
     - Server: `osr serve` or `docker compose up -d`.


# Implementation Plan: Open Skill Registry

**Branch**: `001-open-skill-registry` | **Date**: 2026-09-26 | **License**: Apache-2.0 | **Spec**: [`spec.md`](./spec.md)

**Input**: Feature specification from [`spec.md`](./spec.md)

---

## Summary

Open Skill Registry is an open-source skill registry ecosystem for discovering, distributing, and dynamically loading AI agent skills, designed with a **dual delivery architecture** (inspired by Mem0):
1. **Embedded Library Mode (`SkillRegistry` / `AsyncSkillRegistry`)**: In-process Python engine that connects directly to the developer's infrastructure (PostgreSQL/pgvector, local SQLite, pluggable embeddings) without requiring an HTTP server, with zero network overhead.
2. **Hosted Server & Client Mode (`open_skill_registry.server` + `SkillRegistryClient`)**: Self-hostable FastAPI server with Web UI, REST API, Redis caching, multi-tier visibility (`PUBLIC`, `NAMESPACE_ONLY`, `PRIVATE`), and a drop-in HTTP client sharing identical operational semantics.

Both modes share the identical core engine (`SkillService`, `SearchService`, `EmbeddingService`), content-addressed storage (SHA-256 manifests), and 100% Google ADK 2.9.2+ `SkillToolset` compatibility. The ecosystem also features a native MCP Server (SEP-2640), a Security Scanner, and a Universal Installer.

---

## Technical Context

**Language/Version**: Python 3.11+ (leveraging modern typing, AsyncIO, and Pydantic v2).

**Primary Dependencies**:
- Web & API: `fastapi>=0.115.0`, `uvicorn>=0.30.0`, `pydantic>=2.8.0`, `python-multipart>=0.0.9`, `mcp>=1.0.0` (for MCP server).
- Database & ORM: `sqlalchemy[asyncio]>=2.0.30`, `sqlmodel>=0.0.21`, `asyncpg>=0.29.0`, `pgvector>=0.3.0`, `alembic>=1.13.0`.
- Configuration: `pyyaml>=6.0.1`.
- Cache: `redis[hiredis]>=5.0.0` (optional in embedded mode).
- CLI: `typer>=0.12.0`, `rich>=13.7.0`, `httpx>=0.27.0`.
- Embeddings & Math: `fastembed>=0.3.0` (default local ONNX embedder, 0 API keys required), `numpy>=1.24.0` (in-process vector cosine similarity), plus pluggable (`google-genai` / `openai` / `ollama` / `sentence-transformers` / none).

**Storage**: PostgreSQL 16 with `pgvector` extension (single transactional store for metadata, manifests, vector embeddings, and file contents) + Redis 7 for high-speed caching in hosted mode; or SQLite 3 / PostgreSQL in embedded mode.

**Testing**: `pytest`, `pytest-asyncio`, `testcontainers[postgres,redis]`, `respx` (for HTTP mocking), `httpx.AsyncClient`, MCP protocol tests, and security AST/Regex tests.

**Target Platform**: Multi-platform (macOS, Linux, Docker containerized environment, Kubernetes, embedded in Python processes).

**Project Type**: Multi-component Python package providing:
1. Embedded in-process library engine (`open_skill_registry.SkillRegistry`).
2. Hosted REST API & Web UI server (`open_skill_registry.server`).
3. Hosted API client (`open_skill_registry.SkillRegistryClient`).
4. CLI developer utility (`osr`).
5. Google ADK Python SDK adapter (`open_skill_registry.adk.OpenSkillRegistry`).

**Performance Goals**:
- In-process library search & retrieval: < 50ms p95.
- Hosted semantic and keyword search discovery: < 2 seconds p95 for catalogs up to 1,000 skills.
- Frontmatter retrieval (cached with ETag): < 20ms p95.
- Cold container boot time: < 10 seconds.

**Constraints**:
- Low friction: No mandatory zip packaging; accepts raw files and folders directly.
- Strict security: Package traversal prevention (`../`), 1MB per-file limit, 10MB package limit, file type allowlist.
- Zero data leakage: Private and namespace-scoped skills strictly excluded from unauthorized search results.

**Scale/Scope**: v1 supports both embedded in-process agent execution and self-hosted enterprise/team deployments managing 1,000+ skills with high concurrency.

---

## Coding Paradigm: LLM-Optimized Vibe Coding

To maximize development velocity, maintainability, and predictability when coding with AI agents ("vibe coding"), this project enforces a **Functional and Declarative** programming paradigm:
- **Functional Core, Imperative Shell**: Core business logic (manifest hashing, payload validation, search ranking, skill resolution, security AST scanning) is implemented strictly as pure, side-effect-free functions. Database operations, network IO, and CLI printing are pushed to thin outer layers (the imperative shell).
- **Declarative Data Flow**: Heavy reliance on Pydantic models for declarative data validation and immutability. Classes are only used for dependency injection or Pydantic schemas, not for encapsulating complex mutating state.
- **Test-Driven Predictability**: Pure functions make writing deterministic unit tests trivial. LLM agents must write comprehensive unit tests *before* writing the implementation. This provides a high-quality feedback loop that allows the LLM to verify its own logic reliably.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Library-First**: The core registry is implemented as an importable in-process Python library (`SkillRegistry`) completely decoupled from HTTP frameworks. The ADK adapter (`OpenSkillRegistry`) and the hosted server (`open_skill_registry.server`) both layer directly on top of this core library. **PASS**
- **Principle II: CLI Interface & Multi-Client Protocol**: The `osr` CLI exposes full functionality (`init`, `serve`, `login`, `search`, `push`, `pull`, `info`, `tag`, `yank`, `verify`, `namespace`) with both human-readable table outputs and `--format json` support. **PASS**
- **Principle III: Test-First (TDD)**: Test suites are structured across unit tests (manifest hashing, validation, library engine), integration tests (pgvector, sqlite in-memory, redis caching), and contract tests (OpenAPI endpoints, ADK protocol). **PASS**
- **Principle IV: Superior Hybrid Discovery with Zero-Config Local Embeddings**: Semantic search is enabled by default via FastEmbed local ONNX runtime (`BAAI/bge-small-en-v1.5`, 384-dim, 0 API keys) blended with PostgreSQL/SQLite weighted full-text search (Name/Slug: 1.0, Description: 0.4 via `ts_rank_cd`). **PASS**
- **Principle V: Simplicity, Transparency & YAGNI**: Dual database drivers (SQLite for zero-ops local, PostgreSQL for hosted) eliminate external object store (S3/MinIO) complexity; single unified configuration file (`osr.config.yaml`); built-in FastAPI Web UI eliminates separate frontend container build pipelines for v1. **PASS**

---

## Project Structure

### Documentation (this feature)

```text
specs/001-open-skill-registry/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 architectural decisions & technical context
├── data-model.md        # Phase 1 database schema and entity specifications
├── quickstart.md        # Phase 1 end-to-end validation guide
├── contracts/           # Phase 1 interface contracts
│   ├── api-contract.md  # REST API specification
│   ├── cli-contract.md  # CLI command specification
│   └── adk-contract.md  # ADK Python SDK specification
└── checklists/
    └── requirements.md  # Quality validation checklist
```

### Source Code Layout

```text
open-skill-registry/
├── pyproject.toml                     # Unified package with [cli], [server], [all] extras
├── osr.config.yaml                    # Single unified configuration template
├── Dockerfile                         # Production server container image
├── docker-compose.yml                 # Local development orchestration (server, pgvector, redis)
├── src/
│   └── open_skill_registry/
│       ├── __init__.py                # Root exports: SkillRegistry, SkillRegistryClient, OpenSkillRegistry
│       ├── config.py                  # RegistryConfig loader (loads osr.config.yaml, env vars, or dict)
│       ├── registry/                  # Embedded in-process library engine (direct-to-infra)
│       │   ├── __init__.py
│       │   ├── main.py                # SkillRegistry & AsyncSkillRegistry classes
│       │   ├── storage/               # Pluggable storage & vector backend interfaces
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # Base storage provider contract
│       │   │   └── pgvector.py        # PostgreSQL + pgvector + tsvector backend
│       │   ├── embeddings/            # Pluggable vector embedding providers
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # Base embedder contract
│       │   │   ├── fastembed.py       # Default local ONNX embedding provider (BAAI/bge-small-en-v1.5)
│       │   │   ├── gemini.py          # Gemini embedding provider
│       │   │   ├── openai.py          # OpenAI embedding provider
│       │   │   ├── ollama.py          # Ollama embedding provider
│       │   │   └── huggingface.py     # Sentence-transformers / HuggingFace provider
│       │   └── core/                  # Pure manifest, hashing, validation logic
│       │       ├── __init__.py
│       │       ├── manifest.py        # Content-addressed SHA-256 manifest engine
│       │       └── validator.py       # Package safety, allowlist & size checks
│       ├── client/                    # Hosted registry HTTP client (Mem0 MemoryClient pattern)
│       │   ├── __init__.py
│       │   └── main.py                # SkillRegistryClient & AsyncSkillRegistryClient
│       ├── adk.py                     # Google ADK drop-in SkillToolset registry adapter
│       ├── models/                    # Shared Pydantic data schemas
│       │   ├── __init__.py
│       │   ├── manifest.py            # Manifest & file hashing models
│       │   ├── skill.py               # Frontmatter, version, and skill DTOs
│       │   └── response.py            # Unified response envelope
│       ├── server/                    # FastAPI registry server (wraps core engine)
│       │   ├── __init__.py
│       │   ├── app.py                 # FastAPI application factory
│       │   ├── config.py              # Server settings & environment parsing
│       │   ├── db/
│       │   │   ├── __init__.py
│       │   │   ├── session.py         # Async database session management
│       │   │   ├── models.py          # SQLModel / SQLAlchemy ORM entities
│       │   │   └── migrations/        # Alembic schema migrations
│       │   ├── services/              # Server service wrappers over registry core
│       │   │   ├── __init__.py
│       │   │   ├── skill_service.py   # Skill lifecycle & ingestion
│       │   │   ├── search_service.py  # Hybrid pgvector + tsvector query execution
│       │   │   └── cache_service.py   # Redis caching & ETag computation
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── skills.py          # Skill search, CRUD, resolve, file streaming
│       │   │   ├── namespaces.py      # Namespace CRUD
│       │   │   ├── auth.py            # API key issuance and validation
│       │   │   └── health.py          # System health check
│       │   ├── static/                # Built-in lightweight Web UI
│       │   │   ├── index.html         # Catalog view & drag-and-drop uploader
│       │   │   ├── app.js             # Client-side search and upload logic
│       │   │   └── styles.css         # Modern clean interface styles
│       │   └── middleware/
│       │       └── auth.py            # API key & namespace authentication middleware
│       └── cli/                       # Typer-based developer CLI
│           ├── __init__.py
│           ├── main.py                # CLI entry point
│           ├── config.py              # Configuration loader (osr.config.yaml / ~/.osr/config.toml)
│           └── commands/
│               ├── init.py            # Scaffolds ready-to-use osr.config.yaml
│               ├── serve.py           # Starts registry server locally
│               ├── login.py
│               ├── push.py            # Flexible upload (file, folder, batch, zip)
│               ├── pull.py            # Download and verification
│               ├── search.py          # Search display
│               ├── info.py            # Skill metadata display
│               ├── tag.py             # Tag management
│               ├── yank.py            # Version deprecation
│               ├── verify.py          # Local checksum verification
│               └── namespace.py       # Namespace management
└── tests/
    ├── unit/                          # Schema, validation, manifest tests
    ├── integration/                   # Real PostgreSQL + Redis tests
    ├── contract/                      # REST API OpenAPI compliance tests
    └── adk/                           # ADK SkillToolset integration tests
```

### Database Migration Strategy

- **Initial Migration**: A single Alembic migration creates all 7 tables (`namespaces`, `skills`, `skill_versions`, `skill_resources`, `skill_embeddings`, `release_tags`, `api_keys`) with indexes, constraints, and the `public` namespace seed.
- **Auto-Generation**: Migrations are auto-generated from SQLModel/SQLAlchemy ORM model changes using `alembic revision --autogenerate`.
- **pgvector Extension**: The initial migration includes `CREATE EXTENSION IF NOT EXISTS vector` to enable pgvector.

### Unified Configuration & Minimal Setup Workflow

- **Single Configuration File (`osr.config.yaml`)**:
  Both the embedded library (`SkillRegistry`) and the hosted server (`open_skill_registry.server`) read from a single canonical configuration file:
  ```yaml
  version: "1.0"
  mode: "embedded" # "embedded" or "server"

  database:
    driver: "sqlite" # "sqlite" or "postgres"
    url: "sqlite:///~/.osr/registry.db" # or postgresql+asyncpg://user:pass@localhost:5432/skills

  search:
    semantic_enabled: true  # ON by default
    provider: "fastembed"   # default local ONNX model, zero API keys
    model: "BAAI/bge-small-en-v1.5"
    dimension: 384
    syntactic_weight: 0.3
    semantic_weight: 0.7

  storage:
    driver: "local"
    local_path: "~/.osr/storage"

  server:
    host: "0.0.0.0"
    port: 8080
    auth_enabled: false
  ```
- **Minimal User Setup**:
  1. `pip install open-skill-registry`
  2. `osr init` (generates commented `osr.config.yaml` with zero-config defaults)
  3. Start using:
     - Embedded: `from open_skill_registry import SkillRegistry; reg = SkillRegistry()`
     - Server: `osr serve` or `docker compose up -d`

---

## Complexity Tracking

| Mechanism | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Default Local ONNX FastEmbed + Weighted tsvector | Delivers out-of-the-box semantic search with zero API keys or external GPU, backed by weighted tsvector (Name/Slug: 1.0, Description: 0.4) for high-precision hybrid discovery | Cloud-only embeddings force mandatory API keys and create network failure points; keyword-only search misses semantic synonym queries. |
| Redis cache | Required for sub-20ms frontmatter retrieval during high-frequency agent tool evaluation | Direct database queries on every agent prompt evaluation create DB bottlenecks under load. |
| Content-addressed SHA-256 manifest | Required for deterministic version immutability and client-side tamper verification | Timestamp or sequential IDs cannot verify bit-for-bit file integrity. |
| Single `osr.config.yaml` file | Unifies library and server configuration in one intuitive, declarative place | Fragmented environment variables and multiple disjoint config files increase cognitive friction. |

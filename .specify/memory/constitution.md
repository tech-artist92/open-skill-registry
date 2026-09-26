# Open Skill Registry Constitution

## Core Principles

### Principle I: Library-First Architecture
Every capability is first implemented as a clean, in-process, self-contained Python library (`SkillRegistry`) completely decoupled from HTTP frameworks. The hosted microservice server (`open_skill_registry.server`) and the Google ADK adapter (`OpenSkillRegistry`) are thin layers over this core library engine.

### Principle II: CLI Interface & Multi-Client Protocol
Every feature exposes direct functionality via the `osr` CLI. Commands accept standard arguments/stdin, output formatted human-readable text or structured JSON (`--format json`), and provide exit codes for automation scripts and diverse agent runtimes.

### Principle III: Test-First & Deterministic Verification
Test-Driven Development (TDD) is standard: unit, integration, and contract tests are maintained for all endpoints, schemas, and packaging pipelines. Published skills are content-addressed and verified via cryptographic SHA-256 manifests.

### Principle IV: Superior Hybrid Discovery with Zero-Config Local Embeddings
Skill discovery is the central user experience. Semantic search is enabled by default via a built-in lightweight local ONNX embedding engine (FastEmbed, requiring zero API keys and zero cost), blended with high-precision weighted syntactic search (prioritizing Name/Slug at 1.0 and Description at 0.4 via `ts_rank_cd`). Users can plug in alternative providers (Gemini, OpenAI, Ollama) or disable semantic search (`none`) via `osr.config.yaml` without functional degradation.

### Principle V: Simplicity, Transparency & YAGNI
Direct database storage (SQLite for zero-ops local, PostgreSQL for hosted) eliminates external object store (S3/MinIO) complexity. A single unified configuration file (`osr.config.yaml`) and built-in lightweight Web UI eliminate separate configuration silos and frontend container build pipelines for v1. Unnecessary services or premature abstractions are rejected.
### Principle VI: Universal Interoperability & Trust
The registry acts as a universal bridge for all agent ecosystems, with native Model Context Protocol (MCP) support (SEP-2640) for runtime interoperability, and direct IDE workspace integration (`.cursor/skills/`, `.claude/skills/`). Security is non-negotiable: all published skills undergo static security scanning for prompt-injection and malicious scripts. Direct Git imports enable seamless sourcing from external repositories.

### Principle VII: LLM-Optimized Vibe Coding (Functional & Declarative)
To maximize development velocity and reliability when coding with LLMs ("vibe coding"), the codebase strictly adheres to a functional and declarative paradigm. Complex state mutations, deeply nested class hierarchies, and hidden side effects are explicitly rejected in favor of the "Functional Core, Imperative Shell" pattern. Core logic (hashing, validation, search, parsing) is built as pure, easily-testable functions operating on immutable declarative data structures (Pydantic). LLM agents must write comprehensive tests *before* implementation, using pure functions to ensure predictable, deterministic behavior.

## Licensing & Governance

- **License**: Apache License, Version 2.0 (permissive open-source for community and enterprise use).
- **Compliance**: All contributions and published packages adhere to the Apache 2.0 terms and Agent Skills Specification.

**Version**: 1.0.0 | **Ratified**: 2026-09-26 | **Status**: Active

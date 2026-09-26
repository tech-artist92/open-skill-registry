# Open Skill Registry Constitution

## Core Principles

### Principle I: Library-First Architecture
Every capability is first implemented as a clean, in-process, self-contained Python library (`SkillRegistry`) completely decoupled from HTTP frameworks. The hosted microservice server (`open_skill_registry.server`) and the Google ADK adapter (`OpenSkillRegistry`) are thin layers over this core library engine.

### Principle II: CLI Interface & Multi-Client Protocol
Every feature exposes direct functionality via the `osr` CLI. Commands accept standard arguments/stdin, output formatted human-readable text or structured JSON (`--format json`), and provide exit codes for automation scripts and diverse agent runtimes.

### Principle III: Test-First & Deterministic Verification
Test-Driven Development (TDD) is standard: unit, integration, and contract tests are maintained for all endpoints, schemas, and packaging pipelines. Published skills are content-addressed and verified via cryptographic SHA-256 manifests.

### Principle IV: Superior Discovery with Zero-Friction Syntactic Search
Skill discovery is the central user experience. High-precision syntactic search (heavily weighting Name/Slug at 1.0 and Description at 0.4 via `ts_rank_cd`) is a first-class citizen operating out of the box with zero external AI model requirements or API costs. Vector embeddings are an optional layered enhancement.

### Principle V: Simplicity, Transparency & YAGNI
Direct database storage eliminates external object store (S3/MinIO) complexity. A built-in lightweight Web UI eliminates separate frontend container build pipelines for v1. Unnecessary services or premature abstractions are rejected.

## Licensing & Governance

- **License**: Apache License, Version 2.0 (permissive open-source for community and enterprise use).
- **Compliance**: All contributions and published packages adhere to the Apache 2.0 terms and Agent Skills Specification.

**Version**: 1.0.0 | **Ratified**: 2026-09-26 | **Status**: Active

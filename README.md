# Open Skill Registry

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![ADK Compatible](https://img.shields.io/badge/Google_ADK-2.9.2%2B-green)](https://github.com/google/adk)

Open Skill Registry is an open-source, high-performance skill registry ecosystem for discovering, distributing, and dynamically loading AI agent skills. Built for seamless compatibility with **Google ADK 2.9.2+ `SkillToolset`** and enterprise governance.

---

## 🌟 Dual Delivery Architecture

Open Skill Registry supports two distinct execution modes out of the box (inspired by modern AI frameworks like Mem0):

1. **Embedded Library Mode (`SkillRegistry`)**:
   - In-process Python engine connecting directly to your database (PostgreSQL + pgvector or local SQLite).
   - Zero network overhead, zero HTTP servers to deploy or manage.
   - Ideal for single-agent apps, local pipelines, and zero-ops setups.
2. **Hosted Server Mode (`open_skill_registry.server` + `SkillRegistryClient`)**:
   - Centralized FastAPI server with REST API, Web UI, Redis caching, multi-tenant namespaces, and token scoping.
   - Ideal for engineering teams, shared organizational registries, and multi-agent microservice architectures.

---

## ⚡ Minimal 2-Step Setup

Get up and running in under 60 seconds:

```bash
# Step 1: Install
pip install open-skill-registry

# Step 2: Initialize configuration
osr init
```

This generates a ready-to-use `osr.config.yaml` file with semantic search **enabled by default** using an embedded local ONNX model (`BAAI/bge-small-en-v1.5`), requiring **zero API keys** and zero external GPU!

---

## ⚙️ Single Unified Configuration (`osr.config.yaml`)

Both the embedded Python library and the hosted server read from a single, intuitive config file:

```yaml
version: "1.0"
mode: "embedded" # "embedded" or "server"

database:
  driver: "sqlite" # "sqlite" (default embedded) or "postgres" (hosted)
  url: "sqlite:///~/.osr/registry.db"

search:
  semantic_enabled: true  # ON by default
  provider: "fastembed"   # default local ONNX model, zero external API keys
  model: "BAAI/bge-small-en-v1.5"
  dimension: 384
  syntactic_weight: 0.3
  semantic_weight: 0.7
  # Configurable options:
  # provider: "gemini"     # model: "text-embedding-004", api_key: "${GEMINI_API_KEY}"
  # provider: "openai"     # model: "text-embedding-3-small", api_key: "${OPENAI_API_KEY}"
  # provider: "ollama"     # base_url: "http://localhost:11434", model: "nomic-embed-text"
  # provider: "none"       # disables semantic search; uses weighted keyword search

storage:
  driver: "local"
  local_path: "~/.osr/storage"

server:
  host: "0.0.0.0"
  port: 8080
  auth_enabled: false
```

---

## 🔍 Superior Skill Discovery

- **Semantic Search ON by Default**:
  - Embedded local ONNX runtime via FastEmbed (`BAAI/bge-small-en-v1.5`, 384 dimensions).
  - Runs in-process with 0 external API keys, 0 network latency, and 0 external costs.
- **Heavily Weighted Syntactic Search**:
  - PostgreSQL tsvector cover density with primary priority on **Skill Name/Slug (Weight A: 1.0)** and **Description (Weight B: 0.4)**.
  - Hybrid search combines semantic similarity and weighted keywords via Reciprocal Rank Fusion (RRF).
- **Pluggable & Fully Configurable**:
  - Easily switch to Gemini, OpenAI, Ollama, HuggingFace, or disable semantic search (`provider: none`) in `osr.config.yaml`.

---

## 🚀 Usage

### 1. Embedded Library Usage (Zero Server)

```python
import asyncio
from open_skill_registry import SkillRegistry
from open_skill_registry.adk import OpenSkillRegistry
from google.adk.tools.skill_toolset import SkillToolset

async def main():
    # 1. Initialize embedded registry directly from osr.config.yaml
    # Semantic search is ON by default with local model
    registry = SkillRegistry.from_config("osr.config.yaml")
    await registry.initialize()

    # 2. Wire directly into Google ADK SkillToolset
    skill_toolset = SkillToolset(
        registry=OpenSkillRegistry(registry=registry),
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Hosted Server Usage

```bash
# Option A: Start using CLI
osr serve

# Option B: Start via Docker Compose (Server + PostgreSQL/pgvector + Redis)
docker compose up -d

# Verify health
curl http://localhost:8080/health

# Access Web UI at: http://localhost:8080/
```

---

## 📦 Documentation Suite

- **Specification**: [`specs/001-open-skill-registry/spec.md`](./specs/001-open-skill-registry/spec.md)
- **Implementation Plan**: [`specs/001-open-skill-registry/plan.md`](./specs/001-open-skill-registry/plan.md)
- **Tasks & Roadmap**: [`specs/001-open-skill-registry/tasks.md`](./specs/001-open-skill-registry/tasks.md)
- **Data Model**: [`specs/001-open-skill-registry/data-model.md`](./specs/001-open-skill-registry/data-model.md)
- **Research Decisions**: [`specs/001-open-skill-registry/research.md`](./specs/001-open-skill-registry/research.md)
- **Quickstart Guide**: [`specs/001-open-skill-registry/quickstart.md`](./specs/001-open-skill-registry/quickstart.md)
- **Contracts**:
  - [REST API Contract](specs/001-open-skill-registry/contracts/api-contract.md)
  - [CLI Contract](specs/001-open-skill-registry/contracts/cli-contract.md)
  - [Google ADK Integration Contract](specs/001-open-skill-registry/contracts/adk-contract.md)

---

## ⚖️ License

Licensed under the **Apache License, Version 2.0** (the "License"). You may obtain a copy of the License in the [LICENSE](./LICENSE) file or at:

[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)

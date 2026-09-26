# Quickstart & Validation Guide: Open Skill Registry

**Feature**: Open Skill Registry  
**Branch**: `001-open-skill-registry`  
**Date**: 2026-09-26  
**License**: Apache-2.0  

This guide provides end-to-end steps to run, validate, and verify the Open Skill Registry.

---

## 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose (for hosted server mode)
- `pip` or `uv`

---

## 2. Minimal Setup (Get Started in 60 Seconds)

### Step 1: Install Package
```bash
pip install open-skill-registry
# or with uv:
uv pip install open-skill-registry
```

### Step 2: Initialize Configuration
```bash
osr init
```
This generates `osr.config.yaml` with semantic search enabled out of the box using FastEmbed ONNX runtime (`BAAI/bge-small-en-v1.5`, zero API keys required).

### Step 3: Choose Your Runtime
- **Library Mode (In-Process)**: Use directly in Python with `SkillRegistry` — zero background processes!
- **Hosted Server Mode**: Run `osr serve` or `docker compose up -d`.

---

## 3. Embedded Library Validation Flow (Direct to Infrastructure)

No server or Docker background services required — connect directly to your database and embeddings in Python:

```python
import asyncio
from open_skill_registry import SkillRegistry, RegistryConfig

async def test_embedded():
    # 1. Initialize registry directly from osr.config.yaml (or passing config in code)
    # Default uses FastEmbed local model (zero API keys needed)
    registry = SkillRegistry.from_config("osr.config.yaml")
    await registry.initialize()

    # 2. Publish a skill directly in-process
    result = await registry.publish(
        path="./samples/weather-skill/SKILL.md",
        namespace="public",
        version="1.0.0",
    )
    print(f"Published in-process: {result.slug} (hash: {result.content_hash})")

    # 3. Direct semantic search with zero network hops
    matches = await registry.search(query="rainy day forecasts", limit=5)
    print("Found skills:", [m.slug for m in matches.items])
    assert len(matches.items) > 0

    # 4. Direct retrieval
    skill = await registry.get(namespace="public", slug="weather-lookup")
    print(f"Loaded instructions: {skill.instructions[:50]}...")

if __name__ == "__main__":
    asyncio.run(test_embedded())
```

---

## 4. Starting the Hosted Registry Locally

### Option 1: Via OSR CLI
```bash
osr serve --config osr.config.yaml
```

### Option 2: Via Docker Compose (Server + PostgreSQL + Redis)
```bash
# Start background services
docker compose up -d

# Verify services are healthy
curl http://localhost:8080/health
# Output: {"status": "ok", "db": "connected", "redis": "connected"}

# Web UI is now accessible in browser at:
# http://localhost:8080/
```

---

## 5. CLI Validation Flow

### Install and Configure CLI
```bash
pip install -e ".[cli]"

# Verify CLI connection
osr search "test"
```

### Publish Sample Skill
```bash
# 1. Create a minimal skill
mkdir -p ./samples/weather-skill
cat << 'EOF' > ./samples/weather-skill/SKILL.md
---
name: weather-lookup
description: Fetches real-time weather information for any city.
---
# Weather Lookup Instructions
Step 1: Check city name.
Step 2: Return simulated weather response.
EOF

# 2. Publish to registry
osr push ./samples/weather-skill --namespace public --version 1.0.0

# 3. Inspect published skill
osr info public/weather-lookup
```

### Semantic Search Validation
```bash
osr search "forecast for rainy day"
# Output shows 'weather-lookup' ranked at top with similarity score
```

### Content Integrity Verification
```bash
# Download to test dir
osr pull public/weather-lookup --version 1.0.0 --output ./downloaded-skills/

# Verify fingerprint
osr verify ./downloaded-skills/weather-lookup
# Output: [OK] All 1 file(s) match release SHA-256 manifest
```

### Single File Publish Validation
```bash
# Create and publish a standalone SKILL.md without a directory
cat << 'EOF' > ./samples/standalone-skill.md
---
name: quick-math
description: Performs quick arithmetic calculations.
version: 1.0.0
---
# Quick Math
Provide two numbers and an operation. Return the result.
EOF

osr push ./samples/standalone-skill.md --namespace public
# Verify it was published
osr info public/quick-math
```

### Batch Publish Validation
```bash
# Create a collection of skills
mkdir -p ./samples/batch-skills/skill-a ./samples/batch-skills/skill-b

cat << 'EOF' > ./samples/batch-skills/skill-a/SKILL.md
---
name: skill-a
description: First batch skill.
---
# Skill A Instructions
EOF

cat << 'EOF' > ./samples/batch-skills/skill-b/SKILL.md
---
name: skill-b
description: Second batch skill.
---
# Skill B Instructions
EOF

# Publish all skills at once
osr push ./samples/batch-skills/ --batch --namespace public

# Verify both were published
osr search "batch skill"
```

---

## 6. Web UI Validation Flow

1. Open `http://localhost:8080/` in your browser.
2. Verify the **Catalog View** displays `public/weather-lookup`.
3. Test search bar by typing `"weather"` or `"forecast"` and observing instant live search results.
4. Drag and drop a new standalone `SKILL.md` file onto the upload target and verify the skill is created and immediately searchable.

---

## 7. Google ADK Agent Dynamic Discovery Flow

### Mode A: In-Process Embedded Library Mode (Direct to DB, Zero HTTP)
```python
import asyncio
from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset
from open_skill_registry import SkillRegistry
from open_skill_registry.adk import OpenSkillRegistry

async def main():
    # Uses osr.config.yaml with default local FastEmbed semantic search
    embedded_registry = SkillRegistry.from_config("osr.config.yaml")
    await embedded_registry.initialize()

    registry = OpenSkillRegistry(registry=embedded_registry)
    
    # 1. Test search_skills
    matches = await registry.search_skills(query="what is the weather in Tokyo?")
    print("Found skills (embedded):", [m.name for m in matches])
    assert "weather-lookup" in [m.name for m in matches]

    # 2. Test get_skill
    skill = await registry.get_skill(name="public/weather-lookup")
    assert "Weather Lookup Instructions" in skill.instructions
    print("Embedded ADK Validation Success!")

if __name__ == "__main__":
    asyncio.run(main())
```

### Mode B: Hosted Server Mode (Remote HTTP)
```python
import asyncio
from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset
from open_skill_registry.adk import OpenSkillRegistry

async def main():
    registry = OpenSkillRegistry(endpoint="http://localhost:8080")
    
    matches = await registry.search_skills(query="what is the weather in Tokyo?")
    print("Found skills (hosted):", [m.name for m in matches])
    assert "weather-lookup" in [m.name for m in matches]

    skill = await registry.get_skill(name="public/weather-lookup")
    assert "Weather Lookup Instructions" in skill.instructions
    print("Hosted ADK Validation Success!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. Running Automated Tests

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests against real PostgreSQL & Redis testcontainers
pytest tests/integration/

# Run ADK adapter mock tests (both embedded and hosted modes)
pytest tests/adk/
```

# CLI Contract: `osr` (Open Skill Registry CLI)

**Binary**: `osr`  
**Built With**: Python + Typer  
**Configuration Files**: `osr.config.yaml` (workspace root) or `~/.osr/config.yaml` / `~/.osr/config.toml` (user home)  
**License**: Apache-2.0  

---

## 1. Global Flags & Configuration

```text
Usage: osr [OPTIONS] COMMAND [ARGS]...

Options:
  --config PATH         Path to configuration file [default: osr.config.yaml or ~/.osr/config.yaml]
  --registry-url TEXT   Target registry endpoint [env: OSR_REGISTRY_URL, default: http://localhost:8080]
  --api-key TEXT        Authentication API key [env: OSR_API_KEY]
  --format [text|json]  Output format [default: text]
  --help                Show help message and exit
```

Single Unified Configuration (`osr.config.yaml`):
```yaml
version: "1.0"
mode: "embedded" # "embedded" or "server"
server:
  host: "0.0.0.0"
  port: 8080
  auth_enabled: false
database:
  driver: "sqlite" # "sqlite" (default embedded) or "postgres" (hosted)
  url: "sqlite:///~/.osr/registry.db"
search:
  semantic_enabled: true  # ON by default
  provider: "fastembed"   # default local ONNX model, zero API keys
  model: "BAAI/bge-small-en-v1.5"
  dimension: 384
```

---

## 2. Command Specifications

### `osr init`
Initializes a new Open Skill Registry configuration file (`osr.config.yaml`) with clean, commented defaults.

```bash
# Initialize local configuration in current directory
osr init [--mode <embedded|server>] [--global]
```

**Behaviors**:
- Generates a fully documented `osr.config.yaml` with FastEmbed enabled locally (0 API keys required).
- When `--global` is passed, creates `~/.osr/config.yaml`.
- Prompts for confirmation before overwriting an existing config.

---

### `osr serve`
Starts the self-hosted Open Skill Registry FastAPI server and Web UI.

```bash
# Start server using osr.config.yaml
osr serve [--config <PATH>] [--host <HOST>] [--port <PORT>]
```

---

### `osr login`
Configures authentication credentials and default registry URL.

```bash
osr login [REGISTRY_URL] [--api-key <KEY>] [--namespace <NS>]
```

---

### `osr push`
Publishes a skill from a single file, a local directory, a zip archive, or a batch directory.

```bash
osr push <PATH> [--namespace <NS>] [--version <VER>] [--visibility <PUBLIC|NAMESPACE_ONLY|PRIVATE>]
```

**Behaviors**:
- **Single file**: `osr push ./SKILL.md` -> Extracts frontmatter, uploads single file directly.
- **Directory**: `osr push ./my-skill/` -> Recursively scans `references/`, `assets/`, `scripts/`, validates against allowlist, uploads as multi-file payload without needing pre-compression.
- **Batch directory**: `osr push ./skills-collection/ --batch` -> Discovers all skill subdirectories and publishes them sequentially.
- **Archive**: `osr push ./skill.zip` -> Server unpacks and verifies archive contents.
- **Version inference**: If `--version` is omitted, reads from `SKILL.md` frontmatter, or auto-increments the latest published patch version.

---

### `osr search`
Performs natural language discovery of skills in the registry.

```bash
osr search "<QUERY>" [--limit <N>] [--namespace <NS>]
```

**Output (text format)**:
```text
NAME                        VERSION  NAMESPACE  SIMILARITY  DESCRIPTION
bigquery-optimizer          1.2.0    google     0.89        Optimizes BigQuery SQL queries for cost...
sql-formatter               0.4.1    public     0.78        Formats complex SQL queries into clean standard...
```

---

### `osr pull`
Downloads a skill package to the local filesystem.

```bash
osr pull <NAMESPACE/NAME> [--version <VER>] [--tag <TAG>] [--output <DIR>]
```

**Behaviors**:
- Pulls from the registry, streams files into `<output>/<slug>/`.
- Default `--output` directory: `.agents/skills/` (project-level, if `.agents/` exists) or `~/.osr/skills/` (global fallback).
- Computes local SHA-256 hashes of all files and verifies against the remote content manifest.

**Pull Algorithm**:
1. Resolves the target version via `GET /api/v1/skills/{ns}/{slug}/resolve?tag=latest` (or specified `--version`/`--tag`).
2. Fetches the version manifest via `GET /api/v1/skills/{ns}/{slug}/versions/{version}`.
3. Iterates each file in the manifest and downloads individually via `GET .../versions/{version}/file?path={path}`.
4. Writes files to `<output>/<slug>/` preserving directory structure.
5. Computes local SHA-256 hashes for each downloaded file and verifies against the manifest.

---

### `osr info`
Displays detailed skill metadata, release history, and tags.

```bash
osr info <NAMESPACE/NAME>
```

---

### `osr tag`
Points a mutable release channel tag (`latest`, `production`, `staging`) to a specific version.

```bash
osr tag <NAMESPACE/NAME> <VERSION> <TAG_NAME>
```

---

### `osr yank`
Deprecates or soft-deletes a faulty version.

```bash
osr yank <NAMESPACE/NAME> <VERSION>
```

---

### `osr verify`
Verifies that a local skill directory matches a published release manifest.

```bash
osr verify <LOCAL_DIR> [--remote <NAMESPACE/NAME>] [--version <VER>]
```

---

### `osr namespace`
Manages registry namespaces.

```bash
# List all accessible namespaces
osr namespace list

# Create a new namespace
osr namespace create <SLUG> [--name <DISPLAY_NAME>] [--visibility <PUBLIC|NAMESPACE_ONLY|PRIVATE>]

# Show namespace details
osr namespace info <SLUG>
```

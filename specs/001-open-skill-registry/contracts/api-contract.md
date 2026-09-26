# API Contract: Open Skill Registry REST Endpoints

**Base Path**: `/api/v1`  
**Protocol**: HTTP/1.1 & HTTP/2  
**Content-Type**: `application/json` (except raw file streaming and multipart uploads)  
**License**: Apache-2.0

> **Deployment Context**: This contract specifies the HTTP/REST interface exposed by the **Hosted Server** (`open_skill_registry.server`) and consumed by `SkillRegistryClient`, the CLI (`osr`), and external language runtimes. Applications using **Embedded Library Mode** (`SkillRegistry`) call equivalent Python methods directly in-process without network overhead.

---

## 1. Unified Response Envelope

All JSON responses adhere to the standard envelope format:

```json
{
  "code": 0,
  "msg": "success",
  "data": {},
  "timestamp": "2026-09-26T12:00:00Z",
  "requestId": "req_01j8v3wz9y..."
}
```

- `code`: `0` on success. On failure, matches HTTP status code (e.g. `400`, `401`, `403`, `404`, `409`, `422`, `500`).
- `data`: Payload object, list, or pagination wrapper `{ "items": [...], "total": 42, "page": 1, "size": 20 }`.
- `requestId`: Distributed tracing UUID injected into response headers as `X-Request-Id`.

---

## 2. Authentication & Authorization

The registry supports two operational modes controlled by the `AUTH_ENABLED` environment variable:

**Open Mode** (`AUTH_ENABLED=false`, default):
- All endpoints are accessible without authentication.
- Write operations (publish, tag, yank) are unrestricted.

**Secured Mode** (`AUTH_ENABLED=true`):
- **Always public** (no auth required): `GET /health`, `GET /api/v1/skills/search` (PUBLIC skills only), `GET /api/v1/skills` (PUBLIC skills only), `GET /api/v1/skills/{ns}/{slug}` (PUBLIC skills), `GET /api/v1/skills/{ns}/{slug}/versions/*`, `GET /api/v1/skills/{ns}/{slug}/resolve`.
- **Auth required for reads** of `NAMESPACE_ONLY` and `PRIVATE` skills: Client must present `Authorization: Bearer <api_key>` with access to the skill's namespace.
- **Auth required for all writes**: `POST /api/v1/skills/publish`, `PUT .../tags/{tag}`, `DELETE .../versions/{version}`, all `/api/v1/namespaces` mutations, all `/api/v1/keys` endpoints.
- API keys are passed via the `Authorization: Bearer <api_key>` header.

---

## 3. Discovery & Search Endpoints

### `GET /api/v1/skills/search`
Discovers skills via hybrid search (PostgreSQL full-text tsvector weighted heavily on Name/Slug and Description blended with dense vector cosine similarity). Operates out of the box with the default local FastEmbed ONNX model (`BAAI/bge-small-en-v1.5`, zero API keys), user-configured external models (Gemini, OpenAI, Ollama, HuggingFace), or pure weighted syntactic search when `provider: none`.

**Query Parameters**:
- `q` (string, required): Natural language search prompt (e.g. `"query optimization in bigquery"`).
- `limit` (integer, default 10, max 50): Number of matches.
- `namespace` (string, optional): Restrict search to specific namespace.

**Response `data`**:
```json
{
  "items": [
    {
      "namespace": "google",
      "slug": "bigquery-optimizer",
      "name": "BigQuery Query Optimizer",
      "description": "Optimizes BigQuery SQL queries for cost and execution speed",
      "version": "1.2.0",
      "tags": ["sql", "bigquery", "cost-optimization"],
      "similarity_score": 0.892,
      "content_hash": "sha256:4d6a1b..."
    }
  ],
  "total": 1
}
```

---

### `GET /api/v1/skills`
Lists skills with pagination and filters.

**Query Parameters**:
- `page` (integer, default 1): Page number.
- `size` (integer, default 20, max 100): Page size.
- `namespace` (string, optional): Filter by namespace.
- `sort` (string, default `updated`): `updated`, `downloads`, `name`.

---

### `GET /api/v1/skills/{namespace}/{slug}`
Retrieves skill overview, latest version metadata, release tags, and version history.

---

### `GET /api/v1/skills/{namespace}/{slug}/versions`
Lists all available published versions for the skill.

---

## 4. Skill Retrieval & Loading (L1 -> L2 -> L3)

### `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
Retrieves full version details, parsed frontmatter, and file manifest (L1).

**Headers**:
- `If-None-Match`: Client sends previously cached `content_hash` -> Returns `304 Not Modified` if unchanged.

**Response `data`**:
```json
{
  "namespace": "google",
  "slug": "bigquery-optimizer",
  "version": "1.2.0",
  "content_hash": "sha256:4d6a1b2c3d...",
  "frontmatter": {
    "name": "bigquery-optimizer",
    "description": "Optimizes BigQuery SQL queries"
  },
  "instructions": "# BigQuery Optimizer\n\nStep 1: Check partition filters...",
  "manifest": {
    "schema_version": "1.0",
    "files": [
      {"path": "SKILL.md", "hash": "sha256:7c9e...", "size": 2048},
      {"path": "references/best-practices.md", "hash": "sha256:a1f3...", "size": 4096}
    ]
  },
  "tags": ["production", "latest"],
  "is_yanked": false,
  "visibility": "PUBLIC",
  "compliance_snapshot": {
    "license": "Apache-2.0",
    "author": "google",
    "compliance_tags": ["pii-safe", "no-external-calls"]
  },
  "created_at": "2026-09-26T10:00:00Z"
}
```

---

### `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/instructions`
Returns L2 markdown instructions directly as `text/markdown`.

---

### `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file?path={relpath}`
Returns raw binary or text content of an individual resource file (L3).
- Uses query parameter `path` to avoid nested URL path escaping bugs.
- Returns `Content-Type` matching the stored file MIME type.
- Sets `ETag` to file content hash.

---

### `GET /api/v1/skills/{namespace}/{slug}/resolve`
Deterministic resolution endpoint for agents and CLIs.

**Query Parameters**:
- `hash` (string, optional): SHA-256 fingerprint.
- `version` (string, optional): SemVer string.
- `tag` (string, optional, defaults to `latest` if neither hash nor version provided).

**Response `data`**:
```json
{
  "namespace": "google",
  "slug": "bigquery-optimizer",
  "version": "1.2.0",
  "content_hash": "sha256:4d6a1b...",
  "manifest_url": "/api/v1/skills/google/bigquery-optimizer/versions/1.2.0"
}
```

> **Note**: This points to the version detail which includes the manifest. Clients iterate the manifest and fetch each file via `/file?path=...`.

---

### `GET /api/v1/skills/{namespace}/{slug}/tags/{tag}`
Shortcut endpoint that resolves a release tag and returns the full version detail (equivalent to resolving via `/resolve?tag=...` and then fetching the version).

**Response**: Same as `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`.

---

## 5. Publishing & Management Endpoints

### `POST /api/v1/skills/publish`
Publishes a skill package without forcing archive pre-compression.

**Headers**:
- `Authorization: Bearer <api_key>` (required if `AUTH_ENABLED=true`).
- `Content-Type: multipart/form-data`.

**Form Fields**:
- `namespace` (string, optional, defaults to `public` or key-scoped namespace).
- `version` (string, optional, inferred from frontmatter or auto-incremented).
- `visibility` (string, optional: `PUBLIC`, `NAMESPACE_ONLY`, `PRIVATE`).
- `files` (array of UploadFile): Standalone `SKILL.md`, multiple raw directory files, or uploaded `.zip`/`.tar.gz` bundle.

**Validation Rules**:
- Validates `SKILL.md` exists and contains required frontmatter (`name`, `description`).
- Enforces file type allowlist and file/package size limits.
- Rejects any paths containing `../` or starting with `/`.

**Response `data`**:
```json
{
  "namespace": "myorg",
  "slug": "sql-helper",
  "version": "1.0.0",
  "content_hash": "sha256:e3b0c442...",
  "total_files": 3,
  "package_size": 8192
}
```

---

### `PUT /api/v1/skills/{namespace}/{slug}/tags/{tag}`
Assigns a mutable release tag to a version.

**Request Body**:
```json
{
  "version": "1.0.1"
}
```

---

### `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}`
Yanks a published version (soft-deletion).

---

## 6. Namespace Management Endpoints

### `POST /api/v1/namespaces`
Creates a new namespace. Requires admin API key when `AUTH_ENABLED=true`.

**Request Body**:
```json
{
  "slug": "myorg",
  "name": "My Organization",
  "description": "Internal skills for MyOrg engineering teams",
  "visibility": "NAMESPACE_ONLY"
}
```

**Validation**:
- `slug`: Lowercase alphanumeric with hyphens, 1-64 characters, unique.
- `visibility`: `PUBLIC` (default), `NAMESPACE_ONLY`, or `PRIVATE`.

---

### `GET /api/v1/namespaces`
Lists all namespaces visible to the current client.

**Query Parameters**:
- `page` (integer, default 1): Page number.
- `size` (integer, default 20, max 100): Page size.

---

### `GET /api/v1/namespaces/{slug}`
Retrieves namespace details including skill count and visibility.

---

### `PUT /api/v1/namespaces/{slug}`
Updates namespace metadata (name, description, visibility). Requires admin API key scoped to the namespace.

---

## 7. API Key Management Endpoints

All key management endpoints require an admin-level API key (or the bootstrap admin key).

### `POST /api/v1/keys`
Creates a new API key. The raw key is returned **only once** in the response.

**Request Body**:
```json
{
  "label": "ci-cd-pipeline",
  "namespace_id": "uuid-of-namespace",
  "permissions": "WRITE"
}
```

**Response `data`**:
```json
{
  "id": "uuid",
  "key": "osr_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "key_prefix": "osr_live",
  "label": "ci-cd-pipeline",
  "permissions": "WRITE",
  "namespace_slug": "myorg",
  "expires_at": null
}
```

> **Note**: The `key` field is only returned on creation. Store it securely.

---

### `GET /api/v1/keys`
Lists all API keys (without exposing raw keys). Shows prefix, label, namespace, permissions, and last used timestamp.

---

### `DELETE /api/v1/keys/{id}`
Revokes an API key immediately.

---

### Bootstrap Strategy

When `AUTH_ENABLED=true`, the initial admin API key is bootstrapped via the `OSR_ADMIN_KEY` environment variable. If the env var is set and no admin key exists in the database, the server auto-seeds it on first startup. If the env var is not set and no keys exist, the server auto-generates an admin key and prints it to stdout on first boot.

---

## 8. System & Health

### `GET /health`
Returns system status (`db`, `redis`, `embeddings`). Unauthenticated.

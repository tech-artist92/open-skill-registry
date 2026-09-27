"""Canonical CAS manifest hashing engine (T010).

Follows the Functional Core paradigm: pure functions with no side effects.
Computes deterministic SHA-256 digests over sorted file entries.
"""

import hashlib
import mimetypes
from pathlib import Path

from open_skill_registry.models.manifest import FileManifestEntry, SkillManifest

MIME_TYPE_OVERRIDES: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".py": "text/x-python",
    ".sh": "application/x-sh",
    ".ts": "application/typescript",
    ".js": "text/javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def detect_content_type(path: str) -> str:
    """Detect MIME content type from file path or extension.

    Provides explicit overrides for modern web/skill formats (e.g. TypeScript, Markdown)
    and falls back to standard mimetypes detection or application/octet-stream.
    """
    ext = Path(path).suffix.lower()
    if ext in MIME_TYPE_OVERRIDES:
        return MIME_TYPE_OVERRIDES[ext]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def compute_manifest(files: dict[str, bytes]) -> SkillManifest:
    """Compute the canonical content-addressed storage (CAS) manifest for a set of files.

    Args:
        files: Mapping of relative file paths to their raw binary byte content.

    Returns:
        SkillManifest with sorted FileManifestEntries, total byte size, and root content_hash.
    """
    # Deterministic ascending sort by relative path
    sorted_paths = sorted(files.keys())

    manifest_entries: list[FileManifestEntry] = []
    lines: list[str] = []

    for path in sorted_paths:
        file_bytes = files[path]
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        size_bytes = len(file_bytes)
        content_type = detect_content_type(path)

        entry = FileManifestEntry(
            path=path,
            hash=file_hash,
            size_bytes=size_bytes,
            content_type=content_type,
        )
        manifest_entries.append(entry)
        lines.append(f"{path}:{file_hash}:{size_bytes}\n")

    manifest_payload = "".join(lines)
    root_content_hash = hashlib.sha256(manifest_payload.encode("utf-8")).hexdigest()
    total_size_bytes = sum(entry.size_bytes for entry in manifest_entries)

    return SkillManifest(
        version="1.0",
        files=manifest_entries,
        total_size_bytes=total_size_bytes,
        content_hash=root_content_hash,
    )

"""Package safety validator (T011).

Follows the Functional Core paradigm: pure functions with no side effects.
Validates file safety constraints:
- Must contain SKILL.md at the package root
- Path traversal rejection (no leading slashes, no ../ or ..\\)
- Strict extension allowlist
- Per-file size limits (default 1MB)
- Total package size limits (default 10MB)
"""

from pathlib import Path

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".py",
        ".sh",
        ".ts",
        ".js",
        ".png",
        ".jpg",
        ".svg",
    }
)

DEFAULT_MAX_FILE_SIZE = 1_048_576  # 1MB
DEFAULT_MAX_PACKAGE_SIZE = 10_485_760  # 10MB


def _has_path_traversal(path: str) -> bool:
    """Check if the given relative path contains traversal attempts or is absolute."""
    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    parts = normalized.split("/")
    if ".." in parts:
        return True
    if len(parts[0]) == 2 and parts[0][1] == ":":
        return True
    try:
        p = Path(path)
        if p.is_absolute() or ".." in p.parts:
            return True
    except Exception:
        return True
    return False


def validate_package(
    files: dict[str, bytes],
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    max_package_size: int = DEFAULT_MAX_PACKAGE_SIZE,
) -> list[str]:
    """Validate skill package files against security and size constraints.

    Args:
        files: Mapping of relative file paths to file bytes.
        max_file_size: Maximum allowed size in bytes for any single file (default 1MB).
        max_package_size: Maximum allowed combined size in bytes for the entire
            package (default 10MB).

    Returns:
        List of validation error strings. Empty list indicates the package is valid.
    """
    errors: list[str] = []

    # 1. Root SKILL.md check
    if "SKILL.md" not in files:
        errors.append("Package must include a 'SKILL.md' file at the root.")

    total_package_size = 0

    # Sort paths for deterministic validation error reporting
    for path in sorted(files.keys()):
        content = files[path]
        file_size = len(content)
        total_package_size += file_size

        # 2. Path traversal checks
        if _has_path_traversal(path):
            errors.append(f"Invalid path traversal or absolute path detected in file '{path}'")

        # 3. Allowed extensions check
        suffix = Path(path).suffix.lower()
        if not suffix or suffix not in ALLOWED_EXTENSIONS:
            allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
            errors.append(
                f"File '{path}' has disallowed extension '{suffix}'. "
                f"Allowed extensions: {allowed_str}"
            )

        # 4. Per-file size check
        if file_size > max_file_size:
            errors.append(
                f"File '{path}' exceeds maximum file size of {max_file_size} bytes "
                f"({file_size} bytes)"
            )

    # 5. Total package size check
    if total_package_size > max_package_size:
        errors.append(
            f"Total package size ({total_package_size} bytes) exceeds maximum "
            f"allowed size of {max_package_size} bytes"
        )

    return errors


def validate_package_or_raise(
    files: dict[str, bytes],
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    max_package_size: int = DEFAULT_MAX_PACKAGE_SIZE,
) -> None:
    """Validate skill package files and raise ValueError if any safety checks fail.

    Args:
        files: Mapping of relative file paths to file bytes.
        max_file_size: Maximum allowed size for any single file.
        max_package_size: Maximum allowed combined size for the package.

    Raises:
        ValueError: If one or more validation errors are found.
    """
    errors = validate_package(
        files,
        max_file_size=max_file_size,
        max_package_size=max_package_size,
    )
    if errors:
        raise ValueError("; ".join(errors))

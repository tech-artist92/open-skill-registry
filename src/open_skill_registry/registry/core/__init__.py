"""Pure functional core for Open Skill Registry."""

from open_skill_registry.registry.core.manifest import compute_manifest, detect_content_type
from open_skill_registry.registry.core.validator import (
    ALLOWED_EXTENSIONS,
    validate_package,
    validate_package_or_raise,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "compute_manifest",
    "detect_content_type",
    "validate_package",
    "validate_package_or_raise",
]

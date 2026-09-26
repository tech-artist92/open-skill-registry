"""Unit tests for canonical CAS manifest hashing engine (T010)."""

import hashlib

from open_skill_registry.models.manifest import SkillManifest
from open_skill_registry.registry.core.manifest import compute_manifest, detect_content_type


def test_compute_manifest_empty():
    manifest = compute_manifest({})
    assert isinstance(manifest, SkillManifest)
    assert manifest.version == "1.0"
    assert manifest.files == []
    assert manifest.total_size_bytes == 0
    # SHA-256 of empty string is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    expected_hash = hashlib.sha256(b"").hexdigest()
    assert manifest.content_hash == expected_hash


def test_compute_manifest_single_file():
    content = b"# Test Skill\nHello world\n"
    files = {"SKILL.md": content}
    manifest = compute_manifest(files)

    assert len(manifest.files) == 1
    entry = manifest.files[0]
    assert entry.path == "SKILL.md"
    assert entry.size_bytes == len(content)
    assert entry.content_type == "text/markdown"
    assert entry.hash == hashlib.sha256(content).hexdigest()
    assert manifest.total_size_bytes == len(content)

    # Root hash verification
    expected_manifest_line = f"SKILL.md:{entry.hash}:{len(content)}\n"
    expected_root_hash = hashlib.sha256(expected_manifest_line.encode("utf-8")).hexdigest()
    assert manifest.content_hash == expected_root_hash


def test_compute_manifest_deterministic_sorting():
    # Pass files in arbitrary order
    content_a = b"File A content"
    content_b = b"File B content"
    content_c = b"File C content"

    files_order_1 = {
        "z_file.py": content_c,
        "a_file.txt": content_a,
        "m_file.json": content_b,
    }
    files_order_2 = {
        "m_file.json": content_b,
        "z_file.py": content_c,
        "a_file.txt": content_a,
    }

    manifest_1 = compute_manifest(files_order_1)
    manifest_2 = compute_manifest(files_order_2)

    # Order must be sorted deterministically: a_file.txt, m_file.json, z_file.py
    assert [f.path for f in manifest_1.files] == ["a_file.txt", "m_file.json", "z_file.py"]
    assert [f.path for f in manifest_2.files] == ["a_file.txt", "m_file.json", "z_file.py"]

    # Manifest hashes must be completely identical
    assert manifest_1.content_hash == manifest_2.content_hash
    assert manifest_1.total_size_bytes == manifest_2.total_size_bytes


def test_compute_manifest_content_type_detection():
    test_cases = [
        ("SKILL.md", "text/markdown"),
        ("readme.markdown", "text/markdown"),
        ("notes.txt", "text/plain"),
        ("config.json", "application/json"),
        ("schema.yaml", "application/yaml"),
        ("schema.yml", "application/yaml"),
        ("script.py", "text/x-python"),
        ("run.sh", "application/x-sh"),
        ("index.ts", "application/typescript"),
        ("index.js", "text/javascript"),
        ("logo.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("icon.svg", "image/svg+xml"),
        ("unknown_file.xyz_unknown", "application/octet-stream"),
    ]

    for filename, expected_mime in test_cases:
        assert detect_content_type(filename) == expected_mime


def test_compute_manifest_multiple_files_total_size():
    files = {
        "SKILL.md": b"12345",  # 5 bytes
        "scripts/main.py": b"1234567890",  # 10 bytes
        "data.json": b"123",  # 3 bytes
    }
    manifest = compute_manifest(files)
    assert manifest.total_size_bytes == 18
    assert len(manifest.files) == 3

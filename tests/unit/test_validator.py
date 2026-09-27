"""Unit tests for package safety validator (T011)."""

import pytest

from open_skill_registry.registry.core.validator import (
    ALLOWED_EXTENSIONS,
    validate_package,
    validate_package_or_raise,
)


def test_allowed_extensions_set():
    expected = {
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
    assert expected == ALLOWED_EXTENSIONS


def test_validate_package_valid():
    files = {
        "SKILL.md": b"# My Skill\nSome valid markdown content.",
        "scripts/run.sh": b"#!/usr/bin/env bash\necho 1",
        "references/info.json": b'{"key": "value"}',
    }
    errors = validate_package(files)
    assert errors == []


def test_validate_package_missing_skill_md():
    files = {
        "scripts/run.sh": b"#!/bin/bash",
    }
    errors = validate_package(files)
    assert any("SKILL.md" in err for err in errors)


def test_validate_package_skill_md_nested_not_root():
    # SKILL.md must be at the package root
    files = {
        "subdir/SKILL.md": b"# Subdir Skill",
    }
    errors = validate_package(files)
    assert any("SKILL.md" in err for err in errors)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../evil.sh",
        "..\\evil.sh",
        "subdir/../evil.sh",
        "subdir/..\\evil.sh",
        "subdir/..",
        "subdir\\..",
        "/etc/passwd",
        "\\Windows\\System32\\calc.exe",
        "C:\\Windows\\System32\\calc.exe",
        "C:/Windows/calc.exe",
        "..",
    ],
)
def test_validate_package_path_traversal(bad_path: str):
    files = {
        "SKILL.md": b"# Valid root",
        bad_path: b"malicious content",
    }
    errors = validate_package(files)
    assert any("path traversal" in err.lower() or "invalid path" in err.lower() for err in errors)


@pytest.mark.parametrize(
    "disallowed_file",
    [
        "malware.exe",
        "library.so",
        "archive.zip",
        "firmware.bin",
        "file_without_extension",
    ],
)
def test_validate_package_disallowed_extensions(disallowed_file: str):
    files = {
        "SKILL.md": b"# Valid root",
        disallowed_file: b"binary content",
    }
    errors = validate_package(files)
    assert any("extension" in err.lower() for err in errors)


def test_validate_package_case_insensitive_extension():
    files = {
        "SKILL.md": b"# Valid root",
        "image.PNG": b"fake png bytes",
        "CONFIG.YAML": b"key: val",
    }
    errors = validate_package(files)
    assert errors == []


def test_validate_package_file_size_exceeded():
    max_file_size = 100
    files = {
        "SKILL.md": b"x" * (max_file_size + 1),
    }
    errors = validate_package(files, max_file_size=max_file_size)
    assert any("exceeds maximum file size" in err for err in errors)


def test_validate_package_file_size_boundary():
    max_file_size = 100
    files = {
        "SKILL.md": b"x" * max_file_size,
    }
    errors = validate_package(files, max_file_size=max_file_size)
    assert errors == []


def test_validate_package_total_size_exceeded():
    max_file_size = 100
    max_package_size = 150
    files = {
        "SKILL.md": b"x" * 90,
        "notes.txt": b"y" * 70,  # Each file < 100, but sum = 160 > 150
    }
    errors = validate_package(
        files,
        max_file_size=max_file_size,
        max_package_size=max_package_size,
    )
    assert any("Total package size" in err for err in errors)


def test_validate_package_total_size_boundary():
    max_file_size = 100
    max_package_size = 150
    files = {
        "SKILL.md": b"x" * 80,
        "notes.txt": b"y" * 70,  # Total = 150 == max_package_size
    }
    errors = validate_package(
        files,
        max_file_size=max_file_size,
        max_package_size=max_package_size,
    )
    assert errors == []


def test_validate_package_multiple_errors():
    files = {
        "../bad.exe": b"x" * 200,  # traversal, disallowed extension, size exceeded
    }
    errors = validate_package(files, max_file_size=100)
    # Should flag missing SKILL.md, traversal, disallowed extension, and size exceeded
    assert len(errors) >= 3


def test_validate_package_or_raise_success():
    files = {
        "SKILL.md": b"# Valid",
    }
    # Should not raise
    validate_package_or_raise(files)


def test_validate_package_or_raise_failure():
    files = {
        "invalid.exe": b"binary",
    }
    with pytest.raises(ValueError) as exc_info:
        validate_package_or_raise(files)

    assert "SKILL.md" in str(exc_info.value)

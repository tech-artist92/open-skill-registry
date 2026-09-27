"""Security scanner for skill packages (T061).

Inspects skill package contents for prompt injections, leaked secrets,
dangerous shell commands, and unsafe Python AST usage.
"""

import ast
import re
import zipfile
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class ScanFinding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    file_path: str = ""
    line_number: int | None = None
    snippet: str | None = None


class SecurityScanResult(BaseModel):
    safety_score: str = "SAFE"
    passed: bool = True
    findings: list[ScanFinding] = Field(default_factory=list)
    scanned_files_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


# Heuristic Regex Rules

PROMPT_INJECTION_PATTERNS = [
    (
        re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions\b", re.IGNORECASE),
        "Prompt injection detected: ignore previous instructions",
    ),
    (
        re.compile(
            r"\bdisregard\s+(?:all\s+)?previous\s+(?:instructions|prompts|commands)?\b",
            re.IGNORECASE,
        ),
        "Prompt injection detected: disregard previous instructions",
    ),
    (
        re.compile(r"\bsystem\s+prompt\s+override\b", re.IGNORECASE),
        "Prompt injection detected: system prompt override",
    ),
    (
        re.compile(r"\b(?:you\s+are\s+now\s+in\s+)?developer\s+mode\b", re.IGNORECASE),
        "Prompt injection / jailbreak detected: developer mode",
    ),
    (
        re.compile(r"\b(?:act\s+as\s+dan|dan\s+mode)\b", re.IGNORECASE),
        "Prompt injection / jailbreak detected: DAN mode",
    ),
]

SECRET_RULES = [
    (
        "secret-aws-key",
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
        Severity.CRITICAL,
        "Leaked AWS Access Key ID detected",
    ),
    (
        "secret-private-key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        Severity.CRITICAL,
        "Private encryption key block detected",
    ),
    (
        "secret-github-token",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b"),
        Severity.CRITICAL,
        "Leaked GitHub personal access token detected",
    ),
    (
        "secret-openai-key",
        re.compile(r"\b(sk-[a-zA-Z0-9]{32,})\b"),
        Severity.CRITICAL,
        "Leaked OpenAI API secret key detected",
    ),
]

SHELL_RULES = [
    (
        "shell-rm-rf-root",
        re.compile(
            r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+(?:/\*?)(?:\s|$)",
            re.IGNORECASE,
        ),
        Severity.CRITICAL,
        "Dangerous shell command: rm -rf / root directory removal",
        True,  # Check in all files
    ),
    (
        "shell-curl-pipe-bash",
        re.compile(r"\b(?:curl|wget)\b.*?\|\s*(?:bash|sh)\b", re.IGNORECASE),
        Severity.CRITICAL,
        "Dangerous shell command: downloading and executing remote script via pipe",
        True,  # Check in all files
    ),
    (
        "shell-reverse-shell",
        re.compile(r"\b(?:nc(?:\.traditional)?\s+-[a-zA-Z]*e\s+|/dev/tcp/\d+/\d+)", re.IGNORECASE),
        Severity.CRITICAL,
        "Dangerous shell command: reverse shell execution",
        True,  # Check in all files
    ),
    (
        "shell-chmod-777",
        re.compile(r"\bchmod\s+(?:-[a-zA-Z]+\s+)?777\b"),
        Severity.CRITICAL,
        "Dangerous shell command: chmod 777 world-writable permissions",
        False,  # Shell / script files only
    ),
    (
        "shell-sudo",
        re.compile(r"\bsudo\b"),
        Severity.CRITICAL,
        "Dangerous shell command: sudo privilege escalation",
        False,  # Shell / script files only
    ),
]

SHELL_EXTENSIONS = {
    ".sh", ".bash", ".zsh", ".fish", ".ksh", ".csh", ".tcsh", ".bat", ".cmd", ".ps1"
}


def _is_shell_file(path: str, content: bytes) -> bool:
    lower_path = path.lower()
    if any(lower_path.endswith(ext) for ext in SHELL_EXTENSIONS):
        return True
    return bool(content.startswith(b"#!"))


class _PythonSecurityVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.findings: list[ScanFinding] = []

    def visit_Call(self, node: ast.Call):
        # 1. eval()
        if isinstance(node.func, ast.Name) and node.func.id == "eval":
            self.findings.append(
                ScanFinding(
                    rule_id="ast-eval",
                    severity=Severity.CRITICAL,
                    message="Direct call to eval() detected",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )

        # 2. exec()
        elif isinstance(node.func, ast.Name) and node.func.id == "exec":
            self.findings.append(
                ScanFinding(
                    rule_id="ast-exec",
                    severity=Severity.CRITICAL,
                    message="Direct call to exec() detected",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )

        # 3. __import__()
        elif isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.findings.append(
                ScanFinding(
                    rule_id="ast-dynamic-import",
                    severity=Severity.WARN,
                    message="Dynamic import via __import__() detected",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )

        # 4. os.system()
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "system"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            self.findings.append(
                ScanFinding(
                    rule_id="ast-os-system",
                    severity=Severity.CRITICAL,
                    message="Call to os.system() detected",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )

        # 5. subprocess execution with shell=True
        is_subproc = False
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                is_subproc = True
        elif (
            isinstance(node.func, ast.Name)
            and node.func.id in {"Popen", "run", "call", "check_call", "check_output"}
        ):
            is_subproc = True

        if is_subproc:
            has_shell_true = False
            for kw in node.keywords:
                if kw.arg == "shell":
                    if isinstance(kw.value, ast.Constant):
                        if bool(kw.value.value) is True:
                            has_shell_true = True
                    else:
                        has_shell_true = True
            if has_shell_true:
                self.findings.append(
                    ScanFinding(
                        rule_id="ast-subprocess-shell",
                        severity=Severity.CRITICAL,
                        message="Subprocess execution with shell=True detected",
                        file_path=self.file_path,
                        line_number=node.lineno,
                    )
                )

        self.generic_visit(node)


def scan_skill_package(files: dict[str, bytes]) -> SecurityScanResult:
    """Scan a dictionary of relative file paths and bytes content for security issues."""
    findings: list[ScanFinding] = []

    for path, content in files.items():
        is_shell = _is_shell_file(path, content)
        text = content.decode("utf-8", errors="replace")
        lines = text.splitlines()

        # 1. Prompt Injection detection (check text line by line)
        for line_idx, line in enumerate(lines, start=1):
            for pattern, msg in PROMPT_INJECTION_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        ScanFinding(
                            rule_id="prompt-injection",
                            severity=Severity.CRITICAL,
                            message=msg,
                            file_path=path,
                            line_number=line_idx,
                            snippet=line.strip()[:100],
                        )
                    )
                    break

        # 2. Secret Scanner detection
        for line_idx, line in enumerate(lines, start=1):
            for rule_id, regex, severity, msg in SECRET_RULES:
                if regex.search(line):
                    findings.append(
                        ScanFinding(
                            rule_id=rule_id,
                            severity=severity,
                            message=msg,
                            file_path=path,
                            line_number=line_idx,
                            snippet=line.strip()[:100],
                        )
                    )

        # 3. Shell Injection / Dangerous Commands
        for line_idx, line in enumerate(lines, start=1):
            for rule_id, regex, severity, msg, check_all in SHELL_RULES:
                if (check_all or is_shell) and regex.search(line):
                    findings.append(
                        ScanFinding(
                            rule_id=rule_id,
                            severity=severity,
                            message=msg,
                            file_path=path,
                            line_number=line_idx,
                            snippet=line.strip()[:100],
                        )
                    )

        # 4. Python AST inspection
        if path.endswith(".py"):
            try:
                tree = ast.parse(content.decode("utf-8"), filename=path)
                visitor = _PythonSecurityVisitor(file_path=path)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            except SyntaxError as e:
                findings.append(
                    ScanFinding(
                        rule_id="ast-syntax-error",
                        severity=Severity.WARN,
                        message=f"Python syntax error: {e.msg}",
                        file_path=path,
                        line_number=e.lineno or 1,
                    )
                )
            except UnicodeDecodeError as e:
                findings.append(
                    ScanFinding(
                        rule_id="ast-syntax-error",
                        severity=Severity.WARN,
                        message=f"Python encoding error: {e}",
                        file_path=path,
                        line_number=1,
                    )
                )

    has_critical = any(f.severity == Severity.CRITICAL for f in findings)
    has_warn = any(f.severity == Severity.WARN for f in findings)

    if has_critical:
        safety_score = "CRITICAL"
        passed = False
    elif has_warn:
        safety_score = "WARN"
        passed = True
    else:
        safety_score = "SAFE"
        passed = True

    return SecurityScanResult(
        safety_score=safety_score,
        passed=passed,
        findings=findings,
        scanned_files_count=len(files),
    )


def scan_path(path: Path | str) -> SecurityScanResult:
    """Scan a file, directory, or zip archive path for security issues."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")

    files: dict[str, bytes] = {}
    if target.is_file():
        if zipfile.is_zipfile(target):
            with zipfile.ZipFile(target, "r") as zf:
                for name in zf.namelist():
                    if not zf.getinfo(name).is_dir():
                        files[name] = zf.read(name)
        else:
            files[target.name] = target.read_bytes()
    elif target.is_dir():
        for file_path in target.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(target).as_posix()
                files[rel_path] = file_path.read_bytes()
    else:
        raise ValueError(f"Unsupported path: {target}")

    return scan_skill_package(files)


def scan_directory(path: Path | str) -> SecurityScanResult:
    """Alias for scan_path targeting directories."""
    return scan_path(path)

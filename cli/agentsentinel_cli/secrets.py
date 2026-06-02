"""File discovery and scanning engine for sentinel secrets.

Classifies files as memory, config, source, or other, then applies the appropriate
rule layers from secrets_rules.py. Memory file findings are severity-upgraded when
credentials are found inside agent memory paths (higher impact — often git-committed).
"""

import dataclasses
import time
from pathlib import Path

from agentsentinel_cli.secrets_rules import (
    SecretFinding,
    _CRED_RULES,
    _PII_RULES,
    check_memory_contamination,
    redact_value,
    redact_line_context,
)


# ── Report ────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class SecretsReport:
    """Full result set from a secrets scan."""

    target: Path
    files_scanned: int
    memory_files_scanned: int
    config_files_scanned: int
    findings: list[SecretFinding]
    gitignore_warnings: list[str]
    duration_seconds: float


# ── File classification ───────────────────────────────────────────────────────

# Known agent framework memory directories — any file inside counts as "memory"
_MEMORY_DIRS: frozenset[str] = frozenset({
    "memory", "memories",
    "projects",               # Claude Code: ~/.claude/projects/*/memory/
    "autogen_cache", ".autogen",
    ".langchain", "langchain_cache",
    ".crewai", "crew_workspace",
    ".mem0", "mem0_storage",
    ".openai_agents", "agent_workspace",
    "agent_logs", "conversation_history",
})

# Filename stem keywords that identify memory files regardless of parent directory
_MEMORY_NAME_KW: frozenset[str] = frozenset({
    "memory", "conversation", "session", "history", "cache", "agent_log", "chat_log",
})

_MEMORY_EXTS: frozenset[str] = frozenset({".md", ".txt", ".json", ""})
_CONFIG_EXTS: frozenset[str] = frozenset({".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"})
_CONFIG_NAMES: frozenset[str] = frozenset({
    ".env", "config.json", "settings.json", "secrets.json",
    "credentials.json", "docker-compose.yml", "docker-compose.yaml",
})
_SOURCE_EXTS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".go", ".rb", ".java", ".rs", ".cs", ".php", ".sh",
})
_SKIP_EXTS: frozenset[str] = frozenset({
    ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".bin", ".exe", ".so", ".dll",
    ".dylib", ".zip", ".tar", ".gz", ".bz2", ".7z", ".pdf",
    ".pkl", ".pt", ".onnx", ".safetensors", ".parquet", ".arrow",
})
_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", "node_modules", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "site-packages",
})

_MAX_FILE_BYTES = 1_000_000  # skip files larger than 1 MB


def _classify_file(path: Path) -> str:
    """Classify a file as 'memory', 'config', 'source', or 'other'."""
    name = path.name.lower()
    ext = path.suffix.lower()
    stem = path.stem.lower()
    dir_names = {p.lower() for p in path.parts[:-1]}

    # Memory: inside a known agent memory directory
    if dir_names & _MEMORY_DIRS and ext in _MEMORY_EXTS:
        return "memory"

    # Memory: filename contains a memory keyword
    if any(kw in stem for kw in _MEMORY_NAME_KW) and ext in _MEMORY_EXTS:
        return "memory"

    # Config: .env files (name-based, handles .env, .env.local, .env.production)
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return "config"
    if name in _CONFIG_NAMES or ext in _CONFIG_EXTS:
        return "config"

    # Source code
    if ext in _SOURCE_EXTS:
        return "source"

    return "other"


def _should_skip(path: Path) -> bool:
    """Return True if this file should not be scanned."""
    if path.suffix.lower() in _SKIP_EXTS:
        return True
    parts = set(path.parts)
    if parts & _SKIP_DIRS:
        return True
    # Skip hidden directories except .env files and .claude
    for part in path.parts[:-1]:
        if part.startswith(".") and part not in {".claude", ".env", ".langchain",
                                                  ".autogen", ".crewai", ".mem0",
                                                  ".openai_agents"}:
            return True
    try:
        return path.stat().st_size > _MAX_FILE_BYTES
    except OSError:
        return True


def _read_lines(path: Path) -> list[str] | None:
    """Read file lines with UTF-8 encoding, ignoring decode errors. Returns None on IO error."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None


# ── Per-file scanner ──────────────────────────────────────────────────────────

def _scan_file(
    path: Path,
    file_type: str,
    scope: str,
    redact: bool,
) -> list[SecretFinding]:
    """Apply credential, PII, and memory-contamination rules to a single file."""
    if scope == "memory" and file_type != "memory":
        return []
    if scope == "config" and file_type not in {"memory", "config"}:
        return []

    lines = _read_lines(path)
    if lines is None:
        return []

    findings: list[SecretFinding] = []
    seen: set[tuple[str, int]] = set()  # (rule_id, line_number) dedup

    # Layer 1 — credentials
    for rule in _CRED_RULES:
        if file_type not in rule.file_types:
            continue
        for i, line in enumerate(lines, 1):
            for m in rule.pattern.finditer(line):
                key = (rule.rule_id, i)
                if key in seen:
                    continue
                seen.add(key)
                matched = m.group()
                # Credentials found inside memory files are upgraded to CRITICAL:
                # memory files are often git-committed with no secrets management.
                sev = "CRITICAL" if file_type == "memory" and rule.severity == "HIGH" else rule.severity
                findings.append(SecretFinding(
                    rule_id=rule.rule_id,
                    severity=sev,
                    category="credential",
                    jurisdiction=rule.jurisdiction,
                    file=path,
                    line=i,
                    match_preview=redact_value(matched, enabled=redact),
                    context_line=redact_line_context(line, matched, enabled=redact),
                    recommendation=rule.recommendation,
                    validated=True,
                ))

    # Layer 2 — PII (skip inline code comments in source files)
    for rule in _PII_RULES:
        if file_type not in rule.file_types:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if file_type == "source" and (stripped.startswith("#") or stripped.startswith("//")):
                continue
            for m in rule.pattern.finditer(line):
                matched = m.group()
                if rule.validator and not rule.validator(matched):
                    continue
                key = (rule.rule_id, i)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(SecretFinding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    category="pii",
                    jurisdiction=rule.jurisdiction,
                    file=path,
                    line=i,
                    match_preview=redact_value(matched, enabled=redact),
                    context_line=redact_line_context(line, matched, enabled=redact),
                    recommendation=rule.recommendation,
                    validated=rule.validator is not None,
                ))

    # Layer 3 — memory contamination (compound rules, memory files only)
    if file_type == "memory":
        for finding in check_memory_contamination(lines, path):
            findings.append(finding)

    return findings


# ── .gitignore check ──────────────────────────────────────────────────────────

def _check_gitignore(root: Path, memory_files: list[Path]) -> list[str]:
    """Warn about memory file directories not covered by .gitignore."""
    if not memory_files:
        return []

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return ["No .gitignore found — agent memory files may be committed to git"]

    patterns = set()
    try:
        for ln in gitignore.read_text(errors="ignore").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                patterns.add(ln)
    except OSError:
        return []

    warnings: list[str] = []
    warned_dirs: set[str] = set()

    for mf in memory_files:
        parent = mf.parent.name
        if parent in warned_dirs:
            continue
        covered = any(
            parent in p or mf.name in p or "memory" in p or "*.md" in p
            for p in patterns
        )
        if not covered:
            warned_dirs.add(parent)
            rel = mf.parent.relative_to(root) if root in mf.parents else mf.parent
            warnings.append(
                f"{rel}/ is not covered by .gitignore — "
                f"memory files containing PII or secrets may be committed to git"
            )

    return warnings


# ── Public entrypoint ─────────────────────────────────────────────────────────

def scan_secrets(
    target: Path,
    scope: str = "all",
    redact: bool = True,
) -> SecretsReport:
    """Scan target path for secrets, PII, and AI memory contamination.

    Args:
        target: File or directory to scan.
        scope:  'all' | 'memory' | 'config' — restricts which file types are scanned.
        redact: If True (default), match previews are partially masked in the report.
    """
    t0 = time.monotonic()
    target = target.resolve()

    candidates = list(target.rglob("*")) if target.is_dir() else [target]
    files = [f for f in candidates if f.is_file() and not _should_skip(f)]

    findings: list[SecretFinding] = []
    memory_files: list[Path] = []
    n_memory = n_config = 0

    for f in files:
        ft = _classify_file(f)
        if ft == "memory":
            memory_files.append(f)
            n_memory += 1
        elif ft == "config":
            n_config += 1
        findings.extend(_scan_file(f, ft, scope, redact))

    root = target if target.is_dir() else target.parent
    gitignore_warnings = _check_gitignore(root, memory_files)

    # Sort by severity rank, then file path, then line number
    _rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda x: (_rank.get(x.severity, 4), str(x.file), x.line))

    return SecretsReport(
        target=target,
        files_scanned=len(files),
        memory_files_scanned=n_memory,
        config_files_scanned=n_config,
        findings=findings,
        gitignore_warnings=gitignore_warnings,
        duration_seconds=round(time.monotonic() - t0, 2),
    )

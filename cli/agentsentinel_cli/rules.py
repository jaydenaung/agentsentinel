"""Standalone posture rules — no database required, works purely on static analysis."""

import dataclasses
from agentsentinel_cli.scanner import AgentInfo, ToolInfo


@dataclasses.dataclass
class Finding:
    severity: str       # CRITICAL | HIGH | MEDIUM | LOW
    rule_id: str
    message: str
    detail: str = ""


_INTERNAL_READ_KW = {"db", "database", "crm", "file", "filesystem", "s3_read", "storage_read", "read_file"}
_EXTERNAL_WRITE_KW = {"email", "smtp", "webhook", "http_post", "http_external", "s3_write", "send", "slack"}
_READ_PURPOSE_WORDS = {"read", "search", "query", "view", "lookup", "fetch", "get", "retrieve"}


def _rule_exfiltration_path(agent: AgentInfo) -> Finding | None:
    tool_names = {t.name.lower() for t in agent.tools}
    internal_hits = [n for n in tool_names if any(kw in n for kw in _INTERNAL_READ_KW)]
    external_hits = [n for n in tool_names if any(kw in n for kw in _EXTERNAL_WRITE_KW)]
    if internal_hits and external_hits:
        return Finding(
            severity="CRITICAL",
            rule_id="EXFILTRATION_PATH",
            message="Agent holds both internal-read and external-write grants.",
            detail=f"Internal-read: {', '.join(internal_hits)} | External-write: {', '.join(external_hits)}",
        )
    return None


def _rule_privilege_excess(agent: AgentInfo) -> Finding | None:
    if not agent.description:
        return None
    desc = agent.description.lower()
    if not any(w in desc for w in _READ_PURPOSE_WORDS):
        return None
    elevated = [t.name for t in agent.tools if t.scope in ("write",) or t.is_dangerous]
    if elevated:
        return Finding(
            severity="HIGH",
            rule_id="PRIVILEGE_EXCESS",
            message="Agent description implies read-only purpose but holds write/dangerous grants.",
            detail=f"Elevated grants: {', '.join(elevated)}",
        )
    return None


def _rule_dangerous_grants(agent: AgentInfo) -> Finding | None:
    dangerous = [t.name for t in agent.tools if t.is_dangerous]
    if dangerous:
        return Finding(
            severity="HIGH",
            rule_id="DANGEROUS_GRANTS",
            message="Agent holds dangerous tool grants. Verify intent and add rate limits.",
            detail=f"Dangerous tools: {', '.join(dangerous)}",
        )
    return None


def _rule_missing_rate_limit(agent: AgentInfo) -> Finding | None:
    """Flag dangerous tools — rate limits aren't visible in static analysis."""
    dangerous = [t.name for t in agent.tools if t.is_dangerous]
    if dangerous:
        return Finding(
            severity="LOW",
            rule_id="MISSING_RATE_LIMIT",
            message="Dangerous grants detected. Ensure rate limits are configured at runtime.",
            detail=f"Tools to check: {', '.join(dangerous)}",
        )
    return None


def _rule_write_without_description(agent: AgentInfo) -> Finding | None:
    write_tools = [t.name for t in agent.tools if t.scope == "write"]
    if write_tools and not agent.description:
        return Finding(
            severity="MEDIUM",
            rule_id="UNDESCRIBED_WRITE_AGENT",
            message="Agent has write-scope grants but no description.",
            detail=(
                f"Write tools: {', '.join(write_tools)}. "
                "Add a description so posture rules can assess intent."
            ),
        )
    return None


_ALL_RULES = [
    _rule_exfiltration_path,
    _rule_privilege_excess,
    _rule_dangerous_grants,
    _rule_write_without_description,
    _rule_missing_rate_limit,
]

_SEVERITY_WEIGHT = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 10, "LOW": 5}


def run_rules(agent: AgentInfo) -> list[Finding]:
    findings = []
    seen_rules: set[str] = set()
    for rule_fn in _ALL_RULES:
        f = rule_fn(agent)
        if f and f.rule_id not in seen_rules:
            findings.append(f)
            seen_rules.add(f.rule_id)
    return findings


def posture_score(findings: list[Finding]) -> int:
    """Calculate posture score (0-100) from findings, same formula as the platform."""
    deductions = sum(_SEVERITY_WEIGHT.get(f.severity, 0) for f in findings)
    return max(0, 100 - deductions)

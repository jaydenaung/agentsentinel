"""Posture rule engine — six static rules that produce Findings."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from agentsentinel.models.agent import Agent, McpConnection, ToolGrant
from agentsentinel.models.finding import Finding


def _make_finding(
    agent_id: UUID,
    severity: str,
    rule_id: str,
    message: str,
) -> Finding:
    """Construct a Finding without persisting it."""
    return Finding(
        agent_id=agent_id,
        severity=severity,
        finding_type="POSTURE",
        rule_id=rule_id,
        message=message,
        status="OPEN",
    )


_INTERNAL_READ_KEYWORDS = {"db", "database", "crm", "file", "filesystem", "s3_read", "storage_read"}
_EXTERNAL_WRITE_KEYWORDS = {"s3_write", "http_external", "email", "smtp", "webhook", "http_post"}
_READ_PURPOSE_WORDS = {"read", "search", "query", "view", "lookup", "fetch", "get"}


def rule_exfiltration_path(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """CRITICAL: agent holds both an internal-read and an external-write grant."""
    tool_names = {g.tool_name.lower() for g in grants}
    has_internal_read = any(kw in name for name in tool_names for kw in _INTERNAL_READ_KEYWORDS)
    has_external_write = any(kw in name for name in tool_names for kw in _EXTERNAL_WRITE_KEYWORDS)
    if has_internal_read and has_external_write:
        return _make_finding(
            agent.id,
            "CRITICAL",
            "EXFILTRATION_PATH",
            f"Agent '{agent.name}' holds both internal-read and external-write grants, "
            "creating a potential data exfiltration path.",
        )
    return None


def rule_privilege_excess(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: write/admin grant on an agent whose description implies read-only purpose."""
    if not agent.description:
        return None
    desc_lower = agent.description.lower()
    if not any(word in desc_lower for word in _READ_PURPOSE_WORDS):
        return None
    elevated = [g for g in grants if g.scope in ("admin", "write")]
    if elevated:
        names = ", ".join(g.tool_name for g in elevated)
        return _make_finding(
            agent.id,
            "HIGH",
            "PRIVILEGE_EXCESS",
            f"Agent '{agent.name}' description implies read-only purpose but holds elevated "
            f"grants: {names}.",
        )
    return None


def rule_unused_dangerous_grant(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: dangerous grant that has never been called or not called in 30 days."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
    stale = [
        g for g in grants
        if g.is_dangerous and (g.last_called_at is None or g.last_called_at < cutoff)
    ]
    if stale:
        names = ", ".join(g.tool_name for g in stale)
        return _make_finding(
            agent.id,
            "HIGH",
            "UNUSED_DANGEROUS_GRANT",
            f"Agent '{agent.name}' has dangerous grants with no recent activity: {names}.",
        )
    return None


def rule_mcp_over_connection(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """MEDIUM: more than 3 MCP connections with no description on the agent."""
    if len(connections) > 3 and not agent.description:
        return _make_finding(
            agent.id,
            "MEDIUM",
            "MCP_OVER_CONNECTION",
            f"Agent '{agent.name}' has {len(connections)} MCP connections but no description. "
            "Uncharacterized agents with many external connections increase attack surface.",
        )
    return None


def rule_credential_scope_mismatch(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """MEDIUM: admin-scoped grant that has never been used in the past 7 days."""
    unused_admin = [g for g in grants if g.scope == "admin" and g.call_count_7d == 0]
    if unused_admin:
        names = ", ".join(g.tool_name for g in unused_admin)
        return _make_finding(
            agent.id,
            "MEDIUM",
            "CREDENTIAL_SCOPE_MISMATCH",
            f"Agent '{agent.name}' holds admin grants with zero calls in the last 7 days: {names}.",
        )
    return None


def rule_missing_rate_limit(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """LOW: dangerous grant with no rate limit configured."""
    unlimited = [g for g in grants if g.is_dangerous and g.rate_limit_per_hour is None]
    if unlimited:
        names = ", ".join(g.tool_name for g in unlimited)
        return _make_finding(
            agent.id,
            "LOW",
            "MISSING_RATE_LIMIT",
            f"Agent '{agent.name}' has dangerous grants without rate limits: {names}.",
        )
    return None


ALL_RULES = [
    rule_exfiltration_path,
    rule_privilege_excess,
    rule_unused_dangerous_grant,
    rule_mcp_over_connection,
    rule_credential_scope_mismatch,
    rule_missing_rate_limit,
]


def run_all_rules(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> list[Finding]:
    """Run all posture rules and return the non-None findings."""
    results: list[Finding] = []
    for rule_fn in ALL_RULES:
        finding = rule_fn(agent, grants, connections)
        if finding is not None:
            results.append(finding)
    return results

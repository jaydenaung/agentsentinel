"""Posture rule engine — thirteen static rules that produce Findings."""

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
_CODE_EXEC_KEYWORDS = {"exec", "bash", "shell", "run_code", "eval", "terminal", "subprocess", "python_repl"}
_SECRETS_KEYWORDS = {"secret", "credential", "vault", "token", "password", "api_key", "read_env"}
_ADMIN_KEYWORDS = {"admin", "iam", "role", "permission", "policy", "sudo", "privilege"}
_INFRA_KEYWORDS = {"deploy", "container", "k8s", "kubernetes", "aws", "gcp", "azure", "terraform"}
_WEB_READ_KEYWORDS = {"http", "fetch", "url", "web", "scrape", "browse", "request"}


def _tool_matches(tool_name: str, keywords: set[str]) -> bool:
    lower = tool_name.lower()
    return any(kw in lower for kw in keywords)


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


def rule_code_execution_grant(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """CRITICAL: agent holds code execution grants — arbitrary code paths enable host compromise."""
    exec_grants = [g for g in grants if _tool_matches(g.tool_name, _CODE_EXEC_KEYWORDS)]
    if exec_grants:
        names = ", ".join(g.tool_name for g in exec_grants)
        return _make_finding(
            agent.id,
            "CRITICAL",
            "CODE_EXECUTION_GRANT",
            f"Agent '{agent.name}' holds code-execution grants ({names}). "
            "Arbitrary code execution enables full host compromise. Apply strict sandboxing.",
        )
    return None


def rule_secrets_access_grant(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: agent holds tools that access secrets, vaults, or credentials at runtime."""
    secrets_grants = [g for g in grants if _tool_matches(g.tool_name, _SECRETS_KEYWORDS)]
    if secrets_grants:
        names = ", ".join(g.tool_name for g in secrets_grants)
        return _make_finding(
            agent.id,
            "HIGH",
            "SECRETS_ACCESS_GRANT",
            f"Agent '{agent.name}' holds secrets-access grants ({names}). "
            "Verify the agent requires runtime credential access; use scoped vault policies.",
        )
    return None


def rule_prompt_injection_vector(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: agent reads from web (untrusted input) and holds write grants — injection-to-write path."""
    has_web_read = any(_tool_matches(g.tool_name, _WEB_READ_KEYWORDS) for g in grants)
    write_grants = [g for g in grants if g.scope in ("write", "admin")]
    if has_web_read and write_grants:
        names = ", ".join(g.tool_name for g in write_grants)
        return _make_finding(
            agent.id,
            "HIGH",
            "PROMPT_INJECTION_VECTOR",
            f"Agent '{agent.name}' reads from web sources and holds write grants ({names}). "
            "Prompt injection in fetched content could redirect write operations.",
        )
    return None


def rule_lateral_movement_path(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: agent combines admin/IAM grants with infrastructure grants — lateral movement risk."""
    admin_grants = [g for g in grants if _tool_matches(g.tool_name, _ADMIN_KEYWORDS)]
    infra_grants = [g for g in grants if _tool_matches(g.tool_name, _INFRA_KEYWORDS)]
    if admin_grants and infra_grants:
        admin_names = ", ".join(g.tool_name for g in admin_grants)
        infra_names = ", ".join(g.tool_name for g in infra_grants)
        return _make_finding(
            agent.id,
            "HIGH",
            "LATERAL_MOVEMENT_PATH",
            f"Agent '{agent.name}' holds admin grants ({admin_names}) alongside infrastructure "
            f"grants ({infra_names}). Separation of duty violation — lateral movement risk.",
        )
    return None


def rule_unbounded_file_access(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: agent holds filesystem write grants with no scoped description."""
    fs_write = [
        g for g in grants
        if any(kw in g.tool_name.lower() for kw in {"write_file", "delete_file", "move_file", "filesystem"})
        and g.scope in ("write", "admin")
    ]
    if fs_write and not agent.description:
        names = ", ".join(g.tool_name for g in fs_write)
        return _make_finding(
            agent.id,
            "HIGH",
            "UNBOUNDED_FILE_ACCESS",
            f"Agent '{agent.name}' holds filesystem write grants ({names}) with no description. "
            "Without a declared scope, write access is effectively unbounded.",
        )
    return None


def rule_insecure_mcp_connection(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """HIGH: MCP connection using plain HTTP (not HTTPS) — credentials and data sent in the clear."""
    insecure = [c for c in connections if c.server_url.startswith("http://")]
    if insecure:
        endpoints = ", ".join(c.server_url for c in insecure)
        return _make_finding(
            agent.id,
            "HIGH",
            "INSECURE_MCP_CONNECTION",
            f"Agent '{agent.name}' connects to MCP endpoints over plain HTTP: {endpoints}. "
            "Use HTTPS to prevent credential interception.",
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


def rule_tool_sprawl(
    agent: Agent,
    grants: list[ToolGrant],
    connections: list[McpConnection],
) -> Finding | None:
    """MEDIUM: agent holds an excessive number of grants — blast radius scales with sprawl."""
    if len(grants) > 15:
        return _make_finding(
            agent.id,
            "MEDIUM",
            "TOOL_SPRAWL",
            f"Agent '{agent.name}' holds {len(grants)} tool grants. "
            "Excessive grants increase blast radius. Apply least-privilege — remove what isn't used.",
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
    # CRITICAL
    rule_exfiltration_path,
    rule_code_execution_grant,
    # HIGH
    rule_secrets_access_grant,
    rule_prompt_injection_vector,
    rule_lateral_movement_path,
    rule_unbounded_file_access,
    rule_insecure_mcp_connection,
    rule_privilege_excess,
    rule_unused_dangerous_grant,
    # MEDIUM
    rule_tool_sprawl,
    rule_mcp_over_connection,
    rule_credential_scope_mismatch,
    # LOW
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

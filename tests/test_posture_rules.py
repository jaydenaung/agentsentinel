"""Tests for all six posture rules — trigger and clean cases."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agentsentinel.models.agent import Agent, McpConnection, ToolGrant
from agentsentinel.posture.rules import (
    rule_credential_scope_mismatch,
    rule_exfiltration_path,
    rule_missing_rate_limit,
    rule_mcp_over_connection,
    rule_privilege_excess,
    rule_unused_dangerous_grant,
)


def make_agent(**kwargs) -> Agent:
    """Build an Agent instance without persisting it."""
    defaults = dict(
        id=uuid.uuid4(),
        name="test-agent",
        agent_type="llm_agent",
        model="claude-sonnet-4-6",
        owner_team="platform",
        description=None,
        status="WATCH",
    )
    defaults.update(kwargs)
    return Agent(**defaults)


def make_grant(**kwargs) -> ToolGrant:
    """Build a ToolGrant without persisting it."""
    defaults = dict(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool_name="some_tool",
        scope=None,
        is_dangerous=False,
        call_count_7d=5,
        last_called_at=datetime.now(tz=timezone.utc),
        rate_limit_per_hour=None,
    )
    defaults.update(kwargs)
    return ToolGrant(**defaults)


def make_mcp(**kwargs) -> McpConnection:
    """Build an McpConnection without persisting it."""
    defaults = dict(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        server_name="test-server",
        server_url="https://mcp.example.com",
        capabilities=["read"],
    )
    defaults.update(kwargs)
    return McpConnection(**defaults)


# ── EXFILTRATION_PATH ────────────────────────────────────────────────────────

class TestExfiltrationPath:
    def test_triggers_with_read_and_write_grants(self):
        agent = make_agent()
        grants = [
            make_grant(tool_name="database_read"),
            make_grant(tool_name="s3_write"),
        ]
        finding = rule_exfiltration_path(agent, grants, [])
        assert finding is not None
        assert finding.rule_id == "EXFILTRATION_PATH"
        assert finding.severity == "CRITICAL"

    def test_clean_with_only_read(self):
        agent = make_agent()
        grants = [make_grant(tool_name="database_read")]
        assert rule_exfiltration_path(agent, grants, []) is None

    def test_clean_with_only_write(self):
        agent = make_agent()
        grants = [make_grant(tool_name="s3_write")]
        assert rule_exfiltration_path(agent, grants, []) is None

    def test_clean_with_no_grants(self):
        assert rule_exfiltration_path(make_agent(), [], []) is None


# ── PRIVILEGE_EXCESS ─────────────────────────────────────────────────────────

class TestPrivilegeExcess:
    def test_triggers_admin_on_read_agent(self):
        agent = make_agent(description="This agent searches and queries the CRM")
        grants = [make_grant(tool_name="crm_tool", scope="admin")]
        finding = rule_privilege_excess(agent, grants, [])
        assert finding is not None
        assert finding.rule_id == "PRIVILEGE_EXCESS"

    def test_triggers_write_on_view_agent(self):
        agent = make_agent(description="View-only dashboard agent")
        grants = [make_grant(tool_name="db_write", scope="write")]
        finding = rule_privilege_excess(agent, grants, [])
        assert finding is not None

    def test_clean_no_description(self):
        agent = make_agent(description=None)
        grants = [make_grant(scope="admin")]
        assert rule_privilege_excess(agent, grants, []) is None

    def test_clean_non_read_description(self):
        agent = make_agent(description="Deploys and manages infrastructure")
        grants = [make_grant(scope="admin")]
        assert rule_privilege_excess(agent, grants, []) is None

    def test_clean_read_description_read_scope(self):
        agent = make_agent(description="Searches product catalog")
        grants = [make_grant(scope="read")]
        assert rule_privilege_excess(agent, grants, []) is None


# ── UNUSED_DANGEROUS_GRANT ───────────────────────────────────────────────────

class TestUnusedDangerousGrant:
    def test_triggers_never_called(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=True, last_called_at=None)]
        finding = rule_unused_dangerous_grant(agent, grants, [])
        assert finding is not None
        assert finding.rule_id == "UNUSED_DANGEROUS_GRANT"

    def test_triggers_stale_call(self):
        agent = make_agent()
        old_ts = datetime.now(tz=timezone.utc) - timedelta(days=31)
        grants = [make_grant(is_dangerous=True, last_called_at=old_ts)]
        assert rule_unused_dangerous_grant(agent, grants, []) is not None

    def test_clean_recently_called(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=True, last_called_at=datetime.now(tz=timezone.utc))]
        assert rule_unused_dangerous_grant(agent, grants, []) is None

    def test_clean_not_dangerous(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=False, last_called_at=None)]
        assert rule_unused_dangerous_grant(agent, grants, []) is None


# ── MCP_OVER_CONNECTION ──────────────────────────────────────────────────────

class TestMcpOverConnection:
    def test_triggers_four_connections_no_description(self):
        agent = make_agent(description=None)
        connections = [make_mcp() for _ in range(4)]
        finding = rule_mcp_over_connection(agent, [], connections)
        assert finding is not None
        assert finding.rule_id == "MCP_OVER_CONNECTION"

    def test_clean_four_connections_with_description(self):
        agent = make_agent(description="Well-documented agent")
        connections = [make_mcp() for _ in range(4)]
        assert rule_mcp_over_connection(agent, [], connections) is None

    def test_clean_three_connections_no_description(self):
        agent = make_agent(description=None)
        connections = [make_mcp() for _ in range(3)]
        assert rule_mcp_over_connection(agent, [], connections) is None


# ── CREDENTIAL_SCOPE_MISMATCH ────────────────────────────────────────────────

class TestCredentialScopeMismatch:
    def test_triggers_admin_unused(self):
        agent = make_agent()
        grants = [make_grant(scope="admin", call_count_7d=0)]
        finding = rule_credential_scope_mismatch(agent, grants, [])
        assert finding is not None
        assert finding.rule_id == "CREDENTIAL_SCOPE_MISMATCH"

    def test_clean_admin_with_calls(self):
        agent = make_agent()
        grants = [make_grant(scope="admin", call_count_7d=10)]
        assert rule_credential_scope_mismatch(agent, grants, []) is None

    def test_clean_non_admin_zero_calls(self):
        agent = make_agent()
        grants = [make_grant(scope="read", call_count_7d=0)]
        assert rule_credential_scope_mismatch(agent, grants, []) is None


# ── MISSING_RATE_LIMIT ───────────────────────────────────────────────────────

class TestMissingRateLimit:
    def test_triggers_dangerous_no_limit(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=True, rate_limit_per_hour=None)]
        finding = rule_missing_rate_limit(agent, grants, [])
        assert finding is not None
        assert finding.rule_id == "MISSING_RATE_LIMIT"
        assert finding.severity == "LOW"

    def test_clean_dangerous_with_limit(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=True, rate_limit_per_hour=100)]
        assert rule_missing_rate_limit(agent, grants, []) is None

    def test_clean_not_dangerous(self):
        agent = make_agent()
        grants = [make_grant(is_dangerous=False, rate_limit_per_hour=None)]
        assert rule_missing_rate_limit(agent, grants, []) is None

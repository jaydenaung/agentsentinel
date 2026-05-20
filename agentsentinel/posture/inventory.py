"""Permission inventory builder — summarises an agent's effective permissions."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.agent import McpConnection, ToolGrant


async def build_inventory(agent_id: uuid.UUID, db: AsyncSession) -> dict:
    """Return a structured inventory of all grants and MCP connections for an agent."""
    grants_result = await db.execute(select(ToolGrant).where(ToolGrant.agent_id == agent_id))
    grants = grants_result.scalars().all()

    connections_result = await db.execute(
        select(McpConnection).where(McpConnection.agent_id == agent_id)
    )
    connections = connections_result.scalars().all()

    return {
        "agent_id": str(agent_id),
        "tool_grants": [
            {
                "tool_name": g.tool_name,
                "scope": g.scope,
                "is_dangerous": g.is_dangerous,
                "call_count_7d": g.call_count_7d,
                "rate_limit_per_hour": g.rate_limit_per_hour,
            }
            for g in grants
        ],
        "mcp_connections": [
            {
                "server_name": c.server_name,
                "server_url": c.server_url,
                "capabilities": c.capabilities,
            }
            for c in connections
        ],
        "dangerous_grant_count": sum(1 for g in grants if g.is_dangerous),
        "admin_grant_count": sum(1 for g in grants if g.scope == "admin"),
    }

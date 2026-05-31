"""CRUD endpoints for agents, tool grants, and MCP connections."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agentsentinel.auth import require_admin, require_read
from agentsentinel.database import get_db
from agentsentinel.models.agent import Agent, McpConnection, ToolGrant
from agentsentinel.schemas.agent import (
    AgentCreate,
    AgentDetailResponse,
    AgentResponse,
    McpConnectionCreate,
    McpConnectionResponse,
    ToolGrantCreate,
    ToolGrantResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])
log = structlog.get_logger(__name__)

# Tool classification patterns — duplicated from cli/scanner.py intentionally
# (separate package; avoids cross-package import coupling)
_WRITE_PATTERNS = frozenset({
    "write", "edit", "create", "delete", "remove", "move", "rename",
    "execute", "run", "exec", "patch", "update", "insert", "drop",
    "truncate", "send", "post", "put", "upload", "deploy", "reset", "kill",
})
_DANGEROUS_PATTERNS = frozenset({
    "delete", "remove", "drop", "truncate", "execute", "run", "exec",
    "send", "deploy", "reset", "kill",
})


def _classify_tool(name: str) -> tuple[str, bool]:
    """Derive (scope, is_dangerous) from a tool name server-side.

    Callers must not supply these values — server-side derivation prevents
    agents from self-classifying dangerous tools as safe to bypass posture rules.
    """
    lower = name.lower()
    is_dangerous = any(p in lower for p in _DANGEROUS_PATTERNS)
    is_write = is_dangerous or any(p in lower for p in _WRITE_PATTERNS)
    return ("write" if is_write else "read"), is_dangerous


@router.post("", response_model=AgentResponse, status_code=201,
             dependencies=[Depends(require_admin)])
async def create_agent(
    body: AgentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Agent:
    """Register a new agent for monitoring."""
    agent = Agent(**body.model_dump())
    db.add(agent)
    await db.flush()
    log.info("agent.created", agent_id=str(agent.id), name=agent.name)
    return agent


@router.get("", response_model=list[AgentResponse],
            dependencies=[Depends(require_read)])
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    owner_team: Annotated[str | None, Query()] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Agent]:
    """List registered agents with optional filtering. Paginated."""
    stmt = select(Agent)
    if status:
        stmt = stmt.where(Agent.status == status)
    if owner_team:
        stmt = stmt.where(Agent.owner_team == owner_team)
    stmt = stmt.order_by(Agent.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentDetailResponse,
            dependencies=[Depends(require_read)])
async def get_agent(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Agent:
    """Fetch a single agent with its grants, connections, and latest findings."""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.grants), selectinload(Agent.mcp_connections))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/grants", response_model=ToolGrantResponse, status_code=201,
             dependencies=[Depends(require_admin)])
async def add_grant(
    agent_id: uuid.UUID,
    body: ToolGrantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolGrant:
    """Add a tool grant to an agent.

    scope and is_dangerous are derived server-side from the tool name —
    any caller-supplied values would be ignored even if the schema accepted them.
    """
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    scope, is_dangerous = _classify_tool(body.tool_name)
    grant = ToolGrant(
        agent_id=agent_id,
        tool_name=body.tool_name,
        scope=scope,
        is_dangerous=is_dangerous,
        rate_limit_per_hour=body.rate_limit_per_hour,
    )
    db.add(grant)
    await db.flush()
    return grant


@router.post("/{agent_id}/mcp", response_model=McpConnectionResponse, status_code=201,
             dependencies=[Depends(require_admin)])
async def add_mcp_connection(
    agent_id: uuid.UUID,
    body: McpConnectionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> McpConnection:
    """Add an MCP server connection to an agent."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    conn = McpConnection(agent_id=agent_id, **body.model_dump())
    db.add(conn)
    await db.flush()
    return conn

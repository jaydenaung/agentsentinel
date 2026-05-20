"""CRUD endpoints for agents, tool grants, and MCP connections."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


@router.post("", response_model=AgentResponse, status_code=201)
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


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    owner_team: Annotated[str | None, Query()] = None,
) -> list[Agent]:
    """List all registered agents with optional filtering."""
    stmt = select(Agent)
    if status:
        stmt = stmt.where(Agent.status == status)
    if owner_team:
        stmt = stmt.where(Agent.owner_team == owner_team)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentDetailResponse)
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


@router.post("/{agent_id}/grants", response_model=ToolGrantResponse, status_code=201)
async def add_grant(
    agent_id: uuid.UUID,
    body: ToolGrantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolGrant:
    """Add a tool grant to an agent."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    grant = ToolGrant(agent_id=agent_id, **body.model_dump())
    db.add(grant)
    await db.flush()
    return grant


@router.post("/{agent_id}/mcp", response_model=McpConnectionResponse, status_code=201)
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

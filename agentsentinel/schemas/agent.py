"""Pydantic schemas for Agent, ToolGrant, and McpConnection."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentCreate(BaseModel):
    """Request body for registering a new agent."""

    name: str
    agent_type: str
    model: str
    owner_team: str
    description: str | None = None


class AgentResponse(BaseModel):
    """Full agent representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    agent_type: str
    model: str
    owner_team: str
    description: str | None
    status: str
    trust_score: float | None
    posture_score: float | None
    behavior_score: float | None
    last_scored_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ToolGrantCreate(BaseModel):
    """Request body for adding a ToolGrant to an agent."""

    tool_name: str
    scope: str | None = None
    is_dangerous: bool = False
    rate_limit_per_hour: int | None = None


class ToolGrantResponse(BaseModel):
    """ToolGrant as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    tool_name: str
    scope: str | None
    is_dangerous: bool
    rate_limit_per_hour: int | None
    call_count_7d: int
    last_called_at: datetime | None
    created_at: datetime


class McpConnectionCreate(BaseModel):
    """Request body for adding an MCP server connection."""

    server_name: str
    server_url: str
    capabilities: list[str] | None = None


class McpConnectionResponse(BaseModel):
    """McpConnection as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    server_name: str
    server_url: str
    capabilities: list | None
    created_at: datetime


class AgentDetailResponse(AgentResponse):
    """Agent with its grants, connections, and recent findings."""

    grants: list[ToolGrantResponse] = []
    mcp_connections: list[McpConnectionResponse] = []

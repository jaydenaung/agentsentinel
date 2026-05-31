"""Pydantic schemas for Agent, ToolGrant, and McpConnection."""

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCreate(BaseModel):
    """Request body for registering a new agent."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    agent_type: Annotated[str, Field(min_length=1, max_length=64)]
    model: Annotated[str, Field(min_length=1, max_length=128)]
    owner_team: Annotated[str, Field(min_length=1, max_length=128)]
    description: Annotated[str | None, Field(max_length=1000)] = None


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
    """Request body for adding a ToolGrant to an agent.

    is_dangerous and scope are intentionally excluded — they are derived
    server-side from the tool name to prevent callers from self-classifying
    their tools as safe to bypass posture rules.
    """

    tool_name: Annotated[str, Field(min_length=1, max_length=255)]
    rate_limit_per_hour: Annotated[int | None, Field(ge=1, le=100_000)] = None


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

    server_name: Annotated[str, Field(min_length=1, max_length=255)]
    server_url: Annotated[str, Field(min_length=1, max_length=512)]
    capabilities: list[str] | None = None

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("server_url must use http or https")
        # Block link-local and cloud metadata endpoints
        blocked = ("169.254.", "metadata.google", "::1")
        if any(b in parsed.netloc for b in blocked):
            raise ValueError("server_url cannot point to a link-local or metadata endpoint")
        return v


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

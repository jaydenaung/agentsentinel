"""Agent, ToolGrant, and McpConnection ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from agentsentinel.models.base import Base


class Agent(Base):
    """Represents a registered AI agent under monitoring."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_team: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="WATCH")
    trust_score: Mapped[float | None] = mapped_column(nullable=True)
    posture_score: Mapped[float | None] = mapped_column(nullable=True)
    behavior_score: Mapped[float | None] = mapped_column(nullable=True)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    grants: Mapped[list["ToolGrant"]] = relationship(
        "ToolGrant", back_populates="agent", cascade="all, delete-orphan"
    )
    mcp_connections: Mapped[list["McpConnection"]] = relationship(
        "McpConnection", back_populates="agent", cascade="all, delete-orphan"
    )


class ToolGrant(Base):
    """A permission granting an agent access to a specific tool."""

    __tablename__ = "tool_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    call_count_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_dangerous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limit_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="grants")


class McpConnection(Base):
    """An MCP server connection granted to an agent."""

    __tablename__ = "mcp_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    server_name: Mapped[str] = mapped_column(String(255), nullable=False)
    server_url: Mapped[str] = mapped_column(String(512), nullable=False)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="mcp_connections")

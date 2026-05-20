"""Initial schema with TimescaleDB hypertable for agent_events.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and convert agent_events to a TimescaleDB hypertable."""
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("agent_type", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("owner_team", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="WATCH"),
        sa.Column("trust_score", sa.Float(), nullable=True),
        sa.Column("posture_score", sa.Float(), nullable=True),
        sa.Column("behavior_score", sa.Float(), nullable=True),
        sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tool_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(64), nullable=True),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_dangerous", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rate_limit_per_hour", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mcp_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("server_name", sa.String(255), nullable=False),
        sa.Column("server_url", sa.String(512), nullable=False),
        sa.Column("capabilities", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("anomaly_score", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "timestamp"),
    )
    op.create_index("ix_agent_events_timestamp", "agent_events", ["timestamp"])
    op.create_index("ix_agent_events_agent_id", "agent_events", ["agent_id"])

    # Convert agent_events to a TimescaleDB hypertable partitioned by timestamp
    op.execute(
        "SELECT create_hypertable('agent_events', 'timestamp', if_not_exists => TRUE)"
    )

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("finding_type", sa.String(16), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("mean_calls_per_hour", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("stddev_calls_per_hour", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_baselines_agent_tool", "baselines", ["agent_id", "tool_name"], unique=True)


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("baselines")
    op.drop_table("findings")
    op.drop_table("agent_events")
    op.drop_table("mcp_connections")
    op.drop_table("tool_grants")
    op.drop_table("agents")

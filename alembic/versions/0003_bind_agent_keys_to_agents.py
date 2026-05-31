"""Bind agent-scoped API keys to a specific agent_id.

Adds a nullable agent_id FK column to api_keys. When non-null, the key may
only report events for that specific agent, preventing cross-agent event injection.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add agent_id column and FK to api_keys."""
    op.add_column(
        "api_keys",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_api_keys_agent_id",
        "api_keys",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_api_keys_agent_id", "api_keys", ["agent_id"])


def downgrade() -> None:
    """Remove agent_id column and FK from api_keys."""
    op.drop_index("ix_api_keys_agent_id", table_name="api_keys")
    op.drop_constraint("fk_api_keys_agent_id", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "agent_id")

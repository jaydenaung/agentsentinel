"""Pydantic schemas for API key management."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiKeyCreate(BaseModel):
    """Request body for creating an API key.

    agent_id is required when scope is 'agent' and forbidden otherwise.
    This binding ensures each agent-scoped key can only report events for
    its designated agent, preventing cross-agent event injection.
    """

    name: Annotated[str, Field(min_length=1, max_length=255)]
    scope: Literal["admin", "agent", "readonly"]
    agent_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_agent_id_scope(self) -> "ApiKeyCreate":
        if self.scope == "agent" and self.agent_id is None:
            raise ValueError("agent_id is required when scope is 'agent'")
        if self.scope != "agent" and self.agent_id is not None:
            raise ValueError("agent_id may only be set when scope is 'agent'")
        return self


class ApiKeyResponse(BaseModel):
    """API key metadata — never includes the hash or full plaintext key."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    scope: str
    agent_id: uuid.UUID | None
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned once at creation — includes the full plaintext key.

    The plaintext key is NOT stored and cannot be retrieved again.
    """

    key: str

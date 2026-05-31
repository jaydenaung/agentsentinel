"""Pydantic schemas for API key management."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    """Request body for creating an API key."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    scope: Literal["admin", "agent", "readonly"]


class ApiKeyResponse(BaseModel):
    """API key metadata — never includes the hash or full plaintext key."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    scope: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned once at creation — includes the full plaintext key.

    The plaintext key is NOT stored and cannot be retrieved again.
    """

    key: str

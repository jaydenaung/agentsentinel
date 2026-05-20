"""Pydantic schemas for API key management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyCreate(BaseModel):
    """Request body for creating an API key."""

    name: str
    scope: str  # admin | agent | readonly


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

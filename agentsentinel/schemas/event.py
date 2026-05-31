"""Pydantic schemas for AgentEvent ingestion."""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_PATTERN = re.compile(r'^[a-f0-9]{64}$')


class EventIngest(BaseModel):
    """Request body for the event ingestion endpoint."""

    agent_id: uuid.UUID
    tool_name: Annotated[str, Field(min_length=1, max_length=255)]
    input_hash: Annotated[str, Field(min_length=64, max_length=64)]
    output_hash: Annotated[str, Field(min_length=64, max_length=64)]
    duration_ms: Annotated[int | None, Field(ge=0, le=300_000)] = None
    session_id: Annotated[str | None, Field(max_length=255)] = None

    @field_validator("input_hash", "output_hash")
    @classmethod
    def validate_sha256_format(cls, v: str) -> str:
        """Reject anything that is not a valid lowercase hex SHA-256 digest."""
        if not _SHA256_PATTERN.match(v):
            raise ValueError("must be a 64-character lowercase hex SHA-256 digest")
        return v


class EventResponse(BaseModel):
    """Response returned after successful event ingestion."""

    event_id: uuid.UUID
    anomaly_score: float | None
    timestamp: datetime


class EventListItem(BaseModel):
    """A single event row returned by the list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    tool_name: str
    anomaly_score: float | None
    duration_ms: int | None
    session_id: str | None
    timestamp: datetime

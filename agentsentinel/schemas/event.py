"""Pydantic schemas for AgentEvent ingestion."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventIngest(BaseModel):
    """Request body for the event ingestion endpoint."""

    agent_id: uuid.UUID
    tool_name: str
    input_hash: str
    output_hash: str
    duration_ms: int | None = None
    session_id: str | None = None


class EventResponse(BaseModel):
    """Response returned after successful event ingestion."""

    event_id: uuid.UUID
    anomaly_score: float | None
    timestamp: datetime

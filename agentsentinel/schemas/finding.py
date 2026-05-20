"""Pydantic schemas for Finding objects."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FindingResponse(BaseModel):
    """Finding as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    severity: str
    finding_type: str
    rule_id: str
    message: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class FindingStatusUpdate(BaseModel):
    """Request body for PATCH /findings/{id}."""

    status: str

"""Event ingestion endpoint."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.behavior.anomaly import score_event
from agentsentinel.behavior.collector import ingest_event
from agentsentinel.database import get_db
from agentsentinel.dependencies import get_redis
from agentsentinel.models.agent import Agent
from agentsentinel.schemas.event import EventIngest, EventResponse

router = APIRouter(prefix="/events", tags=["events"])
log = structlog.get_logger(__name__)


@router.post("", response_model=EventResponse, status_code=201)
async def ingest(
    body: EventIngest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> EventResponse:
    """Ingest a tool-call event, score it for anomalies, and push to Redis Stream."""
    agent = await db.get(Agent, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    event = await ingest_event(
        agent_id=body.agent_id,
        tool_name=body.tool_name,
        input_hash=body.input_hash,
        output_hash=body.output_hash,
        duration_ms=body.duration_ms,
        session_id=body.session_id,
        db=db,
        redis=redis,
    )

    anomaly_score = await score_event(event, db)
    event.anomaly_score = anomaly_score

    log.info(
        "event.scored",
        event_id=str(event.id),
        anomaly_score=anomaly_score,
    )

    return EventResponse(
        event_id=event.id,
        anomaly_score=anomaly_score,
        timestamp=event.timestamp,
    )

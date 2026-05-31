"""Event ingestion and listing endpoints."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.auth import require_agent, require_read
from agentsentinel.behavior.anomaly import score_event
from agentsentinel.behavior.collector import ingest_event
from agentsentinel.database import get_db
from agentsentinel.dependencies import get_redis
from agentsentinel.models.agent import Agent
from agentsentinel.models.api_key import ApiKey
from agentsentinel.models.event import AgentEvent
from agentsentinel.schemas.event import EventIngest, EventListItem, EventResponse

router = APIRouter(prefix="/events", tags=["events"])
log = structlog.get_logger(__name__)


@router.get("", response_model=list[EventListItem])
async def list_events(
    key: Annotated[ApiKey, Depends(require_read)],
    db: Annotated[AsyncSession, Depends(get_db)],
    agent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[EventListItem]:
    """Return the most recent tool-call events, newest first.

    Non-admin keys must supply agent_id — omitting it would expose events from
    every monitored agent (cross-tenant data leakage). Admin keys may omit
    agent_id to retrieve the global event stream.
    """
    if key.scope in ("readonly", "agent") and agent_id is None:
        raise HTTPException(
            status_code=400,
            detail="agent_id query parameter is required for non-admin keys",
        )

    stmt = (
        select(AgentEvent, Agent.name.label("agent_name"))
        .join(Agent, Agent.id == AgentEvent.agent_id)
        .order_by(AgentEvent.timestamp.desc())
        .limit(limit)
    )
    if agent_id is not None:
        stmt = stmt.where(AgentEvent.agent_id == agent_id)

    rows = (await db.execute(stmt)).all()
    return [
        EventListItem(
            event_id=ev.id,
            agent_id=ev.agent_id,
            agent_name=agent_name,
            tool_name=ev.tool_name,
            anomaly_score=ev.anomaly_score,
            duration_ms=ev.duration_ms,
            session_id=ev.session_id,
            timestamp=ev.timestamp,
        )
        for ev, agent_name in rows
    ]


@router.post("", response_model=EventResponse, status_code=201)
async def ingest(
    body: EventIngest,
    key: Annotated[ApiKey, Depends(require_agent)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> EventResponse:
    """Ingest a tool-call event, score it for anomalies, and push to Redis Stream.

    Agent-scoped keys with a bound agent_id may only report events for that agent.
    """
    if key.scope == "agent" and key.agent_id is not None:
        if body.agent_id != key.agent_id:
            log.warning(
                "event.unauthorized_agent_id",
                key_id=str(key.id),
                key_agent_id=str(key.agent_id),
                body_agent_id=str(body.agent_id),
            )
            raise HTTPException(
                status_code=403,
                detail="API key is not authorised to report events for this agent_id",
            )

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

    log.info("event.scored", event_id=str(event.id), anomaly_score=anomaly_score)

    return EventResponse(
        event_id=event.id,
        anomaly_score=anomaly_score,
        timestamp=event.timestamp,
    )

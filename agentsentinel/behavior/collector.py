"""Event collector — ingests tool-call events and writes them to Redis Streams."""

import json
import uuid
from datetime import datetime, timezone

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)

STREAM_KEY = "agent_events"


async def ingest_event(
    agent_id: uuid.UUID,
    tool_name: str,
    input_hash: str,
    output_hash: str,
    duration_ms: int | None,
    session_id: str | None,
    db: AsyncSession,
    redis: Redis,
) -> AgentEvent:
    """Persist an AgentEvent and push a notification to the Redis Stream."""
    event = AgentEvent(
        agent_id=agent_id,
        tool_name=tool_name,
        input_hash=input_hash,
        output_hash=output_hash,
        duration_ms=duration_ms,
        session_id=session_id,
        timestamp=datetime.now(tz=timezone.utc),
    )
    db.add(event)
    await db.flush()  # populate id without full commit

    payload = {
        "event_id": str(event.id),
        "agent_id": str(agent_id),
        "tool_name": tool_name,
        "timestamp": event.timestamp.isoformat(),
    }
    await redis.xadd(STREAM_KEY, payload)  # type: ignore[arg-type]
    log.info(
        "event.ingested",
        event_id=str(event.id),
        agent_id=str(agent_id),
        tool_name=tool_name,
    )
    return event

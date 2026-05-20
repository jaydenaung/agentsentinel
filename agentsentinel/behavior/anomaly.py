"""Anomaly detector — scores individual tool-call events against baselines."""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.baseline import Baseline
from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)


async def count_calls_last_hour(
    agent_id: uuid.UUID,
    tool_name: str,
    db: AsyncSession,
) -> int:
    """Count how many times this agent called this tool in the last 60 minutes."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    result = await db.execute(
        select(func.count()).where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.tool_name == tool_name,
            AgentEvent.timestamp >= since,
        )
    )
    return result.scalar_one()


async def is_first_ever_call(
    agent_id: uuid.UUID,
    tool_name: str,
    db: AsyncSession,
    exclude_event_id: uuid.UUID | None = None,
) -> bool:
    """Return True if there are no prior AgentEvent rows for this agent+tool pair.

    Pass ``exclude_event_id`` to ignore the event currently being scored (it has
    already been flushed to the session before scoring runs).
    """
    stmt = select(func.count()).where(
        AgentEvent.agent_id == agent_id,
        AgentEvent.tool_name == tool_name,
    )
    if exclude_event_id is not None:
        stmt = stmt.where(AgentEvent.id != exclude_event_id)
    result = await db.execute(stmt)
    return result.scalar_one() == 0


async def score_event(
    event: AgentEvent,
    db: AsyncSession,
) -> float:
    """Compute an anomaly score (0.0–1.0) for a tool-call event.

    Higher scores indicate more suspicious activity. Rules are applied in
    priority order; the highest triggered score is returned.
    """
    agent_id = event.agent_id
    tool_name = event.tool_name

    # Rule: first-ever call to this tool by this agent → highest risk
    # Exclude the current event since it was already flushed before scoring.
    first_call = await is_first_ever_call(agent_id, tool_name, db, exclude_event_id=event.id)
    if first_call:
        log.info(
            "anomaly.first_ever_call",
            agent_id=str(agent_id),
            tool_name=tool_name,
            score=0.9,
        )
        return 0.9

    # Fetch baseline
    result = await db.execute(
        select(Baseline).where(
            Baseline.agent_id == agent_id,
            Baseline.tool_name == tool_name,
        )
    )
    baseline = result.scalar_one_or_none()

    if baseline is None or baseline.sample_count == 0:
        log.info(
            "anomaly.no_baseline",
            agent_id=str(agent_id),
            tool_name=tool_name,
            score=0.7,
        )
        return 0.7

    calls_last_hour = await count_calls_last_hour(agent_id, tool_name, db)
    mean = baseline.mean_calls_per_hour
    stddev = baseline.stddev_calls_per_hour

    threshold_3sigma = mean + (3 * stddev)
    threshold_2sigma = mean + (2 * stddev)

    if stddev > 0 and calls_last_hour > threshold_3sigma:
        log.info(
            "anomaly.high_frequency_3sigma",
            agent_id=str(agent_id),
            tool_name=tool_name,
            calls=calls_last_hour,
            threshold=threshold_3sigma,
            score=0.8,
        )
        return 0.8

    if stddev > 0 and calls_last_hour > threshold_2sigma:
        log.info(
            "anomaly.high_frequency_2sigma",
            agent_id=str(agent_id),
            tool_name=tool_name,
            calls=calls_last_hour,
            threshold=threshold_2sigma,
            score=0.5,
        )
        return 0.5

    return 0.0

"""Behavior score calculator — aggregates recent anomaly scores into 0–100."""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.agent import Agent
from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)


async def compute_behavior_score(agent_id: uuid.UUID, db: AsyncSession) -> float:
    """Compute a behavior score (0–100) from anomaly scores in the last 24 hours.

    Score = (1 - mean_anomaly_score) * 100.
    Returns the agent's last known behavior_score (or 75) when no recent events exist.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    result = await db.execute(
        select(AgentEvent.anomaly_score).where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.timestamp >= since,
            AgentEvent.anomaly_score.is_not(None),
        )
    )
    scores = [row[0] for row in result.all()]

    if not scores:
        agent = await db.get(Agent, agent_id)
        fallback = agent.behavior_score if (agent and agent.behavior_score is not None) else 75.0
        log.info(
            "behavior_score.no_recent_events",
            agent_id=str(agent_id),
            fallback=fallback,
        )
        return fallback

    mean_anomaly = sum(scores) / len(scores)
    behavior_score = (1.0 - mean_anomaly) * 100.0
    log.info(
        "behavior_score.computed",
        agent_id=str(agent_id),
        mean_anomaly=mean_anomaly,
        behavior_score=behavior_score,
    )
    return behavior_score

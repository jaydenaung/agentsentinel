"""Trust score compositor — combines posture, behavior, and recency into Trust Score."""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.behavior.scoring import compute_behavior_score
from agentsentinel.models.agent import Agent
from agentsentinel.models.event import AgentEvent
from agentsentinel.models.finding import Finding
from agentsentinel.posture.scanner import run_posture_scan

log = structlog.get_logger(__name__)


def derive_status(score: float) -> str:
    """Map a numeric trust score to a status label."""
    match True:
        case _ if score >= 80:
            return "TRUSTED"
        case _ if score >= 60:
            return "WATCH"
        case _ if score >= 40:
            return "ALERT"
        case _:
            return "CRITICAL"


async def _recency_bonus(agent_id: uuid.UUID, db: AsyncSession) -> float:
    """Return 10 if the agent was seen in the last 5 minutes, else 0."""
    since = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    result = await db.execute(
        select(func.count()).where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.timestamp >= since,
        )
    )
    count = result.scalar_one()
    return 10.0 if count > 0 else 0.0


async def compute_trust_score(agent_id: uuid.UUID, db: AsyncSession) -> dict:
    """Run a full trust score recomputation and persist results to the Agent row.

    Returns a dict with trust_score, posture_score, behavior_score, status,
    and findings_count.
    """
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    posture_score = float(await run_posture_scan(agent_id, db))
    behavior_score = await compute_behavior_score(agent_id, db)
    recency = await _recency_bonus(agent_id, db)

    trust_score = (posture_score * 0.45) + (behavior_score * 0.45) + recency
    trust_score = min(100.0, max(0.0, trust_score))
    status = derive_status(trust_score)

    agent.posture_score = posture_score
    agent.behavior_score = behavior_score
    agent.trust_score = trust_score
    agent.status = status
    agent.last_scored_at = datetime.now(tz=timezone.utc)

    findings_result = await db.execute(
        select(func.count()).where(
            Finding.agent_id == agent_id,
            Finding.status == "OPEN",
        )
    )
    findings_count = findings_result.scalar_one()

    log.info(
        "trust_score.computed",
        agent_id=str(agent_id),
        trust_score=trust_score,
        posture=posture_score,
        behavior=behavior_score,
        recency=recency,
        status=status,
    )

    return {
        "trust_score": trust_score,
        "posture_score": posture_score,
        "behavior_score": behavior_score,
        "recency_bonus": recency,
        "status": status,
        "findings_count": findings_count,
    }
